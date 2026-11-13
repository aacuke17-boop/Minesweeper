"""Fair board generation: a logic solver that checks mine layouts.

The solver plays a board the way a careful human would, using only certain
deductions (a number that is already satisfied, a number that needs all of its
unknown neighbours, and comparisons between two overlapping numbers). A layout
that it can finish without ever guessing is a "fair" board.
"""

import random
import time
from functools import lru_cache


@lru_cache(maxsize=16)
def neighbor_table(rows: int, cols: int) -> tuple[tuple[int, ...], ...]:
    table = []
    for r in range(rows):
        for c in range(cols):
            table.append(
                tuple(
                    nr * cols + nc
                    for nr in range(max(0, r - 1), min(rows, r + 2))
                    for nc in range(max(0, c - 1), min(cols, c + 2))
                    if (nr, nc) != (r, c)
                )
            )
    return tuple(table)


def solve(rows: int, cols: int, mines, start: int):
    """Play the board with logic only, beginning with a click on `start`.

    mines: list of 0/1 per cell (row-major).
    Returns (unresolved, state): the number of safe cells logic could not
    open, and the final state list (0 unknown, 1 open, 2 known mine).
    """
    nb = neighbor_table(rows, cols)
    n = rows * cols
    counts = [sum(mines[j] for j in nb[i]) for i in range(n)]
    state = [0] * n
    frontier: set[int] = set()  # open numbers that still have unknown neighbors
    todo: list[int] = []  # numbers to re-check with the simple rule
    safe_left = n - sum(mines)

    def open_cells(first):
        nonlocal safe_left
        stack = list(first)
        while stack:
            j = stack.pop()
            if state[j] != 0:
                continue
            state[j] = 1
            safe_left -= 1
            if counts[j] == 0:
                stack.extend(nb[j])
            else:
                frontier.add(j)
                todo.append(j)
            # an opened cell changes what its numbered neighbors know
            for k in nb[j]:
                if state[k] == 1 and counts[k]:
                    todo.append(k)

    def mark_mines(cells):
        for j in cells:
            if state[j] == 0:
                state[j] = 2
                for k in nb[j]:
                    if state[k] == 1 and counts[k]:
                        todo.append(k)

    open_cells([start])

    while safe_left:
        # --- simple rule: a number that is already satisfied / needs all unknowns
        progress = False
        while todo:
            i = todo.pop()
            if state[i] != 1:
                continue
            unknown = []
            flagged = 0
            for j in nb[i]:
                s = state[j]
                if s == 0:
                    unknown.append(j)
                elif s == 2:
                    flagged += 1
            if not unknown:
                frontier.discard(i)
                continue
            need = counts[i] - flagged
            if need == 0:
                open_cells(unknown)
                progress = True
            elif need == len(unknown):
                mark_mines(unknown)
                progress = True
        if progress:
            continue

        # --- pair rule: compare two overlapping numbers
        cons = []
        by_cell: dict[int, list[int]] = {}
        for i in list(frontier):
            unknown = [j for j in nb[i] if state[j] == 0]
            if not unknown:
                frontier.discard(i)
                continue
            need = counts[i] - sum(1 for j in nb[i] if state[j] == 2)
            idx = len(cons)
            cons.append((frozenset(unknown), need))
            for j in unknown:
                by_cell.setdefault(j, []).append(idx)

        safe_found: set[int] = set()
        mine_found: set[int] = set()
        for a_idx, (sa, a) in enumerate(cons):
            seen = set()
            for j in sa:
                for b_idx in by_cell[j]:
                    if b_idx == a_idx or b_idx in seen:
                        continue
                    seen.add(b_idx)
                    sb, b = cons[b_idx]
                    inter = len(sa & sb)
                    only_b = sb - sa
                    if not only_b:
                        continue
                    only_a = len(sa) - inter
                    lo = b - min(a, inter)  # fewest mines that can be in only_b
                    hi = b - max(0, a - only_a)  # most mines that can be in only_b
                    if hi <= 0:
                        safe_found |= only_b
                    elif lo >= len(only_b):
                        mine_found |= only_b
        if not safe_found and not mine_found:
            break  # stuck: the rest needs a guess
        mark_mines(mine_found)
        open_cells(safe_found - mine_found)

    return safe_left, state


def make_layout(rows, cols, count, forbidden, rng):
    cells = [i for i in range(rows * cols) if i not in forbidden]
    mines = [0] * (rows * cols)
    for i in rng.sample(cells, count):
        mines[i] = 1
    return mines


def forbidden_zone(rows: int, cols: int, start: int) -> set[int]:
    """The first click and its neighbors never hold a mine."""
    return {start, *neighbor_table(rows, cols)[start]}


def generate(rows, cols, count, start, budget=0.3, max_tries=2000, rng=random):
    """Lay out mines so that logic alone (no guessing) can finish the board.

    Tries random layouts, keeps the first one the solver finishes, and falls
    back to the layout with the fewest cells left to guess when the time
    budget (seconds) runs out. Returns (mines, unresolved, tries).
    """
    forbidden = forbidden_zone(rows, cols, start)
    deadline = time.perf_counter() + budget
    best, best_left, tries = None, None, 0
    while tries < max_tries:
        tries += 1
        mines = make_layout(rows, cols, count, forbidden, rng)
        left, _ = solve(rows, cols, mines, start)
        if best is None or left < best_left:
            best, best_left = mines, left
        if left == 0 or time.perf_counter() > deadline:
            break
    return best, best_left, tries