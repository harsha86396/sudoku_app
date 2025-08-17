(function(){
  try{
    const saved = localStorage.getItem('theme') || 'dark';
    if(saved==='light') document.documentElement.classList.add('light');
    window.toggleTheme = function(){
      const isLight = document.documentElement.classList.toggle('light');
      localStorage.setItem('theme', isLight ? 'light' : 'dark');
    }
  }catch(e){}
})();
