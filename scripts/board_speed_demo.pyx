# scripts/board_speed_demo.pyx
# 隔离的微基准测试：直接对比 tuple 重建 vs C 数组 memcpy
#
# 测试内容：模拟搜索树中最热的操作 —— "复制棋盘 + 修改一格 + 生成新状态"
# 重复 100 万次，测量两种方案的吞吐量差异。

import cython
from libc.string cimport memcpy

# ============================================================
# 方案 1: 当前方案 — tuple-of-tuples（与 game_logic.pyx 完全一致）
# ============================================================

def bench_tuple(int iterations):
    """模拟当前 move_piece 的核心热路径"""
    cdef int i
    # 初始棋盘（与真实开局一致）
    board = (
        (1,1,1,1,1),(1,1,1,1,1),(1,1,1,1,1),(0,0,0,0,0),(0,2,2,2,0)
    )
    
    for i in range(iterations):
        # ① tuple → list（5 次对象创建）
        new_board_list = [list(row) for row in board]
        # ② 修改一格（唯一有用的工作）
        new_board_list[4][2] = 0
        new_board_list[3][2] = 2
        # ③ list → tuple（5 次对象创建）
        new_board = tuple(tuple(row) for row in new_board_list)
    
    return new_board

# ============================================================
# 方案 2: C 数组 + memcpy（Phase 3 方案 B）
# ============================================================

cdef struct CBoard:
    int cells[25]
    int current_player
    int soldier_count

cdef void copy_board(CBoard* dst, CBoard* src) noexcept nogil:
    memcpy(dst, src, sizeof(CBoard))

def bench_c_array(int iterations):
    """模拟 C 数组 + memcpy 的 move_piece"""
    cdef CBoard board, new_board
    cdef int i
    
    # 初始化棋盘
    cdef int init[25]
    init = [1,1,1,1,1, 1,1,1,1,1, 1,1,1,1,1, 0,0,0,0,0, 0,2,2,2,0]
    memcpy(board.cells, init, 25 * sizeof(int))
    board.current_player = 2
    board.soldier_count = 15
    
    for i in range(iterations):
        # ① memcpy 复制整个棋盘（~100 字节，1-2 CPU 周期）
        copy_board(&new_board, &board)
        # ② 修改一格
        new_board.cells[4*5+2] = 0   # (4,2) → EMPTY
        new_board.cells[3*5+2] = 2   # (3,2) → CANNON
    
    return new_board.cells[3*5+2]

# ============================================================
# 方案 3: C 数组 + Make/Unmake（Phase 3 方案 A，零分配）
# ============================================================

def bench_make_unmake(int iterations):
    """模拟 Make/Unmake 的 move_piece（原地修改 + 撤销）"""
    cdef CBoard board
    cdef int i, captured
    
    cdef int init[25]
    init = [1,1,1,1,1, 1,1,1,1,1, 1,1,1,1,1, 0,0,0,0,0, 0,2,2,2,0]
    memcpy(board.cells, init, 25 * sizeof(int))
    
    for i in range(iterations):
        # Make: 原地修改
        captured = board.cells[3*5+2]       # 保存目标格
        board.cells[3*5+2] = board.cells[4*5+2]  # 移动棋子
        board.cells[4*5+2] = 0              # 清空原位
        
        # （这里本来是递归搜索下一层...）
        
        # Unmake: 撤销
        board.cells[4*5+2] = board.cells[3*5+2]  # 恢复棋子
        board.cells[3*5+2] = captured       # 恢复目标格
    
    return board.cells[4*5+2]
