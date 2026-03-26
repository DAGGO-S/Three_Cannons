"""
self_play_generator.py - 双方 AI 自对弈批量数据生成器

策略：
  - 炮方/兵方可独立设置搜索深度（--depth-cannon / --depth-soldier）
  - epsilon-greedy 随机：每步有概率随机走，提供局面多样性
  - 重复局面超过 2 次时强制随机，避免循环
  - 每局结束后追加写入 JSONL，支持中断后断点续跑

用法：
    # 炮 depth=8，兵 depth=6，跑 10000 局
    python scripts/self_play_generator.py --depth-cannon 8 --depth-soldier 6 --games 10000

    # 断点续跑（指定同一个 output 文件）
    python scripts/self_play_generator.py --output data/selfplay/run1.jsonl --games 10000
"""
import sys
import os
import json
import time
import random
import argparse
import collections
import threading
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.game_logic import GameState, CANNON, SOLDIER, DRAW, EMPTY
from core.evaluation_logic import evaluate_board
from core.search_manager import find_best_move_iterative_deepening, find_best_move_parallel, clear_transposition_table

# ── 默认配置（直接在这里改，无需记命令行参数）──────────────────────────────
CONFIG = {
    "games":         5000,   # 目标局数 (Run4 - 智能探索时代)
    "depth_cannon":  8,      # 炮方搜索深度
    "depth_soldier": 8,     # 兵方搜索深度 
    "temperature":   0.7,    # Softmax 温度系数
    "use_nnue":      True,   # 开启 NNUE 评估
    "output":        "data/selfplay/run3.jsonl",
    "max_moves":     150,
}
# ────────────────────────────────────────────────────────────────────────────


# ── 断点文件 ─────────────────────────────────────────────────────────────────

CHECKPOINT_SUFFIX = ".checkpoint.json"


def load_checkpoint(out_path):
    cp_path = out_path + CHECKPOINT_SUFFIX
    if os.path.exists(cp_path):
        with open(cp_path, encoding="utf-8") as f:
            return json.load(f)
    return None


def save_checkpoint(out_path, stats):
    cp_path = out_path + CHECKPOINT_SUFFIX
    with open(cp_path, "w", encoding="utf-8") as f:
        json.dump(stats, f)


def delete_checkpoint(out_path):
    cp_path = out_path + CHECKPOINT_SUFFIX
    if os.path.exists(cp_path):
        os.remove(cp_path)


# ── 对局逻辑 ─────────────────────────────────────────────────────────────────

def get_all_valid_moves(state: GameState):
    moves = []
    player = state.current_player
    for r in range(5):
        for c in range(5):
            if state.board[r][c] == player:
                for (tr, tc) in state.get_valid_moves(r, c):
                    moves.append(((r, c), (tr, tc)))
    return moves


def ai_choose_move(state, depth, tau, pos_counts, game_history=None, num_threads=1):
    all_moves = get_all_valid_moves(state)
    if not all_moves:
        return None, 0.0

    # 1. 强制随机打破重复局面 (保留作为安全垫)
    if pos_counts.get(state.hash, 0) >= 2:
        return random.choice(all_moves), 0.0

    # 2. AI 搜索获取全局统计
    clear_transposition_table()
    stop_event = threading.Event()
    settings = {
        "depth": depth,
        "time_limit": 60.0,
        "stop_event": stop_event,
        "analysis_mode": False,
        "num_threads": num_threads,
        "use_nnue": CONFIG["use_nnue"]
    }
    is_maximizing = (state.current_player == CANNON)
    
    # 扩展搜索接口以返回所有合法走法的分值
    if num_threads > 1:
        move, score, stats = find_best_move_parallel(
            state, settings, is_maximizing, progress_callback=None, return_score=True, 
            game_history=game_history, return_all_stats=True
        )
    else:
        move, score, stats = find_best_move_iterative_deepening(
            state, settings, is_maximizing, progress_callback=None, return_score=True, 
            game_history=game_history, return_all_stats=True
        )

    if not move:
        return random.choice(all_moves), 0.0

    # 3. Softmax 采样逻辑
    import numpy as np
    
    moves_list = list(stats.keys())
    scores_list = np.array(list(stats.values()), dtype=np.float64)
    
    # 对兵方分值取反，使 Softmax 始终在“好走法”上分布更高
    if not is_maximizing:
        scores_list = -scores_list

    # 负分截断 (Pruning): 过滤掉比最高分低 300 点以上的智障走法
    max_s = np.max(scores_list)
    mask = scores_list >= (max_s - 300.0)
    
    filtered_moves = [moves_list[i] for i in range(len(moves_list)) if mask[i]]
    filtered_scores = scores_list[mask]

    if not filtered_moves:
        # 理论上不会发生，保底回归 Greedy
        return move, score

    # 计算 Softmax
    # 减去最大值防止指数爆炸
    exp_scores = np.exp((filtered_scores - max_s) / tau)
    probs = exp_scores / np.sum(exp_scores)

    # 采样
    chosen_idx = np.random.choice(len(filtered_moves), p=probs)
    chosen_move = filtered_moves[chosen_idx]
    
    # 如果选中的是最佳走法，直接沿用搜索分；否则返回该变着对应的分值
    chosen_score = stats[chosen_move]
    
    return chosen_move, chosen_score


def play_one_game(depth_cannon, depth_soldier, tau, max_moves=150, num_threads=1):
    """
    进行一局自对弈。max_moves 超出按和棋处理。
    胜负判定由引擎 GameState._check_winner() 统一负责。
    """
    state = GameState()
    history = [state]
    game_history = [] # 存储哈希历史，用于透传给搜索内核
    pos_counts = collections.Counter()
    pos_counts[state.hash] += 1
    game_history.append(state.hash)

    for _ in range(max_moves):
        # 如果引擎自然结束
        if state.winner != -1:
            break
            
        # 训练加速：兵数量 <= 4 视为炮方已获胜（残局裁定）
        if state.soldier_count <= 4:
            state.winner = CANNON
            break

        # 根据当前行棋方选择深度
        depth = depth_cannon if state.current_player == CANNON else depth_soldier
        move, score = ai_choose_move(state, depth, tau, pos_counts, game_history=game_history, num_threads=num_threads)
        if move is None:
            break

        history.append((state, score))
        
        start, end = move
        is_capture = state.board[end[0]][end[1]] != EMPTY
        state = state.move_piece(start[0], start[1], end[0], end[1])

        if is_capture:
            pos_counts.clear()
            # 捕获发生后，通常不再视之前的局面为同一个循环（虽然哈希可能相同，但棋子数变了）
        pos_counts[state.hash] += 1
        game_history.append(state.hash)

        if pos_counts[state.hash] >= 3:
            # 【同步系统级新规】三复局面根据兵力判胜负
            sc = state.soldier_count
            if sc <= 8:
                state.winner = CANNON
            elif sc == 9:
                state.winner = DRAW
            else:
                state.winner = SOLDIER
            break

    if state.winner == -1:
        # 【局后裁定】到达最大步数上限，按兵力判胜负和
        sc = state.soldier_count
        if sc <= 8:
            state.winner = CANNON
        elif sc == 9:
            state.winner = DRAW
        else:
            state.winner = SOLDIER

    winner = state.winner
    return history, winner


def export_game_to_jsonl(history, winner, filepath):
    outcome = 1.0 if winner == CANNON else (0.0 if winner == SOLDIER else 0.5)
    lines = []
    for item in history:
        # 此时 item 可能是 (state, search_score)
        if isinstance(item, tuple):
            state, eval_score = item
        else:
            state = item
            res = evaluate_board(state)
            eval_score = float(res[0] if isinstance(res, tuple) else res)
            
        lines.append(json.dumps({
            "fen": state.to_fen(),
            "eval": eval_score,
            "game_outcome": outcome,
            "soldier_count": state.soldier_count
        }))
    with open(filepath, 'a', encoding='utf-8') as f:
        f.write('\n'.join(lines) + '\n')


# ── 主程序 ───────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description='三炮十五兵 AI 自对弈数据生成器',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
默认配置：炮方深度=8  兵方深度=6  epsilon=0.15  局数=10000
断点续距：指定相同的 --output 文件路径即可从中断处继续
示例：
  一键运行        : python scripts/self_play_generator.py
  自定义参数   : python scripts/self_play_generator.py --depth-cannon 10 --games 5000
  断点续距   : python scripts/self_play_generator.py --output data/selfplay/run1.jsonl
        """
    )
    parser.add_argument('--games',         type=int,   default=CONFIG["games"],         help=f'目标总局数 (默认 {CONFIG["games"]})')
    parser.add_argument('--depth-cannon',  type=int,   default=CONFIG["depth_cannon"],  help=f'炮方搜索深度 (默认 {CONFIG["depth_cannon"]})')
    parser.add_argument('--depth-soldier', type=int,   default=CONFIG["depth_soldier"], help=f'兵方搜索深度 (默认 {CONFIG["depth_soldier"]})')
    parser.add_argument('--tau',           type=float, default=CONFIG["temperature"],   help=f'Softmax 温度系数 (默认 {CONFIG["temperature"]})')
    parser.add_argument('--output',        type=str,   default=CONFIG["output"],        help=f'输出 JSONL 路径 (默认 {CONFIG["output"]})')
    parser.add_argument('--threads',       type=int,   default=1,                       help='并行线程数 (默认 1)')
    parser.add_argument('--nnue',          action='store_true', default=CONFIG["use_nnue"], help='是否开启 NNUE 评估 (默认开启)')
    parser.add_argument('--no-nnue',       action='store_false', dest='nnue',              help='显式关闭 NNUE 评估')
    args = parser.parse_args()

    dc = args.depth_cannon
    ds = args.depth_soldier

    # 输出路径：相对路径以项目根目录为基准
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    out_path = args.output if os.path.isabs(args.output) else os.path.join(root, args.output)
    os.makedirs(os.path.dirname(out_path), exist_ok=True)


    # 断点续跑
    cp = load_checkpoint(out_path)
    if cp:
        start_game = cp["games_done"] + 1
        cannon_wins  = cp["cannon_wins"]
        soldier_wins = cp["soldier_wins"]
        draws        = cp["draws"]
        total_positions = cp["total_positions"]
        print(f"[续跑] 从第 {start_game} 局开始 (已完成 {cp['games_done']} 局)")
    else:
        start_game = 1
        cannon_wins = soldier_wins = draws = total_positions = 0

    print(f"[自对弈生成器]  目标={args.games}局  炮深度={dc}  兵深度={ds}  tau={args.tau}  NNUE={args.nnue}")
    
    # 将全局配置同步为命令行参数（确保 ai_choose_move 使用正确设置）
    CONFIG["use_nnue"] = args.nnue
    print(f"[输出文件] {out_path}")
    print("=" * 70)

    start_total = time.time()

    for game_idx in range(start_game, args.games + 1):
        t0 = time.time()
        history, winner = play_one_game(
            dc, ds, args.tau,
            max_moves=CONFIG["max_moves"],
            num_threads=args.threads
        )
        elapsed = time.time() - t0

        export_game_to_jsonl(history, winner, out_path)
        total_positions += len(history)

        if winner == CANNON:    cannon_wins  += 1
        elif winner == SOLDIER: soldier_wins += 1
        else:                   draws        += 1

        done = game_idx - start_game + 1
        avg = (time.time() - start_total) / done
        eta = avg * (args.games - game_idx)
        eta_str = f"{int(eta//3600)}h{int((eta%3600)//60)}m"

        total_done = cannon_wins + soldier_wins + draws
        c_rate = cannon_wins / total_done * 100 if total_done else 0

        print(
            f"局 {game_idx:>5}/{args.games}  "
            f"{'炮' if winner==CANNON else ('兵' if winner==SOLDIER else '和')}胜  "
            f"步={len(history)-1:>3}  {elapsed:.1f}s  "
            f"炮胜率={c_rate:.1f}%  "
            f"[炮{cannon_wins}/兵{soldier_wins}/和{draws}]  "
            f"ETA≈{eta_str}"
        )

        # 每局更新断点
        save_checkpoint(out_path, {
            "games_done":     game_idx,
            "cannon_wins":    cannon_wins,
            "soldier_wins":   soldier_wins,
            "draws":          draws,
            "total_positions": total_positions,
            "output":         out_path,
            "depth_cannon":   dc,
            "depth_soldier":  ds,
        })

    total_elapsed = time.time() - start_total
    print("=" * 70)
    print(f"完成: {args.games} 局  {total_positions} 条局面  耗时 {total_elapsed/3600:.2f}h")
    total_done = cannon_wins + soldier_wins + draws
    print(f"炮胜率={cannon_wins/total_done*100:.1f}%  兵胜率={soldier_wins/total_done*100:.1f}%  和局={draws}")
    print(f"输出: {out_path}")

    delete_checkpoint(out_path)  # 所有局数跑完，删除断点文件


if __name__ == '__main__':
    main()
