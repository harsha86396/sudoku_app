(function(){
  try {
    // Check for saved theme preference or use system preference
    const saved = localStorage.getItem('theme');
    const systemDark = window.matchMedia('(prefers-color-scheme: dark)').matches;
    
    // Apply theme based on preference
    if (saved === 'light') {
      document.documentElement.classList.add('light');
    } else if (saved === 'dark') {
      document.documentElement.classList.remove('light');
    } else if (systemDark) {
      // Use system preference if no saved preference
      document.documentElement.classList.remove('light');
    } else {
      document.documentElement.classList.add('light');
    }
    
    // Theme toggle function
    window.toggleTheme = function() {
      const isLight = document.documentElement.classList.toggle('light');
      localStorage.setItem('theme', isLight ? 'light' : 'dark');
      updateThemeName();
    }
    
    // Update theme name display
    function updateThemeName() {
      const themeNameEl = document.getElementById('theme-name');
      if (themeNameEl) {
        themeNameEl.textContent = document.documentElement.classList.contains('light') ? 'Light' : 'Dark';
      }
    }
    
    // Listen for system theme changes
    window.matchMedia('(prefers-color-scheme: dark)').addEventListener('change', e => {
      if (!localStorage.getItem('theme')) {
        if (e.matches) {
          document.documentElement.classList.remove('light');
        } else {
          document.documentElement.classList.add('light');
        }
        updateThemeName();
      }
    });
    
    // Initialize theme name
    updateThemeName();
  } catch(e) {
    console.error('Theme error:', e);
  }
})();
