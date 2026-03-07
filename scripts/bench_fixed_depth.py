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
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.game_logic import GameState
from core.ai import find_best_move_iterative_deepening, clear_transposition_table, get_nodes_evaluated, reset_nodes_evaluated

# --- 配置 ---
FIXED_DEPTH = 12
TIME_LIMIT = 9999.0  # 不限时，让深度成为唯一约束

def run_benchmark():
    print("=" * 60)
    print("  Three Cannons 固定深度性能基准测试")
    print("=" * 60)
    print(f"  搜索深度: {FIXED_DEPTH}")
    print(f"  棋盘状态: 标准开局")
    print(f"  执行方:   炮方 (Maximizing)")
    print(f"  时间限制: 无 (深度为唯一约束)")
    print("-" * 60)

    # 清空置换表，确保公平
    clear_transposition_table()
    reset_nodes_evaluated()

    state = GameState()
    stop_event = threading.Event()

    settings = {
        "depth": FIXED_DEPTH,
        "time_limit": TIME_LIMIT,
        "stop_event": stop_event,
    }

    depth_log = []

    def progress_callback(depth, score, move, line, root_stats):
        elapsed = time.time() - start_time
        nodes = get_nodes_evaluated()
        nps = nodes / elapsed if elapsed > 0 else 0
        depth_log.append((depth, score, elapsed, nodes, nps))
        print(f"  深度 {depth:2d} | 分数 {score:+8.1f} | 耗时 {elapsed:7.3f}s | 节点 {nodes:9d} | 速度 {nps:7.0f} NPS | 走法 {move}")

    print("\n开始搜索...\n")
    start_time = time.time()

    best_move = find_best_move_iterative_deepening(
        state, settings, is_maximizing=True, progress_callback=progress_callback
    )

    total_time = time.time() - start_time

    print("-" * 60)
    print(f"\n  最终走法: {best_move}")
    print(f"  总耗时:   {total_time:.3f} 秒")
    if depth_log:
        max_depth = depth_log[-1][0]
        total_nodes = depth_log[-1][3]
        final_nps = total_nodes / total_time if total_time > 0 else 0
        print(f"  达到深度: {max_depth}")
        print(f"  总节点数: {total_nodes}")
        print(f"  平均速度: {final_nps:.0f} NPS (Nodes/评估 每秒)")
    print("=" * 60)

    return total_time, depth_log

if __name__ == "__main__":
    run_benchmark()
