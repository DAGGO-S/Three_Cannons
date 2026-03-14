"""
generate_tablebase.py - 三炮十五兵 逆向推演残局库生成器 (Tablebase Generator)

用于枚举特定子力（如 2炮1兵）下的所有合法局面，并通过逆向分析
(Retrograde Analysis) 计算出每个局面的精确理论胜负及 DTM (Distance to Mate)。
并针对和棋局面，使用强化学习值迭代计算 CTI (累积高压指数)。
"""

import sys
import os
import itertools
import pickle
import time
from collections import deque
from typing import Dict

# 将上一级目录加入sys.path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.game_logic import GameState, CANNON, SOLDIER, EMPTY

# 绝对胜负标识
TB_CANNON_WIN = 1
TB_SOLDIER_WIN = -1
TB_DRAW = 0

class TablebaseNode:
    __slots__ =['hash_val', 'state', 'value', 'dtm', 'cti', 'parents', 'children_count', 'unresolved_children']
    
    def __init__(self, state: GameState):
        self.hash_val = state.get_canonical_hash() # 存储规范化哈希
        self.state = state
        self.value = TB_DRAW       # 默认和棋
        self.dtm = 0               # 默认 DTM 0
        self.cti = 0.0             # 【新增】累积高压指数 (只对和棋有效)
        self.parents =[]          # 能够走到当前节点的前驱节点（规范化 hash 列表）
        self.children_count = 0    # 总合法后续走法数
        self.unresolved_children = 0 # 尚未确定真实价值的后续走法数


def create_all_valid_states(cannon_num: int, soldier_num: int) -> Dict[int, TablebaseNode]:
    print(f"[*] 开始生成状态空间 (对称压缩模式): {cannon_num}炮 vs {soldier_num}兵")
    t0 = time.time()
    nodes = {}
    
    cells = range(25)
    
    # 组合炮的位置
    for cannon_pos in itertools.combinations(cells, cannon_num):
        remaining =[c for c in cells if c not in cannon_pos]
        # 组合兵的位置
        for soldier_pos in itertools.combinations(remaining, soldier_num):
            board_1d = [0] * 25
            for p in cannon_pos: board_1d[p] = CANNON
            for p in soldier_pos: board_1d[p] = SOLDIER
            
            board_2d = [board_1d[i:i+5] for i in range(0, 25, 5)]
            
            for turn in [CANNON, SOLDIER]:
                state = GameState(board_2d, turn)
                # 使用规范化哈希进行去重存储
                ch = state.get_canonical_hash()
                if ch not in nodes:
                    nodes[ch] = TablebaseNode(state)
                    
    print(f"[*] 状态空间去重完毕: 共 {len(nodes)} 个规范化节点，耗时 {time.time() - t0:.2f}s")
    return nodes

def build_graph_and_init_terminals(nodes: Dict[int, TablebaseNode], sub_tb: Dict[int, tuple] = None) -> deque:
    print("[*] 正在基于分层 BFS 规则初始化种子节点...")
    t0 = time.time()
    
    queue = deque()
    
    for ch, node in nodes.items(): 
        state = node.state
        
        # 获取合法走法
        legal_moves =[]
        for r in range(5):
            for c in range(5):
                if state.board[r][c] == state.current_player:
                    for end_pos in state.get_valid_moves(r, c):
                        legal_moves.append(((r, c), end_pos))
        
        # 1. 识别库内内部走法
        internal_moves_count = 0
        has_sub_tb_win = False
        
        for start, end in legal_moves:
            nxt = state.move_piece(start[0], start[1], end[0], end[1])
            n_ch = nxt.get_canonical_hash()
            
            if n_ch in nodes:
                internal_moves_count += 1
                nodes[n_ch].parents.append(ch)
            else:
                # 跨库动作 (子力减少)
                if state.current_player == CANNON:
                    if sub_tb and n_ch in sub_tb:
                        val = sub_tb[n_ch][0] # 兼容新的元组结构 (val, dtm, cti) 或 (val, dtm)
                        if val == TB_CANNON_WIN:
                            has_sub_tb_win = True
                    elif nxt.soldier_count < state.soldier_count:
                        # 兜底：如果没加载子库但吃光了兵，也算赢
                        has_sub_tb_win = True
        
        node.children_count = len(legal_moves)
        node.unresolved_children = internal_moves_count

        # 2. 设置 DTM=0 种子 (困毙)
        if not legal_moves:
            if state.current_player == SOLDIER:
                node.value = TB_CANNON_WIN
            else:
                node.value = TB_SOLDIER_WIN
            node.dtm = 0
            node.unresolved_children = 0
            queue.append(node)
            continue
            
        # 3. 设置 DTM=1 种子 (库间跳转获胜)
        if state.current_player == CANNON and has_sub_tb_win:
            node.value = TB_CANNON_WIN
            node.dtm = 1
            node.unresolved_children = 0
            queue.append(node)

    print(f"[*] 种子初始化完毕: 初始解决 {len(queue)} 个节点，耗时 {time.time() - t0:.2f}s")
    return queue

def retrograde_analysis(nodes: Dict[int, TablebaseNode], queue: deque):
    """
    分层逆向推演系统。用于确立必胜、必败局面及精确 DTM。
    """
    print("[*] 开始执行严格的分层逆向推演...")
    t0 = time.time()
    resolved_count = 0
    
    layer_map = {} 
    for node in queue: 
        layer_map.setdefault(node.dtm,[]).append(node)
    
    current_dtm = 0
    while True:
        if current_dtm not in layer_map or not layer_map[current_dtm]:
            higher_dtms =[d for d in layer_map.keys() if d > current_dtm and layer_map[d]]
            if not higher_dtms:
                break
            current_dtm = min(higher_dtms)
            
        nodes_to_process = layer_map[current_dtm]
        layer_map[current_dtm] =[] 
        
        for node in nodes_to_process:
            resolved_count += 1
            
            for parent_hash in node.parents:
                parent = nodes[parent_hash]
                if parent.value != TB_DRAW:
                    continue
                
                p_player = parent.state.current_player
                p_win_val = TB_CANNON_WIN if p_player == CANNON else TB_SOLDIER_WIN
                p_loss_val = TB_SOLDIER_WIN if p_player == CANNON else TB_CANNON_WIN

                # 情况 A: parent 能走一步到让对方必败的状态 -> parent 必胜
                if node.value == p_win_val:
                    new_dtm = current_dtm + 1
                    
                    if new_dtm % 2 != 1:
                        print(f"🛑 [FATAL] Logic Divergence! DTM={new_dtm} is Even for a Winner.")
                        sys.exit(1)

                    parent.value = p_win_val
                    parent.dtm = new_dtm
                    parent.unresolved_children = 0
                    layer_map.setdefault(parent.dtm,[]).append(parent)
                    
                # 情况 B: parent 的这一步走到了让对方必胜的状态 -> parent 抵抗力减一
                elif node.value == p_loss_val:
                    parent.unresolved_children -= 1
                    parent.dtm = max(parent.dtm, current_dtm + 1)
                    
                    if parent.unresolved_children == 0:
                        parent.value = p_loss_val
                        if parent.dtm % 2 != 0:
                            print(f"🔥[PARITY ERROR] DTM: {parent.dtm} should be Even.")
                        layer_map.setdefault(parent.dtm,[]).append(parent)
        
        current_dtm += 1

    print(f"[*] 逆向推演结束: 解决节点数 {resolved_count}, 耗时 {time.time() - t0:.2f}s")
    draws = len(nodes) - resolved_count
    print(f"[*] 胜负已定: 和棋环/孤岛剩余 {draws} 个。")


def calculate_draw_cti(nodes: Dict[int, TablebaseNode], gamma: float = 0.95, epsilon: float = 1e-5):
    """
    【核心新增】为所有 val=0 (平局) 的状态执行 MDP 值迭代，计算累积高压指数 (CTI)。
    """
    print(f"\n[*] 开始针对平局空间计算 CTI (累积高压指数, Gamma={gamma})...")
    t0 = time.time()
    
    # 1. 预处理提取平局子图，极大地加速后续迭代
    draw_graph = {}
    for h, node in nodes.items():
        if node.value == TB_DRAW:
            state = node.state
            current_player = state.current_player
            total_moves = 0
            draw_children =[]
            
            for r in range(5):
                for c in range(5):
                    if state.board[r][c] == current_player:
                        for end in state.get_valid_moves(r, c):
                            total_moves += 1
                            nxt = state.move_piece(r, c, end[0], end[1])
                            nxt_hash = nxt.get_canonical_hash()
                            child_node = nodes.get(nxt_hash)
                            
                            # 只有走完也是平局的，才纳入 CTI 迭代图谱
                            if child_node and child_node.value == TB_DRAW:
                                draw_children.append(nxt_hash)
                                
            draw_graph[h] = {
                'player': current_player,
                'total_moves': total_moves,
                'draw_children': draw_children
            }
            node.cti = 0.0 # 初始 CTI 为 0
            
    print(f"[*] 预处理完成，共有 {len(draw_graph)} 个平局节点参与 CTI 迭代。")
    
    # 2. 强化学习 值迭代 (Value Iteration)
    iteration = 0
    while True:
        max_delta = 0.0
        
        for h, data in draw_graph.items():
            node = nodes[h]
            old_cti = node.cti
            
            player = data['player']
            total_moves = data['total_moves']
            draw_children_hashes = data['draw_children']
            
            # 如果没有平局出路了 (按理不该发生，因为那说明是困毙必败节点)
            if not draw_children_hashes:
                continue 
                
            children_ctis = [nodes[ch].cti for ch in draw_children_hashes]
            
            if player == CANNON:
                # 炮方 (我方): 选择让兵方未来 CTI 最大的路径 (最大化压迫)
                new_cti = max(children_ctis)
            else: 
                # 兵方 (对方): 选择让自己未来 CTI 最小的路径，并承受瞬时失误风险
                k = len(draw_children_hashes)
                # C_s 即瞬时复杂度：总走法中会导致输棋的走法占比
                C_s = (total_moves - k) / total_moves if total_moves > 0 else 0.0
                
                min_future_cti = min(children_ctis)
                # 累积高压 = 瞬时压力 + 衰减的未来最小压力
                new_cti = C_s + gamma * min_future_cti
                
            node.cti = new_cti
            delta = abs(new_cti - old_cti)
            if delta > max_delta:
                max_delta = delta
                
        iteration += 1
        if iteration % 20 == 0:
            print(f"    - 迭代 {iteration:3d}, 最大更新误差: {max_delta:.6f}")
            
        if max_delta < epsilon:
            print(f"[*] CTI 计算收敛完成！总迭代次数: {iteration}, 耗时: {time.time() - t0:.2f}s")
            break


def export_tablebase(nodes: Dict[int, TablebaseNode], num_cannons: int, num_soldiers: int):
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    tb_dir = os.path.join(root, 'data', 'tablebase')
    os.makedirs(tb_dir, exist_ok=True)
    filepath = os.path.join(tb_dir, f'tb_c{num_cannons}_s{num_soldiers}.pkl')
    
    export_data = {}
    c_win = s_win = draw = 0
    
    for h, n in nodes.items():
        v = n.value
        d = n.dtm if v != TB_DRAW else 0
        
        # 【修改点】仅在平局时写入 CTI，保留4位小数以压缩文件大小
        c = round(n.cti, 4) if v == TB_DRAW else 0.0 
        
        if v == TB_CANNON_WIN: c_win += 1
        elif v == TB_SOLDIER_WIN: s_win += 1
        else: draw += 1
        
        # 导出包含了 CTI 的三元组
        export_data[h] = (v, d, c)
        
    with open(filepath, 'wb') as f:
        pickle.dump(export_data, f)
        
    print(f"[*] 结果文件已导出至: {filepath}")
    print(f"    统计: 炮方必胜: {c_win}  |  兵方必胜: {s_win}  |  和局: {draw}")
    print("="*60)

def main():
    # 依次生成：支持通过加载上一个库来实现 DTM 梯次近似
    configs =[
        (2, 1),
        (2, 2),
        (2, 3), # 2炮 3兵
    ]
    
    for c_num, s_num in configs:
        print(f"\n{'='*20} 正在构建 {c_num}炮 vs {s_num}兵 的全集库 {'='*20}")
        
        last_tb = None
        # 为当前库加载“子力减1”的库作为种子引证
        if s_num > 1:
            sub_filename = f"tb_c{c_num}_s{s_num-1}.pkl"
            path = os.path.join("data", "tablebase", sub_filename)
            if os.path.exists(path):
                with open(path, 'rb') as f:
                    last_tb = pickle.load(f)
                    print(f"[*] 已成功加载子残局库 {sub_filename} (仅用于种子引证)")
            else:
                print(f"[!] 未找到子库 {sub_filename}，将跳过跨库种子初始化。")

        # 1. 生成并去重所有状态
        nodes = create_all_valid_states(c_num, s_num)
        
        # 2. 建立图并初始化必定胜负的种子
        queue = build_graph_and_init_terminals(nodes, sub_tb=last_tb)
        
        # 3. 逆向推演 (Retrograde Analysis) 计算准确的 DTM
        retrograde_analysis(nodes, queue)
        
        # 4. 【新增环节】对剩余的和棋图谱执行强化学习 CTI 迭代
        calculate_draw_cti(nodes, gamma=0.95, epsilon=1e-5)
        
        # 5. 导出包含 (val, dtm, cti) 的超级残局库
        export_tablebase(nodes, c_num, s_num)

if __name__ == '__main__':
    main()