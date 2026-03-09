# cython: profile=True
import collections
from core.game_logic import GameState, CANNON, SOLDIER, EMPTY
from core.game_logic cimport GameState as CGameState  # C 级直接访问 board_c

# Cython imports
import cython
from cython cimport Py_ssize_t
from libc.stdlib cimport malloc, free

ctypedef Py_ssize_t int
ctypedef double float

# --- 缓存机制 ---
# 创建缓存来存储计算结果
cdef dict _material_score_cache = {}
cdef dict _soldier_scores_cache = {}
cdef dict _cannon_forbidden_zone_cache = {}
cdef dict _control_zone_bfs_cache = {}

# 【Phase4优化】导出缓存清理函数，防止无限增长和 hash 碰撞
def clear_evaluation_caches():
    """清空所有评估缓存。应在每次搜索开始前调用。"""
    global _material_score_cache, _soldier_scores_cache
    global _cannon_forbidden_zone_cache, _control_zone_bfs_cache
    _material_score_cache.clear()
    _soldier_scores_cache.clear()
    _cannon_forbidden_zone_cache.clear()
    _control_zone_bfs_cache.clear()

# --- 坐标映射与表定义 ---


# --- 默认权重配置 ---
DEFAULT_SETTINGS = {
    # 兵力数量分 (1-15兵)
    "BASE_MATERIAL_SCORES": [
        1600, 1400, 1200, 1000, 700,
         500,  300,  100,    0, -100,
        -150, -200, -250, -300, -350
    ],
    # 贴炮惩罚
    "WEIGHT_SOLDIER_PROXIMITY": -30,
    # 净控制区评分映射
    "WEIGHT_NET_MAP": { 
        0: -1000, 1: -500, 2: -100, 3: 0, 
        4: 80, 5: 200,  
    },
    "MAX_NET_CONTROL_SCORE": 200,
    # 兵位置分表 (5x5)
    "SOLDIER_POSITION_TABLE": [
        [0, 0, 0, 0, 0],
        [0, -10, -10, -10, 0],
        [-5, -50, -35, -50, -5],
        [-15, -70, -60, -70, -15],
        [0, -25, 0, -25, 0]
    ]
}

# 内部快捷访问（默认值）
cdef int _precomputed_soldier_position_scores[5][5]

# --- 纯 C 加速所需的数据表 ---
cdef unsigned int _neighbor_masks[25]
cdef int _net_map_c[30]
cdef int _base_material_scores_c[16]
cdef bint _is_initialized = False

def _init_precomputed_tables(table=None):
    if table is None:
        table = DEFAULT_SETTINGS["SOLDIER_POSITION_TABLE"]
    cdef int r, c, i, dr, dc, nr, nc
    for r in range(5):
        for c in range(5):
            _precomputed_soldier_position_scores[r][c] = table[r][c]
            
    global _is_initialized
    if _is_initialized:
        return
    _is_initialized = True
    
    # Init neighbor masks
    for i in range(25):
        _neighbor_masks[i] = 0
        r = i // 5
        c = i % 5
        for dr, dc in [(0, 1), (0, -1), (1, 0), (-1, 0)]:
            nr = r + dr
            nc = c + dc
            if 0 <= nr < 5 and 0 <= nc < 5:
                _neighbor_masks[i] |= (1 << (nr * 5 + nc))
                
    # Init material (1-15 兵)
    cdef list m_scores = [0, 1600, 1400, 1200, 1000, 700, 500, 300, 100, 0, -100, -150, -200, -250, -300, -350]
    for i in range(16):
        _base_material_scores_c[i] = m_scores[i]
        
    # Init net map
    for i in range(30):
        _net_map_c[i] = 200
    _net_map_c[0] = -1000
    _net_map_c[1] = -500
    _net_map_c[2] = -100
    _net_map_c[3] = 0
    _net_map_c[4] = 80
    _net_map_c[5] = 200

_init_precomputed_tables()

# ----------- 纯 C 版极速评估函数 (Zero Allocation) -----------
@cython.boundscheck(False)
@cython.wraparound(False)
cdef int c_evaluate_board(CGameState state) noexcept:
    if state.winner != -1:
        return 10000 if state.winner == CANNON else -10000
        
    cdef unsigned int soldiers_mask = 0
    cdef unsigned int cannons_mask = 0
    cdef unsigned int empty_mask = 0
    cdef int i, val, r, c, dr, dc
    cdef int position_score = 0
    cdef int proximity_score = 0
    
    # 1. 一次遍历生成所有掩码和基础分数
    for i in range(25):
        val = state.board_c[i]
        if val == SOLDIER:
            soldiers_mask |= (1 << i)
            position_score += _precomputed_soldier_position_scores[i // 5][i % 5]
            
            r = i // 5
            c = i % 5
            if r > 0 and state.board_c[i - 5] == CANNON:
                proximity_score -= 30
            elif r < 4 and state.board_c[i + 5] == CANNON:
                proximity_score -= 30
            elif c > 0 and state.board_c[i - 1] == CANNON:
                proximity_score -= 30
            elif c < 4 and state.board_c[i + 1] == CANNON:
                proximity_score -= 30
                
        elif val == CANNON:
            cannons_mask |= (1 << i)
        else:
            empty_mask |= (1 << i)
            
    # 2. 炮方禁区掩码 (攻击格子+预瞄格子)
    cdef unsigned int forbidden_mask = 0
    for i in range(25):
        if state.board_c[i] == CANNON:
            r = i // 5
            c = i % 5
            if r - 2 >= 0 and state.board_c[i - 5] == EMPTY:
                if state.board_c[i - 10] != CANNON:  # SOLDIER(攻击) or EMPTY(预瞄)
                    forbidden_mask |= (1 << (i - 10))
            if r + 2 < 5 and state.board_c[i + 5] == EMPTY:
                if state.board_c[i + 10] != CANNON:
                    forbidden_mask |= (1 << (i + 10))
            if c - 2 >= 0 and state.board_c[i - 1] == EMPTY:
                if state.board_c[i - 2] != CANNON:
                    forbidden_mask |= (1 << (i - 2))
            if c + 2 < 5 and state.board_c[i + 1] == EMPTY:
                if state.board_c[i + 2] != CANNON:
                    forbidden_mask |= (1 << (i + 2))
                    
    # 3. 控制区 BFS 计算（极致位移操作，不依赖堆分配内存队列）
    cdef unsigned int safe_soldiers_mask = soldiers_mask & (~forbidden_mask)
    cdef unsigned int visited_mask = safe_soldiers_mask
    cdef unsigned int queue_mask = safe_soldiers_mask
    cdef unsigned int new_queue_mask = 0
    cdef int j

    while queue_mask:
        new_queue_mask = 0
        for j in range(25):
            if queue_mask & (1 << j):
                new_queue_mask |= _neighbor_masks[j]
        
        new_queue_mask &= empty_mask           # 只向空格蔓延
        new_queue_mask &= (~forbidden_mask)    # 不能进入禁区
        new_queue_mask &= (~visited_mask)      # 不能是已访问过的
        
        visited_mask |= new_queue_mask
        queue_mask = new_queue_mask
        
    # 4. 统计比特位数（Kernighan 算法） -> 兵方安全区总格数
    cdef int bit_count = 0
    cdef unsigned int temp = visited_mask
    while temp:
        temp &= (temp - 1)
        bit_count += 1
        
    cdef int net_control_count = 22 - bit_count  # 25总格子 - 3炮 - 兵方安全
    cdef int net_control_score = 200
    if 0 <= net_control_count <= 5:
        net_control_score = _net_map_c[net_control_count]
        
    # 5. 返回综合总分
    cdef int material_score = 0
    cdef int sc = state.soldier_count
    if 1 <= sc <= 15:
        material_score = _base_material_scores_c[sc]
        
    return net_control_score + position_score + proximity_score + material_score


@cython.boundscheck(False)
@cython.wraparound(False)
def get_material_score(int soldier_count, dict settings=None) -> int:
    """获取兵力数量分数"""
    cdef list scores = settings["BASE_MATERIAL_SCORES"] if settings else DEFAULT_SETTINGS["BASE_MATERIAL_SCORES"]
    
    if soldier_count == 0:
        return 10000  # 炮方已胜利
    if 1 <= soldier_count <= 15:
        return scores[soldier_count - 1]
    return 0

@cython.boundscheck(False)
@cython.wraparound(False)
def _calculate_soldier_scores(CGameState state, set soldiers, set cannons, dict settings=None) -> tuple:
    """计算独立的兵方分数项 (位置分 和 贴炮分)"""
    cdef int proximity_weight = settings["WEIGHT_SOLDIER_PROXIMITY"] if settings else DEFAULT_SETTINGS["WEIGHT_SOLDIER_PROXIMITY"]
    cdef list pos_table = settings.get("SOLDIER_POSITION_TABLE") if settings else None
    
    cdef int position_score = 0
    cdef int r, c
    if pos_table:
        for r, c in soldiers:
            position_score += pos_table[r][c]
    else:
        for r, c in soldiers:
            position_score += _precomputed_soldier_position_scores[r][c]
    
    cdef int score_proximity = 0
    cdef int r_soldier, c_soldier, dr, dc
    for r_soldier, c_soldier in soldiers:
        # 【P8优化】手写循环替代 any() 生成器，Cython 可优化为 C 代码
        for dr, dc in [(0,1), (0,-1), (1,0), (-1,0)]:
            if (r_soldier + dr, c_soldier + dc) in cannons:
                score_proximity += proximity_weight
                break
            
    return (position_score, score_proximity)


@cython.boundscheck(False)
@cython.wraparound(False)
def _calculate_cannon_forbidden_zone(CGameState state, set cannons) -> set:
    """一次性计算所有被炮攻击或预瞄的格子 (炮方禁区) - 带缓存优化"""
    global _cannon_forbidden_zone_cache
    
    # 【P1优化】缓存键直接用 Zobrist hash，免去 frozenset + str(board) 的开销
    cdef unsigned long long cache_key = state.hash
    
    # 检查缓存
    if cache_key in _cannon_forbidden_zone_cache:
        return _cannon_forbidden_zone_cache[cache_key].copy()  # 返回副本避免外部修改
    
    # 计算新值
    cdef set attack_squares = set()
    cdef set pre_aim_squares = set()
    cdef list directions = [(0, 1), (0, -1), (1, 0), (-1, 0)]
    cdef int r_start, c_start, r_end, c_end, dr, dc
    cdef tuple pos1, pos2, end_pos
    
    for r_start, c_start in cannons:
        # 获取有效移动并处理攻击方格
        valid_moves = state.get_valid_moves(r_start, c_start)
        for r_end, c_end in valid_moves:
            if abs(r_start - r_end) == 2 or abs(c_start - c_end) == 2:
                attack_squares.add((r_end, c_end))
        
        # 处理预瞄方格
        for dr, dc in directions:
            pos1 = (r_start + dr, c_start + dc)
            pos2 = (r_start + 2*dr, c_start + 2*dc)
            if (0 <= pos1[0] < 5 and 0 <= pos1[1] < 5 and 
                0 <= pos2[0] < 5 and 0 <= pos2[1] < 5 and
                state.board_c[pos1[0] * 5 + pos1[1]] == EMPTY and 
                state.board_c[pos2[0] * 5 + pos2[1]] == EMPTY):
                pre_aim_squares.add(pos2)
    
    # 合并结果并缓存
    result = attack_squares.union(pre_aim_squares)
    _cannon_forbidden_zone_cache[cache_key] = result.copy()  # 缓存副本
    return result


# --- 【逻辑已修正】BFS现在从给定的安全起点开始 ---
@cython.boundscheck(False)
@cython.wraparound(False)
def _calculate_control_zone_bfs(CGameState state, set starting_points, set forbidden_zone) -> set:
    """使用BFS计算控制区域 - 带缓存优化"""
    global _control_zone_bfs_cache
    
    # 【P1优化】缓存键直接用 Zobrist hash
    cdef unsigned long long cache_key = state.hash
    
    # 检查缓存
    if cache_key in _control_zone_bfs_cache:
        return _control_zone_bfs_cache[cache_key].copy()  # 返回副本避免外部修改
    
    # 计算新值
    # 队列的初始值为所有安全的起始点 (水源)
    queue = collections.deque(starting_points)
    # visited集合记录所有已访问的、安全的格子，初始也只包含安全的起始点
    cdef set visited = starting_points.copy()
    
    cdef int r, c, dr, dc, nr, nc
    cdef tuple new_pos
    
    while queue:
        r, c = queue.popleft()
        
        # 探索当前格子的四个邻居
        for dr, dc in [(0, 1), (0, -1), (1, 0), (-1, 0)]:
            nr, nc = r + dr, c + dc
            new_pos = (nr, nc)
            
            # 检查邻居是否满足扩展条件
            if (0 <= nr < 5 and 0 <= nc < 5 and         # 1. 在棋盘内
                state.board_c[nr * 5 + nc] == EMPTY and           # 2. 是一个空格子
                new_pos not in forbidden_zone and         # 3. 不在禁区内
                new_pos not in visited):                  # 4. 之前没有访问过
                
                visited.add(new_pos)
                queue.append(new_pos)
    
    # 缓存结果
    _control_zone_bfs_cache[cache_key] = visited.copy()  # 缓存副本
    return visited


@cython.boundscheck(False)
@cython.wraparound(False)
def evaluate_board(CGameState state, dict settings=None):
    """供外界和向后兼容的评估函数封装层。核心计算已下沉至 C 级 c_evaluate_board"""
    cdef int score = c_evaluate_board(state)
    return score, {"total_score": score, "reason": "Fast C Eval Details Omitted"}