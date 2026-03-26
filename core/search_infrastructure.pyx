# core/search_infrastructure.pyx
import os
import pickle
from libc.stdlib cimport malloc, free
from libc.string cimport memset
import cython

# --- 置换表和相关常量 ---
cdef int TT_SIZE = 4194304
cdef TTEntry* transposition_table = NULL

cdef unsigned long long _total_nodes_evaluated = 0
cdef unsigned long long _thread_nodes[64]
cdef int stop_search_flag = 0

cdef void reset_nodes_evaluated_c() noexcept nogil:
    global _total_nodes_evaluated
    _total_nodes_evaluated = 0
    cdef int i
    for i in range(64):
        _thread_nodes[i] = 0

cdef unsigned long long get_nodes_evaluated_total() noexcept nogil:
    cdef unsigned long long total = _total_nodes_evaluated
    cdef int i
    for i in range(64):
        total += _thread_nodes[i]
    return total

def get_nodes_evaluated():
    return get_nodes_evaluated_total()

def reset_nodes_evaluated():
    with nogil:
        reset_nodes_evaluated_c()

def clear_transposition_table():
    global transposition_table
    if transposition_table == NULL:
        transposition_table = <TTEntry*>malloc(TT_SIZE * sizeof(TTEntry))
    if transposition_table != NULL:
        memset(transposition_table, 0, TT_SIZE * sizeof(TTEntry))

# --- 残局表 (Tablebases) ---
cdef dict tablebase_cache = {}
cdef bint tb_loaded = False

def init_tablebases():
    pass

def get_tablebase_cache():
    return {}

def is_stop_search():
    return stop_search_flag != 0

def set_stop_search(int val):
    global stop_search_flag
    stop_search_flag = val
