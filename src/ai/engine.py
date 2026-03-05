# ai_engine.py (Corrected Version)

import threading
import time
from typing import Callable, Optional, Dict, Any, Tuple
from copy import deepcopy
from core.game_logic import GameState, CANNON

# 导入重构后的AI模块
try:
    # 假设这是你的AI核心模块
    from core.ai import (
        find_best_move_iterative_deepening,
        clear_transposition_table,
        save_transposition_table,
        load_transposition_table
    )
except ImportError:
    # 占位符，以防核心模块不存在
    def find_best_move_iterative_deepening(*args, **kwargs):
        import time
        # 模拟耗时
        time.sleep(0.1)
        # 模拟检查停止事件
        if 'stop_event' in kwargs.get('settings', {}) and kwargs['settings']['stop_event'].is_set():
            return None
        return ((1, 1), (2, 2))

    def clear_transposition_table():
        pass
    def save_transposition_table(filepath): pass
    def load_transposition_table(filepath): pass

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

    def is_calculating(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    def start_calculation(
        self,
        game_state: GameState,
        config: Dict[str, Any],
        on_complete_callback: Callable[[Optional[Tuple]], None],
        progress_callback: Callable[[str], None]
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
            # >>> 修正：将测试钩子作为最后一个参数传入 <<<
            args=(state_copy, config, self._stop_event, on_complete_callback, progress_callback, self._test_hook_worker_done_event),
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
        test_hook_event: Optional[threading.Event] = None
    ) -> None:
        """
        此方法在后台线程中执行。它调用核心AI算法并处理回调。
        """
        
        try:
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

                # 任务2: 将进度信息传递给上层 Orchestrator
                if on_progress:
                    on_progress(depth, score, move, line, root_moves_stats)

            settings = {
                "depth": config.get("depth", 5),
                "time_limit": config.get("time_limit", 10.0),
                "stop_event": stop_event,
                "analysis_mode": config.get("analysis_mode", False),
            }
            if "memory_limit" in config:
                settings["memory_limit"] = config["memory_limit"]
            
            is_maximizing = (state.current_player == CANNON)
            
            # AI函数返回的是最终的、完整搜索后的最佳走法
            final_best_move = find_best_move_iterative_deepening(
                state,
                settings,
                is_maximizing,
                progress_callback=combined_progress_callback
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
            print(f"AI Worker Exception: {e}")
            import traceback
            traceback.print_exc()
            if not stop_event.is_set():
                on_complete(None, {})
                
        finally:
            if test_hook_event:
                test_hook_event.set()