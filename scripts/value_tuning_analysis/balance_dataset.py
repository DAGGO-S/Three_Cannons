"""
balance_dataset.py - 对 JSONL 局面进行均衡采样，解决权重调优中的“偏科”问题。
"""
import json
import os
import random

def main():
    input_path = "data/selfplay/run1.jsonl"
    output_path = "data/selfplay/balanced_run1.jsonl"
    
    if not os.path.exists(input_path):
        print(f"找不到输入文件: {input_path}")
        return

    print(f"正在读取 {input_path} ...")
    
    # 按结果分类
    cannon_wins = []
    soldier_wins = []
    draws = []
    
    with open(input_path, 'r', encoding='utf-8') as f:
        for line in f:
            record = json.loads(line)
            outcome = record.get("game_outcome", 0.5)
            if outcome > 0.9:
                cannon_wins.append(line)
            elif outcome < 0.1:
                soldier_wins.append(line)
            else:
                draws.append(line)
    
    n_cannon = len(cannon_wins)
    n_soldier = len(soldier_wins)
    n_draw = len(draws)
    
    print(f"原始分布:")
    print(f"  炮胜: {n_cannon}")
    print(f"  兵胜: {n_soldier}")
    print(f"  和棋: {n_draw}")
    
    # --- 智能采样策略 ---
    # 为了防止因为某类样本（如和棋）过少导致总样本量崩溃，我们采用“上限截断 + 少见类过采样”策略
    target_per_class = max(n_cannon, n_soldier, n_draw)
    if target_per_class > 170000:
        target_per_class = 170000
    
    print(f"\n策略：目标每类采样 {target_per_class} 条 (少见类别将进行重复采样以对齐权重)")

    def smart_sample(data, count):
        if not data: return []
        n = len(data)
        if n >= count:
            return random.sample(data, count)
        else:
            # 过采样 (Oversampling)：重复利用已有样本
            full_repeats = count // n
            remainder = count % n
            return data * full_repeats + random.sample(data, remainder)

    balanced_data = (
        smart_sample(cannon_wins, target_per_class) +
        smart_sample(soldier_wins, target_per_class) +
        smart_sample(draws, target_per_class)
    )
    
    random.shuffle(balanced_data)
    
    print(f"正在写入 {output_path} ({len(balanced_data)} 条)...")
    with open(output_path, 'w', encoding='utf-8') as f:
        for line in balanced_data:
            f.write(line)
            
    print("✅ 数据集均衡化完成。")

if __name__ == "__main__":
    main()
