"""
texel_tuner.py - Texel 自动化调优训练脚本

基于海量自我对弈数据，通过坐标下降法自动优化引擎的静态评估权重。
核心思路：最小化 "Sigmoid(引擎分数) 预测的胜率" 与 "实际对弈胜率" 之间的均方误差。

用法：
    # 完整训练（默认读取 data/selfplay/run1.jsonl）
    python scripts/texel_tuner.py

    # 指定数据文件和参数
    python scripts/texel_tuner.py --data data/selfplay/run1.jsonl --epochs 50

    # 快速验证（仅取前 1000 条）
    python scripts/texel_tuner.py --max-samples 1000 --epochs 3

    # 强制使用 CPU（即使有 GPU）
    python scripts/texel_tuner.py --cpu
"""

import sys
import os
import json
import time
import argparse
import math

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

# ─── NumPy / CuPy 自动切换 ────────────────────────────────────────────────────
np = None  # 延迟初始化，由 setup_backend() 确定

def setup_backend(force_cpu=False):
    """自动选择 NumPy 或 CuPy 后端"""
    global np
    # 增加环境变量检查
    if os.environ.get("TUNER_FORCE_CPU") == "1":
        force_cpu = True
        
    if not force_cpu:
        try:
            import cupy
            np = cupy
            print("[后端] CuPy (GPU 加速)")
            return
        except ImportError as e:
            print(f"[后端] 未找到 CuPy 或加载失败 (将使用 CPU): {e}")
            print("提示: 若有 NVIDIA 显卡, 请根据 CUDA 版本安装: pip install cupy-cudaXXx")
    import numpy
    np = numpy
    print("[后端] NumPy (CPU)")


# ═══════════════════════════════════════════════════════════════════════════════
#  第一部分：参数向量定义
# ═══════════════════════════════════════════════════════════════════════════════

# 参数索引映射（共 37 维）
# [0..14]  BASE_MATERIAL_SCORES  (15个：兵数1~15依次对应)
# [15]     WEIGHT_SOLDIER_PROXIMITY
# [16..21] WEIGHT_NET_MAP[0..5]
# [22..36] SOLDIER_POSITION_TABLE (5行 × 3独立列，左右对称)
#          每行存 col0, col1, col2；col3=col1, col4=col0

PARAM_DIM = 37

# 位置表对称映射：15个独立参数 → 25格
# 每行3个独立值 (左, 中左, 中), 右侧镜像
_POS_SYMMETRIC_COLS = [0, 1, 2, 1, 0]  # col_idx → 独立参数索引

PARAM_NAMES = (
    [f"material_{i+1}兵" for i in range(15)]
    + ["proximity_贴炮惩罚"]
    + [f"net_map_{i}" for i in range(6)]
    + [f"pos_table[{r}][col{c}]" for r in range(5) for c in range(3)]
)

def get_default_params():
    """从 DEFAULT_SETTINGS 构建初始参数向量"""
    params = [0.0] * PARAM_DIM

    # BASE_MATERIAL_SCORES (index 0-14)
    material = [1600, 1400, 1200, 1000, 700, 500, 300, 100, 0, -100, -150, -200, -250, -300, -350]
    for i in range(15):
        params[i] = float(material[i])

    # WEIGHT_SOLDIER_PROXIMITY (index 15)
    params[15] = -30.0

    # WEIGHT_NET_MAP (index 16-21)
    net_map = [-1000, -500, -100, 0, 80, 200]
    for i in range(6):
        params[16 + i] = float(net_map[i])

    # SOLDIER_POSITION_TABLE (index 22-36, 15个独立值)
    # 每行3个: col0, col1, col2 (col3=col1, col4=col0)
    pos_independent = [
          0,   0,   0,   # row 0
          0, -10, -10,   # row 1
         -5, -50, -35,   # row 2
        -15, -70, -60,   # row 3
          0, -25,   0,   # row 4
    ]
    for i in range(15):
        params[22 + i] = float(pos_independent[i])

    return params


def load_params_from_json(filepath):
    """从 JSON 权重文件（如 tuned_weights.json）恢复参数列表"""
    if not os.path.exists(filepath):
        print(f"[警告] 权重文件不存在: {filepath}")
        return None

    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            data = json.load(f)

        params = [0.0] * PARAM_DIM

        # 映射逻辑与 export_results 相反
        # 0-14: BASE_MATERIAL_SCORES
        mat = data["BASE_MATERIAL_SCORES"]
        for i in range(15): params[i] = float(mat[i])

        # 15: WEIGHT_SOLDIER_PROXIMITY
        params[15] = float(data["WEIGHT_SOLDIER_PROXIMITY"])

        # 16-21: WEIGHT_NET_MAP
        nm = data["WEIGHT_NET_MAP"]
        for i in range(6): params[16+i] = float(nm[str(i)])

        # 22-36: SOLDIER_POSITION_TABLE (对称参数，存储 col0, col1, col2)
        pos = data["SOLDIER_POSITION_TABLE"]
        for r in range(5):
            for c in range(3):
                params[22 + r * 3 + c] = float(pos[r][c])

        return params
    except Exception as e:
        print(f"[错误] 解析权重文件失败: {e}")
        return None


# ═══════════════════════════════════════════════════════════════════════════════
#  第二部分：FEN 解析与数据加载
# ═══════════════════════════════════════════════════════════════════════════════

EMPTY = 0
SOLDIER = 1
CANNON = 2


def parse_fen_to_board(fen_str):
    """
    将 FEN 字符串解析为 int[25] 数组（行主序）。
    返回 (board_array, current_player)。
    """
    parts = fen_str.split(' ')
    board_str = parts[0]
    player_str = parts[1] if len(parts) > 1 else 'c'

    board = [0] * 25
    idx = 0
    for ch in board_str:
        if ch == '/':
            continue
        elif ch == 'c' or ch == 'C':
            board[idx] = CANNON
            idx += 1
        elif ch == 's' or ch == 'S':
            board[idx] = SOLDIER
            idx += 1
        elif ch.isdigit():
            idx += int(ch)  # 空格跳过

    current_player = CANNON if player_str.lower() == 'c' else SOLDIER
    return board, current_player


def load_dataset(filepath, max_samples=None):
    """
    读取 JSONL 数据文件，返回：
      boards:   int8 numpy array, shape (N, 25)
      outcomes: float32 numpy array, shape (N,)

    会过滤掉终局局面（eval == ±10000）
    """
    import numpy as _np  # 数据加载始终用 CPU numpy

    print(f"[数据] 加载 {filepath} ...")
    t0 = time.time()

    boards_list = []
    outcomes_list = []
    soldier_counts_list = []
    skipped = 0
    total = 0

    with open(filepath, 'r', encoding='utf-8') as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            total += 1

            record = json.loads(line)
            eval_score = record.get("eval", 0.0)

            # 过滤终局局面（已定胜负，分数为 ±10000）
            if abs(eval_score) >= 9999:
                skipped += 1
                continue

            fen = record["fen"]
            outcome = record["game_outcome"]

            board, _ = parse_fen_to_board(fen)
            boards_list.append(board)
            outcomes_list.append(outcome)
            # 尝试记录兵力（Run2 以上版本支持）
            try:
                sc = record.get("soldier_count", 15) # 默认 15
            except:
                sc = 15
            soldier_counts_list.append(sc)

            if max_samples and len(boards_list) >= max_samples:
                break

    boards = _np.array(boards_list, dtype=_np.int8)
    outcomes = _np.array(outcomes_list, dtype=_np.float32)
    soldier_counts = _np.array(soldier_counts_list, dtype=_np.int8)

    elapsed = time.time() - t0
    print(f"[数据] 加载完成: {len(boards)} 条有效局面 "
          f"(跳过 {skipped} 条终局, 共扫描 {total} 条), 耗时 {elapsed:.1f}s")

    # 统计胜负分布
    cannon_wins = int((outcomes > 0.9).sum())
    soldier_wins = int((outcomes < 0.1).sum())
    draws = len(outcomes) - cannon_wins - soldier_wins
    print(f"[数据] 分布: 炮胜={cannon_wins} 兵胜={soldier_wins} 和棋={draws}")

    return boards, outcomes, soldier_counts


# ═══════════════════════════════════════════════════════════════════════════════
#  第三部分：纯 Python/NumPy 评估函数（镜像 c_evaluate_board）
# ═══════════════════════════════════════════════════════════════════════════════

# 预计算邻居掩码表（与 Cython 版一致）
_NEIGHBOR_MASKS = [0] * 25
for _i in range(25):
    _r, _c = _i // 5, _i % 5
    for _dr, _dc in [(0, 1), (0, -1), (1, 0), (-1, 0)]:
        _nr, _nc = _r + _dr, _c + _dc
        if 0 <= _nr < 5 and 0 <= _nc < 5:
            _NEIGHBOR_MASKS[_i] |= (1 << (_nr * 5 + _nc))


def precompute_net_control(boards):
    """
    预计算所有样本的 net_control_count（BFS 控制区统计）。

    关键优化：net_control_count 仅依赖棋盘布局，与可调参数无关。
    因此只需在数据加载后计算一次，后续 batch_evaluate 直接查表。

    参数:
      boards: numpy array, shape (N, 25), dtype int8

    返回:
      net_control_counts: numpy int8 array, shape (N,)
        值域：0-22，其中 0-5 映射到 net_map，>5 映射到 max_net_score
    """
    import numpy as _np
    N = boards.shape[0]
    counts = _np.zeros(N, dtype=_np.int8)

    print(f"[预计算] 正在计算 {N} 个局面的控制区 (BFS)...")
    t0 = time.time()

    # 确保在 CPU 上操作
    try:
        boards_cpu = _np.asarray(boards)
    except Exception:
        boards_cpu = boards

    report_interval = max(1, N // 10)

    for sample_idx in range(N):
        board = boards_cpu[sample_idx]

        soldiers_bits = 0
        empty_bits = 0

        for i in range(25):
            val = int(board[i])
            if val == SOLDIER:
                soldiers_bits |= (1 << i)
            elif val == EMPTY:
                empty_bits |= (1 << i)

        # 炮方禁区掩码
        forbidden = 0
        for i in range(25):
            if int(board[i]) == CANNON:
                r = i // 5
                c = i % 5
                if r - 2 >= 0 and int(board[i - 5]) == EMPTY:
                    if int(board[i - 10]) != CANNON:
                        forbidden |= (1 << (i - 10))
                if r + 2 < 5 and int(board[i + 5]) == EMPTY:
                    if int(board[i + 10]) != CANNON:
                        forbidden |= (1 << (i + 10))
                if c - 2 >= 0 and int(board[i - 1]) == EMPTY:
                    if int(board[i - 2]) != CANNON:
                        forbidden |= (1 << (i - 2))
                if c + 2 < 5 and int(board[i + 1]) == EMPTY:
                    if int(board[i + 2]) != CANNON:
                        forbidden |= (1 << (i + 2))

        # BFS
        safe_soldiers = soldiers_bits & (~forbidden)
        visited = safe_soldiers
        queue = safe_soldiers

        while queue:
            new_queue = 0
            temp = queue
            while temp:
                j = (temp & (-temp)).bit_length() - 1
                new_queue |= _NEIGHBOR_MASKS[j]
                temp &= (temp - 1)

            new_queue &= empty_bits
            new_queue &= (~forbidden)
            new_queue &= (~visited)
            visited |= new_queue
            queue = new_queue

        bit_count = bin(visited).count('1')
        counts[sample_idx] = 22 - bit_count

        if (sample_idx + 1) % report_interval == 0:
            pct = (sample_idx + 1) * 100 // N
            print(f"  [预计算] {pct}% ({sample_idx + 1}/{N})", end='\r')

    elapsed = time.time() - t0
    print(f"[预计算] 完成! {N} 个局面, 耗时 {elapsed:.1f}s                    ")
    return counts


def batch_evaluate(boards, params, net_control_counts):
    """
    批量评估函数：对 N 个棋盘同时计算静态评估分。

    参数:
      boards:             numpy array, shape (N, 25), dtype int8
      params:             list[float], 长度 37 的参数向量
      net_control_counts: numpy int8 array, shape (N,), 预计算的控制区计数

    返回:
      scores: numpy array, shape (N,), dtype float64
    """
    global np
    if np is None:
        setup_backend()
    
    N = boards.shape[0]

    # 解包参数 (与 37 维参数向量定义严格对应)
    # [0..14] 子力, [15] 贴炮, [16..21] 控制区 net_map (0,1,2,3,4,5), [21] 其实也是 net_map[5]
    # 重新核对：[16,17,18,19,20,21] 确实是 6 个。那么 max_net_score 应该在 21 之后？
    # 不，根据定义 22 开始是位置表。所以 max_net_score 是硬编码或在 params 之外？
    # 查找定义：[16..21] WEIGHT_NET_MAP[0..5]，[21] 被标记为 max_net_score 是之前的 Bug。
    # 修正：max_net_score 应该是 200 (硬编码或从 weights 获取)，params 中不包含它。
    material_scores = [0.0] + [params[i] for i in range(15)]
    proximity_penalty = params[15]
    net_map = [params[16 + i] for i in range(6)]
    max_net_score = 200 # 或者是 weights.get("MAX_NET_CONTROL_SCORE", 200)，但在 batch_evaluate 中我们只拿 params

    # 从 15 个独立参数 (22-36) 展开为 25 格位置表
    pos_table = []
    for r in range(5):
        base = 22 + r * 3
        v0, v1, v2 = params[base], params[base + 1], params[base + 2]
        pos_table.extend([v0, v1, v2, v1, v0])

    # 转为 numpy 数组以便向量化
    boards_np = np.asarray(boards, dtype=np.int32)

    # ── 1. 兵数量（子力分）──
    soldier_mask = (boards_np == SOLDIER)
    soldier_counts = np.sum(soldier_mask, axis=1)

    mat_lookup = np.array(material_scores + [0.0] * 10, dtype=np.float64)
    soldier_counts_clipped = np.clip(soldier_counts, 0, 15)
    material_component = mat_lookup[soldier_counts_clipped]

    # ── 2. 兵位置分 ──
    pos_weights = np.array(pos_table, dtype=np.float64)
    position_component = np.sum(soldier_mask * pos_weights[np.newaxis, :], axis=1)

    # ── 3. 贴炮惩罚 ──
    proximity_component = np.zeros(N, dtype=np.float64)
    for cell_idx in range(25):
        is_soldier = boards_np[:, cell_idx] == SOLDIER
        r, c = cell_idx // 5, cell_idx % 5

        has_adjacent_cannon = np.zeros(N, dtype=np.bool_)
        if r > 0:
            has_adjacent_cannon |= (boards_np[:, cell_idx - 5] == CANNON)
        if r < 4:
            has_adjacent_cannon |= (boards_np[:, cell_idx + 5] == CANNON)
        if c > 0:
            has_adjacent_cannon |= (boards_np[:, cell_idx - 1] == CANNON)
        if c < 4:
            has_adjacent_cannon |= (boards_np[:, cell_idx + 1] == CANNON)

        proximity_component += is_soldier * has_adjacent_cannon * proximity_penalty

    # ── 4. 控制区分（从预计算的 count 查表）──
    # net_control_counts (0~22). 0~5 用 net_map, >5 用 max_net_score
    ncc = np.asarray(net_control_counts, dtype=np.int32)
    net_map_arr = np.array(net_map, dtype=np.float64)
    
    # 逻辑：只有 0-5 计数有特殊得分，>5 的统一封顶为 max_net_score
    net_control_component = np.full((N,), float(max_net_score), dtype=np.float64)
    # 彻底稳健的逻辑：逐个处理 0-5 的匹配项
    for i in range(len(net_map)):
        # 向量化填充符合条件的索引
        net_control_component[ncc == i] = float(net_map[i])

    # ── 5. 综合 ──
    total_scores = material_component + position_component + proximity_component + net_control_component

    # 调试模式支持：如果需要查看分量
    if os.environ.get("TUNER_DEBUG_COMPONENTS") == "1":
        return total_scores, {
            "material": material_component,
            "position": position_component,
            "proximity": proximity_component,
            "net_control": net_control_component
        }

    return total_scores


def evaluate_board_python(state, weights):
    """
    单局面 Python 评估函数，用于 verify_alignment.py 进行对齐验证。
    逻辑必须与 evaluation_logic.pyx 中的 c_evaluate_board 严格一致。
    """
    if state.winner != -1:
        return 10000 if state.winner == CANNON else -10000

    # 展平棋盘 (state.board 是二维元组)
    board = [cell for row in state.board for cell in row]
    material_scores = weights["BASE_MATERIAL_SCORES"]
    proximity_penalty = weights["WEIGHT_SOLDIER_PROXIMITY"]
    net_map = weights["WEIGHT_NET_MAP"]
    max_net_score = weights.get("MAX_NET_CONTROL_SCORE", 200)
    pos_table = weights["SOLDIER_POSITION_TABLE"]

    position_score = 0
    proximity_score = 0
    soldiers_bits = 0
    empty_bits = 0

    # 1. 遍历计算基础分和位掩码
    for i in range(25):
        val = board[i]
        if val == SOLDIER:
            soldiers_bits |= (1 << i)
            position_score += pos_table[i // 5][i % 5]
            
            r, c = i // 5, i % 5
            has_adj = False
            if r > 0 and board[i - 5] == CANNON: has_adj = True
            elif r < 4 and board[i + 5] == CANNON: has_adj = True
            elif c > 0 and board[i - 1] == CANNON: has_adj = True
            elif c < 4 and board[i + 1] == CANNON: has_adj = True
            
            if has_adj:
                proximity_score += proximity_penalty
        elif val == EMPTY:
            empty_bits |= (1 << i)

    # 2. 炮方禁区
    forbidden = 0
    for i in range(25):
        if board[i] == CANNON:
            r, c = i // 5, i % 5
            if r - 2 >= 0 and board[i - 5] == EMPTY:
                if board[i - 10] != CANNON: forbidden |= (1 << (i - 10))
            if r + 2 < 5 and board[i + 5] == EMPTY:
                if board[i + 10] != CANNON: forbidden |= (1 << (i + 10))
            if c - 2 >= 0 and board[i - 1] == EMPTY:
                if board[i - 2] != CANNON: forbidden |= (1 << (i - 2))
            if c + 2 < 5 and board[i + 1] == EMPTY:
                if board[i + 2] != CANNON: forbidden |= (1 << (i + 2))

    # 3. BFS 控制区 (镜像 C 版 c_evaluate_board)
    safe_soldiers = soldiers_bits & (~forbidden)
    visited = safe_soldiers
    queue = safe_soldiers
    while queue:
        new_queue = 0
        temp = queue
        while temp:
            j = (temp & (-temp)).bit_length() - 1
            new_queue |= _NEIGHBOR_MASKS[j]
            temp &= (temp - 1)
        new_queue &= empty_bits
        new_queue &= (~forbidden)
        new_queue &= (~visited)
        visited |= new_queue
        queue = new_queue

    bit_count = bin(visited).count('1')
    net_control_count = 22 - bit_count
    
    net_control_score = max_net_score
    if 0 <= net_control_count <= 5:
        net_control_score = net_map.get(str(net_control_count), net_map.get(net_control_count, max_net_score))

    # 4. 子力分
    material_score = 0
    sc = state.soldier_count
    if 1 <= sc <= 15:
        material_score = material_scores[sc - 1]

    total_score = int(net_control_score + position_score + proximity_score + material_score)
    
    if os.environ.get("TUNER_DEBUG_COMPONENTS") == "1":
        return total_score, {
            "material": material_score,
            "position": position_score,
            "proximity": proximity_score,
            "net_control": net_control_score,
            "ncc_for_debug": net_control_count
        }
    return total_score


# ═══════════════════════════════════════════════════════════════════════════════
#  第四部分：Sigmoid 误差函数与 K 值搜索
# ═══════════════════════════════════════════════════════════════════════════════

def sigmoid(scores, K):
    """将评估分映射为胜率预测: 1 / (1 + 10^(-K*score/400))"""
    exponent = -K * scores / 400.0
    return 1.0 / (1.0 + np.power(10.0, exponent))


def compute_loss(scores, outcomes, K, params, ref_params, lmbda, sample_weights=None):
    """
    计算总损失: Weighted MSE + L2 正则化项。
    sample_weights: 如果提供，将对不同 outcome 的样本进行加权。
    返回 (total_loss, mse)
    """
    predicted = sigmoid(scores, K)
    diff = outcomes - predicted
    sq_diff = diff * diff
    
    if sample_weights is not None:
        # 加权 MSE
        mse = float(np.sum(sample_weights * sq_diff) / np.sum(sample_weights))
    else:
        mse = float(np.mean(sq_diff))
    
    if lmbda <= 0 or ref_params is None:
        return mse, mse
        
    p_np = np.asarray(params, dtype=np.float64)
    r_np = np.asarray(ref_params, dtype=np.float64)
    reg_loss = float(np.sum((p_np - r_np)**2)) / len(params)
    
    total_loss = mse + lmbda * reg_loss
    return total_loss, mse


def find_optimal_k(boards, outcomes, params, net_control_counts, k_range=(0.1, 3.0), precision=0.01):
    """
    黄金分割法搜索最优 K 值。
    K 控制 score → 胜率的映射斜率。
    """
    print("\n[K值搜索] 开始...")
    scores = batch_evaluate(boards, params, net_control_counts)
    outcomes_np = np.asarray(outcomes, dtype=np.float64)

    PHI = (1 + math.sqrt(5)) / 2  # 黄金比 ≈ 1.618
    a, b = k_range

    while (b - a) > precision:
        c = b - (b - a) / PHI
        d = a + (b - a) / PHI

        # 搜索 K 阶段不考虑正则化 (lambda=0)
        loss_c, _ = compute_loss(scores, outcomes_np, c, params, None, 0, sample_weights=None)
        loss_d, _ = compute_loss(scores, outcomes_np, d, params, None, 0, sample_weights=None)

        if loss_c < loss_d:
            b = d
        else:
            a = c

    best_k = (a + b) / 2
    best_loss, _ = compute_loss(scores, outcomes_np, best_k, params, None, 0)
    print(f"[K值搜索] 最优 K = {best_k:.4f}, MSE = {best_loss:.8f}")
    return best_k


# ═══════════════════════════════════════════════════════════════════════════════
#  第五部分：单调性约束 + 坐标下降优化器
# ═══════════════════════════════════════════════════════════════════════════════

def check_logic_constraints(params, param_idx):
    """
    执行评估逻辑硬约束：
    1. 子力分单调递减 (Material(n) >= Material(n+1))
    2. 控制区映射单调递增
    3. 贴炮惩罚必须为非正数 (<= 0)
    
    返回 True 表示满足约束，False 表示违反。
    """
    # ── 1. 子力分单调递减约束 ──
    if 0 <= param_idx <= 14:
        if param_idx > 0 and params[param_idx] > params[param_idx - 1]:
            return False
        if param_idx < 14 and params[param_idx] < params[param_idx + 1]:
            return False
        return True

    # ── 2. 贴炮项符号约束 ──
    if param_idx == 15:
        if params[15] > 0:
            return False
        return True

    # ── 3. 控制区映射单调递增约束 ──
    if 16 <= param_idx <= 21:
        if param_idx > 16 and params[param_idx] < params[param_idx - 1]:
            return False
        if param_idx < 21 and params[param_idx] > params[param_idx + 1]:
            return False
        return True

    return True


def save_checkpoint(path, params, step, epoch, K, mse):
    """保存训练断点"""
    data = {
        "params": params,
        "step": step,
        "epoch": epoch,
        "K": K,
        "mse": mse,
        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
    }
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=2)


def load_checkpoint(path):
    """加载训练断点，返回 dict 或 None"""
    if os.path.exists(path):
        with open(path, 'r', encoding='utf-8') as f:
            return json.load(f)
    return None


def coordinate_descent(boards, outcomes, params, K, net_control_counts,
                       ref_params=None, lmbda=1e-6,
                       initial_step=10, min_step=1, decay=0.7,
                       max_epochs=100, checkpoint_path=None,
                       sample_weights=None):
    """
    坐标下降法优化参数向量（含逻辑约束 + L2 正则化 + 断点续训 + 加权 Loss）。
    """
    outcomes_np = np.asarray(outcomes, dtype=np.float64)
    best_params = list(params)

    # ── 尝试从断点恢复 ──
    resumed = False
    if checkpoint_path:
        cp = load_checkpoint(checkpoint_path)
        if cp:
            best_params = cp["params"]
            step = cp["step"]
            epoch = cp["epoch"]
            K = cp["K"]
            best_loss = cp["mse"]
            resumed = True
            print(f"\n[续训] 从断点恢复: 轮次={epoch}, step={step}, "
                  f"Loss={best_loss:.8f}, K={K:.4f}")
            print(f"       断点时间: {cp['timestamp']}")

    if not resumed:
        scores = batch_evaluate(boards, best_params, net_control_counts)
        best_loss, best_mse = compute_loss(scores, outcomes_np, K, best_params, ref_params, lmbda, sample_weights=sample_weights)
        print(f"\n[优化] 初始状态: Loss={best_loss:.8f}, MSE={best_mse:.8f}")
        step = initial_step
        epoch = 0

    skipped_total = 0

    while step >= min_step and epoch < max_epochs:
        epoch += 1
        improved = False
        improvements_this_epoch = 0
        skipped_this_epoch = 0

        t0 = time.time()

        for param_idx in range(PARAM_DIM):
            original_val = best_params[param_idx]

            for direction in [+step, -step]:
                best_params[param_idx] = original_val + direction

                # 先检查硬约束
                if not check_logic_constraints(best_params, param_idx):
                    best_params[param_idx] = original_val
                    skipped_this_epoch += 1
                    continue

                new_scores = batch_evaluate(boards, best_params, net_control_counts)
                new_loss, new_mse = compute_loss(new_scores, outcomes_np, K, best_params, ref_params, lmbda, sample_weights=sample_weights)

                if new_loss < best_loss:
                    best_loss = new_loss
                    best_mse = new_mse
                    improved = True
                    improvements_this_epoch += 1
                    original_val = best_params[param_idx]
                    break
            else:
                best_params[param_idx] = original_val

        elapsed = time.time() - t0
        skipped_total += skipped_this_epoch

        print(f"  [轮次 {epoch:>3}] step={step:>4} | Loss={best_loss:.8f} | MSE={best_mse:.8f} | "
              f"改进={improvements_this_epoch:>2}/{PARAM_DIM} | "
              f"约束跳过={skipped_this_epoch} | 耗时={elapsed:.1f}s")

        # ── 每轮保存断点 ──
        if checkpoint_path:
            save_checkpoint(checkpoint_path, best_params, step, epoch, K, best_loss)

        if not improved:
            step = int(step * decay)
            if step < min_step:
                break
            print(f"  [步长缩小] 新步长 = {step}")

    print(f"\n[优化] 完成! 最终 Loss = {best_loss:.8f}, 共 {epoch} 轮")
    return best_params, best_loss, K


# ═══════════════════════════════════════════════════════════════════════════════
#  第六部分：结果输出
# ═══════════════════════════════════════════════════════════════════════════════

def export_results(original_params, tuned_params, K, mse, output_dir):
    """导出调优结果为 JSON 并打印可复制的代码片段"""

    os.makedirs(output_dir, exist_ok=True)

    # ── 1. 构建结果字典 ──
    result = {
        "description": "Texel 调优结果 (含正则化与逻辑约束)",
        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
        "optimal_K": round(K, 4),
        "final_loss": round(mse, 8),
        "BASE_MATERIAL_SCORES": [int(tuned_params[i]) for i in range(15)],
        "WEIGHT_SOLDIER_PROXIMITY": int(tuned_params[15]),
        "WEIGHT_NET_MAP": {str(i): int(tuned_params[16 + i]) for i in range(6)},
        "SOLDIER_POSITION_TABLE": [
            [int(tuned_params[22 + r * 3 + _POS_SYMMETRIC_COLS[c]]) for c in range(5)]
            for r in range(5)
        ],
    }

    # ── 2. 保存 JSON ──
    json_path = os.path.join(output_dir, "tuned_weights.json")
    with open(json_path, 'w', encoding='utf-8') as f:
        json.dump(result, f, indent=4, ensure_ascii=False)
    print(f"\n[输出] JSON 已保存: {json_path}")

    # ── 3. 打印对比表 ──
    print("\n" + "=" * 70)
    print("参数对比（原始 → 调优后）:")
    print("=" * 70)
    for i in range(PARAM_DIM):
        old = int(original_params[i])
        new = int(tuned_params[i])
        delta = new - old
        marker = " ◀" if delta != 0 else ""
        print(f"  [{i:>2}] {PARAM_NAMES[i]:<22s}: {old:>6} → {new:>6}  ({delta:+d}){marker}")

    # ── 4. 打印可复制代码 ──
    print("\n" + "=" * 70)
    print("可直接复制到 evaluation_logic.pyx 的 DEFAULT_SETTINGS:")
    print("=" * 70)

    mat = [int(tuned_params[i]) for i in range(15)]
    print(f'''
DEFAULT_SETTINGS = {{
    "BASE_MATERIAL_SCORES": [
        {mat[0]:>5}, {mat[1]:>5}, {mat[2]:>5}, {mat[3]:>5}, {mat[4]:>5},
        {mat[5]:>5}, {mat[6]:>5}, {mat[7]:>5}, {mat[8]:>5}, {mat[9]:>5},
        {mat[10]:>5}, {mat[11]:>5}, {mat[12]:>5}, {mat[13]:>5}, {mat[14]:>5}
    ],
    "WEIGHT_SOLDIER_PROXIMITY": {int(tuned_params[15])},
    "WEIGHT_NET_MAP": {{
        0: {int(tuned_params[16])}, 1: {int(tuned_params[17])}, 2: {int(tuned_params[18])}, 3: {int(tuned_params[19])},
        4: {int(tuned_params[20])}, 5: {int(tuned_params[21])},
    }},
    "MAX_NET_CONTROL_SCORE": {int(tuned_params[21])},
    "SOLDIER_POSITION_TABLE": [''')

    for r in range(5):
        base = 22 + r * 3
        v0, v1, v2 = int(tuned_params[base]), int(tuned_params[base+1]), int(tuned_params[base+2])
        row = [v0, v1, v2, v1, v0]  # 对称展开
        comma = "," if r < 4 else ""
        print(f"        [{row[0]:>4}, {row[1]:>4}, {row[2]:>4}, {row[3]:>4}, {row[4]:>4}]{comma}")

    print("    ]")
    print("}")

    # ── 5. 同步更新 C 数组初始化代码片段 ──
    print("\n" + "=" * 70)
    print("同步更新 _init_precomputed_tables() 中的 m_scores 列表:")
    print("=" * 70)
    print(f"    cdef list m_scores = [0, {', '.join(str(int(tuned_params[i])) for i in range(15))}]")

    # 位置表 C 数组初始化
    print(f"\n    # Position table (对称)")
    for r in range(5):
        base = 22 + r * 3
        v0, v1, v2 = int(tuned_params[base]), int(tuned_params[base+1]), int(tuned_params[base+2])
        for c, v in enumerate([v0, v1, v2, v1, v0]):
            print(f"    _precomputed_soldier_position_scores[{r}][{c}] = {v}")

    net_vals = [int(tuned_params[16 + i]) for i in range(6)]
    print(f"\n    # Init net map")
    print(f"    for i in range(30):")
    print(f"        _net_map_c[i] = {net_vals[5]}")
    for idx, val in enumerate(net_vals):
        print(f"    _net_map_c[{idx}] = {val}")


# ═══════════════════════════════════════════════════════════════════════════════
#  主程序
# ═══════════════════════════════════════════════════════════════════════════════

def main():
    parser = argparse.ArgumentParser(
        description='Texel 自动化调优 - Three Cannons 引擎',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  快速测试:   python scripts/texel_tuner.py --max-samples 1000 --epochs 3
  完整训练:   python scripts/texel_tuner.py --data data/selfplay/run1.jsonl
  强制CPU:    python scripts/texel_tuner.py --cpu
        """
    )

    root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    default_data = os.path.join(root, "data", "selfplay", "run2.jsonl")
    default_output = os.path.join(root, "data", "tuning")
    default_base_weights = os.path.join(root, "data", "tuning", "tuned_weights-R1.json")

    parser.add_argument("--data", type=str, default=default_data,
                        help="数据文件路径 (JSONL)")
    parser.add_argument("--output", type=str, default=default_output,
                        help="输出目录")
    parser.add_argument("--max-samples", type=int, default=None,
                        help="最大样本数（用于快速测试）")
    parser.add_argument("--epochs", type=int, default=100,
                        help="最大迭代轮次 (默认 100)")
    parser.add_argument("--initial-step", type=int, default=10,
                        help="初始步长 (默认 10)")
    parser.add_argument("--min-step", type=int, default=1,
                        help="最小步长 (默认 1)")
    parser.add_argument("--cpu", action="store_true",
                        help="强制使用 CPU (禁用 CuPy)")
    parser.add_argument("--k-value", type=float, default=None,
                        help="手动指定 K 值（跳过自动搜索）")
    parser.add_argument("--reset", action="store_true",
                        help="忽略已有断点，从头开始")
    parser.add_argument("--weights", type=str, default=default_base_weights,
                        help="从指定的 JSON 权重文件加载初始参数 (默认使用 R1 权重作为起点)")
    parser.add_argument("--ref-weights", type=str, default=os.path.join(root, "data", "tuning", "original_weights.json"),
                        help="L2 正则化参考基准权重 JSON 路径")
    parser.add_argument("--draw-weight", type=float, default=2.0,
                        help="和棋样本的加权系数 (用于补偿样本稀少问题，默认加倍为 2.0)")
    parser.add_argument("--lmbda", type=float, default=1e-6,
                        help="L2 正则化强度 (默认 1e-6)。若参数不动, 请尝试调低此值。")
    args = parser.parse_args()

    # ── 初始化 ──
    setup_backend(force_cpu=args.cpu)

    print("=" * 70)
    print("  Texel 自动化调优 - Three Cannons 引擎")
    print("=" * 70)

    # ── 断点路径 ──
    os.makedirs(args.output, exist_ok=True)
    checkpoint_path = os.path.join(args.output, "checkpoint.json")

    if args.reset and os.path.exists(checkpoint_path):
        os.remove(checkpoint_path)
        print("[断点] 已清除旧断点，从头开始")

    # ── 加载数据 ──
    boards, outcomes, sc_list = load_dataset(args.data, max_samples=args.max_samples)

    # ── 计算样本权重 (用于均衡稀有样本贡献) ──
    sample_weights = None
    if args.draw_weight != 1.0:
        print(f"[加权] 正在为和棋样本应用权重系数: {args.draw_weight}")
        sample_weights = np.ones(len(outcomes), dtype=np.float64)
        outcomes_cpu = np.asarray(outcomes) 
        is_draw = (np.abs(outcomes_cpu - 0.5) < 0.01)
        sample_weights[is_draw] = args.draw_weight
        
        # 如果有兵力数据，可以进一步微调（此处暂仅记录，保留逻辑扩展位）
        # if sc_list is not None: ...

    # ── BFS 预计算（一次性，不依赖可调参数）──
    net_control_counts = precompute_net_control(boards)

    # ── 初始参数负载顺序：断点 > 指定权重 > 默认配置 ──
    params = None
    cp = None
    if not args.reset:
        cp = load_checkpoint(checkpoint_path)

    if cp:
        params = cp["params"]
        K = cp["K"]
        print(f"\n[续训] 检测到断点，将忽略 --weights 并从断点恢复 (K={K:.4f})")
    elif args.weights:
        print(f"\n[参数] 正在从 {args.weights} 加载初始权重...")
        params = load_params_from_json(args.weights)
        if params:
            # 如果从权重文件加载，需要先找这个权重对应的最优 K
            K = args.k_value if args.k_value is not None else find_optimal_k(boards, outcomes, params, net_control_counts)
        else:
            print("[参数] 权重加载失败，回退到默认配置。")

    if params is None:
        params = get_default_params()
        K = args.k_value if args.k_value is not None else find_optimal_k(boards, outcomes, params, net_control_counts)

    original_params = list(params)
    print(f"[参数] 维度 = {PARAM_DIM}")

    # ── 加载正则化参考基准 ──
    ref_params = None
    if args.lmbda > 0:
        if os.path.exists(args.ref_weights):
            print(f"[正则化] 正在加载基准权重: {args.ref_weights} (lambda={args.lmbda})")
            ref_params = load_params_from_json(args.ref_weights)
        else:
            print(f"[警告] 正则化基准文件不存在: {args.ref_weights}，将禁用正则化。")

    # ── 坐标下降 ──
    tuned_params, final_mse, K = coordinate_descent(
        boards, outcomes, params, K, net_control_counts,
        ref_params=ref_params,
        lmbda=args.lmbda,
        initial_step=args.initial_step,
        min_step=args.min_step,
        max_epochs=args.epochs,
        checkpoint_path=checkpoint_path,
        sample_weights=sample_weights, # 传入权重向量
    )

    # ── 调优后重新搜索 K（参数变了，最优 K 可能也变了）──
    if args.k_value is None:
        print("\n[K值] 调优后再次搜索以确保映射最优...")
        K = find_optimal_k(boards, outcomes, tuned_params, net_control_counts)

    # ── 输出结果 ──
    export_results(original_params, tuned_params, K, final_mse, args.output)

    # ── 训练完成，清理断点 ──
    if os.path.exists(checkpoint_path):
        os.remove(checkpoint_path)
        print("[断点] 训练完成，已清理断点文件")

    print("\n" + "=" * 70)
    print("  调优完成！")
    print("=" * 70)


if __name__ == "__main__":
    main()
