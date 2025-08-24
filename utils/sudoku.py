# utils/sudoku.py
import random
import copy

def generate_sudoku(difficulty='medium'):
    """
    Generate a Sudoku puzzle of the specified difficulty.
    Returns a tuple of (puzzle, solution)
    """
    # Create a solved Sudoku board
    board = [[0] * 9 for _ in range(9)]
    solve_sudoku(board)
    
    # Create a copy for the puzzle
    puzzle = copy.deepcopy(board)
    
    # Remove numbers based on difficulty
    cells_to_remove = {
        'easy': random.randint(35, 40),
        'medium': random.randint(45, 50),
        'hard': random.randint(55, 60)
    }[difficulty]
    
    # Remove cells while ensuring the puzzle has a unique solution
    cells_removed = 0
    attempts = 0
    max_attempts = 200
    
    while cells_removed < cells_to_remove and attempts < max_attempts:
        row, col = random.randint(0, 8), random.randint(0, 8)
        
        # Skip if already empty
        if puzzle[row][col] == 0:
            attempts += 1
            continue
            
        # Store the value in case we need to put it back
        backup = puzzle[row][col]
        puzzle[row][col] = 0
        
        # Check if the puzzle still has a unique solution
        temp_puzzle = copy.deepcopy(puzzle)
        if not has_unique_solution(temp_puzzle):
            puzzle[row][col] = backup
            attempts += 1
        else:
            cells_removed += 1
            attempts = 0
    
    return puzzle, board

def solve_sudoku(board):
    """
    Solve the Sudoku board using backtracking.
    Returns True if solved, False otherwise.
    """
    empty = find_empty(board)
    if not empty:
        return True
        
    row, col = empty
    
    # Try numbers in random order for more variety
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
    """
    Find an empty cell in the board.
    Returns (row, col) or None if no empty cells.
    """
    for i in range(9):
        for j in range(9):
            if board[i][j] == 0:
                return i, j
    return None

def is_valid_move(board, num, row, col):
    """
    Check if placing num at (row, col) is valid.
    """
    # Check row
    for i in range(9):
        if board[row][i] == num:
            return False
            
    # Check column
    for i in range(9):
        if board[i][col] == num:
            return False
            
    # Check 3x3 box
    start_row, start_col = 3 * (row // 3), 3 * (col // 3)
    for i in range(start_row, start_row + 3):
        for j in range(start_col, start_col + 3):
            if board[i][j] == num:
                return False
                
    return True

def has_unique_solution(board):
    """
    Check if the Sudoku puzzle has exactly one solution.
    """
    # Create a copy to avoid modifying the original
    temp_board = copy.deepcopy(board)
    return count_solutions(temp_board) == 1

def count_solutions(board, count=0):
    """
    Count the number of solutions for the Sudoku puzzle.
    """
    # Limit the number of solutions to 2 for efficiency
    if count > 1:
        return count
        
    empty = find_empty(board)
    if not empty:
        return count + 1
        
    row, col = empty
    
    for num in range(1, 10):
        if is_valid_move(board, num, row, col):
            board[row][col] = num
            count = count_solutions(board, count)
            board[row][col] = 0
            
            if count > 1:
                break
                
    return count

def print_board(board):
    """
    Utility function to print the Sudoku board.
    """
    for i in range(9):
        if i % 3 == 0 and i != 0:
            print("- - - - - - - - - - -")
            
        for j in range(9):
            if j % 3 == 0 and j != 0:
                print("| ", end="")
                
            if j == 8:
                print(board[i][j])
            else:
                print(str(board[i][j]) + " ", end="")
