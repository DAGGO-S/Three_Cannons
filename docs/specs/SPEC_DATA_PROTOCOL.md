# SPEC: 数据存储协议

本文档规范了棋谱存档与训练数据集的物理存储格式。

## 1. 棋谱存档格式：JSON
文件头包含元数据段，随后是走法序列。

```json
{
  "metadata": {
    "version": "1.0",
    "date": "2026-03-22",
    "mode": "AB_Engine",
    "result": "Cannon_Wins"
  },
  "history": [
    {"move": [4, 1, 3, 1], "side": "c", "fen": "..."},
    {"move": [0, 0, 1, 0], "side": "p", "fen": "..."}
  ]
}
```

## 2. 训练数据集规范：JSONL
每一行代表一个独立局面及其搜索标签，用于 NNUE 训练。

```json
{"fen": "...", "score": 248, "depth": 10, "best_move": [2, 2, 2, 3]}
```

## 3. 文件命名约定
- 实验对战对局：`data/history/*.json`
- 原始训练语料：`data/training/run*.jsonl`
