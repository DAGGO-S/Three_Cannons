"""
闭环验证：export_as_jsonl 的 eval 和 game_outcome 字段的数据质量。
game_outcome 是回溯性标签，记录该局最终归属（与局面进行中否无关）。
"""
import sys
import os
import json
import tempfile
import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.game_logic import GameState, CANNON, SOLDIER
from src.io.game_io import export_as_jsonl


def _make_simple_history():
    """构造一个 3 步棋局历史：初始状态（炮方先手） + 炮走 + 兵走"""
    s0 = GameState()                    # current_player=CANNON
    s1 = s0.move_piece(4, 1, 3, 1)     # 炮方走
    s2 = s1.move_piece(2, 4, 3, 4)     # 兵 (2,4) 向下到第3行 (3,4)，兵方走
    return [s0, s1, s2]


class TestJSONLEvalQuality:
    def test_eval_is_not_hardcoded_zero(self):
        """eval 字段必须来自真实评估，不能固定为 0.0"""
        history = _make_simple_history()
        tmpfile = os.path.join(tempfile.gettempdir(), "test_eval_quality.jsonl")
        if os.path.exists(tmpfile):
            os.remove(tmpfile)

        export_as_jsonl(history, SOLDIER, tmpfile)

        with open(tmpfile, "r", encoding="utf-8") as f:
            rows = [json.loads(line) for line in f if line.strip()]

        assert len(rows) == 3
        eval_values = [row["eval"] for row in rows]
        assert any(v != 0.0 for v in eval_values), (
            f"所有 eval 均为 0.0，说明未调用真实评估函数。实际值: {eval_values}"
        )

    def test_game_outcome_reflects_winner(self):
        """game_outcome 必须正确反映最终胜者，与当前局面进行状态无关"""
        history = _make_simple_history()

        tmpfile_c = os.path.join(tempfile.gettempdir(), "test_outcome_c.jsonl")
        if os.path.exists(tmpfile_c):
            os.remove(tmpfile_c)
        export_as_jsonl(history, CANNON, tmpfile_c)
        with open(tmpfile_c) as f:
            rows = [json.loads(line) for line in f if line.strip()]
        assert all(row["game_outcome"] == 1.0 for row in rows), \
            "炮方赢时全局 game_outcome 应为 1.0"

        tmpfile_s = os.path.join(tempfile.gettempdir(), "test_outcome_s.jsonl")
        if os.path.exists(tmpfile_s):
            os.remove(tmpfile_s)
        export_as_jsonl(history, SOLDIER, tmpfile_s)
        with open(tmpfile_s) as f:
            rows = [json.loads(line) for line in f if line.strip()]
        assert all(row["game_outcome"] == 0.0 for row in rows), \
            "兵方赢时全局 game_outcome 应为 0.0"

    def test_no_legacy_result_field(self):
        """确保不再出现旧版 result 字段，字段名已统一为 game_outcome"""
        history = _make_simple_history()
        tmpfile = os.path.join(tempfile.gettempdir(), "test_no_legacy.jsonl")
        if os.path.exists(tmpfile):
            os.remove(tmpfile)

        export_as_jsonl(history, CANNON, tmpfile)
        with open(tmpfile) as f:
            rows = [json.loads(line) for line in f if line.strip()]

        for row in rows:
            assert "result" not in row, \
                f"发现旧版 result 字段，应已替换为 game_outcome: {row}"
            assert "game_outcome" in row, f"缺少 game_outcome 字段: {row}"

    def test_fen_round_trip_in_jsonl(self):
        """JSONL 中的 FEN 必须能反序列化回一致的棋盘状态"""
        history = _make_simple_history()
        tmpfile = os.path.join(tempfile.gettempdir(), "test_fen_rtrip.jsonl")
        if os.path.exists(tmpfile):
            os.remove(tmpfile)

        export_as_jsonl(history, SOLDIER, tmpfile)
        with open(tmpfile) as f:
            rows = [json.loads(line) for line in f if line.strip()]

        for i, (row, original_state) in enumerate(zip(rows, history)):
            recovered = GameState.from_fen(row["fen"])
            assert recovered.board == original_state.board, (
                f"第 {i} 步 FEN 往返不一致: {row['fen']}"
            )

    def test_autosave_file_schema_if_exists(self):
        """若 autosave 文件存在则自动采样验证字段结构，不依赖人工检查"""
        autosave_dir = os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            "data", "game_history", "auto_save"
        )
        if not os.path.isdir(autosave_dir):
            pytest.skip("autosave 目录不存在")

        jsonl_files = sorted(f for f in os.listdir(autosave_dir) if f.endswith(".jsonl"))
        if not jsonl_files:
            pytest.skip("没有 autosave 文件可检验")

        fpath = os.path.join(autosave_dir, jsonl_files[-1])
        with open(fpath, encoding="utf-8") as f:
            lines = [l.strip() for l in f if l.strip()]

        assert lines, f"{jsonl_files[-1]} 是空文件"

        for line in lines[:5]:
            row = json.loads(line)
            assert "fen" in row, "缺少 fen 字段"
            assert "eval" in row, "缺少 eval 字段"
            assert "game_outcome" in row, \
                f"缺少 game_outcome 字段（旧文件用 result，需重新落盘）: {row}"
            assert row["game_outcome"] in (0.0, 0.5, 1.0), \
                f"game_outcome 值非法: {row['game_outcome']}"
            assert row["eval"] != 0.0 or row["fen"].count("5") >= 3, \
                f"eval=0.0 但棋盘不为空，疑似未调用评估函数: {row}"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
