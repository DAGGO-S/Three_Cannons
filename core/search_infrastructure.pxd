# core/search_infrastructure.pxd
from core.game_logic cimport GameState

cdef struct TTEntry:
    unsigned long long hash_key
    int depth
    float score
    int flag
    int best_move_encoded

cdef TTEntry* transposition_table
cdef int TT_SIZE

cpdef enum TTFlag:
    EXACT_SCORE = 1
    LOWER_BOUND = 2
    UPPER_BOUND = 3

cdef unsigned long long _thread_nodes[64]
cdef int stop_search_flag

cdef void reset_nodes_evaluated_c() noexcept nogil
cdef unsigned long long get_nodes_evaluated_total() noexcept nogil
