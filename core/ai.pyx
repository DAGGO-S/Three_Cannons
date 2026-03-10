# cython: profile=False
import cython
import time
import math
import traceback
import pickle # Added for persistence
import os
from core.game_logic import GameState, CANNON, SOLDIER, EMPTY
from core.game_logic cimport GameState as CGameState  # C 级直接访问 board_c
from core.evaluation_logic import evaluate_board, clear_evaluation_caches
from core.evaluation_logic cimport c_evaluate_board

# Cython imports
from cython cimport Py_ssize_t
from libc.stdlib cimport malloc, free
from libc.string cimport memset

ctypedef Py_ssize_t int
ctypedef double float
ctypedef bint bool

# --- 置换表和相关常量 ---
# 【Phase1优化】定长数组 + 哈希位运算掩码，消除 O(N) 清理并解决 Boxing
cdef int TT_SIZE = 4194304  # 4M 个槽位，支持 TT_SIZE - 1 位运算
cdef struct TTEntry:
    unsigned long long hash_key
    int depth
    float score
    int flag
    int best_move_encoded

cdef TTEntry* transposition_table = NULL

EXACT_SCORE = 1
LOWER_BOUND = 2
UPPER_BOUND = 3

# --- 性能统计 ---
cdef unsigned long long _total_nodes_evaluated = 0

def get_nodes_evaluated():
    global _total_nodes_evaluated
    return _total_nodes_evaluated

def reset_nodes_evaluated():
    global _total_nodes_evaluated
    _total_nodes_evaluated = 0

def clear_transposition_table():
    """清空置换表，由外部调用者（AIEngine）在每次新计算开始时调用。"""
    global transposition_table
    if transposition_table == NULL:
        transposition_table = <TTEntry*>malloc(TT_SIZE * sizeof(TTEntry))
    if transposition_table != NULL:
        memset(transposition_table, 0, TT_SIZE * sizeof(TTEntry))

def save_transposition_table(filepath):
    """保存置换表（因为已替换为 C 级别非托管内存，暂不支持持久化）"""
    pass

def load_transposition_table(filepath):
    """加载置换表（暂不读取 C 级别指针内存块）"""
    pass

from core.game_logic cimport c_get_ordered_moves

# --- 内部 C 级辅助函数（无需 _get_ordered_moves 了，直接用底层的 c_get_ordered_moves）---

# --- 静默搜索（带深度限制，防止无限递归）---
cdef int MAX_QS_DEPTH = 8

@cython.boundscheck(False)
@cython.wraparound(False)
cdef tuple _quiescence_search(CGameState state, float alpha, float beta, bint maximizing_player, object settings=None, int qs_depth=0):
    """
    静默搜索：只搜索吃子走法，直到局面安静后做静态评估。
    带深度限制防止无限递归。
    """
    stop_event = settings.get("stop_event", None) if settings else None
    
    global _total_nodes_evaluated
    _total_nodes_evaluated += 1
    
    cdef float stand_pat_score, evaluation
    cdef int player_piece
    cdef object new_state
    
    # 1. 静态评估 (直接走 C 通道)
    stand_pat_score = c_evaluate_board(state)

    if stop_event and stop_event.is_set():
        return 0.0, None, []

    # 达到终局或深度限制，直接返回静态评估
    if abs(stand_pat_score) >= 10000 or qs_depth >= MAX_QS_DEPTH:
        return stand_pat_score, None, []

    # 2. Stand-pat 剪枝
    if maximizing_player:
        if stand_pat_score >= beta:
            return beta, None, []
        alpha = max(alpha, stand_pat_score)
    else:
        if stand_pat_score <= alpha:
            return alpha, None, []
        beta = min(beta, stand_pat_score)

    # 3. C 级走法生成 (零分配)
    cdef int ordered_moves[64]
    cdef int num_moves, i, move_encoded, start_idx, end_idx
    
    player_piece = CANNON if maximizing_player else SOLDIER
    num_moves = c_get_ordered_moves(state, player_piece, -1, ordered_moves)
    
    # 4. 递归搜索吃子走法
    cdef unsigned long long old_hash
    cdef int old_winner, captured

    if maximizing_player:
        for i in range(num_moves):
            if stop_event and stop_event.is_set():
                break
                
            move_encoded = ordered_moves[i]
            end_idx = move_encoded & 0xFF
            
            # 仅搜索吃子走法 (终点非空)
            if state.board_c[end_idx] == EMPTY:
                continue
                
            start_idx = move_encoded >> 8
            
            old_hash = state.hash
            old_winner = state.winner
            captured = state.c_move_piece(start_idx, end_idx)
            
            evaluation, _, _ = _quiescence_search(state, alpha, beta, False, settings, qs_depth + 1)
            
            state.c_unmake_piece(start_idx, end_idx, captured, old_hash, old_winner)
            
            alpha = max(alpha, evaluation)
            if beta <= alpha:
                return beta, None, []
        return alpha, None, []
    else:
        for i in range(num_moves):
            if stop_event and stop_event.is_set():
                break
                
            move_encoded = ordered_moves[i]
            end_idx = move_encoded & 0xFF
            
            if state.board_c[end_idx] == EMPTY:
                continue
                
            start_idx = move_encoded >> 8
                
            old_hash = state.hash
            old_winner = state.winner
            captured = state.c_move_piece(start_idx, end_idx)
            
            evaluation, _, _ = _quiescence_search(state, alpha, beta, True, settings, qs_depth + 1)
            
            state.c_unmake_piece(start_idx, end_idx, captured, old_hash, old_winner)
            
            beta = min(beta, evaluation)
            if beta <= alpha:
                return alpha, None, []
        return beta, None, []

# --- 迭代加深搜索主入口 ---
cdef list _extract_pv_from_tt(CGameState state, int max_depth):
    """
    通过查找置换表(TT) 还原主变路线(PV Line)。
    完全消除在核心搜索树中动态构建列表的开销。
    """
    cdef list pv_line = []
    cdef unsigned long long state_hash
    cdef int tt_index
    cdef TTEntry* hash_entry
    cdef int move_encoded, start_idx, end_idx, captured, old_winner
    cdef unsigned long long old_hash
    cdef int depth = 0
    
    # 防止陷入哈希循环
    cdef set visited_hashes = set()
    
    while depth < max_depth:
        state_hash = state.hash
        if state_hash in visited_hashes:
            break
        visited_hashes.add(state_hash)
            
        tt_index = <int>(state_hash & (TT_SIZE - 1))
        
        if transposition_table == NULL:
            break
            
        hash_entry = &transposition_table[tt_index]
        if hash_entry.hash_key != state_hash or hash_entry.best_move_encoded == -1:
            break
            
        move_encoded = hash_entry.best_move_encoded
        pv_line.append(move_encoded)
        
        # 顺推状态以查找下一层
        start_idx = move_encoded >> 8
        end_idx = move_encoded & 0xFF
        old_hash = state.hash
        old_winner = state.winner
        captured = state.c_move_piece(start_idx, end_idx)
        
        depth += 1
        
    # 回溯还原状态
    for i in range(len(pv_line) - 1, -1, -1):
         move_encoded = pv_line[i]
         # 注：为了图省事这里直接深拷贝或者利用 Python 层级的 undo 记录，但最纯粹的是：
         # 提取 PV 一般在根节点调用，因为 state 是通过值拷贝或者回溯完整的，
         # 所以我们可以借用 _extract_pv_from_tt 外部复制一个 dummy_state
    
    return pv_line

@cython.boundscheck(False)
@cython.wraparound(False)
def find_best_move_iterative_deepening(CGameState state, dict settings, bint is_maximizing, object progress_callback=None):
    """
    通过迭代加深搜索最佳走法。
    这是AI思考的主入口。
    """
    # 【Phase1优化】定长数组无需清理，旧条目自动被覆盖
    # 【Phase4优化】清空评估缓存，防止无限增长和 hash 碰撞
    clear_evaluation_caches()
    
    start_time = time.time()
    best_move_so_far = None
    best_line_so_far = []
    
    cdef int max_depth = settings["depth"]
    cdef float time_limit = settings["time_limit"]
    cdef int depth
    cdef int player_piece = CANNON if is_maximizing else SOLDIER
    cdef int hash_encoded
    cdef int ordered_moves_c[64]
    cdef int num_moves
    cdef int current_depth_best_move
    cdef float current_depth_best_score
    cdef list current_depth_best_line
    cdef float current_alpha
    cdef float current_beta
    cdef bint analysis_mode = settings.get("analysis_mode", False)
    cdef int move_encoded, start_idx, end_idx
    cdef tuple final_move
    
    cdef unsigned long long old_hash
    cdef int old_winner, captured

    stop_event = settings.get("stop_event", None)

    # 用于存储根节点每个子走法的最佳分数 {move: score}
    # 这样可以在GUI上显示每个走法的评价
    root_moves_stats = {} 

    for depth in range(1, max_depth + 1):
        # 检查是否应该提前终止 (更精确的时间控制)
        elapsed_time = time.time() - start_time
        
        if depth > 1:
            estimated_next_depth_time = elapsed_time * 2.5
            remaining_time = time_limit - elapsed_time
            if estimated_next_depth_time > remaining_time:
                if progress_callback:
                    print(f"时间限制，提前于深度 {depth} 终止搜索。")
                break
            if elapsed_time > time_limit * 0.8:
                if progress_callback:
                    print(f"时间使用达到80%，提前于深度 {depth} 终止搜索。")
                break
        
        if stop_event and stop_event.is_set():
            if progress_callback:
                print(f"接收到停止信号，终止搜索。")
            break

        # --- 核心修改：手动展开根节点的搜索 ---
        # 1. 获取并排序根节点走法 (16-bit encoded move)
        # 用 c_get_ordered_moves() 传入指针避免 Python list 申请
        hash_encoded = -1
        if best_move_so_far is not None:
             hash_encoded = best_move_so_far
             
        num_moves = c_get_ordered_moves(state, player_piece, hash_encoded, ordered_moves_c)
        
        current_depth_best_move = -1
        current_depth_best_score = -math.inf if is_maximizing else math.inf
        current_depth_best_line = []
        
        # Alpha-Beta 窗口
        current_alpha = -math.inf
        current_beta = math.inf
        
        root_moves_stats.clear() # 每个深度清空一次，保证是最新的评估

        for i in range(num_moves):
            if stop_event and stop_event.is_set():
                break
                
            move_encoded = ordered_moves_c[i]
            start_idx = move_encoded >> 8
            end_idx = move_encoded & 0xFF
            
            old_hash = state.hash
            old_winner = state.winner
            captured = state.c_move_piece(start_idx, end_idx)
            
            # --- 关键逻辑分支 ---
            if analysis_mode:
                if is_maximizing:
                    score = _alpha_beta(state, depth - 1, -math.inf, math.inf, not is_maximizing, settings)
                else:
                    score = _alpha_beta(state, depth - 1, -math.inf, math.inf, not is_maximizing, settings)
            else:
                if i == 0:
                    score = _alpha_beta(state, depth - 1, current_alpha, current_beta, not is_maximizing, settings)
                else:
                    if is_maximizing:
                        score = _alpha_beta(state, depth - 1, current_alpha, current_alpha + 1, not is_maximizing, settings)
                        if current_alpha < score < current_beta:
                             score = _alpha_beta(state, depth - 1, current_alpha, current_beta, not is_maximizing, settings)
                    else:
                        score = _alpha_beta(state, depth - 1, current_beta - 1, current_beta, not is_maximizing, settings)
                        if current_alpha < score < current_beta:
                             score = _alpha_beta(state, depth - 1, current_alpha, current_beta, not is_maximizing, settings)

            state.c_unmake_piece(start_idx, end_idx, captured, old_hash, old_winner)

            # 记录分数 (存 16bit encode值)
            root_moves_stats[move_encoded] = score

            # 更新最佳 (用于最终走棋决策)
            if is_maximizing:
                if score > current_depth_best_score:
                    current_depth_best_score = score
                    current_depth_best_move = move_encoded
                current_alpha = max(current_alpha, score)
            else:
                if score < current_depth_best_score:
                    current_depth_best_score = score
                    current_depth_best_move = move_encoded
                current_beta = min(current_beta, score)

        # 本层迭代结束
        if not stop_event.is_set():
            current_iter_time = time.time() - start_time
            if current_iter_time < time_limit:
                 best_move_so_far = current_depth_best_move
                 
                 # 利用临时 dummy state 和 TT 表提出完整 PV
                 # 降低开销，仅给 UI 发送进度时提取
                 if progress_callback:
                     import copy
                     dummy_state = copy.deepcopy(state)
                     current_depth_best_line = _extract_pv_from_tt(dummy_state, depth)
                     best_line_so_far = current_depth_best_line
                     
                     decoded_best = (((current_depth_best_move>>8)//5, (current_depth_best_move>>8)%5), ((current_depth_best_move&0xFF)//5, (current_depth_best_move&0xFF)%5)) if current_depth_best_move != -1 else None
                     decoded_line = [(((m>>8)//5, (m>>8)%5), ((m&0xFF)//5, (m&0xFF)%5)) for m in current_depth_best_line]
                     decoded_stats = {(((m>>8)//5, (m>>8)%5), ((m&0xFF)//5, (m&0xFF)%5)): s for m, s in root_moves_stats.items()}
                     progress_callback(depth, current_depth_best_score, decoded_best, decoded_line, decoded_stats)
            else:
                if progress_callback:
                     print(f"时间限制，完成深度 {depth-1} 的搜索。")
                break
        else:
            break

    final_move = None
    if best_move_so_far is not None and best_move_so_far != -1:
        m = best_move_so_far
        final_move = (((m>>8)//5, (m>>8)%5), ((m&0xFF)//5, (m&0xFF)%5))
        
    return final_move


# --- Alpha-Beta + PVS + NMP + LMR ---
@cython.boundscheck(False)
@cython.wraparound(False)
cdef float _alpha_beta(CGameState state, int depth, float alpha, float beta, bint maximizing_player, object settings):
    """
    极速 Alpha-Beta 搜索。
    去除了任何 Tuple 与 List 创建的副作用。返回值仅为分数，所有的 PV 还原靠外部查表。
    """
    global _total_nodes_evaluated
    _total_nodes_evaluated += 1
    
    # 降频检查中断信号（每 4096 个节点探底1次，大幅降低 GIL 通信开销）
    if (_total_nodes_evaluated & 4095) == 0:
        stop_event = settings.get("stop_event", None)
        if stop_event and stop_event.is_set():
            return 0.0
    
    cdef float original_alpha = alpha
    cdef int player_piece = CANNON if maximizing_player else SOLDIER
    cdef int hash_move_encoded
    cdef int ordered_moves[64]
    cdef int num_moves
    cdef int best_move_encoded
    cdef int move_encoded, start_idx, end_idx
    cdef int i
    cdef float max_eval, min_eval, evaluation, eval_score
    cdef bint is_capture_move
    cdef int reduction
    
    cdef unsigned long long state_hash = state.hash
    cdef int tt_index = <int>(state_hash & (TT_SIZE - 1))
    cdef int flag
    cdef TTEntry* hash_entry = NULL
    
    cdef unsigned long long old_hash
    cdef int old_winner, captured
    
    # --- 1. 查找置换表 ---
    if transposition_table != NULL:
        hash_entry = &transposition_table[tt_index]
        if hash_entry.hash_key == state_hash and hash_entry.depth >= depth:
            if hash_entry.flag == EXACT_SCORE:
                return hash_entry.score
            elif hash_entry.flag == LOWER_BOUND:
                alpha = max(alpha, hash_entry.score)
            elif hash_entry.flag == UPPER_BOUND:
                beta = min(beta, hash_entry.score)
            if alpha >= beta:
                return hash_entry.score

    # --- 2. 终止条件 ---
    if state.winner != -1:
        return 10000 if state.winner == CANNON else -10000
    
    # 待未来启用 QS 的地方，目前直接测基分
    if depth == 0:
        return c_evaluate_board(state)
    
    # --- 3. Mate distance 剪枝 ---
    if alpha >= 10000:
        return alpha
    if beta <= -10000:
        return beta
    
    # --- 5. 获取走法排序 ---
    hash_move_encoded = -1
    if hash_entry != NULL and hash_entry.hash_key == state_hash:
        hash_move_encoded = hash_entry.best_move_encoded
        
    num_moves = c_get_ordered_moves(state, player_piece, hash_move_encoded, ordered_moves)
    
    if num_moves == 0:
        return -10000 if maximizing_player else 10000
    
    best_move_encoded = -1
    
    # --- 6. PVS + LMR 递归搜索 ---
    if maximizing_player:
        max_eval = -math.inf
        for i in range(num_moves):
            move_encoded = ordered_moves[i]
            start_idx = move_encoded >> 8
            end_idx = move_encoded & 0xFF
            
            is_capture_move = (state.board_c[end_idx] != EMPTY)
            old_hash = state.hash
            old_winner = state.winner
            captured = state.c_move_piece(start_idx, end_idx)
            
            reduction = 0
            if i >= 5 and depth >= 3 and not is_capture_move:
                reduction = 1
            
            if i == 0:
                evaluation = _alpha_beta(state, depth - 1, alpha, beta, False, settings)
            else:
                evaluation = _alpha_beta(state, depth - 1 - reduction, alpha, alpha + 1, False, settings)
                if alpha < evaluation < beta:
                    evaluation = _alpha_beta(state, depth - 1, alpha, beta, False, settings)

            state.c_unmake_piece(start_idx, end_idx, captured, old_hash, old_winner)

            if evaluation > max_eval:
                max_eval = evaluation
                best_move_encoded = move_encoded
            
            alpha = max(alpha, evaluation)
            if beta <= alpha:
                break
        eval_score = max_eval
    else: # minimizing_player
        min_eval = math.inf
        for i in range(num_moves):
            move_encoded = ordered_moves[i]
            start_idx = move_encoded >> 8
            end_idx = move_encoded & 0xFF
                
            is_capture_move = (state.board_c[end_idx] != EMPTY)
            old_hash = state.hash
            old_winner = state.winner
            captured = state.c_move_piece(start_idx, end_idx)
            
            reduction = 0
            if i >= 5 and depth >= 3 and not is_capture_move:
                reduction = 1
            
            if i == 0:
                evaluation = _alpha_beta(state, depth - 1, alpha, beta, True, settings)
            else:
                evaluation = _alpha_beta(state, depth - 1 - reduction, beta - 1, beta, True, settings)
                if alpha < evaluation < beta:
                    evaluation = _alpha_beta(state, depth - 1, alpha, beta, True, settings)

            state.c_unmake_piece(start_idx, end_idx, captured, old_hash, old_winner)

            if evaluation < min_eval:
                min_eval = evaluation
                best_move_encoded = move_encoded

            beta = min(beta, evaluation)
            if beta <= alpha:
                break
        eval_score = min_eval

    # --- 7. 存储到置换表 ---
    flag = EXACT_SCORE
    if eval_score <= original_alpha:
        flag = UPPER_BOUND
    elif eval_score >= beta:
        flag = LOWER_BOUND
    
    if transposition_table != NULL and best_move_encoded != -1:
        if hash_entry.depth <= depth or hash_entry.hash_key != state_hash:
            hash_entry.hash_key = state_hash
            hash_entry.depth = depth
            hash_entry.score = eval_score
            hash_entry.flag = flag
            hash_entry.best_move_encoded = best_move_encoded
    
    return eval_score