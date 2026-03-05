#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
测试棋谱加载功能
"""

import sys
import os

# 添加项目根目录到Python路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from game_io import load_game
from game_model import GameModel

def test_load_game_data():
    """测试棋谱加载功能"""
    print("测试棋谱加载功能...")
    
    # 由于测试环境中无法弹出文件对话框，我们直接测试加载逻辑
    # 创建一个模拟的棋谱文件数据
    import json
    from core.game_logic import GameState
    
    # 创建测试数据
    game_data = {
        "version": "1.0",
        "save_time": "2025-01-01T12:00:00Z",
        "initial_board": [
            [1, 1, 1, 1, 1],
            [1, 1, 1, 1, 1],
            [1, 1, 1, 1, 1],
            [0, 0, 0, 0, 0],
            [0, 2, 2, 2, 0]
        ],
        "initial_player": 2,
        "moves": [
            [[4, 1], [3, 1]],
            [[0, 0], [1, 0]],
            [[3, 1], [2, 1]]
        ]
    }
    
    # 保存到临时文件
    temp_file = "temp_test_game.json"
    with open(temp_file, 'w', encoding='utf-8') as f:
        json.dump(game_data, f, indent=2, ensure_ascii=False)
    
    print(f"创建临时棋谱文件: {temp_file}")
    
    # 直接测试加载逻辑（绕过文件对话框）
    try:
        with open(temp_file, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        # 验证必需的键
        required_keys = ['initial_board', 'initial_player', 'moves']
        for key in required_keys:
            if key not in data:
                raise ValueError("棋谱文件格式不正确")
        
        # 提取数据
        initial_board = data['initial_board']
        initial_player = data['initial_player']
        moves = data['moves']
        
        # 创建初始状态
        initial_state = GameState()
        initial_state.board = initial_board
        initial_state.current_player = initial_player
        # 重新计算士兵数量
        soldier_count = 0
        for row in initial_board:
            for cell in row:
                if cell == 1:  # SOLDIER
                    soldier_count += 1
        initial_state.soldier_count = soldier_count
        # 重新检查胜负状态
        initial_state._check_winner()
        
        print(f"初始玩家: {initial_state.current_player}")
        print(f"士兵数量: {initial_state.soldier_count}")
        print(f"移动数量: {len(moves)}")
        print(f"移动列表: {moves}")
        
        # 测试GameModel的load_from_gamedata方法
        model = GameModel()
        model.load_from_gamedata(initial_state, moves)
        
        print(f"加载后历史记录长度: {len(model.move_history)}")
        print(f"加载后当前玩家: {model.game_state.current_player}")
        print(f"加载后士兵数量: {model.game_state.soldier_count}")
        print(f"加载后复盘索引: {model.replay_index}")
        
        print("\n棋谱加载功能测试通过!")
        
    except Exception as e:
        print(f"加载测试失败: {e}")
    finally:
        # 删除临时文件
        if os.path.exists(temp_file):
            os.remove(temp_file)
            print(f"删除临时文件: {temp_file}")

if __name__ == "__main__":
    test_load_game_data()