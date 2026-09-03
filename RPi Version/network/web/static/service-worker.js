"use strict";

const CACHE_VERSION = "__PHYTO_CACHE_VERSION__";
const ASSET_CACHE = `phyto-assets-${CACHE_VERSION}`;
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
        (name.startsWith("phyto-pages-") && name !== PAGE_CACHE)
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
      if (cached) return cached;
    }
    return (await caches.match("/offline")) || Response.error();
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
