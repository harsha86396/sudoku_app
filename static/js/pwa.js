// static/js/pwa.js
// Register service worker for PWA functionality
if ('serviceWorker' in navigator) {
    window.addEventListener('load', () => {
        navigator.serviceWorker.register('/sw.js')
            .then((registration) => {
                console.log('SW registered: ', registration);
                
                // Check for updates
                registration.addEventListener('updatefound', () => {
                    const newWorker = registration.installing;
                    console.log('New service worker found:', newWorker);
                    
                    newWorker.addEventListener('statechange', () => {
                        if (newWorker.state === 'installed' && navigator.serviceWorker.controller) {
                            showUpdateNotification();
                        }
                    });
                });
            })
            .catch((registrationError) => {
                console.log('SW registration failed: ', registrationError);
            });
    });
}

// Handle app installation
let deferredPrompt;
const installButton = document.getElementById('install-btn');

window.addEventListener('beforeinstallprompt', (e) => {
    // Prevent the mini-infobar from appearing on mobile
    e.preventDefault();
    // Stash the event so it can be triggered later
    deferredPrompt = e;
    // Show the install button if it exists
    if (installButton) {
        installButton.style.display = 'block';
        installButton.addEventListener('click', installApp);
    }
    
    // Also show install prompt in menu
    showInstallPrompt();
});

function installApp() {
    if (!deferredPrompt) return;
    
    // Show the install prompt
    deferredPrompt.prompt();
    
    // Wait for the user to respond to the prompt
    deferredPrompt.userChoice.then((choiceResult) => {
        if (choiceResult.outcome === 'accepted') {
            console.log('User accepted the install prompt');
            trackEvent('pwa', 'install', 'accepted');
        } else {
            console.log('User dismissed the install prompt');
            trackEvent('pwa', 'install', 'dismissed');
        }
        deferredPrompt = null;
        
        // Hide the install button
        if (installButton) {
            installButton.style.display = 'none';
        }
        
        hideInstallPrompt();
    });
}

// Check if app is running in standalone mode
function isRunningStandalone() {
    return window.matchMedia('(display-mode: standalone)').matches || 
           window.navigator.standalone === true;
}

// If running in standalone mode, hide browser UI elements
if (isRunningStandalone()) {
    document.documentElement.classList.add('standalone');
    
    // Add standalone-specific styles
    const style = document.createElement('style');
    style.textContent = `
        .standalone header {
            padding-top: env(safe-area-inset-top);
        }
        .standalone .nav-links {
            margin-bottom: env(safe-area-inset-bottom);
        }
    `;
    document.head.appendChild(style);
}

// Show install prompt in the app menu
function showInstallPrompt() {
    // Create install prompt element if it doesn't exist
    if (!document.getElementById('install-prompt')) {
        const prompt = document.createElement('div');
        prompt.id = 'install-prompt';
        prompt.innerHTML = `
            <div style="padding: 1rem; background: #f0f9ff; border: 1px solid #bae6fd; border-radius: 0.5rem; margin: 1rem 0;">
                <h3>📱 Install Sudoku App</h3>
                <p>Install our app for a better experience and offline play!</p>
                <button onclick="installApp()" class="btn" style="margin-right: 0.5rem;">Install Now</button>
                <button onclick="hideInstallPrompt()" class="btn btn-outline">Not Now</button>
            </div>
        `;
        
        // Add to the top of the main content
        const main = document.querySelector('main');
        if (main) {
            main.insertBefore(prompt, main.firstChild);
        }
    }
}

function hideInstallPrompt() {
    const prompt = document.getElementById('install-prompt');
    if (prompt) {
        prompt.style.display = 'none';
    }
}

// Show update notification
function showUpdateNotification() {
    const notification = document.createElement('div');
    notification.innerHTML = `
        <div style="position: fixed; bottom: 20px; right: 20px; background: white; padding: 1rem; border-radius: 0.5rem; box-shadow: 0 4px 12px rgba(0,0,0,0.15); z-index: 1000; max-width: 300px;">
            <h4>Update Available</h4>
            <p>A new version of the app is available.</p>
            <button onclick="window.location.reload()" class="btn">Update Now</button>
            <button onclick="this.parentElement.style.display='none'" class="btn btn-outline">Later</button>
        </div>
    `;
    document.body.appendChild(notification);
}

// Track PWA events
function trackEvent(category, action, label) {
    if ('gtag' in window) {
        gtag('event', action, {
            'event_category': category,
            'event_label': label
        });
    }
}

// Handle online/offline status
window.addEventListener('online', () => {
    showNotification('You are back online!', 'success');
});

window.addEventListener('offline', () => {
    showNotification('You are offline. Some features may not work.', 'warning');
});

function showNotification(message, type = 'info') {
    // Create notification element
    const notification = document.createElement('div');
    notification.style.cssText = `
        position: fixed;
        top: 20px;
        right: 20px;
        padding: 1rem;
        border-radius: 0.5rem;
        color: white;
        z-index: 1000;
        max-width: 300px;
        animation: slideIn 0.3s ease;
    `;
    
    notification.style.background = type === 'success' ? '#22c55e' : 
                                  type === 'warning' ? '#f59e0b' : '#3b82f6';
    
    notification.textContent = message;
    document.body.appendChild(notification);
    
    // Remove after 3 seconds
    setTimeout(() => {
        notification.style.animation = 'slideOut 0.3s ease';
        setTimeout(() => notification.remove(), 300);
    }, 3000);
}

// Add CSS animations
const style = document.createElement('style');
style.textContent = `
    @keyframes slideIn {
        from { transform: translateX(100%); opacity: 0; }
        to { transform: translateX(0); opacity: 1; }
    }
    
    @keyframes slideOut {
        from { transform: translateX(0); opacity: 1; }
        to { transform: translateX(100%); opacity: 0; }
    }
`;
document.head.appendChild(style);
