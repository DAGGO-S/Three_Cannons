"""
weight_arena.py - 新旧权重公平对战验证脚本

设计：每轮包含 2 局（消除先后手不对称）：
  - 局 A：新权重执炮 vs 旧权重执兵
  - 局 B：旧权重执炮 vs 新权重执兵

统计「新权重平均得分率」(胜=1, 和=0.5, 负=0)，>50% 说明新权重更强。

用法：
    python scripts/weight_arena.py --rounds 50 --depth 6
    python scripts/weight_arena.py --old data/tuning/original_weights.json --new data/tuning/tuned_weights.json
"""
import sys
import os
import json
import time
import random
import argparse
import collections
import threading

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from core.game_logic import GameState, CANNON, SOLDIER, DRAW, EMPTY
from core.evaluation_logic import apply_weights
from core.search_manager import find_best_move_iterative_deepening, find_best_move_parallel, clear_transposition_table


# ═══════════════════════════════════════════════════════════════════════════════
#  权重加载
# ═══════════════════════════════════════════════════════════════════════════════

def load_weights(filepath):
    """从 JSON 文件加载权重字典"""
    with open(filepath, 'r', encoding='utf-8') as f:
        return json.load(f)


# ═══════════════════════════════════════════════════════════════════════════════
#  对局逻辑
# ═══════════════════════════════════════════════════════════════════════════════

def get_all_valid_moves(state):
    moves = []
    player = state.current_player
    for r in range(5):
        for c in range(5):
            if state.board[r][c] == player:
                for (tr, tc) in state.get_valid_moves(r, c):
                    moves.append(((r, c), (tr, tc)))
    return moves


def ai_choose_move(state, depth, pos_counts, num_threads=1):
    all_moves = get_all_valid_moves(state)
    if not all_moves:
        return None

    # 强制随机打破重复局面
    if pos_counts.get(state.hash, 0) >= 2:
        return random.choice(all_moves)

    stop_event = threading.Event()
    settings = {
        "depth": depth,
        "time_limit": 60.0,
        "stop_event": stop_event,
        "analysis_mode": False,
        "num_threads": num_threads,
        "use_nnue": False
    }
    is_maximizing = (state.current_player == CANNON)
    if num_threads > 1:
        move = find_best_move_parallel(
            state, settings, is_maximizing, progress_callback=None
        )
    else:
        move = find_best_move_iterative_deepening(
            state, settings, is_maximizing, progress_callback=None
        )
    return move if move else random.choice(all_moves)


def play_one_game(cannon_weights, soldier_weights, depth, max_moves=150, num_threads=1):
    """
    进行一局对弈。

    cannon_weights: 执炮方使用的权重
    soldier_weights: 执兵方使用的权重
    depth: 双方统一搜索深度
    """
    state = GameState()
    pos_counts = collections.Counter()
    pos_counts[state.hash] += 1

    for move_num in range(max_moves):
        if state.winner != -1:
            break

        # 残局裁定：兵 <= 4 视为炮胜
        if state.soldier_count <= 4:
            state.winner = CANNON
            break

        # 根据当前行棋方切换权重
        if state.current_player == CANNON:
            apply_weights(cannon_weights)
        else:
            apply_weights(soldier_weights)

        # 清除 TT（权重变了，之前的缓存失效）
        clear_transposition_table()

        move = ai_choose_move(state, depth, pos_counts, num_threads=num_threads)
        if move is None:
            break

        start, end = move
        is_capture = state.board[end[0]][end[1]] != EMPTY
        state = state.move_piece(start[0], start[1], end[0], end[1])

        if is_capture:
            pos_counts.clear()
        pos_counts[state.hash] += 1

        if pos_counts[state.hash] >= 3:
            # 【同步系统新规】循环局面根据兵力判定
            sc = state.soldier_count
            if sc <= 8:
                state.winner = CANNON
            elif sc == 9:
                state.winner = DRAW
            else:
                state.winner = SOLDIER
            break

    winner = state.winner if state.winner != -1 else DRAW
    return winner, move_num + 1


# ═══════════════════════════════════════════════════════════════════════════════
#  主程序
# ═══════════════════════════════════════════════════════════════════════════════

def main():
    parser = argparse.ArgumentParser(
        description='新旧权重公平对战验证',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  快速验证:  python scripts/weight_arena.py --rounds 20 --depth 4
  标准验证:  python scripts/weight_arena.py --rounds 50 --depth 6
        """
    )

    root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    default_old = os.path.join(root, "data", "tuning", "tuned_weights-R1.json")
    default_new = os.path.join(root, "data", "tuning", "tuned_weights.json")

    parser.add_argument("--old", type=str, default=default_old,
                        help="旧权重 JSON 路径")
    parser.add_argument("--new", type=str, default=default_new,
                        help="新权重 JSON 路径")
    parser.add_argument("--rounds", type=int, default=20,
                        help="对弈轮数，每轮 2 局 (默认 20)")
    parser.add_argument("--depth", type=int, default=10,
                        help="双方统一搜索深度 (默认 10)")
    parser.add_argument("--max-moves", type=int, default=150,
                        help="单局最大步数 (默认 150)")
    parser.add_argument("--threads", type=int, default=1,
                        help="并行线程数 (默认 1)")
    args = parser.parse_args()

    # ── 加载权重 ──
    old_weights = load_weights(args.old)
    new_weights = load_weights(args.new)

    print("=" * 70)
    print("  新旧权重公平对战验证")
    print("=" * 70)
    print(f"  旧权重: {args.old}")
    print(f"  新权重: {args.new}")
    print(f"  搜索深度: {args.depth}")
    print(f"  对弈轮数: {args.rounds} (共 {args.rounds * 2} 局)")
    print("=" * 70)

    # ── 统计 ──
    new_score = 0.0  # 新权重累计得分
    total_games = 0
    new_cannon_wins = 0   # 新权重执炮的胜局数
    new_cannon_draws = 0
    new_cannon_losses = 0
    new_soldier_wins = 0  # 新权重执兵的胜局数
    new_soldier_draws = 0
    new_soldier_losses = 0

    start_time = time.time()

    for round_idx in range(1, args.rounds + 1):
        # ── 局 A: 新权重执炮 vs 旧权重执兵 ──
        t0 = time.time()
        winner_a, moves_a = play_one_game(
            cannon_weights=new_weights,
            soldier_weights=old_weights,
            depth=args.depth,
            max_moves=args.max_moves,
            num_threads=args.threads
        )
        time_a = time.time() - t0

        total_games += 1
        if winner_a == CANNON:
            new_score += 1.0
            new_cannon_wins += 1
            result_a = "新胜(炮)"
        elif winner_a == DRAW:
            new_score += 0.5
            new_cannon_draws += 1
            result_a = "和局"
        else:
            new_cannon_losses += 1
            result_a = "旧胜(兵)"

        # ── 局 B: 旧权重执炮 vs 新权重执兵 ──
        t0 = time.time()
        winner_b, moves_b = play_one_game(
            cannon_weights=old_weights,
            soldier_weights=new_weights,
            depth=args.depth,
            max_moves=args.max_moves,
            num_threads=args.threads
        )
        time_b = time.time() - t0

        total_games += 1
        if winner_b == SOLDIER:
            new_score += 1.0
            new_soldier_wins += 1
            result_b = "新胜(兵)"
        elif winner_b == DRAW:
            new_score += 0.5
            new_soldier_draws += 1
            result_b = "和局"
        else:
            new_soldier_losses += 1
            result_b = "旧胜(炮)"

        # ── 实时输出 ──
        current_rate = new_score / total_games * 100
        elapsed = time.time() - start_time
        eta = elapsed / round_idx * (args.rounds - round_idx)

        print(
            f"  轮次 {round_idx:>3}/{args.rounds}  "
            f"A:{result_a}({moves_a}步,{time_a:.1f}s) "
            f"B:{result_b}({moves_b}步,{time_b:.1f}s)  "
            f"新权重得分率={current_rate:.1f}%  "
            f"ETA≈{int(eta//60)}m{int(eta%60)}s"
        )

    # ── 最终统计 ──
    elapsed = time.time() - start_time
    final_rate = new_score / total_games * 100

    print("\n" + "=" * 70)
    print("  最终结果")
    print("=" * 70)
    print(f"  总局数: {total_games}")
    print(f"  新权重得分: {new_score:.1f} / {total_games} ({final_rate:.1f}%)")
    print()
    print(f"  新权重执炮: {new_cannon_wins}胜 {new_cannon_draws}和 {new_cannon_losses}负")
    print(f"  新权重执兵: {new_soldier_wins}胜 {new_soldier_draws}和 {new_soldier_losses}负")
    print()

    if final_rate > 55:
        verdict = "✅ 新权重显著更强"
    elif final_rate > 50:
        verdict = "⬆️ 新权重略有优势"
    elif final_rate == 50:
        verdict = "➡️ 新旧权重持平"
    elif final_rate > 45:
        verdict = "⬇️ 新权重略有劣势"
    else:
        verdict = "❌ 旧权重显著更强"

    print(f"  判定: {verdict}")
    print(f"  总耗时: {elapsed/60:.1f} 分钟")
    print("=" * 70)


if __name__ == '__main__':
    main()
