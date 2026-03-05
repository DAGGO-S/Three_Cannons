# 棋力提升方案

> 目标：在 Alpha-Beta + 手写评估函数的框架下，最大化棋力。

---

## 现状分析

| 项目     |      状态       | 说明                            |
| :------- | :-------------: | :------------------------------ |
| 搜索算法 | ✅ 完成度 70-75% | PVS、置换表、静默搜索、迭代加深 |
| 评估函数 |   ⚠️ 4 个维度    | 兵力、位置、贴炮、控制区        |
| 深度 10  |      15秒       | 已优化                          |
| 深度 15  |      >60秒      | 不可用                          |

### 核心问题

1. **搜索深度受限**：深度每增加 1 层，时间约增 2.5 倍
2. **评估函数是固定的超参数**：无法自动学习新特征
3. **深度 6 vs 深度 15 的差距**：50% 是深度限制，50% 是评估函数精度

---

# 第一类：加快单次计算速度

## 1.1 get_valid_moves 优化

**当前问题**：

```python
cdef list directions = [(0,1),(0,-1),(1,0),(-1,0)]  # 每次重建
if self.is_within_bounds(tr,tc):                     # 函数调用开销
```

**优化方案**：

| 问题                  | 改进                | 提升  |
| :-------------------- | :------------------ | :---: |
| directions 重复创建   | 模块级 `cdef tuple` |  5%   |
| is_within_bounds 调用 | 内联 `0 <= r < 5`   |  10%  |
| 炮两次循环            | 合并为 1 次         |  3%   |

**优化后代码**：

```python
cdef tuple DIRECTIONS = ((0,1),(0,-1),(1,0),(-1,0))

def get_valid_moves(self, cint r, cint c):
    for dr, dc in DIRECTIONS:
        tr, tc = r + dr, c + dc
        if 0 <= tr < 5 and 0 <= tc < 5:  # 内联
            if self.board[tr][tc] == EMPTY:
                moves.append((tr, tc))
                if piece == CANNON:  # 合并跳吃检查
                    jr, jc = tr + dr, tc + dc
                    if 0 <= jr < 5 and 0 <= jc < 5 and self.board[jr][jc] == SOLDIER:
                        moves.append((jr, jc))
```

**预期提升**：15-20%

---

## 1.2 move_piece 的 tuple 转换

**当前问题**：

```python
new_board_list = [list(row) for row in self.board]   # tuple → list
new_state.board = tuple(tuple(row) for row in ...)   # list → tuple
```

每次走法都做 2 次转换。

**优化方案**：

- 方案 A：棋盘内部保持 list，只在哈希时转换
- 方案 B：使用 numpy array

**预期提升**：10-15%

---

## 1.3 评估函数缓存键

**当前问题**：

```python
cache_key = (frozenset(soldiers), frozenset(cannons), hash(str(state.board)))
```

`hash(str(board))` 将整个棋盘转成字符串再哈希。

**优化方案**：直接用 `state.hash`

```python
cache_key = (frozenset(soldiers), frozenset(cannons), state.hash)
```

**预期提升**：5-10%

---

## 1.4 走法缓存

**当前问题**：同一位置的 `get_valid_moves` 被多处调用

**优化方案**：

```python
cdef dict _moves_cache = {}

def get_valid_moves(self, r, c):
    key = (self.hash, r, c)
    if key in _moves_cache:
        return _moves_cache[key]
    moves = self._compute_moves(r, c)
    _moves_cache[key] = moves
    return moves
```

**预期提升**：15-20%

---

# 第二类：提高搜索效率（同等时间搜更深）

## 2.1 历史启发表

**原理**：记录导致剪枝的走法，未来优先搜索。

**实现**：

```python
cdef dict history_table = {}

# 在剪枝处更新
if beta <= alpha:
    history_table[move] = history_table.get(move, 0) + depth * depth
    break

# 在走法排序中使用
quiet_moves.sort(key=lambda m: history_table.get(m, 0), reverse=True)
```

**预期提升**：剪枝效率 +25%

---

## 2.2 LMR（晚走法削减）

**原理**：排序靠后的走法减少搜索深度。

**实现**：

```python
for i, move in enumerate(ordered_moves):
    reduction = 0
    if i >= 3 and depth >= 3 and not is_capture(move):
        reduction = 1
        if i >= 6:
            reduction = 2
    
    evaluation = _alpha_beta(new_state, depth - 1 - reduction, ...)
    
    # 如果结果有趣，重新完整搜索
    if evaluation > alpha and reduction > 0:
        evaluation = _alpha_beta(new_state, depth - 1, ...)
```

**预期提升**：同等时间多搜 1-2 层

---

## 2.3 Killer Moves

**原理**：记录同层导致剪枝的走法。

```python
killer_moves = {}  # {depth: [move1, move2]}

def update_killer(move, depth):
    if depth not in killer_moves:
        killer_moves[depth] = [None, None]
    if killer_moves[depth][0] != move:
        killer_moves[depth][1] = killer_moves[depth][0]
        killer_moves[depth][0] = move
```

**预期提升**：5-10%

---

## 第四阶段：AI 棋力提升

- [x] 分析历史启发表实现方案
- [x] 分析评估函数改进方案
- [x] 生成改进建议文档
- [x] 规划“人机协同调参”教练系统原型

# 第三类：改进评估函数

## 3.1 增加战术评估维度

当前只有静态维度，缺少对**未来 1-2 步威胁**的感知。

### 炮的威胁强度分

```python
def _calculate_cannon_threat_score(state, cannons):
    for r, c in cannons:
        for end_r, end_c in state.get_valid_moves(r, c):
            if state.board[end_r][end_c] == SOLDIER:
                threat_score += 50  # 能吃兵
            elif abs(r - end_r) == 2 or abs(c - end_c) == 2:
                threat_score += 15  # 能预瞄
```

### 兵的围堵形态分

```python
def _calculate_formation_score(soldiers, cannons):
    for cannon_r, cannon_c in cannons:
        adjacent = sum(1 for dr, dc in DIRECTIONS
                       if (cannon_r+dr, cannon_c+dc) in soldiers)
        if adjacent >= 3: score -= 200  # 快围死
        elif adjacent >= 2: score -= 80
```

### 炮的机动性分

```python
def _calculate_mobility_score(state, cannons, soldiers):
    for r, c in cannons:
        safe_moves = len([m for m in state.get_valid_moves(r, c)
                          if not surrounded(m, soldiers)])
        score += safe_moves * 20
```

**预期提升**：等效 +2 层搜索深度

---

## 3.2 参数调优：从“手调”进化到“教练模式”

### 方案 A：增量自对弈 (低效)
1. **每次只改一个参数**，进行 50 局对战。
2. 胜率 > 55% 才更新。这种方式对参数间的耦合（如兵力分与位置分的关系）处理较差。

### 方案 B：人机协同监督学习 (高效/精准) — [推荐]
**核心逻辑**：利用人类的棋觉（Intuition）作为标注，让机器通过优化算法自动拟合参数。

1. **采样标注**：在深度 0 节点，让 AI 给出 Top 3 走法。如果你认为 AI 的 Top 1 错了，手动指出正确的 Move。
2. **目标设定**：优化算法自动调整所有 48+ 个参数，使得 `Score(正确走法) > Score(其他所有走法)`。
3. **算法选择**：使用 **Rank Loss（排序损失）** 配合 **CMA-ES** 或 **线性回归** 进行参数拟合。

**优势**：不需要漫长的自对弈，直接将人类的战术理解“蒸馏”进评估函数中。

---

# 第四类：极限突破（高工作量）

## 4.1 位棋盘（Bitboard）

用 25 位整数表示棋盘，走法生成/判断用位运算。

**预期提升**：2-3 倍（不是 10 倍）

**原因**：
- 10 倍提升适用于国际象棋（64 格，滑动走法复杂）
- "三炮十五兵"只有 25 格，走法简单（最多看 2 格）
- 位棋盘的核心优势用不上

**结论**：工作量大，收益有限，**不推荐**。

---

## 4.2 神经网络评估函数

用小型神经网络替代手写评估函数，通过自博弈学习。

**优势**：能发现人类没想到的局面特征

**劣势**：训练时间长，不适合个人开发者

---

# 总结

## 推荐优先级

| 改进                     | 类型     | 工作量  | 预期效果         |
| :----------------------- | :------- | :-----: | :--------------- |
| **历史启发表**           | 搜索效率 | 30 分钟 | +25% 剪枝        |
| **LMR**                  | 搜索效率 | 1 小时  | 同等时间 +1-2 层 |
| **get_valid_moves 内联** | 计算速度 | 30 分钟 | +15-20%          |
| **战术评估维度**         | 评估精度 | 1 小时  | 等效 +2 层       |
| **缓存键优化**           | 计算速度 | 5 分钟  | +5-10%           |

## 诚实的预期

在不引入神经网络的前提下：

- **可以做到**：深度 10 接近深度 12-13
- **做不到**：深度 6 接近深度 15

原因：评估函数的**表达能力有限**，只有人类设计的 4-6 个维度，无法替代真正的深度搜索。
