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
from core.ai import find_best_move_iterative_deepening, clear_transposition_table

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


def ai_choose_move(state, depth, epsilon, pos_counts):
    all_moves = get_all_valid_moves(state)
    if not all_moves:
        return None

    # 强制随机打破重复局面
    if pos_counts.get(state.hash, 0) >= 2:
        return random.choice(all_moves)

    # epsilon 随机
    if random.random() < epsilon:
        return random.choice(all_moves)

    # AI 搜索
    stop_event = threading.Event()
    settings = {
        "depth": depth,
        "time_limit": 60.0,
        "stop_event": stop_event,
        "analysis_mode": False,
    }
    is_maximizing = (state.current_player == CANNON)
    move = find_best_move_iterative_deepening(
        state, settings, is_maximizing, progress_callback=None
    )
    return move if move else random.choice(all_moves)


def play_one_game(depth_cannon, depth_soldier, epsilon, max_moves=200):
    state = GameState()
    history = [state]
    pos_counts = collections.Counter()
    pos_counts[state.hash] += 1

    for _ in range(max_moves):
        if state.winner != -1:
            break

        # 根据当前行棋方选择深度
        depth = depth_cannon if state.current_player == CANNON else depth_soldier
        move = ai_choose_move(state, depth, epsilon, pos_counts)
        if move is None:
            break

        start, end = move
        is_capture = state.board[end[0]][end[1]] != EMPTY
        state = state.move_piece(start[0], start[1], end[0], end[1])
        history.append(state)

        if is_capture:
            pos_counts.clear()
        pos_counts[state.hash] += 1

        if pos_counts[state.hash] >= 3:
            state.winner = DRAW
            break

    winner = state.winner if state.winner != -1 else DRAW
    return history, winner


def export_game_to_jsonl(history, winner, filepath):
    outcome = 1.0 if winner == CANNON else (0.0 if winner == SOLDIER else 0.5)
    lines = []
    for state in history:
        res = evaluate_board(state)
        eval_score = float(res[0] if isinstance(res, tuple) else res)
        lines.append(json.dumps({
            "fen": state.to_fen(),
            "eval": eval_score,
            "game_outcome": outcome
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
    parser.add_argument('--games',         type=int,   default=10000, help='目标总局数 (默认 10000)')
    parser.add_argument('--depth-cannon',  type=int,   default=8,     help='炮方搜索深度 (默认 8)')
    parser.add_argument('--depth-soldier', type=int,   default=6,     help='兵方搜索深度 (默认 6)')
    parser.add_argument('--epsilon',       type=float, default=0.15,  help='随机走棋概率 (默认 0.15)')
    parser.add_argument('--output',        type=str,   default='',    help='输出 JSONL 路径（不指定则自动生成）')
    args = parser.parse_args()

    dc = args.depth_cannon
    ds = args.depth_soldier

    # 输出路径
    if args.output:
        out_path = args.output
        os.makedirs(os.path.dirname(os.path.abspath(out_path)), exist_ok=True)
    else:
        root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        out_dir = os.path.join(root, 'data', 'selfplay')
        os.makedirs(out_dir, exist_ok=True)
        stamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        out_path = os.path.join(out_dir, f'selfplay_{stamp}.jsonl')

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

    print(f"[自对弈生成器]  目标={args.games}局  炮深度={dc}  兵深度={ds}  epsilon={args.epsilon}")
    print(f"[输出文件] {out_path}")
    print("=" * 70)

    start_total = time.time()

    for game_idx in range(start_game, args.games + 1):
        t0 = time.time()
        history, winner = play_one_game(dc, ds, args.epsilon)
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
