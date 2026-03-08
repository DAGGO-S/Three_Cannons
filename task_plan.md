# Phase 3C: 彻底零分配 (Zero Allocation) 冲击百万 NPS 计划

此文件通过 `planning-with-files` 工作流长期维护。

## 目标设定
突破当前 ~141,769 NPS 的瓶颈，以“零 Python 对象分配” (First Principles) 为核心指引，挑战 50万~100万 NPS。

## 阶段规划

### Phase 1: 评估函数 `evaluate_board` 的零分配改造
- [ ] 重构炮方控制区鉴定，移除 BFS (`collections.deque`)。
- [ ] 移除所有的 `set` 集合和元组，改用简单的 C array 作为检查掩码，或 Bitboard。
- [ ] 确保 `evaluate_board` 内部没有任何 Python 类型（包含 `{}`，`set()`，`list`）被生成。

### Phase 2: `get_valid_moves` C 数组投喂
- [ ] 废弃让 `get_valid_moves` 返回 `[((r,c),(nr,nc)), ...]` 的逻辑。
- [ ] 改为接收一个静态 C 数组指针：`cdef int num_moves = get_valid_moves_c(state, &moves_array)`。

### Phase 3: Option C 原位操作 (Zero State Allocation)
- [ ] 从不断创建新的 `GameState` 实例，改为 `make_move / unmake_move`。
- [ ] 深度搜索自始至终只维护单一 `CGameState` 内存指针。
- [ ] 同步修改 Zobrist 状态树的维护方法。

## Errors Encountered
| Error | Attempt | Resolution |
| ----- | ------- | ---------- |
| ...   | 1       | ...        |
