import pickle
import os
import sys

# 保证能找到 core
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from core.game_logic import GameState, CANNON, SOLDIER

def analyze_pressure(fen, tb_file):
    state = GameState.from_fen(fen)
    root = os.getcwd()
    path = os.path.join(root, "data", "tablebase", tb_file)
    
    with open(path, 'rb') as f:
        tb = pickle.load(f)
        
    print(f"[*] 分析 FEN: {fen}")
    print(f"[*] 当前玩家: {'炮' if state.current_player == CANNON else '兵'}")
    
    # 1. 获取库中本方价值
    h = state.get_canonical_hash()
    val, dtm = tb.get(h, (0, 0))
    if val != 0:
        print(f"[!] 注意: 此局面在库中并非理论和棋 (Val={val}, DTM={dtm})")
    
    # 2. 遍历本方合法走法
    moves = []
    for r in range(5):
        for c in range(5):
            if state.board[r][c] == state.current_player:
                for end in state.get_valid_moves(r, c):
                    moves.append(((r,c), end))
                    
    results = []
    for start, end in moves:
        nxt = state.move_piece(start[0], start[1], end[0], end[1])
        nh = nxt.get_canonical_hash()
        n_val, n_dtm = tb.get(nh, (0, 0))
        
        # 只关注维持和棋的走法 (或者胜势走法)
        if n_val != 0 and n_val != val: 
            # 如果走入了一个必败分支，直接忽略（除非没有和棋分支）
            continue
            
        # 3. 计算对手的压力：统计对手的下一个动作
        opp_moves = []
        for r in range(5):
            for c in range(5):
                if nxt.board[r][c] == nxt.current_player:
                    for e in nxt.get_valid_moves(r, c):
                        opp_moves.append(((r,c), e))
        
        draw_count = 0
        loss_count = 0 # 对对手来说是 Loss，对我来说是 Win
        win_count = 0  # 对对手来说是 Win，对我来说是 Loss
        
        for os_pos, oe_pos in opp_moves:
            onn = nxt.move_piece(os_pos[0], os_pos[1], oe_pos[0], oe_pos[1])
            # 处理吃子带来的子库跳转
            if onn.soldier_count < nxt.soldier_count:
                sub_file = f"tb_c2_s{onn.soldier_count}.pkl"
                sub_path = os.path.join(root, "data", "tablebase", sub_file)
                if os.path.exists(sub_path):
                    with open(sub_path, 'rb') as f:
                        sub_tb = pickle.load(f)
                    onnh = onn.get_canonical_hash()
                    nv, _ = sub_tb.get(onnh, (0, 0))
                else:
                    nv = 1 # 假设吃完兵赢了 (针对 2C0S)
            else:
                onnh = onn.get_canonical_hash()
                nv, _ = tb.get(onnh, (0, 0))
            
            # 站在对手角度判定
            if nv == 0: draw_count += 1
            elif (nxt.current_player == CANNON and nv == 1) or (nxt.current_player == SOLDIER and nv == -1):
                win_count += 1
            else:
                loss_count += 1
        
        total = draw_count + loss_count + win_count
        pressure = (loss_count / total * 100) if total > 0 else 0
        
        results.append({
            'move': (start, end),
            'fen': nxt.to_fen(),
            'draws': draw_count,
            'losses': loss_count,
            'wins': win_count,
            'pressure': pressure
        })
        
    # 按压力降序排列
    results.sort(key=lambda x: x['pressure'], reverse=True)
    
    print("\n[候选走法分析]")
    for i, r in enumerate(results):
        mark = " (CURRENT CHOICE)" if i == 0 else ""
        print(f"{i+1}. {r['move']} -> Pressure: {r['pressure']:.1f}% | Opponent: {r['draws']} Draws, {r['losses']} Blunders, {r['wins']} Sure-Wins{mark}")
        print(f"   Next FEN: {r['fen']}")

if __name__ == "__main__":
    analyze_pressure("5/2s2/1s1s1/1c1c1/5 c", "tb_c2_s3.pkl")
