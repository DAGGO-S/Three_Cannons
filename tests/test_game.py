#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
测试游戏核心玩法循环
"""

import sys
import os

# 添加项目根目录到Python路径
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, project_root)

from game_model import GameModel
from gui import GameGUI
from orchestrator import GameOrchestrator

class MockAIEngine:
    """模拟AI引擎"""
    def __init__(self):
        self._is_calculating = False
    
    def is_calculating(self):
        return self._is_calculating
    
    def start_calculation(self, game_state, config, on_complete_callback, progress_callback):
        """模拟开始计算"""
        self._is_calculating = True
        # 模拟立即完成计算
        import time
        time.sleep(0.1)  # 短暂延迟
        self._is_calculating = False
        # 查找一个合法的走法
        # 遍历棋盘找到当前玩家的棋子
        from core.game_logic import CANNON, SOLDIER
        valid_move_found = False
        move = None
        
        for r in range(5):
            for c in range(5):
                piece = game_state.board[r][c]
                # 检查是否是当前玩家的棋子
                if (game_state.current_player == CANNON and piece == CANNON) or \
                   (game_state.current_player == SOLDIER and piece == SOLDIER):
                    # 获取该棋子的合法走法
                    valid_moves = game_state.get_valid_moves(r, c)
                    if valid_moves:
                        # 选择第一个合法走法
                        move = ((r, c), valid_moves[0])
                        valid_move_found = True
                        break
            if valid_move_found:
                break
        
        # 如果找到了合法走法，则调用回调函数
        if valid_move_found:
            on_complete_callback(move)
        else:
            # 如果没有找到合法走法，使用默认的非法走法以触发错误
            on_complete_callback(((1, 1), (2, 2)))
    
    def stop_calculation(self):
        """模拟停止计算"""
        self._is_calculating = False

class MockConfig:
    """模拟配置"""
    def __init__(self):
        # 默认配置
        self.ai_mode = {
            "player_cannon": "human",  # "human" 或 "ai"
            "player_soldier": "ai"     # "human" 或 "ai"
        }
        self.ai_settings = {
            "depth": 5,
            "time_limit": 10.0
        }
    
    def get_all(self):
        """返回所有配置设置"""
        return {
            "player_cannon": self.ai_mode["player_cannon"],
            "player_soldier": self.ai_mode["player_soldier"],
            "depth": self.ai_settings["depth"],
            "time_limit": self.ai_settings["time_limit"]
        }
    
    def update(self, new_config):
        """批量更新配置"""
        # 更新玩家类型设置
        if "player_cannon" in new_config:
            self.ai_mode["player_cannon"] = new_config["player_cannon"]
        if "player_soldier" in new_config:
            self.ai_mode["player_soldier"] = new_config["player_soldier"]
            
        # 更新AI设置
        if "depth" in new_config:
            self.ai_settings["depth"] = new_config["depth"]
        if "time_limit" in new_config:
            self.ai_settings["time_limit"] = new_config["time_limit"]
    
    def is_ai_turn(self, current_player):
        """检查当前玩家是否为AI"""
        from core.game_logic import CANNON, SOLDIER
        if current_player == CANNON:
            return self.ai_mode["player_cannon"] == "ai"
        elif current_player == SOLDIER:
            return self.ai_mode["player_soldier"] == "ai"
        return False

def main():
    """主函数"""
    # 创建游戏组件
    model = GameModel()
    view = GameGUI(model)
    ai_engine = MockAIEngine()
    config = MockConfig()
    
    # 创建协调器
    orchestrator = GameOrchestrator(model, view, ai_engine, config)
    
    # 启动GUI
    view.run()

if __name__ == "__main__":
    main()