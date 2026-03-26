"""
diagnose_dtm.py - 诊断高 DTM 局面

从 pkl 中定位指定 DTM 的局面，前向推演到 mate，检测重复，输出 JSONL。

用法:
  python scripts/tb_analysis/diagnose_dtm.py --cannons 3 --soldiers 8 --dtm 200
  python scripts/tb_analysis/diagnose_dtm.py --cannons 3 --soldiers 8 --dtm 50 --count 3
"""

import sys
import os
import json
import pickle
import argparse
import random
import itertools
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from core.game_logic import GameState, CANNON, SOLDIER, EMPTY

TB_SOLDIER_WIN = -1
TB_CANNON_WIN = 1


def load_tb(cannon_num, soldier_num, data_dir):
    search_dirs = [
        os.path.join(data_dir, 'cannon_win'),
        os.path.join(data_dir, 'soldier_win'),
        data_dir
    ]
    fname = f'tb_c{cannon_num}_s{soldier_num}.pkl'
    for d in search_dirs:
        path = os.path.join(d, fname)
        if os.path.exists(path):
            with open(path, 'rb') as f:
                return pickle.load(f)
    return None


def find_state_by_dtm(tb, cannon_num, soldier_num, target_dtm, max_attempts=2000000):
    """通过随机采样棋盘配置，定位指定 DTM 的局面。"""
    cells = list(range(25))

    for attempt in range(max_attempts):
        # 随机放置棋子
        positions = random.sample(cells, cannon_num + soldier_num)
        cannon_pos = positions[:cannon_num]
        soldier_pos = positions[cannon_num:]

        board_1d = [EMPTY] * 25
        for p in cannon_pos:
            board_1d[p] = CANNON
        for p in soldier_pos:
            board_1d[p] = SOLDIER

        board_2d = [board_1d[i:i + 5] for i in range(0, 25, 5)]

        for turn in [CANNON, SOLDIER]:
            state = GameState(board_2d, turn)
            ch = state.get_canonical_hash()
            if ch in tb:
                val, dtm, cti = tb[ch]
                if dtm == target_dtm:
                    return state

        if attempt % 500000 == 0 and attempt > 0:
            print(f"    采样 {attempt} 次...")

    return None


def trace_optimal_game(start_state, tbs, max_moves=300):
    """通用前向推演：赢家追求最快 Kill，输家追求最慢 Death。"""
    trajectory = []
    seen = {}
    current = start_state
    
    # 确定谁是赢家
    ch_start = start_state.get_canonical_hash()
    c0 = sum(row.count(CANNON) for row in start_state.board)
    s0 = start_state.soldier_count
    tb0 = tbs.get((c0, s0))
    if not tb0 or ch_start not in tb0:
        print("起始局面不在库中")
        return [], 0
    winner_val, start_dtm, _ = tb0[ch_start]
    print(f"检测到 {'炮' if winner_val == 1 else '兵'} 胜局，开始最优路径追踪 (Start DTM={start_dtm})")

    for move_num in range(max_moves):
        print(f"Tracing move {move_num}...", end='\r')
        ch = current.get_canonical_hash()
        fen = current.to_fen()
        player = current.current_player
        c_num = sum(row.count(CANNON) for row in current.board)
        s_num = current.soldier_count

        # 状态评价
        def evaluate_node(s):
            if s.winner == CANNON: return 1, 0
            if s.winner == SOLDIER: return -1, 0
            
            s_ch = s.get_canonical_hash()
            # 使用最稳健的计数方式
            s_c_num = sum(row.count(CANNON) for row in s.board)
            s_s_num = s.soldier_count
            
            s_tb = tbs.get((int(s_c_num), int(s_s_num)))
            if s_tb and s_ch in s_tb:
                return s_tb[s_ch][0], s_tb[s_ch][1]
            return 0, 0

        val, dtm = evaluate_node(current)
        
        entry = {
            'move': move_num, 'fen': fen,
            'turn': 'c' if player == CANNON else 's',
            'val': val, 'dtm': dtm, 'soldiers': s_num,
        }

        if ch in seen:
            entry['status'] = 'repeated'
            entry['repeat_of'] = seen[ch]
            trajectory.append(entry)
            break
        seen[ch] = move_num

        # 收集走法评估
        all_moves = []
        print(f"\n      -- Step {move_num} evaluation for {player} --")
        for r in range(5):
            for c in range(5):
                if current.board[r][c] == player:
                    for end in current.get_valid_moves(r, c):
                        nxt = current.move_piece(r, c, end[0], end[1])
                        n_val, n_dtm = evaluate_node(nxt)
                        
                        cols, rows = "ABCDE", "12345"
                        ms = f"{cols[c]}{rows[r]}-{cols[end[1]]}{rows[end[0]]}"
                        all_moves.append((ms, nxt, n_val, n_dtm))
                        print(f"        {ms}: val={n_val}, dtm={n_dtm}")

        if not all_moves or dtm == 0:
            entry['status'] = 'checkmate/captured'
            trajectory.append(entry); break

        # 最优策略：
        is_winner_turn = (player == CANNON and winner_val == 1) or (player == SOLDIER and winner_val == -1)
        winning_moves = [m for m in all_moves if m[2] == winner_val]
        
        if winning_moves:
            if is_winner_turn:
                winning_moves.sort(key=lambda x: x[3]) # 赢家找最短
            else:
                winning_moves.sort(key=lambda x: -x[3]) # 输家找最长
            best = winning_moves[0]
        else:
            best = all_moves[0]
            entry['note'] = 'no_winning_move_found'

        entry['move_played'] = best[0]
        entry['next_val'] = best[2]
        entry['next_dtm'] = best[3]
        trajectory.append(entry)
        current = best[1]

    return trajectory, 0


def main():
    parser = argparse.ArgumentParser(description='诊断高 DTM 局面')
    parser.add_argument('--cannons', type=int, default=3)
    parser.add_argument('--soldiers', type=int, default=8)
    parser.add_argument('--dtm', type=int, default=200)
    parser.add_argument('--count', type=int, default=1)
    parser.add_argument('--fen', type=str, default=None, help='直接指定 FEN 局面进行诊断')

    args = parser.parse_args()

    root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    data_dir = os.path.join(root, 'data', 'tablebase')

    print(f"加载残局库...")
    tbs = {}
    for s in range(1, args.soldiers + 1):
        tb = load_tb(args.cannons, s, data_dir)
        if tb:
            print(f"    c{args.cannons}s{s}: {len(tb)} 条")
            tbs[(args.cannons, s)] = tb

    main_tb = tbs.get((args.cannons, args.soldiers))
    if not main_tb:
        print("主库未找到")
        return

    # DTM 分布统计
    from collections import Counter
    dtm_dist = Counter(dtm for val, dtm, cti in main_tb.values())
    print(f"\nDTM 分布 (>=100):")
    for d in sorted(d for d in dtm_dist if d >= 100):
        print(f"    DTM={d}: {dtm_dist[d]} 个")

    # 查找目标 DTM 的局面
    for i in range(args.count):
        print(f"\n{'='*50}")
        if args.fen:
            print(f"诊断提供的 FEN 局面...")
            state = GameState.from_fen(args.fen)
        else:
            print(f"采样第 {i+1} 个 DTM={args.dtm} 局面...")
            state = find_state_by_dtm(main_tb, args.cannons, args.soldiers, args.dtm)
        
        if not state:
            print("未找到，尝试更多采样或降低目标 DTM")
            continue

        print(f"    FEN: {state.to_fen()}")
        print(f"    行动方: {'炮' if state.current_player == CANNON else '兵'}")

        # 前向推演
        print(f"    开始前向推演...")
        trajectory, repeats = trace_optimal_game(state, tbs)

        print(f"    步数: {len(trajectory)}")
        print(f"    重复局面: {repeats} 次")

        # 输出 JSONL
        output_path = os.path.join(data_dir,
            f'dtm{args.dtm}_trace_{i}.jsonl')
        with open(output_path, 'w', encoding='utf-8') as f:
            for entry in trajectory:
                f.write(json.dumps(entry, ensure_ascii=False) + '\n')
        print(f"    已保存: {output_path}")

        # 打印关键帧
        print(f"\n    关键帧:")
        for entry in trajectory:
            m = entry['move']
            if m <= 10 or m % 20 == 0 or 'status' in entry or 'repeat_of' in entry or 'note' in entry:
                repeat_mark = f" [重复第{entry['repeat_of']}步]" if 'repeat_of' in entry else ""
                note = f" [{entry['note']}]" if 'note' in entry else ""
                status = f" **{entry.get('status', '')}**" if 'status' in entry else ""
                move_info = f" -> {entry.get('move_played', '')}" if 'move_played' in entry else ""
                print(f"      #{m:3d} {entry['turn']} DTM={entry['dtm']:3d} "
                      f"{entry['fen']}{move_info}{repeat_mark}{note}{status}")


if __name__ == '__main__':
    main()
