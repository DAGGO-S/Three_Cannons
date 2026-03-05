# own_game/core/zobrist_hashing.pyx

# Cython imports
import cython
from cython cimport Py_ssize_t
import random

# 定义棋子类型常量
cdef int SOLDIER = 1
cdef int CANNON = 2
cdef int EMPTY = 0

# 定义棋子类型到索引的映射
cdef dict _PIECE_TO_INDEX = {EMPTY: -1, SOLDIER: 0, CANNON: 1}

# 在Python级别提供访问
PIECE_TO_INDEX = {EMPTY: -1, SOLDIER: 0, CANNON: 1}

@cython.boundscheck(False)
@cython.wraparound(False)
cdef class ZobristHasher:
    """优化的Zobrist哈希计算器 - Cython版本"""
    
    # 使用Python列表存储哈希表
    cdef object table
    cdef unsigned long long turn_key
    cdef int rows, cols
    
    def __init__(self, tuple board_size=(5, 5), int num_piece_types=2):
        """
        初始化Zobrist Hashing表。
        为棋盘的每个位置上的每种棋子生成一个独特的随机数。
        """
        cdef int r, c, p
        
        self.rows, self.cols = board_size
        
        # 使用Python列表创建哈希表
        self.table = [[[0 for _ in range(num_piece_types)] 
                       for _ in range(self.cols)] for _ in range(self.rows)]
        
        # 填充随机数
        for r in range(self.rows):
            for c in range(self.cols):
                for p in range(num_piece_types):
                    self.table[r][c][p] = random.getrandbits(64)
        
        self.turn_key = random.getrandbits(64)
    
    @cython.boundscheck(False)
    @cython.wraparound(False)
    def compute_hash(self, list board, int current_player):
        """从头计算整个棋盘的哈希值"""
        cdef unsigned long long h = 0
        cdef int r, c, piece, piece_index
        
        for r in range(self.rows):
            for c in range(self.cols):
                piece = board[r][c]
                if piece != EMPTY:
                    piece_index = _PIECE_TO_INDEX[piece]
                    h ^= self.table[r][c][piece_index]
        
        if current_player == CANNON:
            h ^= self.turn_key
            
        return h
    
    @cython.boundscheck(False)
    @cython.wraparound(False)
    def update_hash(self, unsigned long long old_hash, tuple move, int piece_type, int current_player):
        """
        增量更新哈希值，比从头计算更快
        move: (from_row, from_col, to_row, to_col)
        piece_type: 移动的棋子类型
        """
        cdef unsigned long long new_hash = old_hash
        cdef int from_row, from_col, to_row, to_col
        cdef int piece_index
        
        from_row, from_col, to_row, to_col = move
        piece_index = _PIECE_TO_INDEX[piece_type]
        
        # 移除原位置的棋子
        new_hash ^= self.table[from_row][from_col][piece_index]
        
        # 添加到新位置
        new_hash ^= self.table[to_row][to_col][piece_index]
        
        # 如果是炮方回合，需要考虑回合键
        if current_player == CANNON:
            new_hash ^= self.turn_key
            
        return new_hash
    
    @cython.boundscheck(False)
    @cython.wraparound(False)
    def place_piece_hash(self, unsigned long long old_hash, tuple position, int piece_type):
        """
        在指定位置放置棋子后的哈希值
        """
        cdef int row, col, piece_index
        row, col = position
        piece_index = _PIECE_TO_INDEX[piece_type]
        
        return old_hash ^ self.table[row][col][piece_index]
    
    @cython.boundscheck(False)
    @cython.wraparound(False)
    def remove_piece_hash(self, unsigned long long old_hash, tuple position, int piece_type):
        """
        从指定位置移除棋子后的哈希值
        """
        # 移除和放置棋子的操作是相同的，因为异或操作是可逆的
        return self.place_piece_hash(old_hash, position, piece_type)
    
    @cython.boundscheck(False)
    @cython.wraparound(False)
    def switch_turn_hash(self, unsigned long long old_hash):
        """
        切换回合后的哈希值
        """
        return old_hash ^ self.turn_key

# 创建一个全局唯一的hasher实例供其他模块使用
cdef ZobristHasher _hasher = ZobristHasher()

# 提供Python接口
def get_hasher():
    """获取全局哈希器实例"""
    return _hasher

def compute_board_hash(list board, int current_player):
    """计算棋盘哈希值的便捷函数"""
    return _hasher.compute_hash(board, current_player)

def update_board_hash(unsigned long long old_hash, tuple move, int piece_type, int current_player):
    """更新棋盘哈希值的便捷函数"""
    return _hasher.update_hash(old_hash, move, piece_type, current_player)