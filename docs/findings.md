# 探索发现录 (Findings)

这部分存放针对当前 AI 评测的真实数据。这能够解释为何从 11万 跃升至 14万 NPS 后不再继续提升的原理。遵循 `Measure, don't guess`：

## 1. 2026-03-09 CProfile 数据追踪

强制开启 `# cython: profile=True` 以打破黑盒，在限定深度的 2.3 ~ 2.8 秒探测中，得到了以下内部函数实际占用开销列表（经过 Top 选择）：

```text
ncalls  tottime  percall  cumtime  percall filename:lineno(function)
124579/100212    0.518    0.000    1.749    0.000 core/ai.pyx:123(_quiescence_search)
   123457    0.441    0.000    0.441    0.000 core/evaluation_logic.pyx:157(_calculate_control_zone_bfs)
   123457    0.338    0.000    1.476    0.000 core/evaluation_logic.pyx:201(evaluate_board)
  1097862    0.316    0.000    0.316    0.000 core/game_logic.pyx:96(get_valid_moves)
   123457    0.289    0.000    0.289    0.000 core/evaluation_logic.pyx:85(_calculate_soldier_scores)
   123457    0.284    0.000    0.399    0.000 core/evaluation_logic.pyx:113(_calculate_cannon_forbidden_zone)
259685/101    0.281    0.000    0.004    0.000 core/ai.pyx:330(_alpha_beta)
```

### 数据解析与诊断

| 排名 | 核心函数                           | 调用次数 | 纯耗时 (s) | 占比   | 开销主要来源分析                                                     |
| :--- | :--------------------------------- | :------- | :--------- | :----- | :------------------------------------------------------------------- |
| 1    | `_quiescence_search`               | 12.4万   | 0.518      | 18.2%  | 静默搜索的主循环，高频调用下属子函数。                               |
| 2    | `_calculate_control_zone_bfs`      | 12.3万   | 0.441      | 15.5%  | 广度优先搜索核心。依赖 `collections.deque` 与 `set` 进行状态集维护。 |
| 3    | `evaluate_board`                   | 12.3万   | 0.338      | 11.8%  | 静态评估主框架。分发与累计得分。                                     |
| 4    | `get_valid_moves`                  | 109.7万  | 0.316      | 11.1%  | 走法封装机制。频繁实例化包含元组的底层 `list` 对象以进行返回。       |
| 5    | `_calculate_soldier_scores`        | 12.3万   | 0.289      | 10.1%  | 兵源阵地计算。通过嵌套迭代处理数组访问。                             |
| 6    | `_calculate_cannon_forbidden_zone` | 12.3万   | 0.284      | 10.0%  | 禁区推算。触发多线程去重与 `set().add()` 底层开销。                  |
| 7    | `_alpha_beta`                      | 25.9万   | 0.281      | 9.9%   | Alpha-Beta 剪枝递归框架调度耗时。                                    |
| 8    | `move_piece`                       | 35.5万   | 0.213      | 7.5%   | 利用 `memcpy` 复制状态。该优化点已脱离主要瓶颈区。                   |
| 9    | `threading.py:605(is_set)`         | 43.6万   | 0.028      | < 1.0% | 多线程信号的周期性探查，非重度热路径。                               |
| 10   | `get_material_score`               | 12.3万   | 0.011      | < 1.0% | 基础字典/数组查询，无对象创建压力。                                  |

**客观诊断**：
以上前十大热点覆盖了绝大部分 CPU 时间。评估框架内附带的数组和对象集合调用（第2、3、5、6名）合计占用高达 47.4% 的周期。排名第4的走法生成单独占用 11.1%。它们的共同特性是强依赖内建高级数据结构的堆分配。这是妨碍引擎跨域到 1,000,000 NPS 的根本原因。

## Conclusion 结论

为达成 1,000,000 NPS 目标，必须要在评估与走法生成这两个高频执行的热路径上实现零堆内存分配（Zero Allocation）：

1. **评估函数扁平化**：移除所有依赖内置结构(`set`, `deque`)的检索算法，采用一维标志数组或位运算符（Bitwise operation）对棋盘防线及火力范围进行标记。同时为了获取不受干扰的观测对照极限，首次重构应前置性切断静默搜索（QS）。
2. **走法生成静态化**：所有走法生成逻辑不可采用 `return list` 的形式。应要求函数接收预先申请好的 C 级别结构体数组指针，并在内部直接执行数据赋值。

--

### 用例级经验与闭环教训 (2026/03/10)

**测试破坏成因分析**

1. **只读强制效应**：由于底层的 `GameState.board` 升级为 `Tuple[Tuple]`，它保护了核心数组但同时导致诸如 `GameIO` 等非评估主链路上、习惯“随手赋值” `board` 属性的外围代码大量抛出 `AttributeError`。这迫使上层数据流入时必须通过严谨的构造函数生命周期注入，阻止了侧漏修改。
2. **结构解耦的连带断开**：AI Engine 移入 `src.ai.engine` 后，超过半数的用例未能更新 `patch` 指针，造成虚假验证。并且 AI Worker 增加了回调状态统计参数 `stats`，导致旧参数签名的 mock 用例全部溃败。

**总结性教导**：在系统级调优中，严防“外层开环”；仅看 NPS 提升是不负责的，唯有将波及外层业务的隐形地雷排空（直至所有 37 项单测 100% 通过），性能提升才有真实的落地价值。-

## 2. 2026-03-09 Phase 1 纯 C 化评估基准胜利

在彻底剥离了 `evaluate_board` 内的 `set` 和 `deque`，并重写为 32-bit 位域 (Bitmask) 核算后（且如计划屏蔽了 QS），NPS 从 141,769 跃升至惊人的 **379,485 NPS**（提升约 2.67 倍）！

新的 cProfile 数据呈现了全新的瓶颈版图：

```text
   ncalls  tottime  percall  cumtime  percall filename:lineno(function)
635997/105    0.453    0.000    0.001    0.000 core/ai.pyx:331(_alpha_beta)
837146/490859 0.434    0.000    0.177    0.000 core/game_logic.pyx:138(move_piece)
   267013    0.412    0.000    0.412    0.000 core/evaluation_logic.pyx:111(c_evaluate_board)
   156021    0.259    0.000    0.513    0.000 core/ai.pyx:87(_get_ordered_moves)
  1173653    0.254    0.000    0.254    0.000 core/game_logic.pyx:96(get_valid_moves)
```

## 3. 2026-03-09 Phase 2 剥离走法抛解后的定盘

通过引入 `c_get_ordered_moves`，向预先申请的 16-bit 掩码栈数组中写入数据，彻底废弃了原先返回 `tuple` 列表的操作：
NPS 测试最高探至 **470,745 NPS**！

最新前5名开销函数追踪定格：

```text
   ncalls  tottime  percall  cumtime  percall filename:lineno(function)
   220298    0.386    0.000    0.386    0.000 core/evaluation_logic.pyx:111(c_evaluate_board)
700944/412372 0.347    0.000    0.159    0.000 core/game_logic.pyx:232(c_move_piece)
536560/97    0.333    0.000    0.001    0.000 core/ai.pyx:317(_alpha_beta)
   133768    0.125    0.000    0.125    0.000 core/game_logic.pyx:264(c_get_ordered_moves)
```

**解析：**
由于彻底消灭了 Python 层走法对象的产生，昔日排在榜单前列占 500多毫秒的走法生成双煞已经被压缩到了极致的 **0.125 秒**！这意味着走法生成的时间被生生削去了近乎 **80%**！

目前排行第二耗时的是 `c_move_piece`。它虽然完成了 `memcpy` 化，但依然包含 `GameState.__new__(GameState)` 对象申请。执行原位状态回溯可能进一步降低内存管理开销。

## 4. 2026-03-10 Phase 3 单项耗时对比与架构隔离

之前直接修改 `move_piece` 导致状态管理逻辑故障，因此执行了隔离重构：
对 `game_logic.pyx` 进行接口重组，保留对外部深拷贝机制，新增供 AI 内部调用的 `c_move_piece` 和 `c_unmake_piece` 实现原位修改。同时将 Python `dict` 置换表替换为 C 原生定长静态数组。

**性能追踪剖析与数据对比**：
无探针测试得出，NPS 从约 49.0 万 提升至 524,272 NPS (+6.8%)。
通过 cProfile 获取具体耗时子项数据对比：

- **实施前 (内含 __new__)**：`c_move_piece` 本身总耗时 **0.347s**。
- **实施后 (原位操作)**：`c_move_piece` 耗时 **0.347s**，再加上新增的测算回退 `c_unmake_piece` 耗时 **0.041s**，单一搜索操作节点的纯耗时总和变为 **0.388s**。

结论：单一搜索函数内部执行耗时实际上升约 0.041s，但消除了内存垃圾回收和由于置换表带来的对象封包损耗从而换取了总 NPS 提升。
*(注：这种单体微观耗时的“不降反升”，部分源于 cProfile 探针自身的观察者效应。极纯粹的 C 函数执行极快，此时挂载探针所带来的进出栈日志开销反而成为了显性成本。开启探针后全局 NPS 被观察到下降至约 350k)*
结合 cProfile 的前 5 排行：

```text
   ncalls  tottime  percall  cumtime  percall filename:lineno(function)
   219336    0.361    0.000    0.361    0.000 core/evaluation_logic.pyx:111(c_evaluate_board)
699801/411699    0.347    0.000    0.155    0.000 core/game_logic.pyx:232(c_move_piece)
535695/97    0.309    0.000    0.001    0.000 core/ai.pyx:318(_alpha_beta)
   133554    0.142    0.000    0.142    0.000 core/game_logic.pyx:275(c_get_ordered_moves)
   411699    0.041    0.000    0.041    0.000 core/game_logic.pyx:257(c_unmake_piece)
```

下一个优化对象应重新确立为静态评估 `c_evaluate_board` 或算法逻辑调整。

## 4. 2026-03-10 Phase 3 彻底实现 Zero-Allocation 与 MVC 隔离

在经历了一次直接修改 move_piece 导致的测试集（及 MVC 历史指针）崩溃后，我们吸取了教训：在 game_logic.pyx 中，将需要保留历史记录的对外接口 move_piece 维持深拷贝，而重新编写了专供 AI Alpha-Beta 节点内部调用的 c_move_piece 和 c_unmake_piece (原生 C 数组与位的原位增减和还原)。同时，连根拔起了 i.pyx 中的 Python dict 置换表，使用 #define TT_SIZE 和 malloc(TTEntry*) 彻底静态化了枝干查询。

**结果与诊断**：
最新无探针测试达到 **524,272 NPS**。基于之前约 49.0 万的基础线，这 **+3.4 万 NPS (+6.8%)** 的固化提升，证明了剥离 Tuple/Dict 等高级对象分配的优化方向是正确的。根据上文提取的 cProfile 真实数据，当前系统的前三大耗时对象已**明确**发生转移：

1. **状态推演 (`c_move_piece` + `c_unmake_piece`)**：共耗时 **0.388s**，位列开销第一。证明原位修改与状态回退所引发的位运算和边界检查已成为核心阻力。
2. **静态评估 (`c_evaluate_board`)**：耗时 **0.361s**，紧随其后。在消除了内存申请阻断后，评估逻辑自身的纯数学计算量成为第二大显性瓶颈。
3. **走法生成 (`c_get_ordered_moves`)**：耗时 **0.142s**。

在所有外部测试用例 100% 修复完毕的闭环状态下，下阶段的所有优化规划必将且仅将针对上述确凿的耗时分布榜单进行靶向手术（如对静态评估进一步实施常量折叠或位级降维），。
