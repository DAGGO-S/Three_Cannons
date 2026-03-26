import pickle
import os
import sys

# 保证能找到 core
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
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
    root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    path = os.path.join(root, "data", "tablebase", filename)
    if not os.path.exists(path): return None
    print(f"[*] 加载库: {filename}")
    with open(path, 'rb') as f:
        TB_CACHE[s_num] = pickle.load(f)
    return TB_CACHE[s_num]

def probe_tb(state):
    tb = get_tb(state.soldier_count)
    if not tb: 
        # 兼容性修复：当兵力超过 3 或库缺失时，返回全零哑元，避免调用方解包崩溃
        return (0, 0, 0.0)
    h = state.get_canonical_hash()
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
            'move': f"({start[0]},{start[1]})->({end[0]},{end[1]})",
            'state': nxt,
            'val': n_val,
            'dtm': n_dtm,
            'cti': n_cti,       # 将 CTI 记录下来
            'winning': is_winning,
            'draw': is_draw
        })

    # 排序逻辑 (与兵方逻辑对称，但目标相反):
    # 对炮方而言: 优先级为 必胜 (val=1) > 和棋 (val=0) > 必败 (val=-1)
    # 值越大越好。在和棋内部，CTI 越大越好（施压）。
    # 按照 (val, -cti, dtm) 排序，其中 val=1 为炮胜，val=0 为和棋，val=-1 为兵胜
    # 炮方希望 val 越大越好，cti 越大越好，dtm 越小越好
    results.sort(key=lambda x: (-x['val'], -x['cti'], x['dtm']))
    
    print("--- 炮方备选策略 (Top 3) ---")
    for i, m in enumerate(results[:3]):
        v_str = "和棋" if m['val'] == 0 else ("炮胜" if m['val'] == 1 else "兵胜")
        print(f" {i+1}. {m['move']} | 状态: {v_str} | DTM: {m['dtm']} | CTI: {m['cti']:.4f}")
    print("----------------------------")

    if results:
        best = results[0]
        strategy = "定解必胜" if best['val'] == 1 else ("定解挤压" if best['val'] == 0 else "定解困守")
        return best['state'], best['dtm'], f"{strategy} (CTI: {best['cti']:.4f})"
        
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
    fens = {
        'A': "s1s1s/5/5/5/1c1c1 c",
        'B': "1s2s/5/5/5/1c1c1 c",
        'C': "5/5/1sss1/2c1c/5 s",
        'D': "1s3/s1c2/c4/5/5 c"
    }
    print(f"A: {fens['A']} (高压和棋)")
    print(f"B: {fens['B']} (快速杀局)")
    print(f"C: {fens['C']} (用户测试例)")
    print(f"D: {fens['D']} (绝杀吃子验证)")

    print("\n请输入 FEN (直接回车默认 A): ", end="")
    fen_input = input().strip()
    if not fen_input:
        state = GameState.from_fen(fens['A'])
    elif fen_input.upper() in fens:
        state = GameState.from_fen(fens[fen_input.upper()])
    else:
        state = GameState.from_fen(fen_input)

    history = [] # 存储 GameState 用于回退

    while state.winner == -1:
        history.append(state)
        print_board(state)
        
        # 1. 探测当前局面理论指标
        val, dtm, cti = probe_tb(state)
        status = "炮胜" if val == 1 else ("兵胜" if val == -1 else "和棋")
        if val == 0:
            avg_dtm = get_avg_trap_dtm(state)
            print(f"-> 理论状态: {status} | DTM=0 | 当前CTI压力={cti:.4f} | 平均陷阱深度={avg_dtm:.1f}")
        else:
            print(f"-> 理论状态: {status} | DTM={dtm}")

        # 2. 生成并评估所有合法走法
        current_p = state.current_player
        moves_data = []
        for r in range(5):
            for c in range(5):
                if state.board[r][c] == current_p:
                    for end in state.get_valid_moves(r, c):
                        nxt = state.move_piece(r, c, end[0], end[1])
                        v, d, c_score = probe_tb(nxt)
                        moves_data.append({
                            'move_coords': (r, c, end[0], end[1]),
                            'move_str': f"({r},{c})->({end[0]},{end[1]})",
                            'state': nxt,
                            'val': v,
                            'dtm': d,
                            'cti': c_score,
                            'sc': nxt.soldier_count
                        })
        
        # 3. 根据玩家身份排序 (双控审计)
        # 核心逻辑：物质变化 (sc) 优于 DTM。
        if current_p == SOLDIER:
            # 兵方排序：必胜(-1) > 和棋(0) > 必败(1)
            # 物质：sc 越大越好 (即保持兵力)
            # 和棋内：CTI 越小越安全
            moves_data.sort(key=lambda x: (x['val'], -x['sc'], x['cti'], -x['dtm']))
        else:
            # 炮方排序：必胜(1) > 和棋(0) > 必败(-1)
            # 物质：sc 越小越好 (即吃子进入简易子库)
            # 和棋内：CTI 越大越压迫
            moves_data.sort(key=lambda x: (-x['val'], x['sc'], -x['cti'], x['dtm']))
            
        # 4. 展示策略建议
        print(f"\n[{'兵' if current_p == SOLDIER else '炮'}方备选策略 (Top 5)]")
        for i, m in enumerate(moves_data[:5]):
            v_str = "和棋" if m['val'] == 0 else ("炮胜" if m['val'] == 1 else "兵胜")
            print(f" {i+1}. {m['move_str']} | 状态: {v_str} | DTM: {m['dtm']} | CTI: {m['cti']:.4f}")
        print("-----------------------------------")
        
        # 5. 交互循环
        while True:
            try:
                prompt = f"[{'兵' if current_p == SOLDIER else '炮'}方] 请输入序号(1-N)、坐标(r c r c) 或 'u'回退: "
                user_in = input(prompt).strip().lower()
                if not user_in: continue
                
                # 回退逻辑
                if user_in in ('u', 'undo'):
                    if len(history) > 1:
                        history.pop() # 弹出当前局面 (刚刚进入循环时加入的)
                        state = history.pop() # 恢复上一个局面
                        print("<<< 已回退")
                        break # 跳出交互循环，进入下一个大循环显示局面
                    else:
                        print("[!] 无法继续回退")
                        continue

                # 序号选择逻辑
                if user_in.isdigit():
                    idx = int(user_in) - 1
                    if 0 <= idx < len(moves_data):
                        state = moves_data[idx]['state']
                        print(f"-> 已选择: {moves_data[idx]['move_str']}")
                        break # 跳出交互循环
                    else:
                        print(f"[!] 序号范围错误 (1-{len(moves_data)})")
                        continue

                # 坐标输入逻辑
                parts = user_in.replace(",", " ").split()
                if len(parts) == 4:
                    r1, c1, r2, c2 = map(int, parts)
                    state = state.move_piece(r1, c1, r2, c2)
                    break # 跳出交互循环
                else:
                    print("[!] 输入格式错误，请重新输入")
                    continue
                    
            except Exception as e:
                print(f"[!] 操作失败: {e}")
                continue

    print_board(state)
    winner_str = "炮" if state.winner == CANNON else "兵"
    print(f"\n[游戏结束] 胜利者: {winner_str}")

if __name__ == "__main__":
    main()