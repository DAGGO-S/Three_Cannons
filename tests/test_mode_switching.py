import unittest
from unittest.mock import MagicMock, patch
import sys
import os

# 添加项目根目录到路径
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from src.model.game_model import GameModel
from src.controller.orchestrator import GameOrchestrator
from src.ai.engine import AIEngine
from src.model.config import GameConfig
from core.game_logic import GameState, CANNON, SOLDIER
from core.search_manager import find_best_move_iterative_deepening, init_tablebases


class TestModeSwitching(unittest.TestCase):
    """测试模式切换的集成测试类"""
    
    def setUp(self):
        """测试前的准备工作"""
        # 创建真实的GameModel
        self.model = GameModel()
        
        # 创建模拟的GameGUI
        self.mock_view = MagicMock()
        
        # 创建AI引擎和配置
        self.ai_engine = AIEngine()
        self.config = GameConfig()
        self.config.update({"cannon_player": "Human", "soldier_player": "Human"})
        
        # 创建Orchestrator，传入真实的model和模拟的view
        self.orchestrator = GameOrchestrator(self.model, self.mock_view, self.ai_engine, self.config)
    
    def test_switch_from_live_to_replay_mode(self):
        """测试从对战模式切换到复盘模式"""
        print("测试 对战 -> 复盘 切换...")
        
        # Act 1: 模拟炮方走一步合法的棋
        self.orchestrator.on_canvas_click(4, 1) # 选炮
        self.orchestrator.on_canvas_click(3, 1) # 走子
        
        # Assert 1: 确认处于对战模式
        self.assertGreaterEqual(self.mock_view.update_button_states.call_count, 2)
        # >>> 修正！使用 .kwargs 访问关键字参数 <<<
        final_kwargs = self.mock_view.update_button_states.call_args.kwargs
        self.assertFalse(final_kwargs['is_replay_mode'])
        
        # Act 2: 模拟玩家点击"悔棋"（前一步）
        self.orchestrator.on_prev_move()
        
        # Assert 2: 验证悔棋后进入复盘模式
        final_kwargs = self.mock_view.update_button_states.call_args.kwargs
        self.assertTrue(final_kwargs['is_replay_mode'])
        self.assertEqual(self.model.replay_index, 0)
        
        print("✓ 对战 -> 复盘 切换测试通过。")
    
    def test_switch_from_replay_to_live_mode(self):
        """测试从复盘模式切换到对战模式"""
        print("测试 复盘 -> 对战 切换...")

        # Arrange: 创建一个有2步历史的对局
        self.orchestrator.model.make_move((4, 1), (3, 1)) # C. 轮到兵
        self.orchestrator.model.make_move((2, 2), (3, 2)) # S. 轮到炮

        # 进入复盘模式，回到第1步之后的状态 (轮到兵方)
        self.orchestrator.on_prev_move()
        self.assertTrue(self.orchestrator.model.is_replay_mode)
        
        # Act: 模拟玩家在复盘时，走一步合法的兵棋
        # 在 S1 状态下，兵(2,1) 可以移动到空格 (1,1)
        self.orchestrator.on_canvas_click(2, 0) # 选兵 (2,0)
        self.orchestrator.on_canvas_click(3, 0) # >>> 修正！走子到合法的空格 (3,0) <<<
        
        # Assert: 验证走完新棋后切换到对战模式
        self.assertFalse(self.orchestrator.model.is_replay_mode)
        # 历史应为 [S0, S1, S_new_2]
        self.assertEqual(len(self.model.move_history), 3)

        print("✓ 复盘 -> 对战 切换测试通过。")

    def test_undo_button_should_be_enabled_in_live_mode(self):
        """测试：在对战模式下走一步棋后，悔棋（前一步）按钮应被启用"""
        print("测试对战模式下的悔棋按钮可用性...")

        # Arrange: 确认初始状态下，悔棋按钮是禁用的
        # 我们需要访问按钮对象本身，所以我们用一个真实的 view
        from src.view.main_window import GameGUI
        with patch('tkinter.Tk'): # 避免创建真实窗口
            real_view = GameGUI(self.model)
        orchestrator = GameOrchestrator(self.model, real_view, self.ai_engine, self.config)
        
        # 初始刷新，此时历史记录为1
        orchestrator.update_view()
        self.assertEqual(real_view.prev_move_btn['state'], 'disabled')
        
        # Act: 模拟玩家走一步棋
        orchestrator.on_canvas_click(4, 1) # 选炮
        orchestrator.on_canvas_click(3, 1) # 走子
        
        # Assert: 走完棋后，历史记录大于1，悔棋按钮必须被启用
        self.assertEqual(real_view.prev_move_btn['state'], 'normal',
                         "在走了一步棋之后，'前一步'（悔棋）按钮必须是可用的！")

        print("✓ 对战模式下悔棋按钮可用性测试场景已建立。")


if __name__ == '__main__':
    unittest.main()