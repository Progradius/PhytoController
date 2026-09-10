"use strict";

const CACHE_VERSION = "__PHYTO_CACHE_VERSION__";
const ASSET_CACHE = `phyto-assets-${CACHE_VERSION}`;
const CULTURE_CACHE = `phyto-cultures-${CACHE_VERSION}`;
const MEDIA_CACHE = `phyto-culture-media-${CACHE_VERSION}`;
const PAGE_CACHE = `phyto-pages-${CACHE_VERSION}`;
const PRECACHE_URLS = __PHYTO_PRECACHE_URLS__;

const warmReadablePages = async () => {
  const pages = await caches.open(PAGE_CACHE);
  for (const path of ["/", "/history", "/alarms"]) {
    try {
      const response = await fetch(path, {cache: "no-store"});
      if (response.ok) await pages.put(new URL(path, self.location.origin).href, response);
    } catch (_error) {
      // Une page dynamique indisponible ne doit pas empêcher l'installation
      // de la coque minimale hors ligne.
    }
  }
};

self.addEventListener("install", (event) => {
  event.waitUntil(
    Promise.all([
      caches.open(ASSET_CACHE).then((cache) => cache.addAll(PRECACHE_URLS)),
      warmReadablePages(),
    ])
      .then(() => self.skipWaiting())
  );
});

self.addEventListener("activate", (event) => {
  event.waitUntil((async () => {
    const names = await caches.keys();
    await Promise.all(names
      .filter((name) => (
        (name.startsWith("phyto-assets-") && name !== ASSET_CACHE) ||
        (name.startsWith("phyto-pages-") && name !== PAGE_CACHE) ||
        (name.startsWith("phyto-cultures-") && name !== CULTURE_CACHE) ||
        (name.startsWith("phyto-culture-media-") && name !== MEDIA_CACHE)
      ))
      .map((name) => caches.delete(name)));
    await self.clients.claim();
  })());
});

const networkOnly = (request) => fetch(request);

const cachedAsset = async (request) => {
  const cached = await caches.match(request);
  if (cached) return cached;
  const response = await fetch(request);
  if (response.ok) {
    const cache = await caches.open(ASSET_CACHE);
    await cache.put(request, response.clone());
  }
  return response;
};

const navigationFallback = async (request, cacheable) => {
  const pages = await caches.open(PAGE_CACHE);
  try {
    const response = await fetch(request);
    if (cacheable && response.ok) await pages.put(request.url, response.clone());
    return response;
  } catch (_error) {
    if (cacheable) {
      const cached = await pages.match(request.url);
      // La page est marquée comme venant du cache : c'est la preuve que la navigation elle-même a
      // échoué, et elle autorise la PWA à annoncer « hors ligne » sans attendre son délai de silence.
      if (cached) {
        const html = (await cached.text()).replace("</head>", '<meta name="phyto-offline-shell" content=""></head>');
        return new Response(html, {status: 200, headers: cached.headers});
      }
    }
    return (await caches.match("/offline")) || Response.error();
  }
};


// Le carnet reste réseau d'abord. Seul un échec de transport permet de relire une page datée.
const cultureFallback = async (request, photo = false) => {
  let cache = null;
  try { cache = await caches.open(photo ? MEDIA_CACHE : CULTURE_CACHE); } catch (_error) { /* Le stockage ne bloque pas le réseau. */ }
  try {
    const response = await fetch(request);
    if (response.ok && cache) {
      try {
      const copy = response.clone();
      const bytes = await copy.arrayBuffer();
      if (bytes.byteLength <= 4 * 1024 * 1024) {
        const headers = new Headers(response.headers);
        headers.delete("Content-Encoding"); headers.delete("Content-Length");
        headers.set("X-Phyto-Cached-At", String(Date.now()));
        await cache.delete(request.url);
        await cache.put(request.url, new Response(bytes, {status: response.status, headers}));
        const keys = await cache.keys();
        for (const key of keys.slice(0, Math.max(0, keys.length - (photo ? 40 : 20)))) await cache.delete(key);
      }
      } catch (_error) { /* Une réponse réseau réussie reste prioritaire sur un cache saturé. */ }
    }
    return response;
  } catch (_error) {
    const cached = cache ? await cache.match(request.url) : null;
    if (!cached) return photo ? Response.error() : (await caches.match("/offline")) || Response.error();
    if (photo) return cached;
    const at = Number(cached.headers.get("X-Phyto-Cached-At")) || 0;
    const html = (await cached.text()).replace("</head>", `<meta name="phyto-offline-snapshot" content="${at}"></head>`);
    return new Response(html, {status: 200, headers: cached.headers});
  }
};

self.addEventListener("fetch", (event) => {
  const request = event.request;
  if (request.method !== "GET") return;

  const url = new URL(request.url);
  if (url.origin !== self.location.origin) return;

  if (
    url.pathname.startsWith("/api/") ||
    url.pathname.startsWith("/actions/") ||
    url.pathname.startsWith("/health/") ||
    url.pathname === "/status" ||
    url.pathname === "/console/stream"
  ) {
    event.respondWith(networkOnly(request));
    return;
  }

  if (/^\/cultures\/photos\/[0-9a-f-]{36}$/.test(url.pathname)) {
    event.respondWith(cultureFallback(request, true)); return;
  }
  if (request.mode === "navigate" && /^\/cultures(?:\/(?:cycles|solutions|targets|light|equipment|journal|[0-9a-f-]{36}))?$/.test(url.pathname)) {
    event.respondWith(cultureFallback(request)); return;
  }
  if (request.mode === "navigate") {
    const cacheable = (
      url.search === "" &&
      ["/", "/index.html", "/history", "/alarms"].includes(url.pathname)
    );
    event.respondWith(navigationFallback(request, cacheable));
    return;
  }

  if (
    url.pathname.startsWith("/static/") ||
    url.pathname === "/favicon.svg" ||
    url.pathname === "/app.webmanifest"
  ) {
    event.respondWith(cachedAsset(request));
  }
});

self.addEventListener("notificationclick", (event) => {
  event.notification.close();
  const destination = new URL(event.notification.data?.url || "/alarms", self.location.origin).href;
  event.waitUntil((async () => {
    const windows = await self.clients.matchAll({type: "window", includeUncontrolled: true});
    for (const client of windows) {
      if (new URL(client.url).origin === self.location.origin) {
        await client.focus();
        await client.navigate(destination);
        return;
      }
    }
    await self.clients.openWindow(destination);
  })());
});
