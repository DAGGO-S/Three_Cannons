import pickle
import os
import sys

# 保证能找到 core
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from core.game_logic import GameState, CANNON, SOLDIER

def debug_parity():
    path = "data/tablebase/tb_c2_s1.pkl"
    with open(path, 'rb') as f:
        tb = pickle.load(f)
        
    count = 0
    for h, (val, dtm) in tb.items():
        # 我们只关心炮胜的情况
        if val == 1:
            # 根据 FEN 判定玩家
            # 由于我们没存 FEN，我们需要从全集节点中找，或者逆向推导
            pass
            
    # 计划：直接遍历 nodes 字典（在生成器运行期间）
    print("Please run this logic inside generate_tablebase.py for access to nodes object.")

if __name__ == "__main__":
    # 我们直接修改 generate_tablebase.py 在末尾打印一些统计信息
    pass
