#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
简单测试游戏逻辑
"""

import sys
import os

# 添加项目根目录到Python路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.game_logic import GameState, CANNON, SOLDIER, EMPTY

def test_game_logic():
    """测试游戏逻辑"""
    print("创建初始游戏状态...")
    
    # 创建初始状态
    state = GameState()
    
    print(f"初始玩家: {state.current_player}")
    print(f"士兵数量: {state.soldier_count}")
    print(f"获胜者: {state.winner}")
    
    # 显示初始棋盘
    print("\n初始棋盘:")
    for row in state.board:
        print(row)
    
    # 测试获取有效移动
    print("\n测试获取有效移动:")
    # 炮的移动测试
    valid_moves = state.get_valid_moves(4, 1)  # 炮的位置
    print(f"炮在(4,1)的有效移动: {valid_moves}")
    
    # 士兵的移动测试
    valid_moves = state.get_valid_moves(0, 0)  # 士兵的位置
    print(f"士兵在(0,0)的有效移动: {valid_moves}")
    
    # 测试执行移动
    print("\n测试执行移动:")
    # 获取炮的有效移动并执行一个合法移动
    valid_moves = state.get_valid_moves(4, 1)  # 炮的位置
    if valid_moves:
        # 执行一个合法的炮移动
        new_state = state.move_piece(4, 1, valid_moves[0][0], valid_moves[0][1])
        print(f"移动后玩家: {new_state.current_player}")
        print(f"移动后士兵数量: {new_state.soldier_count}")
        print(f"移动后获胜者: {new_state.winner}")
        
        print("\n移动后棋盘:")
        for row in new_state.board:
            print(row)
    else:
        print("没有合法的移动可执行")
    
    print("\n游戏逻辑测试通过!")

if __name__ == "__main__":
    test_game_logic()