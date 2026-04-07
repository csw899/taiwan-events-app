const CACHE = 'events-v1';
const STATIC = ['/static/style.css', '/static/app.js'];

self.addEventListener('install', e => {
  e.waitUntil(caches.open(CACHE).then(c => c.addAll(STATIC)));
  self.skipWaiting();
});

self.addEventListener('activate', e => {
  e.waitUntil(caches.keys().then(keys =>
    Promise.all(keys.filter(k => k !== CACHE).map(k => caches.delete(k)))
  ));
  self.clients.claim();
});

self.addEventListener('fetch', e => {
  const url = new URL(e.request.url);
  // API 請求永遠走網路
  if (url.pathname.startsWith('/api/')) return;
  // 靜態資源優先用快取
  e.respondWith(
    caches.match(e.request).then(cached => cached || fetch(e.request))
  );
});
