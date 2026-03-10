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
2. **和棋由 Model 管理**: `GameModel.position_counts` 通过 Zobrist 哈希计数判定三次重复，吃子移动会清空计数器
3. **AI 异步执行**: `AIEngine` 在独立线程运行，通过 `stop_event` 支持中断，中断时回调已搜索到的最佳走法
4. **GUI 线程安全**: AI 计算在后台线程，GUI 更新需通过 `view.after()` 回到主线程
5. **Cython 核心已编译**: `.pyd` 文件已预编译，修改 `.pyx` 后需运行 `python setup.py build_ext --inplace`
6. **置换表重置**: 每次 AI 计算前调用 `clear_transposition_table()` 重置，避免旧数据干扰

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

# 运行所有测试
python -m pytest tests/

# 运行单个测试文件
python -m pytest tests/test_game_logic.py

# 运行特定测试类
python -m pytest tests/test_game_logic.py::TestGameState

# 运行特定测试方法
python -m pytest tests/test_game_logic.py::TestGameState::test_cannon_capture
```

## 开发工作流与绝对铁律

> 坚持第一性原理的SKILL流程，事实为本。

1. **结构化流程严控**：
   - 必须严格遵循 **“构思方案 → 提请审核 → 分解为具体任务”** 的开发顺序。
   - 在大规模改动前，**必须建立还原点**，确保随时回退。
2. **强制双重闭环验证法则 (The Closed-Loop Matrix)**：
   每一次优化战役，都必须经过以下完整的闭环链条：
   - **步骤一：基线测量 (Measure Baseline)**：在尚未修改代码前，必须先利用基准脚本 (如 `bench_fixed_depth.py`) 和探针 (如 `cProfile`) 抓取当前的详尽耗时和 NPS 线，将数据客观打底。
   - **步骤二：防危隔离 (Task Loop)**：构思重构方案时，必须通过编写 `implementation_plan.md` 审核架构副作用。底层优化绝对不可打破外部的 MVC/测试 接口预设（隔离重构法）。随后辅以自动化测试 `pytest` 运行通过，客观得出“第一性原理逻辑通过”的结论。
   - **步骤三：性能核算 (Performance Loop)**：代码完工后，再次执行相同的基准脚本提取修正后的 NPS。如果无明显上升甚至倒退，立刻重跑 Profile 定位真凶；如果有提升，记录增益百分比。客观得出“第一性原理算力通过”的结论。
   - **步骤四：成果固化 (Ref & Archive)**：当重构被证实有效并验收，立即将分析原数据写入 `findings.md` 或 `progress.md`，并将承载此任务的主线 Task 冠以 `REF_` 前缀归档封存，供后续 AI 阅读参考。严禁开环结题。
   - 在执行任何激进的安全优化后，第一要务是让用户**运行主程序手动对弈或执行跑盘测试**，确保核心智力和游戏规则不被破坏。
4. **禁止主动运行**：
   - AI **严禁主动运行或越权执行** 任何测试脚本、编译脚本甚至主程序。除非用户主动提出自动化执行。
   - 撰写程序或提供命令，并请用户自行执行。你运行就卡死。
5. **文档规范**：
   - **冷峻客观**：使用平铺直叙、干练且客观的语言风格撰写所有文档和代码注释。聚焦事物本质与技术逻辑分析。
   - **禁止情绪化与夸张修饰**：绝对禁止在项目**任何**文档（如 `docs/` 下的所有文件、甚至 `CLAUDE.md` 自身）及聊天输出中使用诸如夸张、渲染、具象或带有主观情绪色彩的词汇。
   - **禁止双语混用**：除无法替代的专业术语（如 `NPS`, `Alpha-Beta`）和代码外，通篇必须使用纯净的中文。禁止使用括号夹杂英文解释（如 `First Principles`, `Pros` 等）。禁止引号、破折号。**所有文档都必须遵循此风格。**

- **修改 `.pyx` 后**: 必须重新编译 Cython 才能生效，提供命令给用户运行 `python setup.py build_ext --inplace`
- **棋盘坐标**: 行列从 0 开始，棋盘大小为 `BOARD_ROWS=5 × BOARD_COLS=5`
- **GUI 线程安全**: AI 计算在后台线程，GUI 更新需通过 `view.after()` 回到主线程
- **置换表**: 每次 AI 计算前调用 `clear_transposition_table()` 重置
- **评估函数缓存**: `evaluation_logic.pyx` 使用 `_cannon_forbidden_zone_cache` 和 `_control_zone_bfs_cache`，跨调用复用
- **性能剖析**: 性能重构必须对代码进行 `cProfile` 结合 `cython: profile=True` 的全量实测。
- **Zero Allocation 铁律**: 在 AI 计算核心热路径中，代之以纯 C 数组、静态结构体指针或位运算。
