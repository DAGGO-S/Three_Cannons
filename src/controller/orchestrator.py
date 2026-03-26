# orchestrator.py

from core.game_logic import EMPTY, SOLDIER, CANNON
from src.view.dialogs import SettingsDialog
from src.io.game_io import save_game, load_game
from src.ai.engine import load_transposition_table, save_transposition_table
from src.ai.tb_solver import EndgameTablebaseSolver

class GameOrchestrator:
    def __init__(self, model, view, ai_engine, config):
        self.model = model
        self.view = view
        self.ai = ai_engine
        self.config = config

        # 加载AI记忆
        load_transposition_table('ai_memory.pkl')
        
        # 初始化残局库求解器
        self.tb_solver = EndgameTablebaseSolver()
        
        # 注入到 AI 引擎，使其可以在搜索前查库
        self.ai.tb_solver = self.tb_solver
        
        # 绑定窗口关闭事件以保存记忆
        self.view.protocol("WM_DELETE_WINDOW", self.on_window_close)

        # 将自己的方法连接到View的事件上
        self.view.bind_event_handlers(
            on_canvas_click=self.on_canvas_click,
            on_new_game=self.on_new_game,
            on_calculate_move=self.on_calculate_move,
            on_stop_calculation=self.on_stop_calculation,
            on_prev_move=self.on_prev_move,
            on_next_move=self.on_next_move,
            on_first_move=self.on_first_move,
            on_last_move=self.on_last_move,
            on_save_game=self.on_save_game,
            on_load_game=self.on_load_game,
            on_open_settings=self.on_open_settings,
            on_open_editor=self.open_editor
        )
        self.update_view()
        # [新增] 异步预加载第一回合可能需要的库
        self._async_preload_tb()

    def _async_preload_tb(self):
        """异步预加载当前局面对应的残局库，避免首回合 IO 卡顿"""
        import threading
        def load():
            state = self.model.game_state
            sc = state.soldier_count
            # 获取炮数
            c_num = 0
            for r in range(5):
                for c in range(5):
                    if state.board[r][c] == CANNON: c_num += 1
            
            # 只有当兵力进入残局库可能的搜索范围（如 <= 10）时预加载
            if sc <= 10:
                self.tb_solver.preload(c_num, sc)
        
        threading.Thread(target=load, daemon=True).start()

    def on_window_close(self):
        """处理窗口关闭事件"""
        save_transposition_table('ai_memory.pkl')
        self.view.destroy()

    def open_editor(self):
        """挂载前端的可视化 FEN 编辑器"""
        from src.view.editor_dialog import EditorDialog
        from core.game_logic import GameState
        
        def on_confirm(fen_str):
            try:
                state = GameState.from_fen(fen_str)
                self.model.reset()
                self.model.game_state = state
                self.model.move_history = [state]
                self.model.position_counts.clear()
                self.model.position_counts[state.hash] = 1
                
                # 终止任何可能运行的代码计算
                self.ai.stop_calculation() 
                self.update_view()
                self._async_preload_tb() # 确认局面时预读
                self.check_for_ai_turn()
            except Exception:
                pass # 报错已被 Dialog 前端承接展示

        def on_tb_solve(state):
            return self.tb_solver.get_recommendations(state)
                
        EditorDialog(self.view, self.model.game_state, on_confirm, on_tb_solve)

    def update_view(self):
        """通知View使用Model的最新数据进行刷新"""
        self.view.render(self.model)
        self.view.update_button_states(
            is_ai_calculating=self.ai.is_calculating(),
            is_replay_mode=self.model.is_replay_mode,
            model=self.model
        )


    def on_canvas_click(self, r, c):
        """处理棋盘点击事件"""
        if self.ai.is_calculating():
            return
            
        if self.model.game_state.winner != -1:
            return
            
        if self.config.is_ai_turn(self.model.game_state.current_player):
            return

        piece = self.model.game_state.board[r][c]
        selected = self.model.selected_piece
        current_player = self.model.game_state.current_player
        
        move_successful = False
        engine_mode = self.config.data.get("engine_mode", "AB")

        if selected:
            start_r, start_c = selected
            valid_moves = self.model.game_state.get_valid_moves(start_r, start_c)
            
            if (r, c) in valid_moves:
                # 统一规则：所有模式均受“三复平”自动判决约束
                self.model.make_move(selected, (r, c), ignore_repetition=False)
                move_successful = True
            else:
                self.view.update_debug_text(f"不合法的走法: 从({start_r},{start_c})到({r},{c})", append=False)
            
            self.model.selected_piece = None

        elif piece == current_player:
            self.model.selected_piece = (r, c)

        self.update_view()

        if move_successful:
            if self.model.game_state.winner != -1:
                self.view.show_winner(self.model.game_state.winner)
            else:
                self.check_for_ai_turn()

    def on_new_game(self):
        """处理“新游戏”按钮点击"""
        self.ai.stop_calculation()
        self.model.reset()
        self.update_view()
        self._async_preload_tb() # 新游戏启动时预读
        self.check_for_ai_turn()

    def on_calculate_move(self):
        """处理"计算一步"按钮点击或由AI回合自动触发。"""
        if self.ai.is_calculating():
            return

        current_state = self.model.game_state
        config = self.config.get_all()
        # >>> [统一搜索路径] 自动执行：残局库(If enabled) -> AB 搜索(NNUE) <<<
        if self.model.is_replay_mode:
            self.model.move_history = self.model.move_history[:self.model.replay_index + 1]
            self.model._rebuild_position_counts()
            self.model.is_replay_mode = False

        config_data = config
        config_data['analysis_mode'] = self.view.debug_enabled
        game_history = [state.hash for state in self.model.move_history]

        self.ai.start_calculation(
            game_state=self.model.game_state,
            config=config_data,
            on_complete_callback=self._on_ai_move_completed,
            progress_callback=self._ai_progress_callback,
            game_history=game_history
        )
        self.update_view()

    def _ai_progress_callback(self, depth, score, move, line, root_moves_stats=None):
        m_str = self._format_move_for_display(move)
        if isinstance(line, str):
            l_str = line
        else:
            l_str = " -> ".join([self._format_move_for_display(m) for m in (line or [])])
        self.view.update_debug_text(f"D:{depth} | S:{score:.1f} | M:{m_str} | Line: {l_str}\n", append=True)
        if root_moves_stats:
            self.view.update_analysis_overlay(root_moves_stats)

    def _format_move_for_display(self, move):
        if not move: return "N/A"
        try:
            cols, rows = "ABCDE", "12345"
            s, e = move
            return f"{cols[s[1]]}{rows[s[0]]}-{cols[e[1]]}{rows[e[0]]}"
        except: return str(move)

    def _on_ai_move_completed(self, move, stats=None):
        """AI计算完成后的回调函数"""
        if stats:
            d, t, s = stats.get('depth',0), stats.get('time',0.0), stats.get('score',0.0)
            raw_line = stats.get('line', [])
            if isinstance(raw_line, str):
                pv = raw_line
            else:
                pv = " -> ".join([self._format_move_for_display(m) for m in (raw_line or [])])
            self.view.update_debug_text(f"\n>>> 搜索完成! {t:.2f}s, D:{d}, S:{s:.2f}, PV:{pv}\n", append=True, force=True)

        delay = 2000 if self.view.debug_enabled else 0
        def execute_move():
            if move:
                # [关键] AB 模式必须 enforce_repetition (正常判定次数)
                self.model.make_move(move[0], move[1], ignore_repetition=False)
            
            self.view.render(self.model)
            if self.model.game_state.winner != -1:
                self.update_view()
                self.view.show_winner(self.model.game_state.winner)
                return

            def final_turn():
                self.update_view()
                if move: self.check_for_ai_turn()
            self.view.after(10, final_turn)
        self.view.after(delay, execute_move)

    def on_open_settings(self):
        current_config = self.config.get_all()
        dialog = SettingsDialog(self.view, current_config)
        if dialog.result:
            self.config.update(dialog.result)
            self.update_view()
            self.check_for_ai_turn()

    def on_stop_calculation(self):
        self.ai.stop_calculation()
        self.update_view()

    def check_for_ai_turn(self):
        if self.model.game_state.winner != -1 or self.ai.is_calculating(): return
        player = self.model.game_state.current_player
        config = self.config.get_all()
        is_ai = False
        if player == CANNON and config.get("cannon_player") == "AI": is_ai = True
        elif player == SOLDIER and config.get("soldier_player") == "AI": is_ai = True
        if is_ai: self.view.after(100, self.on_calculate_move)

    def on_prev_move(self):
        if self.model.load_state_from_history(self.model.replay_index - 1): self.update_view()
    def on_next_move(self):
        if self.model.load_state_from_history(self.model.replay_index + 1): self.update_view()
    def on_first_move(self):
        self.model.load_state_from_history(0)
        self.update_view()
    def on_last_move(self):
        self.model.load_state_from_history(len(self.model.move_history) - 1)
        self.update_view()

    def on_save_game(self):
        res = save_game(self.model)
        self.view.update_debug_text(res, append=False)
    def on_load_game(self):
        res = load_game()
        if res:
            self.model.load_from_gamedata(res[0], res[1])
            self.update_view()
            self._async_preload_tb() # 加载棋谱后预读
            self.view.update_debug_text("棋谱加载成功", append=False)
        else:
            self.view.update_debug_text("棋谱加载失败", append=False)
