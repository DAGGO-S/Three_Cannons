# test_ai_engine.py (Corrected and Reliable Version)

import sys
import os
import unittest
import threading
from unittest.mock import patch, MagicMock, ANY

# 添加项目根目录到Python路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from ai_engine import AIEngine
from core.game_logic import GameState

class TestAIEngine(unittest.TestCase):
    """测试AIEngine类的核心功能（已修复，可靠且快速）"""
    
    def setUp(self):
        """测试前的准备工作"""
        self.ai_engine = AIEngine()
        # 为每个测试设置一个同步Event
        self.worker_done_event = threading.Event()
        self.ai_engine._test_hook_worker_done_event = self.worker_done_event

    def tearDown(self):
        """确保线程在测试后结束"""
        if self.ai_engine.is_calculating():
            self.ai_engine.stop_calculation()
            self.worker_done_event.wait(timeout=1)

    @patch('ai_engine.find_best_move_iterative_deepening')
    @patch('ai_engine.clear_transposition_table')
    def test_start_calculation_normal_flow(self, mock_clear_tt, mock_find_best_move):
        """测试start_calculation正常流程"""
        # Arrange
        expected_move = ((1, 1), (2, 2))
        mock_find_best_move.return_value = expected_move
        on_complete_callback = MagicMock()

        # Act
        self.ai_engine.start_calculation(GameState(), {}, on_complete_callback, MagicMock())
        
        # Assert
        # 等待worker线程完成，而不是盲目sleep
        self.assertTrue(self.worker_done_event.wait(timeout=1), "Worker thread did not finish in time.")
        
        mock_clear_tt.assert_called_once()
        mock_find_best_move.assert_called_once()
        on_complete_callback.assert_called_once_with(expected_move)
        self.assertFalse(self.ai_engine.is_calculating())

    @patch('ai_engine.find_best_move_iterative_deepening')
    def test_stop_calculation_interrupts_flow(self, mock_find_best_move):
        """测试stop_calculation中断流程"""
        # Arrange
        # 模拟一个会检查停止事件的长时间运行任务
        def long_running_ai(*args, **kwargs):
            stop_event = kwargs['settings']['stop_event']
            # 等待被停止
            stopped = stop_event.wait(timeout=0.5)
            return None # 如果被停止，返回None
        
        mock_find_best_move.side_effect = long_running_ai
        on_complete_callback = MagicMock()

        # Act
        self.ai_engine.start_calculation(GameState(), {}, on_complete_callback, MagicMock())
        
        # 确认线程已启动
        self.assertTrue(self.ai_engine.is_calculating())
        self.ai_engine.stop_calculation() # 发出停止信号

        # Assert
        # 等待worker结束（因为它应该检测到停止信号并退出）
        self.assertTrue(self.worker_done_event.wait(timeout=1), "Worker thread did not stop in time.")
        
        # 因为被中断，on_complete不应该被调用
        on_complete_callback.assert_not_called()
        self.assertFalse(self.ai_engine.is_calculating())

    @patch('ai_engine.find_best_move_iterative_deepening')
    def test_progress_callback_is_called(self, mock_find_best_move):
        """测试进度回调是否被调用"""
        # Arrange
        # 模拟AI在计算时调用进度回调
        def ai_with_progress(*args, **kwargs):
            progress_callback = kwargs.get('progress_callback')
            if progress_callback:
                progress_callback("Depth 1...")
                progress_callback("Depth 2...")
            return ((1,1), (2,2))

        mock_find_best_move.side_effect = ai_with_progress
        progress_callback = MagicMock()

        # Act
        self.ai_engine.start_calculation(GameState(), {}, MagicMock(), progress_callback)
        self.worker_done_event.wait(timeout=1)

        # Assert
        self.assertGreater(progress_callback.call_count, 0)
        progress_callback.assert_any_call("Depth 1...")
        progress_callback.assert_any_call("Depth 2...")

    @patch('ai_engine.find_best_move_iterative_deepening')
    def test_state_is_deep_copied(self, mock_find_best_move):
        """测试游戏状态是否被深拷贝"""
        print("测试游戏状态是否被深拷贝...")

        # Arrange
        game_state = GameState()
        
        # Act
        self.ai_engine.start_calculation(game_state, {}, MagicMock(), MagicMock())
        
        # 在主线程中，立即修改原始的game_state
        game_state.board[0][0] = 99 # 用一个不存在的棋子ID来标记修改
        
        self.worker_done_event.wait(timeout=1)

        # Assert
        # 获取传递给模拟函数的第一个参数（即game_state的副本）
        call_args, _ = mock_find_best_move.call_args
        state_in_thread = call_args[0]
        
        self.assertIsInstance(state_in_thread, GameState)
        # 关键断言：断言线程中的棋盘状态，没有我们后来做的修改
        self.assertNotEqual(state_in_thread.board[0][0], 99)

        print("✓ 深拷贝游戏状态测试通过")

if __name__ == "__main__":
    unittest.main()