import pytest
from core.game_logic import GameState, CANNON, SOLDIER

class TestFENSupport:
    """微观测试防线第一关：FEN 互转的绝对闭环验证"""

    def test_fen_initial_board(self):
        # 测试三炮十五兵标准开盘图，小写为规范编码
        fen = "sssss/sssss/sssss/5/c1c1c s"
        state = GameState.from_fen(fen)
        
        assert state.current_player == SOLDIER
        assert state.soldier_count == 15
        
        # 反向序列化
        assert state.to_fen() == fen

    def test_fen_midgame(self):
        # 稀疏残局：只有三个兵和两个炮，小写为规范编码
        fen = "s4/1s3/4s/1c3/4c c"
        state = GameState.from_fen(fen)
        
        assert state.current_player == CANNON
        assert state.soldier_count == 3
        assert state.to_fen() == fen

    def test_fen_invalid_format(self):
        with pytest.raises(ValueError, match="Invalid FEN format"):
            GameState.from_fen("invalid_fen")



    def test_fen_invalid_character(self):
        with pytest.raises(ValueError, match="Invalid FEN character"):
            GameState.from_fen("sssss/x/sssss/5/c1c1c s")

    def test_baseline_eval(self):
        """
        [保护网纪律]: 这是 2026/03/10 在消除 set() 和 BFS 之前提取的，原版原生算法计算出的绝对估分。
        下面每一条重构（即使全部换成位级运算），都必须保证这些特定 FEN 下的分数一丝不苟地对齐。
        """
        from core.evaluation_logic import evaluate_board
        from src.model.config import GameConfig
        
        config = GameConfig().data
        
        # 提取真正的打分数字 (兼容返回 tuple 的情况)
        def get_score(fen):
            state = GameState.from_fen(fen)
            res = evaluate_board(state, config)
            return res[0] if isinstance(res, tuple) else res
            
        assert get_score("SSSSS/SSSSS/SSSSS/5/C1C1C S") == -525, "开局标准阵分值漂移"
        assert get_score("5/5/2C2/5/5 C") == 10000, "单炮空旷阵没有被正确识别为满分 (或未死局)"
        assert get_score("5/1SSS1/1SCS1/1SSS1/5 C") == -10000, "兵墙合围阵未被正确识别为死棋极小值"
        assert get_score("5/5/5/5/2C2 S") == 10000, "底线炮未触发极大得分"
        assert get_score("SSSSS/SSSSS/1S1S1/5/2C2 C") == -830, "兵海炮少被困阵分值漂移"
