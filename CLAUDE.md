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
│   ├── search_manager.pyx   # 迭代加深、PVS 搜索调度
│   ├── engine.pyx           # _alpha_beta 内核、NNUE 增量更新逻辑
│   ├── search_infrastructure.pyx # 置换表 (TT)、全局原子计数
│   ├── zobrist_hashing.pyx  # Zobrist 哈希: 增量更新、回合切换
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
                                  AIEngine (后台线程) → core.search_manager → core.engine
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

| 常量        | 值 | 含义     |
| ----------- | -- | -------- |
| `EMPTY`   | 0  | 空位     |
| `SOLDIER` | 1  | 兵       |
| `CANNON`  | 2  | 炮       |
| `DRAW`    | 3  | 和棋状态 |

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

1. **结构化流程严控 (计划 - 执行 - 验证 三段论)**：

   必须严格遵循以下执行链路，各流程相互绝对独立，严禁跳步与越权流转：

   - **计划 (Plan with file)**：构思方案 → 提请审核 → 建立并更新文档（如 `TASK_xxx.md`）。**铁律**：计划完毕即任务终止！绝对不允许处于计划期间顺手去改代码。计划落锤后，必须在文档末尾明文撰写给下一个执行 AI 的【交接指令】（指明：干什么、看什么、输出要求什么）。
   - **执行 (Execute with output file)**：阅读交接书后，严格基于获批计划改动代码物理边界，完成后立即交棒终止。若无特别指令，严禁越俎代庖去替用户执行或进入下一校验流程。
   - **验证 (Check with test)**：根据测试交接清单，运用实测脚本与测试集形成硬性闭环，将成败数值归档至报告内。
   - 在大规模改动前，**必须建立还原点**，确保随时回退。
2. **强制双重闭环验证法则 (The Closed Loop)**：
   AI 必须具备真实的鉴别能力，绝对禁止“自以为是”的判断。每一次行为都应经过以下闭环验证，并在文档中强制要求与记录：

   - **闭环一：逻辑与功能的正确性闭环**。你经常说代码对，完成了任务。可是真正对吗？必须本着第一性原理，**用测试程序去硬性验证**，获得客观测试断言后再进行结果讨论，最后才能给出结论。
   - **闭环二：优化方案的效能闭环**。你经常说目前的方案有问题，需要做XXX。可是新方案真的对吗？必须本着第一性原理，**去做 AB 测试验证**。获取执行前后的性能表现数据，通过客观讨论后才能给出结案声明。

   **落地执行工作流 (Task 转换映射)**：

   - **创建规范**：所有非微型改动必须建立 `docs/tasks/TASK_xxx.md`。必须包含：`目标`、`推进状态 (Progress Tracking)`、`待处理缺陷`、`维护过程记录 (Execution Logs)`。
   - **记录保留铁律**：在子任务执行期间，**严禁清理或覆盖** `Execution Logs` 中的原始过程数据（如脚本输出、采样值、性能指标）。该记录是闭环验证的唯一审计线索。
   - **防危隔离验证**：开始实现 TASK 前确保自动化测试（`pytest`）有基带保护。
   - **性能对照核算**：对底层重构，执行 `bench_fixed_depth.py` 获取前后 NPS 及耗时的 AB 对照数据。
   - **复盘与固化**：只有在完成逻辑正确性（硬性测试通过）与效能（数据提升）的双重验证后，方可总结结案。
   - **强制归档与清理**：结案后将核心结论与事实提炼至 `REF_xxx.md`，随后立即**物理删除**对应的 `TASK_xxx.md`。严禁在总库中留存失效或中间态的任务描述。
3. **禁止主动运行**：

   - AI **严禁主动运行或越权执行** 任何测试脚本、编译脚本甚至主程序。除非用户主动提出自动化执行。
   - 撰写程序或提供命令，并请用户自行执行。你运行就卡死。
4. **文档规范**：

   - **冷峻客观**：使用平铺直叙、干练且客观的语言风格完整撰写所有文档和代码注释。聚焦事物本质与技术逻辑分析。完整不遗漏。
   - **禁止情绪化与夸张修饰**：禁止在任何文档及输出中使用夸张、主观的词汇。
   - **禁止双语混用**：除专业术语代码外，通篇使用纯净中文。禁止使用括号夹杂英文解释。禁止使用引号、破折号、表情图标（Emoji）。
5. **文档库状态机管理法则 (DOCS WORKFLOW)**：

   - 项目 `docs/` 下推行“核心-动态-观测”三位一体隔离态：
     - **核心规格**：`specs/` (协议规范)。
     - **技术参考**：`ref/` (带 ARCH/ALGO/INTERFACE 前缀的资产库)。
     - **实验观测**：`experiments/` (结构化实验记录)。
   - **绝对红线**：禁止将探讨中的半成品提案或失效任务驻留于总库中。通过双轨闭环后提取“事实+逻辑+约束”三段式数据并升级为 `REF_` 资产，旧档随即强制抹除。
   - 任何涉及文档新增或知识体系查阅的人员/AI，必须事先阅读并遵守 `docs/guides/GUIDE_docs_workflow.md` 的纲领进行操作流转。
6. **需求与代码越权红线**：

   - **绝不自造轮子**：在诊断缺陷或进行现状分析时，严格收束于“查阅现有代码与数据”，绝不允许逾越边界去自行编写“探针脚本”、“分析程序”或任何前置未明文要求的新代码。
   - **凡立码必有案**：所有新增代码行为（无论是分析工具还是产品特性），必须在此前的“计划 (Plan with file)”阶段明文入禀，并取得人工许可。

- **修改 `.pyx` 后**: 必须重新编译 Cython 才能生效，提供命令给用户运行 `python setup.py build_ext --inplace`
- **棋盘坐标**: 行列从 0 开始，棋盘大小为 `BOARD_ROWS=5 × BOARD_COLS=5`
- **GUI 线程安全**: AI 计算在后台线程，GUI 更新需通过 `view.after()` 回到主线程
- **置换表**: 每次 AI 计算前调用 `clear_transposition_table()` 重置
- **评估函数缓存**: `evaluation_logic.pyx` 使用 `_cannon_forbidden_zone_cache` 和 `_control_zone_bfs_cache`，跨调用复用
- **性能剖析**: 性能重构必须对代码进行 `cProfile` 结合 `cython: profile=True` 的全量实测。
- **Zero Allocation 铁律**: 在 AI 计算核心热路径中，代之以纯 C 数组、静态结构体指针或位运算。
