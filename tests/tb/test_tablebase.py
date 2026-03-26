"""
test_tablebase.py - 残局库生成器的自动化验证测试集

运行方式:
  python -m pytest tests/tb/test_tablebase.py -v
"""

import pytest
import os
import sys
import pickle
import struct
import zlib
import tempfile
import shutil

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from core.game_logic import GameState, CANNON, SOLDIER, EMPTY
from scripts.tb_analysis.generate_tablebase import (
    TablebaseData,
    enumerate_states,
    build_graph_and_seed,
    retrograde_analysis,
    calculate_cti,
    export_pickle,
    export_binary,
    export_csv,
    load_binary_as_dict,
    build_tablebase,
    TB_CANNON_WIN, TB_SOLDIER_WIN, TB_DRAW,
    TB_MAGIC, TB_VERSION,
    WDL_ENCODE, WDL_DECODE,
)


# ---------------------------------------------------------------------------
# 辅助函数
# ---------------------------------------------------------------------------
@pytest.fixture
def tmp_dir():
    """创建临时目录用于导出测试，测试结束后清理。"""
    d = tempfile.mkdtemp(prefix='tb_test_')
    yield d
    shutil.rmtree(d, ignore_errors=True)


def run_full_pipeline(cannon_num, soldier_num, enable_cti=False, sub_tb=None):
    """执行完整的推演流水线，返回 TablebaseData。"""
    data = enumerate_states(cannon_num, soldier_num)
    queue = build_graph_and_seed(data, sub_tb=sub_tb)
    retrograde_analysis(data, queue)
    if enable_cti:
        calculate_cti(data)
    return data


# ===========================================================================
# 测试类 1：状态空间枚举
# ===========================================================================
class TestEnumeration:
    """验证状态空间枚举的正确性。"""

    def test_c2_s1_node_count(self):
        """2炮1兵：验证去重后节点数量。"""
        data = enumerate_states(2, 1)
        # C(25,2) * C(23,1) * 2 = 13800，D4 对称压缩后约 1808
        assert data.size == 1808

    def test_c1_s1_node_count(self):
        """1炮1兵：最小子力，验证基础枚举。"""
        data = enumerate_states(1, 1)
        # C(25,1) * C(24,1) * 2 = 1200，压缩后应远少于此
        assert data.size > 0
        assert data.size < 1200

    def test_no_duplicate_hashes(self):
        """枚举结果中不存在哈希冲突。"""
        data = enumerate_states(2, 1)
        assert len(set(data.hashes)) == data.size

    def test_all_states_valid(self):
        """每个枚举出的 GameState 都包含正确数量的棋子。"""
        data = enumerate_states(2, 1)
        for idx in range(data.size):
            state = data.states[idx]
            board = state.board
            cannons = sum(row.count(CANNON) for row in board)
            soldiers = sum(row.count(SOLDIER) for row in board)
            assert cannons == 2, f"节点 {idx}: 炮数 {cannons} != 2"
            assert soldiers == 1, f"节点 {idx}: 兵数 {soldiers} != 1"


# ===========================================================================
# 测试类 2：逆向推演正确性
# ===========================================================================
class TestRetrograde:
    """验证逆向推演结果的逻辑一致性。"""

    def test_c2_s1_all_cannon_win(self):
        """2炮1兵：所有局面必须为炮胜（1兵无法困住2炮）。"""
        data = run_full_pipeline(2, 1)
        for idx in range(data.size):
            assert data.values[idx] == TB_CANNON_WIN, \
                f"节点 {idx} 应为炮胜, 实际 {data.values[idx]}"

    def test_c2_s1_no_draw(self):
        """2炮1兵：不存在和棋局面。"""
        data = run_full_pipeline(2, 1)
        draws = sum(1 for v in data.values if v == TB_DRAW)
        assert draws == 0

    def test_c1_s1_no_soldier_win(self):
        """1炮1兵：1个兵无法围困1个炮，故不存在兵胜局面。"""
        data = run_full_pipeline(1, 1)
        soldier_wins = sum(1 for v in data.values if v == TB_SOLDIER_WIN)
        cannon_wins = sum(1 for v in data.values if v == TB_CANNON_WIN)
        draws = sum(1 for v in data.values if v == TB_DRAW)
        assert soldier_wins == 0, f"1炮1兵不应存在兵胜, 实际 {soldier_wins}"
        assert cannon_wins > 0, "应存在炮胜局面（兵处于无法逃脱的位置）"
        assert draws > 0, "应存在和棋局面（兵可持续回避炮的捕获）"

    def test_dtm_non_negative(self):
        """所有 DTM 值必须非负。"""
        data = run_full_pipeline(2, 1)
        for idx in range(data.size):
            assert data.dtms[idx] >= 0

    def test_dtm_zero_for_terminal(self):
        """困毙局面（终端节点）的 DTM 必须为 0。"""
        data = run_full_pipeline(2, 1)
        for idx in range(data.size):
            state = data.states[idx]
            has_moves = False
            for r in range(5):
                for c in range(5):
                    if state.board[r][c] == state.current_player:
                        if state.get_valid_moves(r, c):
                            has_moves = True
                            break
                if has_moves:
                    break
            if not has_moves:
                assert data.dtms[idx] == 0, \
                    f"终端节点 {idx} DTM 应为 0, 实际 {data.dtms[idx]}"

    def test_dtm_parity(self):
        """
        DTM 奇偶性校验：
          - 必胜局面的 DTM 为奇数（或 0/1 的种子节点）
          - 必败局面的 DTM 为偶数（或 0 的种子节点）
        注意：DTM=0 的困毙节点和 DTM=1 的吃子种子是特殊情况。
        """
        data = run_full_pipeline(2, 2)
        for idx in range(data.size):
            v = data.values[idx]
            dtm = data.dtms[idx]
            if dtm == 0:
                continue  # 终端种子节点不受奇偶约束
            state = data.states[idx]
            player = state.current_player
            if player == CANNON:
                if v == TB_CANNON_WIN:
                    # 炮走，炮胜 = 攻方必胜，DTM 应为奇数
                    assert dtm % 2 == 1, \
                        f"节点 {idx}: 炮攻炮胜 DTM={dtm} 应为奇数"
                elif v == TB_SOLDIER_WIN:
                    # 炮走，兵胜 = 守方必败，DTM 应为偶数
                    assert dtm % 2 == 0, \
                        f"节点 {idx}: 炮守兵胜 DTM={dtm} 应为偶数"
            else:
                if v == TB_SOLDIER_WIN:
                    # 兵走，兵胜 = 攻方必胜，DTM 应为奇数
                    assert dtm % 2 == 1, \
                        f"节点 {idx}: 兵攻兵胜 DTM={dtm} 应为奇数"
                elif v == TB_CANNON_WIN:
                    # 兵走，炮胜 = 守方必败，DTM 应为偶数
                    assert dtm % 2 == 0, \
                        f"节点 {idx}: 兵守炮胜 DTM={dtm} 应为偶数"


# ===========================================================================
# 测试类 3：已知局面验证
# ===========================================================================
class TestKnownPositions:
    """通过特定 FEN 局面验证推演结果。"""

    def test_single_soldier_cornered(self):
        """1兵被困在角落，炮在旁边：应为炮胜。"""
        fen = "s4/c4/c3/5/5 c"
        state = GameState.from_fen(fen)
        data = run_full_pipeline(2, 1)

        ch = state.get_canonical_hash()
        if ch in data.hash_to_idx:
            idx = data.hash_to_idx[ch]
            assert data.values[idx] == TB_CANNON_WIN

    def test_cannon_surrounded_c2_s2(self):
        """2炮2兵局面：验证存在兵胜或和棋的可能。"""
        data = run_full_pipeline(2, 2)
        has_soldier_win = any(v == TB_SOLDIER_WIN for v in data.values)
        has_draw = any(v == TB_DRAW for v in data.values)
        # 2炮2兵中应存在兵胜局面（兵可以困住炮）
        assert has_soldier_win or has_draw, "2炮2兵未产生非炮胜节点"


# ===========================================================================
# 测试类 4：导出与加载
# ===========================================================================
class TestExport:
    """验证各种导出格式的正确性。"""

    def test_pickle_roundtrip(self, tmp_dir):
        """pickle 导出后重新加载，数据一致。"""
        data = run_full_pipeline(2, 1)
        filepath = os.path.join(tmp_dir, 'test.pkl')
        export_pickle(data, filepath)

        with open(filepath, 'rb') as f:
            loaded = pickle.load(f)

        assert len(loaded) == data.size
        for idx in range(data.size):
            h = data.hashes[idx]
            assert h in loaded
            val, dtm, cti = loaded[h]
            assert val == data.values[idx]
            if val != TB_DRAW:
                assert dtm == data.dtms[idx]

    def test_pickle_compatible_with_solver(self, tmp_dir):
        """pickle 格式兼容 tb_solver.py 的 (val, dtm, cti) 三元组。"""
        data = run_full_pipeline(1, 1)
        filepath = os.path.join(tmp_dir, 'compat.pkl')
        export_pickle(data, filepath)

        with open(filepath, 'rb') as f:
            loaded = pickle.load(f)

        for h, entry in loaded.items():
            assert isinstance(entry, tuple)
            assert len(entry) == 3
            val, dtm, cti = entry
            assert val in (TB_CANNON_WIN, TB_SOLDIER_WIN, TB_DRAW)
            assert isinstance(dtm, int)
            assert isinstance(cti, float)

    def test_binary_roundtrip(self, tmp_dir):
        """binary 导出后加载，数据一致。"""
        data = run_full_pipeline(2, 1)
        filepath = os.path.join(tmp_dir, 'test.tb')
        export_binary(data, filepath, 2, 1)

        loaded = load_binary_as_dict(filepath)

        assert len(loaded) == data.size
        for idx in range(data.size):
            h = data.hashes[idx]
            assert h in loaded
            val, dtm, cti = loaded[h]
            assert val == data.values[idx]
            if val != TB_DRAW:
                assert dtm == data.dtms[idx]

    def test_binary_header(self, tmp_dir):
        """binary 文件头格式正确。"""
        data = run_full_pipeline(1, 1)
        filepath = os.path.join(tmp_dir, 'header.tb')
        export_binary(data, filepath, 1, 1)

        with open(filepath, 'rb') as f:
            magic = f.read(5)
            version = struct.unpack('<B', f.read(1))[0]
            cannons = struct.unpack('<B', f.read(1))[0]
            soldiers = struct.unpack('<B', f.read(1))[0]
            count = struct.unpack('<I', f.read(4))[0]

        assert magic == TB_MAGIC
        assert version == TB_VERSION
        assert cannons == 1
        assert soldiers == 1
        assert count == data.size

    def test_binary_smaller_than_pickle(self, tmp_dir):
        """binary 格式文件应小于 pickle 格式。"""
        data = run_full_pipeline(2, 1)
        pkl_path = os.path.join(tmp_dir, 'cmp.pkl')
        tb_path = os.path.join(tmp_dir, 'cmp.tb')
        export_pickle(data, pkl_path)
        export_binary(data, tb_path, 2, 1)

        pkl_size = os.path.getsize(pkl_path)
        tb_size = os.path.getsize(tb_path)
        assert tb_size < pkl_size, \
            f"binary({tb_size}) 应小于 pickle({pkl_size})"

    def test_csv_output(self, tmp_dir):
        """CSV 导出格式正确，可被重新解析。"""
        data = run_full_pipeline(1, 1)
        filepath = os.path.join(tmp_dir, 'test.csv')
        export_csv(data, filepath)

        import csv
        with open(filepath, 'r', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            rows = list(reader)

        assert len(rows) == data.size
        # 检查列名
        assert set(rows[0].keys()) == {'fen', 'wdl', 'dtm', 'cti', 'turn', 'canonical_hash'}
        # 检查 FEN 可还原
        for row in rows[:10]:
            state = GameState.from_fen(row['fen'])
            assert state is not None
            assert row['wdl'] in ('win', 'lose', 'draw')
            assert row['turn'] in ('c', 's')


# ===========================================================================
# 测试类 5：子库链接
# ===========================================================================
class TestSubTablebase:
    """验证分层构建的子库链接功能。"""

    def test_sub_tb_seed(self, tmp_dir):
        """先构建 c2_s1，再构建 c2_s2 时自动链接子库。"""
        # 构建子库
        data_s1 = run_full_pipeline(2, 1)
        pkl_path = os.path.join(tmp_dir, 'tb_c2_s1.pkl')
        export_pickle(data_s1, pkl_path)

        # 加载子库
        with open(pkl_path, 'rb') as f:
            sub_tb = pickle.load(f)

        # 构建 c2_s2 并链接子库
        data_s2 = enumerate_states(2, 2)
        queue = build_graph_and_seed(data_s2, sub_tb=sub_tb)

        # 种子中应包含通过子库识别的吃子必胜节点
        seed_count = len(queue)
        assert seed_count > 0, "链接子库后应产生种子节点"


# ===========================================================================
# 测试类 6：与已有库文件对比
# ===========================================================================
class TestRegressionAgainstExisting:
    """
    回归测试：与已有的残局库 pkl 文件对比，确保新代码产出一致的结果。
    如果库文件不存在则跳过。
    """

    @pytest.fixture
    def existing_tb_dir(self):
        root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        return os.path.join(root, 'data', 'tablebase')

    def _compare_with_existing(self, cannon_num, soldier_num, existing_dir):
        """通用对比逻辑。"""
        pkl_path = os.path.join(existing_dir, f'tb_c{cannon_num}_s{soldier_num}.pkl')
        if not os.path.exists(pkl_path):
            pytest.skip(f"{pkl_path} 不存在")

        with open(pkl_path, 'rb') as f:
            existing = pickle.load(f)

        # 重新生成（无 CTI）
        data = run_full_pipeline(cannon_num, soldier_num)

        # 对比节点数
        assert data.size == len(existing), \
            f"节点数不一致: 新 {data.size} vs 旧 {len(existing)}"

        # 对比每个节点的 val 和 dtm
        mismatches = []
        for idx in range(data.size):
            h = data.hashes[idx]
            if h not in existing:
                mismatches.append(f"哈希 {h} 在旧库中不存在")
                continue
            old_val, old_dtm, old_cti = existing[h]
            new_val = data.values[idx]
            new_dtm = data.dtms[idx] if new_val != TB_DRAW else 0
            if new_val != old_val:
                mismatches.append(f"哈希 {h}: val 新={new_val} 旧={old_val}")
            elif new_dtm != old_dtm:
                mismatches.append(f"哈希 {h}: dtm 新={new_dtm} 旧={old_dtm}")

        assert not mismatches, \
            f"发现 {len(mismatches)} 处不一致:\n" + "\n".join(mismatches[:20])

    def test_regression_c2_s1(self, existing_tb_dir):
        self._compare_with_existing(2, 1, existing_tb_dir)

    def test_regression_c2_s2(self, existing_tb_dir):
        self._compare_with_existing(2, 2, existing_tb_dir)

    def test_regression_c3_s1(self, existing_tb_dir):
        self._compare_with_existing(3, 1, existing_tb_dir)

    def test_regression_c3_s2(self, existing_tb_dir):
        self._compare_with_existing(3, 2, existing_tb_dir)
