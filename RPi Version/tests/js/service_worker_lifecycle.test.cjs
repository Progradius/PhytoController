"use strict";
const {test} = require("node:test");
const assert = require("node:assert/strict");
const vm = require("node:vm");
const fs = require("node:fs");
const template = fs.readFileSync("network/web/static/service-worker.js", "utf8");
const build = (precache = []) => template.replace("__PHYTO_PRECACHE_URLS__", JSON.stringify(precache));
const source = build();
function worker(fetch, caches, timers = {}, precache = null) {
  const code = precache ? build(precache) : source;
  const events = {};
  const calls = [];
  const scope = {
    fetch, caches, URL, Request, Response, Headers, AbortController,
    setTimeout: timers.setTimeout || setTimeout, clearTimeout,
    self: {location: {origin: "https://phyto.local"}, addEventListener: (name, fn) => { events[name] = fn; },
      clients: {claim: async () => calls.push("claim")}, skipWaiting: async () => calls.push("skip")},
  };
  vm.createContext(scope); vm.runInContext(code, scope);
  return {run: code => vm.runInContext(code, scope), events, calls};
}
const refusal = {open: async () => { throw Error("stockage refusé"); }, match: async () => { throw Error("stockage refusé"); }};
test("stockage refusé : toutes les lectures connectées restent utilisables", async () => {
  const w = worker(async () => new Response("vivant"), refusal);
  for (const expression of ["navigationFallback(new Request('https://phyto.local/'), true)", "cultureFallback(new Request('https://phyto.local/cultures'))", "cachedAsset(new Request('https://phyto.local/static/test.css'))"])
    assert.equal(await (await w.run(expression)).text(), "vivant");
});
test("HTTP 500 reste une vraie réponse, jamais une copie", async () => {
  const cache = {put: async () => assert.fail("ne pas stocker 500"), match: async () => new Response("copie")};
  const w = worker(async () => new Response("panne serveur", {status: 500}), {open: async () => cache});
  for (const expression of ["navigationFallback(new Request('https://phyto.local/'), true)", "cultureFallback(new Request('https://phyto.local/cultures'))"]) {
    const response = await w.run(expression); assert.equal(response.status, 500); assert.equal(await response.text(), "panne serveur");
  }
});
test("navigation muette : abandon à 8 secondes et copie marquée", async () => {
  let budget;
  const w = worker((_request, options) => new Promise((_resolve, reject) => options.signal.addEventListener("abort", () => reject(new DOMException("délai", "AbortError")))),
    {open: async () => ({match: async () => new Response("<head></head>copie")})},
    {setTimeout: (fn, ms) => { budget = ms; return setTimeout(fn, 5); }});
  const response = await w.run("navigationFallback(new Request('https://phyto.local/'), true)");
  assert.equal(budget, 8000); assert.match(await response.text(), /phyto-offline-shell/);
});
test("installation sans skipWaiting, activation uniquement par message", async () => {
  const cache = {put: async () => {}};
  const w = worker(async () => new Response("page"), {open: async () => cache, keys: async () => []});
  let task;
  w.events.install({waitUntil: promise => { task = promise; }}); await task;
  assert.deepEqual(w.calls, []);
  w.events.message({data: {type: "activer"}, waitUntil: promise => { task = promise; }}); await task;
  assert.deepEqual(w.calls, ["skip"]);
});
// La preuve est un **blocage** : chaque réponse attend que les trois requêtes soient
// parties. Une boucle séquentielle ne verrait jamais partir la deuxième et l'installation
// ne se terminerait pas — le test échouerait par délai, pas par une assertion de forme.
test("l’installation précharge en parallèle, et reste atomique", async () => {
  const urls = ["/static/a.css", "/static/b.js", "/static/c.png"];
  let started = 0;
  let toutesParties;
  const parties = new Promise(resolve => { toutesParties = resolve; });
  const cache = {put: async () => {}};
  // Le préchauffage des pages de lecture partage ce `fetch` : seules les URL du précache
  // sont comptées, sinon ses quatre navigations fausseraient le total.
  const w = worker(async url => {
    if (urls.includes(url) && ++started === urls.length) toutesParties();
    await parties;
    return new Response("ressource");
  }, {open: async () => cache, keys: async () => []}, {}, urls);
  let task;
  w.events.install({waitUntil: promise => { task = promise; }});
  await task;
  assert.equal(started, urls.length);
});

test("une ressource d’installation indisponible fait échouer l’installation entière", async () => {
  const w = worker(async url => new Response("", {status: url === "/static/b.js" ? 500 : 200}),
    {open: async () => ({put: async () => {}}), keys: async () => []}, {}, ["/static/a.css", "/static/b.js"]);
  let task;
  w.events.install({waitUntil: promise => { task = promise; }});
  await assert.rejects(task, /Ressource d’installation indisponible/);
});

// Ce que l'activation doit faire, et **dans cet ordre** : prendre la main sur les clients,
// puis seulement supprimer les caches des versions précédentes. L'inverse retirerait les
// copies sous une page encore servie par l'ancienne version.
test("l’activation réclame les clients avant de purger les anciennes versions", async () => {
  const supprimes = [];
  const noms = [
    "phyto-assets-ancienne", "phyto-assets-__PHYTO_CACHE_VERSION__",
    "phyto-pages-ancienne", "phyto-pages-__PHYTO_CACHE_VERSION__",
    "phyto-cultures-ancienne", "phyto-cultures-__PHYTO_CACHE_VERSION__",
    "phyto-culture-media-ancienne", "phyto-culture-media-__PHYTO_CACHE_VERSION__",
    "un-cache-etranger",
  ];
  const w = worker(async () => new Response("page"), {
    keys: async () => noms,
    delete: async (name) => { supprimes.push(`${w.calls.join(",")}|${name}`); return true; },
  });
  let task;
  w.events.activate({waitUntil: (promise) => { task = promise; }});
  await task;
  // Seules les versions précédentes partent : la version courante reste, et un cache qui
  // n'appartient pas à l'application n'est jamais touché.
  assert.deepEqual(supprimes.map((trace) => trace.split("|")[1]).sort(), [
    "phyto-assets-ancienne", "phyto-culture-media-ancienne",
    "phyto-cultures-ancienne", "phyto-pages-ancienne",
  ]);
  // Chaque suppression a eu lieu après `claim`, jamais avant.
  for (const trace of supprimes) assert.equal(trace.split("|")[0], "claim");
});

test("le worker prouve sa version au client demandeur", () => {
  const w = worker(async () => new Response("page"), {open: async () => ({})});
  let message;
  w.events.message({data: {type: "version"}, source: {postMessage: value => { message = value; }}});
  assert.deepEqual({...message}, {type: "version", version: "__PHYTO_CACHE_VERSION__"});
  assert.equal(w.calls.includes("skip"), false);
});
test("aucune interception mutante et API sans cache", async () => {
  let fetched = 0;
  const w = worker(async () => { fetched++; return new Response("api"); }, refusal);
  w.events.fetch({request: new Request("https://phyto.local/actions/test", {method: "POST"}), respondWith: () => assert.fail("mutation interceptée")});
  let answer;
  w.events.fetch({request: new Request("https://phyto.local/api/v1/state"), respondWith: promise => { answer = promise; }});
  assert.equal(await (await answer).text(), "api"); assert.equal(fetched, 1);
});
