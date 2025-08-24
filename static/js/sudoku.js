// static/js/sudoku.js
class SudokuGame {
    constructor() {
        this.board = Array(9).fill().map(() => Array(9).fill(0));
        this.solution = Array(9).fill().map(() => Array(9).fill(0));
        this.startTime = null;
        this.timerInterval = null;
        this.selectedCell = null;
        this.difficulty = 'medium';
        this.init();
    }

    init() {
        this.setupEventListeners();
        this.loadNewPuzzle();
        this.updateTimer();
    }

    setupEventListeners() {
        // Number input
        document.querySelectorAll('.number-btn').forEach(btn => {
            btn.addEventListener('click', (e) => {
                if (this.selectedCell) {
                    this.setCellValue(parseInt(e.target.dataset.num));
                }
            });
        });

        // Cell selection
        document.querySelectorAll('.sudoku-cell').forEach(cell => {
            cell.addEventListener('click', (e) => {
                this.selectCell(e.target);
            });
        });

        // Clear button
        document.getElementById('clear-btn').addEventListener('click', () => {
            if (this.selectedCell && !this.selectedCell.classList.contains('fixed')) {
                this.setCellValue(0);
            }
        });

        // Hint button
        document.getElementById('hint-btn').addEventListener('click', () => {
            this.getHint();
        });

        // Check button
        document.getElementById('check-btn').addEventListener('click', () => {
            this.checkSolution();
        });

        // New game buttons
        document.querySelectorAll('.difficulty-btn').forEach(btn => {
            btn.addEventListener('click', (e) => {
                this.difficulty = e.target.dataset.diff;
                this.loadNewPuzzle();
            });
        });
    }

    selectCell(cell) {
        // Remove previous selection
        if (this.selectedCell) {
            this.selectedCell.classList.remove('selected');
        }
        
        // Set new selection
        this.selectedCell = cell;
        cell.classList.add('selected');
    }

    setCellValue(value) {
        if (!this.selectedCell || this.selectedCell.classList.contains('fixed')) return;
        
        const row = parseInt(this.selectedCell.dataset.row);
        const col = parseInt(this.selectedCell.dataset.col);
        
        this.selectedCell.textContent = value === 0 ? '' : value;
        this.board[row][col] = value;
        
        // Check if puzzle is complete
        if (this.isComplete()) {
            this.stopTimer();
            this.showCompletionMessage();
        }
    }

    async loadNewPuzzle() {
        try {
            const response = await fetch(`/api/new_puzzle?difficulty=${this.difficulty}`);
            const data = await response.json();
            
            if (data.error) {
                alert('Error loading puzzle: ' + data.error);
                return;
            }
            
            this.board = data.puzzle;
            this.solution = data.solution;
            this.renderBoard();
            this.startTimer();
            
        } catch (error) {
            console.error('Error loading puzzle:', error);
            alert('Failed to load puzzle. Please try again.');
        }
    }

    renderBoard() {
        const container = document.getElementById('sudoku-board');
        container.innerHTML = '';
        
        for (let i = 0; i < 9; i++) {
            for (let j = 0; j < 9; j++) {
                const cell = document.createElement('div');
                cell.className = 'sudoku-cell';
                cell.dataset.row = i;
                cell.dataset.col = j;
                
                if (this.board[i][j] !== 0) {
                    cell.textContent = this.board[i][j];
                    cell.classList.add('fixed');
                }
                
                // Add thicker borders for 3x3 boxes
                if (i % 3 === 2 && i < 8) cell.style.borderBottom = '2px solid #000';
                if (j % 3 === 2 && j < 8) cell.style.borderRight = '2px solid #000';
                
                container.appendChild(cell);
            }
        }
        
        // Reattach event listeners
        document.querySelectorAll('.sudoku-cell').forEach(cell => {
            cell.addEventListener('click', (e) => {
                this.selectCell(e.target);
            });
        });
    }

    startTimer() {
        this.stopTimer();
        this.startTime = new Date();
        this.timerInterval = setInterval(() => {
            this.updateTimer();
        }, 1000);
    }

    stopTimer() {
        if (this.timerInterval) {
            clearInterval(this.timerInterval);
            this.timerInterval = null;
        }
    }

    updateTimer() {
        if (!this.startTime) return;
        
        const elapsed = Math.floor((new Date() - this.startTime) / 1000);
        const minutes = Math.floor(elapsed / 60);
        const seconds = elapsed % 60;
        
        document.getElementById('timer').textContent = 
            `${minutes.toString().padStart(2, '0')}:${seconds.toString().padStart(2, '0')}`;
    }

    async getHint() {
        try {
            const response = await fetch('/api/hint', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json'
                }
            });
            
            const data = await response.json();
            
            if (data.error) {
                alert('Error: ' + data.error);
                return;
            }
            
            // Update the board with the hint
            this.board[data.r][data.c] = data.val;
            this.renderBoard();
            
            // Update hints counter
            document.getElementById('hints-count').textContent = data.hints_left;
            
        } catch (error) {
            console.error('Error getting hint:', error);
            alert('Failed to get hint. Please try again.');
        }
    }

    checkSolution() {
        for (let i = 0; i < 9; i++) {
            for (let j = 0; j < 9; j++) {
                if (this.board[i][j] !== this.solution[i][j]) {
                    alert('There are errors in your solution. Keep trying!');
                    return;
                }
            }
        }
        alert('Congratulations! Your solution is correct!');
    }

    isComplete() {
        for (let i = 0; i < 9; i++) {
            for (let j = 0; j < 9; j++) {
                if (this.board[i][j] === 0 || this.board[i][j] !== this.solution[i][j]) {
                    return false;
                }
            }
        }
        return true;
    }

    async showCompletionMessage() {
        const elapsed = Math.floor((new Date() - this.startTime) / 1000);
        
        try {
            const response = await fetch('/api/record_result', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify({ seconds: elapsed })
            });
            
            const data = await response.json();
            
            if (data.error) {
                alert(`Completed in ${elapsed} seconds! ${data.error}`);
            } else {
                alert(`Congratulations! Completed in ${elapsed} seconds! Your best time: ${data.best_time}s. Rank: ${data.rank}`);
            }
            
        } catch (error) {
            console.error('Error recording result:', error);
            alert(`Completed in ${elapsed} seconds! (Error saving result)`);
        }
    }
}

// Initialize game when page loads
document.addEventListener('DOMContentLoaded', () => {
    window.sudokuGame = new SudokuGame();
});
