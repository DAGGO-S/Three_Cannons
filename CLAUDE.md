# CLAUDE.md

此文件为 AI 助手提供本项目的上下文指引。

## 项目概述

**三炮十五兵 AI版** — 基于经典民间棋类游戏的 Python 实现，配备智能 AI 对手。

- **游戏规则**: 5×5 棋盘，3 个炮 vs 15 个兵。炮可移动一格或隔空跳吃兵；兵上下左右移动一格。炮方目标吃光所有兵，兵方目标困住所有炮，同一局面重复 3 次判和棋。
- **技术栈**: Python 3.13 + Cython（核心算法） + Tkinter（GUI） + NumPy/SciPy（调参优化）
- **架构模式**: MVC（Model-View-Controller）

## 项目结构

```
Three_Cannons/
├── main.py                  # 程序入口，组装 MVC 组件
├── setup.py                 # Cython 编译脚本
├── core/                    # Cython 高性能模块 (.pyx → .pyd)
│   ├── game_logic.pyx       # GameState 类: 棋盘状态、走法生成、走子、胜负判定
│   ├── ai.pyx               # Alpha-Beta + 迭代加深 + 置换表 + 静默搜索
│   ├── evaluation_logic.pyx # 局面评估: 子力分 + 位置分 + 控制区BFS + 贴炮分
│   └── zobrist_hashing.pyx  # Zobrist 哈希: 增量更新、回合切换
├── src/
│   ├── model/
│   │   ├── game_model.py    # GameModel: 走子执行、和棋检测、复盘管理
│   │   └── config.py        # GameConfig: 玩家类型、搜索深度、时间限制
│   ├── view/
│   │   ├── main_window.py   # GameGUI(tk.Tk): 棋盘绘制、按钮控制、事件绑定
│   │   └── dialogs.py       # SettingsDialog: 游戏设置对话框
│   ├── controller/
│   │   └── orchestrator.py  # GameOrchestrator: 事件分发、AI调度、复盘导航
│   ├── ai/
│   │   └── engine.py        # AIEngine: 异步线程AI计算、进度回调、中断恢复
│   └── io/
│       └── game_io.py       # save_game/load_game: JSON 棋谱读写
├── tests/                   # pytest 测试集
├── docs/                    # 项目文档 (架构、API、模块概览等)
├── tuning/                  # 评估函数调参工具
│   ├── annotator.py         # 人机协同标注 GUI
│   └── optimizer.py         # 差分进化参数优化 (Rank Loss)
└── data/game_history/       # 保存的棋谱文件 (JSON)
```

## 关键架构要点

### 数据流

```
用户点击 → GameGUI → GameOrchestrator → GameModel.make_move() → core.game_logic
                                       ↓
                                  AIEngine (后台线程) → core.ai → core.evaluation_logic
                                       ↓
                              _on_ai_move_completed → GameModel → GameGUI.render()
```

### 核心约定

1. **GameState 不可变**: `board` 字段为嵌套元组 `tuple[tuple[int]]`，`move_piece()` 返回新实例
2. **和棋由 Model 管理**: `GameModel.position_counts` 通过 Zobrist 哈希计数判定三次重复
3. **AI 异步执行**: `AIEngine` 在独立线程运行，通过 `stop_event` 支持中断，中断时回调已搜索到的最佳走法
4. **Cython 核心已编译**: `.pyd` 文件已预编译，修改 `.pyx` 后需运行 `python setup.py build_ext --inplace`

### 棋子常量

| 常量      | 值  | 含义     |
| --------- | --- | -------- |
| `EMPTY`   | 0   | 空位     |
| `SOLDIER` | 1   | 兵       |
| `CANNON`  | 2   | 炮       |
| `DRAW`    | 3   | 和棋状态 |

## 常用命令

```bash
# 运行游戏
python main.py

# 编译 Cython 模块
python setup.py build_ext --inplace

# 运行测试
python -m pytest tests/

# 调参标注
python tuning/annotator.py

# 参数优化
python tuning/optimizer.py
```

## 开发注意事项

- **不要直接运行代码**: 运行是用户自己的事情，助手不应替用户执行
- **修改 `.pyx` 后**: 必须重新编译 Cython 才能生效，提醒用户运行 `python setup.py build_ext --inplace`
- **棋盘坐标**: 行列从 0 开始，棋盘大小为 `BOARD_ROWS=5 × BOARD_COLS=5`
- **GUI 线程安全**: AI 计算在后台线程，GUI 更新需通过 `view.after()` 回到主线程
- **置换表**: 每次 AI 计算前调用 `clear_transposition_table()` 重置
- **评估函数缓存**: `evaluation_logic.pyx` 使用 `_cannon_forbidden_zone_cache` 和 `_control_zone_bfs_cache`，跨调用复用
