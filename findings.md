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
1. **评估函数扁平化**：移除所有依赖内置结构(`set`, `deque`)的检索算法，采用一维标志数组或位运算符（Bitwise operation）对棋盘防线及火力范围进行标记。
2. **走法生成静态化**：所有走法生成逻辑不可采用 `return list` 的形式。应要求函数接收预先申请好的 C 级别结构体数组指针，并在内部直接执行数据赋值。
