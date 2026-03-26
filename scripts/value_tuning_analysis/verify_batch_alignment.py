"""
verify_batch_alignment.py - 验证向量化 batch_evaluate 与逐个 evaluate_board_python 的一致性。
"""
import sys
import os
import json
import random
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.game_logic import GameState
# 强制使用 CPU 后端进行验证，排除 CuPy 可能的异步/显存同步问题
os.environ["TUNER_FORCE_CPU"] = "1"
from scripts.texel_tuner import evaluate_board_python, batch_evaluate, precompute_net_control, parse_fen_to_board, setup_backend

def main():
    # 1. 加载权重
    weights_path = "data/tuning/tuned_weights.json"
    with open(weights_path, 'r', encoding='utf-8') as f:
        weights = json.load(f)

    # 2. 从数据集中提取局面
    dataset_path = "data/selfplay/run1.jsonl"
    print(f"正在读取数据集...")
    
    samples = []
    with open(dataset_path, 'r', encoding='utf-8') as f:
        for line in f:
            samples.append(json.loads(line))
    
    test_count = min(1000, len(samples))
    boards_list = []
    for i in range(test_count):
        board_arr, _ = parse_fen_to_board(samples[i]["fen"])
        boards_list.append(board_arr)
    
    boards_np = np.array(boards_list, dtype=np.int8)
    
    # 3. 预计算控制区
    net_control_counts = precompute_net_control(boards_np)
    
    # 4. 构造参数
    params = []
    params.extend(weights["BASE_MATERIAL_SCORES"])
    params.append(weights["WEIGHT_SOLDIER_PROXIMITY"])
    params.extend([weights["WEIGHT_NET_MAP"][str(i)] for i in range(6)])
    for r in range(5):
        params.extend(weights["SOLDIER_POSITION_TABLE"][r][:3])

    # 5. 执行对比
    os.environ["TUNER_DEBUG_COMPONENTS"] = "1"
    batch_scores, batch_comps = batch_evaluate(boards_np, params, net_control_counts)
    
    mismatches = 0
    for i in range(test_count):
        state = GameState.from_fen(samples[i]["fen"])
        if state.winner != -1:
            continue
            
        # 获取 (score, comps)
        res = evaluate_board_python(state, weights)
        single_score, single_comps = res if isinstance(res, tuple) else (res, {})
        
        batch_score = batch_scores[i]
        diff = abs(single_score - batch_score)
        
        if diff > 0.0001:
            mismatches += 1
            if mismatches <= 3:
                print(f"\n❌ 不一致! 索引: {i}  FEN: {samples[i]['fen']}")
                # 打印原始计数对比
                s_ncc = single_comps.get("ncc_for_debug", "N/A")
                b_ncc = int(net_control_counts[i])
                print(f"  NCC 计数对比: 逐个={s_ncc} vs 批量={b_ncc}")
                
                print(f"  各分量对比 (逐个 vs 批量):")
                if single_comps:
                    for k in ["material", "position", "proximity", "net_control"]:
                        s_v = single_comps[k]
                        b_v = float(batch_comps[k][i])
                        st = "OK" if abs(s_v - b_v) < 0.0001 else "ERR"
                        print(f"    - {k:<12}: {s_v:>6} vs {b_v:>6}  [{st}]")

    print(f"\n验证完成: 发现 {mismatches}/{test_count} 个局面打分不一致。")

if __name__ == "__main__":
    main()
