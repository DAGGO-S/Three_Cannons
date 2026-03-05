# tuning/optimizer.py
# 参数优化器 - 利用标注数据拟合最优评估函数参数

import json
import os
import sys
import numpy as np
from scipy.optimize import differential_evolution

# 添加项目根目录到路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.game_logic import GameState, CANNON, SOLDIER
from core.evaluation_logic import evaluate_board, DEFAULT_SETTINGS

class WeightMapper:
    """负责将平铺的向量映射回 settings 字典"""
    
    def __init__(self):
        # 记录每个部分的长度
        self.len_material = 15
        self.len_proximity = 1
        self.len_net_map = 6
        self.len_pos_table = 15 # 5行 * 3列 (对称)
        
        self.total_len = self.len_material + self.len_proximity + self.len_net_map + self.len_pos_table

    def vector_to_settings(self, v):
        settings = {}
        
        # 1. Material
        settings["BASE_MATERIAL_SCORES"] = list(v[0:15])
        
        # 2. Proximity
        settings["WEIGHT_SOLDIER_PROXIMITY"] = v[15]
        
        # 3. Net Map
        settings["WEIGHT_NET_MAP"] = {i: v[16+i] for i in range(6)}
        settings["MAX_NET_CONTROL_SCORE"] = v[21] # 通常是 map[5] 的值
        
        # 4. Position Table (还原对称性)
        pos_v = v[22:37]
        table = [[0 for _ in range(5)] for _ in range(5)]
        for r in range(5):
            # 对称填充: (r,0)->v, (r,1)->v, (r,2)->v, (r,3)->(r,1), (r,4)->(r,0)
            table[r][0] = pos_v[r*3 + 0]
            table[r][1] = pos_v[r*3 + 1]
            table[r][2] = pos_v[r*3 + 2]
            table[r][3] = pos_v[r*3 + 1]
            table[r][4] = pos_v[r*3 + 0]
        settings["SOLDIER_POSITION_TABLE"] = table
        
        return settings

    def settings_to_vector(self, settings):
        v = []
        # 1. Material
        v.extend(settings["BASE_MATERIAL_SCORES"])
        # 2. Proximity
        v.append(settings["WEIGHT_SOLDIER_PROXIMITY"])
        # 3. Net Map
        for i in range(6):
            v.append(settings["WEIGHT_NET_MAP"].get(i, 0))
        # 4. Position Table
        table = settings["SOLDIER_POSITION_TABLE"]
        for r in range(5):
            v.extend([table[r][0], table[r][1], table[r][2]])
        return np.array(v)

def load_data(file_path):
    if not os.path.exists(file_path):
        return []
    with open(file_path, 'r', encoding='utf-8') as f:
        data = json.load(f)
        return data.get("samples", [])

def objective_function(v, mapper, samples):
    """
    损失函数：Rank Loss
    目标是让 HumanMoveScore > OtherMoveScore + Margin
    """
    settings = mapper.vector_to_settings(v)
    total_loss = 0
    margin = 10
    
    for sample in samples:
        state = GameState(sample["board"], sample["current_player"])
        human_move = tuple(tuple(m) for m in sample["human_choice"])
        
        human_score = -1e9
        best_other_score = -1e9
        
        player = state.current_player
        for r in range(5):
            for c in range(5):
                if state.board[r][c] == player:
                    for end in state.get_valid_moves(r, c):
                        move = ((r, c), end)
                        # 执行移动并评分
                        child_state = state.move_piece(r, c, end[0], end[1])
                        score, _ = evaluate_board(child_state, settings)
                        real_score = score if player == CANNON else -score
                        
                        if move == human_move:
                            human_score = real_score
                        else:
                            if real_score > best_other_score:
                                best_other_score = real_score
        
        # 如果选中了人类走法，计算损失
        if human_score > -1e8:
            # 希望 human_score > best_other_score + margin
            loss = max(0, margin - (human_score - best_other_score))
            total_loss += loss
            
            # 如果人类走法甚至不是 Top1，给予额外惩罚以促进排名提升
            if best_other_score >= human_score:
                total_loss += 50 

    return total_loss

def analyze_accuracy(v, mapper, samples, label="当前"):
    settings = mapper.vector_to_settings(v)
    correct = 0
    total = len(samples)
    
    for sample in samples:
        state = GameState(sample["board"], sample["current_player"])
        human_move = tuple(tuple(m) for m in sample["human_choice"])
        
        best_ai_score = -float('inf')
        best_ai_move = None
        
        player = state.current_player
        for r in range(5):
            for c in range(5):
                if state.board[r][c] == player:
                    for end in state.get_valid_moves(r, c):
                        move = ((r, c), end)
                        child_state = state.move_piece(r, c, end[0], end[1])
                        score, _ = evaluate_board(child_state, settings)
                        real_score = score if player == CANNON else -score
                        
                        if real_score > best_ai_score:
                            best_ai_score = real_score
                            best_ai_move = move
        
        if best_ai_move == human_move:
            correct += 1
            
    accuracy = correct / total if total > 0 else 0
    print(f"{label}模型命中率: {accuracy:.1%} ({correct}/{total})")
    return accuracy

def main():
    data_path = os.path.join(os.path.dirname(__file__), "training_data.json")
    samples = load_data(data_path)
    if not samples:
        print("没有可用的标注数据。")
        sys.exit(0)
        
    print(f"载入 {len(samples)} 条数据，开始优化...")
    
    mapper = WeightMapper()
    init_v = mapper.settings_to_vector(DEFAULT_SETTINGS)
    
    # 基准评估
    analyze_accuracy(init_v, mapper, samples, "初始")
    
    # 设定搜索范围
    bounds = []
    for val in init_v:
        if val == 0:
            bounds.append((-50, 50))
        elif val > 0:
            bounds.append((val * 0.5, val * 2.0))
        else:
            bounds.append((val * 2.0, val * 0.5)) # 负数
            
    iteration_count = 0
    def callback(xk, convergence=None):
        nonlocal iteration_count
        iteration_count += 1
        print(f"\n>>> 正在完成第 {iteration_count} 轮进化迭代...")
        analyze_accuracy(xk, mapper, samples, f"当前最优")
        sys.stdout.flush()

    # 执行差分进化算法 (Differential Evolution)
    result = differential_evolution(
        objective_function, 
        bounds, 
        args=(mapper, samples),
        strategy='best1bin',
        maxiter=50,      # 增加迭代次数以保证拟合效果
        popsize=10,      # 增加种群规模
        tol=0.01,
        mutation=(0.5, 1),
        recombination=0.7,
        polish=False,    # 禁用 polish 以避免在复杂表面卡死
        disp=True,
        callback=callback
    )
    
    final_v = result.x
    final_settings = mapper.vector_to_settings(final_v)
    
    print("\n" + "#"*50)
    print("### 调参任务圆满完成 ###")
    print("#"*50)
    analyze_accuracy(final_v, mapper, samples, "最终")
    
    # 保存结果
    output_path = os.path.join(os.path.dirname(__file__), "new_weights.json")
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(final_settings, f, indent=2, ensure_ascii=False)
        
    print(f"新权重已保存至: {output_path}")
    
    # 对比关键变化
    print("\n关键权重变化（初始 -> 优化）：")
    old_prox = DEFAULT_SETTINGS["WEIGHT_SOLDIER_PROXIMITY"]
    new_prox = final_settings["WEIGHT_SOLDIER_PROXIMITY"]
    print(f"贴炮惩罚: {old_prox:.1f} -> {new_prox:.1f}")
    
    old_mat = DEFAULT_SETTINGS["BASE_MATERIAL_SCORES"][4] # 5兵时的分数
    new_mat = final_settings["BASE_MATERIAL_SCORES"][4]
    print(f"5兵时兵力分: {old_mat:.1f} -> {new_mat:.1f}")
    
    print("-" * 30)
    print("您可以再次运行此脚本或继续标注更多数据。")

if __name__ == "__main__":
    main()
