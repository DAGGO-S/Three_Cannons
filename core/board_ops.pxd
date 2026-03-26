# core/board_ops.pxd
# 纯 C 级棋盘操作：胜负判定、走法生成、对称变换
# 所有函数只操作 int* 数组和编译期常量，天然 nogil 安全

from core.constants cimport EMPTY as CONST_EMPTY, SOLDIER as CONST_SOLDIER, CANNON as CONST_CANNON, NO_WINNER as CONST_NO_WINNER

# --- 胜负判定 ---
cdef int c_check_winner(int* board_c, int soldier_count) noexcept nogil

# --- 走法生成 ---
cdef int c_gen_moves(int* board_c, int player_piece, int hash_move, int* out_moves) noexcept nogil

# --- 对称变换 ---
cdef unsigned long long c_canonical_hash(int* board_c, int current_player) noexcept

# --- 逆向推演 (Retrograde Analysis) ---
# 生成所有能到达当前棋盘的上一步局面（不涉及吃子）
cdef int c_gen_unmoves(int* board_c, int current_player, int* out_boards) noexcept nogil
# 生成所有通过“被吃子”还原回来的上一步局面（涉及兵数 +1）
cdef int c_gen_uncaptures(int* board_c, int current_player, int* out_boards) noexcept nogil
