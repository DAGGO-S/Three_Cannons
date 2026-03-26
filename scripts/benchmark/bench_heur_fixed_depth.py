#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
固定深度性能基准测试 (Benchmark)

测试条件：
- 初始棋盘开局
- 炮方先手（is_maximizing=True）
- 固定搜索深度 12
- 无时间限制（设为极大值）
- 测量总耗时和达到的实际深度

用法：
    cd Three_Cannons
    python scripts/bench_fixed_depth.py
"""

import sys
import os
import time
import threading

# 添加项目根目录
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from core.game_logic import GameState, CANNON, SOLDIER
from core.search_manager import find_best_move_iterative_deepening, find_best_move_parallel, set_evaluator_mode
from core.search_infrastructure import reset_nodes_evaluated, get_nodes_evaluated, clear_transposition_table

# --- 配置 ---
FIXED_DEPTH = 14
TIME_LIMIT = 9999.0  # 不限时，让深度成为唯一约束

def run_benchmark(depth, threads, mode):
    print("=" * 60)
    print("  Three Cannons 性能基准测试")
    print("=" * 60)
    print(f"  搜索深度: {depth}")
    print(f"  并行线程: {threads}")
    print(f"  评估模式: {'NNUE' if mode == 1 else 'Heuristic'}")
    print(f"  棋盘状态: 标准开局")
    print(f"  时间限制: 无 (深度为唯一约束)")
    print("-" * 60)

    set_evaluator_mode(mode)
    clear_transposition_table()
    reset_nodes_evaluated()

    state = GameState()
    stop_event = threading.Event()

    settings = {
        "depth": depth,
        "time_limit": 9999.0,
        "stop_event": stop_event,
        "num_threads": threads,
        "use_nnue": (mode == 1)
    }

    depth_log = []

    def progress_callback(d, score, move, line, root_stats):
        elapsed = time.time() - start_time
        nodes = get_nodes_evaluated()
        nps = nodes / elapsed if elapsed > 0 else 0
        depth_log.append((d, score, elapsed, nodes, nps))
        print(f"  深度 {d:2d} | 分数 {score:+8.1f} | 耗时 {elapsed:7.3f}s | 节点 {nodes:9d} | 速度 {nps:7.0f} NPS | 走法 {move}")

    print("\n开始搜索...\n")
    start_time = time.time()

    if threads > 1:
        best_move = find_best_move_parallel(
            state, settings, is_maximizing=True, progress_callback=progress_callback
        )
    else:
        best_move = find_best_move_iterative_deepening(
            state, settings, is_maximizing=True, progress_callback=progress_callback
        )

    total_time = time.time() - start_time

    print("-" * 60)
    print(f"\n  最终走法: {best_move}")
    print(f"  总耗时:   {total_time:.3f} 秒")
    if depth_log:
        max_d = depth_log[-1][0]
        total_nodes = depth_log[-1][3]
        final_nps = total_nodes / total_time if total_time > 0 else 0
        print(f"  达到深度: {max_d}")
        print(f"  总节点数: {total_nodes}")
        print(f"  平均速度: {final_nps:.0f} NPS")
    print("=" * 60)

    return total_time, depth_log

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description='Three Cannons Benchmark')
    parser.add_argument('--depth', type=int, default=14, help='Search depth')
    parser.add_argument('--threads', type=int, default=1, help='Number of threads')
    parser.add_argument('--mode', type=int, default=0, choices=[0, 1], help='0: Heuristic, 1: NNUE')
    args = parser.parse_args()
    
    run_benchmark(args.depth, args.threads, args.mode)
