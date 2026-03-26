import pickle
import os
import sys

# 确保脚本可以引用项目核心模块
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
from core.game_logic import GameState, CANNON, SOLDIER
from scripts.tb_analysis.generate_tablebase import TB_CANNON_WIN, TB_SOLDIER_WIN

def audit_tb(filename):
    """
    对特定的残局库文件执行统计审计。
    输出库内状态总数及绝杀步数 (DTM) 的分布情况。
    """
    root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    path = os.path.join(root, "data", "tablebase", filename)
    if not os.path.exists(path):
        print(f"[跳过] {filename} 不存在")
        return
        
    with open(path, 'rb') as f:
        tb = pickle.load(f)
        
    print(f"\n[*] 审计报告: {filename}")
    print(f"    状态总数: {len(tb)}")
    
    dtm_dist = {}
    for h, data in tb.items():
        dtm = data[1] # 获取步数
        dtm_dist[dtm] = dtm_dist.get(dtm, 0) + 1
        
    print("    绝杀步数 (DTM) 分布:")
    for dtm in sorted(dtm_dist.keys()):
        print(f"      步数 {dtm:02d}: {dtm_dist[dtm]} 个局面")

def trace_path(tb_filename, start_fen):
    """
    追踪指定局面在残局库指导下的完美落子序列。
    验证库内路径的连通性以及绝杀锁定的准确性。
    """
    root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    path = os.path.join(root, "data", "tablebase", tb_filename)
    if not os.path.exists(path):
        print(f"[错误] 找不到启动库: {tb_filename}")
        return
        
    with open(path, 'rb') as f:
        tb = pickle.load(f)
        
    state = GameState.from_fen(start_fen)
    print(f"\n" + "="*70)
    print(f"[*] 启动完美路径追踪: {start_fen}")
    print("="*70)
    
    history = set()
    for step in range(100):
        fen = state.to_fen()
        # 环路检测，防止死循环
        if fen in history:
            print(f"[关键错误] 检测到路径循环！循环局面: {fen}")
            return False
        history.add(fen)
        
        # 物理绝杀检测
        if state.winner != -1:
            winner_name = "炮" if state.winner == CANNON else "兵"
            print(f"第 {step:02d} 步: DTM=0  | 状态: 绝杀已达成 | FEN: {fen}")
            print(f"\n[验证通过] 游戏已结束，胜者: {winner_name}")
            return True
            
        h = state.get_canonical_hash() 
        if h not in tb:
            # 自动探测并跨库跳转 (处理吃子后的子力变动)
            sub_path = None
            if state.soldier_count == 2:
                sub_path = os.path.join("data", "tablebase", "tb_c2_s2.pkl")
            elif state.soldier_count == 1:
                sub_path = os.path.join("data", "tablebase", "tb_c2_s1.pkl")
            
            full_sub_path = os.path.join(root, sub_path) if sub_path else None
            if full_sub_path and os.path.exists(full_sub_path):
                with open(full_sub_path, 'rb') as f:
                    tb = pickle.load(f)
                print(f"\n[跨库] 检测到由于吃子引发的库跳转 -> {os.path.basename(sub_path)}")
                h = state.get_canonical_hash()
                if h not in tb:
                    print(f"[错误] 在子库中依然找不到规范化哈希 {h}。")
                    return False
            else:
                print(f"[警告] 局面在库中缺失 (Hash: {h})，且未找到适用跳转规则。")
                return False
            
        # 提取评估数据
        data = tb[h]
        val, dtm = data[0], data[1]
        
        if val == TB_CANNON_WIN:
            val_name = "炮胜"
        elif val == TB_SOLDIER_WIN:
            val_name = "兵胜"
        else:
            val_name = "和棋"
            
        print(f"第 {step:02d} 步: DTM={dtm:02d} | 状态: {val_name:4} | FEN: {state.to_fen()}")
        
        # 寻找最优走法
        best_move = None
        # 进攻方寻求 DTM 极小值，防守方追求抵抗最大化（DTM 极大值）
        is_winner_turn = (val == TB_CANNON_WIN and state.current_player == CANNON) or \
                         (val == TB_SOLDIER_WIN and state.current_player == SOLDIER)
        
        moves = []
        for r in range(5):
            for c in range(5):
                if state.board[r][c] == state.current_player:
                    for end in state.get_valid_moves(r, c):
                        moves.append(((r, c), end))
        
        best_dtm = 999 if is_winner_turn else -1
                        
        for start, end in moves:
            nxt = state.move_piece(start[0], start[1], end[0], end[1])
            
            # 路径 A: 达成即时物理终结
            if (val == TB_CANNON_WIN and nxt.winner == CANNON) or \
               (val == TB_SOLDIER_WIN and nxt.winner == SOLDIER):
                print(f"第 {step+1:02d} 步: DTM=00 | 状态: 致命一击 | FEN: {nxt.to_fen()}")
                print(f"   >>> 胜方选择达成绝杀: {start} -> {end}")
                return True
                
            # 路径 B: 跨库跳转动作 (吃子)
            if nxt.soldier_count < state.soldier_count:
                sub_file = f"tb_c2_s{nxt.soldier_count}.pkl"
                sub_target = os.path.join(root, "data", "tablebase", sub_file)
                if os.path.exists(sub_target):
                    with open(sub_target, 'rb') as f:
                        sub_tb = pickle.load(f)
                    n_ch = nxt.get_canonical_hash()
                    if n_ch in sub_tb:
                        n_res = sub_tb[n_ch]
                        n_val, n_dtm = n_res[0], n_res[1]
                        if n_val == val: # 必须确保持续掌握优势
                            if is_winner_turn:
                                if n_dtm + 1 < best_dtm:
                                    best_dtm = n_dtm + 1
                                    best_move = nxt
                            else:
                                if n_dtm + 1 > best_dtm:
                                    best_dtm = n_dtm + 1
                                    best_move = nxt
            
            # 路径 C: 库内平移
            n_ch = nxt.get_canonical_hash()
            if n_ch in tb:
                n_res = tb[n_ch]
                n_val, n_dtm = n_res[0], n_res[1]
                if n_val == val: 
                    if is_winner_turn:
                        if n_dtm < best_dtm:
                            best_dtm = n_dtm
                            best_move = nxt
                    else:
                        if n_dtm > best_dtm:
                            best_dtm = n_dtm
                            best_move = nxt
        
        # 路径 D: 和棋局面下的高压策略
        if val == 0:
            best_pressure = -1.0
            for start, end in moves:
                nxt = state.move_piece(start[0], start[1], end[0], end[1])
                n_ch = nxt.get_canonical_hash()
                pres = tb.get(n_ch, (0, 0, 0.0))
                n_val = pres[0]
                
                if n_val == 0:
                    # 模拟计算该动作给对手带来的压力系数
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
                        onnh = onn.get_canonical_hash()
                        if onn.soldier_count < nxt.soldier_count:
                            sub_tb_file = f"tb_c2_s{onn.soldier_count}.pkl"
                            sub_path = os.path.join(root, "data", "tablebase", sub_tb_file)
                            if os.path.exists(sub_path):
                                with open(sub_path, 'rb') as f:
                                    stb = pickle.load(f)
                                ores = stb.get(onnh, (0, 0, 0.0))
                                nv = ores[0]
                            else: nv = 1 # 捕获即胜
                        else:
                            ores = tb.get(onnh, (0, 0, 0.0))
                            nv = ores[0]
                        
                        # 判断对手是否陷入必败死局
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
                continue

        if best_move:
            state = best_move
        else:
            print(f"[错误] 无法定位能够维持当前胜利或和棋状态的后续走法。")
            break
    return False

if __name__ == "__main__":
    # 执行标准审计流程
    audit_tb("tb_c2_s1.pkl")
    audit_tb("tb_c2_s2.pkl")
    audit_tb("tb_c2_s3.pkl")
    
    # 执行 2C3S 关键必杀案例的路径追踪
    # 局面: 5/2s2/1s1s1/1c1c1/5 c (极高杀伤红局面)
    trace_path("tb_c2_s3.pkl", "5/2s2/1s1s1/1c1c1/5 c")
