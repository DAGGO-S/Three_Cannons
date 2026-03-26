# ai_engine.py (Corrected Version)

import threading
import time
from typing import Callable, Optional, Dict, Any, Tuple
from copy import deepcopy
from core.game_logic import GameState, CANNON, SOLDIER
from src.ai.tb_solver import EndgameTablebaseSolver

# 导入重构后的AI模块
try:
    # 假设这是你的AI核心模块
    from core.search_manager import (
        find_best_move_iterative_deepening,
        find_best_move_parallel,
        clear_transposition_table
    )
except ImportError:
    import traceback
    print("\n[CRITICAL ERROR] Failed to import core AI modules. Fallback to dummy engine.")
    traceback.print_exc()

    def find_best_move_iterative_deepening(*args, **kwargs):
        import time
        time.sleep(0.1)
        if 'stop_event' in kwargs.get('settings', {}) and kwargs['settings']['stop_event'].is_set():
            return None
        return ((1, 1), (2, 2))

    def clear_transposition_table():
        pass

# 核心模块未提供的功能，在此统一补全空函数，防止 orchestrator 等模块因导入失败而崩溃
if 'save_transposition_table' not in globals():
    def save_transposition_table(filepath): pass
if 'load_transposition_table' not in globals():
    def load_transposition_table(filepath): pass
if 'init_tablebases' not in globals():
    def init_tablebases(): pass

class AIEngine:
    """
    负责异步执行AI计算任务。
    """
    def __init__(self):
        self._thread: Optional[threading.Thread] = None
        self._stop_event: threading.Event = threading.Event()
        # 【新增】用于测试的钩子，让测试代码可以知道worker何时结束
        self._test_hook_worker_done_event: Optional[threading.Event] = None
        # 【新增】用于存储计算过程中找到的最佳走法
        self.current_best_move: Optional[Tuple] = None
        # 【共享残局库求解器】
        self.tb_solver: Optional[EndgameTablebaseSolver] = None
        
        # 预加载残局库，避免首回合卡顿
        try:
            init_tablebases()
        except:
            pass

    def is_calculating(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    def start_calculation(
        self,
        game_state: GameState,
        config: Dict[str, Any],
        on_complete_callback: Callable[[Optional[Tuple]], None],
        progress_callback: Callable[[str], None],
        game_history: Optional[list] = None
    ) -> None:
        # >>> 修正！使用 self.is_calculating() 进行判断，与实例属性保持一致 <<<
        if self.is_calculating():
            return

        self._stop_event.clear()
        # 【新增】重置当前最佳走法
        self.current_best_move = None
        state_copy = deepcopy(game_state)
        
        self._thread = threading.Thread(
            target=self._worker,
            # >>> 修正：增加 game_history 参数 <<<
            args=(state_copy, config, self._stop_event, on_complete_callback, progress_callback, self._test_hook_worker_done_event, game_history),
            daemon=True
        )
        self._thread.start()

    def stop_calculation(self) -> None:
        if self.is_calculating():
            self._stop_event.set()

    def _worker(
        self,
        state: GameState,
        config: Dict[str, Any],
        stop_event: threading.Event,
        on_complete: Callable,
        on_progress: Callable,
        test_hook_event: Optional[threading.Event] = None,
        game_history: Optional[list] = None
    ) -> None:
        """
        此方法在后台线程中执行。它调用核心AI算法并处理回调。
        """
        
        try:
            # --- 【优先查询残局库】 ---
            # 只有开启开关且士兵数 <= 10 时才查库
            if config.get("use_tablebase", True) and state.soldier_count <= 10 and self.tb_solver:
                try:
                    res = self.tb_solver.get_recommendations(state)
                    if res and res['val'] != 0:
                        # 找到残局库结论 (1: 炮胜, -1: 兵胜)
                        if res['moves']:
                            best_tb_move = res['moves'][0]
                            coords = best_tb_move['move_coords']
                            # 转换格式: (r1, c1, r2, c2) -> ((r1, c1), (r2, c2))
                            final_move = ((coords[0], coords[1]), (coords[2], coords[3]))
                            
                            # 计算分值：靠近 MATE 分值更高
                            theory_score = res['val'] * 10000
                            if res['val'] > 0: theory_score -= res['dtm']
                            else: theory_score += res['dtm']
                            
                            # 模拟进度回调，让 UI 显示统计信息
                            on_progress(0, theory_score, final_move, f"Mate in {res['dtm']} (Tablebase)", None)
                            
                            # 直接返回结果，跳过后续 AB 搜索
                            on_complete(final_move, {
                                'depth': 0, 
                                'score': theory_score, 
                                'time': 0, 
                                'line': f"Mate in {res['dtm']} (Tablebase)"
                            })
                            return
                except Exception as tb_err:
                    print(f"[AI ERROR] Tablebase Probe failed: {tb_err}")

            clear_transposition_table()
            
            import time # Defensively import time here
            
            # --- 准备合并的回调函数 ---
            # 【新增】用于存储即时的统计数据
            current_stats = {'depth': 0, 'score': 0.0, 'time': 0.0}
            start_time = time.time()
            
            def combined_progress_callback(depth, score, move, line, root_moves_stats=None):
                # 任务1: 捕获最佳走法到 AIEngine 实例
                self.current_best_move = move
                # 记录统计
                current_stats['depth'] = depth
                current_stats['score'] = score
                current_stats['time'] = time.time() - start_time
                current_stats['line'] = line
                current_stats['root_moves'] = root_moves_stats # 新增：捕获根节点走法数据
                print(f"[ENGINE DEBUG] Progress Callback: depth {depth}, score {score:.2f}")

                # 任务2: 将进度信息传递给上层 Orchestrator
                if on_progress:
                    on_progress(depth, score, move, line, root_moves_stats)

            settings = {
                "depth": config.get("depth", 5),
                "time_limit": config.get("time_limit", 10.0),
                "stop_event": stop_event,
                "analysis_mode": config.get("analysis_mode", False),
                "num_threads": config.get("threads", 1),
                "use_nnue": True
            }
            if "memory_limit" in config:
                settings["memory_limit"] = config["memory_limit"]
            
            is_maximizing = (state.current_player == CANNON)
            
            if settings["num_threads"] > 1:
                final_best_move = find_best_move_parallel(
                    state,
                    settings,
                    is_maximizing,
                    progress_callback=combined_progress_callback,
                    game_history=game_history
                )
            else:
                final_best_move = find_best_move_iterative_deepening(
                    state,
                    settings,
                    is_maximizing,
                    progress_callback=combined_progress_callback,
                    game_history=game_history
                )
            
            # 确保最终时间被更新
            current_stats['time'] = time.time() - start_time
            
            # --- 核心逻辑 ---
            if not stop_event.is_set():
                # 如果是正常完成，回调最终结果
                # >>> 修正：传递 stats <<<
                on_complete(final_best_move, current_stats)
            else:
                # 如果是被中断，回调我们实时捕获的中间最佳结果
                # >>> 修正：传递 stats <<<
                on_complete(self.current_best_move, current_stats)

        except Exception as e:
            # 记录详细错误堆栈到终端，帮助诊断 Import 循环或其他崩溃
            import traceback
            print(f"\n[AI ERROR] Worker Exception Traceback:")
            traceback.print_exc()
            if not stop_event.is_set():
                on_complete(None, {})
                
        finally:
            if test_hook_event:
                test_hook_event.set()