# core/search_manager.pyx
# cython: profile=False
import time
import math
import traceback
import pickle
import os
import threading
import copy

from libc.string cimport memcpy
from core.game_logic import GameState
from core.game_logic cimport GameState as CGameState
from core.game_logic cimport c_get_ordered_moves
from core.constants cimport CANNON, SOLDIER, EMPTY
# Heuristic evaluation disconnected

# 从 engine 导入 NNUE 资源
from core.engine cimport _alpha_beta, _acc_stack, _init_acc_at_root, g_evaluator_mode, NNUE_W1
from core.engine import set_evaluator_mode

# 基础设施导入
from core.search_infrastructure import (
    get_nodes_evaluated,
    reset_nodes_evaluated,
    clear_transposition_table
)
from core.search_infrastructure cimport (
    transposition_table,
    TT_SIZE,
    TTEntry,
    stop_search_flag,
    reset_nodes_evaluated_c
)

import cython

# --- PV 提取 ---
cdef list _extract_pv_from_tt(CGameState state, int max_depth):
    cdef list pv_line = []
    cdef unsigned long long state_hash
    cdef int move_encoded, depth = 0
    cdef TTEntry* hash_entry
    cdef set visited_hashes = set()

    while depth < max_depth:
        state_hash = state.hash
        if state_hash in visited_hashes: break
        visited_hashes.add(state_hash)
        if transposition_table == NULL: break
        hash_entry = &transposition_table[state_hash & (TT_SIZE - 1)]
        if hash_entry.hash_key != state_hash or hash_entry.best_move_encoded == -1: break
        move_encoded = hash_entry.best_move_encoded
        pv_line.append(move_encoded)
        state.c_move_piece(move_encoded >> 8, move_encoded & 0xFF)
        depth += 1
    return pv_line

@cython.boundscheck(False)
@cython.wraparound(False)
def find_best_move_iterative_deepening(CGameState state, dict settings, bint is_maximizing, object progress_callback=None, int thread_id=0, bint return_score=False, list game_history=None, bint return_all_stats=False):
    cdef int max_depth = settings["depth"]
    cdef float time_limit = settings["time_limit"]
    cdef int depth, i, j, num_moves, move_encoded, captured, old_winner
    cdef int player_piece = CANNON if is_maximizing else SOLDIER
    cdef int ordered_moves_c[64]
    cdef float score, current_depth_best_score, val, f_score
    cdef float current_alpha, current_beta
    cdef int current_depth_best_move = -1
    cdef unsigned long long old_hash
    cdef int feat_from, feat_to, feat_cap
    cdef bint not_maximizing = not is_maximizing
    global stop_search_flag

    if not settings.get("is_helper", False):
        # clear_evaluation_caches() # Disconnected
        clear_transposition_table()
        reset_nodes_evaluated_c()
        # 核心：根据设置切换评估模式
        set_evaluator_mode(1 if settings.get("use_nnue", False) else 0)

    # 0. 检查局面是否已经结束
    if state.winner != -1:
        f_score = 0.0
        if state.winner == CANNON: f_score = 10000.0
        elif state.winner == SOLDIER: f_score = -10000.0
        
        if return_all_stats: return None, f_score, {}
        if return_score: return None, f_score
        return None

    start_time = time.time()
    best_move_so_far = -1
    stop_event = settings.get("stop_event", None)
    stop_search_flag = 0
    
    # 初始化历史栈（Repetition Detection）
    cdef unsigned long long history_stack[256]
    cdef int history_len = 0
    if game_history:
        for h in game_history:
            if history_len < 256:
                history_stack[history_len] = h
                history_len += 1

    # NNUE 初始化
    if g_evaluator_mode == 1:
        _init_acc_at_root(state, thread_id)

    root_moves_stats = {}

    for depth in range(1, max_depth + 1):
        elapsed_time = time.time() - start_time
        if depth > 1 and (elapsed_time * 2.5 > (time_limit - elapsed_time) or elapsed_time > time_limit * 0.8):
            break
        if stop_event and stop_event.is_set():
            break

        num_moves = c_get_ordered_moves(state, player_piece, best_move_so_far, ordered_moves_c)
        current_depth_best_move = -1
        current_depth_best_score = -20000 if is_maximizing else 20000
        current_alpha, current_beta = -20000, 20000
        root_moves_stats.clear()

        for i in range(num_moves):
            if stop_event and stop_event.is_set():
                stop_search_flag = 1
                break

            move_encoded = ordered_moves_c[i]
            old_hash, old_winner = state.hash, state.winner
            captured = state.c_move_piece(move_encoded >> 8, move_encoded & 0xFF)

            if g_evaluator_mode == 1:
                feat_from = (move_encoded >> 8) if player_piece == SOLDIER else (move_encoded >> 8) + 25
                feat_to = (move_encoded & 0xFF) if player_piece == SOLDIER else (move_encoded & 0xFF) + 25
                feat_cap = (move_encoded & 0xFF) if captured == SOLDIER else -1
                
                if player_piece == CANNON:
                    if feat_cap != -1:
                        for j in range(256):
                            _acc_stack[thread_id][1][j] = _acc_stack[thread_id][0][j] + NNUE_W1[feat_to][j] - NNUE_W1[feat_from][j] - NNUE_W1[feat_cap][j] - NNUE_W1[50][j]
                    else:
                        for j in range(256):
                            _acc_stack[thread_id][1][j] = _acc_stack[thread_id][0][j] + NNUE_W1[feat_to][j] - NNUE_W1[feat_from][j] - NNUE_W1[50][j]
                else:
                    if feat_cap != -1:
                        for j in range(256):
                            _acc_stack[thread_id][1][j] = _acc_stack[thread_id][0][j] + NNUE_W1[feat_to][j] - NNUE_W1[feat_from][j] - NNUE_W1[feat_cap][j] + NNUE_W1[50][j]
                    else:
                        for j in range(256):
                            _acc_stack[thread_id][1][j] = _acc_stack[thread_id][0][j] + NNUE_W1[feat_to][j] - NNUE_W1[feat_from][j] + NNUE_W1[50][j]

            if i == 0:
                with nogil:
                    score = _alpha_beta(state, depth - 1, current_alpha, current_beta, not_maximizing, thread_id, 1, history_stack, history_len)
            else:
                if is_maximizing:
                    with nogil:
                        score = _alpha_beta(state, depth - 1, current_alpha, current_alpha + 1, not_maximizing, thread_id, 1, history_stack, history_len)
                        if score > current_alpha and score < current_beta:
                            score = _alpha_beta(state, depth - 1, current_alpha, current_beta, not_maximizing, thread_id, 1, history_stack, history_len)
                else:
                    with nogil:
                        score = _alpha_beta(state, depth - 1, current_beta - 1, current_beta, not_maximizing, thread_id, 1, history_stack, history_len)
                        if score > current_alpha and score < current_beta:
                            score = _alpha_beta(state, depth - 1, current_alpha, current_beta, not_maximizing, thread_id, 1, history_stack, history_len)

            state.c_unmake_piece(move_encoded >> 8, move_encoded & 0xFF, captured, old_hash, old_winner)
            root_moves_stats[move_encoded] = score

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
                
            # --- 核心修复：搜到必胜走法（包括 NNUE 蒸馏的高分）立即终止当前深度对其余走法的探索 ---
            if (is_maximizing and score >= 9900) or (not is_maximizing and score <= -9900):
                stop_search_flag = 1
                break

        if current_depth_best_move != -1:
            best_move_so_far = current_depth_best_move
            if progress_callback:
                dummy_state = copy.deepcopy(state)
                current_depth_best_line = _extract_pv_from_tt(dummy_state, depth)
                decoded_best = (((current_depth_best_move>>8)//5, (current_depth_best_move>>8)%5), ((current_depth_best_move&0xFF)//5, (current_depth_best_move&0xFF)%5))
                decoded_line = [(((m>>8)//5, (m>>8)%5), ((m&0xFF)//5, (m&0xFF)%5)) for m in current_depth_best_line]
                decoded_stats = {(((m>>8)//5, (m>>8)%5), ((m&0xFF)//5, (m&0xFF)%5)): s for m, s in root_moves_stats.items()}
                progress_callback(depth, current_depth_best_score, decoded_best, decoded_line, decoded_stats)

        if (stop_event and stop_event.is_set()) or abs(current_depth_best_score) >= 9900:
            break

    decoded_stats = {(((m>>8)//5, (m>>8)%5), ((m&0xFF)//5, (m&0xFF)%5)): s for m, s in root_moves_stats.items()}
    if best_move_so_far != -1:
        m = best_move_so_far
        move = (((m>>8)//5, (m>>8)%5), ((m&0xFF)//5, (m&0xFF)%5))
        if return_all_stats:
            return move, current_depth_best_score, decoded_stats
        if return_score:
            return move, current_depth_best_score
        return move
    if return_all_stats:
        return None, 0.0, decoded_stats
    if return_score:
        return None, 0.0
    return None

def find_best_move_parallel(CGameState state, dict settings, bint is_maximizing, object progress_callback=None, bint return_score=False, list game_history=None, bint return_all_stats=False):
    num_threads = settings.get("num_threads", 4)
    use_nnue = settings.get("use_nnue", False)
    
    set_evaluator_mode(1 if use_nnue else 0)
    clear_transposition_table()
    reset_nodes_evaluated_c()
    
    global stop_search_flag
    stop_search_flag = 0
    
    threads = []
    stop_event = settings.get("stop_event", threading.Event())
    settings["stop_event"] = stop_event
    
    helper_settings = settings.copy()
    helper_settings["is_helper"] = True
    for i in range(1, num_threads):
        t = threading.Thread(
            target=find_best_move_iterative_deepening, 
            args=(copy.deepcopy(state), helper_settings, is_maximizing, None, i, False, game_history), 
            name=f"SearchThread-{i}"
        )
        t.daemon = True
        t.start()
        threads.append(t)
        
    result = find_best_move_iterative_deepening(state, settings, is_maximizing, progress_callback, 0, return_score, game_history, return_all_stats)
    stop_event.set()
    for t in threads:
        t.join(timeout=1.0)
    return result