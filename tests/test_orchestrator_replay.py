# test_orchestrator_replay.py

import sys
import os
import unittest
from unittest.mock import MagicMock, call, patch

# 添加项目根目录到Python路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.controller.orchestrator import GameOrchestrator
from src.model.game_model import GameModel
from src.ai.engine import AIEngine
from core.game_logic import GameState

class TestOrchestratorReplay(unittest.TestCase):  # 可以是一个新类 
    
    def setUp(self): 
        self.mock_view = MagicMock() 
        self.mock_ai_engine = MagicMock() 
        self.mock_config = MagicMock() 
        self.game_model = GameModel() 
        self.orchestrator = GameOrchestrator(self.game_model, self.mock_view, self.mock_ai_engine, self.mock_config) 
        
        # 创建一些历史 
        self.game_model.make_move((4, 1), (3, 1)) # index 1 
        self.game_model.make_move((2, 0), (3, 0)) # index 2 
        self.game_model.make_move((4, 2), (3, 2)) # index 3 

    @patch.object(GameOrchestrator, 'update_view')
    def test_replay_navigation_updates_model_and_view(self, mock_update_view): 
        """测试：复盘导航按钮能否正确调用Model并更新View""" 
        print("测试复盘导航...") 

        # Act 1: 点击"首步" 
        self.orchestrator.on_first_move() 
        # Assert 1 
        self.assertEqual(self.game_model.replay_index, 0) 
        self.assertTrue(self.game_model.is_replay_mode) 
        
        # Act 2: 点击"下一步" 
        self.orchestrator.on_next_move() 
        # Assert 2 
        self.assertEqual(self.game_model.replay_index, 1) 

        # Act 3: 点击"最后一步" 
        self.orchestrator.on_last_move() 
        # Assert 3 
        self.assertEqual(self.game_model.replay_index, 3) 

        # Act 4: 点击"上一步" 
        self.orchestrator.on_prev_move() 
        # Assert 4 
        self.assertEqual(self.game_model.replay_index, 2) 
        
        # 验证每次操作后都调用了 update_view 
        self.assertEqual(mock_update_view.call_count, 4) 
        
        print("✓ 复盘导航测试通过。")

if __name__ == "__main__":
    unittest.main()