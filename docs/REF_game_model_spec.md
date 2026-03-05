# 引入类型提示
from typing import Optional, List, Tuple
from core.game_logic import GameState # 假设 core/game_logic.pyx 中定义了 GameState 类

class GameModel:
    """
    管理所有游戏数据，包括当前状态、历史记录和UI相关状态。
    """
    # --- 公开属性 ---
    game_state: GameState         # 当前的游戏局面对象
    move_history: List[GameState] # 从开局到现在的每一步棋的 GameState 列表
    selected_piece: Optional[Tuple[int, int]] # 当前玩家选中的棋子坐标 (r, c)，若无则为 None
    is_replay_mode: bool          # 标记当前是否处于复盘模式
    replay_index: int             # 在复盘模式下，当前查看的是 move_history 中的第几步

    # --- 构造函数 ---
    def __init__(self):
        """
        初始化 GameModel。
        
        需求:
        1. 调用 self.reset() 方法来初始化所有属性。
        """
        self.reset()

    # --- 公开方法 ---
    def reset(self) -> None:
        """
        将游戏重置为初始状态。

        需求:
        1. 创建一个新的 `GameState()` 实例并赋值给 `self.game_state`。
        2. 将 `self.move_history` 初始化为一个只包含这个初始 `game_state` 的列表。
        3. 将 `self.selected_piece` 设置为 `None`。
        4. 将 `self.is_replay_mode` 设置为 `False`。
        5. 将 `self.replay_index` 设置为 `0`。
        """
        pass

    def make_move(self, start_pos: Tuple[int, int], end_pos: Tuple[int, int]) -> bool:
        """
        根据给定的起始和结束位置执行一步走法，并更新历史记录。

        参数:
        - start_pos (Tuple[int, int]): 棋子移动的起始坐标 (r, c)。
        - end_pos (Tuple[int, int]): 棋子移动的目标坐标 (r, c)。

        返回:
        - bool: 始终返回 `True`，表示操作完成。

        需求:
        1. 检查 `self.is_replay_mode` 是否为 `True`。
           - 如果是，说明玩家在复盘过程中走出了一步新棋，历史记录需要被“截断”。
           - 执行 `self.move_history = self.move_history[:self.replay_index + 1]`。
           - 之后，将 `self.is_replay_mode` 设置为 `False`，因为现在进入了正常游戏流程。
        2. 调用当前 `self.game_state` 的 `.move_piece(start_pos[0], start_pos[1], end_pos[0], end_pos[1])` 方法，获取一个新的 `GameState` 对象，记为 `new_state`。
        3. 将 `self.game_state` 更新为 `new_state`。
        4. 将 `new_state` 添加到 `self.move_history` 列表的末尾。
        5. 更新 `self.replay_index` 为 `len(self.move_history) - 1`。
        6. 将 `self.selected_piece` 设置为 `None`，因为走子已完成。
        7. 返回 `True`。
        """
        pass

    def load_state_from_history(self, index: int) -> bool:
        """
        从历史记录中加载一个指定的状态，用于复盘。

        参数:
        - index (int): `move_history` 列表中的索引。

        返回:
        - bool: 如果索引有效且加载成功，返回 `True`；否则返回 `False`。

        需求:
        1. 检查 `index` 是否在有效范围内 (`0 <= index < len(self.move_history)`)。
           - 如果无效，直接返回 `False`。
        2. 将 `self.is_replay_mode` 设置为 `True`。
        3. 更新 `self.replay_index` 为传入的 `index`。
        4. 从 `self.move_history[self.replay_index]` 中获取历史 `GameState` 对象，并赋值给 `self.game_state`。
        5. 将 `self.selected_piece` 设置为 `None`。
        6. 返回 `True`。
        """
        pass
    
    def load_from_gamedata(self, initial_state: GameState, moves: List[Tuple[Tuple[int, int], Tuple[int, int]]]) -> None:
        """
        根据棋谱数据（初始状态和走法列表）完全重构游戏模型。

        参数:
        - initial_state (GameState): 棋谱中的初始局面。
        - moves (List[...]): 从初始局面开始的完整走法列表。

        需求:
        1. 将 `self.game_state` 设置为 `initial_state`。
        2. 将 `self.move_history` 初始化为只包含 `initial_state` 的列表。
        3. 创建一个循环，遍历 `moves` 列表中的每一步 `move`。
           - 在循环中，基于当前的 `self.game_state` 执行 `move`，得到 `next_state`。
           - 将 `next_state` 赋值给 `self.game_state`。
           - 将 `next_state` 添加到 `self.move_history` 的末尾。
        4. 循环结束后，调用 `self.load_state_from_history(len(self.move_history) - 1)`，将状态设置为最终局面并进入复盘模式。
        """
        pass