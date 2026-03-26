# Texel 自动化调优系统说明 (`scripts/value_tuning_analysis/texel_tuner.py`)

该脚本是为 **Three Cannons** 引擎量身定制的评估参数自动优化工具。它通过分析海量“自对弈”历史数据，反求最能反映真实胜率的评估权重。

## 核心功能

### 1. 参数向量化与对称约束
系统将引擎的静态评估逻辑拆解为 **37 维** 可调参数。
- **子力分 (15维)**：1-15 个兵的剩余价值。
- **贴炮惩罚 (1维)**：兵被炮邻接时的威慑扣分。
- **控制区映射 (6维)**：安全格数对应的得分映射。
- **位置分 (15维)**：5x5 棋盘的位置权重，**强制左右对称**（col0=col4, col1=col3），确保调优结果的稳定性。

### 2. 数学原理：Texel Tuning
核心目标是最小化 **均方误差 (MSE)**：
$$MSE = \frac{1}{N} \sum (Outcome - Sigmoid(EvalScore, K))^2$$
其中 $Sigmoid$ 函数将引擎的整数分数映射为 $0 \sim 1$ 的预估胜率。脚本使用**黄金分割法**自动搜索最优的 $K$ 值，使评分尺度与真实胜率完美对齐。

### 3. GPU 加速机制 (CuPy)
脚本支持自动后端切换：
- **实现方式**：通过 `setup_backend` 探测 `cupy` 库。若存在，则将 `np` 指向 `cupy`，否则指向 `numpy`。
- **加速点**：评估函数中的矩阵乘法（位置分）和向量化运算（子力、贴炮）在显卡上并行执行。
- **混合计算**：位运算（BFS 控制区计算）在 CPU 上完成，数值统计和误差反传在 GPU 上完成。

### 4. 稳定性增强：单调性钳制 (Monotonicity Constraints)
为了防止过度拟合导致参数变得“诡异”，系统强制执行以下规则：
- **子力递减**：兵越多，对方炮的威胁越大，因此 1 兵局面的分值必须 $\ge$ 2 兵 $\ge$ ... $\ge$ 15 兵。
- **控制区递增**：兵方控制的格子越多，分数必须越高。
- **执行方式**：在坐标下降的尝试步中，若新参数破坏单调性，则该方向的优化动作直接被拦截（Skipped）。

### 5. 断点续训 (Checkpoint)
针对大规模数据集（如 50 万条以上）设计的保护机制：
- **存储**：每迭代一轮，自动更新 `data/tuning/checkpoint.json`。
- **恢复**：程序启动时重读参数、当前步长（Step）、迭代轮次及最优 K 值。
- **参数说明**：
    - `--reset`: 强制清除旧断点，从头开始。

# 常用命令

```bash
# 1. 快速测试（1000样本，3轮）
python scripts/texel_tuner.py --max-samples 1000 --epochs 3

# 2. 标准生产训练
python scripts/texel_tuner.py --max-samples 100000 --epochs 50

# 3. 结果微调（在之前训练出的 tuned_weights.json 基础上再跑 20 轮）
python scripts/texel_tuner.py --weights data/tuning/tuned_weights.json --epochs 20

# 4. 指定已知的最优 K 值（跳过 K 搜索以提速）
python scripts/texel_tuner.py --k-value 0.75
```

## 故障排除 (GPU)
如果显示 `[后端] NumPy (CPU)`，请检查：
1. 验证 CuPy 环境配置: `pip install cupy-cudaXXx` (对应物理 CUDA 版本)。
2. 确认 GPU 驱动运行状态。
3. 检查控制台输出的导入错误详情。

## 交付产出
训练结束后，除了生成 `tuned_weights.json` 外，控制台会直接输出：
1. 可直接粘贴到 `evaluation_logic.pyx` 的 `DEFAULT_SETTINGS` 字典。
2. 可直接粘贴到 C 初始化函数中的代码片段，无需人工换算。
