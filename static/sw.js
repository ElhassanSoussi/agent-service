// Xone Service Worker v2 - Network-first for HTML, cache static assets only
const CACHE_NAME = 'xone-v2';
const STATIC_ASSETS = [
  '/static/manifest.json',
  '/static/icon-192.svg'
];

// Install - cache only static assets (NOT HTML)
self.addEventListener('install', (event) => {
  event.waitUntil(
    caches.open(CACHE_NAME).then((cache) => {
      return cache.addAll(STATIC_ASSETS);
    })
  );
  self.skipWaiting();
});

// Activate - clean ALL old caches immediately
self.addEventListener('activate', (event) => {
  event.waitUntil(
    caches.keys().then((cacheNames) => {
      return Promise.all(
        cacheNames
          .filter((name) => name !== CACHE_NAME)
          .map((name) => caches.delete(name))
      );
    })
  );
  self.clients.claim();
});

// Fetch - NEVER cache navigation (HTML) requests
self.addEventListener('fetch', (event) => {
  const url = new URL(event.request.url);
  
  // Navigation requests (HTML pages) - ALWAYS network, no cache
  if (event.request.mode === 'navigate' || 
      url.pathname.startsWith('/ui/')) {
    event.respondWith(fetch(event.request));
    return;
  }
  
  // API calls - always network, no cache
  if (url.pathname.startsWith('/v1/') || 
      url.pathname.startsWith('/agent/') ||
      url.pathname.startsWith('/llm/') ||
      url.pathname.startsWith('/memory/') ||
      url.pathname.startsWith('/feedback/') ||
      url.pathname.startsWith('/health') ||
      url.pathname.startsWith('/docs')) {
    event.respondWith(fetch(event.request));
    return;
  }
  
  // Static assets - cache-first
  if (url.pathname.startsWith('/static/')) {
    event.respondWith(
      caches.match(event.request).then((cached) => {
        return cached || fetch(event.request).then((response) => {
          if (response.status === 200) {
            const clone = response.clone();
            caches.open(CACHE_NAME).then((cache) => cache.put(event.request, clone));
          }
          return response;
        });
      })
    );
    return;
  }
  
  // Everything else - network only
  event.respondWith(fetch(event.request));
});
