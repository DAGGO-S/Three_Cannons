# core/game_logic.pxd
# Cython 声明文件：让其他 .pyx 模块通过 cimport 直接访问 GameState 的 C 级字段

cdef class GameState:
    cdef int board_c[25]           # 1D C 数组，行主序 index = r*5+c
    cdef public int current_player
    cdef public int winner          # -1 = None
    cdef public int soldier_count
    cdef public unsigned long long hash
    
    cdef void _check_winner(self)
    cdef int c_move_piece(self, int start_idx, int end_idx) noexcept
    cdef void c_unmake_piece(self, int start_idx, int end_idx, int captured_piece, unsigned long long old_hash, int old_winner) noexcept

cdef int c_get_ordered_moves(GameState state, int player_piece, int hash_move, int* out_moves) noexcept
