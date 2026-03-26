# core/nnue_evaluator.pxd
from core.game_logic cimport GameState as CGameState

cdef float c_evaluate_nnue(CGameState state) noexcept nogil
