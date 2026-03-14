import pickle
import os
import sys

# 保证能找到 core
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from core.game_logic import GameState, CANNON, SOLDIER
from scripts.generate_tablebase import TB_CANNON_WIN, TB_SOLDIER_WIN

def audit_tb(filename):
    path = os.path.join("data", "tablebase", filename)
    if not os.path.exists(path):
        print(f"[SKIP] {filename} 不存在")
        return
        
    with open(path, 'rb') as f:
        tb = pickle.load(f)
        
    print(f"\n[*] 审计报告: {filename}")
    print(f"    状态总数: {len(tb)}")
    
    dtm_dist = {}
    for h, (val, dtm) in tb.items():
        dtm_dist[dtm] = dtm_dist.get(dtm, 0) + 1
        
    print("    DTM 分布:")
    for dtm in sorted(dtm_dist.keys()):
        print(f"      DTM {dtm:02d}: {dtm_dist[dtm]} 个")

def trace_path(tb_filename, start_fen):
    path = os.path.join("data", "tablebase", tb_filename)
    if not os.path.exists(path):
        return
        
    with open(path, 'rb') as f:
        tb = pickle.load(f)
        
    state = GameState.from_fen(start_fen)
    print(f"\n============================================================")
    print(f"[*] 追踪 FEN: {start_fen}")
    print(f"============================================================")
    
    history = set()
    for step in range(100):
        fen = state.to_fen()
        if fen in history:
            print(f"[ERROR] 检测到分枝循环！循环点: {fen}")
            return False
        history.add(fen)
        
        if state.winner != -1:
            winner_name = "炮" if state.winner == CANNON else "兵"
            print(f"Step {step:02d}: DTM=0  | 绝杀   | FEN: {fen}")
            print(f"\n[SUCCESS] 游戏结束！胜者: {winner_name} (判定成功)")
            return True
            
        h = state.get_canonical_hash() # 使用规范化哈希进行检索
        if h not in tb:
            # 尝试库间跳转
            sub_path = None
            if state.soldier_count == 2:
                sub_path = os.path.join("data", "tablebase", "tb_c2_s2.pkl")
            elif state.soldier_count == 1:
                sub_path = os.path.join("data", "tablebase", "tb_c2_s1.pkl")
            
            if sub_path and os.path.exists(sub_path):
                with open(sub_path, 'rb') as f:
                    tb = pickle.load(f)
                print(f"\n[JUMP] 已切换至 {os.path.basename(sub_path)} 残局库继续追踪...")
                h = state.get_canonical_hash() # 跳转后重新规范化
                if h in tb:
                    val, dtm = tb[h]
                else:
                    print(f"[ERROR] 跳转后的哈希 {h} 仍不在子库中。")
                    return False
            else:
                print(f"[WARNING] 状态不在当前库中 (Hash: {h}), 且未找到合适的跳转逻辑。")
                return False
            
        val, dtm = tb[h]
        if val == TB_CANNON_WIN:
            val_name = "炮胜"
        elif val == TB_SOLDIER_WIN:
            val_name = "兵胜"
        else:
            val_name = "和棋"
            
        print(f"Step {step:02d}: DTM={dtm:02d} | {val_name:4} | FEN: {state.to_fen()}")
        
        # 选择最佳走法
        best_move = None
        # 如果是胜方回合，找 DTM 最小的；如果是败方回合，找 DTM 最大的（延长抵抗）
        is_winner_turn = (val == TB_CANNON_WIN and state.current_player == CANNON) or \
                         (val == TB_SOLDIER_WIN and state.current_player == SOLDIER)
        
        # 获取合法走法
        moves = []
        for r in range(5):
            for c in range(5):
                if state.board[r][c] == state.current_player:
                    for end in state.get_valid_moves(r, c):
                        moves.append(((r, c), end))
        
        best_dtm = 999 if is_winner_turn else -1
                        
        for start, end in moves:
            nxt = state.move_piece(start[0], start[1], end[0], end[1])
            
            # 情况 A: 立即获胜
            if (val == TB_CANNON_WIN and nxt.winner == CANNON) or \
               (val == TB_SOLDIER_WIN and nxt.winner == SOLDIER):
                print(f"Step {step+1:02d}: DTM=00 | 绝杀   | FEN: {nxt.to_fen()}")
                print(f"   >>> 胜方选择绝杀: {start} -> {end}")
                return True
                
            # 情况 B: 跨库跳转 (吃子)
            if nxt.soldier_count < state.soldier_count:
                sub_path = os.path.join("data", "tablebase", f"tb_c2_s{nxt.soldier_count}.pkl")
                if os.path.exists(sub_path):
                    with open(sub_path, 'rb') as f:
                        sub_tb = pickle.load(f)
                    n_ch = nxt.get_canonical_hash()
                    if n_ch in sub_tb:
                        n_val, n_dtm = sub_tb[n_ch]
                        if n_val == val: # 必须维持胜果
                            if is_winner_turn:
                                if n_dtm + 1 < best_dtm:
                                    best_dtm = n_dtm + 1
                                    best_move = nxt
                            else: # 败方（理论上不会主动吃子跳转到对方必胜局，但需逻辑完备）
                                if n_dtm + 1 > best_dtm:
                                    best_dtm = n_dtm + 1
                                    best_move = nxt
            
            # 情况 C: 库内移动
            n_ch = nxt.get_canonical_hash()
            if n_ch in tb:
                n_val, n_dtm = tb[n_ch]
                if n_val == val: # 必须维持胜负状态
                    if is_winner_turn:
                        if n_dtm < best_dtm:
                            best_dtm = n_dtm
                            best_move = nxt
                    else:
                        if n_dtm > best_dtm:
                            best_dtm = n_dtm
                            best_move = nxt
        
        # 情况 D: 和棋局面下的压力分析 (抓失误策略)
        if val == 0:
            best_pressure = -1.0
            
            for start, end in moves:
                nxt = state.move_piece(start[0], start[1], end[0], end[1])
                n_ch = nxt.get_canonical_hash()
                n_val, _ = tb.get(n_ch, (0, 0))
                
                if n_val == 0:
                    # 计算此走法给对手带来的压力
                    opp_moves = []
                    for r in range(5):
                        for c in range(5):
                            if nxt.board[r][c] == nxt.current_player:
                                for e in nxt.get_valid_moves(r, c):
                                    opp_moves.append(((r,c), e))
                                    
                    loss_count = 0
                    total = len(opp_moves)
                    
                    for os_pos, oe_pos in opp_moves:
                        onn = nxt.move_piece(os_pos[0], os_pos[1], oe_pos[0], oe_pos[1])
                        # 处理对手失误导致的必败
                        onnh = onn.get_canonical_hash()
                        # 检查跳转收益 (针对兵方失误被吃)
                        if onn.soldier_count < nxt.soldier_count:
                            sub_tb_file = f"tb_c2_s{onn.soldier_count}.pkl"
                            sub_path = os.path.join("data", "tablebase", sub_tb_file)
                            if os.path.exists(sub_path):
                                with open(sub_path, 'rb') as f:
                                    stb = pickle.load(f)
                                nv, _ = stb.get(onnh, (0, 0))
                            else: nv = 1 # 捕获收益
                        else:
                            nv, _ = tb.get(onnh, (0, 0))
                        
                        # 如果对我方有利 (对手必败)
                        is_opp_loss = (nxt.current_player == CANNON and nv == -1) or \
                                      (nxt.current_player == SOLDIER and nv == 1)
                        if is_opp_loss:
                            loss_count += 1
                    
                    pressure = (loss_count / total) if total > 0 else 0
                    if pressure > best_pressure:
                        best_pressure = pressure
                        best_move = nxt
            
            if best_move:
                state = best_move
                # print(f"   >>> 和棋策略: 选择压迫感权重 {best_pressure:.1%}")
                continue

        if best_move:
            # 打印选择
            # print(f"   >>> 选择移动: DTM={best_dtm}")
            state = best_move
        else:
            print(f"[ERROR] 无法在库中找到维持 {val_name} 状态的后续走法。")
            break
    return False

if __name__ == "__main__":
    audit_tb("tb_c2_s1.pkl")
    audit_tb("tb_c2_s2.pkl")
    audit_tb("tb_c2_s3.pkl")
    
    # 追踪三个关键案例
    # 1. 2C1S 回流案例 (验证一致性)
    #trace_path("tb_c2_s1.pkl", "5/2s2/5/1c1c1/5 c")
    
    # 2. 2C2S 起点案例 (长路径验证)
    # ccss1/5/5/5/5 s (2炮2兵紧凑布局，兵方落子)
    #trace_path("tb_c2_s2.pkl", "ccss1/5/5/5/5 s")

    # 3. 2C3S 重点案例 (验证炮方必杀)暂时只关注这个
    # 5/2s2/1s1s1/1c1c1/5 c
    trace_path("tb_c2_s3.pkl", "5/2s2/1s1s1/1c1c1/5 c")
