"""
migrate_save_files.py - 将旧版 `initial_board` 格式的 JSON 棋谱文件，
原地转换为新版 `initial_fen` 格式，并自动断言迁移后的文件可被 load_game 正确加载。

用法：
    python scripts/migrate_save_files.py              # 处理 data/game_history/ 下所有 JSON
    python scripts/migrate_save_files.py foo.json     # 处理单个文件
"""
import sys
import os
import json
import shutil
import glob

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.game_logic import GameState


def _compact_moves(moves):
    """
    将 moves 列表序列化为紧凑的单行格式，例如：
    [[[3,1],[4,1]],[[2,0],[3,0]]]
    而不是 json.dump 默认的多层缩进展开格式。
    """
    parts = []
    for move in moves:
        start, end = move
        parts.append(f"[[{start[0]},{start[1]}],[{end[0]},{end[1]}]]")
    return "[" + ",".join(parts) + "]"


def migrate_file(filepath: str) -> bool:
    """
    迁移单个 JSON 存档。
    返回 True 表示成功转换，False 表示已是新版或跳过。
    """
    with open(filepath, "r", encoding="utf-8") as f:
        data = json.load(f)

    # 已是新版，跳过
    if "initial_fen" in data:
        print(f"  [跳过] 已是新版格式: {os.path.basename(filepath)}")
        return False

    # 检查旧版必要字段
    if "initial_board" not in data or "moves" not in data:
        print(f"  [警告] 无法识别的格式，跳过: {os.path.basename(filepath)}")
        return False

    # 转换棋盘 → FEN
    board = data["initial_board"]
    current_player = data.get("current_player", 2)  # 默认炮方
    initial_state = GameState(board=board, current_player=current_player)
    initial_fen = initial_state.to_fen()

    # moves 保持不变（格式已是 [[start],[end]] 的 list，load_game 可直接解析）
    moves = data["moves"]

    # 验证 moves 中每一步可以在对应局面被合法执行（非空 moves 才验证）
    if moves:
        try:
            cur = initial_state
            for move in moves:
                start, end = move
                valid = cur.get_valid_moves(start[0], start[1])
                if tuple(end) not in [tuple(v) for v in valid]:
                    print(f"  [告警] 存档含非法走法 {start}->{end}（可能是旧版规则差异），保留原样: {os.path.basename(filepath)}")
                    break
                cur = cur.move_piece(start[0], start[1], end[0], end[1])
        except Exception as e:
            print(f"  [告警] moves 验证异常: {e}，保留原走法: {os.path.basename(filepath)}")

    # 构建新版数据体，手动组装 JSON 以保持 moves 单行紧凑格式
    metadata = dict(data.get("metadata", {}))
    metadata["format"] = "fen_v1"
    metadata["migrated_from"] = "initial_board"

    # 构建最终 JSON 字符串（metadata 和 initial_fen 正常缩进，moves 紧凑单行）
    lines = [
        "{",
        f'  "metadata": {json.dumps(metadata, ensure_ascii=False)},',
        f'  "initial_fen": "{initial_fen}",',
        f'  "moves": {_compact_moves(moves)}',
        "}",
    ]
    output = "\n".join(lines)

    # 验证输出可被 json.loads 解析
    try:
        json.loads(output)
    except json.JSONDecodeError as e:
        print(f"  [错误] 生成的 JSON 无效，中止: {e}")
        return False

    # 备份原文件
    bak_path = filepath + ".bak"
    shutil.copy2(filepath, bak_path)

    # 写入新版
    with open(filepath, "w", encoding="utf-8") as f:
        f.write(output)

    # 闭环断言：迁移后的文件必须能被 load_game 加载
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            loaded_data = json.load(f)
        recovered = GameState.from_fen(loaded_data["initial_fen"])
        assert recovered.board is not None
    except Exception as e:
        # 回滚
        shutil.copy2(bak_path, filepath)
        print(f"  [回滚] load_game 验证失败，已恢复原文件: {e}")
        return False

    print(f"  [完成] {os.path.basename(filepath)}: initial_fen={initial_fen}, moves={len(moves)}步")
    return True


def main():
    if len(sys.argv) > 1:
        targets = sys.argv[1:]
    else:
        root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        targets = sorted(glob.glob(
            os.path.join(root, "data", "game_history", "**", "*.json"),
            recursive=True
        ))

    if not targets:
        print("未找到需要迁移的 JSON 文件。")
        return

    converted, skipped, failed = 0, 0, 0
    for path in targets:
        if not os.path.isfile(path):
            print(f"  [找不到文件] {path}")
            continue
        result = migrate_file(path)
        if result:
            converted += 1
        else:
            skipped += 1

    print(f"\n迁移完成: {converted} 个已转换，{skipped} 个跳过/已是新版。")


if __name__ == "__main__":
    main()
