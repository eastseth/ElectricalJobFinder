const CACHE = 'electrical-job-finder-v2';
const ASSETS = ['./','index.html','styles.css','app.js','manifest.webmanifest','icon-180.png','icon-512.png'];
self.addEventListener('install', e => {
  self.skipWaiting();
  e.waitUntil(caches.open(CACHE).then(c=>c.addAll(ASSETS)));
});
self.addEventListener('activate', e => {
  e.waitUntil(
    caches.keys().then(keys => Promise.all(keys.filter(k => k !== CACHE).map(k => caches.delete(k))))
      .then(() => self.clients.claim())
  );
});
self.addEventListener('fetch', e => {
  if (e.request.url.includes('jobs.json') || e.request.url.includes('status.json')) return;
  e.respondWith(caches.match(e.request).then(r=>r || fetch(e.request)));
});
