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

# Cython imports
from cython cimport Py_ssize_t

ctypedef Py_ssize_t int
ctypedef double float
ctypedef bint bool

# --- 置换表和相关常量 ---
# 【Phase1优化】定长数组 + 哈希取模，消除 O(N) 清理
cdef int TT_SIZE = 1 << 21  # 2,097,152 个槽位
transposition_table = [None] * TT_SIZE
EXACT_SCORE = 0
LOWER_BOUND = 1
UPPER_BOUND = 2

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
    transposition_table = [None] * TT_SIZE

def save_transposition_table(filepath):
    """保存置换表到文件（只序列化非空条目）"""
    global transposition_table
    try:
        # 只保存非 None 条目，格式：{index: entry}
        data_to_save = {}
        for i in range(TT_SIZE):
            if transposition_table[i] is not None:
                data_to_save[i] = transposition_table[i]
        with open(filepath, 'wb') as f:
            pickle.dump(data_to_save, f)
        print(f"DEBUG: Saved {len(data_to_save)} entries to {filepath}")
    except Exception as e:
        print(f"Warning: Failed to save AI memory: {e}")

def load_transposition_table(filepath):
    """从文件加载置换表"""
    global transposition_table
    if not os.path.exists(filepath):
        print("DEBUG: AI memory file not found, starting fresh.")
        return
    
    try:
        with open(filepath, 'rb') as f:
            data = pickle.load(f)
            if isinstance(data, dict):
                # 兼容旧格式（key=hash, value=4-tuple）和新格式（key=index, value=5-tuple）
                loaded_count = 0
                for key, entry in data.items():
                    # 旧格式 entry 只有 4 字段，需要补全 hash 字段
                    if len(entry) == 4:
                        # 旧格式：key 本身就是 hash
                        entry = entry + (key,)
                    idx = <int>(key % TT_SIZE)
                    transposition_table[idx] = entry
                    loaded_count += 1
                print(f"DEBUG: Loaded {len(data)} entries from {filepath}")
            else:
                print("Warning: Corrupt AI memory file.")
    except Exception as e:
        print(f"Warning: Failed to load AI memory: {e}")

# --- 辅助函数：走法排序 ---
@cython.boundscheck(False)
@cython.wraparound(False)
cdef list _get_ordered_moves(CGameState state, int player_piece, tuple hash_move):
    """
    生成并排序所有合法走法。
    排序优先级：hash_move > 吃子 > 安静走法
    """
    cdef list all_moves = []
    cdef list captures = []
    cdef list quiet_moves = []
    cdef int opponent_piece = SOLDIER if player_piece == CANNON else CANNON
    cdef int r, c
    cdef tuple move, end_pos

    for r in range(5):
        for c in range(5):
            if state.board_c[r * 5 + c] == player_piece:
                for end_pos in state.get_valid_moves(r, c):
                    move = ((r, c), end_pos)
                    # 【P7优化】生成时跳过 hash_move，避免后续 O(n) 的 list.remove
                    if move == hash_move:
                        continue
                    if state.board_c[end_pos[0] * 5 + end_pos[1]] == opponent_piece:
                        captures.append(move)
                    else:
                        quiet_moves.append(move)

    if hash_move:
        all_moves.append(hash_move)
    
    all_moves.extend(captures)
    all_moves.extend(quiet_moves)
    return all_moves

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
    
    # 1. 静态评估
    stand_pat_score, _ = evaluate_board(state, None)

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
    if maximizing_player:
        for move in capture_moves:
            if stop_event and stop_event.is_set():
                break
            new_state = state.move_piece(move[0][0], move[0][1], move[1][0], move[1][1])
            evaluation, _, _ = _quiescence_search(new_state, alpha, beta, False, settings, qs_depth + 1)
            alpha = max(alpha, evaluation)
            if beta <= alpha:
                return beta, None, []
        return alpha, None, []
    else:
        for move in capture_moves:
            if stop_event and stop_event.is_set():
                break
            new_state = state.move_piece(move[0][0], move[0][1], move[1][0], move[1][1])
            evaluation, _, _ = _quiescence_search(new_state, alpha, beta, True, settings, qs_depth + 1)
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
    stop_event = settings.get("stop_event", None)
    cdef int depth

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
        # 这样我们才能获取每个根走法的即时分数
        
        # 1. 获取并排序根节点走法
        player_piece = CANNON if is_maximizing else SOLDIER
        root_ordered_moves = _get_ordered_moves(state, player_piece, best_move_so_far)
        
        current_depth_best_move = None
        current_depth_best_score = -math.inf if is_maximizing else math.inf
        current_depth_best_line = []
        
        # Alpha-Beta 窗口
        current_alpha = -math.inf
        current_beta = math.inf
        
        # 检查是否开启了分析模式
        analysis_mode = settings.get("analysis_mode", False)

        root_moves_stats.clear() # 每个深度清空一次，保证是最新的评估

        for i, move in enumerate(root_ordered_moves):
            if stop_event and stop_event.is_set():
                break
            
            # 执行一步
            new_state = state.move_piece(move[0][0], move[0][1], move[1][0], move[1][1])
            
            # --- 关键逻辑分支 ---
            if analysis_mode:
                # 分析模式：为了获取每个走法的精确得分，我们必须禁用根节点的窗口传递
                # 对每个根走法都使用全窗口搜索 (-inf, inf)
                # 这会牺牲性能，但能保证 visible scores 是准确的（不是 fail-low/high 的边界值）
                if is_maximizing:
                     # 下一层是 minimizing
                    score, _, line = _alpha_beta(new_state, depth - 1, -math.inf, math.inf, not is_maximizing, settings)
                else:
                    score, _, line = _alpha_beta(new_state, depth - 1, -math.inf, math.inf, not is_maximizing, settings)
            else:
                # 正常模式：使用 PVS 和 窗口传递，追求最高性能
                if i == 0:
                    score, _, line = _alpha_beta(new_state, depth - 1, current_alpha, current_beta, not is_maximizing, settings)
                else:
                    # 零窗口搜索
                    if is_maximizing:
                        score, _, line = _alpha_beta(new_state, depth - 1, current_alpha, current_alpha + 1, not is_maximizing, settings)
                        if current_alpha < score < current_beta:
                             score, _, line = _alpha_beta(new_state, depth - 1, current_alpha, current_beta, not is_maximizing, settings)
                    else:
                        score, _, line = _alpha_beta(new_state, depth - 1, current_beta - 1, current_beta, not is_maximizing, settings)
                        if current_alpha < score < current_beta:
                             score, _, line = _alpha_beta(new_state, depth - 1, current_alpha, current_beta, not is_maximizing, settings)

            # 记录分数
            root_moves_stats[move] = score

            # 更新最佳 (用于最终走棋决策)
            if is_maximizing:
                if score > current_depth_best_score:
                    current_depth_best_score = score
                    current_depth_best_move = move
                    current_depth_best_line = [move] + line
                current_alpha = max(current_alpha, score)
            else:
                if score < current_depth_best_score:
                    current_depth_best_score = score
                    current_depth_best_move = move
                    current_depth_best_line = [move] + line
                current_beta = min(current_beta, score)

        # 本层迭代结束
        if not stop_event.is_set():
            current_iter_time = time.time() - start_time
            if current_iter_time < time_limit:
                 best_move_so_far = current_depth_best_move
                 best_line_so_far = current_depth_best_line
                 # 回调：多传一个 root_moves_stats
                 if progress_callback:
                     # **API 变更说明**：这里多传了一个参数
                     progress_callback(depth, current_depth_best_score, current_depth_best_move, current_depth_best_line, root_moves_stats.copy())
            else:
                if progress_callback:
                     print(f"时间限制，完成深度 {depth-1} 的搜索。")
                break
        else:
            break

    return best_move_so_far


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
    cdef object hash_entry
    cdef tuple best_move, move
    cdef list best_line, line, ordered_moves
    cdef int player_piece, i
    cdef float max_eval, min_eval, evaluation, eval_score
    cdef bint is_capture_move  # P4: LMR 判断是否吃子
    cdef int reduction  # P4: LMR 减层数
    cdef int store_index  # Phase1: 置换表存储位置
    
    # --- 1. 查找置换表 ---
    # 【Phase1优化】定长数组 + 哈希取模 + full hash 校验
    cdef unsigned long long state_hash = state.hash
    cdef int tt_index = <int>(state_hash % TT_SIZE)
    hash_entry = transposition_table[tt_index]
    if hash_entry and hash_entry[4] == state_hash and hash_entry[1] >= depth:  # [4]=hash, [1]=depth
        tt_score, tt_depth, tt_flag, tt_move, _ = hash_entry
        if tt_flag == EXACT_SCORE:
            return tt_score, tt_move, [tt_move]
        elif tt_flag == LOWER_BOUND:
            alpha = max(alpha, tt_score)
        elif tt_flag == UPPER_BOUND:
            beta = min(beta, tt_score)
        if alpha >= beta:
            return tt_score, tt_move, [tt_move]

    # --- 2. 终止条件 ---
    if state.winner != -1:
        return (10000 if state.winner == CANNON else -10000), None, []
    
    # 【P0优化】达到搜索深度，进入静默搜索
    if depth == 0:
        score, _, _ = _quiescence_search(state, alpha, beta, maximizing_player, settings)
        if stop_event and stop_event.is_set():
            return 0.0, None, []
        return score, None, []
    
    # --- 3. Mate distance 剪枝 ---
    if alpha >= 10000:
        return alpha, None, []
    if beta <= -10000:
        return beta, None, []
    
    
    # --- 4. 【P3优化】Null Move Pruning ---
    # Disabled for debugging Bug #2 and potential Zugzwang issues
    # if depth >= 3:
    #     null_state = state.pass_turn()
    #     null_score, _, _ = _alpha_beta(null_state, depth - 3, -beta, -beta + 1, not maximizing_player, settings)
    #     if maximizing_player and null_score >= beta:
    #         return beta, None, []
    #     elif not maximizing_player and null_score <= alpha:
    #         return alpha, None, []
    
    # --- 5. 获取排序后的走法列表 ---
    player_piece = CANNON if maximizing_player else SOLDIER
    # 只有当 hash_entry 校验通过时才使用 hash_move
    hash_move = hash_entry[3] if (hash_entry and hash_entry[4] == state_hash) else None  # [3]=best_move, [4]=hash
    ordered_moves = _get_ordered_moves(state, player_piece, hash_move)
    
    if not ordered_moves:
        return (-10000 if maximizing_player else 10000), None, []
    
    best_move = None
    best_line = []
    
    # --- 6. PVS + LMR 递归搜索 ---
    if maximizing_player:
        max_eval = -math.inf
        for i, move in enumerate(ordered_moves):
            if stop_event and stop_event.is_set():
                break
                
            new_state = state.move_piece(move[0][0], move[0][1], move[1][0], move[1][1])
            
            # 【P4优化】后期非吃子走法做浅搜索
            is_capture_move = (state.board_c[move[1][0] * 5 + move[1][1]] != EMPTY)
            reduction = 0
            if i >= 5 and depth >= 3 and not is_capture_move:
                reduction = 1
            
            if i == 0:
                evaluation, _, line = _alpha_beta(new_state, depth - 1, alpha, beta, False, settings)
            else:
                # 零窗口搜索（可能带 LMR 减层）
                evaluation, _, line = _alpha_beta(new_state, depth - 1 - reduction, alpha, alpha + 1, False, settings)
                # 如果零窗口搜索失败，用全窗口重搜
                if alpha < evaluation < beta:
                    evaluation, _, line = _alpha_beta(new_state, depth - 1, alpha, beta, False, settings)

            if evaluation > max_eval:
                max_eval = evaluation
                best_move = move
                best_line = [move] + line
            
            alpha = max(alpha, evaluation)
            if beta <= alpha:
                break
        eval_score = max_eval
    else: # minimizing_player
        min_eval = math.inf
        for i, move in enumerate(ordered_moves):
            if stop_event and stop_event.is_set():
                break
                
            new_state = state.move_piece(move[0][0], move[0][1], move[1][0], move[1][1])
            
            # PVS + LMR
            is_capture_move = (state.board_c[move[1][0] * 5 + move[1][1]] != EMPTY)
            reduction = 0
            if i >= 5 and depth >= 3 and not is_capture_move:
                reduction = 1
            
            if i == 0:
                evaluation, _, line = _alpha_beta(new_state, depth - 1, alpha, beta, True, settings)
            else:
                evaluation, _, line = _alpha_beta(new_state, depth - 1 - reduction, beta - 1, beta, True, settings)
                if alpha < evaluation < beta:
                    evaluation, _, line = _alpha_beta(new_state, depth - 1, alpha, beta, True, settings)

            if evaluation < min_eval:
                min_eval = evaluation
                best_move = move
                best_line = [move] + line

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
    
    # 【Phase1优化】定长数组存储，优先保存搜索深度更深的结果
    if best_move:
        store_index = <int>(state.hash % TT_SIZE)
        existing_entry = transposition_table[store_index]
        if existing_entry is None or existing_entry[1] <= depth:
            transposition_table[store_index] = (eval_score, depth, flag, best_move, state.hash)
    
    return eval_score, best_move, best_line