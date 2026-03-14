import pickle
import os
import sys

# 保证能找到 core
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from core.game_logic import GameState, CANNON, SOLDIER, EMPTY

def print_board(state):
    piece_map = {EMPTY: ".", SOLDIER: "S", CANNON: "C"}
    print("\n   0 1 2 3 4")
    print("  ----------")
    for r in range(5):
        row_str = f"{r}| "
        for c in range(5):
            p = state.board[r][c]
            row_str += piece_map[p] + " "
        print(row_str)
    print(f"\nTurn: {'Cannon (炮)' if state.current_player == CANNON else 'Soldier (兵)'}")
    print(f"FEN: {state.to_fen()}")

# 全局库缓存
TB_CACHE = {}

def get_tb(s_num):
    if s_num in TB_CACHE: return TB_CACHE[s_num]
    filename = f"tb_c2_s{s_num}.pkl"
    path = os.path.join("data", "tablebase", filename)
    if not os.path.exists(path): return None
    print(f"[*] 加载库: {filename}")
    with open(path, 'rb') as f:
        TB_CACHE[s_num] = pickle.load(f)
    return TB_CACHE[s_num]

def probe_tb(state):
    tb = get_tb(state.soldier_count)
    if not tb: return None
    h = state.get_canonical_hash()
    # 接收三个返回值：胜负(val), 离杀步数(dtm), 累积高压指数(cti)
    return tb.get(h, (0, 0, 0.0))

def get_best_move(state):
    val, dtm, cti = probe_tb(state)
    current_ai = state.current_player
    
    # 获取所有合法走法
    moves =[]
    for r in range(5):
        for c in range(5):
            if state.board[r][c] == current_ai:
                for end in state.get_valid_moves(r, c):
                    moves.append(((r, c), end))
    
    results =[]
    for start, end in moves:
        nxt = state.move_piece(start[0], start[1], end[0], end[1])
        if nxt.winner == current_ai: return nxt, 0, "绝杀"
        
        # 正确接收三个返回值
        n_val, n_dtm, n_cti = probe_tb(nxt)
        
        is_winning = (current_ai == CANNON and n_val == 1) or \
                     (current_ai == SOLDIER and n_val == -1)
        
        is_draw = (n_val == 0)
        
        results.append({
            'state': nxt,
            'val': n_val,
            'dtm': n_dtm,
            'cti': n_cti,       # 将 CTI 记录下来
            'winning': is_winning,
            'draw': is_draw
        })

    # 1. 优先选 DTM 最小的必胜路径
    wins =[r for r in results if r['winning']]
    if wins:
        best = min(wins, key=lambda x: x['dtm'])
        return best['state'], best['dtm'], "必胜"

    # 2. 和棋：利用残局库预处理的 CTI 进行上帝视角挤压
    draws = [r for r in results if r['draw']]
    if draws:
        # CTI 是“兵方面临的累积高压指数”，CTI 越大代表兵越难受
        if current_ai == CANNON:
            # 炮方希望兵最难受，直接选择 CTI 最大的路径！
            best = max(draws, key=lambda x: x['cti'])
        else:
            # 兵方希望自己最安全，选择 CTI 最小的路径
            best = min(draws, key=lambda x: x['cti'])
        
        return best['state'], 0, f"全图空间挤压 (目标CTI: {best['cti']:.4f})"

    # 3. 困守：拖延最长时间
    if results:
        best = max(results, key=lambda x: x['dtm'])
        return best['state'], best['dtm'], "困守"
        
    return None, 0, "无路可退"

def get_avg_trap_dtm(state):
    """
    计算当前局面下，对手所有“败招陷阱”的平均 DTM。
    这反映了对手一旦走错，面临的杀局平均有多深。
    """
    current_player = state.current_player
    
    moves =[]
    for r in range(5):
        for c in range(5):
            if state.board[r][c] == current_player:
                for end in state.get_valid_moves(r, c):
                    moves.append(((r, c), end))
    
    trap_dtms =[]
    for s, e in moves:
        nxt = state.move_piece(s[0], s[1], e[0], e[1])
        # 正确接收三个返回值
        val, dtm, cti = probe_tb(nxt)
        
        is_blunder = (current_player == CANNON and val == -1) or \
                     (current_player == SOLDIER and val == 1)
        if is_blunder:
            trap_dtms.append(dtm)
            
    if not trap_dtms:
        return 0.0
    return sum(trap_dtms) / len(trap_dtms)

def main():
    print("=========================================")
    print("   2C3S 对弈实验室 (由 CTI 深度图谱驱动)")
    print("=========================================")
    
    # 案例 FEN
    print("\n[推荐局面]")
    print("A: 5/2s2/1c1c1/1s1s1/5 c c (高压和棋)")
    print("B: 5/1s1c1/2s2/1c1s1/5 c (快速杀局)")
    print("C: 5/5/1sss1/2c1c/5 s (用户测试例)")
    
    start_fen = input("\n请输入 FEN (直接回车默认 A): ").strip()
    if not start_fen or start_fen == 'A':
        start_fen = "5/2s2/1c1c1/1s1s1/5 c"
    elif start_fen == 'B':
        start_fen = "5/1s1c1/2s2/1c1s1/5 c"
    elif start_fen == 'C':
        start_fen = "5/5/1sss1/2c1c/5 s"
    
    state = GameState.from_fen(start_fen)

    while state.winner == -1:
        print_board(state)
        # 正确接收三个返回值
        val, dtm, cti = probe_tb(state)
        
        status = "炮胜" if val == 1 else ("兵胜" if val == -1 else "和棋")
        if val == 0:
            avg_dtm = get_avg_trap_dtm(state)
            print(f"-> 理论状态: {status} | DTM=0 | 当前CTI压力={cti:.4f} | 平均陷阱深度={avg_dtm:.1f}")
        else:
            print(f"-> 理论状态: {status} | DTM={dtm}")

        if state.current_player == SOLDIER:
            print("\n[你的回合(兵)]")
            try:
                move = input("输入(r,c r,c): ").strip().replace(",", " ").split()
                if not move: continue
                r1, c1, r2, c2 = map(int, move)
                state = state.move_piece(r1, c1, r2, c2)
            except Exception as e:
                print(f"[!] 走法无效: {e}")
                continue
        else:
            print("\n[炮方正在读取全局 CTI 压力场...]")
            nxt, n_dtm, strategy = get_best_move(state)
            if nxt:
                state = nxt
                print(f"-> 炮方动作完成 | 策略: {strategy}")
            else:
                print("-> 炮方无路可走")
                break

    print_board(state)
    print(f"\n[游戏结束] 胜利者: {'炮' if state.winner == CANNON else '兵'}")

if __name__ == "__main__":
    main()