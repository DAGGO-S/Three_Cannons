import sys
import os
import argparse

# 桥接到项目核心目录
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.game_logic import GameState, CANNON, SOLDIER, EMPTY
from core.evaluation_logic import DEFAULT_SETTINGS

def analyze_fen_detailed(fen: str):
    """
    通过 Python 结构等效复刻 `c_evaluate_board` 的逻辑。
    用于绕过 Cython `Zero Allocation` 无法返回字典的限制，以便在 CLI 中打印拆解维度得分。
    """
    state = GameState.from_fen(fen)
    board = state.board
    
    position_score = 0
    proximity_score = 0
    soldiers_pos = []
    cannons_pos = []
    empty_pos = []
    
    pos_table = DEFAULT_SETTINGS["SOLDIER_POSITION_TABLE"]
    mat_scores = DEFAULT_SETTINGS["BASE_MATERIAL_SCORES"]
    net_map = DEFAULT_SETTINGS["WEIGHT_NET_MAP"]
    
    for r in range(5):
        for c in range(5):
            piece = board[r][c]
            if piece == SOLDIER:
                soldiers_pos.append((r, c))
                position_score += pos_table[r][c]
                
                # 贴炮惩罚计算
                for dr, dc in [(0,1), (0,-1), (1,0), (-1,0)]:
                    nr, nc = r + dr, c + dc
                    if 0 <= nr < 5 and 0 <= nc < 5 and board[nr][nc] == CANNON:
                        proximity_score -= 30
            elif piece == CANNON:
                cannons_pos.append((r, c))
            else:
                empty_pos.append((r, c))
                
    # 炮方禁区掩码映射 (同等效逻辑)
    forbidden = set()
    for r, c in cannons_pos:
        for dr, dc in [(0,1), (0,-1), (1,0), (-1,0)]:
            nr, nc = r + dr, c + dc
            if 0 <= nr < 5 and 0 <= nc < 5 and board[nr][nc] == EMPTY:
                nnr, nnc = r + 2*dr, c + 2*dc
                if 0 <= nnr < 5 and 0 <= nnc < 5 and board[nnr][nnc] != CANNON:
                    forbidden.add((nnr, nnc))
                    
    # 连通域控制度扩展 (BFS)
    safe_soldiers = [pos for pos in soldiers_pos if pos not in forbidden]
    visited = set(safe_soldiers)
    queue = list(safe_soldiers)
    
    while queue:
        curr_r, curr_c = queue.pop(0)
        for dr, dc in [(0,1), (0,-1), (1,0), (-1,0)]:
            nr, nc = curr_r + dr, curr_c + dc
            if 0 <= nr < 5 and 0 <= nc < 5:
                pos = (nr, nc)
                if pos not in visited and pos not in forbidden and board[nr][nc] == EMPTY:
                    visited.add(pos)
                    queue.append(pos)
                    
    net_control_count = 22 - len(visited)
    net_control_score = 200
    if 0 <= net_control_count <= 5:
        net_control_score = net_map.get(net_control_count, 200)
    
    # 材质分加总
    material_score = 0
    sc = len(soldiers_pos)
    if sc == 0:
        overall = 10000
    else:
        if 1 <= sc <= 15:
            material_score = mat_scores[sc - 1]
        overall = net_control_score + position_score + proximity_score + material_score
        
    return {
        "FEN 标定串": fen,
        "Total 评估总分": overall,
        "Material (兵力生存)": material_score,
        "Position (阵型压制)": position_score,
        "Proximity (贴身禁区)": proximity_score,
        "Control Score (宏域控制)": net_control_score,
        "-> 控制网格数 (物理)": net_control_count
    }

def print_comparison(fens):
    print("\n[AI 静态权重探测器] 载入解析...")
    results = [analyze_fen_detailed(f) for f in fens]

    if not results: return
    keys = list(results[0].keys())
    
    print("=" * 90)
    print(f"{'探测项':<25} | " + " | ".join(f"局面 {i+1:<25}" for i in range(len(fens))))
    print("-" * 90)
    
    for key in keys:
        row = f"{key:<25} | "
        row += " | ".join(f"{str(res[key]):<27}" for res in results)
        print(row)
    print("=" * 90)

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description='对比剖析多个组合 FEN 的内在评分权重')
    parser.add_argument('fens', nargs='*', help='需要对照查阅的 FEN 字符串数组', 
                        default=[
                            "sssss/sssss/sssss/5/1ccc1 c",
                            "sssss/sssss/sssss/5/c1c1c s"
                        ])
    args = parser.parse_args()
    print_comparison(args.fens)
