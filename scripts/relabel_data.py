import os
import sys
import json
import time
import argparse
from datetime import datetime

# 保证能找到 core
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.game_logic import GameState
from core.search_manager import find_best_move_iterative_deepening, find_best_move_parallel, clear_transposition_table

from multiprocessing import Pool, cpu_count

def worker_init(use_nnue):
    from core.engine import set_evaluator_mode
    set_evaluator_mode(1 if use_nnue else 0)

def process_record(args):
    record, depth, use_nnue = args
    fen = record["fen"]
    state = GameState.from_fen(fen)
    is_maximizing = (state.current_player == 2)
    
    from core.search_manager import find_best_move_iterative_deepening
    _, score = find_best_move_iterative_deepening(
        state, 
        {"depth": depth, "time_limit": 60.0}, 
        is_maximizing, 
        return_score=True
    )
    
    record["eval"] = float(score)
    record["relabel_depth"] = depth
    record["relabel_time"] = datetime.now().isoformat()
    return record

def relabel_file(input_path, output_path, depth=10, processes=None, use_nnue=True):
    if not os.path.exists(input_path):
        print(f"Error: Input file {input_path} not found.")
        return

    if processes is None:
        processes = max(1, cpu_count() - 1)

    print(f"[*] Relabeling {input_path} -> {output_path} (Depth: {depth}, Processes: {processes})")
    
    records = []
    with open(input_path, 'r', encoding='utf-8') as f:
        for line in f:
            if line.strip():
                records.append(json.loads(line))
    
    total = len(records)
    print(f"[*] Total records to process: {total}")
    
    start_time = time.time()
    
    # 将任务分包给进程池
    pool_args = [(r, depth, use_nnue) for r in records if r.get("relabel_depth") != depth]
    skipped = total - len(pool_args)
    
    new_records = [r for r in records if r.get("relabel_depth") == depth]
    
    if pool_args:
        with Pool(processes=processes, initializer=worker_init, initargs=(use_nnue,)) as pool:
            for i, res in enumerate(pool.imap(process_record, pool_args, chunksize=50)):
                new_records.append(res)
                if (i + 1) % 100 == 0 or (i + 1) == len(pool_args):
                    elapsed = time.time() - start_time
                    avg = elapsed / (i + 1)
                    eta = avg * (len(pool_args) - (i + 1))
                    print(f"Progress: {i+1+skipped}/{total} | ETA: {eta/60:.1f}m | T-Avg: {avg:.4f}s", end='\r')

    print(f"\n[*] Relabeling complete. Total time: {time.time() - start_time:.1f}s (Processed: {len(pool_args)}, Skipped: {skipped})")
    
    with open(output_path, 'w', encoding='utf-8') as f:
        for record in new_records:
            f.write(json.dumps(record) + '\n')
    print(f"[*] Saved to {output_path}")

def main():
    parser = argparse.ArgumentParser(description='Relabel JSONL game data with fixed depth search (High Performance).')
    parser.add_argument('--input', type=str, required=True, help='Input JSONL file or directory')
    parser.add_argument('--output', type=str, help='Output JSONL file or directory')
    parser.add_argument('--depth', type=int, default=10, help='Search depth (default: 10)')
    parser.add_argument('--processes', type=int, default=None, help='Number of parallel processes (default: CPU-1)')
    parser.add_argument('--no-nnue', action='store_false', dest='nnue', help='Disable NNUE during search')
    parser.set_defaults(nnue=True)
    
    args = parser.parse_args()
    
    # 检测是文件还是文件夹
    if os.path.isdir(args.input):
        input_dir = args.input
        # 获取所有 .jsonl 文件
        files = [os.path.join(input_dir, f) for f in os.listdir(input_dir) if f.endswith('.jsonl')]
        print(f"[*] Found {len(files)} files in {input_dir}")
        
        for f_path in files:
            # 如果指定了输出目录
            if args.output and os.path.isdir(args.output):
                f_out = os.path.join(args.output, os.path.basename(f_path))
            else:
                # 默认原位更新（符合用户目前的工作流需求）
                f_out = f_path
            
            relabel_file(f_path, f_out, depth=args.depth, processes=args.processes, use_nnue=args.nnue)
    else:
        # 单文件模式
        out = args.output if args.output else args.input.replace('.jsonl', '_relabeled.jsonl')
        relabel_file(args.input, out, depth=args.depth, processes=args.processes, use_nnue=args.nnue)

if __name__ == "__main__":
    main()


