#!/usr/bin/env python3
"""编译并运行 board_speed_demo.pyx 的微基准测试"""

import sys, os, time, glob

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
ROOT_DIR = os.path.dirname(SCRIPT_DIR)
os.chdir(ROOT_DIR)

# 先编译
print("正在编译 board_speed_demo.pyx ...")
from Cython.Build import cythonize
from setuptools import Extension
from setuptools.dist import Distribution

ext = Extension("board_speed_demo", [os.path.join("scripts", "board_speed_demo.pyx")])
dist = Distribution({"ext_modules": cythonize([ext], compiler_directives={"language_level": "3"})})
cmd = dist.get_command_obj("build_ext")
cmd.inplace = True
cmd.ensure_finalized()
cmd.run()
print("编译完成!\n")

# 找到编译产物并确保可以导入
# inplace 模式会把 .pyd 放在与 .pyx 同目录（scripts/）
sys.path.insert(0, SCRIPT_DIR)
# 也可能放在项目根目录
sys.path.insert(0, ROOT_DIR)

import board_speed_demo

ITERATIONS = 1_000_000

print("=" * 60)
print("  棋盘操作微基准测试：三种方案直接对比")
print("=" * 60)
print(f"  每种方案重复 {ITERATIONS:,} 次")
print("-" * 60)

# --- 方案 1: tuple ---
t0 = time.perf_counter()
board_speed_demo.bench_tuple(ITERATIONS)
t_tuple = time.perf_counter() - t0
ops_tuple = ITERATIONS / t_tuple
print(f"\n  方案 1 (当前 tuple 重建):")
print(f"    耗时: {t_tuple:.3f}s | 吞吐: {ops_tuple:,.0f} ops/s")

# --- 方案 2: C array + memcpy ---
t0 = time.perf_counter()
board_speed_demo.bench_c_array(ITERATIONS)
t_carray = time.perf_counter() - t0
ops_carray = ITERATIONS / t_carray
print(f"\n  方案 2 (C 数组 + memcpy):")
print(f"    耗时: {t_carray:.3f}s | 吞吐: {ops_carray:,.0f} ops/s")

# --- 方案 3: Make/Unmake ---
t0 = time.perf_counter()
board_speed_demo.bench_make_unmake(ITERATIONS)
t_mu = time.perf_counter() - t0
ops_mu = ITERATIONS / t_mu
print(f"\n  方案 3 (Make/Unmake 零分配):")
print(f"    耗时: {t_mu:.3f}s | 吞吐: {ops_mu:,.0f} ops/s")

# --- 汇总 ---
print("\n" + "=" * 60)
print("  加速比 (相对于当前 tuple 方案):")
print(f"    方案 2 (C数组+memcpy):   {ops_carray/ops_tuple:.1f}x")
print(f"    方案 3 (Make/Unmake):    {ops_mu/ops_tuple:.1f}x")
print("=" * 60)
