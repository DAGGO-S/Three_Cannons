"""
jsonl_to_json.py - 将诊断轨迹 (JSONL) 转换为 GUI 可加载的 JSON 棋谱

用法:
  python scripts/tb_analysis/jsonl_to_json.py data/game_history/dtm150_trace_0.jsonl
"""

import os
import sys
import json
import datetime

def parse_move_str(move_str):
    """'A2-B2' -> ((r, c), (r, c))"""
    if not move_str or '-' not in move_str:
        return None
    
    cols = "ABCDE"
    rows = "12345"
    
    try:
        start_raw, end_raw = move_str.split('-')
        start_c = cols.index(start_raw[0])
        start_r = rows.index(start_raw[1])
        end_c = cols.index(end_raw[0])
        end_r = rows.index(end_raw[1])
        return ((start_r, start_c), (end_r, end_c))
    except (ValueError, IndexError):
        return None

def convert(input_path):
    if not os.path.exists(input_path):
        print(f"Error: {input_path} 不存在")
        return

    moves = []
    initial_fen = None
    
    with open(input_path, 'r', encoding='utf-8') as f:
        for idx, line in enumerate(f):
            if not line.strip():
                continue
            entry = json.loads(line)
            
            # 记录初始 FEN
            if idx == 0:
                initial_fen = entry.get('fen')
            
            # 解析走法
            move_played = entry.get('move_played')
            if move_played:
                parsed = parse_move_str(move_played)
                if parsed:
                    moves.append(parsed)

    if not initial_fen:
        print("Error: 找不到初始局面")
        return

    output_data = {
        "metadata": {
            "save_time": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "format": "fen_v1",
            "source": input_path
        },
        "initial_fen": initial_fen,
        "moves": moves
    }

    output_path = input_path.replace('.jsonl', '.json')
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(output_data, f, indent=2, ensure_ascii=False)
    
    print(f"转换成功: {output_path}")
    print(f"    初始局面: {initial_fen}")
    print(f"    走法数量: {len(moves)}")

if __name__ == '__main__':
    if len(sys.argv) < 2:
        print("Usage: python jsonl_to_json.py <file.jsonl>")
    else:
        convert(sys.argv[1])
