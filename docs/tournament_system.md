# 实现方案：公平对战系统 (Fair Tournament System)

## 0. 核心痛点
-   兵种不对称（炮 vs 兵），胜率本身就不容易是 50%。
-   如何判断参数 A 真的比 B 强，而不是因为 A 拿到了优势较大的那一一方（比如炮）？

## 1. 解决方案：Double Round-Robin (双循环/分先)
**“每一场对决必须成对出现 (Pairwise Matches)”**
-   **Round 1**: 模型 A (执炮) vs 模型 B (执兵) -> 结果 R1
-   **Round 2**: 模型 B (执炮) vs 模型 A (执兵) -> 结果 R2
-   **净胜分** (Score) = R1 + R2

**判定标准**：
-   若 A 在两场中总分胜出（例如：A赢了B，B没赢A），则 A 强。
-   若 A、B 都赢了各自的炮方（或者都输了），说明差距不大。

## 2. 系统设计 (script/arena.py)
这是一个**无头 (Headless)** 脚本，不依赖 `main_window.py` 或 `tkinter`。

### 2.1 核心类 `Arena`
-   **输入**：两个配置字典 `config_A` 和 `config_B`。
-   **比赛流程**：
    1.  初始化 `GameModel`。
    2.  初始化两个 `AIEngine` 实例（Engine A, Engine B）。
    3.  **Game 1**: `Engine A` 思考炮，`Engine B` 思考兵。
        -   循环调用 `engine.get_best_move` 直到分出胜负或由 Referee 判和。
        -   记录结果。
    4.  **Game 2**: 交换持方。
    5.  返回 Pair 结果。

### 2.2 裁判系统 (Referee)
-   **判和机制**：
    -   超过 N 回合（如 100）未分胜负 -> 和棋。
    -   重复局面 3 次 -> 和棋（利用 Zobrist Hash）。
    -   双方无吃子超过 M 步 -> 和棋。

### 2.3 并行加速 (Multiprocessing)
-   Python 的 GIL 会限制单核效率。
-   使用 `concurrent.futures.ProcessPoolExecutor`。
-   同时开 4-8 个 Arena 进程跑不同的 Pair。
-   **目标效率**：1 分钟跑完 100 场。

## 3. 参数注入接口
我们需要修改 `src/ai/engine.py` 或 `core/evaluation_logic.pyx`，允许从外部 `config` 动态传入评估参数（权重）。
-   目前 `DEFAULT_SETTINGS` 是写死的。
-   **修改**：在 `evaluate_board` 中，优先使用传入的 `settings` 字典。
-   这样 `Engine A` 和 `Engine B` 就可以拥有完全不同的价值观。

## 4. 预期产出
运行 `python scripts/arena.py`：
```text
Match 1 (A=Cannon): A Wins!
Match 1 (B=Cannon): B Wins!
...
Total Score:
Model A (Challenger): 55.5
Model B (Baseline):   44.5
Result: Challenger is BETTER (+11.0 Elo)
```
