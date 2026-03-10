import tkinter as tk
from tkinter import ttk, messagebox, scrolledtext, Menu
import threading

# 导入游戏常量
from core.game_logic import CANNON, SOLDIER, EMPTY, BOARD_ROWS, BOARD_COLS

# UI常量定义 - 采用旧版本更合适的尺寸
CELL_SIZE = 80  # 增大棋盘格子尺寸，使棋子更清晰
PIECE_RADIUS = 30  # 棋子半径
BOARD_COLOR = "#CDBA96"  # 棋盘颜色
HIGHLIGHT_COLOR = "#00FF00"  # 高亮颜色
COORD_MARGIN = 30
BOARD_WIDTH = BOARD_COLS * CELL_SIZE
BOARD_HEIGHT = BOARD_ROWS * CELL_SIZE
WINDOW_WIDTH = BOARD_WIDTH + 2 * COORD_MARGIN + 350  # 增加宽度以容纳信息面板
WINDOW_HEIGHT = max(BOARD_HEIGHT + 2 * COORD_MARGIN, 500)  # 增加高度

class GameGUI(tk.Tk):
    def __init__(self, model):
        super().__init__()
        self.model = model
        self.title("三炮十五兵")
        self.geometry(f"{WINDOW_WIDTH}x{WINDOW_HEIGHT}")
        self.resizable(False, False)
        
        # 初始化变量
        self.selected_piece = None
        self.valid_moves = []
        self.debug_enabled = False
        self._cached_board = None  # 初始化缓存棋盘
        self._board_items = {}  # 存储棋盘网格线的Canvas项目ID
        self._piece_items = {}  # 存储棋子的Canvas项目ID {(r,c): (oval_id, text_id)}
        self._highlight_items = set()  # 存储高亮标记的Canvas项目ID
        self._coord_items = []  # 存储坐标标签的ID
        
        # 创建界面
        self._create_widgets()
        self._initial_draw_board()
        
    def _create_widgets(self):
        # 创建菜单栏
        self._create_menu()
        
        # 创建主框架 - 采用旧版本的布局结构
        main_frame = tk.Frame(self)
        main_frame.pack(fill="both", expand=True)
        
        # 左侧控制按钮区域 - 采用旧版本的按钮布局
        left_frame = tk.Frame(main_frame, width=150)
        left_frame.pack(side="left", fill="y", padx=5)
        
        # 添加控制按钮 - 采用旧版本的按钮样式
        tk.Label(left_frame, text="游戏控制", font=("Arial", 12, "bold")).pack(pady=5)
        
        self.btn_reset = tk.Button(left_frame, text="新游戏", width=12, font=("Arial", 10))
        self.btn_reset.pack(pady=2)
        
        tk.Frame(left_frame, height=10).pack()  # 分隔符
        
        self.btn_calculate = tk.Button(left_frame, text="计算一步", width=12, font=("Arial", 10))
        self.btn_calculate.pack(pady=2)
        
        self.btn_stop = tk.Button(left_frame, text="停止计算", width=12, font=("Arial", 10), state=tk.DISABLED)
        self.btn_stop.pack(pady=2)
        
        tk.Frame(left_frame, height=10).pack()  # 分隔符
        
        # 添加复盘控制按钮
        self.first_move_btn = tk.Button(left_frame, text="首步", width=12, font=("Arial", 10))
        self.first_move_btn.pack(pady=2)
        
        self.prev_move_btn = tk.Button(left_frame, text="前一步", width=12, font=("Arial", 10))
        self.prev_move_btn.pack(pady=2)
        
        self.next_move_btn = tk.Button(left_frame, text="后一步", width=12, font=("Arial", 10))
        self.next_move_btn.pack(pady=2)
        
        self.last_move_btn = tk.Button(left_frame, text="最后一步", width=12, font=("Arial", 10))
        self.last_move_btn.pack(pady=2)
        
        tk.Frame(left_frame, height=10).pack()  # 分隔符
        
        # 添加保存和加载按钮
        self.save_game_btn = tk.Button(left_frame, text="保存棋谱", width=12, font=("Arial", 10))
        self.save_game_btn.pack(pady=2)
        
        self.load_game_btn = tk.Button(left_frame, text="加载棋谱", width=12, font=("Arial", 10))
        self.load_game_btn.pack(pady=2)
        
        tk.Frame(left_frame, height=10).pack()  # 分隔符
        
        # 调试开关
        self.debug_var = tk.BooleanVar()
        debug_check = tk.Checkbutton(
            left_frame, 
            text="启用调试", 
            variable=self.debug_var,
            font=("Arial", 10),
            command=self._toggle_debug
        )
        debug_check.pack(pady=10, anchor="w")
        
        # 中间棋盘区域
        canvas_width = BOARD_COLS * CELL_SIZE + COORD_MARGIN
        canvas_height = BOARD_ROWS * CELL_SIZE + COORD_MARGIN
        self.canvas = tk.Canvas(main_frame, width=canvas_width, height=canvas_height, bg=BOARD_COLOR)
        self.canvas.pack(side="left", fill="both", expand=True)
        
        # 右侧信息展示区 - 采用旧版本的信息展示布局
        right_frame = tk.Frame(main_frame, width=200)
        right_frame.pack(side="right", fill="y", padx=5)
        
        info_label = tk.Label(right_frame, text="游戏信息", font=("Arial", 12, "bold"))
        info_label.pack(pady=5)
        
        # 当前玩家信息
        self.current_player_label = tk.Label(right_frame, text="当前玩家: 炮", font=("Arial", 10))
        self.current_player_label.pack(pady=5, anchor="w")
        
        # 士兵数量信息
        self.soldier_count_label = tk.Label(right_frame, text="士兵数量: 15", font=("Arial", 10))
        self.soldier_count_label.pack(pady=5, anchor="w")
        
        # 调试信息文本框 - 采用旧版本的scrolledtext组件
        debug_label = tk.Label(right_frame, text="调试信息", font=("Arial", 12, "bold"))
        debug_label.pack(pady=5, anchor="w")
        
        self.debug_text = scrolledtext.ScrolledText(right_frame, wrap=tk.WORD, width=30, height=25, font=("Courier New", 10))
        self.debug_text.pack(fill="both", expand=True, padx=5, pady=5)
        self.debug_text.config(state='disabled')
        
    def _create_menu(self):
        """创建菜单栏"""
        menubar = Menu(self)
        self.config(menu=menubar)
        
        # 游戏菜单
        self.game_menu = Menu(menubar, tearoff=0)  # 保存为实例属性
        menubar.add_cascade(label="游戏", menu=self.game_menu)
        self.game_menu.add_command(label="新游戏")  # 先创建，不绑定command
        self.game_menu.add_separator()
        self.game_menu.add_command(label="设置")  # 先创建
        self.game_menu.add_command(label="操作说明") # 占位
        self.game_menu.add_command(label="残局编辑器 (FEN)") # 先创建
        self.game_menu.add_separator()
        self.game_menu.add_command(label="退出", command=self.quit)
        

        
    def _initial_draw_board(self):
        """初始绘制棋盘，只执行一次"""
        # 使用批量操作提高效率
        self.canvas.itemconfig(self.canvas.create_rectangle(
            COORD_MARGIN, COORD_MARGIN, 
            BOARD_COLS * CELL_SIZE + COORD_MARGIN, 
            BOARD_ROWS * CELL_SIZE + COORD_MARGIN, 
            outline="black", width=2
        ), tags="board_border")
        
        # 绘制棋盘格子
        for r in range(BOARD_ROWS):
            for c in range(BOARD_COLS):
                x0, y0, x1, y1 = c*CELL_SIZE+COORD_MARGIN, r*CELL_SIZE+COORD_MARGIN, (c+1)*CELL_SIZE+COORD_MARGIN, (r+1)*CELL_SIZE+COORD_MARGIN
                item_id = self.canvas.create_rectangle(x0, y0, x1, y1, outline="black", tags="board_cell")
                self._board_items[(r, c)] = item_id  # 修改存储方式以匹配旧版本
        
        # 绘制坐标
        self._draw_coordinates()
        
        # 初始化棋子位置字典
        for r in range(BOARD_ROWS):
            for c in range(BOARD_COLS):
                self._piece_items[(r, c)] = (None, None)
                
    def _draw_coordinates(self):
        """绘制坐标，使用批量操作"""
        col_labels, row_labels = "ABCDE", "12345"
        
        # 批量创建列标签
        for i in range(5):
            item_id = self.canvas.create_text(
                COORD_MARGIN+i*CELL_SIZE+CELL_SIZE/2, 
                COORD_MARGIN/2, 
                text=col_labels[i], 
                font=("Arial",12,"bold"),
                tags="col_label"
            )
            self._coord_items.append(item_id)
        
        # 批量创建行标签
        for i in range(5):
            item_id = self.canvas.create_text(
                COORD_MARGIN/2, 
                COORD_MARGIN+i*CELL_SIZE+CELL_SIZE/2, 
                text=row_labels[i], 
                font=("Arial",12,"bold"),
                tags="row_label"
            )
            self._coord_items.append(item_id)
                
    def bind_event_handlers(self, **handlers):
        """绑定事件处理器"""
        # 绑定画布点击事件
        if 'on_canvas_click' in handlers:
            self.canvas.bind("<Button-1>", lambda event: self._handle_canvas_click(event, handlers['on_canvas_click']))
        
        # 绑定按钮事件
        if 'on_new_game' in handlers:
            self.btn_reset.config(command=handlers['on_new_game'])
            
        if 'on_calculate_move' in handlers:
            self.btn_calculate.config(command=handlers['on_calculate_move'])
            
        if 'on_stop_calculation' in handlers:
            self.btn_stop.config(command=handlers['on_stop_calculation'])
            
        # 绑定保存和加载按钮事件
        if 'on_save_game' in handlers:
            self.save_game_btn.config(command=handlers['on_save_game'])
            
        if 'on_load_game' in handlers:
            self.load_game_btn.config(command=handlers['on_load_game'])
        
        # 绑定菜单命令
        if 'on_new_game' in handlers:
            # 使用 entryconfig 来配置已存在的菜单项
            self.game_menu.entryconfig("新游戏", command=handlers['on_new_game'])
        if 'on_open_settings' in handlers:
            self.game_menu.entryconfig("设置", command=handlers['on_open_settings'])
        if 'on_open_editor' in handlers:
            self.game_menu.entryconfig("残局编辑器 (FEN)", command=handlers['on_open_editor'])
        
        # 确保复盘按钮被正确绑定
        if 'on_first_move' in handlers:
            self.first_move_btn.config(command=handlers['on_first_move'])
        if 'on_prev_move' in handlers:
            self.prev_move_btn.config(command=handlers['on_prev_move'])
        if 'on_next_move' in handlers:
            self.next_move_btn.config(command=handlers['on_next_move'])
        if 'on_last_move' in handlers:
            self.last_move_btn.config(command=handlers['on_last_move'])
        
        # 存储处理器引用以备后用
        self._event_handlers = handlers
        
    def _handle_canvas_click(self, event, handler):
        """处理画布点击事件"""
        # pos 是 (row, col) 或 None
        pos = self.get_board_position(event.x, event.y)
        if pos:
            # 传递解包后的 row 和 col
            handler(pos[0], pos[1])
        
    def render(self, model):
        """根据模型状态重绘界面"""
        # 清除分析图层 (防止显示过期的分析结果)
        self.canvas.delete("analysis_overlay")

        # 更新棋子
        self._draw_pieces(model)
        
        # 更新高亮
        self._update_highlights(model)
        
        # 更新游戏信息
        self._update_game_info(model)
        
    def _draw_pieces(self, model):
        """优化后的棋盘绘制方法，只重绘变化的部分"""
        # 检查是否需要完全重绘
        if not hasattr(self, '_cached_board') or self._cached_board is None:
            # 首次绘制，完全重绘
            self._full_redraw_board(model)
        else:
            # 只重绘变化的部分
            self._partial_redraw_board(model)
        
        # 更新缓存
        self._cached_board = [row[:] for row in model.game_state.board]  # 浅拷贝

    def _full_redraw_board(self, model):
        """完全重绘棋盘"""
        # 清除所有棋子
        for r, c in self._piece_items:
            oval_id, text_id = self._piece_items[(r, c)]
            if oval_id:
                self.canvas.delete(oval_id)
            if text_id:
                self.canvas.delete(text_id)
            self._piece_items[(r, c)] = (None, None)
        
        # 绘制所有棋子
        for r in range(BOARD_ROWS):
            for c in range(BOARD_COLS):
                piece = model.game_state.board[r][c]
                if piece != EMPTY:
                    self._draw_piece(r, c, piece)

    def _partial_redraw_board(self, model):
        """部分重绘棋盘，只重绘变化的部分"""
        # 检查棋子变化
        for r in range(BOARD_ROWS):
            for c in range(BOARD_COLS):
                current_piece = model.game_state.board[r][c]
                if hasattr(self, '_cached_board') and self._cached_board:
                    cached_piece = self._cached_board[r][c]
                else:
                    cached_piece = EMPTY
                
                if current_piece != cached_piece:
                    # 棋子有变化，先删除旧的
                    oval_id, text_id = self._piece_items[(r, c)]
                    if oval_id:
                        self.canvas.delete(oval_id)
                    if text_id:
                        self.canvas.delete(text_id)
                    
                    # 绘制新的
                    if current_piece != EMPTY:
                        self._draw_piece(r, c, current_piece)
                    else:
                        # 更新缓存
                        self._piece_items[(r, c)] = (None, None)
                    
    def _draw_piece(self, r, c, piece):
        """绘制棋子，使用缓存和批量操作"""
        x_center, y_center = c*CELL_SIZE+CELL_SIZE/2+COORD_MARGIN, r*CELL_SIZE+CELL_SIZE/2+COORD_MARGIN
        color = "red" if piece == CANNON else "black"
        text = "炮" if piece == CANNON else "兵"
        
        # 创建棋子圆形和文字
        oval_id = self.canvas.create_oval(
            x_center-PIECE_RADIUS, y_center-PIECE_RADIUS,
            x_center+PIECE_RADIUS, y_center+PIECE_RADIUS,
            fill=color, outline="white", width=2,
            tags=f"piece_{r}_{c}"
        )
        
        text_id = self.canvas.create_text(
            x_center, y_center,
            text=text, fill="white", font=("Arial",16),
            tags=f"piece_text_{r}_{c}"
        )
        
        # 缓存棋子对象ID
        self._piece_items[(r, c)] = (oval_id, text_id)
        
        return oval_id, text_id
        
    def _update_highlights(self, model):
        """更新高亮点，使用批量操作"""
        # 清除所有旧的高亮点
        for item_id in self._highlight_items:
            self.canvas.delete(item_id)
        self._highlight_items.clear()
        
        # 如果有选中的棋子，绘制新的高亮点
        if model.selected_piece:
            r, c = model.selected_piece
            # 获取有效移动位置
            valid_moves = model.game_state.get_valid_moves(r, c)
            
            # 高亮选中的棋子（使用蓝色边框）
            x_center, y_center = c*CELL_SIZE+CELL_SIZE/2+COORD_MARGIN, r*CELL_SIZE+CELL_SIZE/2+COORD_MARGIN
            highlight_id = self.canvas.create_oval(
                x_center-PIECE_RADIUS-3, y_center-PIECE_RADIUS-3,
                x_center+PIECE_RADIUS+3, y_center+PIECE_RADIUS+3,
                outline="blue", width=3, tags="selected_highlight"
            )
            self._highlight_items.add(highlight_id)
            
            # 批量创建可移动位置的高亮点
            for move_r, move_c in valid_moves:
                x_center, y_center = move_c*CELL_SIZE+CELL_SIZE/2+COORD_MARGIN, move_r*CELL_SIZE+CELL_SIZE/2+COORD_MARGIN
                item_id = self.canvas.create_oval(
                    x_center-10, y_center-10, 
                    x_center+10, y_center+10, 
                    fill=HIGHLIGHT_COLOR, outline="", tags="move_highlight"
                )
                self._highlight_items.add(item_id)
        
    def update_button_states(self, is_ai_calculating, is_replay_mode, model):
        """根据游戏状态更新按钮的启用/禁用状态（最终统一逻辑版）"""
        
        # --- 阶段一：处理最高优先级的"AI计算中"状态 ---
        if is_ai_calculating:
            # AI计算时，禁用所有交互按钮，只启用"停止"
            self.btn_reset.config(state=tk.DISABLED)
            self.load_game_btn.config(state=tk.DISABLED)
            self.save_game_btn.config(state=tk.DISABLED)
            self.btn_calculate.config(state=tk.DISABLED)
            self.btn_stop.config(state=tk.NORMAL)
            self.first_move_btn.config(state=tk.DISABLED)
            self.prev_move_btn.config(state=tk.DISABLED)
            self.next_move_btn.config(state=tk.DISABLED)
            self.last_move_btn.config(state=tk.DISABLED)
            return # AI计算时，逻辑结束
        
        # --- 阶段二：处理非计算状态下的通用逻辑 ---
        
        # "停止"按钮总是禁用
        self.btn_stop.config(state=tk.DISABLED)
        # "新游戏"和"加载游戏"按钮总是可用
        self.btn_reset.config(state=tk.NORMAL)
        self.load_game_btn.config(state=tk.NORMAL)

        # >>> 修正！"计算一步"不再与复盘模式挂钩 <<<
        self.btn_calculate.config(state=tk.NORMAL)
        # "保存"按钮仍然只在对战模式下可用
        self.save_game_btn.config(state=tk.NORMAL if not is_replay_mode else tk.DISABLED)
        
        # --- 阶段三：处理导航/悔棋按钮的精细逻辑（这是唯一的标准）---
        
        # 是否有历史可以后退（悔棋）？
        can_go_back = model.replay_index > 0
        # 是否有未来可以前进（仅在复盘模式）？
        can_go_forward = is_replay_mode and model.replay_index < len(model.move_history) - 1

        self.first_move_btn.config(state=tk.NORMAL if can_go_back else tk.DISABLED)
        self.prev_move_btn.config(state=tk.NORMAL if can_go_back else tk.DISABLED)
        
        self.next_move_btn.config(state=tk.NORMAL if can_go_forward else tk.DISABLED)
        self.last_move_btn.config(state=tk.NORMAL if can_go_forward else tk.DISABLED)
        
        # --- 阶段四：处理游戏结束的最终状态覆盖 ---
        
        if model.game_state.winner != -1:
            # 游戏结束后，禁用计算和保存
            self.btn_calculate.config(state=tk.DISABLED)
            self.save_game_btn.config(state=tk.DISABLED)
        
    def _update_game_info(self, model):
        """根据模型更新游戏信息显示"""
        # 更新当前玩家
        current_player_text = "炮" if model.game_state.current_player == CANNON else "兵"
        self.current_player_label.config(text=f"当前玩家: {current_player_text}")
        
        # 更新士兵数量
        self.soldier_count_label.config(text=f"士兵数量: {model.game_state.soldier_count}")
        
    def _toggle_debug(self):
        """切换调试模式"""
        self.debug_enabled = self.debug_var.get()
        if not self.debug_enabled:
            self.update_debug_text("")  # 清除调试信息
            self.canvas.delete("analysis_overlay")  # 清除分析图层

    def update_debug_text(self, text, append=True, force=False):
        """更新调试信息文本"""
        if self.debug_enabled or force:
            self.debug_text.config(state=tk.NORMAL)
            if not append:
                self.debug_text.delete(1.0, tk.END)
            self.debug_text.insert(tk.END, text)
            self.debug_text.config(state=tk.DISABLED)
            self.debug_text.see(tk.END)
            
    def show_winner(self, winner):
        """显示获胜者"""
        winner_text = "炮方" if winner == CANNON else "兵方"
        messagebox.showinfo("游戏结束", f"{winner_text} 胜利!")
        
    def get_board_position(self, event_x, event_y):
        """将鼠标点击坐标转换为棋盘位置"""
        # 转换为相对坐标
        x = event_x - COORD_MARGIN
        y = event_y - COORD_MARGIN
        
        # 检查是否在棋盘范围内
        if 0 <= x < BOARD_WIDTH and 0 <= y < BOARD_HEIGHT:
            # 计算行列索引
            col = x // CELL_SIZE
            row = y // CELL_SIZE
            
            # 确保在有效范围内
            if 0 <= row < BOARD_ROWS and 0 <= col < BOARD_COLS:
                return (int(row), int(col))
                
        return None
        
    def update_analysis_overlay(self, root_moves_stats):
        """
        在棋盘上绘制AI分析的分数覆盖层。
        root_moves_stats: { ((r1,c1),(r2,c2)): score, ... }
        """
        if not self.debug_enabled:
            return

        # 1. 清除旧的覆盖层
        self.canvas.delete("analysis_overlay")
        
        # 2. 整理每个棋子的最佳分数
        # 因为一个棋子可能有多个走法，我们只显示最好的那个（或者显示最好的走法目标）
        # 这里我们选择：在棋子起始位置显示该棋子的最佳得分
        piece_scores = {} # (r, c) -> max_score
        
        for move, score in root_moves_stats.items():
            start_pos, end_pos = move
            # 过滤掉无限值（未被完全评估的）
            if abs(score) > 9000: continue
            
            if start_pos not in piece_scores:
                piece_scores[start_pos] = score
            else:
                # 简单地取最大值（对于当前行动方来说）
                # 注意：AI引擎里返回的分数已经是相对于当前行动方的（正数好，负数坏）
                if score > piece_scores[start_pos]:
                    piece_scores[start_pos] = score

        # 3. 绘制标签
        for pos, score in piece_scores.items():
            r, c = pos
            x_center, y_center = c*CELL_SIZE+CELL_SIZE/2+COORD_MARGIN, r*CELL_SIZE+CELL_SIZE/2+COORD_MARGIN
            
            # 颜色编码：正为绿，负为红
            color = "#00FF00" if score > 0 else "#FF0000" if score < 0 else "yellow"
            
            # 在棋子上方偏右绘制一个小标签
            self.canvas.create_text(
                x_center + 15, y_center - 15,
                text=str(int(score)),
                fill="black", # 描边
                font=("Arial", 10, "bold"),
                tags="analysis_overlay"
            )
            self.canvas.create_text(
                 x_center + 14, y_center - 16, # 稍微错位一点
                 text=str(int(score)),
                 fill=color,
                 font=("Arial", 10, "bold"),
                 tags="analysis_overlay"
            )

    def run(self):
        """启动GUI事件循环"""
        self.mainloop()