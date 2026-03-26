"""
eval_battle_arena.py - Heuristic vs NNUE 评估器对决脚本 (带开局库 & 随机采样)

用于验证 NNUE 评估器相对于传统手写启发式评估器的性能与强度。
支持加载开局库，并从中随机采样进行对称对弈 (Symmetric Match)。
"""
import sys
import os
import json
import time
import random
import argparse
import collections
import threading

# 添加项目根目录到路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from core.game_logic import GameState, CANNON, SOLDIER, DRAW, EMPTY
from core.evaluation_logic import apply_weights
from core.search_manager import find_best_move_iterative_deepening, find_best_move_parallel, clear_transposition_table, set_evaluator_mode

# ═══════════════════════════════════════════════════════════════════════════════
#  AI 步法选择 (带评估器切换)
# ═══════════════════════════════════════════════════════════════════════════════

def ai_choose_move(state, depth, pos_counts, use_nnue, weights=None, time_limit=15.0, num_threads=4):
    # 1. 切换评估模式
    if use_nnue:
        set_evaluator_mode(1)
    else:
        set_evaluator_mode(0)
        if weights:
            apply_weights(weights)

    # 2. 清除 TT
    clear_transposition_table()

    stop_event = threading.Event()
    settings = {
        "depth": depth,
        "time_limit": time_limit,
        "stop_event": stop_event,
        "analysis_mode": False,
        "num_threads": num_threads,
        "use_nnue": use_nnue
    }
    
    is_maximizing = (state.current_player == CANNON)
    t_start = time.time()
    if num_threads > 1:
        move = find_best_move_parallel(
            state, settings, is_maximizing, progress_callback=None
        )
    else:
        move = find_best_move_iterative_deepening(
            state, settings, is_maximizing, progress_callback=None
        )
    t_spent = time.time() - t_start
    
    # 兜底：如果没有搜索出招法则随机（极端情况）
    if not move:
        moves = []
        player = state.current_player
        for r in range(5):
            for c in range(5):
                if state.board[r][c] == player:
                    for (tr, tc) in state.get_valid_moves(r, c):
                        moves.append(((r, c), (tr, tc)))
        move = random.choice(moves) if moves else None
        
    return move, t_spent

# ═══════════════════════════════════════════════════════════════════════════════
#  单局对弈
# ═══════════════════════════════════════════════════════════════════════════════

def play_one_game(cannon_cfg, soldier_cfg, depth, max_moves=100, start_fen=None):
    if start_fen:
        state = GameState.from_fen(start_fen)
    else:
        state = GameState()
        
    pos_counts = collections.Counter()
    pos_counts[state.hash] += 1
    
    cannon_total_time = 0.0
    soldier_total_time = 0.0

    for move_num in range(max_moves):
        if state.winner != -1:
            break
        if state.soldier_count <= 4:
            state.winner = CANNON
            break

        curr_cfg = cannon_cfg if state.current_player == CANNON else soldier_cfg
        move, t_spent = ai_choose_move(state, depth, pos_counts, curr_cfg['use_nnue'], curr_cfg.get('weights'), 
                                      time_limit=curr_cfg.get('time_limit', 15.0), 
                                      num_threads=curr_cfg.get('threads', 1))
        if state.current_player == CANNON:
            cannon_total_time += t_spent
        else:
            soldier_total_time += t_spent
            
        if move is None:
            break

        start, end = move
        is_capture = state.board[end[0]][end[1]] != EMPTY
        state = state.move_piece(start[0], start[1], end[0], end[1])

        if is_capture:
            pos_counts.clear()
        pos_counts[state.hash] += 1

        if pos_counts[state.hash] >= 3:
            sc = state.soldier_count
            if sc <= 8: state.winner = CANNON
            elif sc == 9: state.winner = DRAW
            else: state.winner = SOLDIER
            break

    winner = state.winner if state.winner != -1 else DRAW
    return winner, move_num + 1, cannon_total_time, soldier_total_time

# ═══════════════════════════════════════════════════════════════════════════════
#  主程序
# ═══════════════════════════════════════════════════════════════════════════════

def main():
    parser = argparse.ArgumentParser(description='NNUE vs Heuristic Arena with Opening Selection')
    parser.add_argument("--openings", type=str, default="data/arena_openings.json", help="开局库路径")
    parser.add_argument("--rounds", type=int, default=10, help="从对决库中随机选取的开局数量 (默认 10)")
    parser.add_argument("--depth", type=int, default=12, help="搜索深度")
    parser.add_argument("--threads", type=int, default=1, help="并行线程数 (默认1，开启并行建议 4-16)")
    parser.add_argument("--time-limit", dest="time_limit", type=float, default=15.0, help="单次步数搜索时限")
    parser.add_argument("--weights", type=str, default="data/tuning/tuned_weights.json", help="启发式权重 JSON")
    args = parser.parse_args()

    # 加载启发式权重
    with open(args.weights, 'r', encoding='utf-8') as f:
        heuristic_weights = json.load(f)

    # 加载开局库
    if os.path.exists(args.openings):
        with open(args.openings, 'r', encoding='utf-8') as f:
            all_openings = json.load(f)
    else:
        all_openings = ["sssss/sssss/sssss/5/1ccc1 c"]

    # 随机采样开局
    if len(all_openings) > args.rounds:
        selected_openings = random.sample(all_openings, args.rounds)
    else:
        selected_openings = all_openings
        random.shuffle(selected_openings)

    nnue_cfg = {'use_nnue': True, 'time_limit': args.time_limit, 'threads': args.threads}
    heur_cfg = {'use_nnue': False, 'weights': heuristic_weights, 'time_limit': args.time_limit, 'threads': args.threads}

    print("=" * 60)
    print("  NNUE vs Heuristic Arena (Random Openings Mode)")
    print("=" * 60)
    print(f"  Library:           {args.openings} (Total {len(all_openings)})")
    print(f"  Selected Rounds:   {len(selected_openings)} openings")
    print(f"  Heuristic Weights: {args.weights}")
    print(f"  Search Depth:      {args.depth}")
    print("-" * 60)

    stats = {
        'nnue_wins': 0,
        'heur_wins': 0,
        'draws': 0,
        'nnue_as_cannon_wins': 0,
        'nnue_as_soldier_wins': 0
    }

    start_time = time.time()

    for idx, fen in enumerate(selected_openings, 1):
        print(f"  [对决 {idx}/{len(selected_openings)}] FEN: {fen}")
        
        # 局 A: NNUE (Cannon) vs Heuristic (Soldier)
        w_a, m_a, t_nnue_a, t_heur_a = play_one_game(nnue_cfg, heur_cfg, args.depth, start_fen=fen)
        if w_a == CANNON: 
            stats['nnue_wins'] += 1
            stats['nnue_as_cannon_wins'] += 1
            res_a = "NNUE胜"
        elif w_a == SOLDIER: 
            stats['heur_wins'] += 1
            res_a = "Heur胜"
        else:
            stats['draws'] += 1
            res_a = "和局"
        print(f"    - A:{res_a:>6} ({m_a}步) [NNUE:{t_nnue_a:5.1f}s | Heur:{t_heur_a:5.1f}s]")

        # 局 B: Heuristic (Cannon) vs NNUE (Soldier)
        w_b, m_b, t_heur_b, t_nnue_b = play_one_game(heur_cfg, nnue_cfg, args.depth, start_fen=fen)
        if w_b == SOLDIER:
            stats['nnue_wins'] += 1
            stats['nnue_as_soldier_wins'] += 1
            res_b = "NNUE胜"
        elif w_b == CANNON:
            stats['heur_wins'] += 1
            res_b = "Heur胜"
        else:
            stats['draws'] += 1
            res_b = "和局"
        print(f"    - B:{res_b:>6} ({m_b}步) [Heur:{t_heur_b:5.1f}s | NNUE:{t_nnue_b:5.1f}s]")

        current_total = (idx) * 2
        rate = (stats['nnue_wins'] + 0.5 * stats['draws']) / current_total * 100
        print(f"    > 实时得分率: {rate:.1f}%")

    end_time = time.time()
    
    print("-" * 60)
    games_count = len(selected_openings) * 2
    print(f"  总局数: {games_count}")
    print(f"  NNUE 胜局: {stats['nnue_wins']} (Cannon胜:{stats['nnue_as_cannon_wins']}, Soldier胜:{stats['nnue_as_soldier_wins']})")
    print(f"  Heur 胜局: {stats['heur_wins']}")
    print(f"  和局:      {stats['draws']}")
    print(f"  NNUE 最终得分率: {(stats['nnue_wins'] + 0.5 * stats['draws'])/ games_count * 100:.1f}%")
    print("-" * 60)
    print(f"  总耗时: {(end_time - start_time)/60:.1f}m")
    print("=" * 60)

if __name__ == '__main__':
    main()
