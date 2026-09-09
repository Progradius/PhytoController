(() => {
  "use strict";
  // Lot H : saisie, correction et photo d'une observation d'espace, plus l'inventaire daté
  // des pages du carnet conservées hors ligne. Aucune mutation n'est mise en attente.
  // La pagination conserve les filtres : seul le décalage change dans l'adresse courante.
  document.querySelectorAll("[data-journal-offset]").forEach(link => {
    const query = new URLSearchParams(location.search);
    query.set("offset", link.dataset.journalOffset);
    query.delete("focus");
    link.search = query.toString();
  });
  // Envoi, clé d'idempotence, garde hors ligne et restitution des refus : le socle partagé.
  // L'observation et sa photo suivent désormais le même chemin que le reste du carnet ;
  // le texte des messages, lui, ne change pas.
  const forms = window.PhytoCultureForms;
  document.querySelectorAll("[data-journal-form], [data-journal-photo]").forEach(form => {
    forms.register(form);
    const get = name => form.elements[name]?.value || "";
    form.addEventListener("submit", async event => {
      event.preventDefault();
      const photo = form.hasAttribute("data-journal-photo");
      const command = {confirm_date: form.elements.confirm_date?.checked || false};
      let file = null;
      if (photo) {
        file = form.elements.photo.files[0];
        // Refus local : il désigne le champ fautif comme n'importe quel refus du serveur.
        if (!file || file.size > 5 * 1024 * 1024) {
          forms.showError(form, {error: "Choisir une photo de 5 Mio maximum.", field: "photo"});
          return;
        }
        Object.assign(command, {space_event_id: form.dataset.id, space_event_revision: Number(form.dataset.version),
          caption: get("caption")});
      } else {
        command.operation = form.dataset.operation;
        Object.assign(command, {effective_at: get("effective_at"), note: get("note")});
        if (command.operation === "space_event") Object.assign(command, {space: get("space"), kind: get("kind"), precision: get("precision")});
        else Object.assign(command, {id: form.dataset.id, version: Number(form.dataset.version),
          reason: get("reason"), cancelled: form.elements.cancelled?.checked || false});
      }
      forms.clearErrors(form);
      forms.status(form, photo ? "Vérification et enregistrement de la photo…" : "Enregistrement…");
      // La clé d'idempotence est celle du socle : elle survit à un renvoi identique et change
      // dès que la saisie — ou le fichier choisi — change.
      const answer = photo
        ? await forms.submitBinary(form, "/api/v1/cultures/journal/photos", file, command, {timeoutMs: 45000})
        : await forms.submitJson(form, "/api/v1/cultures/journal", command, {timeoutMs: 45000});
      // Hors ligne et envoi déjà en vol : le socle a posé son message, la saisie reste intacte.
      if (answer.offline || answer.busy || answer.preview) return;
      if (!answer.ok) {
        const data = answer.data || {};
        // Sans réponse HTTP il n'y a pas de refus à qualifier : le message du socle dit déjà
        // que la saisie est conservée, l'y répéter en ferait deux.
        forms.showError(form, {...data, error: answer.status
          ? `${data.error} Saisie conservée.${answer.status === 409 ? " Ouvrir la version actuelle dans un nouvel onglet." : ""}`
          : data.error});
        return;
      }
      const result = answer.data;
      forms.status(form, "Enregistré. Actualisation…");
      // Les filtres restent ceux de la page ; seul le repère d'opération est ajouté pour
      // retrouver l'entrée à travers la pagination.
      const next = new URL(location.href);
      next.searchParams.delete("offset");
      next.searchParams.set("focus", photo ? form.dataset.id : result.id);
      next.hash = `entry-${photo ? form.dataset.id : result.id}`;
      if (next.search === location.search) { location.hash = next.hash; location.reload(); }
      else location.assign(next.href);
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
