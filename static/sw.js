// Service worker for offline functionality
const CACHE_NAME = 'sudoku-v1';
const urlsToCache = [
  '/',
  '/static/css/style.css',
  '/static/js/theme.js',
  '/static/js/sudoku.js',
  '/static/js/pwa.js',
  '/static/icon-192.png',
  '/static/icon-512.png',
  '/manifest.json'
];

self.addEventListener('install', event => {
  event.waitUntil(
    caches.open(CACHE_NAME)
      .then(cache => cache.addAll(urlsToCache))
  );
});

self.addEventListener('fetch', event => {
  event.respondWith(
    caches.match(event.request)
      .then(response => {
        // Return cached version or fetch from network
        return response || fetch(event.request);
      })
  );
});

self.addEventListener('activate', event => {
  event.waitUntil(
    caches.keys().then(cacheNames => {
      return Promise.all(
        cacheNames.map(cacheName => {
          if (cacheName !== CACHE_NAME) {
            return caches.delete(cacheName);
          }
        })
      );
    })
  );
});
