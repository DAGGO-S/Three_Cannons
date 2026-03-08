# core/zobrist_hashing.pxd
cdef class ZobristHasher:
    cdef object table
    cdef unsigned long long table_c[25][2]
    cdef public unsigned long long turn_key
    cdef int rows, cols

    cdef unsigned long long c_compute_hash(self, int[25] board_c, int current_player)
    cdef unsigned long long c_update_hash(self, unsigned long long old_hash, int start_r, int start_c, int end_r, int end_c, int piece_type, int current_player)
    cdef unsigned long long c_remove_piece_hash(self, unsigned long long old_hash, int r, int c, int piece_type)
    cdef unsigned long long c_switch_turn_hash(self, unsigned long long old_hash)
