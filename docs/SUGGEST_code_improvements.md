# 代码改进建议

本文档提供代码规范和质量方面的改进建议，供后续迭代参考。

> [!NOTE]
> 这些建议是基于 PEP 8、类型提示和 Docstring 规范的分析结果，**不影响现有功能**。

---

## 1. 类型提示 (Type Hints)

### 当前状态

部分文件有类型提示，但不完整：
- `ai_engine.py` ✅ 类型提示较完整
- `game_model.py` ⚠️ 部分方法缺少返回类型
- `orchestrator.py` ❌ 大部分方法无类型提示

### 建议改进

#### orchestrator.py

```diff
- def on_canvas_click(self, r, c):
+ def on_canvas_click(self, r: int, c: int) -> None:

- def on_new_game(self):
+ def on_new_game(self) -> None:

- def check_for_ai_turn(self):
+ def check_for_ai_turn(self) -> None:
```

#### game_model.py

```diff
- def make_move(self, start_pos, end_pos) -> bool:
+ def make_move(self, start_pos: tuple[int, int], end_pos: tuple[int, int]) -> bool:
```

### 优先级：⭐⭐⭐ 中

---

## 2. Docstring 规范化

### 当前状态

Docstring 风格不统一：
- 部分使用简短描述
- 部分使用"需求"列表格式
- 缺少参数和返回值说明

### 建议改进

采用 **Google 风格** Docstring：

```python
def make_move(self, start_pos: tuple[int, int], end_pos: tuple[int, int]) -> bool:
    """执行走法并更新历史记录。

    如果当前处于复盘模式，会自动截断历史并退出复盘。

    Args:
        start_pos: 起始位置 (row, col)
        end_pos: 目标位置 (row, col)

    Returns:
        始终返回 True，表示操作完成。

    Example:
        >>> model.make_move((4, 1), (3, 1))
        True
    """
```

### 优先级：⭐⭐⭐ 中

---

## 3. 常量管理

### 当前状态

常量分散在多个文件：
- `core/game_logic.pyx`: `EMPTY`, `SOLDIER`, `CANNON`, `DRAW`
- `gui.py`: `CELL_SIZE`, `COORD_MARGIN` 等

### 建议改进

创建统一的常量文件：

```python
# constants.py

# 棋子类型
EMPTY = 0
SOLDIER = 1
CANNON = 2
DRAW = 3

# 棋盘尺寸
BOARD_ROWS = 5
BOARD_COLS = 5

# UI 常量
CELL_SIZE = 100
COORD_MARGIN = 30
```

### 优先级：⭐⭐ 低

---

## 4. 异常处理

### 当前状态

异常处理方式不一致：
- `game_logic.pyx`: 抛出 `ValueError`
- `orchestrator.py`: 捕获后静默处理

### 建议改进

1. 定义自定义异常类：

```python
# exceptions.py

class GameError(Exception):
    """游戏相关错误的基类"""
    pass

class IllegalMoveError(GameError):
    """非法走法错误"""
    pass
```

2. 在关键位置使用自定义异常：

```python
# game_logic.pyx
if (end_r, end_c) not in valid_moves:
    raise IllegalMoveError(f"非法走法: ({start_r},{start_c}) -> ({end_r},{end_c})")
```

### 优先级：⭐⭐ 低

---

## 5. 代码组织

### 当前状态

- 私有方法命名规范 ✅ 使用 `_` 前缀
- 导入语句位置 ⚠️ 部分在函数内部导入

### 建议改进

#### 移除函数级导入

```diff
# orchestrator.py
+ from settings_dialog import SettingsDialog
+ from game_io import save_game, load_game

  def on_open_settings(self):
-     from settings_dialog import SettingsDialog
      dialog = SettingsDialog(self.view, current_config)
```

> [!WARNING]
> 函数级导入会在每次调用时执行导入逻辑，虽然有缓存但仍有微小开销。

### 优先级：⭐ 低

---

## 6. 注释清理

### 当前状态

代码中有部分调试注释和过时说明：
- `# >>> 新增！处理从复盘模式发起的计算 <<<`
- `# >>> 核心修正！<<<`

### 建议改进

清理临时注释，保留有意义的说明：

```diff
- # >>> 新增！处理从复盘模式发起的计算 <<<
  if self.model.is_replay_mode:
+     # 从复盘模式发起计算时，先截断历史创建新分支
      self.model.move_history = self.model.move_history[:self.model.replay_index + 1]
```

### 优先级：⭐ 低

---

## 总结

| 改进项 | 优先级 | 工作量 |
|:---|:---:|:---:|
| 类型提示完善 | ⭐⭐⭐ | 中 |
| Docstring 规范化 | ⭐⭐⭐ | 中 |
| 常量管理 | ⭐⭐ | 小 |
| 异常处理 | ⭐⭐ | 中 |
| 代码组织 | ⭐ | 小 |
| 注释清理 | ⭐ | 小 |

---

## 相关文档

- [性能优化建议](SUGGEST_performance_optimization.md)
- [现代化实践建议](SUGGEST_modern_practices.md)
