import pickle
import os
import sys
import itertools

# 保证能找到 core
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from core.game_logic import GameState

def find_samples(filename):
    path = os.path.join("data", "tablebase", filename)
    if not os.path.exists(path):
        print(f"File not found: {path}")
        return
        
    with open(path, 'rb') as f:
        tb = pickle.load(f)
    
    print(f"[*] 载入 {filename}, 状态数: {len(tb)}")
    
    cells = list(range(25))
    c_wins = []
    s_wins = []
    
    count = 0
    total_combos = 300 * 1771 # 25C2 * 23C3
    
    for cannon_pos in itertools.combinations(cells, 2):
        remaining = [c for c in cells if c not in cannon_pos]
        for soldier_pos in itertools.combinations(remaining, 3):
            count += 1
            if count % 50000 == 0:
                print(f"进度: {count}/{total_combos}...")
                
            board_1d = [0] * 25
            for p in cannon_pos: board_1d[p] = 2
            for p in soldier_pos: board_1d[p] = 1
            board_2d = [board_1d[i:i+5] for i in range(0, 25, 5)]
            
            for turn in [2, 1]:
                state = GameState(board_2d, turn)
                ch = state.get_canonical_hash()
                if ch in tb:
                    val, dtm = tb[ch]
                    if val == 1 and dtm >= 6:
                        if len(c_wins) < 5:
                            c_wins.append((state.to_fen(), dtm))
                    if val == -1:
                        if len(s_wins) < 5:
                            s_wins.append((state.to_fen(), dtm))
            
            if len(c_wins) >= 5 and len(s_wins) >= 5:
                break
        if len(c_wins) >= 5 and len(s_wins) >= 5:
            break

    print("\n--- 采样结果 ---")
    print("炮胜样例:")
    for fen, d in c_wins:
        print(f"  FEN: {fen} | DTM: {d}")
    print("兵胜样例:")
    for fen, d in s_wins:
        print(f"  FEN: {fen} | DTM: {d}")

if __name__ == "__main__":
    find_samples("tb_c2_s3.pkl")
