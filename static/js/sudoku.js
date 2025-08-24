// static/js/sudoku.js
class SudokuGame {
    constructor() {
        this.board = Array(9).fill().map(() => Array(9).fill(0));
        this.solution = Array(9).fill().map(() => Array(9).fill(0));
        this.startTime = null;
        this.timerInterval = null;
        this.selectedCell = null;
        this.difficulty = 'medium';
        this.errors = new Set();
        this.init();
    }

    init() {
        this.setupEventListeners();
        this.loadNewPuzzle();
        this.updateTimer();
        this.setupKeyboardNavigation();
    }

    setupEventListeners() {
        // Number input
        document.querySelectorAll('.number-btn').forEach(btn => {
            btn.addEventListener('click', (e) => {
                if (this.selectedCell) {
                    const num = parseInt(e.target.dataset.num);
                    this.setCellValue(num);
                    this.updateNumberPad();
                }
            });
        });

        // Cell selection
        document.getElementById('sudoku-board').addEventListener('click', (e) => {
            if (e.target.classList.contains('sudoku-cell')) {
                this.selectCell(e.target);
                this.updateNumberPad();
            }
        });

        // Clear button
        document.getElementById('clear-btn').addEventListener('click', () => {
            if (this.selectedCell && !this.selectedCell.classList.contains('fixed')) {
                this.setCellValue(0);
                this.updateNumberPad();
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

        // New game button
        document.getElementById('new-game-btn').addEventListener('click', () => {
            this.loadNewPuzzle();
        });

        // Difficulty selection
        document.getElementById('difficulty-select').addEventListener('change', (e) => {
            this.difficulty = e.target.value;
            this.loadNewPuzzle();
        });
    }

    setupKeyboardNavigation() {
        document.addEventListener('keydown', (e) => {
            if (!this.selectedCell) return;

            const key = e.key;
            
            // Number input
            if (key >= '1' && key <= '9') {
                this.setCellValue(parseInt(key));
                this.updateNumberPad();
            }
            
            // Clear cell
            if (key === '0' || key === 'Backspace' || key === 'Delete') {
                if (!this.selectedCell.classList.contains('fixed')) {
                    this.setCellValue(0);
                    this.updateNumberPad();
                }
            }
            
            // Navigation
            if (key === 'ArrowUp' || key === 'ArrowDown' || key === 'ArrowLeft' || key === 'ArrowRight') {
                this.navigateBoard(key);
            }
        });
    }

    navigateBoard(direction) {
        if (!this.selectedCell) return;
        
        const row = parseInt(this.selectedCell.dataset.row);
        const col = parseInt(this.selectedCell.dataset.col);
        let newRow = row;
        let newCol = col;
        
        switch (direction) {
            case 'ArrowUp': newRow = Math.max(0, row - 1); break;
            case 'ArrowDown': newRow = Math.min(8, row + 1); break;
            case 'ArrowLeft': newCol = Math.max(0, col - 1); break;
            case 'ArrowRight': newCol = Math.min(8, col + 1); break;
        }
        
        const newCell = document.querySelector(`.sudoku-cell[data-row="${newRow}"][data-col="${newCol}"]`);
        if (newCell) {
            this.selectCell(newCell);
        }
    }

    selectCell(cell) {
        // Remove previous selection
        if (this.selectedCell) {
            this.selectedCell.classList.remove('selected');
        }
        
        // Set new selection
        this.selectedCell = cell;
        cell.classList.add('selected');
        
        // Scroll cell into view on mobile
        if (window.innerWidth < 768) {
            cell.scrollIntoView({ behavior: 'smooth', block: 'center', inline: 'center' });
        }
    }

    setCellValue(value) {
        if (!this.selectedCell || this.selectedCell.classList.contains('fixed')) return;
        
        const row = parseInt(this.selectedCell.dataset.row);
        const col = parseInt(this.selectedCell.dataset.col);
        
        // Clear error state
        this.selectedCell.classList.remove('error');
        this.errors.delete(`${row}-${col}`);
        
        this.selectedCell.textContent = value === 0 ? '' : value;
        this.board[row][col] = value;
        
        // Validate move
        if (value !== 0 && this.solution[row][col] !== value) {
            this.selectedCell.classList.add('error');
            this.errors.add(`${row}-${col}`);
        }
        
        // Check if puzzle is complete
        if (this.isComplete()) {
            this.stopTimer();
            this.showCompletionMessage();
        }
    }

    updateNumberPad() {
        // Update number pad active state based on selected cell
        document.querySelectorAll('.number-btn').forEach(btn => {
            btn.classList.remove('active');
        });
        
        if (this.selectedCell && !this.selectedCell.classList.contains('fixed')) {
            const value = this.selectedCell.textContent;
            if (value) {
                const activeBtn = document.querySelector(`.number-btn[data-num="${value}"]`);
                if (activeBtn) {
                    activeBtn.classList.add('active');
                }
            }
        }
    }

    async loadNewPuzzle() {
        try {
            // Show loading state
            const newGameBtn = document.getElementById('new-game-btn');
            const originalText = newGameBtn.textContent;
            newGameBtn.innerHTML = '<span class="loading"></span> Loading...';
            newGameBtn.disabled = true;
            
            const response = await fetch(`/api/new_puzzle?difficulty=${this.difficulty}`);
            const data = await response.json();
            
            if (data.error) {
                alert('Error loading puzzle: ' + data.error);
                return;
            }
            
            this.board = data.puzzle;
            this.solution = data.solution;
            this.errors.clear();
            this.renderBoard();
            this.startTimer();
            
            // Reset button state
            newGameBtn.textContent = originalText;
            newGameBtn.disabled = false;
            
        } catch (error) {
            console.error('Error loading puzzle:', error);
            alert('Failed to load puzzle. Please try again.');
            
            // Reset button state even on error
            const newGameBtn = document.getElementById('new-game-btn');
            newGameBtn.textContent = 'New Game';
            newGameBtn.disabled = false;
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
                
                // Add error class if this cell has an error
                if (this.errors.has(`${i}-${j}`)) {
                    cell.classList.add('error');
                }
                
                // Add thicker borders for 3x3 boxes
                if (i % 3 === 2 && i < 8) cell.style.borderBottom = '2px solid var(--border)';
                if (j % 3 === 2 && j < 8) cell.style.borderRight = '2px solid var(--border)';
                
                container.appendChild(cell);
            }
        }
        
        this.selectedCell = null;
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
            const hintBtn = document.getElementById('hint-btn');
            const originalText = hintBtn.textContent;
            hintBtn.innerHTML = '<span class="loading"></span>';
            hintBtn.disabled = true;
            
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
            
            // Reset button state
            hintBtn.textContent = originalText;
            hintBtn.disabled = false;
            
        } catch (error) {
            console.error('Error getting hint:', error);
            alert('Failed to get hint. Please try again.');
            
            // Reset button state even on error
            const hintBtn = document.getElementById('hint-btn');
            hintBtn.textContent = 'Hint';
            hintBtn.disabled = false;
        }
    }

    checkSolution() {
        let hasErrors = false;
        
        for (let i = 0; i < 9; i++) {
            for (let j = 0; j < 9; j++) {
                const cell = document.querySelector(`.sudoku-cell[data-row="${i}"][data-col="${j}"]`);
                if (cell && !cell.classList.contains('fixed')) {
                    if (this.board[i][j] !== this.solution[i][j]) {
                        cell.classList.add('error');
                        hasErrors = true;
                    } else {
                        cell.classList.remove('error');
                    }
                }
            }
        }
        
        if (hasErrors) {
            alert('There are errors in your solution. Keep trying!');
        } else {
            alert('Congratulations! Your solution is correct!');
        }
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
        const minutes = Math.floor(elapsed / 60);
        const seconds = elapsed % 60;
        const timeString = `${minutes.toString().padStart(2, '0')}:${seconds.toString().padStart(2, '0')}`;
        
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
                alert(`Completed in ${timeString}! ${data.error}`);
            } else {
                alert(`Congratulations! Completed in ${timeString}! Your best time: ${data.best_time}s. Rank: ${data.rank}`);
            }
            
        } catch (error) {
            console.error('Error recording result:', error);
            alert(`Completed in ${timeString}! (Error saving result)`);
        }
    }
}

// Initialize game when page loads
document.addEventListener('DOMContentLoaded', () => {
    window.sudokuGame = new SudokuGame();
});
