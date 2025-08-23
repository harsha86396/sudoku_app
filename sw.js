// Service worker for offline functionality
const CACHE_NAME = 'sudoku-v1';
const urlsToCache = [
  '/',
  '/static/css/style.css',
  '/static/js/theme.js',
  '/static/js/sudoku.js',
  '/static/js/pwa.js',
  '/favicon.ico'
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
      .then(response => response || fetch(event.request))
  );
});
