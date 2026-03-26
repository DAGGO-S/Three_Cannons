"""
generate_tablebase_expand.py - 种子扩展模式残局库生成器

与全量模式 generate_tablebase.py 并存。
全量模式枚举所有局面，适合小力残局（C3S1-S6）和炮方胜分析。
本脚本仅发现 soldier_win（兵胜/炮被困毙）局面，内存占用与 mate 数量成正比。

算法三阶段：
  1. 种子枚举：仅枚举炮方被完全包围的困毙局面（DTM=0）
  2. BFS 反向扩展：从种子出发逐层计算所有 mate 前驱局面
  3. 导出：仅输出 soldier_win 节点

用法：
  python scripts/tb_analysis/generate_tablebase_expand.py --cannons 3 --soldiers 8
  python scripts/tb_analysis/generate_tablebase_expand.py --cannons 3 --soldiers 5 --max-dtm 200
"""

import sys
import os
import argparse
import itertools
import pickle
import time
from collections import deque
import logging

# 确保可从项目根目录导入核心模块
root_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if root_dir not in sys.path:
    sys.path.insert(0, root_dir)

from core.game_logic import GameState, CANNON, SOLDIER, EMPTY

# ---------------------------------------------------------------------------
# 常量（与 generate_tablebase.py 保持一致）
# ---------------------------------------------------------------------------
TB_CANNON_WIN = 1
TB_SOLDIER_WIN = -1
TB_DRAW = 0

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


# ============================================================================
# 工具函数
# ============================================================================

def get_all_moves(state):
    """获取 state 的所有合法走法，返回 [(start_r, start_c, end_r, end_c), ...]"""
    moves = []
    player = state.current_player
    for r in range(5):
        for c in range(5):
            if state.board[r][c] == player:
                for end in state.get_valid_moves(r, c):
                    moves.append((r, c, end[0], end[1]))
    return moves


def load_sub_tb(cannons, soldiers, data_dir):
    """加载 S-1 的子库。返回 {canonical_hash: (val, dtm, cti)} 或 空dict。"""
    if soldiers <= 0:
        return {}
    fname = f"tb_c{cannons}_s{soldiers}.pkl"
    search_dirs = [
        os.path.join(data_dir, 'soldier_win'),
        os.path.join(data_dir, 'cannon_win'),
        data_dir,
    ]
    merged = {}
    for d in search_dirs:
        path = os.path.join(d, fname)
        if os.path.exists(path):
            try:
                with open(path, 'rb') as f:
                    data = pickle.load(f)
                merged.update(data)
                logger.info(f"Loaded sub-TB: {path} ({len(data)} entries)")
            except Exception as e:
                logger.warning(f"Failed to load {path}: {e}")
    return merged


# ============================================================================
# 阶段 1: 种子枚举
# ============================================================================

def enumerate_seeds(cannon_num, soldier_num):
    """
    枚举所有 soldier_win（DTM=0）的困毙局面。
    困毙 = 轮到炮走，但炮方所有棋子（炮）无路可走。
    
    优化策略：计算每组炮位置的必要封堵格，提前剪枝。
    """
    logger.info(f"[1/3] Enumerating mate seeds for C{cannon_num}S{soldier_num}...")
    t0 = time.time()

    cells = list(range(25))
    seeds = []  # [(GameState, canonical_hash)]
    seen = set()

    # 预计算每个格子的邻居
    neighbors = {}
    for idx in range(25):
        r, c = idx // 5, idx % 5
        ns = []
        for dr, dc in [(0,1),(0,-1),(1,0),(-1,0)]:
            nr, nc = r + dr, c + dc
            if 0 <= nr < 5 and 0 <= nc < 5:
                ns.append(nr * 5 + nc)
        neighbors[idx] = ns

    for cannon_pos in itertools.combinations(cells, cannon_num):
        # 计算必要封堵格：要困住所有炮，必须用其他棋子（兵 or 其他炮）堵住这些炮的相邻空格
        blocking_needed = set()
        for cp in cannon_pos:
            for nb in neighbors[cp]:
                if nb not in cannon_pos:
                    blocking_needed.add(nb)

        # 剪枝：如果需要堵的格子数 > 可用的兵数，那这组炮位一定无法被困住
        if len(blocking_needed) > soldier_num:
            continue

        # 剪枝：可用格子（排除炮位）中足够的兵来填充封堵格
        remaining = [c for c in cells if c not in cannon_pos]
        available_for_block = [c for c in remaining if c in blocking_needed]
        if len(available_for_block) < len(blocking_needed):
            continue

        # 封堵格必须全部由兵填充
        forced_soldiers = list(blocking_needed)
        extra_soldiers_needed = soldier_num - len(forced_soldiers)

        if extra_soldiers_needed < 0:
            continue

        # 剩余兵可以放在任何非炮非封堵格位置
        extra_cells = [c for c in remaining if c not in blocking_needed]

        if extra_soldiers_needed > len(extra_cells):
            continue

        for extra_pos in itertools.combinations(extra_cells, extra_soldiers_needed):
            # 构建棋盘
            board_1d = [EMPTY] * 25
            for p in cannon_pos:
                board_1d[p] = CANNON
            for p in forced_soldiers:
                board_1d[p] = SOLDIER
            for p in extra_pos:
                board_1d[p] = SOLDIER

            board_2d = [board_1d[i:i+5] for i in range(0, 25, 5)]

            # 困毙只发生在轮到炮方走时
            state = GameState(board_2d, CANNON)

            # 验证确实困毙：炮方无任何合法走法
            if state.winner == SOLDIER:
                ch = state.get_canonical_hash()
                if ch not in seen:
                    seen.add(ch)
                    seeds.append((state, ch))

    elapsed = time.time() - t0
    logger.info(f"    Found {len(seeds)} seeds in {elapsed:.2f}s")
    return seeds


# ============================================================================
# 阶段 2: BFS 逆向扩展
# ============================================================================

def expand_from_seeds(seeds, sub_tb=None, max_dtm=200):
    """
    从种子出发，严格按 DTM 逐层推进的 BFS 逆向扩展。
    
    核心逻辑：
    - 奇数 DTM（兵方走的前驱）：OR 逻辑，任意子节点为 mate 即标记为 mate
    - 偶数 DTM（炮方走的前驱）：AND 逻辑，所有子节点均为 mate 才标记
    
    使用 set[hash] 追踪 cannon_pending，避免误判。
    """
    if sub_tb is None:
        sub_tb = {}

    logger.info(f"[2/3] Starting BFS expansion from {len(seeds)} seeds...")
    t0 = time.time()

    # mate_set: {canonical_hash: (val, dtm)}
    mate_set = {}
    # state_cache: {canonical_hash: GameState}，用于探索前驱
    state_cache = {}
    # cannon_pending: {canonical_hash: set(unresolved子节点的canonical_hash)}
    cannon_pending = {}
    # cannon_pending_dtm: {canonical_hash: max_child_dtm}
    cannon_pending_dtm = {}
    # layer_queue: {dtm: [canonical_hash]}
    layer_queue = {}

    # 初始化种子（DTM=0）
    for state, ch in seeds:
        mate_set[ch] = (TB_SOLDIER_WIN, 0)
        state_cache[ch] = state
        layer_queue.setdefault(0, []).append(ch)

    current_dtm = 0
    stats_interval = time.time()

    while current_dtm <= max_dtm:
        if current_dtm not in layer_queue or not layer_queue[current_dtm]:
            higher = [d for d in layer_queue if d > current_dtm and layer_queue[d]]
            if not higher:
                break
            current_dtm = min(higher)

        batch = layer_queue[current_dtm]
        layer_queue[current_dtm] = []

        for state_ch in batch:
            state = state_cache[state_ch]

            # 生成此局面的所有"反走"前驱（Un-move）
            # 反走 = 将棋子退回相邻空格（不涉及吃子，同子力级别内）
            predecessors = _generate_predecessors(state)

            for pred_state in predecessors:
                ph = pred_state.get_canonical_hash()
                if ph in mate_set:
                    continue

                # 确定前驱的走子方
                pred_player = pred_state.current_player

                if pred_player == SOLDIER:
                    # 兵走前驱（OR 逻辑）：兵走到了 state 这步，这步是 mate
                    # 所以 pred 的某个走法能导致 mate -> pred 也是 mate
                    mate_set[ph] = (TB_SOLDIER_WIN, current_dtm + 1)
                    state_cache[ph] = pred_state
                    layer_queue.setdefault(current_dtm + 1, []).append(ph)

                elif pred_player == CANNON:
                    # 炮走前驱（AND 逻辑）：必须验证炮的所有走法是否均不能逃脱
                    if ph not in cannon_pending:
                        # 首次访问：统计该局面炮方的所有合法走法的去向
                        all_moves = get_all_moves(pred_state)
                        unresolved = set()
                        has_escape = False  # 是否存在逃逸路径

                        for sr, sc, er, ec in all_moves:
                            nxt = pred_state.move_piece(sr, sc, er, ec)
                            nxt_ch = nxt.get_canonical_hash()

                            if nxt_ch in mate_set:
                                # 这条路已经是 mate，不加入 unresolved
                                pass
                            elif nxt.soldier_count < pred_state.soldier_count:
                                # 吃子走法：进入子库空间
                                if sub_tb and nxt_ch in sub_tb:
                                    sub_val = sub_tb[nxt_ch][0]
                                    if sub_val != TB_SOLDIER_WIN:
                                        # 子库中不是兵胜 -> 炮能逃跑
                                        has_escape = True
                                        break
                                else:
                                    # 吃子后无子库数据 -> 保守视为逃逸
                                    has_escape = True
                                    break
                            else:
                                # 非吃子走法，去向尚未确定为 mate
                                unresolved.add(nxt_ch)

                        # 关键修复：只要有逃逸路径，直接跳过，不创建 pending
                        if has_escape:
                            continue

                        if not unresolved:
                            # 所有走法均已确认 mate -> 该前驱也是 mate
                            dtm_val = current_dtm + 1
                            mate_set[ph] = (TB_SOLDIER_WIN, dtm_val)
                            state_cache[ph] = pred_state
                            layer_queue.setdefault(dtm_val, []).append(ph)
                            continue

                        # 有 unresolved 但无逃逸 -> 创建 pending
                        cannon_pending[ph] = unresolved
                        cannon_pending_dtm[ph] = current_dtm + 1
                        state_cache[ph] = pred_state

                    else:
                        # 已在 cannon_pending 中，尝试消除一个 unresolved
                        # 关键修复：只有 state_ch 确实在 unresolved 中时才消除
                        if state_ch not in cannon_pending[ph]:
                            continue
                        cannon_pending[ph].discard(state_ch)
                        cannon_pending_dtm[ph] = max(cannon_pending_dtm.get(ph, 0), current_dtm + 1)

                        if not cannon_pending[ph]:
                            # 所有子节点已确认 mate -> 该前驱也是 mate
                            dtm_val = cannon_pending_dtm[ph]
                            mate_set[ph] = (TB_SOLDIER_WIN, dtm_val)
                            layer_queue.setdefault(dtm_val, []).append(ph)
                            del cannon_pending[ph]
                            del cannon_pending_dtm[ph]

        # 每层输出进度（前50层逐层，之后每5秒一次）
        layer_count = len(batch)
        if layer_count > 0:
            if current_dtm <= 50:
                logger.info(f"    DTM={current_dtm}: +{layer_count} in batch, "
                            f"total={len(mate_set)} mates, pending={len(cannon_pending)}")
            else:
                now = time.time()
                if now - stats_interval > 5.0:
                    logger.info(f"    DTM={current_dtm}, found {len(mate_set)} mates, "
                                f"pending={len(cannon_pending)}")
                    stats_interval = now

        current_dtm += 1

    elapsed = time.time() - t0
    max_found_dtm = max((v[1] for v in mate_set.values()), default=0)
    logger.info(f"    BFS complete: {len(mate_set)} mates, max DTM={max_found_dtm}, "
                f"{elapsed:.2f}s")

    return mate_set


def _generate_predecessors(state):
    """
    生成所有能通过一次非吃子移动到达 state 的前驱局面。
    
    原理：当前局面中属于"上一步走子方"的棋子，可能是从相邻空格走过来的。
    将该棋子退回空格，即得到一个前驱局面。
    """
    predecessors = []
    board = state.board
    # 上一步走子方 = 当前待行方的对手
    other = SOLDIER if state.current_player == CANNON else CANNON

    for end_idx in range(25):
        end_r, end_c = end_idx // 5, end_idx % 5
        if board[end_r][end_c] != other:
            continue

        for dr, dc in [(0,1),(0,-1),(1,0),(-1,0)]:
            start_r, start_c = end_r + dr, end_c + dc
            if 0 <= start_r < 5 and 0 <= start_c < 5:
                if board[start_r][start_c] == EMPTY:
                    # 构建前驱棋盘：棋子从 start 走到 end，反向即 end->start
                    pred_board = [list(row) for row in board]
                    pred_board[start_r][start_c] = other
                    pred_board[end_r][end_c] = EMPTY
                    pred_state = GameState(pred_board, other)
                    predecessors.append(pred_state)

    return predecessors


# ============================================================================
# 阶段 3: 导出
# ============================================================================

def export_results(mate_set, cannons, soldiers, output_dir, fmt='pickle'):
    """
    以兼容 tb_solver.py 的格式导出。
    格式：{canonical_hash: (TB_SOLDIER_WIN, dtm, 0.0)}
    """
    logger.info(f"[3/3] Exporting {len(mate_set)} entries...")

    # 转换为 tb_solver.py 期望的格式
    tb_data = {}
    for ch, (val, dtm) in mate_set.items():
        tb_data[ch] = (val, dtm, 0.0)

    # 导出到 soldier_win 子目录
    out_dir = os.path.join(output_dir, 'soldier_win')
    os.makedirs(out_dir, exist_ok=True)

    fname = f"tb_c{cannons}_s{soldiers}.pkl"
    out_path = os.path.join(out_dir, fname)

    with open(out_path, 'wb') as f:
        pickle.dump(tb_data, f)
    logger.info(f"    Saved to {out_path}")

    # 统计
    dtm_counts = {}
    for ch, (val, dtm, cti) in tb_data.items():
        dtm_counts[dtm] = dtm_counts.get(dtm, 0) + 1

    logger.info(f"    DTM distribution:")
    for dtm in sorted(dtm_counts.keys()):
        logger.info(f"      DTM={dtm}: {dtm_counts[dtm]} states")


# ============================================================================
# 主入口
# ============================================================================

def build_expand(cannons, soldiers, output_dir, max_dtm=200):
    """单一子力组合的完整构建流程。"""
    t0 = time.time()
    label = f"C{cannons}S{soldiers}"
    logger.info(f"Building expansion for {label}...")

    # 加载子库（S-1 级别）
    sub_tb = load_sub_tb(cannons, soldiers - 1, output_dir)
    if sub_tb:
        logger.info(f"Sub-TB loaded: {len(sub_tb)} entries for S{soldiers-1}")

    # 阶段 1: 种子枚举
    seeds = enumerate_seeds(cannons, soldiers)

    # 阶段 2: BFS 反向扩展
    mate_set = expand_from_seeds(seeds, sub_tb=sub_tb, max_dtm=max_dtm)

    # 阶段 3: 导出
    export_results(mate_set, cannons, soldiers, output_dir)

    elapsed = time.time() - t0
    logger.info(f"=== {label} complete: {len(mate_set)} mates in {elapsed:.2f}s ===")


def main():
    parser = argparse.ArgumentParser(
        description="Seed Expansion Tablebase Generator (soldier_win only)")
    parser.add_argument("--cannons", type=int, default=3,
                        help="Number of cannons (default: 3)")
    parser.add_argument("--soldiers", type=int, default=10,
                        help="Number of soldiers. Use '5-10' for range.")
    parser.add_argument("--output", type=str, default="data/tablebase",
                        help="Output directory")
    parser.add_argument("--max-dtm", type=int, default=200,
                        help="Maximum DTM depth for BFS")
    parser.add_argument("--format", type=str, default="pickle",
                        choices=["pickle"],
                        help="Output format")
    args = parser.parse_args()

    s_arg = str(args.soldiers)
    if '-' in s_arg:
        s_min, s_max = map(int, s_arg.split('-'))
        soldier_range = range(s_min, s_max + 1)
    else:
        soldier_range = [int(s_arg)]

    for s in soldier_range:
        build_expand(args.cannons, s, args.output, args.max_dtm)


if __name__ == "__main__":
    main()
