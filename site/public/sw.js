// Service worker: lets the site open from the home screen and show the last forecast offline.
// It handles only what the app itself needs and lets everything else go straight to the network:
// - the app page (navigations to …/ or …/index.html) and data/*.json: network first, cached copy offline
// - hashed build assets and icons: cache first (their names change with every build)
// - anything else (cards/*.png, manifest, other origins such as live.json): not intercepted
const CACHE = "bahn-wetter-v2";

self.addEventListener("install", () => self.skipWaiting());
self.addEventListener("activate", (e) => {
  e.waitUntil(
    caches.keys().then((keys) => Promise.all(keys.filter((k) => k !== CACHE).map((k) => caches.delete(k)))).then(() => self.clients.claim()),
  );
});

// Fetch by URL, never by re-wrapping the original Request: a navigation Request cannot be cloned with
// new options in every browser, and its "manual" redirect mode would break on a redirect.
async function networkFirst(url) {
  const cache = await caches.open(CACHE);
  try {
    const res = await fetch(url, { cache: "no-cache", credentials: "same-origin" });
    if (res.ok && !res.redirected) cache.put(url, res.clone());
    return res;
  } catch (err) {
    const hit = await cache.match(url, { ignoreSearch: true });
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
  const scope = new URL(self.registration.scope).pathname;
  const path = url.pathname;
  if (!path.startsWith(scope)) return;
  const rel = path.slice(scope.length);
  if (rel.startsWith("assets/") || rel.startsWith("icons/")) {
    e.respondWith(cacheFirst(req));
  } else if (req.mode === "navigate" && (rel === "" || rel === "index.html")) {
    e.respondWith(networkFirst(url.origin + path));
  } else if (/^data\/[\w-]+\.json$/.test(rel)) {
    e.respondWith(networkFirst(url.origin + path));
  }
});
