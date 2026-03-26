import pickle
import os
import sys
from core.game_logic import GameState, CANNON, SOLDIER

class EndgameTablebaseSolver:
    def __init__(self, data_dir="data/tablebase"):
        self.data_dir = data_dir
        self.cache = {}

    def preload(self, c_num, s_num):
        """显式预加载指定的库到内存"""
        self.get_tb(c_num, s_num)

    def get_tb(self, c_num, s_num):
        key = (c_num, s_num)
        if key in self.cache:
            return self.cache[key]
        
        filename = f"tb_c{c_num}_s{s_num}.pkl"
        
        # 按优先级搜索：soldier_win/ -> cannon_win/ -> 根目录
        search_dirs = [
            os.path.join(self.data_dir, 'soldier_win'),
            os.path.join(self.data_dir, 'cannon_win'),
            self.data_dir,
        ]
        
        merged = {}
        for d in search_dirs:
            path = os.path.join(d, filename)
            if os.path.exists(path):
                try:
                    with open(path, 'rb') as f:
                        data = pickle.load(f)
                    merged.update(data)
                except Exception as e:
                    print(f"Error loading TB {path}: {e}")
        
        if not merged:
            return None
        
        self.cache[key] = merged
        return merged

    def probe_tb(self, state):
        c_num = sum(row.count(CANNON) for row in state.board)
        tb = self.get_tb(c_num, state.soldier_count)
        if not tb:
            return (0, 0, 0.0)
        h = state.get_canonical_hash()
        return tb.get(h, (0, 0, 0.0))

    def get_recommendations(self, state):
        """获取当前局面的所有合法走法及其库评价"""
        val, dtm, cti = self.probe_tb(state)
        current_ai = state.current_player
        
        # 获取所有合法走法
        moves_data = []
        for r in range(5):
            for c in range(5):
                if state.board[r][c] == current_ai:
                    for end in state.get_valid_moves(r, c):
                        nxt = state.move_piece(r, c, end[0], end[1])
                        v, d, c_score = self.probe_tb(nxt)
                        
                        cols, rows = "ABCDE", "12345"
                        move_str = f"{cols[c]}{rows[r]}-{cols[end[1]]}{rows[end[0]]}"
                        
                        moves_data.append({
                            'move_coords': (r, c, end[0], end[1]),
                            'move_str': move_str,
                            'state': nxt,
                            'val': v,
                            'dtm': d,
                            'cti': c_score,
                            'sc': nxt.soldier_count
                        })
        
        if not moves_data:
            return None, "无路可退"

        # 根据玩家身份排序 (与 play_against_tb.py 一致)
        if current_ai == SOLDIER:
            # 核心原则：结果(val) > 步数(dtm) > 物质(sc) > 压迫感(cti)
            # 排序逻辑：必胜(-1) > 和棋(0) > 必败(1)
            # DTM逻辑：若必胜选最小(快杀)，若必败选最大(拖延)
            moves_data.sort(key=lambda x: (
                x['val'], 
                x['dtm'] if x['val'] == -1 else -x['dtm'],
                -x['sc'], 
                x['cti']
            ))
        else:
            # 核心原则：结果(val) > 步数(dtm) > 物质(sc) > 压迫感(cti)
            # 排序逻辑：必胜(1) > 和棋(0) > 必败(-1)
            # DTM逻辑：若必胜选最小(快杀)，若必败选最大(拖延)
            moves_data.sort(key=lambda x: (
                -x['val'], 
                x['dtm'] if x['val'] == 1 else -x['dtm'],
                x['sc'], 
                -x['cti']
            ))

        theory_status = "炮胜" if val == 1 else ("兵胜" if val == -1 else "和棋")
        summary = {
            'val': val,
            'dtm': dtm,
            'cti': cti,
            'status': theory_status,
            'moves': moves_data[:5] # 返回前 5 个建议
        }
        return summary
