# 项目开发与迭代计划 (Project Development & Iteration Plan)

## 1. 概述

本文档是 "三炮十五兵" Python 版项目的核心开发指南，旨在取代过去混乱、缺乏明确方向的开发模式。所有未来的开发工作都应严格遵循本文档定义的架构和迭代计划，以确保代码的高质量、低耦合和易维护性。

## 2. 核心设计哲学

为避免重蹈覆辙，项目必须遵循以下核心设计原则：

*   **单一职责原则 (SRP)**: 每个类或模块只做一件事，并把它做好。例如，`AIEngine` 只负责AI计算，`GameModel` 只负责数据管理。
*   **松耦合 (Loose Coupling)**: 各模块间通过定义好的接口（方法）进行通信，最大限度地减少直接依赖。任何模块的内部修改不应引发其他模块的大规模连锁反应。
*   **数据驱动模型 (Data-Centric Model)**: `GameModel` 是项目中唯一的“事实来源”(Single Source of Truth)。所有游戏状态的读取和修改都必须通过它进行。
*   **异步设计 (Asynchronous First)**: 任何耗时操作（尤其是AI计算）必须在后台线程中异步执行，确保UI主线程永远不会被阻塞。
*   **清晰的数据流 (Clear Data Flow)**: 严格遵循 **模型(Model) -> 协调器(Orchestrator) -> 视图(View)** 的单向数据流。用户输入由 `View` 捕获，交由 `Orchestrator` 处理，`Orchestrator` 更新 `Model`，最后通知 `View` 根据新的 `Model` 数据进行渲染。

## 3. 架构蓝图 (Architectural Blueprint)

项目采用基于 MVC 变体的分层架构，各组件职责如下：

| 组件 | 文件 | 核心职责 |
| :--- | :--- | :--- |
| **程序入口** | `main.py` | 初始化所有核心组件，并将它们“注入”到协调器中，启动应用主循环。**不包含任何业务逻辑**。 |
| **游戏模型** | `game_model.py` | 管理所有游戏数据：`GameState`、历史记录、复盘状态、选中的棋子等。**完全独立，对UI和AI无感知**。 |
| **游戏视图** | `gui.py` | 仅负责根据 `GameModel` 的数据渲染UI界面。捕获用户输入事件并**无逻辑地转发**给协调器。 |
| **总协调器** | `orchestrator.py` | 应用的“大脑”。接收 `View` 的事件，调用 `Model` 更新数据，调用 `AIEngine` 进行计算，并最终通知 `View` 刷新。 |
| **AI引擎** | `ai_engine.py` | **唯一**负责AI计算的模块。管理AI后台线程，提供`start_calculation`和`stop_calculation`接口，通过回调函数返回结果。 |
| **核心算法库** | `*.pyx` | Cython实现的高性能底层库，包括游戏逻辑、AI搜索、局面评估等，被 `Model` 和 `AIEngine` 调用。 |
| **持久化模块** | `game_io.py` | 负责游戏的加载与保存，处理与文件系统（如JSON棋谱）的交互。 |

## 4. 核心功能开发需求

### 4.1. GameModel (`game_model.py`)
- [x] 必须封装 `GameState` 对象。
- [x] 维护一个 `move_history` 列表，存储每一步棋后的 `GameState` 对象。
- [x] 提供 `make_move(start, end)` 方法，该方法在执行走法后，必须自动更新 `GameState` 和 `move_history`。
- [x] 实现复盘逻辑，提供 `load_state_from_history(index)` 方法，能够无误地将游戏状态切换到历史记录中的任意一点。
- [x] 提供 `reset()` 方法，将所有状态恢复到初始对局。

### 4.2. AIEngine (`ai_engine.py`)
- [x] 实现 `start_calculation(game_state, config, on_complete_callback, progress_callback)` 异步方法。
- [x] `start_calculation` 必须在新的后台线程中执行，并立即返回，不能阻塞调用者。
- [x] 实现 `stop_calculation()` 方法，能够安全地终止后台的AI计算线程。
- [x] AI计算完成后，必须通过 `on_complete_callback` 将 `best_move` 结果返回给主线程。
- [x] AI计算过程中，必须通过 `progress_callback` 实时反馈进度信息。

### 4.3. GameOrchestrator (`orchestrator.py`)
- [x] 必须持有 `Model`, `View`, `AIEngine` 的实例。
- [x] 实现所有用户事件的处理函数（如 `on_canvas_click`, `on_new_game`, `on_calculate_move` 等）。
- [x] 事件处理函数中，只允许调用 `Model` 的方法来修改状态，或调用 `AIEngine` 的方法来触发计算。
- [x] 任何可能改变UI显示状态的操作完成后，都必须调用 `update_view()` 来刷新界面。
- [x] 实现 `check_for_ai_turn()` 逻辑，用于在人机对战或AI互搏模式下自动触发AI计算。

### 4.4. GameIO (`game_io.py`)
- [x] 实现 `save_game(model)` 函数，将 `GameModel` 中的初始棋盘和完整走法历史导出为JSON格式的棋谱文件。
- [x] 实现 `load_game()` 函数，该函数应打开文件选择对话框，读取JSON棋谱，并返回 `(initial_state, moves)` 元组。
- [x] **必须**明确定义棋谱的JSON结构，例如：
  ```json
  {
    "metadata": {
      "save_time": "2025-09-03 15:30:00",
      "comment": "一场对局"
    },
    "initial_board": [
      [0, 0, 0, 0, 1],
      [1, 1, 0, 0, 0],
      [1, 1, 1, 0, 0],
      [2, 1, 1, 1, 0],
      [2, 0, 2, 1, 0]
    ],
    "current_player": 2,
    "moves": [
      [[3, 1], [4, 1]],
      [[3, 0], [3, 2]],
      [[2, 1], [3, 1]]
    ]
  }

  ## 5. 迭代路线图 (Iteration Roadmap)

### Phase 1: 架构搭建与核心玩法 (MVP)
1.  **目标**: 实现一个功能完整的、仅支持**人类对人类**对战的版本。
2.  **任务**:
    - [x] 搭建好所有新模块的文件和类结构。
    - [x] 完整实现 `GameModel` 的所有功能。
    - [x] 完整实现 `GameOrchestrator` 中与人类对战相关的逻辑（棋盘点击、选子、走子）。
    - [x] 改造 `GameGUI`，使其完全由 `Orchestrator` 驱动。
    - [x] 确保新游戏、悔棋（通过复盘实现）功能正常。

### Phase 2: AI 集成与人机对战
1.  **目标**: 实现稳定的人机对战功能。
2.  **任务**:
    - [x] 完整实现 `AIEngine` 的异步计算和回调机制。
    - [x] 在 `Orchestrator` 中集成 "计算一步"、"停止计算" 功能。
    - [x] 在 `Orchestrator` 中实现 `check_for_ai_turn` 逻辑。
    - [x] 将AI思考过程的实时信息正确显示在UI上。

### Phase 3: 功能完善
1.  **目标**: 实现所有辅助功能，成为一个完整的游戏应用。
2.  **任务**:
    - [x] 完整实现 `GameIO` 模块，支持棋谱的保存和加载。
    - [x] 在 `Orchestrator` 中集成加载/保存棋谱的逻辑。
    - [x] 实现完整的复盘导航功能（首/末步、上/下一步）。
    - [x] 实现游戏设置功能，允许用户选择对战模式（人vsAI, AIvs人, AIvsAI）和AI难度。

### Phase 4: 优化与发布
1.  **目标**: 提升性能和用户体验。
2.  **任务**:
    - [x] 对Cython代码（尤其是评估函数）进行性能分析和优化。
    - [x] 修复所有已知的BUG。
    - [ ] 美化UI界面。
    - [ ] 编写最终的用户文档 (`README.md`) 并准备发布。

## 6. 旧文件逻辑迁移说明

为了清晰地指导重构过程，本节详细说明了原有项目文件中的逻辑将如何迁移到新的、分层的架构中。

| 旧文件 / 主要类 | 原始职责 (总结) | 在新架构中的归宿 | 迁移说明与原因 |
| :--- | :--- | :--- | :--- |
| **`main.py`**<br/>`MainApplication` | **上帝对象**：创建UI、管理所有Manager、处理UI事件、启动AI线程、执行复盘逻辑。 | ➡️ **`main.py` (入口)**<br/>➡️ **`orchestrator.py` (大脑)** | 新的 **`main.py`** 将被极度简化，只负责初始化并“连接”所有核心组件。`MainApplication` 中的所有业务逻辑、事件处理和流程控制都将移至 **`orchestrator.py`**。 |
| **`game_engine.py`**<br/>`GameController` | **混合体**：封装`GameState`、执行走法、管理AI计算线程和回调。 | ➡️ **`game_model.py` (数据)**<br/>➡️ **`ai_engine.py` (AI)** | 这是本次重构的关键拆分对象。管理 `GameState` 和 `move_history` 的职责移至 **`game_model.py`**。所有与AI计算、线程、停止事件相关的方法 (`get_ai_move`, `_ai_worker_thread` 等) 全部移至 **`ai_engine.py`**。 |
| **`game_manager.py`**<br/>`GameManager` / `ReplayManager` | **游戏流程管理器**：管理UI状态（如按钮）、处理复盘流程。 | ➡️ **`orchestrator.py` (逻辑)**<br/>➡️ **`game_model.py` (数据)** | 复盘的*状态*（如 `replay_history`, `replay_index`）归 **`game_model.py`** 管理。复盘的*控制逻辑*（如响应“上一步”按钮点击）归 **`orchestrator.py`** 处理。 |
| **`ai_manager.py`**<br/>`AIManager` | **AI专职管理器**：负责启动、停止、监控AI计算。 | ➡️ **`ai_engine.py`** | 这是最直接的映射。**`AIEngine`** 就是 `AIManager` 的演进版本，但其职责更纯粹，完全与UI和主游戏逻辑解耦，只通过回调函数通信。 |
| **`replay_controller.py`**<br/>`ReplayController` | **功能重叠**：另一套复盘逻辑的实现。 | ➡️ **将被完全吸收并删除** | 该文件的功能与 `game_manager.py` 和 `main.py` 中的复盘逻辑重叠，是代码混乱的根源之一。其功能将被 **`game_model.py`** 和 **`orchestrator.py`** 完全取代，此文件将被废弃。 |
| **`gui/gui.py`**<br/>`GameGUI` | **视图**：负责UI的渲染和绘制。 | ➡️ **`gui.py` (重构)** | 文件保留，但其内部实现将被重构。它将不再包含任何游戏逻辑判断，变成一个纯粹的“哑巴”视图，只负责根据 `GameModel` 的数据进行渲染，并将用户输入事件转发给 `Orchestrator`。 |
| **`game_logic.pyx`**<br/>`ai.pyx`<br/>`core/evaluation_logic.pyx` | **核心算法库**：游戏规则 (`GameState`)、AI搜索算法、局面评估函数。 | ➡️ **保持为核心算法库** | 这些底层库的职责已经非常清晰且独立。它们在新架构中的角色不变，只是调用者发生了变化：**`game_model.py`** 会使用 `game_logic.pyx`，而 **`ai_engine.py`** 会调用 `ai.pyx`。 |