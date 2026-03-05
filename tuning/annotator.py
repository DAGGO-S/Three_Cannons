# tuning/annotator.py
# 人机协同标注工具 - 用于收集评估函数优化数据

import sys
import os
import json
import random
import tkinter as tk
from tkinter import ttk, messagebox
from datetime import datetime

# 添加项目根目录到路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.game_logic import GameState, CANNON, SOLDIER, EMPTY
from core.evaluation_logic import evaluate_board


class RandomBoardGenerator:
    """随机生成棋盘（3炮固定，兵随机分布）"""
    
    @staticmethod
    def generate(soldier_count=None):
        """生成随机棋盘
        
        Args:
            soldier_count: 兵的数量，None则随机(5-12)
        """
        if soldier_count is None:
            soldier_count = random.randint(5, 12)
        
        # 创建空棋盘
        board = [[EMPTY for _ in range(5)] for _ in range(5)]
        
        # 放置3个炮（随机位置）
        all_positions = [(r, c) for r in range(5) for c in range(5)]
        cannon_positions = random.sample(all_positions, 3)
        for r, c in cannon_positions:
            board[r][c] = CANNON
        
        # 放置兵（随机位置，避开炮）
        remaining = [p for p in all_positions if p not in cannon_positions]
        soldier_positions = random.sample(remaining, min(soldier_count, len(remaining)))
        for r, c in soldier_positions:
            board[r][c] = SOLDIER
        
        # 随机决定当前玩家
        current_player = random.choice([CANNON, SOLDIER])
        
        return GameState(board, current_player)

    @staticmethod
    def get_opening():
        """获取标准开局局面"""
        return GameState()  # 默认构造函数即为标准开局


class AnnotatorGUI:
    """标注工具 GUI"""
    
    CELL_SIZE = 80
    BOARD_SIZE = 5
    
    def __init__(self, root):
        self.root = root
        self.root.title("评估函数标注工具")
        
        # 数据
        self.current_state = None
        self.ai_top_moves = []
        self.selected_move = None
        self.selected_move_idx = None  # 选中的是哪个推荐
        self.click_start = None  # 用于自定义走法
        self.annotations = []
        self.sample_count = 0
        
        # 箭头颜色 (红、蓝、绿对比方案)
        self.arrow_colors = ['#FF0000', '#0000FF', '#008000']  
        self.btn_colors = ['#CC0000', '#0000CC', '#006400']    
        
        # 数据文件路径
        self.data_file = os.path.join(os.path.dirname(__file__), "training_data.json")
        self.load_existing_data()
        
        self.setup_ui()
        self.generate_new_board()
    
    def load_existing_data(self):
        """加载已有标注数据"""
        if os.path.exists(self.data_file):
            with open(self.data_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
                self.annotations = data.get("samples", [])
                self.sample_count = len(self.annotations)
    
    def save_data(self):
        """保存标注数据"""
        data = {
            "version": 1,
            "updated_at": datetime.now().isoformat(),
            "samples": self.annotations
        }
        with open(self.data_file, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    
    def setup_ui(self):
        """设置界面"""
        # 顶部状态栏
        top_frame = ttk.Frame(self.root, padding=10)
        top_frame.pack(fill=tk.X)
        
        self.status_label = ttk.Label(top_frame, text=f"已标注: {self.sample_count} 个", font=('Arial', 12))
        self.status_label.pack(side=tk.LEFT)
        
        self.auto_filter_var = tk.BooleanVar(value=True)
        ttk.Checkbutton(top_frame, text="自动过滤简单题", variable=self.auto_filter_var).pack(side=tk.LEFT, padx=10)
        
        self.continuous_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(top_frame, text="连续标注模式", variable=self.continuous_var).pack(side=tk.LEFT, padx=10)
        
        ttk.Button(top_frame, text="保存并退出", command=self.save_and_exit).pack(side=tk.RIGHT, padx=5)
        ttk.Button(top_frame, text="跳过", command=self.skip_board).pack(side=tk.RIGHT, padx=5)
        ttk.Button(top_frame, text="标准开局", command=self.load_opening).pack(side=tk.RIGHT, padx=5)
        
        # 主区域
        main_frame = ttk.Frame(self.root, padding=10)
        main_frame.pack(fill=tk.BOTH, expand=True)
        
        # 左侧：棋盘
        left_frame = ttk.Frame(main_frame)
        left_frame.pack(side=tk.LEFT, padx=10)
        
        self.canvas = tk.Canvas(
            left_frame,
            width=self.CELL_SIZE * self.BOARD_SIZE,
            height=self.CELL_SIZE * self.BOARD_SIZE,
            bg='#DEB887'
        )
        self.canvas.pack()
        self.canvas.bind("<Button-1>", self.on_canvas_click)
        
        # 当前玩家显示（更醒目）
        self.player_frame = tk.Frame(left_frame, padx=10, pady=5)
        self.player_frame.pack(pady=5, fill=tk.X)
        self.player_label = tk.Label(self.player_frame, text="", font=('Arial', 14, 'bold'), fg='white', padx=20, pady=5)
        self.player_label.pack()
        
        # 右侧：AI推荐 + 选择按钮
        right_frame = ttk.Frame(main_frame, padding=10)
        right_frame.pack(side=tk.LEFT, fill=tk.Y, padx=20)
        
        ttk.Label(right_frame, text="AI 推荐走法:", font=('Arial', 12, 'bold')).pack(anchor=tk.W)
        
        self.move_buttons = []
        # 使用自定义样式来设置按钮颜色（Tkinter原生Button在某些系统下颜色难调，这里用Label模拟或设置fg）
        for i in range(3):
            btn = tk.Button(right_frame, text=f"[{i+1}] --", width=35,
                           font=('Arial', 10, 'bold'),
                           command=lambda idx=i: self.select_ai_move(idx))
            btn.pack(pady=5, anchor=tk.W)
            self.move_buttons.append(btn)
        
        ttk.Separator(right_frame, orient=tk.HORIZONTAL).pack(fill=tk.X, pady=15)
        
        ttk.Label(right_frame, text="你的选择:", font=('Arial', 12, 'bold')).pack(anchor=tk.W)
        
        self.choice_label = ttk.Label(right_frame, text="(点击上方按钮或棋盘选择)", font=('Arial', 10))
        self.choice_label.pack(anchor=tk.W, pady=5)
        
        ttk.Button(right_frame, text="✓ AI Top1 正确", width=20,
                  command=lambda: self.select_ai_move(0)).pack(pady=3)
        
        ttk.Separator(right_frame, orient=tk.HORIZONTAL).pack(fill=tk.X, pady=15)
        
        ttk.Label(right_frame, text="自定义走法:", font=('Arial', 10)).pack(anchor=tk.W)
        ttk.Label(right_frame, text="在棋盘上点击起点→终点", font=('Arial', 9), foreground='gray').pack(anchor=tk.W)
        
        self.custom_label = ttk.Label(right_frame, text="", font=('Arial', 10), foreground='blue')
        self.custom_label.pack(anchor=tk.W, pady=5)
        
        ttk.Button(right_frame, text="确认自定义走法", command=self.confirm_custom_move).pack(pady=5)
        
        # 底部：确认提交
        bottom_frame = ttk.Frame(self.root, padding=10)
        bottom_frame.pack(fill=tk.X)
        
        self.submit_btn = ttk.Button(bottom_frame, text="提交并下一个", command=self.submit_annotation)
        self.submit_btn.pack(side=tk.RIGHT, padx=10)
    
    def generate_new_board(self, state=None):
        """显示新棋盘
        
        Args:
            state: 如果提供，则显示该局面；否则随机生成。
        """
        if state is None:
            self.current_state = RandomBoardGenerator.generate()
        else:
            self.current_state = state
            
        self.selected_move = None
        self.click_start = None
        self.custom_label.config(text="")
        self.choice_label.config(text="(点击上方按钮或棋盘选择)")
        
        self.calculate_ai_moves()
        self.draw_board()
        self.update_move_buttons()
        
        # 自动跳过无聊盘面 (只在随机生成模式且开启过滤时生效)
        if state is None and hasattr(self, 'auto_filter_var') and self.auto_filter_var.get():
            if len(self.ai_top_moves) >= 2:
                diff = self.ai_top_moves[0][1] - self.ai_top_moves[1][1]
                if diff > 50:
                    self.root.after(100, self.generate_new_board)
                    return

        # 更新玩家显示
        player_type = " (开局/连续)" if state is not None else ""
        if self.current_state.current_player == CANNON:
            self.player_label.config(text=f"▶ 炮方走棋{player_type}", bg='#DC143C')
        else:
            self.player_label.config(text=f"▶ 兵方走棋{player_type}", bg='#2E8B57')
    
    def calculate_ai_moves(self):
        """计算 AI 的 Top3 走法（深度 0）"""
        self.ai_top_moves = []
        player = self.current_state.current_player
        
        all_moves = []
        for r in range(5):
            for c in range(5):
                if self.current_state.board[r][c] == player:
                    for end in self.current_state.get_valid_moves(r, c):
                        move = ((r, c), end)
                        # 模拟走法后评估
                        new_state = self.current_state.move_piece(r, c, end[0], end[1])
                        score, _ = evaluate_board(new_state)
                        # 对于兵方需要取反（因为评估函数是炮方视角）
                        if player == SOLDIER:
                            score = -score
                        all_moves.append((move, score))
        
        # 按分数排序取 Top3
        all_moves.sort(key=lambda x: x[1], reverse=True)
        self.ai_top_moves = all_moves[:3]
    
    def update_move_buttons(self):
        """更新走法按钮显示，并同步颜色"""
        for i, btn in enumerate(self.move_buttons):
            if i < len(self.ai_top_moves):
                move, score = self.ai_top_moves[i]
                start, end = move
                text = f"[{i+1}] ({start[0]},{start[1]})→({end[0]},{end[1]})  分数: {score:.0f}"
                btn.config(text=text, state=tk.NORMAL, fg=self.btn_colors[i])
            else:
                btn.config(text=f"[{i+1}] --", state=tk.DISABLED, fg='gray')
    
    def draw_arrow(self, start, end, color, width=3, label=None):
        """在棋盘上绘制箭头"""
        sr, sc = start
        er, ec = end
        
        # 计算起点和终点的像素坐标
        x1 = sc * self.CELL_SIZE + self.CELL_SIZE // 2
        y1 = sr * self.CELL_SIZE + self.CELL_SIZE // 2
        x2 = ec * self.CELL_SIZE + self.CELL_SIZE // 2
        y2 = er * self.CELL_SIZE + self.CELL_SIZE // 2
        
        # 缩短箭头（避免覆盖棋子）
        import math
        dx, dy = x2 - x1, y2 - y1
        length = math.sqrt(dx*dx + dy*dy)
        if length > 0:
            offset = 25  # 缩短距离
            x1 += dx / length * offset
            y1 += dy / length * offset
            x2 -= dx / length * offset
            y2 -= dy / length * offset
        
        # 绘制箭头阴影/边框（先画一层黑色的稍宽的线）
        self.canvas.create_line(x1, y1, x2, y2, fill='black', width=width+2, arrow=tk.LAST, arrowshape=(14, 17, 6))
        # 绘制主箭头线
        self.canvas.create_line(x1, y1, x2, y2, fill=color, width=width, arrow=tk.LAST, arrowshape=(12, 15, 5))
        
        # 绘制标签
        if label:
            mid_x, mid_y = (x1 + x2) / 2, (y1 + y2) / 2
            # 优化标签位置
            if length > 0:
                nx, ny = -dy / length, dx / length
                offset_val = 18
                if abs(dx) < 5: nx, ny = 1, 0
                
                # 绘制文字背景框（增强可读性）
                tx, ty = mid_x + nx * offset_val, mid_y + ny * offset_val
                self.canvas.create_rectangle(tx-10, ty-10, tx+10, ty+10, fill='black', outline=color)
                # 绘制文字
                self.canvas.create_text(tx, ty, text=label, fill='white', font=('Arial', 10, 'bold'))
            else:
                self.canvas.create_text(mid_x, mid_y - 12, text=label, fill='white', font=('Arial', 10, 'bold'), bg='black')
    
    def draw_board(self):
        """绘制棋盘"""
        self.canvas.delete("all")
        
        # 绘制网格
        for i in range(self.BOARD_SIZE + 1):
            # 横线
            self.canvas.create_line(
                0, i * self.CELL_SIZE,
                self.BOARD_SIZE * self.CELL_SIZE, i * self.CELL_SIZE,
                fill='black'
            )
            # 竖线
            self.canvas.create_line(
                i * self.CELL_SIZE, 0,
                i * self.CELL_SIZE, self.BOARD_SIZE * self.CELL_SIZE,
                fill='black'
            )
        
        # 绘制棋子
        for r in range(5):
            for c in range(5):
                piece = self.current_state.board[r][c]
                if piece != EMPTY:
                    x = c * self.CELL_SIZE + self.CELL_SIZE // 2
                    y = r * self.CELL_SIZE + self.CELL_SIZE // 2
                    radius = self.CELL_SIZE // 2 - 8
                    
                    if piece == SOLDIER:
                        self.canvas.create_oval(
                            x - radius, y - radius, x + radius, y + radius,
                            fill='#2E8B57', outline='black', width=2
                        )
                        self.canvas.create_text(x, y, text="兵", fill='white', font=('Arial', 16, 'bold'))
                    else:  # CANNON
                        self.canvas.create_oval(
                            x - radius, y - radius, x + radius, y + radius,
                            fill='#DC143C', outline='black', width=2
                        )
                        self.canvas.create_text(x, y, text="炮", fill='white', font=('Arial', 16, 'bold'))
        
        # 绘制 AI Top3 走法箭头
        for i, (move, score) in enumerate(self.ai_top_moves):
            start, end = move
            color = self.arrow_colors[i] if i < len(self.arrow_colors) else 'gray'
            width = 4 if i == 0 else 2  # Top1 更粗
            label = f"[{i+1}]"
            self.draw_arrow(start, end, color, width, label)
        
        # 高亮选中的起点
        if self.click_start:
            r, c = self.click_start
            x = c * self.CELL_SIZE + self.CELL_SIZE // 2
            y = r * self.CELL_SIZE + self.CELL_SIZE // 2
            self.canvas.create_rectangle(
                x - 35, y - 35, x + 35, y + 35,
                outline='yellow', width=3
            )
    
    def on_canvas_click(self, event):
        """棋盘点击事件"""
        c = event.x // self.CELL_SIZE
        r = event.y // self.CELL_SIZE
        
        if not (0 <= r < 5 and 0 <= c < 5):
            return
        
        if self.click_start is None:
            # 第一次点击：选起点
            piece = self.current_state.board[r][c]
            if piece == self.current_state.current_player:
                self.click_start = (r, c)
                self.custom_label.config(text=f"起点: ({r},{c}) → 请点击终点")
                self.draw_board()
        else:
            # 第二次点击：选终点
            start = self.click_start
            end = (r, c)
            
            # 检查是否合法
            valid = self.current_state.get_valid_moves(start[0], start[1])
            if end in valid:
                self.selected_move = (start, end)
                self.custom_label.config(text=f"自定义: ({start[0]},{start[1]})→({end[0]},{end[1]})")
                self.choice_label.config(text=f"已选: 自定义走法")
            else:
                self.custom_label.config(text="无效走法，请重选")
            
            self.click_start = None
            self.draw_board()
    
    def select_ai_move(self, idx):
        """选择 AI 推荐的走法并自动提交"""
        if idx < len(self.ai_top_moves):
            self.selected_move = self.ai_top_moves[idx][0]
            self.selected_move_idx = idx
            self.choice_label.config(text=f"已选: AI Top{idx+1}")
            self.custom_label.config(text="")
            self.click_start = None
            # 自动提交
            self.submit_annotation()
    
    def confirm_custom_move(self):
        """确认自定义走法并自动提交"""
        if self.selected_move:
            self.choice_label.config(text=f"已确认自定义走法")
            # 自动提交
            self.submit_annotation()
    
    def submit_annotation(self):
        """提交标注"""
        if self.selected_move is None:
            messagebox.showwarning("提示", "请先选择一个走法")
            return
        
        # 保存标注
        start, end = self.selected_move
        sample = {
            "id": len(self.annotations) + 1,
            "board": [list(row) for row in self.current_state.board],
            "current_player": self.current_state.current_player,
            "ai_top3": [
                {"move": [list(m[0]), list(m[1])], "score": s}
                for m, s in self.ai_top_moves
            ],
            "human_choice": [list(start), list(end)],
            "timestamp": datetime.now().isoformat()
        }
        self.annotations.append(sample)
        self.sample_count += 1
        self.status_label.config(text=f"已标注: {self.sample_count} 个")
        
        # 保存下一状态以便进入连续模式
        next_state = self.current_state.move_piece(start[0], start[1], end[0], end[1])
        
        # 自动保存
        self.save_data()
        
        # 判断模式
        if self.continuous_var.get():
            if next_state.winner is not None:
                winner_name = "炮方" if next_state.winner == CANNON else "兵方"
                messagebox.showinfo("结束", f"对局结束，胜者: {winner_name}\n将自动生成新盘面。")
                self.generate_new_board()
            else:
                self.generate_new_board(state=next_state)
        else:
            self.generate_new_board()
    
    def skip_board(self):
        """跳过当前棋盘"""
        self.generate_new_board()
        
    def load_opening(self):
        """加载标准开局并将模式切换为连续"""
        self.continuous_var.set(True)  # 既然选了开局，通常是想连续标注
        self.generate_new_board(state=RandomBoardGenerator.get_opening())
    
    def save_and_exit(self):
        """保存并退出"""
        self.save_data()
        messagebox.showinfo("保存成功", f"已保存 {self.sample_count} 条标注数据")
        self.root.quit()


def main():
    root = tk.Tk()
    root.geometry("800x500")
    app = AnnotatorGUI(root)
    root.mainloop()


if __name__ == "__main__":
    main()
