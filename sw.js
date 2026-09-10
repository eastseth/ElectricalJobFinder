
const CACHE = 'electrical-job-finder-v1';
const ASSETS = ['./','index.html','styles.css','app.js','manifest.webmanifest','icon-180.png','icon-512.png'];
self.addEventListener('install', e => e.waitUntil(caches.open(CACHE).then(c=>c.addAll(ASSETS))));
self.addEventListener('fetch', e => {
  if (e.request.url.includes('jobs.json')) return;
  e.respondWith(caches.match(e.request).then(r=>r || fetch(e.request)));
});
