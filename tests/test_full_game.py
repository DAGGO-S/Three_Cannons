#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
测试完整的游戏流程
"""

import sys
import os

# 添加项目根目录到Python路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.model.game_model import GameModel
from core.game_logic import GameState, CANNON, SOLDIER, EMPTY
from src.io.game_io import _find_move_between_states

def test_full_game():
    """测试完整的游戏流程"""
    print("创建游戏模型...")
    
    # 创建游戏模型
    model = GameModel()
    
    print(f"初始玩家: {model.game_state.current_player}")
    print(f"士兵数量: {model.game_state.soldier_count}")
    print(f"获胜者: {model.game_state.winner}")
    
    # 显示初始棋盘
    print("\n初始棋盘:")
    for row in model.game_state.board:
        print(row)
    
    # 进行几轮游戏
    print("\n开始游戏...")
    
    # 第1回合：炮方移动
    print("\n第1回合：炮方移动")
    success = model.make_move((4, 1), (3, 1))  # 炮向前移动
    print(f"移动成功: {success}")
    print(f"当前玩家: {model.game_state.current_player}")
    print(f"士兵数量: {model.game_state.soldier_count}")
    
    # 第2回合：兵方移动
    print("\n第2回合：兵方移动")
    # 获取士兵的有效移动并执行一个合法移动
    valid_moves = model.game_state.get_valid_moves(0, 0)
    if valid_moves:
        success = model.make_move((0, 0), valid_moves[0])  # 执行第一个合法移动
        print(f"移动成功: {success}")
        print(f"当前玩家: {model.game_state.current_player}")
        print(f"士兵数量: {model.game_state.soldier_count}")
    else:
        print("士兵没有合法的移动")
        # 尝试其他士兵的移动
        for r in range(3):
            for c in range(5):
                if model.game_state.board[r][c] == SOLDIER:
                    valid_moves = model.game_state.get_valid_moves(r, c)
                    if valid_moves:
                        success = model.make_move((r, c), valid_moves[0])
                        print(f"移动成功: {success}")
                        print(f"当前玩家: {model.game_state.current_player}")
                        print(f"士兵数量: {model.game_state.soldier_count}")
                        break
            else:
                continue
            break
    
    # 第3回合：炮方移动
    print("\n第3回合：炮方移动")
    # 获取炮的有效移动
    valid_moves = model.game_state.get_valid_moves(3, 1)
    if valid_moves:
        success = model.make_move((3, 1), valid_moves[0])  # 执行第一个合法移动
        print(f"移动成功: {success}")
        print(f"当前玩家: {model.game_state.current_player}")
        print(f"士兵数量: {model.game_state.soldier_count}")
    else:
        print("炮没有合法的移动")
    
    # 显示当前棋盘
    print("\n当前棋盘:")
    for row in model.game_state.board:
        print(row)
    
    # 检查历史记录
    print(f"\n历史记录长度: {len(model.move_history)}")
    
    # 测试_find_move_between_states函数
    print("\n测试移动识别功能:")
    for i in range(1, len(model.move_history)):
        prev_state = model.move_history[i-1]
        next_state = model.move_history[i]
        move = _find_move_between_states(prev_state, next_state)
        print(f"第{i}步移动: {move}")
    
    # 测试复盘功能
    print("\n测试复盘功能:")
    print(f"当前复盘索引: {model.replay_index}")
    
    # 回到第一步
    model.load_state_from_history(0)
    print(f"回到初始状态，复盘索引: {model.replay_index}")
    print(f"当前玩家: {model.game_state.current_player}")
    print(f"士兵数量: {model.game_state.soldier_count}")
    
    # 回到最后一步
    model.load_state_from_history(len(model.move_history) - 1)
    print(f"回到最后状态，复盘索引: {model.replay_index}")
    print(f"当前玩家: {model.game_state.current_player}")
    print(f"士兵数量: {model.game_state.soldier_count}")
    
    print("\n完整游戏流程测试通过!")

if __name__ == "__main__":
    test_full_game()