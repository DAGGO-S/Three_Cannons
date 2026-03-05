# AI模块重构说明

## 重构目标
对旧版本的`ai.pyx`进行重构，主要进行"净化"和接口标准化工作，确保它能被`AIEngine`干净利落地调用。

## 主要改动

### 1. 标准化主入口函数
- 保留`find_best_move_iterative_deepening`函数，确认其签名与`AIEngine`的调用方式完全匹配
- 函数接口设计良好，无需修改

### 2. 处理全局状态
- 最重要的改动是将置换表的清理逻辑移到一个新的公开函数`clear_transposition_table()`中
- 从`find_best_move_iterative_deepening`内部移除了置换表的清理逻辑
- 将置换表的生命周期管理权交给了上层的`AIEngine`，使得`ai.pyx`模块更加无状态和可控

### 3. 确认异步停止机制
- 代码已经完美地集成了`stop_event`
- 无需任何修改，完全符合新架构中`AIEngine`的异步停止要求

### 4. 代码净化
- 从内部函数（如`_alpha_beta`和`_adaptive_quiescence_search`）的签名中移除了不再需要的`use_threading`和`thread_count`参数
- 这些参数在新架构中是冗余的，因为多线程的管理完全由`AIEngine`负责

## 重构后的优势
1. **无状态性**：通过将置换表的管理权交给`AIEngine`，`ai.pyx`模块变得更加无状态
2. **接口清晰**：移除了不必要的参数，使函数签名更加简洁明了
3. **可控性增强**：上层可以更好地控制AI模块的生命周期
4. **兼容性保持**：核心搜索算法（PVS、静默搜索等）保持不变，确保性能不受影响

## 使用方式
在`AIEngine`中，每次开始新的计算前调用`clear_transposition_table()`来清空置换表，然后正常调用`find_best_move_iterative_deepening()`函数进行计算。