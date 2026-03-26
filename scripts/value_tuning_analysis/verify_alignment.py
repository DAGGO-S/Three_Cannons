"""
verify_alignment.py - 验证 Python 调优器与 Cython 引擎评估函数的一致性。

如果两者对同一个局面的打分不一致，Texel Tuner 就会优化出错误的权重。
"""
import sys
import os
import json
import random

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# 导入 Cython 版评估 (引擎使用)
from core.game_logic import GameState
from core.evaluation_logic import evaluate_board as cython_evaluate, apply_weights

# 导入 Python 版评估 (调优器使用)
from scripts.texel_tuner import evaluate_board_python

def main():
    # 1. 加载一组权重 (使用精调后的)
    weights_path = "data/tuning/tuned_weights.json"
    if not os.path.exists(weights_path):
        print(f"找不到权重文件: {weights_path}")
        return

    with open(weights_path, 'r', encoding='utf-8') as f:
        weights = json.load(f)

    # 2. 将权重应用到 Cython 引擎
    apply_weights(weights)

    # 3. 从数据集中随机抽取 1000 个局面进行对比
    dataset_path = "data/selfplay/run1.jsonl"
    if not os.path.exists(dataset_path):
        print(f"找不到数据集: {dataset_path}")
        return

    print(f"正在从 {dataset_path} 验证评估对齐...")
    
    samples = []
    with open(dataset_path, 'r', encoding='utf-8') as f:
        for line in f:
            samples.append(json.loads(line))
    
    random.shuffle(samples)
    test_count = min(2000, len(samples))
    
    mismatches = 0
    max_diff = 0
    
    print(f"测试局面数: {test_count}")
    print("-" * 50)

    for i in range(test_count):
        fen = samples[i]["fen"]
        state = GameState.from_fen(fen)
        
        # Cython 评估
        cy_score, _ = cython_evaluate(state)
        
        # Python 评估
        py_score = evaluate_board_python(state, weights)
        
        diff = abs(cy_score - py_score)
        if diff != 0:
            mismatches += 1
            max_diff = max(max_diff, diff)
            if mismatches <= 5:
                print(f"不一致! FEN: {fen}")
                print(f"  Cython: {cy_score}")
                print(f"  Python: {py_score}")
                print(f"  差异: {diff}")
                print("-" * 30)

    print("-" * 50)
    if mismatches == 0:
        print("✅ 验证通过! Python 与 Cython 评估 100% 对齐。")
    else:
        print(f"❌ 验证失败! 发现 {mismatches}/{test_count} 个局面打分不一致。")
        print(f"最大差异: {max_diff}")
        print("\n原因分析：请检查 texel_tuner.py 中的 evaluate_board_python 是否与 evaluation_logic.pyx 逻辑完全一致。")

if __name__ == "__main__":
    main()
