cimport core.zobrist_hashing as zh
from core.board_ops cimport c_check_winner, c_gen_moves, c_canonical_hash
# 导出常量到 Python 层，以兼容旧的 Python 导入 (如 from core.game_logic import DRAW)
from core.constants import EMPTY, SOLDIER, CANNON, DRAW, NO_WINNER, BOARD_ROWS, BOARD_COLS
from libc.string cimport memcpy

# Cython imports
import cython

# 初始棋盘（开局布局，行主序 1D）
cdef int INITIAL_BOARD[25]

def _init_initial_board():
    global INITIAL_BOARD
    cdef int i
    cdef list temp = [1,1,1,1,1, 1,1,1,1,1, 1,1,1,1,1, 0,0,0,0,0, 0,2,2,2,0]
    for i in range(25):
        INITIAL_BOARD[i] = temp[i]

_init_initial_board()

# 对称变换表已移至 board_ops.pyx


@cython.boundscheck(False)
@cython.wraparound(False)
cdef class GameState:
    """【Phase3B】高性能 GameState：board 存储为 C int[25] 数组。

    字段声明在 game_logic.pxd 中，方法实现在此处。
    对外接口：
    - state.board          -> tuple-of-tuples（兼容 GUI/model 的只读访问）
    - state.winner         -> int  (-1=None, 0=CONST_DRAW, 1=CONST_SOLDIER, 2=CONST_CANNON)
    - state.current_player -> int
    - state.soldier_count  -> int
    - state.hash           -> unsigned long long
    """

    def __init__(self, board=None, current_player=CONST_CANNON):
        cdef int r, c, s_count, c_count, i, val
        self.winner = CONST_NO_WINNER

        if board is None:
            # 使用预定义的初始棋盘
            memcpy(self.board_c, INITIAL_BOARD, 25 * sizeof(int))
            self.soldier_count = 15
            self.cannon_count = 3
        else:
            # 从外部 board（list-of-lists 或 tuple-of-tuples）初始化
            s_count = 0
            c_count = 0
            for r in range(5):
                for c in range(5):
                    val = board[r][c]
                    self.board_c[r * 5 + c] = val
                    if val == CONST_SOLDIER:
                        s_count += 1
                    elif val == CONST_CANNON:
                        c_count += 1
            self.soldier_count = s_count
            self.cannon_count = c_count

        self.current_player = current_player

        # 计算初始哈希（使用 C 级内联方法）
        self.hash = zh._hasher.c_compute_hash(self.board_c, self.current_player)

        # 检查胜负 (委托到 board_ops)
        self.winner = c_check_winner(self.board_c, self.soldier_count)
        self._has_canonical_hash = False

    # ------------------------------------------------------------------
    # Python 兼容层：通过 property 把 board_c 以 tuple-of-tuples 暴露出去
    # 只在 GUI 渲染时调用，不在搜索热路径上
    # ------------------------------------------------------------------
    @property
    def board(self):
        """返回 tuple-of-tuples，与改造前完全兼容。"""
        return tuple(
            tuple(self.board_c[r * 5 + c] for c in range(5))
            for r in range(5)
        )

    # ------------------------------------------------------------------
    # pickle 支持（历史记录保存用）
    # ------------------------------------------------------------------
    def __reduce__(self):
        board_2d = [[self.board_c[r*5+c] for c in range(5)] for r in range(5)]
        return (GameState, (board_2d, self.current_player))

    # ------------------------------------------------------------------
    # FEN (Forsyth-Edwards Notation) 字符串支持
    # ------------------------------------------------------------------
    @classmethod
    def from_fen(cls, str fen):
        """从 FEN 字符串加载局面，格式示例: 'sssss/sssss/sssss/5/1ccc1 c'"""
        parts = fen.split(' ')
        if len(parts) != 2:
            raise ValueError(f"Invalid FEN format: {fen}")
            
        board_str, player_str = parts
        
        # 预构二维数组
        cdef list board_2d = [[0]*5 for _ in range(5)]
        cdef int r = 0
        cdef int c = 0
        cdef int count, i
        
        for char in board_str:
            if char == '/':
                r += 1
                c = 0
            elif char == 'c' or char == 'C':
                board_2d[r][c] = CONST_CANNON
                c += 1
            elif char == 's' or char == 'S':
                board_2d[r][c] = CONST_SOLDIER
                c += 1
            elif char.isdigit():
                count = int(char)
                for i in range(count):
                    board_2d[r][c] = CONST_EMPTY
                    c += 1
            else:
                raise ValueError(f"Invalid FEN character: {char}")
                
        cdef int current_player = CONST_CANNON if player_str.lower() == 'c' else CONST_SOLDIER
        return cls(board=board_2d, current_player=current_player)

    def to_fen(self):
        """将当前局面序列化为 FEN 字符串"""
        cdef int r, c, piece, empty_count
        cdef list fen_rows = []
        cdef str row_str
        
        for r in range(5):
            row_str = ""
            empty_count = 0
            for c in range(5):
                piece = self.board_c[r * 5 + c]
                if piece == CONST_EMPTY:
                    empty_count += 1
                else:
                    if empty_count > 0:
                        row_str += str(empty_count)
                        empty_count = 0
                    if piece == CONST_CANNON:
                        row_str += 'c'
                    elif piece == CONST_SOLDIER:
                        row_str += 's'
            if empty_count > 0:
                row_str += str(empty_count)
            fen_rows.append(row_str)
            
        board_part = "/".join(fen_rows)
        player_part = 'c' if self.current_player == CONST_CANNON else 's'
        
        return f"{board_part} {player_part}"

    # ------------------------------------------------------------------
    # 走法生成
    # ------------------------------------------------------------------
    @cython.boundscheck(False)
    @cython.wraparound(False)
    def get_valid_moves(self, int r, int c):
        cdef int piece = self.board_c[r * 5 + c]
        if piece == CONST_EMPTY:
            return []

        cdef list moves = []
        cdef int dr, dc, tr, tc, jump_r, jump_c, target_r, target_c

        if piece == CONST_SOLDIER:
            for dr, dc in ((0,1),(0,-1),(1,0),(-1,0)):
                tr = r + dr
                tc = c + dc
                if 0 <= tr < 5 and 0 <= tc < 5 and self.board_c[tr * 5 + tc] == CONST_EMPTY:
                    moves.append((tr, tc))

        elif piece == CONST_CANNON:
            # 规则1: 普通移动
            for dr, dc in ((0,1),(0,-1),(1,0),(-1,0)):
                tr = r + dr
                tc = c + dc
                if 0 <= tr < 5 and 0 <= tc < 5 and self.board_c[tr * 5 + tc] == CONST_EMPTY:
                    moves.append((tr, tc))
            # 规则2: 隔空吃兵
            for dr, dc in ((0,1),(0,-1),(1,0),(-1,0)):
                jump_r = r + dr
                jump_c = c + dc
                target_r = r + 2 * dr
                target_c = c + 2 * dc
                if (0 <= target_r < 5 and 0 <= target_c < 5 and
                        0 <= jump_r < 5 and 0 <= jump_c < 5 and
                        self.board_c[jump_r * 5 + jump_c] == CONST_EMPTY and
                        self.board_c[target_r * 5 + target_c] == CONST_SOLDIER):
                    moves.append((target_r, target_c))

        return moves

    # ------------------------------------------------------------------
    # move_piece：热路径核心
    # 【Phase3B】用 memcpy + 两个整数赋值替代 list/tuple 重建
    # ------------------------------------------------------------------
    @cython.boundscheck(False)
    @cython.wraparound(False)
    def move_piece(self, int start_r, int start_c, int end_r, int end_c):
        cdef int start_idx = start_r * 5 + start_c
        cdef int end_idx   = end_r   * 5 + end_c
        cdef int piece          = self.board_c[start_idx]
        cdef int captured_piece = self.board_c[end_idx]
        cdef int dr = end_r - start_r
        cdef int dc = end_c - start_c
        cdef int jump_r, jump_c
        cdef bint legal = False

        # 内联合法性验证（直接 C 级判断，无 Python 列表分配）
        if piece == CONST_SOLDIER:
            if (abs(dr) + abs(dc) == 1) and captured_piece == CONST_EMPTY:
                legal = True
        elif piece == CONST_CANNON:
            if (abs(dr) + abs(dc) == 1) and captured_piece == CONST_EMPTY:
                legal = True
            elif (abs(dr) == 2 or abs(dc) == 2) and (dr == 0 or dc == 0):
                jump_r = (start_r + end_r) // 2
                jump_c = (start_c + end_c) // 2
                if (self.board_c[jump_r * 5 + jump_c] == CONST_EMPTY and
                        captured_piece == CONST_SOLDIER):
                    legal = True

        if not legal:
            raise ValueError("Attempted to make an illegal move.")

        # 创建新状态（不调用 __init__，直接用 __new__）
        cdef GameState new_state = GameState.__new__(GameState)

        # 【Phase3B 核心】memcpy 整块棋盘，然后只改动两格
        memcpy(new_state.board_c, self.board_c, 25 * sizeof(int))

        # 执行移动（两个整数赋值）
        new_state.board_c[end_idx]   = piece
        new_state.board_c[start_idx] = CONST_EMPTY

        new_state.soldier_count = self.soldier_count
        if captured_piece == CONST_SOLDIER:
            new_state.soldier_count -= 1

        # 增量更新哈希（纯 C XOR，无 GIL 依赖）
        cdef unsigned long long h = self.hash
        h = zh._hasher.c_update_hash(h, start_r, start_c, end_r, end_c, piece)
        if captured_piece != CONST_EMPTY:
            h = zh._hasher.c_remove_piece_hash(h, end_r, end_c, captured_piece)
        h = zh._hasher.c_switch_turn_hash(h)
        new_state.hash = h

        new_state.current_player = CONST_SOLDIER if self.current_player == CONST_CANNON else CONST_CANNON
        new_state.winner = c_check_winner(new_state.board_c, new_state.soldier_count)
        new_state._has_canonical_hash = False

        return new_state

    # ------------------------------------------------------------------
    # 空着剪枝支持
    # ------------------------------------------------------------------
    def pass_turn(self):
        cdef GameState new_state = GameState.__new__(GameState)
        memcpy(new_state.board_c, self.board_c, 25 * sizeof(int))
        new_state.soldier_count  = self.soldier_count
        new_state.current_player = CONST_SOLDIER if self.current_player == CONST_CANNON else CONST_CANNON
        new_state.hash   = zh._hasher.c_switch_turn_hash(self.hash)
        new_state.winner = self.winner
        return new_state

    # ------------------------------------------------------------------
    # 对称性支持 (D4 对称群) - 委托到 board_ops + 缓存
    # ------------------------------------------------------------------
    @cython.boundscheck(False)
    @cython.wraparound(False)
    cpdef unsigned long long get_canonical_hash(self):
        """计算并缓存规范化哈希值（8 个对称变换中的最小值）。"""
        if self._has_canonical_hash:
            return self._cached_canonical_hash
        cdef unsigned long long h = c_canonical_hash(self.board_c, self.current_player)
        self._cached_canonical_hash = h
        self._has_canonical_hash = True
        return h

    # ------------------------------------------------------------------
    # 胜负判断 - 委托到 board_ops
    # ------------------------------------------------------------------
    cdef void _check_winner(self) noexcept nogil:
        self.winner = c_check_winner(self.board_c, self.soldier_count)

    # ------------------------------------------------------------------
    # 【Phase 2 重构】纯 C 原生走棋 (零分配返回值)
    # ------------------------------------------------------------------
    @cython.boundscheck(False)
    @cython.wraparound(False)
    cdef int c_move_piece(self, int start_idx, int end_idx) noexcept nogil:
        cdef int piece = self.board_c[start_idx]
        cdef int captured_piece = self.board_c[end_idx]

        self.board_c[end_idx]   = piece
        self.board_c[start_idx] = CONST_EMPTY

        if captured_piece == CONST_SOLDIER:
            self.soldier_count -= 1

        cdef unsigned long long h = self.hash
        h = zh._hasher.c_update_hash(h, start_idx // 5, start_idx % 5, end_idx // 5, end_idx % 5, piece)
        if captured_piece != CONST_EMPTY:
            h = zh._hasher.c_remove_piece_hash(h, end_idx // 5, end_idx % 5, captured_piece)
        h = zh._hasher.c_switch_turn_hash(h)
        self.hash = h

        self.current_player = CONST_SOLDIER if self.current_player == CONST_CANNON else CONST_CANNON
        self.winner = c_check_winner(self.board_c, self.soldier_count)

        return captured_piece

    @cython.boundscheck(False)
    @cython.wraparound(False)
    cdef void c_unmake_piece(self, int start_idx, int end_idx, int captured_piece, unsigned long long old_hash, int old_winner) noexcept nogil:
        cdef int piece = self.board_c[end_idx]
        
        self.board_c[start_idx] = piece
        self.board_c[end_idx]   = captured_piece
        
        if captured_piece == CONST_SOLDIER:
            self.soldier_count += 1
            
        self.hash = old_hash
        self.winner = old_winner
        self.current_player = CONST_SOLDIER if self.current_player == CONST_CANNON else CONST_CANNON

# ------------------------------------------------------------------
# 走法生成：委托到 board_ops.c_gen_moves
# ------------------------------------------------------------------
@cython.boundscheck(False)
@cython.wraparound(False)
cdef int c_get_ordered_moves(GameState state, int player_piece, int hash_move, int* out_moves) noexcept nogil:
    """委托到 board_ops.c_gen_moves，保持原有签名不变。"""
    return c_gen_moves(state.board_c, player_piece, hash_move, out_moves)
