# REF: 模块概览

本文档提供系统的分层模块描述，作为 `REF_ARCH_architecture.md` 的补充。

---

## 1. 核心层：core/
高性能计算核心，脱离 Python 对象分配。
- `game_logic.pyx`：局面核心逻辑与合法性校验。
- `search_manager.pyx`：搜索算法调度者。
- `engine.pyx`：神经网络与搜索内核。
- `search_infrastructure.pyx`：置换表与哈希状态。

## 2. 模型层：src/model/
维护对局的单事实来源。
- `game_model.py`：封装历史堆栈、和棋计数及对局状态。
- `config.py`：配置注入点。

## 3. 控制层：src/controller/ 与 src/ai/
业务逻辑与异步调度。
- `orchestrator.py`：视图与模型间的枢纽，处理用户输入与结果同步。
- `engine.py`：异步计算封装，管理后台线程。

## 4. 视图层：src/view/
用户交互与状态渲染。
- `main_window.py`：主界面实现。
- `dialogs.py`：配置窗口。

## 5. 规格与协议：docs/specs/
- `SPEC_FEN_FORMAT.md`：棋盘状态序列化标准。
- `SPEC_DATA_PROTOCOL.md`：持久化存储规范。
