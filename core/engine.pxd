# core/engine.pxd
from core.game_logic cimport GameState

cdef extern from "nnue_weights.h":
    const float NNUE_W1[51][256]

cdef int g_evaluator_mode
cdef float _acc_stack[64][64][256]

cdef void _init_acc_at_root(GameState state, int thread_id) noexcept nogil
cdef float _alpha_beta(GameState state, int depth, float alpha, float beta, bint maximizing_player, int thread_id, int ply, unsigned long long* history_stack, int history_len) noexcept nogil
