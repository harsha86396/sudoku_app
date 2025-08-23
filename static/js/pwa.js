// Register service worker for PWA functionality
if ('serviceWorker' in navigator) {
  window.addEventListener('load', () => {
    navigator.serviceWorker.register('/sw.js')
      .then(registration => {
        console.log('SW registered: ', registration);
      })
      .catch(registrationError => {
        console.log('SW registration failed: ', registrationError);
      });
  });
}

// Install prompt
let deferredPrompt;
window.addEventListener('beforeinstallprompt', (e) => {
  e.preventDefault();
  deferredPrompt = e;
  
  // Show install button
  const installButton = document.getElementById('installButton');
  const installLink = document.getElementById('installLink');
  
  if (installButton) {
    installButton.style.display = 'block';
    installButton.addEventListener('click', () => {
      deferredPrompt.prompt();
      deferredPrompt.userChoice.then(choiceResult => {
        if (choiceResult.outcome === 'accepted') {
          console.log('User accepted install');
        }
        deferredPrompt = null;
        installButton.style.display = 'none';
      });
    });
  }
  
  if (installLink) {
    installLink.style.display = 'inline';
    installLink.addEventListener('click', (e) => {
      e.preventDefault();
      deferredPrompt.prompt();
      deferredPrompt.userChoice.then(choiceResult => {
        if (choiceResult.outcome === 'accepted') {
          console.log('User accepted install');
        }
        deferredPrompt = null;
        installLink.style.display = 'none';
      });
    });
  }
});

// Function to manually prompt installation
window.promptInstall = function() {
  if (deferredPrompt) {
    deferredPrompt.prompt();
    deferredPrompt.userChoice.then(choiceResult => {
      if (choiceResult.outcome === 'accepted') {
        console.log('User accepted install');
      }
      deferredPrompt = null;
      
      const installButton = document.getElementById('installButton');
      const installLink = document.getElementById('installLink');
      if (installButton) installButton.style.display = 'none';
      if (installLink) installLink.style.display = 'none';
    });
  } else {
    alert('Installation is already available in your browser\'s menu or has been completed.');
  }
};

// Check if app is already installed
window.addEventListener('appinstalled', (evt) => {
  console.log('App was installed successfully');
  const installButton = document.getElementById('installButton');
  const installLink = document.getElementById('installLink');
  if (installButton) installButton.style.display = 'none';
  if (installLink) installLink.style.display = 'none';
});
