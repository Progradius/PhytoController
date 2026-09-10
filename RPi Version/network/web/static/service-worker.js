"use strict";

const CACHE_VERSION = "__PHYTO_CACHE_VERSION__";
const ASSET_CACHE = `phyto-assets-${CACHE_VERSION}`;
const CULTURE_CACHE = `phyto-cultures-${CACHE_VERSION}`;
const MEDIA_CACHE = `phyto-culture-media-${CACHE_VERSION}`;
const PAGE_CACHE = `phyto-pages-${CACHE_VERSION}`;
const PRECACHE_URLS = __PHYTO_PRECACHE_URLS__;
// Plafond d'une copie du carnet (page ou photo), en octets.
const MAX_CACHED_BYTES = 4 * 1024 * 1024;

// Le budget porte seulement sur les pages, jamais sur les API ni le SSE.
const fetchWithBudget = async (request, ms, options = {}) => {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), ms);
  try { return await fetch(request, {...options, signal: controller.signal}); }
  finally { clearTimeout(timer); }
};
// Une coque hors ligne est **réécrite** : le marqueur `phyto-offline-shell` (ou
// `phyto-offline-snapshot`) allonge le corps. Réutiliser les en-têtes de la copie telles
// quelles annoncerait donc une longueur fausse, et un `Content-Encoding` qui ne s'applique
// plus au texte reconstruit. Les deux sont retirés, comme à la mise en cache.
const shellHeaders = (source) => {
  const headers = new Headers(source);
  headers.delete("Content-Encoding");
  headers.delete("Content-Length");
  return headers;
};
const safeMatch = async (request) => {
  try { return await caches.match(request); } catch (_error) { return null; }
};
const warmReadablePages = async () => {
  let pages;
  try { pages = await caches.open(PAGE_CACHE); } catch (_error) { return; }
  for (const path of ["/", "/history", "/alarms", "/app"]) {
    try {
      const response = await fetchWithBudget(path, 15000, {cache: "no-store"});
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
      // Précache **parallèle** : `cache.addAll` l'était, et une boucle séquentielle
      // rendait l'installation N fois plus longue exactement là où elle compte — un
      // Wi-Fi de serre lent. Ce qui est tout ou rien, ici comme avec `addAll`, c'est
      // l'**installation** : `Promise.all` rejette au premier échec, le worker n'atteint
      // jamais l'état installé et ne peut donc pas prendre la main. Le cache, lui, peut
      // garder les ressources déjà écrites — sans conséquence, puisque c'est la version
      // suivante qui les réécrira sous son propre nom de cache.
      caches.open(ASSET_CACHE).then(cache => Promise.all(PRECACHE_URLS.map(async url => {
        const response = await fetchWithBudget(url, 15000);
        if (!response.ok) throw new Error("Ressource d’installation indisponible");
        await cache.put(url, response);
      }))),
      warmReadablePages(),
    ])
  );
});

self.addEventListener("activate", (event) => {
  event.waitUntil((async () => {
    await self.clients.claim();
    const names = await caches.keys();
    await Promise.all(names
      .filter((name) => (
        (name.startsWith("phyto-assets-") && name !== ASSET_CACHE) ||
        (name.startsWith("phyto-pages-") && name !== PAGE_CACHE) ||
        (name.startsWith("phyto-cultures-") && name !== CULTURE_CACHE) ||
        (name.startsWith("phyto-culture-media-") && name !== MEDIA_CACHE)
      ))
      .map((name) => caches.delete(name)));
  })());
});

self.addEventListener("message", (event) => {
  if (event.data?.type === "activer") event.waitUntil(self.skipWaiting());
  if (event.data?.type === "version") event.source?.postMessage({type: "version", version: CACHE_VERSION});
});

const networkOnly = (request) => fetch(request);

const cachedAsset = async (request) => {
  const cached = await safeMatch(request);
  if (cached) return cached;
  const response = await fetch(request);
  if (response.ok) {
    try {
      const cache = await caches.open(ASSET_CACHE);
      await cache.put(request, response.clone());
    } catch (_error) { /* La réponse réseau reste utilisable sans stockage. */ }
  }
  return response;
};

const navigationFallback = async (request, cacheable) => {
  let pages = null;
  try { pages = await caches.open(PAGE_CACHE); } catch (_error) { /* Réseau prioritaire. */ }
  try {
    const response = await fetchWithBudget(request, 8000);
    if (cacheable && response.ok && pages) {
      try { await pages.put(request.url, response.clone()); } catch (_error) { /* Quota. */ }
    }
    return response;
  } catch (_error) {
    if (cacheable && pages) {
      const cached = await pages.match(request.url).catch(() => null);
      // La page est marquée comme venant du cache : c'est la preuve que la navigation elle-même a
      // échoué, et elle autorise la PWA à annoncer « hors ligne » sans attendre son délai de silence.
      if (cached) {
        const html = (await cached.text()).replace("</head>", '<meta name="phyto-offline-shell" content=""></head>');
        return new Response(html, {status: 200, headers: shellHeaders(cached.headers)});
      }
    }
    return (await safeMatch("/offline")) || Response.error();
  }
};


// Le carnet reste réseau d'abord. Seul un échec de transport permet de relire une page datée.
const cultureFallback = async (request, photo = false) => {
  let cache = null;
  try { cache = await caches.open(photo ? MEDIA_CACHE : CULTURE_CACHE); } catch (_error) { /* Le stockage ne bloque pas le réseau. */ }
  try {
    const response = await fetchWithBudget(request, 8000);
    // La taille annoncée est consultée **avant** de matérialiser le corps : une réponse
    // qui se déclare au-delà du plafond n'a aucune raison d'être chargée entière en
    // mémoire pour être refusée ensuite. L'en-tête peut manquer ou porter la taille
    // compressée : le contrôle sur les octets réels reste donc, il n'est pas remplacé.
    const annonce = Number(response.headers.get("Content-Length"));
    if (response.ok && cache && !(Number.isFinite(annonce) && annonce > MAX_CACHED_BYTES)) {
      try {
      const copy = response.clone();
      const bytes = await copy.arrayBuffer();
      if (bytes.byteLength <= MAX_CACHED_BYTES) {
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
    const cached = cache ? await cache.match(request.url).catch(() => null) : null;
    if (!cached) return photo ? Response.error() : (await safeMatch("/offline")) || Response.error();
    if (photo) return cached;
    const at = Number(cached.headers.get("X-Phyto-Cached-At")) || 0;
    const html = (await cached.text()).replace("</head>", `<meta name="phyto-offline-snapshot" content="${at}"></head>`);
    return new Response(html, {status: 200, headers: shellHeaders(cached.headers)});
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
      // Les chemins réellement servis, et eux seuls : le contrôleur n'expose pas
      // `/index.html`, qui ne pouvait donc jamais être ni mis en cache ni relu.
      ["/", "/history", "/alarms", "/app"].includes(url.pathname)
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
      if (new URL(client.url).origin !== self.location.origin) continue;
      // `navigate()` échoue sur une fenêtre que le worker ne contrôle pas encore, et
      // rejette aussi quand le client a disparu entre l'inventaire et l'appel. Sans ce
      // repli, le clic sur la notification d'une alarme n'ouvrait alors **rien**.
      try {
        await client.focus();
        await client.navigate(destination);
        return;
      } catch (_error) {
        break;
      }
    }
    await self.clients.openWindow(destination);
  })());
});
