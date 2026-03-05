# test_code/test_ai_integration.py

import sys
import os
import unittest
import threading

# 添加项目根目录到Python路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from ai_engine import AIEngine
from core.game_logic import GameState

class TestAiFullIntegration(unittest.TestCase):
    """
    一个简单的集成测试，用于验证从AIEngine到evaluate_board的参数传递链路。
    这个测试不使用任何mock。
    """

    def test_ai_run_at_depth_one_does_not_crash(self):
        """
        测试：当AI以深度1运行时（会立即调用evaluate_board），程序不会因类型错误而崩溃。
        """
        print("执行AI链路集成测试 (depth=1)...")
        
        # Arrange
        ai_engine = AIEngine()
        calculation_finished = threading.Event()
        error_in_thread = None
        
        # 准备一个能捕获异常的回调
        def on_complete_callback(best_move):
            nonlocal error_in_thread
            # 这是一个简化的检查，真实代码中错误处理在worker内部
            # 但如果worker完全崩溃，这个回调可能不会被调用
            calculation_finished.set()

        game_state = GameState()
        config = {
            "depth": 1,
            "time_limit": 5.0
        }

        # Act
        ai_engine.start_calculation(
            game_state,
            config,
            on_complete_callback,
            lambda *args: None # 空的进度回调
        )

        # Assert
        finished_in_time = calculation_finished.wait(timeout=5)
        self.assertTrue(finished_in_time, "AI calculation timed out or thread crashed without calling on_complete.")

        print("✓ AI链路集成测试通过")

if __name__ == "__main__":
    unittest.main()