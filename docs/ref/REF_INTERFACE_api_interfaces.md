# 三炮十五兵：API 接口文档

本文档详细说明各核心类的公开接口、参数类型和使用示例。

---

## GameState：core/game_logic.pyx

游戏局面的不可变表示类。

### 属性

| 属性 | 类型 | 说明 |
| :--- | :--- | :--- |
| `board` | `tuple` | 5×5 棋盘。0 为空，1 为兵，2 为炮 |
| `current_player` | `int` | 当前行动方。炮方为 2，兵方为 1 |
| `winner` | `int \| None` | 胜方。None 表示未结束，3 表示和棋 |
| `soldier_count` | `int` | 剩余兵数。范围为 0 至 15 |
| `hash` | `int` | Zobrist 哈希值 |

### 方法

#### `__init__(board=None, current_player=2)`

创建新局面。

#### `get_valid_moves(r, c)`

获取指定位置棋子的所有合法目标位置。

#### `move_piece(start_r, start_c, end_r, end_c)`

执行走法，返回新的局面。若走法非法，将抛出异常。

---

## GameModel：game_model.py

游戏数据管理器。

### 属性

| 属性 | 类型 | 说明 |
| :--- | :--- | :--- |
| `game_state` | `GameState` | 当前局面 |
| `move_history` | `list` | 历史记录 |
| `selected_piece` | `tuple \| None` | 选中的棋子坐标 |
| `is_replay_mode` | `bool` | 复盘模式激活状态 |
| `replay_index` | `int` | 当前复盘位置 |
| `position_counts` | `Counter` | 局面出现次数。用于三复局判定 |

### 方法

#### `reset()`

重置游戏到初始状态。

#### `make_move(start_pos, end_pos)`

执行走法，自动处理历史记录和和棋检测。

#### `load_state_from_history(index)`

加载历史局面。

---

## AIEngine：ai_engine.py

异步 AI 计算管理器。

### 属性

| 属性 | 类型 | 说明 |
| :--- | :--- | :--- |
| `current_best_move` | `tuple \| None` | 计算过程中的当前最佳走法 |

### 方法

#### `is_calculating()`

AI 运算状态检索。

#### `start_calculation(game_state, config, on_complete, on_progress, history)`

启动异步 AI 计算。

参数：
- `game_state`：当前局面。
- `config`：包含搜索深度、时间限制、引擎模式、线程数、神经网络使用开关等配置。
- `on_complete`：完成回调。
- `on_progress`：进度回调。
- `history`：历史哈希列表。用于三复局判定。

#### `stop_calculation()`

停止正在进行的计算。

---

## 相关文档

- [模块概览](REF_ARCH_modules_overview.md)
- [架构设计](REF_ARCH_architecture.md)
- [快速入门](../guides/GUIDE_getting_started.md)
