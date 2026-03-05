import sys
import os
import unittest
import json
from unittest.mock import patch, mock_open, MagicMock

# 添加项目根目录到Python路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from game_io import save_game, load_game
from core.game_logic import GameState, CANNON, SOLDIER, EMPTY
from game_model import GameModel

class TestGameIO(unittest.TestCase):
    """测试GameIO模块的核心功能"""
    
    def setUp(self):
        """测试前的准备工作"""
        # 创建一个简单的游戏状态用于测试
        self.test_state = GameState()
        
        # 创建一个GameModel实例用于测试
        self.test_model = GameModel()
        # 添加一些测试状态到历史记录中，确保有移动可以保存
        state1 = GameState()
        state2 = GameState()
        # 修改state2的棋盘以模拟移动
        state2.board = [row[:] for row in state1.board]
        state2.board[4][1] = EMPTY  # 移动炮
        state2.board[2][1] = CANNON
        self.test_model.move_history = [state1, state2]
        
        # 创建一些测试走法
        self.test_moves = [
            ((0, 0), (1, 1)),
            ((9, 9), (8, 8))
        ]
    
    @patch('tkinter.filedialog.asksaveasfilename')
    @patch('builtins.open', new_callable=mock_open)
    def test_save_game_success(self, mock_file, mock_filedialog):
        """测试成功保存游戏"""
        # 模拟filedialog.asksaveasfilename返回一个虚拟路径
        mock_filedialog.return_value = "C:/temp/test.json"
        
        # 调用save_game
        result = save_game(self.test_model)
        
        # 断言asksaveasfilename被调用
        mock_filedialog.assert_called_once()
        
        # 断言open被调用
        mock_file.assert_called_once_with("C:/temp/test.json", 'w', encoding='utf-8')
        
        # 断言json.dump被调用
        handle = mock_file()
        self.assertTrue(handle.write.called)
        
        # 验证写入的内容
        written_data = ''.join(call.args[0] for call in handle.write.call_args_list)
        game_data = json.loads(written_data)
        
        # 验证game_data结构和内容（符合新的JSON格式）
        self.assertIn('metadata', game_data)
        self.assertIn('save_time', game_data['metadata'])
        self.assertIn('initial_board', game_data)
        self.assertIn('current_player', game_data)
        self.assertIn('moves', game_data)
        self.assertEqual(len(game_data['moves']), 1)  # 应该有一个移动
    
    @patch('tkinter.filedialog.asksaveasfilename')
    def test_save_game_user_cancel(self, mock_filedialog):
        """测试用户取消保存"""
        # 模拟filedialog.asksaveasfilename返回空字符串
        mock_filedialog.return_value = ""
        
        # 调用save_game
        result = save_game(self.test_model)
        
        # 断言返回"保存操作已取消"的消息
        self.assertEqual(result, "保存操作已取消。")
    
    @patch('tkinter.filedialog.asksaveasfilename')
    def test_save_game_no_moves(self, mock_filedialog):
        """测试无走法保存"""
        # 模拟filedialog.asksaveasfilename返回一个虚拟路径
        mock_filedialog.return_value = "C:/temp/test.json"
        
        # 创建一个只有初始状态的GameModel
        empty_model = GameModel()
        empty_model.move_history = [self.test_state]  # 只有一个状态
        
        # 调用save_game
        result = save_game(empty_model)
        
        # 断言返回"没有走法..."的消息
        self.assertEqual(result, "没有走法，无法保存棋谱。")
    
    @patch('tkinter.filedialog.askopenfilename')
    @patch('builtins.open', new_callable=mock_open, read_data='{"metadata": {"save_time": "2025-01-01 12:00:00"}, "initial_board": [[0, 0, 0, 0, 0], [0, 0, 0, 0, 0], [0, 0, 0, 0, 0], [0, 0, 0, 0, 0], [0, 0, 2, 0, 0]], "current_player": 1, "moves": [[[0, 0], [1, 1]]]}')
    def test_load_game_success(self, mock_file, mock_filedialog):
        """测试成功加载游戏"""
        # 模拟filedialog.askopenfilename返回一个虚拟路径
        mock_filedialog.return_value = "C:/temp/test.json"
        
        # 调用load_game
        result = load_game()
        
        # 断言返回的不是None
        self.assertIsNotNone(result)
        
        # 断言返回的是一个元组
        self.assertIsInstance(result, tuple)
        
        # 断言元组包含GameState和moves
        state, moves = result
        self.assertIsInstance(state, GameState)
        self.assertIsInstance(moves, list)
    
    @patch('tkinter.filedialog.askopenfilename')
    @patch('builtins.open', new_callable=mock_open, read_data='{"invalid": "data"}')
    def test_load_game_invalid_format(self, mock_file, mock_filedialog):
        """测试加载失败 - 格式错误"""
        # 模拟filedialog.askopenfilename返回一个虚拟路径
        mock_filedialog.return_value = "C:/temp/test.json"
        
        # 调用load_game
        result = load_game()
        
        # 断言返回None
        self.assertIsNone(result)
    
    @patch('tkinter.filedialog.askopenfilename')
    @patch('builtins.open', new_callable=mock_open, read_data='{"metadata": {"save_time": "2025-01-01 12:00:00"}, "initial_board": [[0, 0, 0, 0, 0], [0, 0, 0, 0, 0], [0, 0, 0, 0, 0], [0, 0, 0, 0, 0], [0, 0, 2, 0, 0]], "current_player": 1}')
    def test_load_game_missing_keys(self, mock_file, mock_filedialog):
        """测试加载失败 - 缺少键"""
        print("测试加载失败 - 缺少键...")
        
        # 模拟filedialog.askopenfilename返回一个虚拟路径
        mock_filedialog.return_value = "C:/temp/test.json"
        
        # 调用load_game
        result = load_game()
        
        # 断言返回None
        self.assertIsNone(result)
        
        print("✓ 加载失败 - 缺少键测试通过")

if __name__ == "__main__":
    unittest.main()