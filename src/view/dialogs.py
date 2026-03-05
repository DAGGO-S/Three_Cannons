import tkinter as tk
from tkinter import ttk

class SettingsDialog(tk.Toplevel):
    def __init__(self, parent, current_settings):
        super().__init__(parent)
        self.title("游戏设置")
        self.result = None

        # 玩家类型设置框架
        players_frame = ttk.LabelFrame(self, text="玩家类型设置")
        players_frame.pack(padx=10, pady=5, fill="x")
        
        ttk.Label(players_frame, text="先手 (炮方):").grid(row=0, column=0, sticky="w", padx=5, pady=2)
        self.cannon_player_var = tk.StringVar(value=current_settings["cannon_player"], master=self)
        ttk.Radiobutton(players_frame, text="人类", variable=self.cannon_player_var, value="Human").grid(row=0, column=1, sticky="w")
        ttk.Radiobutton(players_frame, text="AI", variable=self.cannon_player_var, value="AI").grid(row=0, column=2, sticky="w")

        ttk.Label(players_frame, text="后手 (兵方):").grid(row=1, column=0, sticky="w", padx=5, pady=2)
        self.soldier_player_var = tk.StringVar(value=current_settings["soldier_player"], master=self)
        ttk.Radiobutton(players_frame, text="人类", variable=self.soldier_player_var, value="Human").grid(row=1, column=1, sticky="w")
        ttk.Radiobutton(players_frame, text="AI", variable=self.soldier_player_var, value="AI").grid(row=1, column=2, sticky="w")
        
        # AI 强度设置框架
        ai_frame = ttk.LabelFrame(self, text="AI 强度设置")
        ai_frame.pack(padx=10, pady=5, fill="x")
        
        ttk.Label(ai_frame, text="最大深度 (2-15):").grid(row=0, column=0, sticky="w", padx=5, pady=2)
        self.depth_var = tk.IntVar(value=int(current_settings["depth"]), master=self)
        ttk.Spinbox(ai_frame, from_=2, to=15, textvariable=self.depth_var, width=5).grid(row=0, column=1, sticky="w")

        ttk.Label(ai_frame, text="最长思考时间 (秒):").grid(row=0, column=2, sticky="w", padx=5, pady=2)
        self.time_limit_var = tk.DoubleVar(value=float(current_settings["time_limit"]), master=self)
        ttk.Spinbox(ai_frame, from_=1, to=300, textvariable=self.time_limit_var, width=5).grid(row=0, column=3, sticky="w")
        
        # 性能设置框架
        performance_frame = ttk.LabelFrame(self, text="性能设置")
        performance_frame.pack(padx=10, pady=5, fill="x")
        
        ttk.Label(performance_frame, text="使用多线程:").grid(row=0, column=0, sticky="w", padx=5, pady=2)
        self.use_threading_var = tk.BooleanVar(value=current_settings.get("use_threading", True), master=self)
        ttk.Checkbutton(performance_frame, variable=self.use_threading_var).grid(row=0, column=1, sticky="w")
        
        ttk.Label(performance_frame, text="线程数量:").grid(row=0, column=2, sticky="w", padx=5, pady=2)
        self.thread_count_var = tk.IntVar(value=current_settings.get("thread_count", 4), master=self)
        thread_spinbox = ttk.Spinbox(performance_frame, from_=1, to=8, textvariable=self.thread_count_var, width=5)
        thread_spinbox.grid(row=0, column=3, sticky="w")
        # 根据是否使用多线程来启用/禁用线程数量选择
        thread_spinbox.config(state="normal" if self.use_threading_var.get() else "disabled")
        
        # 绑定复选框状态变化事件
        self.use_threading_var.trace_add("write", lambda *args: thread_spinbox.config(
            state="normal" if self.use_threading_var.get() else "disabled"
        ))

        # 按钮框架
        button_frame = ttk.Frame(self)
        button_frame.pack(pady=10)
        ttk.Button(button_frame, text="确定", command=self.on_apply).pack(side="left", padx=5)
        ttk.Button(button_frame, text="取消", command=self.on_cancel).pack(side="left", padx=5)
        
        self.protocol("WM_DELETE_WINDOW", self.on_cancel)
        self.transient(parent)
        self.grab_set()
        parent.wait_window(self)

    def on_apply(self):
        self.result = {
            "cannon_player": self.cannon_player_var.get(),
            "soldier_player": self.soldier_player_var.get(),
            "depth": self.depth_var.get(),
            "time_limit": self.time_limit_var.get(),
            "use_threading": self.use_threading_var.get(),
            "thread_count": self.thread_count_var.get()
        }
        self.destroy()

    def on_cancel(self):
        self.result = None
        self.destroy()