const CACHE_NAME = 'filmvault-v3';
const STATIC_ASSETS = [
  './',
  './index.html',
  './style.css',
  './app.js',
  './manifest.json',
  './catalog_index.json'
];

// Install: cache static assets
self.addEventListener('install', function (e) {
  e.waitUntil(
    caches.open(CACHE_NAME).then(function (cache) {
      return cache.addAll(STATIC_ASSETS);
    }).then(function () {
      return self.skipWaiting();
    })
  );
});

// Activate: clean old caches
self.addEventListener('activate', function (e) {
  e.waitUntil(
    caches.keys().then(function (keys) {
      return Promise.all(
        keys.filter(function (key) { return key !== CACHE_NAME; })
            .map(function (key) { return caches.delete(key); })
      );
    })
  );
  self.clients.claim();
});

// Fetch: cache-first for static, network-first for catalog.json
self.addEventListener('fetch', function (e) {
  const url = new URL(e.request.url);

  // Network-first for catalog data (chunks + index)
  if (url.pathname.endsWith('catalog.json') || url.pathname.match(/catalog_(index|\d+)\.json$/)) {
    e.respondWith(
      fetch(e.request)
        .then(function (res) {
          var clone = res.clone();
          caches.open(CACHE_NAME).then(function (cache) {
            cache.put(e.request, clone);
          });
          return res;
        })
        .catch(function () {
          return caches.match(e.request);
        })
    );
    return;
  }

  // Cache-first for everything else
  e.respondWith(
    caches.match(e.request).then(function (cached) {
      return cached || fetch(e.request).then(function (res) {
        // Cache new assets dynamically
        if (res.ok && url.origin === self.location.origin) {
          var clone = res.clone();
          caches.open(CACHE_NAME).then(function (cache) {
            cache.put(e.request, clone);
          });
        }
        return res;
      });
    })
  );
});
