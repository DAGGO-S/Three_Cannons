import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from core.game_logic import GameState
from core.evaluation_logic import evaluate_board
from src.model.config import GameConfig

def main():
    print("="*50)
    print("提取微观残局基线打分 (Baseline Scores)")
    print("="*50)
    
    # 获取默认打分配置
    config = GameConfig()
    
    # 定义测试的极限阵型
    test_cases = [
        ("开局标准阵", "SSSSS/SSSSS/SSSSS/5/C1C1C S"),
        ("单炮空旷阵", "5/5/2C2/5/5 C"),               # 炮在中央，视野全开
        ("兵墙合围阵", "5/1SSS1/1SCS1/1SSS1/5 C"),     # 炮被8个方向的兵彻底包围
        ("底线击杀阵", "5/5/5/5/2C2 S"),               # 炮在底中央，兵方可能面临贴底威胁
        ("兵海炮少", "SSSSS/SSSSS/1S1S1/5/2C2 C"),     # 绝对劣势
    ]
    
    for name, fen in test_cases:
        state = GameState.from_fen(fen)
        score_tuple = evaluate_board(state, config.data)
        # score_tuple 可能是由纯 C 评估返回的 (int, dict) 结构
        score = score_tuple[0] if isinstance(score_tuple, tuple) else score_tuple
        print(f"[{name}] FEN: {fen}")
        print(f" -> 原始估分: {score}")
        print("-" * 50)

if __name__ == "__main__":
    main()
