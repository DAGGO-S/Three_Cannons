# Phase 3C: 彻底零分配 (Zero Allocation) 冲击百万 NPS 计划

此文件通过 `planning-with-files` 工作流长期维护。

## 目标设定
突破当前 ~141,769 NPS 的瓶颈，以“零 Python 对象分配” (First Principles) 为核心指引，挑战 50万~100万 NPS。
短期验证目标：暂时切断静默搜索（QS），通过改造出绝对纯 C 的 `evaluate_board`，观察极致基础算力的天花板，以及能否将部分战术标定融入静态评估。

## 阶段规划

### Phase 1: 剥离并纯 C 化静态评估
- [x] 屏蔽 `ai.pyx` 中的 `_quiescence_search`，使搜索树完全受控于固定 Depth。
- [x] 彻底抛弃 `collections.deque` 和 `set()`，利用 C 静态变量或位掩码重构炮方控制区与禁区推算。
- [x] 确保 `evaluate_board` 内不再有任何动态生命周期的 Python 对象实例化。
- [x] 重新测量基准 NPS，验证零分配的绝对收益。

### Phase 2: `get_valid_moves` C 数组投喂
- [x] 若评估加速达到预期，废弃让 `get_valid_moves` 返回 `[((r,c),(nr,nc)), ...]` 的逻辑。
- [x] 改为接收一个静态 C 数组指针：`cdef int num_moves = get_valid_moves_c(state, &moves_array)`。

### Phase 3: 考虑战术融合与极致状态推演 (Zero State Allocation)
- [ ] 探索基于位运算的静态战术标定，弥补去除 QS 后的视野缺陷。
- [ ] （备选进阶）将增量复制（memcpy）再次升级为单一状态对象的前向/回溯原位操作（Make/Unmake）。

## 遇到的错误与修复记录 (Errors Encountered)
| Error       | Attempt | Resolution |
| ----------- | ------- | ---------- |
| None so far | N/A     | N/A        |
