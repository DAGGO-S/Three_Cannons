import pickle
import os
import sys

# 保证能找到 core
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
from core.game_logic import GameState

def check_fen(fen, tb_file):
    state = GameState.from_fen(fen)
    h = state.get_canonical_hash()
    
    path = os.path.join("data", "tablebase", tb_file)
    if not os.path.exists(path):
        print(f"File not found: {path}")
        return
        
    with open(path, 'rb') as f:
        tb = pickle.load(f)
        
    print(f"FEN: {fen}")
    print(f"Canonical Hash: {h}")
    if h in tb:
        val, dtm = tb[h]
        print(f"Result in {tb_file}: Value={val}, DTM={dtm}")
        if val == 0:
            print("Status: DRAW (or not resolved yet)")
        elif val == 1:
            print("Status: CANNON WIN")
        elif val == -1:
            print("Status: SOLDIER WIN")
    else:
        print(f"Result in {tb_file}: NOT FOUND")

if __name__ == "__main__":
    check_fen("5/2s2/1s1s1/3c1/1c3 s", "tb_c2_s3.pkl")
