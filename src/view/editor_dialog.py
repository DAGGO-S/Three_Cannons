import tkinter as tk
from tkinter import ttk, messagebox
from core.game_logic import GameState, CANNON, SOLDIER, EMPTY

CELL_SIZE = 80
PIECE_RADIUS = 30
COORD_MARGIN = 30
BOARD_COLS = 5
BOARD_ROWS = 5

class EditorDialog(tk.Toplevel):
    def __init__(self, parent, current_state: GameState, on_confirm_callback):
        super().__init__(parent)
        self.title("残局编辑器 (FEN)")
        self.resizable(False, False)
        
        self.on_confirm_callback = on_confirm_callback
        
        # Internal state
        self.board = [list(row) for row in current_state.board]
        self.current_player = current_state.current_player
        
        self.player_var = tk.StringVar(value="c" if self.current_player == CANNON else "s")
        self.fen_var = tk.StringVar()
        
        self._create_widgets()
        self._draw_board()
        self._update_ui_from_state()
        
        # Center the dialog relative to parent
        self.geometry("+%d+%d" % (parent.winfo_rootx() + 50, parent.winfo_rooty() + 50))
        self.transient(parent)
        self.grab_set()
        
    def _create_widgets(self):
        # Canvas Frame
        canvas_width = BOARD_COLS * CELL_SIZE + 2 * COORD_MARGIN
        canvas_height = BOARD_ROWS * CELL_SIZE + 2 * COORD_MARGIN
        
        self.canvas = tk.Canvas(self, width=canvas_width, height=canvas_height, bg="#CDBA96")
        self.canvas.pack(side="top", padx=10, pady=10)
        self.canvas.bind("<Button-1>", self._on_canvas_click)
        
        # Control Frame
        ctrl_frame = ttk.Frame(self)
        ctrl_frame.pack(side="top", fill="x", padx=10, pady=5)
        
        # Player Choice
        player_frame = ttk.LabelFrame(ctrl_frame, text="行棋方")
        player_frame.pack(side="left", fill="y", padx=5)
        ttk.Radiobutton(player_frame, text="炮方", variable=self.player_var, value="c", command=self._update_fen_from_ui).pack(anchor="w")
        ttk.Radiobutton(player_frame, text="兵方", variable=self.player_var, value="s", command=self._update_fen_from_ui).pack(anchor="w")
        
        # Info & Warnings
        info_frame = ttk.Frame(ctrl_frame)
        info_frame.pack(side="left", fill="both", expand=True, padx=10)
        self.lbl_counts = tk.Label(info_frame, text="", font=("Arial", 10))
        self.lbl_counts.pack(anchor="w")
        self.lbl_warning = tk.Label(info_frame, text="", font=("Arial", 10, "bold"), fg="red")
        self.lbl_warning.pack(anchor="w")
        
        # Buttons
        btn_frame = ttk.Frame(ctrl_frame)
        btn_frame.pack(side="right", padx=5)
        ttk.Button(btn_frame, text="清空棋盘", command=self._clear_board).pack(fill="x", pady=2)
        ttk.Button(btn_frame, text="标准初始状态", command=self._reset_board).pack(fill="x", pady=2)
        
        # FEN Section
        fen_frame = ttk.LabelFrame(self, text="FEN 实时同步区 (支持粘贴导入)")
        fen_frame.pack(side="top", fill="x", padx=10, pady=5)
        
        fen_entry = ttk.Entry(fen_frame, textvariable=self.fen_var, font=("Courier", 10))
        fen_entry.pack(side="left", fill="x", expand=True, padx=5, pady=5)
        
        ttk.Button(fen_frame, text="应用 FEN", command=self._apply_fen).pack(side="left", padx=5)
        
        # Confirm
        ttk.Button(self, text=">> 验证并带入主棋盘 <<", command=self._on_confirm).pack(side="bottom", pady=10)
        
    def _draw_board(self):
        # Draw physical grid lines
        for r in range(BOARD_ROWS):
            for c in range(BOARD_COLS):
                x0, y0 = c*CELL_SIZE+COORD_MARGIN, r*CELL_SIZE+COORD_MARGIN
                x1, y1 = (c+1)*CELL_SIZE+COORD_MARGIN, (r+1)*CELL_SIZE+COORD_MARGIN
                self.canvas.create_rectangle(x0, y0, x1, y1, outline="black")
                
    def _update_ui_from_state(self):
        # Clear pieces
        self.canvas.delete("piece")
        
        c_count, s_count = 0, 0
        for r in range(BOARD_ROWS):
            for c in range(BOARD_COLS):
                piece = self.board[r][c]
                if piece != EMPTY:
                    x = c * CELL_SIZE + CELL_SIZE/2 + COORD_MARGIN
                    y = r * CELL_SIZE + CELL_SIZE/2 + COORD_MARGIN
                    if piece == CANNON:
                        c_count += 1
                        self.canvas.create_oval(x-PIECE_RADIUS, y-PIECE_RADIUS, x+PIECE_RADIUS, y+PIECE_RADIUS, fill="red", outline="white", tags="piece")
                        self.canvas.create_text(x, y, text="炮", fill="white", font=("Arial", 16), tags="piece")
                    elif piece == SOLDIER:
                        s_count += 1
                        self.canvas.create_oval(x-PIECE_RADIUS, y-PIECE_RADIUS, x+PIECE_RADIUS, y+PIECE_RADIUS, fill="black", outline="white", tags="piece")
                        self.canvas.create_text(x, y, text="兵", fill="white", font=("Arial", 16), tags="piece")
                        
        self.lbl_counts.config(text=f"当前库存：炮 [{c_count}/3]  |  兵 [{s_count}/15]")
        
        warning_msg = ""
        if c_count > 3: warning_msg += "[告警] 炮的数量不能超过3个！ "
        if s_count > 15: warning_msg += "[告警] 兵的数量不能超过15个！ "
        if c_count == 0 and s_count == 0: warning_msg += "[提示] 棋盘为空！"
        
        self.lbl_warning.config(text=warning_msg)
        
        # Update fen string seamlessly
        try:
            player = CANNON if self.player_var.get() == "c" else SOLDIER
            self.fen_var.set(GameState(board=self.board, current_player=player).to_fen())
        except Exception:
            pass

    def _update_fen_from_ui(self):
        self._update_ui_from_state()

    def _on_canvas_click(self, event):
        x, y = event.x - COORD_MARGIN, event.y - COORD_MARGIN
        c, r = int(x // CELL_SIZE), int(y // CELL_SIZE)
        if 0 <= r < BOARD_ROWS and 0 <= c < BOARD_COLS:
            current = self.board[r][c]
            # Cycle logic: EMPTY -> SOLDIER -> CANNON -> EMPTY
            if current == EMPTY: nxt = SOLDIER
            elif current == SOLDIER: nxt = CANNON
            else: nxt = EMPTY
            
            self.board[r][c] = nxt
            self._update_ui_from_state()
            
    def _clear_board(self):
        self.board = [[EMPTY]*BOARD_COLS for _ in range(BOARD_ROWS)]
        self._update_ui_from_state()

    def _reset_board(self):
        self.board = [list(row) for row in GameState().board]
        self._update_ui_from_state()

    def _apply_fen(self):
        fen_str = self.fen_var.get().strip()
        try:
            state = GameState.from_fen(fen_str)
            self.board = [list(row) for row in state.board]
            self.player_var.set("c" if state.current_player == CANNON else "s")
            self._update_ui_from_state()
        except Exception as e:
            messagebox.showerror("FEN 解析错误", f"无法应用 FEN 字串:\n{str(e)}", parent=self)
            
    def _on_confirm(self):
        # Legality validation before returning
        c_count = sum(row.count(CANNON) for row in self.board)
        s_count = sum(row.count(SOLDIER) for row in self.board)
        
        if c_count == 0 and s_count == 0:
            messagebox.showerror("提交失败", "引擎拒绝接受空的棋盘布局！", parent=self)
            return
            
        if c_count > 3 or s_count > 15:
            if not messagebox.askyesno("覆盖告警", "该残局棋子数量超出游戏设计基准。强制带入可能面临引擎运行错误，是否继续？", parent=self):
                return
                
        fen_str = self.fen_var.get()
        self.on_confirm_callback(fen_str)
        self.destroy()
