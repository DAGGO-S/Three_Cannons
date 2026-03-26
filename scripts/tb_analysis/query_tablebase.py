"""
query_tablebase.py - 残局库 FEN 查询工具

用法:
  python scripts/tb_analysis/query_tablebase.py "4s/5/s4/css2/c1cs1 c"
  python scripts/tb_analysis/query_tablebase.py "s4/c4/c3/5/5 c" --data-dir data/tablebase
"""

import sys
import os
import pickle
import argparse

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from core.game_logic import GameState, CANNON, SOLDIER
from scripts.tb_analysis.generate_tablebase import load_binary_as_dict

WDL_NAME = {1: '炮胜(win)', -1: '兵胜(lose)', 0: '和棋(draw)'}


def load_tb(cannon_num, soldier_num, data_dir):
    """加载残局库，优先 pkl，其次 binary。"""
    pkl = os.path.join(data_dir, f'tb_c{cannon_num}_s{soldier_num}.pkl')
    if os.path.exists(pkl):
        with open(pkl, 'rb') as f:
            return pickle.load(f)
    tb = os.path.join(data_dir, f'tb_c{cannon_num}_s{soldier_num}.tb')
    if os.path.exists(tb):
        return load_binary_as_dict(tb)
    return None


def query(fen, data_dir):
    """查询一个 FEN 局面在残局库中的评估。"""
    state = GameState.from_fen(fen)
    board = state.board

    c_num = sum(row.count(CANNON) for row in board)
    s_num = sum(row.count(SOLDIER) for row in board)

    print(f"FEN:  {fen}")
    print(f"子力: {c_num}炮 {s_num}兵")
    print(f"行动方: {'炮' if state.current_player == CANNON else '兵'}")
    print()

    tb = load_tb(c_num, s_num, data_dir)
    if tb is None:
        print(f"残局库 tb_c{c_num}_s{s_num} 不存在于 {data_dir}")
        return

    ch = state.get_canonical_hash()
    entry = tb.get(ch)

    if entry is None:
        print(f"canonical_hash={ch} 在库中未找到")
        return

    val, dtm, cti = entry
    print(f"查询结果:")
    print(f"  WDL:            {WDL_NAME.get(val, val)}")
    print(f"  DTM:            {dtm}")
    print(f"  CTI:            {cti}")
    print(f"  canonical_hash: {ch}")

    # 列出所有合法走法的库评估
    print(f"\n后续走法评估:")
    moves_info = []
    for r in range(5):
        for c in range(5):
            if board[r][c] == state.current_player:
                for end in state.get_valid_moves(r, c):
                    nxt = state.move_piece(r, c, end[0], end[1])
                    n_c = sum(row.count(CANNON) for row in nxt.board)
                    n_s = nxt.soldier_count
                    n_tb = load_tb(n_c, n_s, data_dir)
                    if n_tb:
                        n_ch = nxt.get_canonical_hash()
                        n_entry = n_tb.get(n_ch, (0, 0, 0.0))
                    else:
                        n_entry = None

                    cols = "ABCDE"
                    rows = "12345"
                    move_str = f"{cols[c]}{rows[r]}-{cols[end[1]]}{rows[end[0]]}"
                    moves_info.append((move_str, n_entry))

    for move_str, entry in moves_info:
        if entry:
            v, d, c_score = entry
            print(f"  {move_str}: {WDL_NAME.get(v, v)}, DTM={d}, CTI={c_score}")
        else:
            print(f"  {move_str}: 库外（子力组合无对应库）")


def main():
    parser = argparse.ArgumentParser(description='残局库 FEN 查询工具')
    parser.add_argument('fen', type=str, help='FEN 字符串，如 "s4/c4/c3/5/5 c"')
    parser.add_argument('--data-dir', type=str, default=None,
                        help='残局库目录（默认 data/tablebase）')
    args = parser.parse_args()

    if args.data_dir is None:
        root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        data_dir = os.path.join(root, 'data', 'tablebase')
    else:
        data_dir = args.data_dir

    query(args.fen, data_dir)


if __name__ == '__main__':
    main()
