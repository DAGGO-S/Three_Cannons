# NNUE 物理基准与实测数据 (2026-03-24)

## 1. 神经网络与训练物理配置

- **网络结构 (MicroNNUE)**: 51 维输入 -> 256 隐藏层 -> 32 隐藏层 -> 1 维输出。
- **输入特征**: 25 (Soldier Positions) + 25 (Cannon Positions) + 1 (Side-to-Move)。
- **核心损失函数**: `sigmoid_loss(prediction, target_outcome, target_eval, lbda=0.0, K=600.0)`。
  - `scaling = 2.302585 / 600.0`
  - `pred_winrate = torch.sigmoid(prediction * scaling)`
  - `target_winrate = torch.sigmoid(target_eval * scaling)`
  - `loss = (eval_weight * (pred_winrate - target_winrate)**2).mean()`
- **当前训练超参数**:
  - `epochs`: 30
  - `batch_size`: 1024
  - `learning_rate`: 1e-3 (AdamW)
  - `lbda`: 0.0 (仅分值回归)
  - `endgame_weight`: 5 (残局数据过采样权重)
- **数据集构成**:
  - **主数据集 (`run3.jsonl`)**: 351,259 样本 (占比 86.67%)
  - **残局必杀集 (`pure_mates.jsonl`)**: 10,804 样本 (原始占比 2.98%)
  - **加权后必杀占比**: **13.33%** (5x 过采样)
- **权重来源 ：**
  - 物理核查证实：`core/nnue_weights.h` 与 `core/nnue_weights-N1.h` 内容 **不一致**。
  - **权重文件**: `core/nnue_weights.h` (当前被引擎编译挂载的物理实体)。
- **特征映射协议 ：**:
  - 输入为 **绝对坐标**（0-24 兵，25-49 炮），不随先手方旋转对称。
  - STM (Side-to-Move) 作为独立特征位（第 50 位）显式输入。
  - **结论**: 神经网络物理结构要求目标的 **绝对一致性视角**。
- **训练目标映射 ：**:
  - `final_score > 9000` 物理映射为 `outcome = 1.0` (炮胜)。
  - `final_score < -9000` 物理映射为 `outcome = 0.0` (兵胜)。
  - 在 `scripts/nnue_trainer.py` 第 140-144 行物理实现。
  - **当前测试版本**: 基于 `core/nnue_weights.h` 已训练版本。
- **引擎终端与循环判定 ：**:
  - **三手重复**: 局面出现第 3 次时触发循环判定。
  - **动态平局判定**:
    - 兵数 **>= 9**: 循环局面判平局 (`0.0`)，强制兵方进攻。
    - 兵数 **<= 8**: 循环局面判炮胜 (`5000.0`)，奖励炮方顽强防御。
  - **极值常数**: 搜索终端分值为 `±10000.0`。
  - 以上逻辑在 `core/engine.pyx` 第 66-75 行物理实现。
- **数值精度与部署**:
  - **核心计算**: 采用 `float32` 浮点精度。 推理引擎通过 AVX2 向量化实现 256x32 位宽点积加速

## 2. 采样验证数据对照表 (10 Cases)

数据源：`data/selfplay/pure_mates.jsonl`，评估引擎：当前编译版 (N1 基础)。

| FEN 局面 (前缀)                | NNUE (D0) | Search (D2) | Search (D10) | 环境状态     |
| :----------------------------- | :-------- | :---------- | :----------- | :----------- |
| `s1s1s/4s/s1ssc/1scss/1s1c1 s` | -722.75   | 715.83      | 10000.00     | 非终局       |
| `5/2s1s/s1ssc/sssss/c3c c`     | -559.64   | -706.83     | -10000.00    | 非终局       |
| `5/2s1s/s1ssc/sssss/c2c1 s`    | -692.83   | 647.34      | 10000.00     | 非终局       |
| `5/2s1s/1sssc/sssss/c2c1 c`    | -609.50   | -577.48     | -10000.00    | 非终局       |
| `5/2s1s/1sssc/sssss/c3c s`     | -517.87   | 705.65      | 10000.00     | 非终局       |
| `5/2s1s/1sssc/s1sss/cs2c c`    | -577.48   | -633.65     | -10000.00    | 非终局       |
| `5/2s1s/1sssc/s1sss/cs1c1 s`   | -513.92   | 795.50      | 10000.00     | 非终局       |
| `5/2s1s/2ssc/sssss/cs1c1 c`    | -470.63   | -10000.00   | -10000.00    | 非终局       |
| `5/2s1s/2ssc/sssss/cc3 s`      | -544.47   | 10000.00    | 10000.00     | 非终局       |
| `5/2s1s/2ssc/ss1ss/ccs2 c`     | -10000.00 | -10000.00   | -10000.00    | **终局状态** |

## 5. 实验结论

### 5.1 拟合突破：梯度饱和物理破解
通过引入 **双尺度损失函数 (Dual-Scale Loss, K1=600, K2=10000)**，预测上限从原本的 `-700` 量级推升至 **`-7000` 至 `-12000`** 区间。

低置信度：但神经网络的泛化特性导致其在可能存在问题。

- **低置信度建议**：**引入独立的残局库 (Tablebase)**。
- **角色分工**：
    1. **NNUE**：负责在全盘和近残局阶段。
    2. **残局库**：负责在棋子数的终结阶段提供的逻辑真值。

---

## 3. 历史任务状态审计 (Audit)

- `docs/tasks/TASK_NNUE_FITTING.md` (记录值):
  - `[X] 状态`: 逻辑重整、脚本规范化、物理修复 (双尺度 Sigmoid)。
  - `Discovery Rate`: 0.00% (深度 1-8 搜索下)。失败，仍然无法到达-10000

低置信度推测

因为sigmoid的归一化，导致1000和10000的胜率变化极低，所以训练缓慢，目前的loss在0.06左右，就无法下降了。

线性的问题是-200至200的数据被牵引，导致错误的跑到了-5000量级。案例，开局本应该-200左右，AI引擎识别为-5000，接近被必杀。且数据混乱。

---

最后更新：2026-03-24

## 4. 补充调查：六项高置信度事实

### 4.1 `sigmoid_loss` 物理代码解析

文件 `scripts/nnue_trainer.py` (行 73-87) 源码：

```python
def sigmoid_loss(prediction, target_outcome, target_eval, lbda=0.0, K=600.0):
    scaling = 2.302585 / K
    pred_winrate = torch.sigmoid(prediction * scaling)
    target_winrate = torch.sigmoid(target_eval * scaling)
  
    # eval_weight 定义: 基于目标分数绝对值线性缩放，范围 [1.0, 2.0]
    eval_weight = 1.0 + torch.abs(target_eval) / 10000.0
  
    loss_eval = (eval_weight * (pred_winrate - target_winrate)**2).mean()
    loss_outcome = (eval_weight * (pred_winrate - target_outcome)**2).mean()
    return lbda * loss_outcome + (1.0 - lbda) * loss_eval
```

### 4.2 `prediction` 原始数值分布实测

测试目标：当前编译版引擎 `core/nnue_weights.h` (基于微调模型)
测试集：`pure_mates.jsonl` (前 5000 条绝杀样本)

- **Sample count**: 5000
- **Mean**: -3209.00
- **Min**: -10000.00 (触发终局判定直接返回)
- **25% & Median**: -3136.19 / -2303.79 (绝大多数停留在该非极值区间)
- **Max**: -320.35

### 4.3 `target_eval` 全数据分布事实

通过 `tmp/data_stats.py` 计算所得真实文件分布：

- **`run3.jsonl` (351,259 条)**
  - `>= 9000` (正向极值): 13 条 (0.00%)
  - `<= -9000` (负向极值): 11,506 条 (3.28%)
- **`pure_mates.jsonl` (10,804 条)**
  - `>= 9000` (正向极值): 25 条 (0.23%)
  - `<= -9000` (负向极值): 10,779 条 (99.77%)

## 4. 补充调查：六项高置信度事实 (Data & Code Evidences)

### 4.1 `sigmoid_loss` 物理代码解析

文件 `scripts/nnue_trainer.py` (行 73-87) 源码：

```python
def sigmoid_loss(prediction, target_outcome, target_eval, lbda=0.0, K=600.0):
    scaling = 2.302585 / K
    pred_winrate = torch.sigmoid(prediction * scaling)
    target_winrate = torch.sigmoid(target_eval * scaling)
  
    # eval_weight 定义: 基于目标分数绝对值线性缩放，范围 [1.0, 2.0]
    eval_weight = 1.0 + torch.abs(target_eval) / 10000.0
  
    loss_eval = (eval_weight * (pred_winrate - target_winrate)**2).mean()
    loss_outcome = (eval_weight * (pred_winrate - target_outcome)**2).mean()
    return lbda * loss_outcome + (1.0 - lbda) * loss_eval
```

### 4.2 `prediction` 原始数值分布实测

测试目标：当前编译版引擎 `core/nnue_weights.h` (基于微调模型)
测试集：`pure_mates.jsonl` (前 5000 条绝杀样本)

- **Sample count**: 5000
- **Mean**: -3209.00
- **Min**: -10000.00 (触发终局判定直接返回)
- **25% & Median**: -3136.19 / -2303.79 (绝大多数停留在该非极值区间)
- **Max**: -320.35

### 4.3 `target_eval` 全数据分布事实

通过 `tmp/data_stats.py` 计算所得真实文件分布：

- **`run3.jsonl` (351,259 条)**
  - `>= 9000` (正向极值): 13 条 (0.00%)
  - `<= -9000` (负向极值): 11,506 条 (3.28%)
- **`pure_mates.jsonl` (10,804 条)**
  - `>= 9000` (正向极值): 25 条 (0.23%)
  - `<= -9000` (负向极值): 10,779 条 (99.77%)

### 4.4 `run3.jsonl` 状态判定与推修正 (Correction)

- **实测回顾**: 用户使用 **N1 NNUE + 深度 10/12** 对 `run3.jsonl` 进行抽样验证。
- **物理事实**: 所有绝杀局面（-10000）均实现了 **对齐 (YES)**。
- **推论修正**: 此前通过 `tmp/audit_shift.py` (使用非 N1 权重) 观测到的“错位”是由于**评估器权重不匹配**导致的假象。
- **最终结论**: `run3.jsonl` 的数据标签与 N1 基准物理一致，**不存在系统性 One-Ply Shift 污染**。

### 4.5 三端分数视角一致性审计

1. **`relabel_data_deep.py`**: 直接使用引擎返回分数。基于高置信度事实：“引擎是单一视角的（绝对炮视角）”，因此这里无需反转，记录的分数本身就是绝对炮视角。
2. **`self_play_generator.py`**: 直接记录搜索分值，由于引擎单一视角，其生成的数据理论上应为绝对视角。
3. **`nnue_trainer.py`**: 强制规定 `>9000` = 炮胜 (`1.0`)，`<-9000` = 兵胜 (`0.0`)（与单一引擎绝对视角相匹配）。

- **结论调整**: 根据物理事实，底层引擎、数据打标和训练层的视角在**设计逻辑上是统一的（绝对炮视角）**。

### 4.6 Mate Discovery Rate 测试标准

基于 `tmp/verify_fitting.py` 代码逻辑：

- 调用 `evaluate_nnue_python(state)` 输出绝对分数。
- 如果该绝对分数 `|score| >= 10000.0`，则判定为成功发现绝杀。
- 由于 `core` 仅在终局（`winner != -1`）才物理返回极值，非终局状态的 NNUE 最大预测能力（-3136）远未触达。
