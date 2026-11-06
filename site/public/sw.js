// Service worker: lets the site open from the home screen and show the last forecast offline.
// - pages and data/*.json: network first (always fresh when online), cached copy when offline
// - hashed build assets and icons: cache first (their names change with every build)
// - other origins (live.json on raw.githubusercontent.com) are not touched
const CACHE = "bahn-wetter-v1";

self.addEventListener("install", () => self.skipWaiting());
self.addEventListener("activate", (e) => {
  e.waitUntil(
    caches.keys().then((keys) => Promise.all(keys.filter((k) => k !== CACHE).map((k) => caches.delete(k)))).then(() => self.clients.claim()),
  );
});

async function networkFirst(req) {
  const cache = await caches.open(CACHE);
  try {
    const res = await fetch(req, { cache: "no-cache" });
    if (res.ok) cache.put(req, res.clone());
    return res;
  } catch (err) {
    const hit = await cache.match(req, { ignoreSearch: true });
    if (hit) return hit;
    throw err;
  }
}

async function cacheFirst(req) {
  const cache = await caches.open(CACHE);
  const hit = await cache.match(req);
  if (hit) return hit;
  const res = await fetch(req);
  if (res.ok) cache.put(req, res.clone());
  return res;
}

self.addEventListener("fetch", (e) => {
  const req = e.request;
  const url = new URL(req.url);
  if (req.method !== "GET" || url.origin !== location.origin) return;
  if (url.pathname.includes("/assets/") || url.pathname.includes("/icons/")) e.respondWith(cacheFirst(req));
  else if (req.mode === "navigate" || url.pathname.endsWith(".json")) e.respondWith(networkFirst(req));
});
