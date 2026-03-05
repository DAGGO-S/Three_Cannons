# 现代化实践建议

本文档提供框架升级和现代开发实践方面的建议。

---

## 1. 项目结构优化

### 当前结构

```
Three_Cannons/
├── main.py
├── game_model.py
├── orchestrator.py
├── gui.py
├── ai_engine.py
├── game_io.py
├── game_config.py
├── core/
│   ├── game_logic.pyx
│   ├── ai.pyx
│   └── ...
└── test_code/
```

### 建议结构

```
Three_Cannons/
├── src/
│   ├── __init__.py
│   ├── main.py
│   ├── model/
│   │   ├── __init__.py
│   │   ├── game_model.py
│   │   └── game_config.py
│   ├── view/
│   │   ├── __init__.py
│   │   ├── gui.py
│   │   └── settings_dialog.py
│   ├── controller/
│   │   ├── __init__.py
│   │   └── orchestrator.py
│   ├── ai/
│   │   ├── __init__.py
│   │   └── ai_engine.py
│   ├── io/
│   │   ├── __init__.py
│   │   └── game_io.py
│   └── core/
│       └── (Cython 模块)
├── tests/
│   ├── unit/
│   ├── integration/
│   └── conftest.py
├── docs/
├── pyproject.toml
└── README.md
```

**优先级**: ⭐⭐ 低（需要较大改动）

---

## 2. 包管理现代化

### 当前: setup.py

```python
# setup.py (传统方式)
from setuptools import setup
from Cython.Build import cythonize
```

### 建议: pyproject.toml

```toml
# pyproject.toml
[build-system]
requires = ["setuptools>=61.0", "cython>=3.0"]
build-backend = "setuptools.build_meta"

[project]
name = "three-cannon-fifteen-soldiers"
version = "1.0.0"
description = "三炮十五兵 AI版"
requires-python = ">=3.10"
dependencies = []

[project.optional-dependencies]
dev = [
    "pytest>=7.0",
    "pytest-cov>=4.0",
    "mypy>=1.0",
]

[tool.setuptools.packages.find]
where = ["src"]

[tool.pytest.ini_options]
testpaths = ["tests"]
python_files = ["test_*.py"]

[tool.mypy]
python_version = "3.10"
strict = true
```

**优先级**: ⭐⭐ 低

---

## 3. 测试覆盖率提升

### 当前状态

- 有较完整的测试文件
- 测试位于 `test_code/` 目录

### 建议改进

#### 3.1 使用 pytest fixtures

```python
# tests/conftest.py
import pytest
from src.model.game_model import GameModel
from src.ai.ai_engine import AIEngine

@pytest.fixture
def game_model():
    """提供干净的 GameModel 实例"""
    return GameModel()

@pytest.fixture
def ai_engine():
    """提供 AIEngine 实例"""
    return AIEngine()
```

#### 3.2 参数化测试

```python
@pytest.mark.parametrize("start,end,expected", [
    ((4, 1), (3, 1), True),   # 正常移动
    ((4, 1), (2, 1), True),   # 隔空跳吃
    ((4, 1), (4, 4), False),  # 非法移动
])
def test_cannon_moves(game_model, start, end, expected):
    # ...
```

#### 3.3 覆盖率目标

```bash
# 运行测试并生成覆盖率报告
pytest --cov=src --cov-report=html
```

**目标**: 核心逻辑覆盖率 > 80%

**优先级**: ⭐⭐⭐ 中

---

## 4. 类型检查

### 建议引入 mypy

```bash
pip install mypy
mypy src/
```

### 配置

```toml
# pyproject.toml
[tool.mypy]
python_version = "3.10"
warn_return_any = true
warn_unused_ignores = true

[[tool.mypy.overrides]]
module = "core.*"
ignore_missing_imports = true  # Cython 模块
```

**优先级**: ⭐⭐ 低

---

## 5. 日志系统

### 当前状态

使用 `print()` 输出调试信息

### 建议替换为 logging

```python
# src/utils/logger.py
import logging

def setup_logger(name: str, level: int = logging.INFO) -> logging.Logger:
    logger = logging.getLogger(name)
    logger.setLevel(level)
    
    handler = logging.StreamHandler()
    formatter = logging.Formatter(
        '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    handler.setFormatter(formatter)
    logger.addHandler(handler)
    
    return logger

# 使用
logger = setup_logger(__name__)
logger.info("AI 计算开始")
logger.debug(f"当前深度: {depth}")
```

**优先级**: ⭐⭐ 低

---

## 6. 配置管理

### 当前状态

配置硬编码在 `GameConfig` 类中

### 建议改进

#### 6.1 配置文件

```yaml
# config.yaml
game:
  cannon_player: "Human"
  soldier_player: "AI"

ai:
  depth: 8
  time_limit: 15.0
  memory_limit: 100000

ui:
  cell_size: 100
  theme: "dark"
```

#### 6.2 配置加载

```python
# src/utils/config.py
import yaml
from pathlib import Path

def load_config(path: Path = Path("config.yaml")) -> dict:
    if path.exists():
        with open(path) as f:
            return yaml.safe_load(f)
    return get_default_config()
```

**优先级**: ⭐ 低

---

## 7. 持续集成

### 建议添加 GitHub Actions

```yaml
# .github/workflows/test.yml
name: Tests

on: [push, pull_request]

jobs:
  test:
    runs-on: windows-latest
    
    steps:
    - uses: actions/checkout@v4
    
    - name: Set up Python
      uses: actions/setup-python@v4
      with:
        python-version: '3.10'
    
    - name: Install dependencies
      run: |
        pip install cython pytest pytest-cov
        python setup.py build_ext --inplace
    
    - name: Run tests
      run: pytest --cov=. --cov-report=xml
    
    - name: Upload coverage
      uses: codecov/codecov-action@v3
```

**优先级**: ⭐⭐ 低

---

## 8. 代码风格检查

### 建议工具

```bash
pip install black isort flake8
```

### 配置

```toml
# pyproject.toml
[tool.black]
line-length = 100
target-version = ['py310']

[tool.isort]
profile = "black"
line_length = 100

[tool.flake8]
max-line-length = 100
extend-ignore = ["E203", "W503"]
```

### 使用

```bash
black src/
isort src/
flake8 src/
```

**优先级**: ⭐⭐ 低

---

## 总结

| 改进项         | 优先级 | 收益  | 工作量 |
| :------------- | :----: | :---: | :----: |
| 测试覆盖率     |  ⭐⭐⭐   |  高   |   中   |
| pyproject.toml |   ⭐⭐   |  中   |   低   |
| 项目结构重组   |   ⭐⭐   |  中   |   高   |
| 类型检查       |   ⭐⭐   |  中   |   中   |
| 日志系统       |   ⭐⭐   |  低   |   低   |
| 配置管理       |   ⭐    |  低   |   中   |
| CI/CD          |   ⭐⭐   |  中   |   低   |
| 代码风格       |   ⭐⭐   |  低   |   低   |

---

## 相关文档

- [代码改进建议](SUGGEST_code_improvements.md)
- [性能优化建议](SUGGEST_performance_optimization.md)
