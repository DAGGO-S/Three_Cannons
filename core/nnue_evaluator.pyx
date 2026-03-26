# core/nnue_evaluator.pyx
# cython: boundscheck=False, wraparound=False, nonecheck=False, cdivision=True

from core.constants cimport CANNON, SOLDIER, EMPTY
from core.game_logic cimport GameState as CGameState

import cython

cdef extern from "nnue_weights.h":
    const float NNUE_W1[51][256]
    const float NNUE_B1[256]
    const float NNUE_W2_T[256][32]
    const float NNUE_B2[32]
    const float NNUE_W3[32]
    const float NNUE_B3

@cython.boundscheck(False)
@cython.wraparound(False)
cdef float c_evaluate_nnue(CGameState state) noexcept nogil:
    if state.winner != -1:
        return 10000.0 if state.winner == CANNON else -10000.0

    cdef int i, j
    cdef float hidden1[256]
    cdef float hidden2[32]
    
    for i in range(256):
        hidden1[i] = NNUE_B1[i]
        
    for i in range(25):
        if state.board_c[i] == SOLDIER:
            for j in range(256):
                hidden1[j] += NNUE_W1[i][j]
        elif state.board_c[i] == CANNON:
            for j in range(256):
                hidden1[j] += NNUE_W1[i + 25][j]

    if state.current_player == CANNON:
        for j in range(256):
            hidden1[j] += NNUE_W1[50][j]

    cdef float out = NNUE_B3
    for i in range(32):
        hidden2[i] = NNUE_B2[i]
        for j in range(256):
            if hidden1[j] > 0.0:
                hidden2[i] += hidden1[j] * NNUE_W2_T[j][i]
        if hidden2[i] > 0.0:
            out += hidden2[i] * NNUE_W3[i]
        
    return out

def evaluate_nnue_python(state):
    return float(c_evaluate_nnue(state))
