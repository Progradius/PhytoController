/* Inventaire partagé de lecture locale : aucune acquisition ni mutation. */
(() => {
  "use strict";
  const connection = document.querySelector("[data-app-connection]");
  if (connection) connection.textContent = `${location.protocol === "https:" ? "HTTPS" : "HTTP"} · ${window.isSecureContext ? "Contexte sécurisé" : "Contexte non sécurisé : installation et stockage hors ligne peuvent être indisponibles"} · ${location.host}`;

  // Mêmes libellés que les rubriques de `templates/culture_navigation.html` : une copie
  // conservée porte le nom de la page telle que l'opérateur la connaît, pas un alias.
  const labels = {
    "/cultures": "Cultures", "/cultures/solutions": "Solutions et relevés",
    "/cultures/cycles": "Cycles et rappels", "/cultures/targets": "Plages cibles",
    "/cultures/light": "Repères d’éclairage", "/cultures/equipment": "Équipements",
    "/cultures/journal": "Journal",
  };
  const inventory = async () => {
    if (!("caches" in window)) return null;
    const entries = new Map();
    try {
      for (const name of await caches.keys()) {
        if (!name.startsWith("phyto-cultures-")) continue;
        const cache = await caches.open(name);
        for (const request of await cache.keys()) {
          const url = new URL(request.url);
          if (url.origin !== location.origin || !url.pathname.startsWith("/cultures")) continue;
          const response = await cache.match(request);
          const at = Number(response?.headers.get("X-Phyto-Cached-At")) || 0;
          if (!entries.has(url.href) || entries.get(url.href).at < at) entries.set(url.href, {url: url.href, at});
        }
      }
      return [...entries.values()].sort((a, b) => b.at - a.at);
    } catch (_error) { return null; }
  };
  const render = async () => {
    const containers = document.querySelectorAll("[data-culture-offline-index]");
    if (!containers.length) return;
    const entries = await inventory();
    containers.forEach(container => {
      container.replaceChildren();
      if (!entries?.length) {
        const message = document.createElement("p");
        message.textContent = entries === null ? "Inventaire hors ligne indisponible : accès au stockage refusé ou non pris en charge." : "Aucune page du carnet n’est conservée hors ligne pour l’instant.";
        container.append(message); return;
      }
      const list = document.createElement("ul");
      entries.forEach(entry => {
        const url = new URL(entry.url), item = document.createElement("li"), link = document.createElement("a");
        link.href = entry.url; link.className = "action-link";
        link.textContent = labels[url.pathname] || "Fiche de culture";
        if (url.search) link.textContent += ` · ${url.searchParams.toString()}`;
        item.append(link, document.createTextNode(` · conservée le ${entry.at ? new Date(entry.at).toLocaleString("fr-FR") : "date inconnue"}`));
        list.append(item);
      });
      container.append(list);
    });
    document.querySelectorAll("[data-offline-latest]").forEach(node => {
      node.textContent = entries?.[0]?.at ? `Dernière copie : ${new Date(entries[0].at).toLocaleString("fr-FR")}.` : "Aucune copie datée disponible.";
    });
    if (!document.querySelector('meta[name="phyto-offline-snapshot"]') || !entries) return;
    const known = new Set(entries.map(entry => entry.url));
    document.querySelectorAll("[data-climate-offset], [data-cycle-offset], [data-culture-page]").forEach(link => {
      if (known.has(link.href.split("#")[0]) || link.dataset.offlineUnavailable) return;
      link.dataset.offlineUnavailable = "true";
      link.setAttribute("aria-disabled", "true"); link.classList.add("culture-unavailable");
      link.append(document.createTextNode(" · non conservé hors ligne"));
      link.addEventListener("click", event => event.preventDefault());
    });
  };
  render();
  window.addEventListener("pageshow", event => { if (event.persisted) render(); });
})();
