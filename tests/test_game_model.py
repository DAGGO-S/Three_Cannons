import sys
import os
import unittest
from unittest.mock import patch, MagicMock

# 添加项目根目录到Python路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from game_model import GameModel
from core.game_logic import GameState, CANNON, SOLDIER, EMPTY

class TestGameModel(unittest.TestCase):
    """测试GameModel类的核心功能"""
    
    def setUp(self):
        """测试前的准备工作"""
        self.model = GameModel()
    
    def test_reset(self):
        """测试reset方法"""
        print("测试reset方法...")
        
        # 调用reset方法
        self.model.reset()
        
        # 验证move_history列表中只有一个元素
        self.assertEqual(len(self.model.move_history), 1)
        
        # 验证replay_index为0
        self.assertEqual(self.model.replay_index, 0)
        
        # 验证is_replay_mode为False
        self.assertFalse(self.model.is_replay_mode)
        
        print("✓ reset方法测试通过")
    
    def test_make_move_history_growth(self):
        """测试make_move历史增长"""
        print("测试make_move历史增长...")
        
        # 记录初始历史长度
        initial_length = len(self.model.move_history)
        
        # 执行一次移动
        self.model.make_move((4, 1), (3, 1))
        
        # 验证历史长度增加1
        self.assertEqual(len(self.model.move_history), initial_length + 1)
        
        print("✓ make_move历史增长测试通过")
    
    def test_make_move_replay_fork(self):
        """测试复盘分叉（使用合法的走法序列）"""
        print("测试复盘分叉...")
        
        # Arrange: 创建一个合法的历史
        # S0: 初始, C turn
        self.model.make_move((4, 1), (3, 1))  # S1: C moved, S turn
        # 在第一步后，棋盘状态变为：
        # 第3行第1列是炮，第4行第1列是空格
        # 现在兵方回合，我们需要找到一个兵可以移动到的空格
        # 第3行除了第1列是炮，其他都是空格
        self.model.make_move((2, 0), (3, 0))  # S2: S moved, C turn
        self.assertEqual(len(self.model.move_history), 3)

        # Act 1: 回到 S1 状态 (兵方回合)
        self.model.load_state_from_history(1)
        self.assertTrue(self.model.is_replay_mode)
        self.assertEqual(self.model.game_state.current_player, SOLDIER)

        # Act 2: 从 S1 状态走一步新的、合法的兵方棋
        # 原始历史中兵走的是 (2,0)->(3,0)。我们走一步不同的 (2,2)->(3,2)
        # 注意：此时(3,2)位置是空格，可以移动
        self.model.make_move((2, 2), (3, 2)) # S_new_2: S moved, C turn

        # Assert: 验证历史被截断
        # 新历史应为 [S0, S1, S_new_2]
        self.assertEqual(len(self.model.move_history), 3)
        self.assertFalse(self.model.is_replay_mode)
        # 验证新历史的最后一步是炮方回合
        self.assertEqual(self.model.game_state.current_player, CANNON)
        
        print("✓ 复盘分叉测试通过")
    
    def test_load_state_from_history_valid_index(self):
        """测试load_state_from_history加载有效索引"""
        print("测试load_state_from_history加载有效索引...")
        
        # 加载一个有效索引
        result = self.model.load_state_from_history(0)
        
        # 验证返回值为True
        self.assertTrue(result)
        
        # 验证game_state已被正确切换
        self.assertEqual(self.model.game_state, self.model.move_history[0])
        
        # 验证is_replay_mode为True
        self.assertTrue(self.model.is_replay_mode)
        
        print("✓ 加载有效索引测试通过")
    
    def test_load_state_from_history_invalid_index(self):
        """测试load_state_from_history加载无效索引"""
        print("测试load_state_from_history加载无效索引...")
        
        # 记录原始状态
        original_state = self.model.game_state
        original_is_replay_mode = self.model.is_replay_mode
        
        # 加载一个无效的索引（如-1）
        result = self.model.load_state_from_history(-1)
        
        # 验证返回值为False
        self.assertFalse(result)
        
        # 验证模型状态不改变
        self.assertEqual(self.model.game_state, original_state)
        self.assertEqual(self.model.is_replay_mode, original_is_replay_mode)
        
        print("✓ 加载无效索引测试通过")
    
    def test_load_from_gamedata(self):
        """测试load_from_gamedata方法"""
        print("测试load_from_gamedata方法...")
        
        # 创建预设的initial_state和moves列表
        initial_state = GameState()
        # 使用合法的移动步骤
        moves = [
            ((4, 1), (3, 1)),  # 炮从(4,1)移动到(3,1) - 合法移动
            ((2, 0), (3, 0)),  # 兵从(2,0)移动到(3,0) - 合法移动
            ((3, 1), (3, 2))   # 炮从(3,1)移动到(3,2) - 合法移动
        ]
        
        # 调用load_from_gamedata
        self.model.load_from_gamedata(initial_state, moves)
        
        # 验证最终的game_state是所有moves都执行完毕后的状态
        # 注意：由于我们移除了load_from_gamedata中的异常处理，所有移动都必须是合法的
        self.assertEqual(len(self.model.move_history), 4)  # 初始状态+3步移动
        
        # 验证move_history包含了从初始状态到最终状态的所有步骤
        self.assertEqual(self.model.move_history[0].board, initial_state.board)
        
        print("✓ load_from_gamedata方法测试通过")

if __name__ == "__main__":
    unittest.main()