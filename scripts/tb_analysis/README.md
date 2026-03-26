# 三炮十五兵 - 残局库 (Tablebase) 分析工具链

本目录包含残局库生成、验证与利用的核心工具脚本。遵循“精简与专业”原则，仅保留必不可少的核心程序。

## 核心脚本指南

### 1. [generate_tablebase.py](file:///z:/2-Lixinjie/temp_note/test/Three_Cannons/scripts/tb_analysis/generate_tablebase.py)
- **用途**: 残局库生成器。
- **功能**: 
  - 枚举所有合法子力组合（如 2C3S）并进行规范化去重（8倍压缩）。
  - 执行逆向推演（Retrograde Analysis）计算精确的 DTM（绝杀步数）。
  - 针对和棋空间执行强化学习值迭代，计算 CTI（累积高压指数）。
- **产出**: `data/tablebase/tb_cX_sY.pkl` 二进制库文件。

### 2. [verify_tablebase.py](file:///z:/2-Lixinjie/temp_note/test/Three_Cannons/scripts/tb_analysis/verify_tablebase.py)
- **用途**: 质量审计与路径追踪。
- **功能**: 
  - `audit_tb`: 统计库内状态总数及 DTM 分布。
  - `trace_path`: 输入一个 FEN，根据残局库指引进行“完美对弈”追踪，验证逻辑连通性及绝杀准确性。支持自动跨库跳转。

### 3. [play_against_tb.py](file:///z:/2-Lixinjie/temp_note/test/Three_Cannons/scripts/tb_analysis/play_against_tb.py)
- **用途**: 残局实验室（交互式验证）。
- **功能**: 提供交互式终端界面，允许用户输入 FEN 与残局库进行对弈。实时显示当前局面的理论评价、DTM 以及 CTI 压力值。

### 4. [peek_tb.py](file:///z:/2-Lixinjie/temp_note/test/Three_Cannons/scripts/tb_analysis/peek_tb.py)
- **用途**: 快速查看工具。
- **功能**: 极速加载库文件，打印局面总数并抽样显示部分（胜/负）节点的元数据。

---

## 隔离原则说明 (Isolation Principle)

在引擎集成中，必须严格区分 **Alpha-Beta 搜索** 与 **残局库** 的决策逻辑：
1. **优先查询**: 局面进入残局库覆盖范围时，优先进行库检索。
2. **胜负判定**: 若残局库返回“必胜”或“必败”，则直接采用该结论，短路搜索。
3. **平局降级**: 若残局库判定为“和棋”(0.00)，则**必须忽略**该结果并切换回核心 Alpha-Beta 搜索。利用评估函数在平局空间内寻找更高压力的走法，而非简单的 DTM 为 0 的摆动，确保持续施压。
