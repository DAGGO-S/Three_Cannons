#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
测试AIEngine类
"""

import sys
import os
import time

# 添加项目根目录到Python路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.game_logic import GameState, CANNON, EMPTY, SOLDIER
from core.search_manager import find_best_move_iterative_deepening, clear_transposition_table

def on_complete_callback(best_move):
    """AI计算完成后的回调函数"""
    print(f"AI计算完成，最佳走法: {best_move}")

def progress_callback(progress_info):
    """AI计算进度回调函数"""
    print(f"AI计算进度: {progress_info}")

def main():
    """主函数"""
    print("开始测试AIEngine...")
    
    # 创建一个游戏状态
    game_state = GameState()
    print("创建了初始游戏状态")
    
    # 创建AIEngine实例
    ai_engine = AIEngine()
    print("创建了AIEngine实例")
    
    # 创建AI配置
    config = {
        "depth": 3,
        "time_limit": 5.0  # 5秒时间限制
    }
    print("创建了AI配置")
    
    # 启动AI计算
    print("启动AI计算...")
    ai_engine.start_calculation(
        game_state=game_state,
        config=config,
        on_complete_callback=on_complete_callback,
        progress_callback=progress_callback
    )
    
    # 等待一段时间以观察结果
    time.sleep(6)
    
    # 检查AI是否正在计算
    print(f"AI正在计算: {ai_engine.is_calculating()}")
    
    print("测试完成")

if __name__ == "__main__":
    main()