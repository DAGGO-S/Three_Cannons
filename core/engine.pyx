# core/engine.pyx
# cython: boundscheck=False, wraparound=False, nonecheck=False, cdivision=True

from libc.string cimport memcpy
from core.game_logic cimport GameState
from core.zobrist_hashing cimport ZobristHasher, _hasher
from core.constants cimport CANNON, SOLDIER, DRAW
from core.nnue_evaluator cimport c_evaluate_nnue
from core.game_logic cimport c_get_ordered_moves
from core.search_infrastructure cimport (
    transposition_table, 
    TT_SIZE, 
    TTEntry,
    EXACT_SCORE, 
    LOWER_BOUND, 
    UPPER_BOUND,
    _thread_nodes,
    stop_search_flag
)

import cython
# Heuristic evaluation disconnected

# NNUE 增量更新资源
cdef float _acc_stack[64][64][256]

cdef extern from "nnue_weights.h":
    # const float NNUE_W1[51][256]  # 已经在 engine.pxd 中定义，这里不再重复定义
    const float NNUE_B1[256]
    const float NNUE_W2_T[256][32]
    const float NNUE_B2[32]
    const float NNUE_W3[32]
    const float NNUE_B3

cdef void _init_acc_at_root(GameState state, int thread_id) noexcept nogil:
    cdef int i, j
    for i in range(256):
        _acc_stack[thread_id][0][i] = NNUE_B1[i]
    for i in range(25):
        if state.board_c[i] == SOLDIER:
            for j in range(256):
                _acc_stack[thread_id][0][j] += NNUE_W1[i][j]
        elif state.board_c[i] == CANNON:
            for j in range(256):
                _acc_stack[thread_id][0][j] += NNUE_W1[i + 25][j]
    if state.current_player == CANNON:
        for j in range(256):
            _acc_stack[thread_id][0][j] += NNUE_W1[50][j]

cdef int g_evaluator_mode = 0

def set_evaluator_mode(int mode):
    global g_evaluator_mode
    g_evaluator_mode = mode

@cython.boundscheck(False)
@cython.wraparound(False)
cdef float _alpha_beta(GameState state, int depth, float alpha, float beta, bint maximizing_player, int thread_id, int ply, unsigned long long* history_stack, int history_len) noexcept nogil:
    _thread_nodes[thread_id] += 1
    if (_thread_nodes[thread_id] & 4095) == 0:
        if stop_search_flag: return 0.0
    
    cdef unsigned long long state_hash = state.hash

    # 1. 循环检测（三手重复判定，对应三手循环规则）
    cdef int i_hist, rep_count = 0
    for i_hist in range(history_len):
        if history_stack[i_hist] == state_hash:
            rep_count += 1
            if rep_count >= 2: # 如果加上当前这次是第 3 次出现
                if state.soldier_count >= 9:
                    return 0.0       # 9子及以上，和棋强制判定为平局 (强迫兵方进攻)
                else:
                    return 5000.0    # 兵数稀少 (<=8) 时，和棋判炮胜 (奖励顽强防御)
    
    cdef float original_alpha = alpha
    cdef int player_piece = CANNON if maximizing_player else SOLDIER
    cdef int hash_move_encoded = -1
    cdef int ordered_moves[64]
    cdef int num_moves, i, j, best_move_encoded = -1
    cdef float max_eval, min_eval, evaluation, eval_score, val
    cdef float acc2[32]
    cdef unsigned long long old_hash
    cdef int old_winner, captured, feat_from, feat_to, feat_cap
    cdef TTEntry* hash_entry = &transposition_table[state_hash & (TT_SIZE - 1)]
    
    # 将当前哈希入栈以便深入搜索
    history_stack[history_len] = state_hash
    cdef int next_history_len = history_len + 1
    
    if hash_entry.hash_key == state_hash:
        if hash_entry.depth >= depth:
            val = hash_entry.score
            # >>> 三复局保护：如果该位置已在路径中出现过，不轻易跳出普通评分，除非是必杀分 <<<
            if rep_count == 0 or abs(val) >= 9999:
                if hash_entry.flag == EXACT_SCORE: return val
                if hash_entry.flag == LOWER_BOUND: alpha = max(alpha, val)
                elif hash_entry.flag == UPPER_BOUND: beta = min(beta, val)
                if alpha >= beta: return val
        hash_move_encoded = hash_entry.best_move_encoded
    # 4. 检查游戏是否结束
    if state.winner != -1:
        if state.winner == CANNON:
            return 10000.0  # 必杀胜利
        if state.winner == SOLDIER:
            return -10000.0 # 必杀胜利
        if state.winner == DRAW:
            return 0.0      # 真正的平局
        return 0.0
    
    if depth <= 0:
        # 【极限加速点 1】重构点积顺序，利用 AVX2 完成 256x32 计算
        for i in range(32):
            acc2[i] = NNUE_B2[i]
        
        # 引入指针以获得最高寻址效率
        prev_acc = _acc_stack[thread_id][ply]
        
        for j in range(256):
            val = prev_acc[j]
            if val > 0.0: # ReLU
                # 此处内层循环 32 次，连续内存访问，利于编译器自动向量化
                for i in range(32):
                    acc2[i] += val * NNUE_W2_T[j][i]

        eval_score = NNUE_B3
        for i in range(32):
            if acc2[i] > 0.0:
                eval_score += acc2[i] * NNUE_W3[i]
        return eval_score
    
    num_moves = c_get_ordered_moves(state, player_piece, hash_move_encoded, ordered_moves)
    if num_moves == 0: return -10000 if maximizing_player else 10000

    if maximizing_player:
        max_eval = -20000
        for i in range(num_moves):
            old_hash, old_winner = state.hash, state.winner
            captured = state.c_move_piece(ordered_moves[i] >> 8, ordered_moves[i] & 0xFF)
            if g_evaluator_mode == 1:
                feat_from = (ordered_moves[i] >> 8) if player_piece == SOLDIER else (ordered_moves[i] >> 8) + 25
                feat_to = (ordered_moves[i] & 0xFF) if player_piece == SOLDIER else (ordered_moves[i] & 0xFF) + 25
                feat_cap = (ordered_moves[i] & 0xFF) if captured == SOLDIER else -1
                
                if player_piece == CANNON:
                    if feat_cap != -1:
                        for j in range(256):
                            _acc_stack[thread_id][ply+1][j] = _acc_stack[thread_id][ply][j] + NNUE_W1[feat_to][j] - NNUE_W1[feat_from][j] - NNUE_W1[feat_cap][j] - NNUE_W1[50][j]
                    else:
                        for j in range(256):
                            _acc_stack[thread_id][ply+1][j] = _acc_stack[thread_id][ply][j] + NNUE_W1[feat_to][j] - NNUE_W1[feat_from][j] - NNUE_W1[50][j]
                else:
                    if feat_cap != -1:
                        for j in range(256):
                            _acc_stack[thread_id][ply+1][j] = _acc_stack[thread_id][ply][j] + NNUE_W1[feat_to][j] - NNUE_W1[feat_from][j] - NNUE_W1[feat_cap][j] + NNUE_W1[50][j]
                    else:
                        for j in range(256):
                            _acc_stack[thread_id][ply+1][j] = _acc_stack[thread_id][ply][j] + NNUE_W1[feat_to][j] - NNUE_W1[feat_from][j] + NNUE_W1[50][j]
            evaluation = _alpha_beta(state, depth - 1, alpha, beta, False, thread_id, ply + 1, history_stack, next_history_len)
            state.c_unmake_piece(ordered_moves[i] >> 8, ordered_moves[i] & 0xFF, captured, old_hash, old_winner)
            if evaluation > max_eval:
                max_eval = evaluation
                best_move_encoded = ordered_moves[i]
            alpha = max(alpha, evaluation)
            if beta <= alpha: break
        eval_score = max_eval
    else:
        min_eval = 20000
        for i in range(num_moves):
            old_hash, old_winner = state.hash, state.winner
            captured = state.c_move_piece(ordered_moves[i] >> 8, ordered_moves[i] & 0xFF)
            if g_evaluator_mode == 1:
                feat_from = (ordered_moves[i] >> 8) if player_piece == SOLDIER else (ordered_moves[i] >> 8) + 25
                feat_to = (ordered_moves[i] & 0xFF) if player_piece == SOLDIER else (ordered_moves[i] & 0xFF) + 25
                feat_cap = (ordered_moves[i] & 0xFF) if captured == SOLDIER else -1
                
                if player_piece == CANNON:
                    if feat_cap != -1:
                        for j in range(256):
                            _acc_stack[thread_id][ply+1][j] = _acc_stack[thread_id][ply][j] + NNUE_W1[feat_to][j] - NNUE_W1[feat_from][j] - NNUE_W1[feat_cap][j] - NNUE_W1[50][j]
                    else:
                        for j in range(256):
                            _acc_stack[thread_id][ply+1][j] = _acc_stack[thread_id][ply][j] + NNUE_W1[feat_to][j] - NNUE_W1[feat_from][j] - NNUE_W1[50][j]
                else:
                    if feat_cap != -1:
                        for j in range(256):
                            _acc_stack[thread_id][ply+1][j] = _acc_stack[thread_id][ply][j] + NNUE_W1[feat_to][j] - NNUE_W1[feat_from][j] - NNUE_W1[feat_cap][j] + NNUE_W1[50][j]
                    else:
                        for j in range(256):
                            _acc_stack[thread_id][ply+1][j] = _acc_stack[thread_id][ply][j] + NNUE_W1[feat_to][j] - NNUE_W1[feat_from][j] + NNUE_W1[50][j]
            evaluation = _alpha_beta(state, depth - 1, alpha, beta, True, thread_id, ply + 1, history_stack, next_history_len)
            state.c_unmake_piece(ordered_moves[i] >> 8, ordered_moves[i] & 0xFF, captured, old_hash, old_winner)
            if evaluation < min_eval:
                min_eval = evaluation
                best_move_encoded = ordered_moves[i]
            beta = min(beta, evaluation)
            if beta <= alpha: break
        eval_score = min_eval

    if hash_entry.depth <= depth or hash_entry.hash_key != state_hash:
        hash_entry.hash_key = state_hash
        hash_entry.depth = depth
        hash_entry.score = eval_score
        hash_entry.best_move_encoded = best_move_encoded
        if eval_score <= original_alpha: hash_entry.flag = UPPER_BOUND
        elif eval_score >= beta: hash_entry.flag = LOWER_BOUND
        else: hash_entry.flag = EXACT_SCORE
    return eval_score
