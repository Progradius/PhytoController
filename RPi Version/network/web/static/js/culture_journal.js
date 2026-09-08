(() => {
  "use strict";
  // Lot H : saisie, correction et photo d'une observation d'espace, plus l'inventaire daté
  // des pages du carnet conservées hors ligne. Aucune mutation n'est mise en attente.
  const csrf = document.querySelector('meta[name="csrf-token"]')?.content;
  const identifier = () => Array.from(crypto.getRandomValues(new Uint8Array(20)), n => n.toString(16).padStart(2, "0")).join("");
  // La pagination conserve les filtres : seul le décalage change dans l'adresse courante.
  document.querySelectorAll("[data-journal-offset]").forEach(link => {
    const query = new URLSearchParams(location.search);
    query.set("offset", link.dataset.journalOffset);
    query.delete("focus");
    link.search = query.toString();
  });
  document.querySelectorAll("[data-journal-form], [data-journal-photo]").forEach(form => {
    let busy = false, previous = null, key = identifier();
    const get = name => form.elements[name]?.value || "";
    form.addEventListener("submit", async event => {
      event.preventDefault();
      if (busy) return;
      const output = form.querySelector("output"), button = form.querySelector('[type="submit"]');
      if (!navigator.onLine || document.body.classList.contains("is-offline")) {
        output.textContent = "Hors ligne : saisie conservée dans cette page, aucun envoi en attente.";
        return;
      }
      try {
        const photo = form.hasAttribute("data-journal-photo");
        const command = {confirm_date: form.elements.confirm_date?.checked || false};
        let body;
        if (photo) {
          const file = form.elements.photo.files[0];
          if (!file || file.size > 5 * 1024 * 1024) throw new Error("Choisir une photo de 5 Mio maximum.");
          Object.assign(command, {space_event_id: form.dataset.id, space_event_revision: Number(form.dataset.version),
            caption: get("caption")});
          body = file;
        } else {
          command.operation = form.dataset.operation;
          Object.assign(command, {effective_at: get("effective_at"), note: get("note")});
          if (command.operation === "space_event") Object.assign(command, {space: get("space"), kind: get("kind"), precision: get("precision")});
          else Object.assign(command, {id: form.dataset.id, version: Number(form.dataset.version),
            reason: get("reason"), cancelled: form.elements.cancelled?.checked || false});
        }
        const signature = JSON.stringify(command) + (photo ? `${body.name}:${body.size}:${body.lastModified}` : "");
        if (previous !== null && previous !== signature) key = identifier();
        previous = signature; command.request_id = key;
        busy = true; button.disabled = true;
        output.textContent = photo ? "Vérification et enregistrement de la photo…" : "Enregistrement…";
        const controller = new AbortController(), timeout = setTimeout(() => controller.abort(), 45000);
        let response;
        try {
          response = await fetch(photo ? "/api/v1/cultures/journal/photos" : "/api/v1/cultures/journal", {method: "POST",
            headers: {"X-CSRF-Token": csrf, "Content-Type": photo ? "application/octet-stream" : "application/json",
              ...(photo ? {"X-Culture-Metadata": encodeURIComponent(JSON.stringify(command))} : {})},
            body: photo ? body : JSON.stringify(command), signal: controller.signal});
        } finally { clearTimeout(timeout); }
        const result = await response.json().catch(() => ({error: "Requête refusée. Vérifier la connexion et la taille de l’envoi."}));
        if (!response.ok) throw new Error(`${result.error} Saisie conservée.${response.status === 409 ? " Ouvrir la version actuelle dans un nouvel onglet." : ""}`);
        output.textContent = "Enregistré. Actualisation…";
        // Les filtres restent ceux de la page ; seul le repère d'opération est ajouté pour
        // retrouver l'entrée à travers la pagination.
        const next = new URL(location.href);
        next.searchParams.delete("offset");
        next.searchParams.set("focus", photo ? form.dataset.id : result.id);
        next.hash = `entry-${photo ? form.dataset.id : result.id}`;
        if (next.search === location.search) { location.hash = next.hash; location.reload(); }
        else location.assign(next.href);
      } catch (error) {
        output.textContent = error instanceof TypeError || error.name === "AbortError"
          ? "Réponse non reçue. Saisie conservée : réessayer sans modification pour vérifier le même enregistrement."
          : error.message;
      } finally { busy = false; button.disabled = false; }
    });
  });
  // Consultation hors ligne : inventaire daté des pages du carnet réellement conservées.
  // Aucune requête n'est émise ici et aucune mutation n'est rejouée.
  const offlineSnapshot = document.querySelector('meta[name="phyto-offline-snapshot"]');
  const inventory = async () => {
    const entries = [];
    if (!("caches" in window)) return null;
    try {
      for (const name of await caches.keys()) {
        if (!name.startsWith("phyto-cultures-")) continue;
        const cache = await caches.open(name);
        for (const request of await cache.keys()) {
          const response = await cache.match(request.url);
          entries.push({url: request.url, at: Number(response?.headers.get("X-Phyto-Cached-At")) || 0});
        }
      }
    } catch (_error) { return null; }
    return entries;
  };
  const label = url => {
    const target = new URL(url);
    const pages = {"/cultures/journal": "Journal du carnet", "/cultures/cycles": "Cycles et rappels",
      "/cultures/solutions": "Solutions et relevés", "/cultures": "Cultures et archives"};
    const page = pages[target.pathname] || "Fiche de culture";
    const filtered = ["start", "end", "target", "type"].some(key => target.searchParams.get(key));
    return filtered ? `${page} · filtre conservé` : page;
  };
  const container = document.querySelector("[data-culture-offline-index]");
  if (container) (async () => {
    const entries = await inventory();
    container.textContent = "";
    if (entries === null) {
      const p = document.createElement("p");
      p.textContent = "Inventaire hors ligne indisponible dans ce navigateur.";
      container.append(p); return;
    }
    if (!entries.length) {
      const p = document.createElement("p");
      p.textContent = "Aucune page du carnet n’est conservée hors ligne pour l’instant.";
      container.append(p); return;
    }
    const list = document.createElement("ul");
    for (const entry of entries.sort((a, b) => b.at - a.at)) {
      const item = document.createElement("li"), link = document.createElement("a");
      link.href = entry.url; link.textContent = label(entry.url);
      item.append(link, document.createTextNode(` · conservée le ${entry.at ? new Date(entry.at).toLocaleString("fr-FR") : "date inconnue"}`));
      list.append(item);
    }
    container.append(list);
    if (!offlineSnapshot) return;
    // Hors ligne, un lien vers une page jamais visitée le dit au lieu d'échouer.
    const known = new Set(entries.map(entry => entry.url));
    document.querySelectorAll("[data-journal-offset], [data-culture-page]").forEach(link => {
      if (known.has(link.href.split("#")[0])) return;
      link.setAttribute("aria-disabled", "true");
      link.classList.add("culture-unavailable");
      link.append(document.createTextNode(" · non conservé hors ligne"));
      link.addEventListener("click", event => { event.preventDefault(); });
    });
  })();
})();
