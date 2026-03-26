#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
NNUE 并行性能基准测试 (Benchmark)

测试条件：
- 初始棋盘开局
- 固定搜索深度 14
- 使用 NNUE 评估 (g_evaluator_mode = 1)
- 使用多线程并行搜索 (Lazy SMP)
"""

import sys
import os
import time
import threading
import multiprocessing

# 添加项目根目录
ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, ROOT)

from core.game_logic import GameState
from core.search_manager import find_best_move_parallel
from core.search_infrastructure import get_nodes_evaluated, reset_nodes_evaluated, clear_transposition_table

# --- 配置 ---
FIXED_DEPTH = 14
NUM_THREADS = max(1, multiprocessing.cpu_count())  # 自动根据系统内核数调整满载线程
TIME_LIMIT = 9999.0

def run_benchmark():
    print("=" * 60)
    print("  Three Cannons NNUE 并行基准测试 (Depth 14)")
    print("=" * 60)
    print(f"  搜索深度: {FIXED_DEPTH}")
    print(f"  并行线程: {NUM_THREADS}")
    print(f"  评估模式: NNUE")
    print("-" * 60)

    # 初始化
    clear_transposition_table()
    reset_nodes_evaluated()

    state = GameState()
    stop_event = threading.Event()

    settings = {
        "depth": FIXED_DEPTH,
        "time_limit": TIME_LIMIT,
        "stop_event": stop_event,
        "num_threads": NUM_THREADS,
        "use_nnue": True
    }

    print("\n开始并行搜索...\n")
    start_time = time.time()

    def progress_callback(depth, score, move, line, root_stats):
        elapsed = time.time() - start_time
        nodes = get_nodes_evaluated()
        nps = nodes / elapsed if elapsed > 0 else 0
        print(f"  深度 {depth:2d} | 分数 {score:+8.1f} | 耗时 {elapsed:7.3f}s | 节点 {nodes:9d} | 速度 {nps:7.0f} NPS | 走法 {move}")

    best_move = find_best_move_parallel(
        state, settings, is_maximizing=True, progress_callback=progress_callback
    )

    total_time = time.time() - start_time
    total_nodes = get_nodes_evaluated()

    print("-" * 60)
    print(f"\n  最终走法: {best_move}")
    print(f"  总耗时:   {total_time:.3f} 秒")
    print(f"  达到深度: {FIXED_DEPTH}")
    print(f"  总节点数: {total_nodes}")
    print(f"  平均速度: {total_nodes / total_time if total_time > 0 else 0:.0f} NPS")
    print("=" * 60)

if __name__ == "__main__":
    run_benchmark()
