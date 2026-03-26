# 项目状态报告

## 1. 核心开发进度

### 计算引擎
- 状态：Phase 1-5 已完成。
- 技术指标：Alpha-Beta + PVS + LMR + NNUE v2 (增量更新)。实测节点吞吐量达 **2.05M NPS (单线程)** / **18.2M NPS (16 线程)**。
- 缺陷说明：静默搜索 (QS) 与空步剪裁 (NMP) 仍处于禁用状态。

### 数据规范
- 状态：FEN 格式支持已就绪。
- 组件：GameState.to_fen 与 from_fen 逻辑已通过 `evaluate_fens.py` 验证。

## 2. 正在进行中的任务

### 残局表集成与隔离
- **状态**：TB/AB 模式路由逻辑已在 `GameOrchestrator` 层完成硬隔离，解决了和棋局面下的评价退化问题。
- **进度**：[x]

## 3. 技术约束与债务

- 静默搜索：永久禁用，用于规避 Zugzwang 逻辑风险。
- 处理性能：通过 C 级重构消除了 Python 对象开销。

## 4. 关键资产路径

- 技术参考：[架构设计](file:///z:/2-Lixinjie/temp_note/test/Three_Cannons/docs/ref/REF_ARCH_architecture.md)
- 技术参考：[设计决策记录](file:///z:/2-Lixinjie/temp_note/test/Three_Cannons/docs/ref/REF_ARCH_design_decisions.md)
- 技术参考：[API 接口](file:///z:/2-Lixinjie/temp_note/test/Three_Cannons/docs/ref/REF_INTERFACE_api_interfaces.md)
- 技术参考：[算法规格书](file:///z:/2-Lixinjie/temp_note/test/Three_Cannons/docs/ref/REF_ALGO_algorithm_spec.md)
- 训练资产：[NNUE 演进记录](file:///z:/2-Lixinjie/temp_note/test/Three_Cannons/docs/ref/REF_ALGO_nnue_evolution.md)
- 实验记录：[典型对战日志](file:///z:/2-Lixinjie/temp_note/test/Three_Cannons/docs/experiments/EXP_20260318_weight_battle.md)
