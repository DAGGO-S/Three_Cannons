import os
import sys

# 保证能找到 core
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from core.game_logic import GameState

def debug_fen(fen):
    state = GameState.from_fen(fen)
    print(f"FEN: {fen}")
    print(f"Current Player: {'CANNON' if state.current_player == 2 else 'SOLDIER'}")
    
    moves = []
    for r in range(5):
        for c in range(5):
            if state.board[r][c] == state.current_player:
                valid_ends = state.get_valid_moves(r, c)
                for end in valid_ends:
                    moves.append(((r, c), end))
    
    print(f"Legal Moves Count: {len(moves)}")
    for start, end in moves:
        print(f"  {start} -> {end}")
        
    print(f"Canonical Hash: {state.get_canonical_hash()}")

if __name__ == "__main__":
    debug_fen("5/2s2/1s1s1/1c1c1/5 c")
