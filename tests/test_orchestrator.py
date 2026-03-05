# test_orchestrator.py

import sys
import os

# 添加项目根目录到Python路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import tkinter as tk
from game_model import GameModel
from gui import GameGUI
from orchestrator import GameOrchestrator

# 创建一个简单的AI引擎模拟类
class MockAIEngine:
    def is_calculating(self):
        return False
    
    def start_calculation(self, game_state, config, on_complete_callback, progress_callback):
        pass
    
    def stop_calculation(self):
        pass

# 创建一个简单的配置模拟类
class MockConfig:
    def __init__(self):
        self.cannon_is_ai = False
        self.soldier_is_ai = False
    
    def get_all(self):
        return {}

# 简单测试
if __name__ == "__main__":
    # 创建根窗口但隐藏它
    root = tk.Tk()
    root.withdraw()
    
    # 创建模型
    model = GameModel()
    
    # 创建视图
    view = GameGUI(model)
    
    # 创建AI引擎和配置的模拟实例
    ai_engine = MockAIEngine()
    config = MockConfig()
    
    # 创建协调器
    orchestrator = GameOrchestrator(model, view, ai_engine, config)
    
    print("GameOrchestrator initialized successfully!")
    print("Model:", orchestrator.model)
    print("View:", orchestrator.view)
    print("AI Engine:", orchestrator.ai)
    print("Config:", orchestrator.config)
    
    # 销毁窗口
    view.destroy()
    root.destroy()