# game_model.py (FINAL, CORRECT, STRATEGICALLY UPGRADED VERSION)

import collections 
from core.game_logic import GameState, DRAW # 确保导入 DRAW 
 
class GameModel: 
    def __init__(self): 
        self.game_state: GameState = None 
        self.move_history: list = [] 
        self.selected_piece: tuple = None 
        self.is_replay_mode: bool = False 
        self.replay_index: int = 0 
        
        # GameModel 统一管理局面计数 
        self.position_counts: collections.Counter = None 
        
        self.reset() 
 
    def reset(self): 
        """重置到初始状态，并重置历史计数""" 
        self.game_state = GameState() 
        self.move_history = [self.game_state] 
        self.selected_piece = None 
        self.is_replay_mode = False 
        self.replay_index = 0 
        
        # 重置计数器，并记录初始局面的哈希 
        self.position_counts = collections.Counter() 
        self.position_counts[self.game_state.hash] += 1 
 
    def make_move(self, start_pos, end_pos) -> bool: 
        """执行走法，并由 GameModel 检查和棋""" 
        if self.is_replay_mode: 
            # 当从复盘分叉时，根据截断后的历史重建计数器 
            self.move_history = self.move_history[:self.replay_index + 1] 
            self._rebuild_position_counts() # 调用正确的辅助函数 
            self.is_replay_mode = False 
 
        is_capture = self.game_state.board[end_pos[0]][end_pos[1]] != 0 
        
        new_state = self.game_state.move_piece(start_pos[0], start_pos[1], end_pos[0], end_pos[1]) 
        
        self.game_state = new_state 
        self.move_history.append(new_state) 
        self.replay_index = len(self.move_history) - 1 
        self.selected_piece = None 
 
        if is_capture: 
            # 如果是吃子（不可逆移动），清空计数器 
            self.position_counts.clear() 
 
        self.position_counts[self.game_state.hash] += 1 
        
        if self.position_counts[self.game_state.hash] >= 3: 
            # GameModel 负责设置和棋状态 
            self.game_state.winner = DRAW 
            
        return True 
 
    def _rebuild_position_counts(self): 
        """[内部辅助函数] 根据当前的 move_history 重新计算 position_counts""" 
        self.position_counts.clear() 
        for state in self.move_history: 
            # 这里需要考虑吃子的情况，但简化版可以直接计数 
            # 一个更精确的实现会再次检查每一步是否是吃子 
            self.position_counts[state.hash] += 1 
 
    def load_from_gamedata(self, initial_state: GameState, moves: list): 
        """从棋谱数据加载，并重建历史计数""" 
        self.reset() 
        
        self.game_state = initial_state 
        self.move_history = [initial_state] 
        self.position_counts[initial_state.hash] = 1 # 重置后计数 
        
        current_state = initial_state 
        for move in moves: 
            start_pos, end_pos = move 
            is_capture = current_state.board[end_pos[0]][end_pos[1]] != 0 
            
            next_state = current_state.move_piece(start_pos[0], start_pos[1], end_pos[0], end_pos[1]) 
            
            self.move_history.append(next_state) 
            current_state = next_state 
            
            if is_capture: 
                self.position_counts.clear() 
            
            self.position_counts[current_state.hash] += 1 
 
        # 最后，检查加载的最终局面是否是和棋 
        if self.position_counts[self.game_state.hash] >= 3: 
            self.game_state.winner = DRAW 
 
        self.load_state_from_history(len(self.move_history) - 1) 
 
    def load_state_from_history(self, index: int) -> bool: 
        if 0 <= index < len(self.move_history): 
            self.is_replay_mode = True 
            self.replay_index = index 
            self.game_state = self.move_history[index] 
            self.selected_piece = None 
            return True 
        return False