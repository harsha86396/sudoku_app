import random
import copy

def generate_sudoku(difficulty='medium'):
    board = [[0] * 9 for _ in range(9)]
    solve_sudoku(board)
    cells_to_remove = {'easy': 35, 'medium': 45, 'hard': 55}[difficulty]
    for _ in range(cells_to_remove):
        row, col = random.randint(0, 8), random.randint(0, 8)
        board[row][col] = 0
    solution = copy.deepcopy(board)
    return board, solution

def solve_sudoku(board):
    empty = find_empty(board)
    if not empty:
        return True
    row, col = empty
    numbers = list(range(1, 10))
    random.shuffle(numbers)
    for num in numbers:
        if is_valid_move(board, num, row, col):
            board[row][col] = num
            if solve_sudoku(board):
                return True
            board[row][col] = 0
    return False

def find_empty(board):
    for i in range(9):
        for j in range(9):
            if board[i][j] == 0:
                return i, j
    return None

def is_valid_move(board, num, row, col):
    for i in range(9):
        if board[row][i] == num or board[i][col] == num:
            return False
    start_row, start_col = 3 * (row // 3), 3 * (col // 3)
    for i in range(start_row, start_row + 3):
        for j in range(start_col, start_col + 3):
            if board[i][j] == num:
                return False
    return True
