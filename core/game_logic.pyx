# own_game/game_logic.pyx
# 【Phase3B】GameState 全面重构为 cdef class + C int[25] 数组

# cython: profile=True
from core.zobrist_hashing cimport ZobristHasher
from core.zobrist_hashing import get_hasher, PIECE_TO_INDEX
from libc.string cimport memcpy

# Cython imports
import cython
from cython cimport Py_ssize_t

# 常量定义
EMPTY = 0
SOLDIER = 1
CODE_CANNON = 2
CANNON = 2
DRAW = 3  # 和棋状态
BOARD_ROWS = 5
BOARD_COLS = 5

# winner 的整数语义：-1 = None（未结束）
cdef int NO_WINNER = -1

# 初始棋盘（开局布局，行主序 1D）
cdef int INITIAL_BOARD[25]
INITIAL_BOARD = [1,1,1,1,1, 1,1,1,1,1, 1,1,1,1,1, 0,0,0,0,0, 0,2,2,2,0]

# 获取全局哈希器实例，并声明为 C 级类型以实现内联调用
cdef ZobristHasher hasher = get_hasher()


@cython.boundscheck(False)
@cython.wraparound(False)
cdef class GameState:
    """【Phase3B】高性能 GameState：board 存储为 C int[25] 数组。

    字段声明在 game_logic.pxd 中，方法实现在此处。
    对外接口：
    - state.board          -> tuple-of-tuples（兼容 GUI/model 的只读访问）
    - state.winner         -> int  (-1=None, 0=DRAW, 1=SOLDIER, 2=CANNON)
    - state.current_player -> int
    - state.soldier_count  -> int
    - state.hash           -> unsigned long long
    """

    def __init__(self, board=None, current_player=CANNON):
        cdef int r, c, s_count, i, val
        self.winner = NO_WINNER

        if board is None:
            # 使用预定义的初始棋盘
            memcpy(self.board_c, INITIAL_BOARD, 25 * sizeof(int))
            self.soldier_count = 15
        else:
            # 从外部 board（list-of-lists 或 tuple-of-tuples）初始化
            s_count = 0
            for r in range(5):
                for c in range(5):
                    val = board[r][c]
                    self.board_c[r * 5 + c] = val
                    if val == SOLDIER:
                        s_count += 1
            self.soldier_count = s_count

        self.current_player = current_player

        # 计算初始哈希（使用 C 级内联方法，传递 C 数组指针）
        self.hash = hasher.c_compute_hash(self.board_c, self.current_player)

        # 检查胜负
        self._check_winner()

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
    # 走法生成
    # ------------------------------------------------------------------
    @cython.boundscheck(False)
    @cython.wraparound(False)
    def get_valid_moves(self, int r, int c):
        cdef int piece = self.board_c[r * 5 + c]
        if piece == EMPTY:
            return []

        cdef list moves = []
        cdef int dr, dc, tr, tc, jump_r, jump_c, target_r, target_c

        if piece == SOLDIER:
            for dr, dc in ((0,1),(0,-1),(1,0),(-1,0)):
                tr = r + dr
                tc = c + dc
                if 0 <= tr < 5 and 0 <= tc < 5 and self.board_c[tr * 5 + tc] == EMPTY:
                    moves.append((tr, tc))

        elif piece == CANNON:
            # 规则1: 普通移动
            for dr, dc in ((0,1),(0,-1),(1,0),(-1,0)):
                tr = r + dr
                tc = c + dc
                if 0 <= tr < 5 and 0 <= tc < 5 and self.board_c[tr * 5 + tc] == EMPTY:
                    moves.append((tr, tc))
            # 规则2: 隔空吃兵
            for dr, dc in ((0,1),(0,-1),(1,0),(-1,0)):
                jump_r = r + dr
                jump_c = c + dc
                target_r = r + 2 * dr
                target_c = c + 2 * dc
                if (0 <= target_r < 5 and 0 <= target_c < 5 and
                        0 <= jump_r < 5 and 0 <= jump_c < 5 and
                        self.board_c[jump_r * 5 + jump_c] == EMPTY and
                        self.board_c[target_r * 5 + target_c] == SOLDIER):
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
        if piece == SOLDIER:
            if (abs(dr) + abs(dc) == 1) and captured_piece == EMPTY:
                legal = True
        elif piece == CANNON:
            if (abs(dr) + abs(dc) == 1) and captured_piece == EMPTY:
                legal = True
            elif (abs(dr) == 2 or abs(dc) == 2) and (dr == 0 or dc == 0):
                jump_r = (start_r + end_r) // 2
                jump_c = (start_c + end_c) // 2
                if (self.board_c[jump_r * 5 + jump_c] == EMPTY and
                        captured_piece == SOLDIER):
                    legal = True

        if not legal:
            raise ValueError("Attempted to make an illegal move.")

        # 创建新状态（不调用 __init__，直接用 __new__）
        cdef GameState new_state = GameState.__new__(GameState)

        # 【Phase3B 核心】memcpy 整块棋盘，然后只改动两格
        memcpy(new_state.board_c, self.board_c, 25 * sizeof(int))

        # 执行移动（两个整数赋值）
        new_state.board_c[end_idx]   = piece
        new_state.board_c[start_idx] = EMPTY

        new_state.soldier_count = self.soldier_count
        if captured_piece == SOLDIER:
            new_state.soldier_count -= 1

        # 增量更新哈希（无 Python 调用的纯 C XOR）
        cdef unsigned long long h = self.hash
        h = hasher.c_update_hash(h, start_r, start_c, end_r, end_c, piece, self.current_player)
        if captured_piece != EMPTY:
            h = hasher.c_remove_piece_hash(h, end_r, end_c, captured_piece)
        h = hasher.c_switch_turn_hash(h)
        new_state.hash = h

        new_state.current_player = SOLDIER if self.current_player == CANNON else CANNON
        new_state.winner = NO_WINNER
        new_state._check_winner()

        return new_state

    # ------------------------------------------------------------------
    # 空着剪枝支持
    # ------------------------------------------------------------------
    def pass_turn(self):
        cdef GameState new_state = GameState.__new__(GameState)
        memcpy(new_state.board_c, self.board_c, 25 * sizeof(int))
        new_state.soldier_count  = self.soldier_count
        new_state.current_player = SOLDIER if self.current_player == CANNON else CANNON
        new_state.hash   = hasher.switch_turn_hash(self.hash)
        new_state.winner = self.winner
        return new_state

    # ------------------------------------------------------------------
    # 胜负判断
    # ------------------------------------------------------------------
    @cython.boundscheck(False)
    @cython.wraparound(False)
    cdef void _check_winner(self):
        if self.soldier_count == 0:
            self.winner = CANNON
            return

        # 炮只要有一个相邻空格就不被困
        cdef int r, c, tr, tc
        for r in range(5):
            for c in range(5):
                if self.board_c[r * 5 + c] == CANNON:
                    for tr, tc in ((r-1,c),(r+1,c),(r,c-1),(r,c+1)):
                        if 0 <= tr < 5 and 0 <= tc < 5 and self.board_c[tr * 5 + tc] == EMPTY:
                            self.winner = NO_WINNER
                            return

        self.winner = SOLDIER

    # ------------------------------------------------------------------
    # 【Phase 2 重构】纯 C 原生走棋 (零分配返回值)
    # ------------------------------------------------------------------
    @cython.boundscheck(False)
    @cython.wraparound(False)
    cdef int c_move_piece(self, int start_idx, int end_idx) noexcept:
        cdef int piece = self.board_c[start_idx]
        cdef int captured_piece = self.board_c[end_idx]
        
        self.board_c[end_idx]   = piece
        self.board_c[start_idx] = EMPTY
        
        if captured_piece == SOLDIER:
            self.soldier_count -= 1
            
        cdef unsigned long long h = self.hash
        h = hasher.c_update_hash(h, start_idx // 5, start_idx % 5, end_idx // 5, end_idx % 5, piece, self.current_player)
        if captured_piece != EMPTY:
            h = hasher.c_remove_piece_hash(h, end_idx // 5, end_idx % 5, captured_piece)
        h = hasher.c_switch_turn_hash(h)
        self.hash = h
        
        self.current_player = SOLDIER if self.current_player == CANNON else CANNON
        self.winner = NO_WINNER
        self._check_winner()
        
        return captured_piece

    @cython.boundscheck(False)
    @cython.wraparound(False)
    cdef void c_unmake_piece(self, int start_idx, int end_idx, int captured_piece, unsigned long long old_hash, int old_winner) noexcept:
        cdef int piece = self.board_c[end_idx]
        
        self.board_c[start_idx] = piece
        self.board_c[end_idx]   = captured_piece
        
        if captured_piece == SOLDIER:
            self.soldier_count += 1
            
        self.hash = old_hash
        self.winner = old_winner
        self.current_player = SOLDIER if self.current_player == CANNON else CANNON

# ------------------------------------------------------------------
# 【Phase 2 重构】纯 C 原生可排序走法生成 (零堆分配)
# ------------------------------------------------------------------
@cython.boundscheck(False)
@cython.wraparound(False)
cdef int c_get_ordered_moves(GameState state, int player_piece, int hash_move, int* out_moves) noexcept:
    """
    生成所有合法走法，直接写入预分配的 C 数组 out_moves 中。
    走法编码规则: move_encoded = (start_idx << 8) | end_idx
    返回生成的走法总数。排序：hash_move > 吃子 > 安静走子。
    """
    cdef int num_moves = 0
    cdef int captures[64]
    cdef int num_captures = 0
    cdef int quiets[64]
    cdef int num_quiets = 0
    cdef int i, r, c, start_idx, end_idx, dr, dc, nr, nc, jump_idx
    cdef int move_encoded
    
    # 1. 如果有 hash_move，先放置于首位
    if hash_move != -1:
        out_moves[num_moves] = hash_move
        num_moves += 1
        
    for start_idx in range(25):
        if state.board_c[start_idx] == player_piece:
            r = start_idx // 5
            c = start_idx % 5
            
            if player_piece == SOLDIER:
                for dr, dc in [(0,1), (0,-1), (1,0), (-1,0)]:
                    nr = r + dr
                    nc = c + dc
                    if 0 <= nr < 5 and 0 <= nc < 5:
                        end_idx = nr * 5 + nc
                        if state.board_c[end_idx] == EMPTY:
                            move_encoded = (start_idx << 8) | end_idx
                            if move_encoded == hash_move:
                                continue
                            quiets[num_quiets] = move_encoded
                            num_quiets += 1
            else: # CANNON
                for dr, dc in [(0,1), (0,-1), (1,0), (-1,0)]:
                    nr = r + dr
                    nc = c + dc
                    if 0 <= nr < 5 and 0 <= nc < 5:
                        end_idx = nr * 5 + nc
                        if state.board_c[end_idx] == EMPTY:
                            move_encoded = (start_idx << 8) | end_idx
                            if move_encoded == hash_move:
                                continue
                            quiets[num_quiets] = move_encoded
                            num_quiets += 1
                            
                    # 取 Jump 吃子
                    nr = r + 2*dr
                    nc = c + 2*dc
                    if 0 <= nr < 5 and 0 <= nc < 5:
                        jump_idx = (r + dr) * 5 + (c + dc)
                        if state.board_c[jump_idx] == EMPTY:
                            end_idx = nr * 5 + nc
                            if state.board_c[end_idx] == SOLDIER:
                                move_encoded = (start_idx << 8) | end_idx
                                if move_encoded == hash_move:
                                    continue
                                captures[num_captures] = move_encoded
                                num_captures += 1
                                
    # 追加 Captures
    for i in range(num_captures):
        out_moves[num_moves] = captures[i]
        num_moves += 1
    # 追加 Quiets
    for i in range(num_quiets):
        out_moves[num_moves] = quiets[i]
        num_moves += 1
        
    return num_moves
