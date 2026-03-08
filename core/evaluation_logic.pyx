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

def _init_precomputed_tables(table=None):
    if table is None:
        table = DEFAULT_SETTINGS["SOLDIER_POSITION_TABLE"]
    cdef int r, c
    for r in range(5):
        for c in range(5):
            _precomputed_soldier_position_scores[r][c] = table[r][c]

_init_precomputed_tables()

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
    """V10 最终版评估函数：基于安全的兵源进行BFS精确计算 - 带缓存优化"""
    cdef int score, position_score, proximity_score, soldier_total_score, material_score
    cdef int net_control_count, net_control_score, total_score
    
    if state.winner != -1:
        score = 10000 if state.winner == CANNON else -10000
        return score, {"total": score, "reason": "Terminal Node"}

    # 【Phase2优化】直接遍历 5×5 board 构建 set（比 frozenset→set 转换更快）
    cdef set soldiers = set()
    cdef set cannons = set()
    cdef int sr, sc
    for sr in range(5):
        for sc in range(5):
            if state.board_c[sr * 5 + sc] == SOLDIER:
                soldiers.add((sr, sc))
            elif state.board_c[sr * 5 + sc] == CANNON:
                cannons.add((sr, sc))
    
    # --- 1. 计算兵方各项分数 ---
    position_score, proximity_score = _calculate_soldier_scores(state, soldiers, cannons, settings)
    soldier_total_score = position_score + proximity_score
    
    # --- 2. 计算兵力数量分 ---
    material_score = get_material_score(state.soldier_count, settings)

    # --- 3. 【核心逻辑修正】基于安全的兵源计算净控制区 ---
    # a. 一次性计算出所有炮方威胁的格子
    cannon_forbidden_zone = _calculate_cannon_forbidden_zone(state, cannons)
    
    # b. 【新增】从所有兵中，筛选出位置安全的兵
    cdef set safe_soldiers = soldiers - cannon_forbidden_zone
    
    # c. 【已修改】使用安全的兵作为BFS的起点，找到所有能安全控制的区域
    pure_soldier_zone = _calculate_control_zone_bfs(state, safe_soldiers, cannon_forbidden_zone)
    
    # d. 计算炮方净控制的格子数
    # 总格子25 - 炮数3 - 兵方安全区大小 = 炮方净控制区大小
    net_control_count = 25 - 3 - len(pure_soldier_zone)
    
    # e. 查表得到最终净控制分
    cdef dict net_map = settings["WEIGHT_NET_MAP"] if settings else DEFAULT_SETTINGS["WEIGHT_NET_MAP"]
    cdef int max_net = settings["MAX_NET_CONTROL_SCORE"] if settings else DEFAULT_SETTINGS["MAX_NET_CONTROL_SCORE"]
    net_control_score = net_map.get(net_control_count, max_net)
    
    # --- 4. 最终融合公式 (炮方视角) ---
    total_score = net_control_score + soldier_total_score + material_score

    # --- 5. 返回结构清晰的评估详情 ---
    cdef dict score_details = {
        "total_score": total_score,
        "net_control_score": net_control_score,
        "soldier_scores": {
            "position": position_score,
            "proximity": proximity_score,
            "total": soldier_total_score
        },
        "material_score": material_score,
        "net_control_count": net_control_count
    }
    return total_score, score_details