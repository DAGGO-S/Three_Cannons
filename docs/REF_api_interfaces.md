# 三炮十五兵 AI版 - API 接口文档

本文档详细说明各核心类的公开接口、参数类型和使用示例。

---

## GameState (`core/game_logic.pyx`)

游戏局面的不可变表示类。

### 属性

| 属性 | 类型 | 说明 |
|:---|:---|:---|
| `board` | `tuple[tuple[int, ...], ...]` | 5×5 棋盘，0=空，1=兵，2=炮 |
| `current_player` | `int` | 当前行动方 (CANNON=2, SOLDIER=1) |
| `winner` | `int \| None` | 胜方，None 表示未结束，3=和棋 |
| `soldier_count` | `int` | 剩余兵数 (0-15) |
| `hash` | `int` | Zobrist 哈希值 |

### 方法

#### `__init__(board=None, current_player=CANNON)`

创建新局面。

```python
# 创建初始局面
state = GameState()

# 从自定义棋盘创建
custom_board = [[1,1,1,1,1], [1,1,1,1,1], [1,1,1,1,1], [0,0,0,0,0], [0,2,2,2,0]]
state = GameState(board=custom_board, current_player=SOLDIER)
```

#### `get_valid_moves(r: int, c: int) -> list[tuple[int, int]]`

获取指定位置棋子的所有合法目标位置。

```python
moves = state.get_valid_moves(4, 1)  # 获取 (4,1) 位置炮的合法走法
# 返回: [(3, 1), (4, 0), (4, 2), ...]
```

#### `move_piece(start_r, start_c, end_r, end_c) -> GameState`

执行走法，返回新的 GameState（原状态不变）。

```python
new_state = state.move_piece(4, 1, 3, 1)  # 炮从 (4,1) 移动到 (3,1)
```

> [!NOTE]
> 如果走法非法，将抛出 `ValueError`。

---

## GameModel (`game_model.py`)

游戏数据管理器。

### 属性

| 属性 | 类型 | 说明 |
|:---|:---|:---|
| `game_state` | `GameState` | 当前局面 |
| `move_history` | `list[GameState]` | 历史记录 |
| `selected_piece` | `tuple \| None` | 选中的棋子坐标 |
| `is_replay_mode` | `bool` | 是否处于复盘模式 |
| `replay_index` | `int` | 当前复盘位置 |
| `position_counts` | `Counter` | 局面出现次数（用于和棋检测） |

### 方法

#### `reset() -> None`

重置游戏到初始状态。

```python
model = GameModel()
model.reset()
```

#### `make_move(start_pos, end_pos) -> bool`

执行走法，自动处理历史记录和和棋检测。

```python
model.make_move((4, 1), (3, 1))  # 始终返回 True
```

#### `load_state_from_history(index: int) -> bool`

加载历史局面（进入复盘模式）。

```python
model.load_state_from_history(5)  # 跳转到第 5 步
```

#### `load_from_gamedata(initial_state, moves) -> None`

从棋谱数据加载完整对局。

```python
model.load_from_gamedata(initial_state, [
    ((4, 1), (3, 1)),
    ((2, 2), (3, 2)),
    # ...
])
```

---

## AIEngine (`ai_engine.py`)

异步 AI 计算管理器。

### 属性

| 属性 | 类型 | 说明 |
|:---|:---|:---|
| `current_best_move` | `tuple \| None` | 计算过程中的当前最佳走法 |

### 方法

#### `is_calculating() -> bool`

检查是否正在计算。

```python
if not engine.is_calculating():
    engine.start_calculation(...)
```

#### `start_calculation(game_state, config, on_complete_callback, progress_callback) -> None`

启动异步 AI 计算。

**参数**:
- `game_state`: `GameState` - 当前局面
- `config`: `dict` - AI 配置
- `on_complete_callback`: `Callable[[tuple | None], None]` - 完成回调
- `progress_callback`: `Callable[[int, float, tuple, list], None]` - 进度回调

**config 字典结构**:
```python
{
    "depth": 8,          # 最大搜索深度
    "time_limit": 15.0   # 时间限制（秒）
}
```

**进度回调参数**:
```python
def on_progress(depth, score, move, pv_line):
    """
    depth: int - 当前完成的搜索深度
    score: float - 当前评估分数
    move: tuple - 当前最佳走法 ((r1,c1), (r2,c2))
    pv_line: list - 主变化线
    """
    pass
```

#### `stop_calculation() -> None`

停止正在进行的计算。

```python
engine.stop_calculation()
# 停止后，on_complete_callback 会被调用，返回当前找到的最佳走法
```

---

## GameOrchestrator (`orchestrator.py`)

事件协调器。

### 构造函数

```python
orchestrator = GameOrchestrator(model, view, ai_engine, config)
```

### 事件处理方法

| 方法 | 触发条件 | 说明 |
|:---|:---|:---|
| `on_canvas_click(r, c)` | 点击棋盘 | 选择棋子或执行走法 |
| `on_new_game()` | 点击"新游戏" | 重置对局 |
| `on_calculate_move()` | 点击"计算一步" | 触发 AI 计算 |
| `on_stop_calculation()` | 点击"停止" | 停止 AI |
| `on_prev_move()` | 点击"上一步" | 复盘后退 |
| `on_next_move()` | 点击"下一步" | 复盘前进 |
| `on_first_move()` | 点击"首步" | 跳到开局 |
| `on_last_move()` | 点击"末步" | 跳到最新 |
| `on_save_game()` | 点击"保存" | 保存棋谱 |
| `on_load_game()` | 点击"加载" | 加载棋谱 |
| `on_open_settings()` | 点击"设置" | 打开设置对话框 |

---

## GameConfig (`game_config.py`)

游戏配置管理。

### 默认配置

```python
{
    "cannon_player": "Human",  # "Human" 或 "AI"
    "soldier_player": "AI",    # "Human" 或 "AI"
    "depth": 8,                # AI 搜索深度
    "time_limit": 15.0         # AI 时间限制（秒）
}
```

### 方法

#### `get_all() -> dict`

获取所有配置的副本。

#### `update(new_settings: dict) -> None`

批量更新配置。

```python
config.update({
    "depth": 10,
    "cannon_player": "AI"
})
```

#### `is_ai_turn(current_player: int) -> bool`

判断当前是否是 AI 回合。

---

## game_io 模块 (`game_io.py`)

棋谱读写函数。

### `save_game(model: GameModel) -> str`

保存棋谱到 JSON 文件。返回操作结果消息。

### `load_game() -> tuple | None`

弹出文件选择对话框，加载棋谱。

返回 `(initial_state: GameState, moves: list)` 或 `None`（取消/失败）。

---

## 相关文档

- [模块概览](REF_modules_overview.md)
- [架构设计](REF_architecture.md)
- [快速入门](GUIDE_getting_started.md)
