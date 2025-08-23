import random

def valid(grid, r, c, n):
    for i in range(9):
        if grid[r][i] == n: return False
        if grid[i][c] == n: return False
    br, bc = 3*(r//3), 3*(c//3)
    for i in range(br, br+3):
        for j in range(bc, bc+3):
            if grid[i][j] == n: return False
    return True

def find_empty(grid):
    for r in range(9):
        for c in range(9):
            if grid[r][c] == 0:
                return r, c
    return None

def solve(grid):
    pos = find_empty(grid)
    if not pos: return True
    r, c = pos
    nums = list(range(1,10)); random.shuffle(nums)
    for n in nums:
        if valid(grid, r, c, n):
            grid[r][c] = n
            if solve(grid): return True
            grid[r][c] = 0
    return False

def generate_full():
    g = [[0]*9 for _ in range(9)]
    solve(g); return g

def copy_grid(g): return [row[:] for row in g]

def count_solutions(grid):
    count = 0
    def backtrack(g):
        nonlocal count
        if count > 1: return
        pos = find_empty(g)
        if not pos:
            count += 1; return
        r,c = pos
        for n in range(1,10):
            if valid(g,r,c,n):
                g[r][c] = n
                backtrack(g)
                g[r][c] = 0
    backtrack([row[:] for row in grid])
    return count

def make_puzzle(difficulty="medium"):
    full = generate_full()
    puzzle = copy_grid(full)
    removals = {
        "easy": random.randint(35,41),
        "medium": random.randint(42,49),
        "hard": random.randint(50,55)
    }.get(difficulty, 42)
    cells = [(r,c) for r in range(9) for c in range(9)]
    random.shuffle(cells)
    removed = 0
    for r,c in cells:
        if removed >= removals: break
        keep = puzzle[r][c]; puzzle[r][c] = 0
        if count_solutions([row[:] for row in puzzle]) != 1:
            puzzle[r][c] = keep
        else:
            removed += 1
    return puzzle, full
