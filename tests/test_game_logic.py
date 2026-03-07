import sys
import os
import unittest
from unittest.mock import patch, MagicMock

# 添加项目根目录到Python路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.game_logic import GameState, CANNON, SOLDIER, EMPTY, BOARD_ROWS, BOARD_COLS

class TestGameState(unittest.TestCase):
    """测试GameState类的核心功能"""
    
    def test_default_initialization(self):
        """测试默认初始化"""
        print("测试默认初始化...")
        state = GameState()
        
        # 验证棋盘布局是否正确（board 存储为 tuple-of-tuples）
        expected_board = tuple(tuple(row) for row in [
            [1,1,1,1,1],
            [1,1,1,1,1],
            [1,1,1,1,1],
            [0,0,0,0,0],
            [0,2,2,2,0]
        ])
        self.assertEqual(state.board, expected_board)
        
        # 验证当前玩家是否为CANNON
        self.assertEqual(state.current_player, CANNON)
        
        # 验证士兵数量是否为15
        self.assertEqual(state.soldier_count, 15)
        
        print("✓ 默认初始化测试通过")
    
    def test_initialization_with_custom_board(self):
        """测试从棋盘初始化"""
        print("测试从棋盘初始化...")
        custom_board = [
            [0,0,0,0,0],
            [0,1,0,0,0],
            [0,0,0,0,0],
            [0,0,0,2,0],
            [0,0,0,0,0]
        ]
        state = GameState(board=custom_board)
        
        # 验证棋盘是否正确设置（board 存储为 tuple-of-tuples）
        self.assertEqual(state.board, tuple(tuple(row) for row in custom_board))
        
        # 验证士兵数量是否正确计算
        self.assertEqual(state.soldier_count, 1)
        
        print("✓ 从棋盘初始化测试通过")
    
    def test_soldier_moves(self):
        """测试兵的移动"""
        print("测试兵的移动...")
        # 创建一个5x5棋盘，只在中心位置放置一个兵
        custom_board = [
            [0,0,0,0,0],
            [0,0,0,0,0],
            [0,0,1,0,0],
            [0,0,0,0,0],
            [0,0,0,0,0]
        ]
        state = GameState(board=custom_board, current_player=SOLDIER)
        
        center_pos = (2, 2)
        moves = state.get_valid_moves(center_pos[0], center_pos[1])
        expected_moves = {(1, 2), (3, 2), (2, 1), (2, 3)}
        # 使用集合比较，忽略顺序
        self.assertEqual(set(moves), expected_moves)
        
        # 测试边上位置的兵（使用自定义棋盘确保有合法移动）
        edge_board = [
            [1,0,0,0,0],
            [0,0,0,0,0],
            [0,0,0,0,0],
            [0,0,0,0,0],
            [0,0,0,0,0]
        ]
        edge_state = GameState(board=edge_board, current_player=SOLDIER)
        edge_pos = (0, 0)
        moves = edge_state.get_valid_moves(edge_pos[0], edge_pos[1])
        # 边上位置的兵应有2个合法走法
        self.assertEqual(len(moves), 2)
        
        print("✓ 兵的移动测试通过")
    
    def test_cannon_moves(self):
        """测试炮的移动"""
        print("测试炮的移动...")
        state = GameState()
        
        # 测试炮的普通一格移动
        cannon_pos = (4, 1)
        moves = state.get_valid_moves(cannon_pos[0], cannon_pos[1])
        expected_moves = {(4, 0), (3, 1), (2, 1)}  # 实际可移动位置
        # 使用集合比较，确保走法位置正确
        self.assertEqual(set(moves), expected_moves)
        
        print("✓ 炮的移动测试通过")
    
    def test_cannon_capture(self):
        """测试炮的吃子"""
        print("测试炮的吃子...")
        # 创建一个炮、一个空格、一个兵在一条线上的布局
        custom_board = [
            [0,0,0,0,0],
            [0,0,0,0,0],
            [0,0,0,0,0],
            [2,0,1,0,0],  # 炮在(3,0)，空格在(3,1)，兵在(3,2)
            [0,0,0,0,0]
        ]
        state = GameState(board=custom_board, current_player=CANNON)
        
        # 验证吃子走法存在
        cannon_pos = (3, 0)
        moves = state.get_valid_moves(cannon_pos[0], cannon_pos[1])
        self.assertIn((3, 2), moves)  # 炮可以吃掉兵
        
        print("✓ 炮的吃子测试通过")
    
    def test_cannon_invalid_capture_no_gap(self):
        """测试炮的非法吃子（无间隔）"""
        print("测试炮的非法吃子（无间隔）...")
        # 创建炮和兵紧挨着的布局
        custom_board = [
            [0,0,0,0,0],
            [0,0,0,0,0],
            [0,0,0,0,0],
            [2,1,0,0,0],  # 炮在(3,0)，兵在(3,1)，紧挨着
            [0,0,0,0,0]
        ]
        state = GameState(board=custom_board, current_player=CANNON)
        
        # 验证吃子走法不存在
        cannon_pos = (3, 0)
        moves = state.get_valid_moves(cannon_pos[0], cannon_pos[1])
        self.assertNotIn((3, 1), moves)  # 炮不能直接吃掉紧邻的兵
        
        print("✓ 炮的非法吃子（无间隔）测试通过")
    
    def test_move_piece_immutability(self):
        """测试move_piece的不可变性"""
        print("测试move_piece的不可变性...")
        old_state = GameState()
        new_state = old_state.move_piece(4, 1, 3, 1)  # 移动一个炮
        
        # 验证返回的是一个新对象
        self.assertIsNot(old_state, new_state)
        
        # 验证棋盘也被复制了
        self.assertIsNot(old_state.board, new_state.board)
        
        print("✓ move_piece的不可变性测试通过")
    
    def test_state_transition(self):
        """测试状态转移"""
        print("测试状态转移...")
        old_state = GameState()
        new_state = old_state.move_piece(4, 1, 3, 1)  # 移动一个炮
        
        # 验证执行一步棋后，新状态的棋盘布局正确
        self.assertEqual(new_state.board[4][1], EMPTY)  # 原位置变为空
        self.assertEqual(new_state.board[3][1], CANNON)  # 新位置变为炮
        
        # 验证current_player已切换
        self.assertEqual(new_state.current_player, SOLDIER)
        
        print("✓ 状态转移测试通过")
    
    def test_capture_decreases_soldier_count(self):
        """测试执行一次吃子后，soldier_count减1"""
        print("测试执行一次吃子后，soldier_count减1...")
        # 创建一个可以吃子的局面
        custom_board = [
            [0,0,0,0,0],
            [0,0,0,0,0],
            [0,0,0,0,0],
            [2,0,1,0,0],  # 炮在(3,0)，空格在(3,1)，兵在(3,2)
            [0,0,0,0,0]
        ]
        old_state = GameState(board=custom_board, current_player=CANNON)
        new_state = old_state.move_piece(3, 0, 3, 2)  # 炮吃掉兵
        
        # 验证士兵数量减少1
        self.assertEqual(new_state.soldier_count, old_state.soldier_count - 1)
        
        print("✓ 吃子减少士兵数量测试通过")
    
    def test_cannon_win(self):
        """测试炮胜"""
        print("测试炮胜...")
        # 创建一个只有一个兵的局面
        custom_board = [
            [0,0,0,0,0],
            [0,0,0,0,0],
            [0,0,0,0,0],
            [0,0,0,0,0],
            [0,2,0,1,0]  # 只有一个兵在(4,3)，炮在(4,1)
        ]
        old_state = GameState(board=custom_board, current_player=CANNON)
        new_state = old_state.move_piece(4, 1, 4, 3)  # 炮吃掉最后一个兵
        
        # 验证新状态的winner属性为CANNON
        self.assertEqual(new_state.winner, CANNON)
        
        print("✓ 炮胜测试通过")
    
    def test_soldier_win(self):
        """测试兵胜"""
        print("测试兵胜...")
        # 创建一个所有炮都被困住的棋盘布局
        # 炮在(4,1), (4,2), (4,3)
        # 兵在(3,1), (3,2), (3,3) 和 (4,0), (4,4) 将其完全困住
        custom_board = [
            [0,0,0,0,0],
            [0,0,0,0,0],
            [0,0,0,0,0],
            [0,1,1,1,0],
            [1,2,2,2,1]
        ]
        # 兵方回合，此时炮方已无路可走，应该在前一回合炮方走完后就判定兵胜
        # 所以我们应该创建一个炮方回合但无路可走的局面
        state = GameState(board=custom_board, current_player=CANNON)
        
        # >>> 直接断言winner属性 <<<
        # GameState 的 _check_winner 应该在初始化时就被调用了
        # 注意：这需要你的 GameState.__init__ 在最后调用了 _check_winner()
        self.assertEqual(state.winner, SOLDIER)
        
        print("✓ 兵胜测试通过")
    
    def test_illegal_move_soldier_capture(self):
        """测试兵尝试“吃”炮（移动到炮的位置）时会发生什么"""
        print("测试非法移动：兵吃炮...")
        # 创建一个布局，例如兵在 (1,1)，炮在 (2,2)
        custom_board = [
            [0,0,0,0,0],
            [0,1,0,0,0],  # 兵在(1,1)
            [0,0,2,0,0],  # 炮在(2,2)
            [0,0,0,0,0],
            [0,0,0,0,0]
        ]
        state = GameState(board=custom_board, current_player=SOLDIER)
        
        # 直接调用 state.move_piece(1, 1, 2, 2)
        # 这是一个不符合规则的操作（兵不能吃子）
        # 现在move_piece方法会抛出ValueError异常来拒绝非法移动
        with self.assertRaises(ValueError):
            state.move_piece(1, 1, 2, 2)
        
        print("✓ 非法移动测试通过")
    
    def test_hasher_state_is_not_corrupted(self):
        """验证连续的、合法的走法不会破坏全局 hasher 的内部状态"""
        print("测试哈希表状态不被破坏...")
        # 获取全局 hasher 实例
        from core.zobrist_hashing import get_hasher
        hasher = get_hasher()
        
        # 创建一个初始状态
        state = GameState()
        
        # 在一个循环中，连续执行10次合法的 make_move 操作
        for i in range(10):
            # 获取当前玩家的棋子位置
            piece_positions = []
            for r in range(BOARD_ROWS):
                for c in range(BOARD_COLS):
                    if state.board[r][c] == state.current_player:
                        piece_positions.append((r, c))
            
            # 如果没有棋子可以移动，跳出循环
            if not piece_positions:
                break
                
            # 选择第一个棋子并获取其合法移动
            start_r, start_c = piece_positions[0]
            valid_moves = state.get_valid_moves(start_r, start_c)
            
            # 如果没有合法移动，尝试下一个棋子
            if not valid_moves:
                continue
                
            # 执行合法移动
            end_r, end_c = valid_moves[0]
            state = state.move_piece(start_r, start_c, end_r, end_c)
            
            # 验证哈希值计算仍然正常工作
            # 通过计算新状态的哈希值并确保它是一个整数
            new_hash = hasher.compute_hash([list(row) for row in state.board], state.current_player)
            self.assertIsInstance(new_hash, int, 
                                  f"哈希表在第{i}步后被破坏：计算出的哈希值不是整数: {new_hash} (类型: {type(new_hash)})")
        
        print("✓ 哈希表状态检查测试通过")

if __name__ == "__main__":
    unittest.main()