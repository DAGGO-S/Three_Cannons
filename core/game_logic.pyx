# own_game/game_logic.pyx

from core.zobrist_hashing import get_hasher, PIECE_TO_INDEX

# Cython imports
import cython
from cython cimport Py_ssize_t

# 类型定义，让Cython生成更快的C代码
ctypedef Py_ssize_t cint
ctypedef bint cbool
ctypedef unsigned long long ULL

# 常量定义
EMPTY = 0
SOLDIER = 1
CANNON = 2
DRAW = 3  # 和棋状态
BOARD_ROWS = 5
BOARD_COLS = 5

# 获取全局哈希器实例
hasher = get_hasher()

# 使用 @cython.cclass 装饰器可以进一步提升性能
# 它将类实现为C结构体，但需要更严格的类型管理
# 为了保持兼容性，我们暂时不使用它，但这是未来的一个优化方向
class GameState:
    # 【P6优化】增加 soldiers/cannons 集合，避免每次评估都扫描棋盘
    __slots__ = ('board', 'current_player', 'winner', 'soldier_count', 'hash', 'soldiers', 'cannons')

    def __init__(self, board=None, current_player=CANNON):
        cdef cint r, c, s_count
        if board is None:
            self.board = [
                [1,1,1,1,1],[1,1,1,1,1],[1,1,1,1,1],[0,0,0,0,0],[0,2,2,2,0]
            ]
            self.soldier_count = 15
        else:
            self.board = board
            # 如果提供了棋盘，需要重新计算兵数
            s_count = 0
            for r in range(BOARD_ROWS):
                for c in range(BOARD_COLS):
                    if board[r][c] == SOLDIER:
                        s_count += 1
            self.soldier_count = s_count

        self.current_player = current_player
        self.winner = None
        
        # >>> 将列表转换为不可变的元组 <<<
        self.board = tuple(tuple(row) for row in self.board)
        
        # 【P6优化】初始化时构建 soldiers/cannons 集合
        self.soldiers = frozenset((r, c) for r in range(BOARD_ROWS) for c in range(BOARD_COLS) if self.board[r][c] == SOLDIER)
        self.cannons = frozenset((r, c) for r in range(BOARD_ROWS) for c in range(BOARD_COLS) if self.board[r][c] == CANNON)
        
        # 计算哈希值时需要使用列表
        board_for_hash = [list(row) for row in self.board]
        self.hash = <ULL>hasher.compute_hash(board_for_hash, self.current_player)
        
        # 检查是否有获胜者
        self._check_winner()


    @cython.boundscheck(False)
    @cython.wraparound(False)
    def is_within_bounds(self, r: cint, c: cint) -> cbool:
        return 0 <= r < BOARD_ROWS and 0 <= c < BOARD_COLS

    @cython.boundscheck(False)
    @cython.wraparound(False)
    def get_valid_moves(self, r: cint, c: cint):
        cdef cint piece = self.board[r][c]
        if piece == EMPTY: 
            return []
        
        moves = []
        cdef list directions = [(0,1),(0,-1),(1,0),(-1,0)]
        cdef cint dr, dc, tr, tc, jump_r, jump_c, target_r, target_c
        
        if piece == SOLDIER:
            for dr, dc in directions:
                tr, tc = r + dr, c + dc
                if self.is_within_bounds(tr,tc) and self.board[tr][tc] == EMPTY:
                    moves.append((tr, tc))

        elif piece == CANNON:
            # 规则1: 普通移动
            for dr, dc in directions:
                tr, tc = r + dr, c + dc
                if self.is_within_bounds(tr,tc) and self.board[tr][tc] == EMPTY:
                    moves.append((tr, tc))
            
            # 规则2: 隔空吃兵
            for dr, dc in directions:
                jump_r, jump_c = r + dr, c + dc
                target_r, target_c = r + 2 * dr, c + 2 * dc
                
                if (self.is_within_bounds(target_r, target_c) and 
                    self.is_within_bounds(jump_r, jump_c) and
                    self.board[jump_r][jump_c] == EMPTY and  
                    self.board[target_r][target_c] == SOLDIER): 
                    moves.append((target_r, target_c))
                    
        return moves

    @cython.boundscheck(False)
    @cython.wraparound(False)
    def move_piece(self, start_r: cint, start_c: cint, end_r: cint, end_c: cint):
        # 验证走法是否合法
        valid_moves = self.get_valid_moves(start_r, start_c)
        if (end_r, end_c) not in valid_moves:
            raise ValueError("Attempted to make an illegal move.")

        new_state = self.__class__.__new__(self.__class__)

        # >>> 先创建列表，修改后转回元组 <<<
        new_board_list = [list(row) for row in self.board]
        
        new_state.soldier_count = self.soldier_count
        
        cdef cint piece = new_board_list[start_r][start_c]
        cdef cint captured_piece = new_board_list[end_r][end_c]
        
        # 执行移动
        new_board_list[end_r][end_c] = piece
        new_board_list[start_r][start_c] = EMPTY
        
        # 将修改后的列表转换回元组
        new_state.board = tuple(tuple(row) for row in new_board_list)
        
        # 【P6优化】增量更新 soldiers/cannons 集合
        cdef set new_soldiers = set(self.soldiers)
        cdef set new_cannons = set(self.cannons)
        
        if piece == SOLDIER:
            new_soldiers.discard((start_r, start_c))
            new_soldiers.add((end_r, end_c))
        elif piece == CANNON:
            new_cannons.discard((start_r, start_c))
            new_cannons.add((end_r, end_c))
        
        if captured_piece == SOLDIER:
            new_soldiers.discard((end_r, end_c))
            new_state.soldier_count -= 1
        
        new_state.soldiers = frozenset(new_soldiers)
        new_state.cannons = frozenset(new_cannons)
        
        # 使用增量更新哈希值
        cdef ULL current_hash = self.hash
        
        # 移动棋子
        current_hash = hasher.update_hash(current_hash, (start_r, start_c, end_r, end_c), piece, self.current_player)
        
        # 如果有吃子，需要额外处理
        if captured_piece != EMPTY:
            current_hash = hasher.remove_piece_hash(current_hash, (end_r, end_c), captured_piece)
        
        # 切换回合
        current_hash = hasher.switch_turn_hash(current_hash)
        
        new_state.hash = current_hash

        new_state.current_player = SOLDIER if self.current_player == CANNON else CANNON
        new_state._check_winner()
        
        return new_state

    # 【P3】空着剪枝支持：只切换回合，不移动棋子
    def pass_turn(self):
        new_state = self.__class__.__new__(self.__class__)
        new_state.board = self.board
        new_state.soldier_count = self.soldier_count
        new_state.soldiers = self.soldiers
        new_state.cannons = self.cannons
        new_state.current_player = SOLDIER if self.current_player == CANNON else CANNON
        new_state.hash = hasher.switch_turn_hash(self.hash)
        new_state.winner = self.winner  # 棋盘未变，胜负不变
        return new_state

    @cython.boundscheck(False)
    @cython.wraparound(False)
    def _check_winner(self):
        if self.soldier_count == 0:
            self.winner = CANNON
            return

        cdef cint r, c
        for r in range(BOARD_ROWS):
            for c in range(BOARD_COLS):
                if self.board[r][c] == CANNON:
                    if self.get_valid_moves(r, c):
                        self.winner = None
                        return
        
        self.winner = SOLDIER