from game import Board


def make_board(rows, cols, mine_positions):
    """Build a board with mines in exact places (no randomness)."""
    board = Board(rows, cols, len(mine_positions))
    for r, c in mine_positions:
        board.grid[r][c].is_mine = True
    board._count_neighbors()
    board.mines_placed = True
    return board


def test_first_click_is_always_safe():
    for _ in range(200):
        board = Board(9, 9, 10)
        board.reveal(4, 4)

        assert not board.game_over
        assert board.grid[4][4].is_revealed
        assert not board.grid[4][4].is_mine
        # neighbors of the first click are mine-free too
        for nr, nc in board.neighbors(4, 4):
            assert not board.grid[nr][nc].is_mine


def test_correct_number_of_mines():
    board = Board(16, 16, 40)
    board.reveal(0, 0)
    total = sum(cell.is_mine for row in board.grid for cell in row)
    assert total == 40


def test_neighbor_counts():
    board = make_board(3, 3, [(0, 0)])
    assert board.grid[0][1].neighbor_count == 1
    assert board.grid[1][0].neighbor_count == 1
    assert board.grid[1][1].neighbor_count == 1
    assert board.grid[2][2].neighbor_count == 0


def test_flood_fill_opens_empty_area_and_wins():
    board = make_board(5, 5, [(0, 0)])
    board.reveal(4, 4)  # a "0" cell, so the empty area opens up

    assert board.grid[4][4].is_revealed
    assert board.grid[1][1].is_revealed
    assert not board.grid[0][0].is_revealed  # the mine stays hidden
    assert board.game_over and board.won  # every safe cell is open


def test_revealing_a_mine_loses():
    board = make_board(3, 3, [(0, 0)])
    board.reveal(0, 0)
    assert board.game_over
    assert not board.won


def test_flag_blocks_reveal_and_updates_counter():
    board = make_board(3, 3, [(0, 0)])

    board.toggle_flag(1, 1)
    assert board.flags_used == 1

    board.reveal(1, 1)
    assert not board.grid[1][1].is_revealed

    board.toggle_flag(1, 1)
    assert board.flags_used == 0


def test_win_by_revealing_all_safe_cells():
    board = make_board(2, 2, [(0, 0)])
    board.reveal(0, 1)
    board.reveal(1, 0)
    assert not board.game_over
    board.reveal(1, 1)
    assert board.game_over and board.won

def test_cannot_flag_before_first_click():
    board = Board(9, 9, 10)
    board.toggle_flag(0, 0)
    assert not board.grid[0][0].is_flagged
    assert board.flags_used == 0


def test_chord_opens_neighbors_when_flags_match():
    board = make_board(3, 3, [(0, 0)])
    board.reveal(1, 1)  # a "1"
    board.toggle_flag(0, 0)
    opened = board.chord(1, 1)
    assert len(opened) == 7
    assert board.game_over and board.won


def test_chord_does_nothing_without_matching_flags():
    board = make_board(3, 3, [(0, 0)])
    board.reveal(1, 1)
    assert board.chord(1, 1) == []
    assert not board.game_over


def test_chord_with_a_wrong_flag_loses():
    board = make_board(3, 3, [(0, 0)])
    board.reveal(1, 1)
    board.toggle_flag(2, 2)  # wrong place
    board.chord(1, 1)
    assert board.game_over and not board.won


def test_chord_on_hidden_cell_does_nothing():
    board = make_board(3, 3, [(0, 0)])
    assert board.chord(1, 1) == []