# Phase 3 可行性分析：从 11万 NPS 到 100万 NPS

> 文档目的：批判性分析"将 board 从 tuple-of-tuples 重构为 C 数组并实现 Make/Unmake"的可行性、代价和预期收益。

## 当前瓶颈的精确定位

通过 Dumb Eval 对照实验已证实：**评估函数开销为零**。11 万 NPS 的硬顶完全由 `move_piece` 中的三行热代码决定：

```python
# game_logic.pyx L115-127 —— 每次搜索节点都执行
new_board_list = [list(row) for row in self.board]     # ① 5 个 tuple→list 转换
new_board_list[end_r][end_c] = piece                   # ② 修改（唯一有用的工作）
new_state.board = tuple(tuple(row) for row in ...)     # ③ 5 个 list→tuple 转换
```

① 和 ③ 各触发 5 次 Python 对象创建+销毁。在 11 万 NPS 下，每秒发生 **110 万次** 微小内存分配/释放。这是 Python 内存管理器（pymalloc）的物理极限。

---

## 方案一览

| 方案                                | 预期 NPS    | 工作量 | 风险 | 上层兼容 |
| ----------------------------------- | ----------- | ------ | ---- | -------- |
| A. C 数组 + Make/Unmake（全量重构） | 100万~200万 | **大** | 高   | 需适配   |
| B. C 数组 + Copy（折中方案）        | 50万~80万   | **中** | 中   | 需适配   |
| C. 仅优化 move_piece 热路径         | 20万~30万   | **小** | 低   | 完全兼容 |

---

## 方案 A：C 数组 + Make/Unmake（全量重构）

### 核心改造

将 `GameState` 改为 `cdef class`，board 改为 `cdef int board[25]`：

```python
# 改造后的 game_logic.pyx（伪代码）
cdef class GameState:
    cdef int board[25]         # 1D C 数组，25 个 int
    cdef int current_player
    cdef int winner
    cdef int soldier_count
    cdef unsigned long long hash

    cdef void make_move(self, int start, int end):
        """原地修改棋盘，无内存分配"""
        self.board[end] = self.board[start]
        self.board[start] = EMPTY

    cdef void unmake_move(self, int start, int end, int captured):
        """撤销走法，恢复棋盘"""
        self.board[start] = self.board[end]
        self.board[end] = captured
```

### 影响范围分析（精确到文件）

| 文件                             | 引用方式                                           | 改动程度                    |
| -------------------------------- | -------------------------------------------------- | --------------------------- |
| `core/game_logic.pyx`            | `self.board[r][c]` (2D) → `self.board[r*5+c]` (1D) | **重写**                    |
| `core/evaluation_logic.pyx`      | `state.board[sr][sc]` 遍历构建 set                 | **中等修改**                |
| `core/ai.pyx`                    | `state.move_piece(...)` 调用                       | **需改为 make/unmake 模式** |
| `core/zobrist_hashing.pyx`       | `compute_hash(list board, ...)`                    | **需改为接受 C 数组**       |
| `src/view/main_window.py`        | `state.board[r][c]` 只读                           | 需兼容层                    |
| `src/controller/orchestrator.py` | `state.board[r][c]` 只读                           | 需兼容层                    |
| `src/model/game_model.py`        | `move_piece(...)` 调用                             | 需适配新接口                |
| `src/io/game_io.py`              | `state.board[r][c]` 只读                           | 需兼容层                    |
| `tests/*.py` (7个文件)           | 各种 board 访问                                    | 需全部更新                  |

### 关键难点

1. **`cdef class` 不能被 pickle 序列化**：当前 `GameState` 被用于历史记录（`game_model.py` 的 `history` 列表）。`cdef class` 需要手动实现 `__reduce__` 方法。
2. **上层 Python 代码无法直接读取 `cdef int board[25]`**：需要额外提供 `def get_board_2d(self)` 的 Python 可调用接口供 GUI 使用（但这个只在渲染时调用，不在热路径上，开销可忽略）。
3. **Make/Unmake 需要重构搜索主循环**：当前 `_alpha_beta` 中使用 `new_state = state.move_piece(...)` 的不可变风格，需要改为：
   ```python
   state.make_move(start, end)
   score = _alpha_beta(state, depth-1, ...)
   state.unmake_move(start, end, captured)
   ```
   这会深刻改变搜索函数的控制流，是最危险的部分。
4. **历史状态保存**：不可变设计的天然优势是历史状态自动保存。Make/Unmake 下，撤销不完整会污染全局状态，调试极其困难。

### 预期收益

- `move_piece` 的 3 行热代码 → 2 行 C 整数赋值（零分配）
- Zobrist hash 增量更新保持不变（已经是 O(1)）
- `_check_winner` 直接读 C 数组（无 Python 对象解包）
- **保守估计 8-10x 加速，NPS 从 11万 → 100万~200万**

---

## 方案 B：C 数组 + memcpy 复制（折中方案）

### 核心思路

保持"每次搜索节点创建新状态"的不可变风格，但用 C 数组 + `memcpy` 替代 tuple 重建。

```python
cdef class GameState:
    cdef int board[25]

    def move_piece(self, int start, int end):
        cdef GameState new_state = GameState.__new__(GameState)
        memcpy(new_state.board, self.board, 25 * sizeof(int))  # ~25 字节，1-2 CPU 周期
        new_state.board[end] = new_state.board[start]
        new_state.board[start] = EMPTY
        ...
        return new_state
```

### 优势
- **保持不可变语义**：上层代码改动最小，搜索代码风格不变
- **无 Make/Unmake 的调试噩梦**：每个节点的状态独立且安全
- **`memcpy` 25 个 int ≈ 100 字节**：在 L1 Cache 内完成，耗时 < 10 纳秒

### 劣势
- 仍然需要为每个节点创建 `GameState` 对象（Python 对象分配），这本身约 0.5-1 微秒
- 速度上限比 Make/Unmake 低，但远好于现状

### 预期收益

- **保守估计 4-6x 加速，NPS 从 11万 → 50万~80万**

---

## 方案 C：仅优化 move_piece 热路径（最小改动）

### 核心思路

不改 `GameState` 的类定义和 board 存储方式，只优化 `move_piece` 内部的 tuple 重建逻辑。

```python
def move_piece(self, start_r, start_c, end_r, end_c):
    # 只重建被修改的 1-2 行，而不是全部 5 行
    cdef tuple row_start = self.board[start_r][:start_c] + (EMPTY,) + self.board[start_r][start_c+1:]
    cdef tuple row_end = self.board[end_r][:end_c] + (piece,) + self.board[end_r][end_c+1:]
    ...
```

### 优势
- **改动极小**：只动 `move_piece` 一个函数
- **零风险**：不涉及类型变更、接口变更

### 劣势
- 仍然在 Python 层创建 tuple 对象，加速幅度有限
- 只是减少了"无意义重建"的行数（从5行→1-2行），本质未变

### 预期收益

- **保守估计 2-3x 加速，NPS 从 11万 → 20万~30万**

---

## 批判性分析与推荐

### 关于"100 万 NPS"这个目标

这个目标**在技术上完全可行**（方案 A），但需要清醒认识代价：

|                  | 方案 A           | 方案 B               | 方案 C       |
| ---------------- | ---------------- | -------------------- | ------------ |
| **NPS**          | 100万~200万      | 50万~80万            | 20万~30万    |
| **额外搜索深度** | +4~5 层          | +3 层                | +1~2 层      |
| **工作量**       | 3-5 天全职       | 1-2 天               | 半天         |
| **破坏性**       | 几乎重写核心层   | 重写核心层，上层微调 | 仅改一个函数 |
| **调试难度**     | 极高（状态污染） | 中等                 | 低           |

### 我的推荐

**先做方案 B（C 数组 + memcpy 复制），后看情况决定是否升级到方案 A。**

理由：
1. 方案 B 能拿到 80% 的收益（50万~80万 NPS），但只需方案 A 40% 的工作量。
2. 方案 B 保持了不可变语义，不需要重写搜索主循环，调试简单。
3. 方案 B 是方案 A 的**必经之路**——无论如何你都需要先把 board 改为 C 数组。做完 B 之后，如果觉得需要更快，再叠加 Make/Unmake 即可。
4. 50万~80万 NPS 下，depth 15 在 3 秒内可达。结合残局表（≤4兵完美信息），棋力会有质的飞跃。

### 一般软件的参考

| 引擎                | 语言          | 棋盘大小 | NPS           | 说明                   |
| ------------------- | ------------- | -------- | ------------- | ---------------------- |
| 你的引擎（现在）    | Cython+Python | 5×5      | 11万          | tuple/list 重建        |
| python-chess        | 纯 Python     | 8×8      | 2万~5万       | 纯 Python 引擎         |
| Sunfish（教学引擎） | Python        | 8×8      | 1万~3万       | 极简设计               |
| 中等 C 引擎         | C/C++         | 8×8      | 200万~500万   | bitboard + make/unmake |
| Stockfish           | C++           | 8×8      | 2000万~5000万 | 极致优化 + NNUE        |
| 你的目标（方案 B）  | Cython        | 5×5      | 50万~80万     | C 数组 + memcpy        |

在 5×5 这种极小棋盘上，方案 B 的 50万~80万 NPS 已经非常接近**中等 C 引擎在 8×8 棋盘上的水平**。考虑到你的棋盘小得多，位置空间小得多，这已经是非常亮眼的成绩。
