const CACHE = 'shengban-v7-three-scores';
self.addEventListener('install', event => event.waitUntil((async () => {
  const response = await fetch('./asset-list.json', { cache: 'no-store' });
  const files = await response.json();
  const cache = await caches.open(CACHE);
  await cache.addAll(files);
  await self.skipWaiting();
})()));
self.addEventListener('activate', event => event.waitUntil((async () => {
  for (const key of await caches.keys()) {
    if (key.startsWith('shengban-') && key !== CACHE) await caches.delete(key);
  }
  await self.clients.claim();
})()));
self.addEventListener('fetch', event => {
  if (event.request.method !== 'GET') return;
  if (new URL(event.request.url).origin !== self.location.origin) return;
  event.respondWith((async () => {
    const cache = await caches.open(CACHE);
    try {
      const response = await fetch(event.request);
      if (response.ok && response.status === 200 && !event.request.headers.has('range')) await cache.put(event.request, response.clone());
      return response;
    } catch {
      const cached = await cache.match(event.request);
      return cached || new Response('离线文件尚未缓存，请联网打开一次', { status: 503 });
    }
  })());
});
