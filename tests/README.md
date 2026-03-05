# 测试文件组织说明

为了保持项目结构的整洁和模块化，所有测试文件都统一放在这个 `test_code` 目录中。

## 测试文件分类

### 核心功能测试
- `test_game.py` - 游戏核心逻辑测试
- `test_game_io.py` - 游戏输入输出功能测试
- `test_game_model_fix.py` - 游戏模型修复测试
- `test_ai.py` - AI核心算法测试

### 集成测试
- `test_full_game.py` - 完整游戏流程测试
- `test_simple_game.py` - 简单游戏流程测试

### 组件测试
- `test_ai_engine.py` - AI引擎功能测试
- `test_load_game.py` - 棋谱加载功能测试
- `test_orchestrator.py` - 游戏协调器测试

### 其他测试
- `simple_test.py` - 简单功能验证测试

## 运行测试

可以使用以下方式运行测试：

```bash
# 运行单个测试文件
python -m test_code.test_game

# 运行所有测试（如果项目支持）
python -m unittest discover test_code
```