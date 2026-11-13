from dataclasses import dataclass
import random


@dataclass
class Cell:
    is_mine: bool = False
    is_revealed: bool = False
    is_flagged: bool = False
    neighbor_count: int = 0


class Board:
    def __init__(self, rows: int = 9, cols: int = 9, mines: int = 10):
        self.rows = rows
        self.cols = cols
        self.mines = mines
        self.reset()

    def reset(self):
        self.grid = [[Cell() for _ in range(self.cols)] for _ in range(self.rows)]
        self.mines_placed = False
        self.game_over = False
        self.won = False
        self.flags_used = 0
        self.revealed_count = 0
        self.safe_cells = self.rows * self.cols - self.mines

    def neighbors(self, r: int, c: int):
        for dr in (-1, 0, 1):
            for dc in (-1, 0, 1):
                if dr == 0 and dc == 0:
                    continue
                nr, nc = r + dr, c + dc
                if 0 <= nr < self.rows and 0 <= nc < self.cols:
                    yield nr, nc

    def place_mines(self, safe_r: int, safe_c: int):
        # The clicked cell and its neighbors can't hold mines
        forbidden = {(safe_r, safe_c), *self.neighbors(safe_r, safe_c)}
        positions = [
            (r, c)
            for r in range(self.rows)
            for c in range(self.cols)
            if (r, c) not in forbidden
        ]
        for r, c in random.sample(positions, self.mines):
            self.grid[r][c].is_mine = True

        self._count_neighbors()
        self.mines_placed = True

    def _count_neighbors(self):
        for r in range(self.rows):
            for c in range(self.cols):
                cell = self.grid[r][c]
                cell.neighbor_count = sum(
                    self.grid[nr][nc].is_mine for nr, nc in self.neighbors(r, c)
                )

    def reveal(self, r: int, c: int) -> list[tuple[int, int]]:
        """Reveal a cell. Returns the list of cells that were newly opened."""
        if self.game_over:
            return []

        cell = self.grid[r][c]
        if cell.is_revealed or cell.is_flagged:
            return []

        if not self.mines_placed:
            self.place_mines(r, c)

        if cell.is_mine:
            cell.is_revealed = True
            self.game_over = True
            self.won = False
            return [(r, c)]

        # Flood-fill with a stack
        opened = []
        stack = [(r, c)]
        while stack:
            cr, cc = stack.pop()
            current = self.grid[cr][cc]
            if current.is_revealed or current.is_flagged:
                continue
            current.is_revealed = True
            self.revealed_count += 1
            opened.append((cr, cc))
            if current.neighbor_count == 0:
                stack.extend(self.neighbors(cr, cc))

        if self.revealed_count >= self.safe_cells:
            self.game_over = True
            self.won = True
        return opened

    def toggle_flag(self, r: int, c: int):
        # No flags before the first click, none after the game ends
        if self.game_over or not self.mines_placed:
            return
        cell = self.grid[r][c]
        if cell.is_revealed:
            return
        cell.is_flagged = not cell.is_flagged
        self.flags_used += 1 if cell.is_flagged else -1

    def chord(self, r: int, c: int) -> list[tuple[int, int]]:
        """Open every hidden, unflagged neighbor of an opened number whose
        flag count matches it. Returns the newly opened cells."""
        if self.game_over:
            return []
        cell = self.grid[r][c]
        if not cell.is_revealed or cell.neighbor_count == 0:
            return []

        around = list(self.neighbors(r, c))
        flags = sum(self.grid[nr][nc].is_flagged for nr, nc in around)
        if flags != cell.neighbor_count:
            return []

        opened = []
        for nr, nc in around:
            target = self.grid[nr][nc]
            if target.is_revealed or target.is_flagged:
                continue
            opened.extend(self.reveal(nr, nc))
            if self.game_over:  # hit a mine (wrong flag) or just won
                break
        return opened