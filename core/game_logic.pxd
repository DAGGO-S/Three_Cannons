from core.constants cimport EMPTY as CONST_EMPTY, SOLDIER as CONST_SOLDIER, CANNON as CONST_CANNON, DRAW as CONST_DRAW, NO_WINNER as CONST_NO_WINNER, BOARD_ROWS as CONST_BOARD_ROWS, BOARD_COLS as CONST_BOARD_COLS

cdef class GameState:
    cdef int board_c[25]           # 1D C 数组，行主序 index = r*5+c
    cdef public int current_player
    cdef public int winner          # -1 = None
    cdef public int soldier_count
    cdef public int cannon_count
    cdef public unsigned long long hash
    cdef unsigned long long _cached_canonical_hash
    cdef bint _has_canonical_hash
    
    cpdef unsigned long long get_canonical_hash(self)
    cdef void _check_winner(self) noexcept nogil
    cdef int c_move_piece(self, int start_idx, int end_idx) noexcept nogil
    cdef void c_unmake_piece(self, int start_idx, int end_idx, int captured_piece, unsigned long long old_hash, int old_winner) noexcept nogil

cdef int c_get_ordered_moves(GameState state, int player_piece, int hash_move, int* out_moves) noexcept nogil

