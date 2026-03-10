# cython: profile=True
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
    cdef int player_piece, opponent_piece, r, c
    cdef tuple move, end_pos
    cdef list capture_moves = []
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

    # 3. 只生成吃子走法
    player_piece = CANNON if maximizing_player else SOLDIER
    opponent_piece = SOLDIER if player_piece == CANNON else CANNON
    
    for r in range(5):
        for c in range(5):
            if state.board_c[r * 5 + c] == player_piece:
                for end_pos in state.get_valid_moves(r, c):
                    if state.board_c[end_pos[0] * 5 + end_pos[1]] == opponent_piece:
                        capture_moves.append(((r, c), end_pos))
    
    # 4. 递归搜索吃子走法
    cdef unsigned long long old_hash
    cdef int old_winner, captured

    if maximizing_player:
        for move in capture_moves:
            if stop_event and stop_event.is_set():
                break
            old_hash = state.hash
            old_winner = state.winner
            captured = state.c_move_piece(move[0][0]*5 + move[0][1], move[1][0]*5 + move[1][1])
            
            evaluation, _, _ = _quiescence_search(state, alpha, beta, False, settings, qs_depth + 1)
            
            state.c_unmake_piece(move[0][0]*5 + move[0][1], move[1][0]*5 + move[1][1], captured, old_hash, old_winner)
            
            alpha = max(alpha, evaluation)
            if beta <= alpha:
                return beta, None, []
        return alpha, None, []
    else:
        for move in capture_moves:
            if stop_event and stop_event.is_set():
                break
                
            old_hash = state.hash
            old_winner = state.winner
            captured = state.c_move_piece(move[0][0]*5 + move[0][1], move[1][0]*5 + move[1][1])
            
            evaluation, _, _ = _quiescence_search(state, alpha, beta, True, settings, qs_depth + 1)
            
            state.c_unmake_piece(move[0][0]*5 + move[0][1], move[1][0]*5 + move[1][1], captured, old_hash, old_winner)
            
            beta = min(beta, evaluation)
            if beta <= alpha:
                return alpha, None, []
        return beta, None, []

# --- 迭代加深搜索主入口 ---
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
                    score, _, line = _alpha_beta(state, depth - 1, -math.inf, math.inf, not is_maximizing, settings)
                else:
                    score, _, line = _alpha_beta(state, depth - 1, -math.inf, math.inf, not is_maximizing, settings)
            else:
                if i == 0:
                    score, _, line = _alpha_beta(state, depth - 1, current_alpha, current_beta, not is_maximizing, settings)
                else:
                    if is_maximizing:
                        score, _, line = _alpha_beta(state, depth - 1, current_alpha, current_alpha + 1, not is_maximizing, settings)
                        if current_alpha < score < current_beta:
                             score, _, line = _alpha_beta(state, depth - 1, current_alpha, current_beta, not is_maximizing, settings)
                    else:
                        score, _, line = _alpha_beta(state, depth - 1, current_beta - 1, current_beta, not is_maximizing, settings)
                        if current_alpha < score < current_beta:
                             score, _, line = _alpha_beta(state, depth - 1, current_alpha, current_beta, not is_maximizing, settings)

            state.c_unmake_piece(start_idx, end_idx, captured, old_hash, old_winner)

            # 记录分数 (存 16bit encode值)
            root_moves_stats[move_encoded] = score

            # 更新最佳 (用于最终走棋决策)
            if is_maximizing:
                if score > current_depth_best_score:
                    current_depth_best_score = score
                    current_depth_best_move = move_encoded
                    current_depth_best_line = [move_encoded] + line
                current_alpha = max(current_alpha, score)
            else:
                if score < current_depth_best_score:
                    current_depth_best_score = score
                    current_depth_best_move = move_encoded
                    current_depth_best_line = [move_encoded] + line
                current_beta = min(current_beta, score)

        # 本层迭代结束
        if not stop_event.is_set():
            current_iter_time = time.time() - start_time
            if current_iter_time < time_limit:
                 best_move_so_far = current_depth_best_move
                 best_line_so_far = current_depth_best_line
                 # 回调：解压缩传回 GUI 可识别的 ((r,c), (r,c)) 数据结构
                 if progress_callback:
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
cdef tuple _alpha_beta(CGameState state, int depth, float alpha, float beta, bint maximizing_player, object settings):
    """
    实现了置换表、PVS、空着剪枝(NMP)、晚走缩减(LMR)的Alpha-Beta搜索。
    """
    stop_event = settings.get("stop_event", None)
    
    global _total_nodes_evaluated
    _total_nodes_evaluated += 1
    
    cdef float original_alpha = alpha
    cdef int player_piece = CANNON if maximizing_player else SOLDIER
    cdef int hash_move_encoded
    cdef int ordered_moves[64]
    cdef int num_moves
    cdef int best_move_encoded
    cdef int move_encoded, start_idx, end_idx
    cdef list best_line, line
    cdef int i
    cdef float max_eval, min_eval, evaluation, eval_score
    cdef bint is_capture_move  # P4: LMR 判断是否吃子
    cdef int reduction  # P4: LMR 减层数
    
    cdef unsigned long long state_hash = state.hash
    cdef int tt_index = <int>(state_hash & (TT_SIZE - 1))
    cdef int flag
    cdef TTEntry* hash_entry = NULL
    
    cdef unsigned long long old_hash
    cdef int old_winner, captured
    
    # --- 1. 查找置换表 ---
    # 【Phase1优化】定长数组 + 位掩码取模 + full hash 校验，完全无 Boxing！
    if transposition_table != NULL:
        hash_entry = &transposition_table[tt_index]
        if hash_entry.hash_key == state_hash and hash_entry.depth >= depth:
            if hash_entry.flag == EXACT_SCORE:
                return hash_entry.score, hash_entry.best_move_encoded, [hash_entry.best_move_encoded]
            elif hash_entry.flag == LOWER_BOUND:
                alpha = max(alpha, hash_entry.score)
            elif hash_entry.flag == UPPER_BOUND:
                beta = min(beta, hash_entry.score)
            if alpha >= beta:
                return hash_entry.score, hash_entry.best_move_encoded, [hash_entry.best_move_encoded]

    # --- 2. 终止条件 ---
    if state.winner != -1:
        return (10000 if state.winner == CANNON else -10000), -1, []
    
    # 【P0优化】达到搜索深度，原本进入静默搜索，现阶段为测试极致静态评估性能而屏蔽 QS
    if depth == 0:
        score = c_evaluate_board(state)
        return score, -1, []
    
    # --- 3. Mate distance 剪枝 ---
    if alpha >= 10000:
        return alpha, -1, []
    if beta <= -10000:
        return beta, -1, []
    
    # --- 5. 获取排序后的走法列表 (C数组，零分配) ---
    hash_move_encoded = -1
    if hash_entry != NULL and hash_entry.hash_key == state_hash:
        hash_move_encoded = hash_entry.best_move_encoded
        
    num_moves = c_get_ordered_moves(state, player_piece, hash_move_encoded, ordered_moves)
    
    if num_moves == 0:
        return (-10000 if maximizing_player else 10000), -1, []
    
    best_move_encoded = -1
    best_line = []
    
    # --- 6. PVS + LMR 递归搜索 ---
    if maximizing_player:
        max_eval = -math.inf
        for i in range(num_moves):
            if stop_event and stop_event.is_set():
                break
                
            move_encoded = ordered_moves[i]
            start_idx = move_encoded >> 8
            end_idx = move_encoded & 0xFF
            
            is_capture_move = (state.board_c[end_idx] != EMPTY)
            
            old_hash = state.hash
            old_winner = state.winner
            captured = state.c_move_piece(start_idx, end_idx)
            
            # 【P4优化】后期非吃子走法做浅搜索
            reduction = 0
            if i >= 5 and depth >= 3 and not is_capture_move:
                reduction = 1
            
            if i == 0:
                evaluation, _, line = _alpha_beta(state, depth - 1, alpha, beta, False, settings)
            else:
                evaluation, _, line = _alpha_beta(state, depth - 1 - reduction, alpha, alpha + 1, False, settings)
                if alpha < evaluation < beta:
                    evaluation, _, line = _alpha_beta(state, depth - 1, alpha, beta, False, settings)

            state.c_unmake_piece(start_idx, end_idx, captured, old_hash, old_winner)

            if evaluation > max_eval:
                max_eval = evaluation
                best_move_encoded = move_encoded
                best_line = [move_encoded] + line
            
            alpha = max(alpha, evaluation)
            if beta <= alpha:
                break
        eval_score = max_eval
    else: # minimizing_player
        min_eval = math.inf
        for i in range(num_moves):
            if stop_event and stop_event.is_set():
                break
                
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
                evaluation, _, line = _alpha_beta(state, depth - 1, alpha, beta, True, settings)
            else:
                evaluation, _, line = _alpha_beta(state, depth - 1 - reduction, beta - 1, beta, True, settings)
                if alpha < evaluation < beta:
                    evaluation, _, line = _alpha_beta(state, depth - 1, alpha, beta, True, settings)

            state.c_unmake_piece(start_idx, end_idx, captured, old_hash, old_winner)

            if evaluation < min_eval:
                min_eval = evaluation
                best_move_encoded = move_encoded
                best_line = [move_encoded] + line

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
    
    # 【Phase1优化】定长数组存储
    if transposition_table != NULL and best_move_encoded != -1:
        if hash_entry.depth <= depth or hash_entry.hash_key != state_hash:
            hash_entry.hash_key = state_hash
            hash_entry.depth = depth
            hash_entry.score = eval_score
            hash_entry.flag = flag
            hash_entry.best_move_encoded = best_move_encoded
    
    return eval_score, best_move_encoded, best_line