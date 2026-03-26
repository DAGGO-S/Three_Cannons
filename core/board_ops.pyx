# core/board_ops.pyx
# 纯 C 级棋盘操作模块：可独立编译、独立测试
# 所有 cdef 函数仅操作 C 数组和编译期常量。

cimport core.zobrist_hashing as zh
from core.constants cimport EMPTY as CONST_EMPTY, SOLDIER as CONST_SOLDIER, CANNON as CONST_CANNON, NO_WINNER as CONST_NO_WINNER
from libc.string cimport memcpy
import cython

# ===================================================================
# 对称变换表 (5x5 D4 群，共 7 组非恒等变换)
# ===================================================================
cdef int SYMMETRY_TRANSFORMS[7][25]

def _init_symmetry_transforms():
    cdef int r, c, i
    for r in range(5):
        for c in range(5):
            i = r * 5 + c
            SYMMETRY_TRANSFORMS[0][r*5 + (4-c)] = i           # 水平翻转
            SYMMETRY_TRANSFORMS[1][(4-r)*5 + c] = i           # 垂直翻转
            SYMMETRY_TRANSFORMS[2][(4-r)*5 + (4-c)] = i       # 180° 旋转
            SYMMETRY_TRANSFORMS[3][c*5 + r] = i               # 转置
            SYMMETRY_TRANSFORMS[4][(4-c)*5 + (4-r)] = i       # 反对角翻转
            SYMMETRY_TRANSFORMS[5][c*5 + (4-r)] = i           # 90° 旋转
            SYMMETRY_TRANSFORMS[6][(4-c)*5 + r] = i           # 270° 旋转

_init_symmetry_transforms()

# ===================================================================
# 胜负判定（纯 C，nogil 安全）
# ===================================================================
@cython.boundscheck(False)
@cython.wraparound(False)
cdef int c_check_winner(int* board_c, int soldier_count) noexcept nogil:
    """
    判断当前局面的胜负状态。
    返回值: CONST_CANNON(兵全灭), CONST_SOLDIER(炮被困), CONST_NO_WINNER(未结束)
    """
    if soldier_count == 0:
        return CONST_CANNON  # 兵方全灭 -> 炮胜

    # 检查炮是否被困：只要有一门炮有相邻空格就未被困
    cdef int r, c, tr, tc, i
    cdef int[4] drs
    cdef int[4] dcs
    drs[0] = -1; drs[1] = 1; drs[2] = 0; drs[3] = 0
    dcs[0] = 0; dcs[1] = 0; dcs[2] = -1; dcs[3] = 1

    for r in range(5):
        for c in range(5):
            if board_c[r * 5 + c] == CONST_CANNON:
                for i in range(4):
                    tr = r + drs[i]
                    tc = c + dcs[i]
                    if 0 <= tr < 5 and 0 <= tc < 5 and board_c[tr * 5 + tc] == CONST_EMPTY:
                        return CONST_NO_WINNER   # 至少一门炮可动 -> 未结束

    return CONST_SOLDIER  # 所有炮被困 -> 兵胜


# ===================================================================
# 走法生成与排序（纯 C，nogil 安全）
# ===================================================================
@cython.boundscheck(False)
@cython.wraparound(False)
cdef int c_gen_moves(int* board_c, int player_piece, int hash_move, int* out_moves) noexcept nogil:
    """
    生成所有合法走法并按优先级排序：hash_move > 吃子 > 安静走子。
    走法编码: move = (start_idx << 8) | end_idx
    返回走法总数。
    """
    cdef int num_moves = 0
    cdef int captures[64]
    cdef int num_captures = 0
    cdef int quiets[64]
    cdef int num_quiets = 0
    cdef int i, r, c, start_idx, end_idx, dr, dc, nr, nc, jump_idx, i_dir
    cdef int move_encoded
    cdef int[4] drs_c
    cdef int[4] dcs_c
    drs_c[0] = 0; drs_c[1] = 0; drs_c[2] = 1; drs_c[3] = -1
    dcs_c[0] = 1; dcs_c[1] = -1; dcs_c[2] = 0; dcs_c[3] = 0

    # 1. hash_move 优先
    if hash_move != -1:
        out_moves[num_moves] = hash_move
        num_moves += 1

    for start_idx in range(25):
        if board_c[start_idx] == player_piece:
            r = start_idx // 5
            c = start_idx % 5

            if player_piece == CONST_SOLDIER:
                for i_dir in range(4):
                    dr = drs_c[i_dir]
                    dc = dcs_c[i_dir]
                    nr = r + dr
                    nc = c + dc
                    if 0 <= nr < 5 and 0 <= nc < 5:
                        end_idx = nr * 5 + nc
                        if board_c[end_idx] == CONST_EMPTY:
                            move_encoded = (start_idx << 8) | end_idx
                            if move_encoded == hash_move:
                                continue
                            quiets[num_quiets] = move_encoded
                            num_quiets += 1
            else:  # CONST_CANNON
                for i_dir in range(4):
                    dr = drs_c[i_dir]
                    dc = dcs_c[i_dir]
                    nr = r + dr
                    nc = c + dc
                    if 0 <= nr < 5 and 0 <= nc < 5:
                        end_idx = nr * 5 + nc
                        if board_c[end_idx] == CONST_EMPTY:
                            move_encoded = (start_idx << 8) | end_idx
                            if move_encoded == hash_move:
                                continue
                            quiets[num_quiets] = move_encoded
                            num_quiets += 1

                    # 隔空吃子
                    nr = r + 2*dr
                    nc = c + 2*dc
                    if 0 <= nr < 5 and 0 <= nc < 5:
                        jump_idx = (r + dr) * 5 + (c + dc)
                        if board_c[jump_idx] == CONST_EMPTY:
                            end_idx = nr * 5 + nc
                            if board_c[end_idx] == CONST_SOLDIER:
                                move_encoded = (start_idx << 8) | end_idx
                                if move_encoded == hash_move:
                                    continue
                                captures[num_captures] = move_encoded
                                num_captures += 1

    # 追加 captures -> quiets
    for i in range(num_captures):
        out_moves[num_moves] = captures[i]
        num_moves += 1
    for i in range(num_quiets):
        out_moves[num_moves] = quiets[i]
        num_moves += 1

    return num_moves

# ===================================================================
# Python 包装层：供 generate_tablebase_expand.py 调用
# ===================================================================

@cython.boundscheck(False)
@cython.wraparound(False)
def get_unmoves_py(board, int player):
    """Python 封装：生成所有非吃子的前驱局面。"""
    cdef int[25] board_c
    cdef int i, r, c
    for r in range(5):
        for c in range(5):
            board_c[r*5+c] = board[r][c]
            
    cdef int out_boards[100 * 25]
    cdef int num = c_gen_unmoves(board_c, player, out_boards)
    
    results = []
    for i in range(num):
        results.append(tuple(tuple(out_boards[i*25 + r*5 + c] for c in range(5)) for r in range(5)))
    return results

@cython.boundscheck(False)
@cython.wraparound(False)
def get_uncaptures_py(board, int player):
    """Python 封装：生成所有反向吃子的前驱局面(兵数+1)。"""
    cdef int[25] board_c
    cdef int r, c, i
    for r in range(5):
        for c in range(5):
            board_c[r*5+c] = board[r][c]
            
    cdef int out_boards[100 * 25]
    cdef int num = c_gen_uncaptures(board_c, player, out_boards)
    
    results = []
    for i in range(num):
        results.append(tuple(tuple(out_boards[i*25 + r*5 + c] for c in range(5)) for r in range(5)))
    return results

# ===================================================================
# 规范化哈希（需要 GIL，因为调用 ZobristHasher）
# ===================================================================

@cython.boundscheck(False)
@cython.wraparound(False)
cdef unsigned long long c_canonical_hash(int* board_c, int current_player) noexcept:
    """
    计算 D4 对称群下的规范化哈希（8 个变换中的最小值）。
    """
    cdef unsigned long long min_h = zh._hasher.c_compute_hash(board_c, current_player)
    cdef int[25] sym_board
    cdef int i, k
    cdef unsigned long long cur_h

    for k in range(7):
        for i in range(25):
            sym_board[i] = board_c[SYMMETRY_TRANSFORMS[k][i]]
        cur_h = zh._hasher.c_compute_hash(sym_board, current_player)
        if cur_h < min_h:
            min_h = cur_h

    return min_h

# ===================================================================
# 逆向推演支持 (Retrograde Analysis)
# ===================================================================

@cython.boundscheck(False)
@cython.wraparound(False)
cdef int c_gen_unmoves(int* board_c, int current_player, int* out_boards) noexcept nogil:
    """
    生成所有能通过一次“非吃子移动”到达当前局面的前驱棋盘。
    current_player: 当前棋盘的待行方（意味着上一步是 other 走的）
    out_boards: 预分配的缓冲区 (例如 int[100][25])
    返回生成的前驱棋盘数量。
    """
    cdef int num = 0
    cdef int other = 3 - current_player
    cdef int r, c, start_idx, end_idx, dr, dc, nr, nc, j, i_dir
    cdef int[4] drs = [0, 0, 1, -1], dcs = [1, -1, 0, 0]
    
    # 遍历棋盘上属于 other 的棋子，看它可能是从哪里“退回来”的
    for end_idx in range(25):
        if board_c[end_idx] == other:
            r = end_idx // 5
            c = end_idx % 5
            for i_dir in range(4):
                dr = drs[i_dir]
                dc = dcs[i_dir]
                nr = r + dr
                nc = c + dc
                if 0 <= nr < 5 and 0 <= nc < 5:
                    start_idx = nr * 5 + nc
                    # 如果 nr, nc 是空的，说明 other 可能是从那里走过来的
                    if board_c[start_idx] == CONST_EMPTY:
                        # 验证合法性：在 start_idx 时 other 是否能走到 end_idx？
                        # 对于兵和炮，普通走子都是移动 1 格到空格
                        memcpy(&out_boards[num * 25], board_c, 25 * sizeof(int))
                        out_boards[num * 25 + start_idx] = other
                        out_boards[num * 25 + end_idx] = CONST_EMPTY
                        num += 1
    return num

@cython.boundscheck(False)
@cython.wraparound(False)
cdef int c_gen_uncaptures(int* board_c, int current_player, int* out_boards) noexcept nogil:
    """
    生成所有能通过一次“吃子移动”到达当前局面的前驱棋盘（兵数 +1）。
    只有炮能吃子。如果当前是兵方走，说明上一步是炮方吃子。
    返回生成的前驱棋盘数量。
    """
    if current_player != CONST_SOLDIER: # 只有上一步是炮走才可能由于吃子导致兵数减少
        return 0
        
    cdef int num = 0
    cdef int r, c, start_idx, end_idx, jump_idx, dr, dc, nr, nc, i_dir
    cdef int[4] drs = [0, 0, 1, -1], dcs = [1, -1, 0, 0]
    
    # 查找棋盘上的每一门炮
    for end_idx in range(25):
        if board_c[end_idx] == CONST_CANNON:
            r = end_idx // 5
            c = end_idx % 5
            for i_dir in range(4):
                dr = drs[i_dir]
                dc = dcs[i_dir]
                # 炮是从 start 跳过空位 jump 吃掉 end 的兵
                # 逆推：炮在 start，end 原本有个兵，jump 是空的
                start_idx = (r + 2*dr) * 5 + (c + 2*dc)
                if 0 <= (r + 2*dr) < 5 and 0 <= (c + 2*dc) < 5:
                    jump_idx = (r + dr) * 5 + (c + dc)
                    if board_c[start_idx] == CONST_EMPTY and board_c[jump_idx] == CONST_EMPTY:
                        # 还原
                        memcpy(&out_boards[num * 25], board_c, 25 * sizeof(int))
                        out_boards[num * 25 + start_idx] = CONST_CANNON
                        out_boards[num * 25 + end_idx] = CONST_SOLDIER
                        num += 1
    return num



