import random

def make_puzzle(difficulty='medium'):
    # Simplified: Generate a fixed puzzle for consistency
    solution = [
        [5,3,4,6,7,8,9,1,2],
        [6,7,2,1,9,5,3,4,8],
        [1,9,8,3,4,2,5,6,7],
        [8,5,9,7,6,1,4,2,3],
        [4,2,6,8,5,3,7,9,1],
        [7,1,3,9,2,4,8,5,6],
        [9,6,1,5,3,7,2,8,4],
        [2,8,7,4,1,9,6,3,5],
        [3,4,5,2,8,6,1,7,9]
    ]
    puzzle = [row[:] for row in solution]
    # Remove numbers based on difficulty
    cells_to_remove = {'easy': 30, 'medium': 40, 'hard': 50}[difficulty]
    cells = [(r, c) for r in range(9) for c in range(9)]
    random.shuffle(cells)
    for r, c in cells[:cells_to_remove]:
        puzzle[r][c] = 0
    return puzzle, solution
