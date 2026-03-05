# 三炮十五兵 AI版

一款基于经典民间棋类游戏"三炮十五兵"的 Python 实现，配备智能 AI 对手。

![Python](https://img.shields.io/badge/Python-3.10+-blue)
![Cython](https://img.shields.io/badge/Cython-Optimized-green)
![License](https://img.shields.io/badge/License-MIT-yellow)

---

## ✨ 特性

- 🎮 **多种对战模式**: 人 vs AI、AI vs 人、AI vs AI、人 vs 人
- 🤖 **智能 AI**: Alpha-Beta 搜索 + 静默搜索 + 置换表
- ⏱️ **可配置难度**: 调整搜索深度和时间限制
- 🔄 **复盘功能**: 随时回顾和分析对局
- 💾 **棋谱管理**: 保存和加载 JSON 格式棋谱
- 🚀 **高性能**: 核心算法使用 Cython 优化

---

## 🚀 快速开始

```bash
# 运行游戏
python main.py
```

详细说明参见 [快速入门指南](docs/GUIDE_getting_started.md)

---

## 📖 游戏规则

### 棋盘布局

```
● ● ● ● ●    ← 15 个兵
● ● ● ● ●
● ● ● ● ●
. . . . .
. ◆ ◆ ◆ .    ← 3 个炮
```

### 移动规则

|   棋子   | 规则                                         |
| :------: | :------------------------------------------- |
| **兵** ● | 上下左右移动一格（目标为空位）               |
| **炮** ◆ | 移动一格，或隔空跳吃兵（中间为空，目标为兵） |

### 胜负判定

- **炮方胜**: 吃光所有兵
- **兵方胜**: 困住所有炮
- **和棋**: 同一局面重复 3 次

---

## 🏗️ 项目结构

```
Three_Cannons/
├── main.py              # 程序入口
├── src/                 # 源代码目录
│   ├── model/           # 数据层
│   │   ├── game_model.py    # 游戏模型
│   │   └── config.py        # 游戏配置
│   ├── view/            # 视图层
│   │   ├── main_window.py   # 主界面
│   │   └── dialogs.py       # 对话框
│   ├── controller/      # 控制层
│   │   └── orchestrator.py  # 协调器
│   ├── ai/              # AI模块
│   │   └── engine.py        # AI引擎
│   └── io/              # IO模块
│       └── game_io.py       # 棋谱读写
├── core/                # Cython 高性能模块
│   ├── game_logic.pyx   # 游戏逻辑
│   ├── ai.pyx           # AI搜索算法
│   ├── evaluation_logic.pyx  # 局面评估
│   └── zobrist_hashing.pyx   # 哈希计算
├── tests/               # 测试文件
└── docs/                # 项目文档
```

---

## 📚 文档

| 文档                                      | 说明                 |
| :---------------------------------------- | :------------------- |
| [模块概览](docs/REF_modules_overview.md)  | 各模块职责和依赖关系 |
| [架构设计](docs/REF_architecture.md)      | MVC 架构和数据流     |
| [API 接口](docs/REF_api_interfaces.md)    | 类和函数接口说明     |
| [快速入门](docs/GUIDE_getting_started.md) | 运行和使用指南       |

---

## 🔧 开发

### 重新编译 Cython 模块

```bash
pip install cython
python setup.py build_ext --inplace
```

### 运行测试

```bash
python -m pytest tests/
```

---

## 📝 许可证

MIT License
