"""
nnue_trainer.py - Micro-NNUE 评估网络训练器 (算法进化版)

针对 5x5 三炮棋设计的神经网络评估方案。
升级特性：水平对称增强、K 值自动化搜索、OneCycleLR 调度、Lambda 权重平滑。

用法:
    python scripts/nnue_trainer.py --data data/selfplay/run3.jsonl --epochs 50
"""

import json
import os
import time
import argparse
import numpy as np
import torch
import torch.nn as nn
import torch.optim as optim
from torch.utils.data import DataLoader, TensorDataset
import torch.nn.functional as F

# ─── 训练全局配置 (在此物理由您调整参数) ──────────────────────────────────────
TRAINING_CONFIG = {
    "main_data": "data/selfplay/run3.jsonl",
    "endgame_data": "data/selfplay/pure_mates.jsonl",
    "endgame_weight": 20,        # 显著增加权重，迫使模型学会 ±10000 边界
    "epochs": 40,               # 深度训练
    "batch_size": 1024,
    "lr": 0.025,
    "lbda": 0.0,                # 目前写死了0，因为没有设置回传衰减，开局居然拟合结局AI始终无法拟合几十步的未来！
    "alpha": 0.5,               # 双尺度权重 (K=600 vs K=10000)
    "K1": 600.0,                # 局面分尺度
    "K2": 10000.0,              # 绝杀分尺度
    "hidden1": 256,
    "hidden2": 32,
    "load_model": "data/nnue/micro_nnue-N1.pth",
    "output_model": "data/nnue/micro_nnue.pth",
    "output_header": "core/nnue_weights.h"
}

# ─── 棋盘与对称变换 ─────────────────────────────────────────────────────────
EMPTY = 0
SOLDIER = 1
CANNON = 2

# 水平镜像索引映射 (c -> 4-c)
def get_hflip_indices():
    indices = np.zeros(51, dtype=np.int32)
    for r in range(5):
        for c in range(5):
            # 兵 (0-24)
            indices[r * 5 + c] = r * 5 + (4 - c)
            # 炮 (25-49)
            indices[25 + r * 5 + c] = 25 + r * 5 + (4 - c)
    indices[50] = 50 # STM 不变
    return indices

HFLIP_INDICES = get_hflip_indices()

# ─── 网络定义与损失函数 ──────────────────────────────────────────────────────

class MicroNNUE(nn.Module):
    def __init__(self, hidden1_dim=256, hidden2_dim=32):
        super(MicroNNUE, self).__init__()
        self.fc1 = nn.Linear(51, hidden1_dim)
        self.fc2 = nn.Linear(hidden1_dim, hidden2_dim)
        self.fc3 = nn.Linear(hidden2_dim, 1)
        self.relu = nn.ReLU()
        
    def forward(self, x):
        x = self.relu(self.fc1(x))
        x = self.relu(self.fc2(x))
        x = self.fc3(x)
        return x

def dual_scale_sigmoid_loss(prediction, target_outcome, target_eval, lbda=0.0, K1=600.0, K2=10000.0, alpha=0.5):
    """
    双尺度损失函数：
    Loss1 (K1=600): 负责捕获精细局面分（0-800区间），但在高分区会饱和。
    Loss2 (K2=10000): 负责提供长程梯度，迫使预测值向 ±10000 推进。
    """
    # 尺度1: 传统 K=600
    scaling1 = 2.302585 / K1
    pred_winrate1 = torch.sigmoid(prediction * scaling1)
    target_winrate1 = torch.sigmoid(target_eval * scaling1)
    
    # 尺度2: 绝杀 K=10000
    scaling2 = 2.302585 / K2
    pred_winrate2 = torch.sigmoid(prediction * scaling2)
    target_winrate2 = torch.sigmoid(target_eval * scaling2)
    
    # 物理权重：绝杀局面权重翻倍
    eval_weight = 1.0 + torch.abs(target_eval) / 10000.0
    
    loss_k600 = (eval_weight * (pred_winrate1 - target_winrate1)**2).mean()
    loss_k10000 = (eval_weight * (pred_winrate2 - target_winrate2)**2).mean()
    
    # 混合损失
    loss_eval = (1.0 - alpha) * loss_k600 + alpha * loss_k10000
    
    # 胜负分类损失 (WDL)
    loss_outcome = (eval_weight * (pred_winrate1 - target_outcome)**2).mean()
    
    return lbda * loss_outcome + (1.0 - lbda) * loss_eval

# ─── 数据加载与增强 ──────────────────────────────────────────────────────────

def parse_fen_to_features(fen):
    features = np.zeros(51, dtype=np.float32)
    parts = fen.split()
    board_part = parts[0]
    if len(parts) > 1 and parts[1].lower() == 'c':
        features[50] = 1.0
    idx = 0
    for ch in board_part:
        if ch == '/': continue
        if ch.isdigit():
            idx += int(ch)
        elif ch.lower() == 's':
            features[idx] = 1.0
            idx += 1
        elif ch.lower() == 'c':
            features[idx + 25] = 1.0
            idx += 1
    return features

def load_nnue_dataset(filepath, max_samples=None, augment=True, weight=1):
    """加载 NNUE 数据集，支持物理过采样权重。"""
    if not os.path.exists(filepath):
        print(f"[!] 跳过缺失文件: {filepath}")
        return [], [], []
        
    print(f"[数据] 正在加载 {filepath} (权重: {weight}x) ...")
    X, y_outcome, y_eval = [], [], []

    # 识别是否为残局数据集 (字段名和过滤逻辑不同)
    is_endgame = "endgame" in filepath.lower()

    with open(filepath, 'r', encoding='utf-8') as f:
        for line in f:
            try:
                record = json.loads(line)
                
                # 1. 提取评估分
                eval_score = float(record.get("eval", record.get("score", 0)))
                
                # 通用数据处理
                if not is_endgame:
                    # 如果不保留绝杀分，则过滤
                    if not augment and abs(eval_score) > 9950: continue 
                    # 注意：这里我们引入了一个机制，如果设置了特殊的训练目标，允许保留绝杀分
                
                # 2. 提取胜负结果 (兼备 game_outcome 或从 final_score 物理映射)
                if "game_outcome" in record:
                    outcome = float(record["game_outcome"])
                elif "final_score" in record:
                    # 逻辑映射 (Cannon 视角): 10000 -> 1.0 (胜), -10000 -> 0.0 (负)
                    fs = float(record["final_score"])
                    if fs > 9000: outcome = 1.0
                    elif fs < -9000: outcome = 0.0
                    else: outcome = 0.5
                else:
                    outcome = 0.5 # 兜底逻辑

                feat = parse_fen_to_features(record["fen"])
                
                # --- 基础样本 ---
                X.append(feat)
                y_outcome.append([outcome])
                y_eval.append([eval_score])
                
                # --- 水平镜像增强 ---
                if augment:
                    X.append(feat[HFLIP_INDICES])
                    y_outcome.append([outcome])
                    y_eval.append([eval_score])
                
                if max_samples and len(X) >= max_samples: break
            except:
                continue
            
    # 执行物理过采样 (权重)
    if weight > 1:
        X = X * weight
        y_outcome = y_outcome * weight
        y_eval = y_eval * weight
        
    return X, y_outcome, y_eval

# ─── 自动化 K 值搜索 ──────────────────────────────────────────────────────────

def find_best_k(X_val, y_out_val, y_eval_val):
    print("[搜索] 正在自动化寻找最优 K 值...")
    best_k = 600.0
    min_loss = float('inf')
    
    # 在 200 到 800 之间搜索
    for k in range(200, 850, 50):
        scaling = 2.302585 / k
        wr_out = y_out_val
        wr_eval = torch.sigmoid(y_eval_val * scaling)
        loss = torch.mean((wr_out - wr_eval)**2).item()
        
        if loss < min_loss:
            min_loss = loss
            best_k = float(k)
            
    print(f"[搜索] 最优 K 值定格为: {best_k}")
    return best_k

# ─── 导出与主程序 ────────────────────────────────────────────────────────────

def export_to_c(model, path):
    fc1_w = model.fc1.weight.data.numpy()
    fc1_b = model.fc1.bias.data.numpy()
    fc2_w = model.fc2.weight.data.numpy()
    fc2_b = model.fc2.bias.data.numpy()
    fc3_w = model.fc3.weight.data.numpy()
    fc3_b = model.fc3.bias.data.numpy()
    
    with open(path, 'w') as f:
        f.write("// Micro-NNUE Weights (Auto-generated)\n")
        f.write(f"#define NNUE_HIDDEN1_DIM {fc1_w.shape[0]}\n")
        f.write(f"#define NNUE_HIDDEN2_DIM {fc2_w.shape[0]}\n\n")
        
        fc1_w_t = fc1_w.T
        f.write(f"const float NNUE_W1[51][{fc1_w.shape[0]}] = {{\n")
        for row in fc1_w_t:
            f.write("    {" + ", ".join([f"{v:.6f}f" for v in row]) + "},\n")
        f.write("};\n\n")
        
        f.write(f"const float NNUE_B1[{fc1_b.shape[0]}] = {{\n")
        f.write("    " + ", ".join([f"{v:.6f}f" for v in fc1_b]) + "\n")
        f.write("};\n\n")
        
        fc2_w_t = fc2_w.T
        f.write(f"const float NNUE_W2_T[{fc2_w_t.shape[0]}][{fc2_w_t.shape[1]}] = {{\n")
        for row in fc2_w_t:
            f.write("    {" + ", ".join([f"{v:.6f}f" for v in row]) + "},\n")
        f.write("};\n\n")
        
        f.write(f"const float NNUE_B2[{fc2_b.shape[0]}] = {{\n")
        f.write("    " + ", ".join([f"{v:.6f}f" for v in fc2_b]) + "\n")
        f.write("};\n\n")
        
        f.write(f"const float NNUE_W3[{fc3_w.shape[1]}] = {{\n")
        f.write("    " + ", ".join([f"{v:.6f}f" for v in fc3_w[0]]) + "\n")
        f.write("};\n\n")
        f.write(f"const float NNUE_B3 = {fc3_b[0]:.6f}f;\n")
    print(f"✅ 权重已导出至: {path}")

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--data", type=str, default=TRAINING_CONFIG["main_data"], help="主训练数据路径")
    parser.add_argument("--endgame-data", type=str, default=TRAINING_CONFIG["endgame_data"], help="精选残杀数据路径")
    parser.add_argument("--endgame-weight", type=int, default=TRAINING_CONFIG["endgame_weight"], help="残局数据过采样权重 (倍数)")
    parser.add_argument("--epochs", type=int, default=TRAINING_CONFIG["epochs"])
    parser.add_argument("--batch-size", type=int, default=TRAINING_CONFIG["batch_size"])
    parser.add_argument("--hidden1", type=int, default=TRAINING_CONFIG["hidden1"])
    parser.add_argument("--hidden2", type=int, default=TRAINING_CONFIG["hidden2"])
    parser.add_argument("--lr", type=float, default=TRAINING_CONFIG["lr"])
    parser.add_argument("--lbda", type=float, default=TRAINING_CONFIG["lbda"], help="胜负预测与分值预测的权重比例 (0.0=纯分值, 1.0=纯胜负)")
    parser.add_argument("--keep-mates", action="store_true", help="是否在普通数据中保留绝杀分局面")
    parser.add_argument("--load-model", type=str, default=TRAINING_CONFIG["load_model"], help="加载既有模型（.pth）进行微调")
    parser.add_argument("--alpha", type=float, default=TRAINING_CONFIG["alpha"], help="双尺度混合权重")
    parser.add_argument("--K1", type=float, default=TRAINING_CONFIG["K1"])
    parser.add_argument("--K2", type=float, default=TRAINING_CONFIG["K2"])
    args = parser.parse_args()

    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    print(f"[设备] 使用: {device}")

    # 1. 加载主数据与残局混合数据
    X1, y_out1, y_eval1 = load_nnue_dataset(args.data, augment=True, weight=1)
    X2, y_out2, y_eval2 = load_nnue_dataset(args.endgame_data, augment=True, weight=args.endgame_weight)
    
    # 合并
    all_X_list = X1 + X2
    all_y_out_list = y_out1 + y_out2
    all_y_eval_list = y_eval1 + y_eval2
    
    if not all_X_list:
        print("[!] 错误: 未加载到任何有效数据。请检查文件路径。")
        return

    all_X = torch.tensor(np.array(all_X_list))
    all_y_out = torch.tensor(np.array(all_y_out_list), dtype=torch.float32)
    all_y_eval = torch.tensor(np.array(all_y_eval_list), dtype=torch.float32)
    
    print(f"[混合] 加载完成。主数据: {len(X1)}，残局增强: {len(X2)}，总计: {len(all_X)}")
    
    # 划分验证集用于 K 值搜索
    n_val = min(5000, len(all_X) // 10)
    indices = torch.randperm(len(all_X))
    val_idx, train_idx = indices[:n_val], indices[n_val:]
    
    X_train, y_out_train, y_eval_train = all_X[train_idx], all_y_out[train_idx], all_y_eval[train_idx]
    X_val, y_out_val, y_eval_val = all_X[val_idx], all_y_out[val_idx], all_y_eval[val_idx]

    # 2. 物理常数设定 (由 TRAINING_CONFIG 读取)
    # best_k 不再需要搜索

    dataset = TensorDataset(X_train, y_out_train, y_eval_train)
    loader = DataLoader(dataset, batch_size=args.batch_size, shuffle=True)
    
    # 3. 定义模型与优化器
    model = MicroNNUE(hidden1_dim=args.hidden1, hidden2_dim=args.hidden2).to(device)
    
    if args.load_model and os.path.exists(args.load_model):
        print(f"[微调] 正在加载模型: {args.load_model} ...")
        # 兼容性处理：如果模型结构不匹配，仅加载匹配部分或报错
        try:
            model.load_state_dict(torch.load(args.load_model, map_location=device))
            print("  ✅ 成功加载既有权重。")
        except Exception as e:
            print(f"  [!] 加载失败: {e}。将从随机初始化开始。")

    optimizer =  optim.AdamW(model.parameters(), lr=args.lr, weight_decay=1e-5)
    
    scheduler = optim.lr_scheduler.ReduceLROnPlateau(
        optimizer, mode='min', factor=0.5, patience=5
    )
    
    # 4. 训练循环
    print(f"[训练] 开始训练 {args.epochs} 轮... (lbda={args.lbda})")
    model.train()
    for epoch in range(args.epochs):
        epoch_loss = 0
        lbda = args.lbda
        
        for batch_X, batch_y_out, batch_y_eval in loader:
            batch_X, batch_y_out, batch_y_eval = batch_X.to(device), batch_y_out.to(device), batch_y_eval.to(device)
            
            optimizer.zero_grad()
            outputs = model(batch_X)
            loss = dual_scale_sigmoid_loss(outputs, batch_y_out, batch_y_eval, lbda=lbda, K1=args.K1, K2=args.K2, alpha=args.alpha)
            loss.backward()
            optimizer.step()
            epoch_loss += loss.item()
            
        avg_loss = epoch_loss / len(loader)
        current_lr = optimizer.param_groups[0]['lr']
        print(f"  Epoch [{epoch+1:>3}/{args.epochs}]  LR: {current_lr:.6f}  Loss: {avg_loss:.8f}")
        
        scheduler.step(avg_loss)

    # 4. 导出
    model.cpu()
    os.makedirs("data/nnue", exist_ok=True)
    torch.save(model.state_dict(), "data/nnue/micro_nnue_v2.pth")
    export_to_c(model, "core/nnue_weights.h")
    print("✨ 训练完成，项目已物理回滚至原始状态。")

if __name__ == "__main__":
    main()
