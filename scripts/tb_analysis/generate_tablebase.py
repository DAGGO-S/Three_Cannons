"""
generate_tablebase.py - 三炮十五兵 逆向推演残局库生成器

通过枚举特定子力组合下的所有合法局面，以逆向推演（Retrograde Analysis）
精确计算每个局面的理论胜负及 DTM（达到将杀的最短步数）。

输出格式:
  - binary (.tb):  紧凑二进制 + zlib 压缩
  - pickle (.pkl): 兼容现有 tb_solver.py 的 {hash: (val, dtm, cti)} 格式
  - csv (.csv):    人可读文本（FEN, wdl, dtm, turn, canonical_hash）

CTI（累积高压指数）为可选计算，默认关闭。

用法：
  python scripts/tb_analysis/generate_tablebase.py --cannons 3 --soldiers 1
"""

import sys
import os
import argparse
import itertools
import pickle
import struct
import zlib
import time
import csv as csv_module
from collections import deque
from typing import Dict, Optional, Tuple, List

# 确保可从项目根目录导入核心模块
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from core.game_logic import GameState, CANNON, SOLDIER, EMPTY

# ---------------------------------------------------------------------------
# 常量定义
# ---------------------------------------------------------------------------
TB_CANNON_WIN = 1     # 炮方胜
TB_SOLDIER_WIN = -1   # 兵方胜
TB_DRAW = 0           # 和棋

# 二进制文件魔数与版本
TB_MAGIC = b'TC_TB'
TB_VERSION = 1

# WDL 编码：将 -1/0/1 映射到 uint8
WDL_ENCODE = {TB_SOLDIER_WIN: 0, TB_DRAW: 1, TB_CANNON_WIN: 2}
WDL_DECODE = {0: TB_SOLDIER_WIN, 1: TB_DRAW, 2: TB_CANNON_WIN}
WDL_LABEL = {TB_CANNON_WIN: 'win', TB_SOLDIER_WIN: 'lose', TB_DRAW: 'draw'}

# ---------------------------------------------------------------------------
# 数据容器：使用平坦数组替代对象，降低内存占用
# ---------------------------------------------------------------------------
class TablebaseData:
    """
    残局库核心数据容器。
    以 hash-to-index 映射 + 平坦数组的方式存储所有节点信息，
    内存效率远高于逐节点 Python 对象。
    """
    __slots__ = [
        'hash_to_idx',      # dict: canonical_hash -> int（节点索引）
        'hashes',           # list[int]: 按索引存储的规范化哈希值
        'states',           # list[GameState]: 按索引存储的 GameState（推演阶段使用，导出后丢弃）
        'values',           # list[int]: 胜负判定（TB_CANNON_WIN / TB_SOLDIER_WIN / TB_DRAW）
        'dtms',             # list[int]: DTM 步数
        'ctis',             # list[float]: CTI 值（仅在启用 CTI 时有意义）
        'parents',          # list[list[int]]: 前驱节点索引列表
        'children_count',   # list[int]: 合法后续走法总数
        'unresolved',       # list[int]: 尚未确定理论价值的后续走法数
    ]

    def __init__(self):
        self.hash_to_idx = {}
        self.hashes = []
        self.states = []
        self.values = []
        self.dtms = []
        self.ctis = []
        self.parents = []
        self.children_count = []
        self.unresolved = []

    @property
    def size(self) -> int:
        return len(self.hashes)

    def add_node(self, canonical_hash: int, state: GameState) -> int:
        """添加一个节点，返回其索引。如果哈希已存在则跳过。"""
        if canonical_hash in self.hash_to_idx:
            return -1
        idx = len(self.hashes)
        self.hash_to_idx[canonical_hash] = idx
        self.hashes.append(canonical_hash)
        self.states.append(state)
        self.values.append(TB_DRAW)
        self.dtms.append(0)
        self.ctis.append(0.0)
        self.parents.append([])
        self.children_count.append(0)
        self.unresolved.append(0)
        return idx


# ---------------------------------------------------------------------------
# 阶段 1：状态空间枚举
# ---------------------------------------------------------------------------
def enumerate_states(cannon_num: int, soldier_num: int) -> TablebaseData:
    """
    枚举指定子力组合下的所有合法局面。
    利用 D4 对称群的规范化哈希实现 8 倍空间压缩。
    """
    print(f"[1/5] 枚举状态空间: {cannon_num}炮 vs {soldier_num}兵")
    t0 = time.time()

    data = TablebaseData()
    cells = range(25)

    for cannon_pos in itertools.combinations(cells, cannon_num):
        remaining = [c for c in cells if c not in cannon_pos]
        for soldier_pos in itertools.combinations(remaining, soldier_num):
            board_1d = [0] * 25
            for p in cannon_pos:
                board_1d[p] = CANNON
            for p in soldier_pos:
                board_1d[p] = SOLDIER

            board_2d = [board_1d[i:i + 5] for i in range(0, 25, 5)]

            for turn in [CANNON, SOLDIER]:
                state = GameState(board_2d, turn)
                ch = state.get_canonical_hash()
                data.add_node(ch, state)

    elapsed = time.time() - t0
    print(f"    去重完毕: {data.size} 个规范化节点, 耗时 {elapsed:.2f}s")
    return data


# ---------------------------------------------------------------------------
# 阶段 2：图构建与种子初始化
# ---------------------------------------------------------------------------
def build_graph_and_seed(data: TablebaseData,
                         sub_tb: Optional[Dict[int, tuple]] = None) -> deque:
    """
    建立状态间的前驱-后继关系图，并识别初始种子节点：
      - 困毙（无合法走法）节点
      - 一步吃入已知子库必胜的节点
    """
    print("[2/5] 构建状态图并识别种子节点...")
    t0 = time.time()

    queue = deque()
    total = data.size

    for idx in range(total):
        state = data.states[idx]
        ch = data.hashes[idx]

        # 收集合法走法
        legal_moves = []
        for r in range(5):
            for c in range(5):
                if state.board[r][c] == state.current_player:
                    for end_pos in state.get_valid_moves(r, c):
                        legal_moves.append(((r, c), end_pos))

        # 区分库内转移与跨库转移
        internal_count = 0
        has_sub_tb_win = False

        for start, end in legal_moves:
            nxt = state.move_piece(start[0], start[1], end[0], end[1])
            n_ch = nxt.get_canonical_hash()

            if n_ch in data.hash_to_idx:
                internal_count += 1
                child_idx = data.hash_to_idx[n_ch]
                data.parents[child_idx].append(idx)
            else:
                # 跨库转移：检查是否吃子进入已知胜利态
                if state.current_player == CANNON:
                    if sub_tb and n_ch in sub_tb:
                        if sub_tb[n_ch][0] == TB_CANNON_WIN:
                            has_sub_tb_win = True
                    elif nxt.soldier_count < state.soldier_count:
                        # 吃光最后一个兵，直接判定胜利
                        has_sub_tb_win = True

        data.children_count[idx] = len(legal_moves)
        data.unresolved[idx] = internal_count

        # 种子 A：困毙（无合法走法）
        if not legal_moves:
            if state.current_player == SOLDIER:
                data.values[idx] = TB_CANNON_WIN
            else:
                data.values[idx] = TB_SOLDIER_WIN
            data.dtms[idx] = 0
            data.unresolved[idx] = 0
            queue.append(idx)
            continue

        # 种子 B：一步吃入子库已知必胜
        if state.current_player == CANNON and has_sub_tb_win:
            data.values[idx] = TB_CANNON_WIN
            data.dtms[idx] = 1
            data.unresolved[idx] = 0
            queue.append(idx)

        # 进度报告
        if idx > 0 and idx % 500000 == 0:
            print(f"    进度: {idx}/{total} ({100 * idx / total:.1f}%)")

    elapsed = time.time() - t0
    print(f"    种子初始化完毕: {len(queue)} 个节点, 耗时 {elapsed:.2f}s")
    return queue


# ---------------------------------------------------------------------------
# 阶段 3：逆向推演
# ---------------------------------------------------------------------------
def retrograde_analysis(data: TablebaseData, queue: deque) -> None:
    """
    分层逆向推演。采用 BFS 波面推进，逐层确立每个局面的胜负及精确 DTM。

    核心逻辑：
      - 攻方存在一步使对手必败 -> 当前局面必胜（DTM 为奇数）
      - 守方所有走法均指向必败 -> 当前局面必败（DTM 为偶数）
    """
    print("[3/5] 逆向推演...")
    t0 = time.time()
    resolved = 0

    # 按 DTM 层分组
    layer_map = {}
    for idx in queue:
        dtm = data.dtms[idx]
        layer_map.setdefault(dtm, []).append(idx)

    current_dtm = 0

    while True:
        if current_dtm not in layer_map or not layer_map[current_dtm]:
            higher = [d for d in layer_map if d > current_dtm and layer_map[d]]
            if not higher:
                break
            current_dtm = min(higher)

        batch = layer_map[current_dtm]
        layer_map[current_dtm] = []

        for idx in batch:
            resolved += 1
            node_val = data.values[idx]

            for parent_idx in data.parents[idx]:
                if data.values[parent_idx] != TB_DRAW:
                    continue

                p_state = data.states[parent_idx]
                p_player = p_state.current_player
                p_win = TB_CANNON_WIN if p_player == CANNON else TB_SOLDIER_WIN
                p_loss = TB_SOLDIER_WIN if p_player == CANNON else TB_CANNON_WIN

                if node_val == p_win:
                    # 路径 A：攻方发现一步必胜
                    new_dtm = current_dtm + 1
                    data.values[parent_idx] = p_win
                    data.dtms[parent_idx] = new_dtm
                    data.unresolved[parent_idx] = 0
                    layer_map.setdefault(new_dtm, []).append(parent_idx)

                elif node_val == p_loss:
                    # 路径 B：守方的一条退路被封堵
                    data.unresolved[parent_idx] -= 1
                    data.dtms[parent_idx] = max(data.dtms[parent_idx], current_dtm + 1)

                    if data.unresolved[parent_idx] == 0:
                        data.values[parent_idx] = p_loss
                        layer_map.setdefault(data.dtms[parent_idx], []).append(parent_idx)

        current_dtm += 1

    elapsed = time.time() - t0
    draws = data.size - resolved
    print(f"    推演结束: 解决 {resolved} 个节点, 平局 {draws} 个, 耗时 {elapsed:.2f}s")


# ---------------------------------------------------------------------------
# 阶段 4（可选）：CTI 值迭代
# ---------------------------------------------------------------------------
def calculate_cti(data: TablebaseData, gamma: float = 0.95,
                  epsilon: float = 1e-5) -> None:
    """
    为平局空间计算 CTI（累积高压指数）。
    使用 MDP 值迭代算法，量化和棋局面下攻击方的施压优势。
    """
    print("[4/5] CTI 值迭代...")
    t0 = time.time()

    # 提取平局子图
    draw_indices = [i for i in range(data.size) if data.values[i] == TB_DRAW]

    draw_graph = {}
    PENALTY = 99.0

    for idx in draw_indices:
        state = data.states[idx]
        player = state.current_player
        total_moves = 0
        draw_children = []
        material_loss = 0

        for r in range(5):
            for c in range(5):
                if state.board[r][c] == player:
                    for end in state.get_valid_moves(r, c):
                        total_moves += 1
                        nxt = state.move_piece(r, c, end[0], end[1])
                        n_ch = nxt.get_canonical_hash()
                        child_idx = data.hash_to_idx.get(n_ch)

                        if child_idx is not None:
                            if data.values[child_idx] == TB_DRAW:
                                draw_children.append(child_idx)
                        else:
                            if nxt.soldier_count < state.soldier_count:
                                material_loss += 1

        draw_graph[idx] = (player, total_moves, draw_children, material_loss)

    print(f"    平局子图: {len(draw_graph)} 个节点")

    # 值迭代
    iteration = 0
    while True:
        max_delta = 0.0

        for idx, (player, total_moves, draw_children, loss_moves) in draw_graph.items():
            if total_moves == 0:
                continue

            old_cti = data.ctis[idx]
            children_ctis = [data.ctis[ci] for ci in draw_children]
            k = len(draw_children)

            if player == CANNON:
                if loss_moves > 0:
                    new_cti = PENALTY
                elif children_ctis:
                    new_cti = max(children_ctis)
                else:
                    new_cti = 0.0
            else:
                game_loss = max(0, total_moves - k - loss_moves)
                instant_risk = (game_loss * 1.0 + loss_moves * PENALTY) / total_moves
                min_future = min(children_ctis) if children_ctis else 0.0
                new_cti = instant_risk + gamma * min_future

            data.ctis[idx] = new_cti
            delta = abs(new_cti - old_cti)
            if delta > max_delta:
                max_delta = delta

        iteration += 1
        if iteration % 20 == 0:
            print(f"    迭代 {iteration}, 残差: {max_delta:.6f}")

        if max_delta < epsilon:
            break

    elapsed = time.time() - t0
    print(f"    CTI 收敛, 迭代 {iteration} 次, 耗时 {elapsed:.2f}s")


# ---------------------------------------------------------------------------
# 阶段 5：导出
# ---------------------------------------------------------------------------
def export_pickle(data: TablebaseData, filepath: str) -> None:
    """导出为 pickle 格式，兼容现有 tb_solver.py。"""
    export = {}
    for idx in range(data.size):
        h = data.hashes[idx]
        v = data.values[idx]
        d = data.dtms[idx] if v != TB_DRAW else 0
        c = round(data.ctis[idx], 4) if v == TB_DRAW else 0.0
        export[h] = (v, d, c)

    with open(filepath, 'wb') as f:
        pickle.dump(export, f, protocol=pickle.HIGHEST_PROTOCOL)

    print(f"    pickle: {filepath} ({os.path.getsize(filepath) / 1024 / 1024:.2f} MB)")


def export_binary(data: TablebaseData, filepath: str,
                  cannon_num: int, soldier_num: int) -> None:
    """
    导出为紧凑二进制格式 + zlib 压缩。

    文件结构:
      Header (固定 24 字节):
        - magic:     5 bytes  ('TC_TB')
        - version:   1 byte
        - cannons:   1 byte
        - soldiers:  1 byte
        - count:     4 bytes  (uint32, 记录总数)
        - reserved: 12 bytes

      Body (zlib 压缩):
        每条记录 13 字节:
          - canonical_hash: 8 bytes (uint64)
          - wdl:            1 byte  (uint8, 0=兵胜 1=和棋 2=炮胜)
          - dtm:            2 bytes (int16)
          - cti:            2 bytes (int16, 实际值 * 100 取整)
    """
    count = data.size
    record_fmt = '<QBhh'  # 8 + 1 + 2 + 2 = 13 bytes
    record_size = struct.calcsize(record_fmt)

    # 序列化记录
    buf = bytearray(count * record_size)
    offset = 0
    for idx in range(count):
        h = data.hashes[idx]
        v = data.values[idx]
        wdl = WDL_ENCODE[v]
        dtm = data.dtms[idx] if v != TB_DRAW else 0
        cti_raw = data.ctis[idx] if v == TB_DRAW else 0.0
        cti_int = max(-32768, min(32767, int(round(cti_raw * 100))))
        struct.pack_into(record_fmt, buf, offset, h, wdl, dtm, cti_int)
        offset += record_size

    compressed = zlib.compress(bytes(buf), level=6)

    # 写入文件
    with open(filepath, 'wb') as f:
        # Header
        f.write(TB_MAGIC)                                  # 5 bytes
        f.write(struct.pack('<B', TB_VERSION))              # 1 byte
        f.write(struct.pack('<B', cannon_num))              # 1 byte
        f.write(struct.pack('<B', soldier_num))             # 1 byte
        f.write(struct.pack('<I', count))                   # 4 bytes
        f.write(b'\x00' * 12)                              # 12 bytes reserved
        # Body
        f.write(compressed)

    raw_size = count * record_size
    file_size = os.path.getsize(filepath)
    ratio = (1 - file_size / raw_size) * 100 if raw_size > 0 else 0
    print(f"    binary: {filepath} ({file_size / 1024 / 1024:.2f} MB, "
          f"压缩率 {ratio:.1f}%)")


def export_csv(data: TablebaseData, filepath: str) -> None:
    """导出为人可读 CSV 格式。"""
    with open(filepath, 'w', newline='', encoding='utf-8') as f:
        writer = csv_module.writer(f)
        writer.writerow(['fen', 'wdl', 'dtm', 'cti', 'turn', 'canonical_hash'])

        for idx in range(data.size):
            state = data.states[idx]
            v = data.values[idx]
            fen = state.to_fen()
            wdl = WDL_LABEL[v]
            dtm = data.dtms[idx] if v != TB_DRAW else 0
            cti = round(data.ctis[idx], 4) if v == TB_DRAW else 0.0
            turn = 'c' if state.current_player == CANNON else 's'
            ch = data.hashes[idx]
            writer.writerow([fen, wdl, dtm, cti, turn, ch])

    print(f"    csv: {filepath} ({os.path.getsize(filepath) / 1024 / 1024:.2f} MB)")


def export_all(data: TablebaseData, cannon_num: int, soldier_num: int,
               output_dir: str, formats: List[str]) -> None:
    """按指定格式导出残局库。"""
    print("[5/5] 导出残局库...")

    # 统计概览
    c_win = s_win = draw = 0
    for idx in range(data.size):
        v = data.values[idx]
        if v == TB_CANNON_WIN:
            c_win += 1
        elif v == TB_SOLDIER_WIN:
            s_win += 1
        else:
            draw += 1

    print(f"    统计: 炮胜 {c_win}, 兵胜 {s_win}, 和棋 {draw}")

    os.makedirs(output_dir, exist_ok=True)
    base = f'tb_c{cannon_num}_s{soldier_num}'

    for fmt in formats:
        if fmt == 'pickle':
            export_pickle(data, os.path.join(output_dir, f'{base}.pkl'))
        elif fmt == 'binary':
            export_binary(data, os.path.join(output_dir, f'{base}.tb'),
                          cannon_num, soldier_num)
        elif fmt == 'csv':
            export_csv(data, os.path.join(output_dir, f'{base}.csv'))


# ---------------------------------------------------------------------------
# 子库加载
# ---------------------------------------------------------------------------
def load_sub_tablebase(cannon_num: int, soldier_num: int,
                       data_dir: str) -> Optional[Dict[int, tuple]]:
    """
    加载下一级子库（兵数少一个）作为跨库种子依据。
    支持 pickle 和 binary 两种格式。
    """
    # 优先尝试 pickle
    pkl_path = os.path.join(data_dir, f'tb_c{cannon_num}_s{soldier_num}.pkl')
    if os.path.exists(pkl_path):
        with open(pkl_path, 'rb') as f:
            sub = pickle.load(f)
        print(f"    子库已加载: {pkl_path} ({len(sub)} 个节点)")
        return sub

    # 尝试 binary
    tb_path = os.path.join(data_dir, f'tb_c{cannon_num}_s{soldier_num}.tb')
    if os.path.exists(tb_path):
        sub = load_binary_as_dict(tb_path)
        print(f"    子库已加载: {tb_path} ({len(sub)} 个节点)")
        return sub

    return None


def load_binary_as_dict(filepath: str) -> Dict[int, tuple]:
    """从 binary 格式加载残局库并转换为 {hash: (val, dtm, cti)} 字典。"""
    result = {}
    with open(filepath, 'rb') as f:
        magic = f.read(5)
        if magic != TB_MAGIC:
            raise ValueError(f"无效的文件魔数: {magic}")

        version = struct.unpack('<B', f.read(1))[0]
        _cannons = struct.unpack('<B', f.read(1))[0]
        _soldiers = struct.unpack('<B', f.read(1))[0]
        count = struct.unpack('<I', f.read(4))[0]
        f.read(12)  # reserved

        compressed = f.read()

    raw = zlib.decompress(compressed)
    record_fmt = '<QBhh'
    record_size = struct.calcsize(record_fmt)

    for i in range(count):
        offset = i * record_size
        h, wdl, dtm, cti_int = struct.unpack_from(record_fmt, raw, offset)
        val = WDL_DECODE[wdl]
        cti = cti_int / 100.0
        result[h] = (val, dtm, cti)

    return result


# ---------------------------------------------------------------------------
# 主流程
# ---------------------------------------------------------------------------
def build_tablebase(cannon_num: int, soldier_num: int,
                    output_dir: str, formats: List[str],
                    enable_cti: bool = False,
                    gamma: float = 0.95) -> TablebaseData:
    """
    完整的残局库构建流水线。
    """
    print(f"\n{'=' * 60}")
    print(f"构建残局库: {cannon_num}炮 vs {soldier_num}兵")
    print(f"{'=' * 60}")

    # 加载子库
    sub_tb = None
    if soldier_num > 1:
        sub_tb = load_sub_tablebase(cannon_num, soldier_num - 1, output_dir)
        if sub_tb is None:
            print("    子库不可用，使用独立生成模式")

    # 阶段 1：枚举
    data = enumerate_states(cannon_num, soldier_num)

    # 阶段 2：图构建 + 种子
    queue = build_graph_and_seed(data, sub_tb=sub_tb)

    # 阶段 3：逆向推演
    retrograde_analysis(data, queue)

    # 阶段 4：CTI（可选）
    if enable_cti:
        calculate_cti(data, gamma=gamma)
    else:
        print("[4/5] CTI 计算已跳过（使用 --cti 启用）")

    # 阶段 5：导出
    export_all(data, cannon_num, soldier_num, output_dir, formats)

    return data


def parse_soldier_range(spec: str) -> List[int]:
    """
    解析兵数量参数。支持格式：
      - 单值: "4"
      - 范围: "1-4"（从低到高递增构建）
    """
    if '-' in spec:
        parts = spec.split('-')
        lo, hi = int(parts[0]), int(parts[1])
        return list(range(lo, hi + 1))
    return [int(spec)]


def main():
    parser = argparse.ArgumentParser(
        description='三炮十五兵 逆向推演残局库生成器',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  python generate_tablebase.py --cannons 3 --soldiers 1-4
  python generate_tablebase.py --cannons 2 --soldiers 3 --format pickle csv
  python generate_tablebase.py --cannons 3 --soldiers 5 --format binary --cti
        """)

    parser.add_argument('--cannons', type=int, default=3,
                        help='炮的数量（默认 3）')
    parser.add_argument('--soldiers', type=str, default='1',
                        help='兵的数量，支持单值或范围（如 "4" 或 "1-4"）')
    parser.add_argument('--format', nargs='+', default=['pickle'],
                        choices=['pickle', 'binary', 'csv'],
                        help='输出格式（默认 pickle）')
    parser.add_argument('--cti', action='store_true',
                        help='启用 CTI（累积高压指数）计算（默认关闭）')
    parser.add_argument('--gamma', type=float, default=0.95,
                        help='CTI 折扣因子（默认 0.95）')
    parser.add_argument('--output-dir', type=str, default=None,
                        help='输出目录（默认 data/tablebase）')

    args = parser.parse_args()

    # 默认输出目录
    if args.output_dir is None:
        root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        output_dir = os.path.join(root, 'data', 'tablebase')
    else:
        output_dir = args.output_dir

    soldier_range = parse_soldier_range(args.soldiers)

    print(f"任务配置: {args.cannons}炮, 兵数 {soldier_range}, "
          f"格式 {args.format}, CTI={'开' if args.cti else '关'}")

    t_total = time.time()

    # 从低子力向高子力递增构建
    for s_num in soldier_range:
        build_tablebase(
            cannon_num=args.cannons,
            soldier_num=s_num,
            output_dir=output_dir,
            formats=args.format,
            enable_cti=args.cti,
            gamma=args.gamma
        )

    elapsed = time.time() - t_total
    print(f"\n全部完成, 总耗时 {elapsed:.1f}s")


if __name__ == '__main__':
    main()