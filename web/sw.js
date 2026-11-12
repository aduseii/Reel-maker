// Works offline once opened: the app's own files are kept, and always refreshed from the
// network when there is one (so updates arrive straight away).
const CACHE = "reelmaker-v1";
const CORE = ["./", "index.html", "style.css", "js/app.js", "js/render.js", "js/export.js", "js/store.js", "js/cloud.js",
  "vendor/mp4-muxer.mjs", "manifest.webmanifest", "icons/favicon.png", "icons/icon-192.png",
  "fonts/InterDisplay-Regular.ttf", "fonts/InterDisplay-Medium.ttf", "fonts/InterDisplay-SemiBold.ttf",
  "fonts/InterDisplay-Bold.ttf", "fonts/InterDisplay-ExtraBold.ttf", "fonts/InterDisplay-Black.ttf"];

self.addEventListener("install", (e) => { e.waitUntil(caches.open(CACHE).then((c) => c.addAll(CORE)).then(() => self.skipWaiting())); });
self.addEventListener("activate", (e) => { e.waitUntil(self.clients.claim()); });
self.addEventListener("fetch", (e) => {
  const url = new URL(e.request.url);
  if (e.request.method !== "GET" || url.origin !== location.origin) return;
  e.respondWith(
    fetch(e.request).then((r) => {
      if (r.ok && !url.pathname.includes("/emoji/")) { const copy = r.clone(); caches.open(CACHE).then((c) => c.put(e.request, copy)); }
      return r;
    }).catch(() => caches.match(e.request).then((m) => m || caches.match("index.html")))
  );
});
