# orchestrator.py

from core.game_logic import EMPTY, SOLDIER, CANNON
from src.view.dialogs import SettingsDialog
from src.io.game_io import save_game, load_game
from src.ai.engine import load_transposition_table, save_transposition_table

class GameOrchestrator:
    def __init__(self, model, view, ai_engine, config):
        self.model = model
        self.view = view
        self.ai = ai_engine
        self.config = config

        # 加载AI记忆
        load_transposition_table('ai_memory.pkl')
        
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
            on_open_settings=self.on_open_settings
        )
        self.update_view()

    def on_window_close(self):
        """处理窗口关闭事件"""
        save_transposition_table('ai_memory.pkl')
        self.view.destroy()

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
        # 确认开头的检查只有这一行
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

        if selected:  # 如果已经选中了一个棋子
            start_r, start_c = selected
            valid_moves = self.model.game_state.get_valid_moves(start_r, start_c)
            
            # 增加严格的走法验证：确保目标位置在合法走法列表内
            if (r, c) in valid_moves:
                self.model.make_move(selected, (r, c))
                move_successful = True
            else:
                # 提示用户走法不合法
                self.view.update_debug_text(f"不合法的走法: 从({start_r},{start_c})到({r},{c})", append=False)
            
            self.model.selected_piece = None  # 无论移动是否成功，都取消之前的选择

        elif piece == current_player:  # 如果没有选中棋子，且点击的是自己的棋子
            self.model.selected_piece = (r, c)

        # ----- 统一的后续处理 -----
        self.update_view()  # 每次点击都刷新UI

        if move_successful:
            if self.model.game_state.winner != -1:
                self.view.show_winner(self.model.game_state.winner)
            else:
                self.check_for_ai_turn()  # 只有在成功走棋后才检查AI回合

    def on_new_game(self):
        """处理“新游戏”按钮点击"""
        self.ai.stop_calculation()
        self.model.reset()
        self.update_view()
        self.check_for_ai_turn()

    def on_calculate_move(self):
        """处理"计算一步"按钮点击或由AI回合自动触发。"""
        
        # >>> 新增！处理从复盘模式发起的计算 <<<
        if self.model.is_replay_mode:
            # 截断历史，退出复盘模式，创建一个新的时间线
            self.model.move_history = self.model.move_history[:self.model.replay_index + 1]
            self.model._rebuild_position_counts()
            self.model.is_replay_mode = False
        
        # 如果AI已在计算，则 return
        if self.ai.is_calculating():
            return
            
        # 调用 self.ai.start_calculation()，并传入:
        # - game_state: self.model.game_state
        # - config: self.config.get_all()
        # - on_complete_callback: self._on_ai_move_completed (一个私有回调方法)
        # - progress_callback: self._ai_progress_callback
        # 准备配置
        config_data = self.config.get_all()
        config_data['analysis_mode'] = self.view.debug_enabled

        self.ai.start_calculation(
            game_state=self.model.game_state,
            config=config_data,
            on_complete_callback=self._on_ai_move_completed,
            progress_callback=self._ai_progress_callback
        )
        
        # 调用 self.update_view() 以更新按钮状态（例如，禁用"计算"按钮）
        self.update_view()

    def _ai_progress_callback(self, depth, score, move, line, root_moves_stats=None):
        """
        AI进度回调的适配器。
        """
        if depth < 1:
            return
        move_str = self._format_move_for_display(move)
        line_str = " -> ".join([self._format_move_for_display(m) for m in (line or [])])
        text_to_display = f"D:{depth} | S:{score:.1f} | M:{move_str} | Line: {line_str}\n"
        self.view.update_debug_text(text_to_display, append=True)
        
        # >>> 新增：调用 View 更新棋盘上的分数组 <<<
        if root_moves_stats:
            print(f"DEBUG: Receiving Analysis Stats: {len(root_moves_stats)} entries. Sample: {list(root_moves_stats.values())[:5] if root_moves_stats else 'Empty'}")
            self.view.update_analysis_overlay(root_moves_stats)

    def _format_move_for_display(self, move):
        """
        辅助函数，将内部坐标元组 ((r1,c1),(r2,c2)格式化为用户友好的棋盘坐标字符串，如 'C3-C4'。
        """
        if not move:
            return "N/A" # 处理空走法的情况
        
        try:
            # 定义坐标映射关系
            cols = "ABCDE"
            rows = "12345" # 如果希望行从1开始
            
            start_pos, end_pos = move
            start_r, start_c = start_pos
            end_r, end_c = end_pos
            
            # 拼接字符串
            start_str = f"{cols[start_c]}{rows[start_r]}"
            end_str = f"{cols[end_c]}{rows[end_r]}"
            
            return f"{start_str}-{end_str}"
        except (TypeError, IndexError):
            # 如果传入的 move 格式不正确，返回其原始字符串形式以供调试
            return str(move)

    def _on_ai_move_completed(self, move, stats=None):
        """AI计算完成后的回调函数"""
        # 显示统计信息
        if stats:
            depth = stats.get('depth', 0)
            time_taken = stats.get('time', 0.0)
            score = stats.get('score', 0.0)
            line = stats.get('line', [])
            line_str = " -> ".join([self._format_move_for_display(m) for m in line])
            # 只有在调试模式下才显示详细日志
            self.view.update_debug_text(f"\n>>> 搜索结束! 耗时: {time_taken:.2f}s, 深度: {depth}, 评分: {score:.2f}, PV: {line_str}\n", append=True, force=True)

        # 核心逻辑修改：如果启用了调试模式，延迟2秒再走棋，让用户能看清刚才的思考分数
        # 如果未启用调试，或者没有分数需要展示，则立即走棋
        delay_ms = 2000 if self.view.debug_enabled else 0
        
        def execute_move():
            move_successful = False
            if move:
                try:
                    self.model.make_move(move[0], move[1])
                    move_successful = True
                except ValueError:
                    # AI返回了非法走法，已拒绝
                    pass
            
            # 立即刷新一次棋盘，让用户看到AI的走法
            self.view.render(self.model)

            # 检查游戏是否已经结束
            if self.model.game_state.winner != -1:
                # 游戏结束后，进行最后一次完整的UI状态更新
                self.update_view()
                self.view.show_winner(self.model.game_state.winner)
                return

            # 确保下一次 is_calculating() 调用返回的是 False。
            def final_update_and_next_turn():
                self.update_view() # 再次调用完整的 update_view 来刷新所有UI元素，特别是按钮
                if move_successful:
                    self.check_for_ai_turn() # 如果是AI vs AI，触发下一步

            self.view.after(10, final_update_and_next_turn)

        # 使用 after 来实现非阻塞的延迟
        self.view.after(delay_ms, execute_move)

    def on_open_settings(self):
        """处理“游戏设置”菜单或按钮的点击事件。"""
        # 获取当前配置
        current_config = self.config.get_all()
        
        # 创建设置对话框
        dialog = SettingsDialog(self.view, current_config)
        
        # 如果用户点击确定，更新配置
        if dialog.result:
            # 更新配置对象
            self.config.update(dialog.result)
            
            # 立即检查一次，处理可能立即开始的AI回合
            self.check_for_ai_turn()

    def on_stop_calculation(self):
        """处理“停止计算”按钮点击。"""
        # 调用 self.ai.stop_calculation()
        self.ai.stop_calculation()
        
        # 调用 self.update_view() 更新按钮状态
        self.update_view()

    def check_for_ai_turn(self):
        """检查当前是否轮到AI行动，如果是，则自动触发AI计算。"""
        if self.model.game_state.winner != -1:
            # 游戏结束时，如果之前有获胜信息，可以不再重复显示
            # self.view.show_winner(self.model.game_state.winner)
            return
            
        if self.ai.is_calculating():
            return

        current_player_id = self.model.game_state.current_player
        # >>> 简化：直接获取包含所有键的最新配置 <<<
        config = self.config.get_all()
        is_ai_turn = False

        # >>> 关键：确保这里使用的键名 ("cannon_player", "soldier_player") 
        # >>> 与 SettingsDialog 返回的键名完全一致！
        if current_player_id == CANNON and config.get("cannon_player") == "AI":
            is_ai_turn = True
            
        elif current_player_id == SOLDIER and config.get("soldier_player") == "AI":
            is_ai_turn = True

        if is_ai_turn:
            # 使用 after 给予UI一个短暂的刷新机会
            self.view.after(100, self.on_calculate_move)

    def on_prev_move(self):
        """处理"上一步"按钮点击"""
        new_index = self.model.replay_index - 1
        if self.model.load_state_from_history(new_index):
            self.update_view()

    def on_next_move(self):
        """处理"下一步"按钮点击"""
        new_index = self.model.replay_index + 1
        if self.model.load_state_from_history(new_index):
            self.update_view()

    def on_first_move(self):
        """处理“首步”按钮点击"""
        self.model.load_state_from_history(0)
        self.update_view()

    def on_last_move(self):
        """处理“最后一步”按钮点击"""
        last_index = len(self.model.move_history) - 1
        self.model.load_state_from_history(last_index)
        self.update_view()

    def on_save_game(self):
        """处理“保存棋谱”按钮点击"""
        # 调用 game_io.save_game(self.model) 来保存游戏
        result = save_game(self.model)
        
        # 在调试信息区域显示保存结果
        self.view.update_debug_text(result, append=False)

    def on_load_game(self):
        """处理“加载棋谱”按钮点击"""
        # 调用 game_io.load_game() 来加载游戏
        result = load_game()
        
        # 如果加载成功，result 是一个元组 (initial_state, moves)
        if result:
            initial_state, moves = result
            
            # 调用 self.model.load_from_gamedata(initial_state, moves) 来加载游戏数据
            self.model.load_from_gamedata(initial_state, moves)
            
            # 调用 self.update_view() 刷新界面
            self.update_view()
            
            # 在调试信息区域显示加载成功信息
            self.view.update_debug_text("棋谱加载成功", append=False)
        else:
            # 加载失败，在调试信息区域显示错误信息
            self.view.update_debug_text("棋谱加载失败或已取消", append=False)