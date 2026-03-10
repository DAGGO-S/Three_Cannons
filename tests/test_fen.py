import pytest
from core.game_logic import GameState, CANNON, SOLDIER, EMPTY

def test_initial_board_fen():
    state = GameState()
    fen = state.to_fen()
    assert fen == "sssss/sssss/sssss/5/1ccc1 c"

def test_fen_roundtrip():
    fen_str = "sssss/sssss/sssss/5/1ccc1 c"
    state = GameState.from_fen(fen_str)
    assert state.current_player == CANNON
    assert state.to_fen() == fen_str

def test_fen_with_multiple_empty_chunks():
    # 测试有多个数字连断的序列，例如 s1s2/c2s1/ 等极端特例
    fen_str = "s1s2/1c1s1/5/3c1/5 s"
    state = GameState.from_fen(fen_str)
    assert state.current_player == SOLDIER
    board = state.board
    
    assert board[0] == (SOLDIER, EMPTY, SOLDIER, EMPTY, EMPTY)
    assert board[1] == (EMPTY, CANNON, EMPTY, SOLDIER, EMPTY)
    assert board[2] == (EMPTY, EMPTY, EMPTY, EMPTY, EMPTY)
    assert board[3] == (EMPTY, EMPTY, EMPTY, CANNON, EMPTY)
    assert board[4] == (EMPTY, EMPTY, EMPTY, EMPTY, EMPTY)
    
    assert state.to_fen() == fen_str

def test_invalid_fen_format():
    with pytest.raises(ValueError):
        GameState.from_fen("sssss/5/5 s extra")

    with pytest.raises(ValueError):
        GameState.from_fen("sssss/5/5/x/5 c")
