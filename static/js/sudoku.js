// Enhanced Sudoku game JavaScript with 3x3 grid styling
function drawBoard() {
  const board = document.getElementById('board');
  board.innerHTML = '';
  
  // Create the 3x3 container grid
  for (let boxRow = 0; boxRow < 3; boxRow++) {
    for (let boxCol = 0; boxCol < 3; boxCol++) {
      const box = document.createElement('div');
      box.className = 'sudoku-box';
      box.style.display = 'grid';
      box.style.gridTemplateColumns = 'repeat(3, 1fr)';
      box.style.gap = '2px';
      box.style.border = '2px solid var(--muted)';
      box.style.padding = '2px';
      
      // Fill the box with cells
      for (let r = 0; r < 3; r++) {
        for (let c = 0; c < 3; c++) {
          const cellRow = boxRow * 3 + r;
          const cellCol = boxCol * 3 + c;
          const cell = makeCell(cellRow, cellCol, puzzle[cellRow][cellCol], original[cellRow][cellCol] !== 0);
          box.appendChild(cell);
        }
      }
      
      board.appendChild(box);
    }
  }
}

// Update CSS for the new layout
[file name]: static/css/style.css
```css
/* Add to existing CSS */
.sudoku-container {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 8px;
  max-width: 500px;
  margin: 0 auto;
}

.sudoku-box {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 1px;
  border: 2px solid var(--muted);
  padding: 2px;
  background-color: var(--muted);
}

.cell {
  width: 100%;
  aspect-ratio: 1;
  background: var(--cell);
  display: flex;
  align-items: center;
  justify-content: center;
  font-weight: 700;
  font-size: 1.2rem;
  user-select: none;
  border: 1px solid var(--muted);
}

/* Responsive design */
@media (max-width: 600px) {
  .sudoku-container {
    grid-template-columns: 1fr;
    max-width: 300px;
  }
  
  .cell {
    font-size: 1rem;
  }
}

/* System preference based theme */
@media (prefers-color-scheme: light) {
  :root:not(.dark) {
    --bg: #f5f7fb;
    --panel: #ffffff;
    --text: #0f172a;
    --accent: #16a34a;
    --muted: #4b5563;
    --danger: #b91c1c;
    --cell: #eef2ff;
    --link: #0369a1;
  }
}

@media (prefers-color-scheme: dark) {
  :root:not(.light) {
    --bg: #0f172a;
    --panel: #111827;
    --text: #e5e7eb;
    --accent: #22c55e;
    --muted: #94a3b8;
    --danger: #ef4444;
    --cell: #0b1220;
    --link: #38bdf8;
  }
}
