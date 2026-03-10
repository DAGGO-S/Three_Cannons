import datetime
import json
from tkinter import filedialog
from typing import Optional, Tuple, List, Dict, Any

from src.model.game_model import GameModel
from core.game_logic import GameState, EMPTY

# --- 内部辅助函数 ---
def _find_move_between_states(prev_state: GameState, next_state: GameState) -> Optional[Tuple[Tuple[int, int], Tuple[int, int]]]:
    """
    通过比较两个连续的棋盘状态，找出其中的一步走法（已修正吃子逻辑）。

    需求:
    1. 遍历 5x5 棋盘，找到一个在 `prev_state.board` 中有棋子，但在 `next_state.board` 中为空格的位置。这就是 `start_pos`。
    2. 再次遍历棋盘，找到一个在 `prev_state.board` 中为空格或与 `start_pos` 相同，但在 `next_state.board` 中有棋子的位置。这就是 `end_pos`。
    3. 如果找到了 `start_pos` 和 `end_pos`，返回 `(start_pos, end_pos)`。
    4. 如果找不到，返回 `None`。
    """
    start_pos = None
    end_pos = None
    moved_piece_type = None

    # 1. 找到哪个棋子离开了原来的位置
    for r in range(5):
        for c in range(5):
            if prev_state.board[r][c] != EMPTY and next_state.board[r][c] == EMPTY:
                start_pos = (r, c)
                moved_piece_type = prev_state.board[r][c]
                break
        if start_pos:
            break
    
    # 如果找不到任何棋子离开，说明状态没变或有问题
    if start_pos is None:
        return None

    # 2. 找到那个离开的棋子现在在哪里
    for r in range(5):
        for c in range(5):
            # 结束位置的特征是：该位置的棋子变成了我们找到的 moved_piece_type，
            # 并且在之前它不是这个棋子（可能是空格，也可能是被吃的棋子）
            if next_state.board[r][c] == moved_piece_type and prev_state.board[r][c] != moved_piece_type:
                end_pos = (r, c)
                break
        if end_pos:
            break
    
    if start_pos and end_pos:
        return (start_pos, end_pos)
    
    return None

# --- 公开接口函数 ---
def save_game(model: GameModel) -> str:
    """
    将当前游戏（来自GameModel）保存为JSON格式的棋谱文件。

    参数:
    - model (GameModel): 包含完整游戏历史的数据模型。

    返回:
    - str: 一条表示操作结果的消息（成功或失败），用于在UI上显示。

    需求:
    1. 检查 `model.move_history` 是否为空或只有一个状态（开局），如果是，则返回 "没有走法，无法保存棋谱。"
    2. 提取初始状态: `initial_state = model.move_history[0]`。
    3. 创建一个空的 `moves` 列表。
    4. 循环遍历 `model.move_history` 从索引 1 到结尾：
       - `prev_state = model.move_history[i-1]`
       - `next_state = model.move_history[i]`
       - 调用 `_find_move_between_states(prev_state, next_state)` 找到 `move`。
       - 如果 `move` 有效，将其添加到 `moves` 列表。
    5. 构建要保存的字典 `game_data`，其结构必须如下：
       {
         "metadata": {
           "save_time": "YYYY-MM-DD HH:MM:SS",
           "format": "fen_v1"
         },
         "initial_fen": initial_state.to_fen(),
         "moves": moves
       }
    6. 调用 `filedialog.asksaveasfilename` 弹出"另存为"对话框，获取用户选择的文件路径 `filepath`。
       - 预设文件类型为 `(("JSON files", "*.json"), ("All files", "*.*"))`。
       - 默认扩展名为 `.json`。
    7. 如果用户取消对话框 (`filepath` 为空)，则返回 "保存操作已取消。"
    8. 使用 `try...except` 块来写入文件：
       - `with open(filepath, 'w', encoding='utf-8') as f:`
       - `json.dump(game_data, f, indent=2)`
       - 成功后返回 f"棋谱已成功保存到: {filepath}"
    9. 在 `except` 块中捕获 `IOError` 或其他异常，并返回 f"保存文件失败: {error}"。
    """
    # 检查是否有走法可以保存
    if len(model.move_history) <= 1:
        return "没有走法，无法保存棋谱。"
    
    # 提取初始状态
    initial_state = model.move_history[0]
    
    # 创建moves列表
    moves = []
    
    # 遍历历史记录找出所有移动
    for i in range(1, len(model.move_history)):
        prev_state = model.move_history[i-1]
        next_state = model.move_history[i]
        move = _find_move_between_states(prev_state, next_state)
        if move:
            moves.append(move)
    
    # 构建要保存的数据，符合指定的 FEN 简化格式
    game_data = {
        "metadata": {
            "save_time": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "format": "fen_v1"
        },
        "initial_fen": initial_state.to_fen(),
        "moves": moves
    }
    
    # 弹出保存对话框
    filepath = filedialog.asksaveasfilename(
        defaultextension=".json",
        filetypes=(("JSON files", "*.json"), ("All files", "*.*"))
    )
    
    # 如果用户取消对话框
    if not filepath:
        return "保存操作已取消。"
    
    # 尝试写入文件
    try:
        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(game_data, f, indent=2, ensure_ascii=False)
        return f"棋谱已成功保存到: {filepath}"
    except Exception as e:
        return f"保存文件失败: {str(e)}"

def load_game() -> Optional[Tuple[GameState, List[Tuple[Tuple[int, int], Tuple[int, int]]]]]:
    """
    弹出一个"打开文件"对话框，加载JSON棋谱文件，并将其解析为初始状态和走法列表。

    返回:
    - Optional[Tuple[GameState, List[...]]]: 如果加载和解析成功，返回一个元组 `(initial_state, moves)`。如果用户取消或发生错误，返回 `None`。

    需求:
    1. 调用 `filedialog.askopenfilename` 弹出"打开文件"对话框，获取 `filepath`。
    2. 如果用户取消 (`filepath` 为空)，则返回 `None`。
    3. 使用 `try...except` 块来读取和解析文件：
       a. `with open(filepath, 'r', encoding='utf-8') as f:`
       b. `data = json.load(f)`
    4. 验证 `data` 字典是否包含必须的键: `'initial_fen'`, `'moves'`。
       - 如果有任何一个键缺失，则考虑是否兼容旧版或直接抛出 `ValueError("棋谱文件格式不正确")`。
    5. 从 `data` 中提取 `initial_fen`, `moves`。
    6. 使用 `GameState.from_fen(initial_fen)` 创建初始状态。
    7. 返回元组 `(initial_state, moves)`。
    8. 在 `except` 块中捕获 `FileNotFoundError`, `json.JSONDecodeError`, `ValueError` 等异常。在发生任何错误时，都应（可选地打印错误日志后）返回 `None`。
    """
    # 弹出打开文件对话框
    filepath = filedialog.askopenfilename(
        filetypes=(("JSON files", "*.json"), ("All files", "*.*"))
    )
    
    # 如果用户取消对话框
    if not filepath:
        return None
    
    try:
        # 读取并解析JSON文件
        with open(filepath, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        # 验证必需的键并兼容旧版
        if 'initial_fen' in data:
            if 'moves' not in data:
                raise ValueError("棋谱文件格式不正确")
            initial_state = GameState.from_fen(data['initial_fen'])
            moves = data['moves']
        else:
            required_keys = ['initial_board', 'current_player', 'moves']
            for key in required_keys:
                if key not in data:
                    raise ValueError("棋谱文件格式不正确")
            initial_board = data['initial_board']
            current_player = data['current_player']
            moves = data['moves']
            initial_state = GameState(board=initial_board, current_player=current_player)
        
        # 返回元组
        return (initial_state, moves)
        
    except (FileNotFoundError, json.JSONDecodeError, ValueError, KeyError) as e:
        # 发生错误时返回None
        return None

def export_as_jsonl(history: List[GameState], winner: int, filepath: str) -> None:
    """
    将一局棋局未托/中间/终局的全量局面写入 JSONL 文件。

    字段规范：
      - fen        : 标准 FEN 字符串，表示该局面
      - eval       : 静态评估分，炮方视角正方向
      - game_outcome: 这一局的最终归属（回溯性标签）
                     1.0 = 炮方赢  |  0.0 = 兵方赢  |  0.5 = 和棋
                     与局面进行中否无关，全局内所有局面共享同一値。
    """
    from core.game_logic import CANNON, SOLDIER, DRAW
    from core.evaluation_logic import evaluate_board

    if winner == CANNON:
        outcome = 1.0
    elif winner == SOLDIER:
        outcome = 0.0
    else:
        outcome = 0.5

    lines = []
    for state in history:
        eval_result = evaluate_board(state)
        eval_score = float(eval_result[0] if isinstance(eval_result, tuple) else eval_result)

        lines.append(json.dumps({
            "fen": state.to_fen(),
            "eval": eval_score,
            "game_outcome": outcome
        }))

    with open(filepath, 'a', encoding='utf-8') as f:
        f.write('\n'.join(lines) + '\n')

def auto_save_game_end(model: GameModel) -> None:
    """被 GameModel 钩子调用，在检测到终局时自动落盘 JSONL 历史"""
    import os
    if model.game_state.winner == -1 or len(model.move_history) <= 1:
        return
    
    save_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), 'data', 'game_history', 'auto_save')
    os.makedirs(save_dir, exist_ok=True)
    filename = f"autosave_{datetime.datetime.now().strftime('%Y%m%d')}.jsonl"
    filepath = os.path.join(save_dir, filename)
    export_as_jsonl(model.move_history, model.game_state.winner, filepath)