(function(){
  try {
    // Check for saved theme preference or use system preference
    const saved = localStorage.getItem('theme');
    const systemDark = window.matchMedia('(prefers-color-scheme: dark)').matches;
    
    if (saved === 'light' || (!saved && !systemDark)) {
      document.documentElement.classList.add('light');
    } else if (saved === 'dark' || (!saved && systemDark)) {
      document.documentElement.classList.remove('light');
    }
    
    window.toggleTheme = function() {
      const isLight = document.documentElement.classList.toggle('light');
      localStorage.setItem('theme', isLight ? 'light' : 'dark');
    }
    
    // Listen for system theme changes
    window.matchMedia('(prefers-color-scheme: dark)').addEventListener('change', e => {
      if (!localStorage.getItem('theme')) {
        if (e.matches) {
          document.documentElement.classList.remove('light');
        } else {
          document.documentElement.classList.add('light');
        }
      }
    });
  } catch(e) {
    console.error('Theme error:', e);
  }
})();
