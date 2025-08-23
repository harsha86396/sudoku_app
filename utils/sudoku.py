
import random
from typing import List, Tuple

Board = List[List[int]]

def make_full_board() -> Board:
    base = 3
    side = base * base

    def pattern(r,c): return (base*(r%base)+r//base+c)%side
    def shuffle(s): return random.sample(s,len(s))
    rBase = range(base)
    rows  = [ g*base + r for g in shuffle(rBase) for r in shuffle(rBase) ]
    cols  = [ g*base + c for g in shuffle(rBase) for c in shuffle(rBase) ]
    nums  = shuffle(range(1,side+1))
    board = [ [nums[pattern(r,c)] for c in cols] for r in rows ]
    return board

def remove_cells(board: Board, holes: int) -> Board:
    side = 9
    puzzle = [row[:] for row in board]
    cells = [(r,c) for r in range(side) for c in range(side)]
    for (r,c) in random.sample(cells, holes):
        puzzle[r][c] = 0
    return puzzle

def make_puzzle(difficulty: str = "easy") -> Tuple[Board, Board]:
    board = make_full_board()
    diffs = {"easy": 38, "medium": 46, "hard": 54}
    holes = diffs.get(difficulty, 46)
    puzzle = remove_cells(board, holes)
    solution = board
    return puzzle, solution
