// Service Worker for FaceID Portal PWA
// Provides offline shell caching and install prompt.

const CACHE_NAME = 'faceid-v1';
const SHELL_URLS = ['/login/', '/face-login/'];

self.addEventListener('install', (event) => {
  event.waitUntil(
    caches.open(CACHE_NAME).then((cache) => cache.addAll(SHELL_URLS))
  );
  self.skipWaiting();
});

self.addEventListener('activate', (event) => {
  event.waitUntil(
    caches.keys().then((keys) =>
      Promise.all(keys.filter((k) => k !== CACHE_NAME).map((k) => caches.delete(k)))
    )
  );
  self.clients.claim();
});

self.addEventListener('fetch', (event) => {
  // Network-first for API calls and POST requests.
  if (event.request.method !== 'GET' || event.request.url.includes('/api/')) {
    return;
  }
  // For navigation, try network first, fall back to cache.
  event.respondWith(
    fetch(event.request).catch(() => caches.match(event.request))
  );
});
