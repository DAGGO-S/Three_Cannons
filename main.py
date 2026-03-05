# main.py - 程序入口

import sys
import os

# 将项目根目录添加到路径
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from src.model.game_model import GameModel
from src.model.config import GameConfig
from src.view.main_window import GameGUI
from src.ai.engine import AIEngine
from src.controller.orchestrator import GameOrchestrator


def main():
    """主程序入口"""
    # 创建所有核心组件
    model = GameModel()
    view = GameGUI(model)
    ai_engine = AIEngine()
    config = GameConfig()
    
    # 创建协调器，将所有组件连接在一起
    orchestrator = GameOrchestrator(model, view, ai_engine, config)
    
    # 启动GUI事件循环
    view.run()


if __name__ == "__main__":
    main()