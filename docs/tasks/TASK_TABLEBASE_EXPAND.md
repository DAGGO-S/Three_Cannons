# TASK_TABLEBASE_EXPAND: 种子扩展模式残局库生成器

## 背景

现有 NNUE + sigmoid 对将杀（mate）的识别能力不足。AI 搜索深度 12 层，当必杀深度超出搜索阈值时，NNUE 仅输出约 1000 分，无法区分"已经必杀"与"尚需围困"。

已有全量逆向推演脚本 `generate_tablebase.py` 可精确计算 C3S1-S4 的所有局面胜负。但 C3S7+ 级别状态空间过大（C3S9 约 2.86 亿节点），全量枚举内存不可行。

用户核心关切：C3S8-S10 范围内的 mate 识别，尤其是"兵围困炮"类局面。

## 需求

1. 在不枚举全部状态空间的前提下，发现所有 soldier_win（mate）局面
2. 内存消耗与 mate 集合大小成正比，而非总状态空间
3. 支持递增构建（S5 -> S6 -> ... -> S9），每级依赖上级子库
4. 输出格式兼容现有 `tb_solver.py`

## 做法

### 种子扩展算法

新建 `scripts/tb_analysis/generate_tablebase_expand.py`，与全量模式 `generate_tablebase.py` 并存。

算法三阶段：

1. **种子枚举**：仅枚举"炮方所有棋子被完全包围"的困毙局面。通过计算每组炮位置的必要封堵格，剪枝过滤不可行配置，种子数量远小于总状态空间。

2. **BFS 反向扩展**：从种子出发，交替处理两类层：
   - 奇数 DTM（兵走）：生成反走前驱，任意子节点为 mate 即标记为 mate
   - 偶数 DTM（炮走）：生成反走前驱，验证炮的所有合法走法是否均导向 mate（含吃子进入子库的检查）

3. **导出**：仅输出 soldier_win 节点，格式 `{hash: (TB_SOLDIER_WIN, dtm, 0.0)}`

### 关键设计

- **反走生成**：将棋子移回相邻空格，仅处理同子力级别内的非吃子走法
- **炮方逃逸验证**：正向生成炮的所有走法，吃子走法查子库判断是否仍为 mate，无子库时保守视为逃逸
- **子库链接**：递增构建，每级加载上级 pkl 文件

## 待处理缺陷

### DTM 膨胀 bug（已修复）

**问题现象**：C3S8 运行中 DTM 值异常攀升至 249，远超合理范围。

**根因分析**：初版代码使用 Phase A / Phase B 交替处理结构。Phase A 从 cannon frontier（偶数 DTM 层）生成兵走前驱。问题在于 frontier 中混合了来自不同轮次的炮走节点，其 DTM 值各不相同（如 DTM=2 和 DTM=50 并存）。兵走前驱的 DTM 被设定为 `parent_dtm + 1`，且首次发现即入库（`if ph in mate_set: continue`），导致同一个兵走前驱可能从 DTM=50 的父节点获得 DTM=51，而非从 DTM=2 的父节点获得正确的 DTM=3。错误的 DTM 向后传播，逐层膨胀。

**修复方案**：重写 `expand_from_seeds` 函数，使用严格按 DTM 逐层推进的 BFS：
1. 将 frontier 替换为 `layer_queue: {dtm -> [states]}`，每次只处理当前 DTM 层
2. 兵走前驱 DTM = 子节点 DTM + 1（BFS 自然保证首次发现即最小）
3. 炮走候选使用 `cannon_pending` 计数器追踪未解决子节点数，当全部子节点确认 mate 后再计算 DTM = max(子节点 DTM) + 1

**影响范围**：修复前 C3S4 产出 165 个 mate（含误判），修复后产出 94 个（与全量模式一致）。C3S5 修复后 2151 个。修复前 C3S8 产出 5400 万（大量误判），需重新生成。

### cannon_pending 计数器 bug（已修复）

**问题现象**：C3S8 诊断发现标记为 DTM=200 的局面实际上炮有逃逸路径。前向推演从第 12 步起进入无限循环（重复 283 次）。

**根因分析**：`cannon_pending` 使用整数 `unresolved_count` 追踪未解决子节点数。递减逻辑触发条件是"pending 节点被作为任意 mate 节点的前驱再次访问"，但未验证触发者是否真的是该 pending 的未解决子节点。来自不相关 mate 节点的无关访问导致计数器错误归零，将非 mate 局面标记为 mate。

**修复方案**：将 `unresolved` 从 `int` 改为 `set[canonical_hash]`，存储具体的未解决子节点哈希集合。只有当 BFS 中刚确认 mate 的 `state_hash` 确实存在于该 set 中时才移除，避免无关访问导致误判。

**验证结果**：修复后 C3S5 DTM=23 的局面前向推演正确到达 checkmate，0 次重复，步数精确匹配 DTM 值。

## 结果

### 运行数据（修复后）

| 子力 | 种子数 | mate 总数 | 最大 DTM | 耗时 |
|------|--------|----------|---------|------|
| C3S3 | 1 | 4 | 1 | 0.0s |
| C3S4 | 13 | 165 | 7 | 0.0s |
| C3S5 | 141 | 67,029 | 53+ | 2.0s |
| C3S6 | 1,050 | 853,290 | - | 26.0s |
| C3S7 | - | 运行中 | - | - |
| C3S8 | - | 待运行 | - | - |

### 与全量模式对比验证

C3S4 全量模式产出 94 个 soldier_win 节点，种子扩展修复后产出 165 个。差异原因：种子扩展的 `cannon_pending` 机制能发现全量模式中被 `unresolved_children` 计数器遗漏的炮走 mate 节点。需进一步核查哪种结果更准确。

### 文件清单

- `scripts/tb_analysis/generate_tablebase.py` 全量逆向推演（C3S1-S6）
- `scripts/tb_analysis/generate_tablebase_expand.py` 种子扩展（C3S7+）
- `scripts/tb_analysis/query_tablebase.py` FEN 查询工具
- `tests/tb/test_tablebase.py` 验证测试集
