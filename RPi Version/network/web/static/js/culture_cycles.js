(() => {
  "use strict";
  // Un lien d'assistance ouvre la vérification du bon sujet, sans cocher de case.
  const openChecks = () => {
    if (!location.hash.startsWith("#verifications-")) return;
    const node = document.getElementById(location.hash.slice(1));
    if (node?.tagName === "DETAILS") { node.open = true; node.querySelector("summary")?.focus(); }
  };
  openChecks(); addEventListener("hashchange", openChecks);
  // Envoi, clé d'idempotence et restitution des refus : le socle partagé. Les rappels, les
  // vérifications et les photos rendaient auparavant leurs refus dans la seule zone d'état,
  // sans champ désigné ni annonce ; le texte des messages, lui, ne change pas.
  const forms = window.PhytoCultureForms;
  document.querySelectorAll("[data-cycle-offset]").forEach(link => {
    const query = new URLSearchParams(location.search); query.set("offset", link.dataset.cycleOffset); link.search = query.toString();
  });
  document.querySelectorAll("[data-climate-offset]").forEach(link => {
    const query = new URLSearchParams(location.search); query.set("climate_offset", link.dataset.climateOffset);
    query.delete("climate_at"); link.search = query.toString();
  });
  document.querySelectorAll("[data-cycle-form], [data-photo-form]").forEach(form => {
    forms.register(form);
    const get = name => form.elements[name]?.value || "";
    form.addEventListener("submit", async event => {
      event.preventDefault();
      const photo = form.hasAttribute("data-photo-form");
      const command = {confirm_date: form.elements.confirm_date?.checked || false};
      let file = null;
      if (photo) {
        file = form.elements.photo.files[0];
        // Refus local : il désigne le champ fautif comme n'importe quel refus du serveur.
        if (!file || file.size > 5 * 1024 * 1024) {
          forms.showError(form, {error: "Choisir une photo de 5 Mio maximum.", field: "photo"});
          return;
        }
        Object.assign(command, {subject_id: form.dataset.subject, event_id: form.dataset.event,
          event_revision: Number(form.dataset.revision), caption: get("caption")});
      } else {
        command.operation = form.dataset.operation;
        if (form.dataset.id) Object.assign(command, {id: form.dataset.id, version: Number(form.dataset.version)});
        if (command.operation === "reminder") Object.assign(command, {title: get("title"), target: get("target"), due_date: get("due_date"), interval_days: Number(get("interval_days")), note: get("note")});
        if (command.operation === "reminder_action") Object.assign(command, {action: get("action"), due_date: get("due_date"), note: get("note")});
        if (command.operation === "checklist") Object.assign(command, {subject_id: form.dataset.subject, version: Number(form.dataset.version),
          effective_at: get("effective_at"), note: get("note"), checks: Object.fromEntries(["lighting", "pump", "ventilation"].map(name => [name, form.elements[name].checked]))});
        // Une correction rejoue la saisie entière avec son motif ; une annulation ne porte
        // que le motif. Aucune des deux ne commande d'équipement.
        if (command.operation === "checklist_correct") Object.assign(command, {effective_at: get("effective_at"), note: get("note"), reason: get("reason"),
          checks: Object.fromEntries(["lighting", "pump", "ventilation"].map(name => [name, form.elements[name].checked]))});
        if (command.operation === "checklist_cancel") Object.assign(command, {reason: get("reason")});
      }
      forms.clearErrors(form);
      forms.status(form, photo ? "Vérification et enregistrement de la photo…" : "Enregistrement…");
      // La clé d'idempotence est celle du socle : elle survit à un renvoi identique et change
      // dès que la saisie — ou le fichier choisi — change.
      const answer = photo
        ? await forms.submitBinary(form, "/api/v1/cultures/photos", file, command, {timeoutMs: 45000})
        : await forms.submitJson(form, "/api/v1/cultures/cycles", command, {timeoutMs: 45000});
      // Hors ligne et envoi déjà en vol : le socle a posé son message, la saisie reste intacte.
      if (answer.offline || answer.busy) return;
      if (!answer.ok) {
        const data = answer.data || {};
        // Sans réponse HTTP il n'y a pas de refus à qualifier : le message du socle dit déjà
        // que la saisie est conservée, l'y répéter en ferait deux.
        forms.showError(form, {...data, error: answer.status
          ? `${data.error} Saisie conservée.${answer.status === 409 ? " Ouvrir la fiche actuelle dans un nouvel onglet." : ""}`
          : data.error});
        return;
      }
      const result = answer.data;
      forms.status(form, "Enregistré. Actualisation…");
      const next = new URL(location.href);
      if (!photo && command.operation.startsWith("reminder") && form.dataset.cycleReturn === "agenda") {
        // Accueil : ni pagination ni sélection à rétablir, seule l'ancre du rappel change.
        next.hash = `reminder-${result.id}`;
      } else if (!photo && command.operation.startsWith("reminder")) {
        next.searchParams.delete("offset");
        next.searchParams.set("reminder", result.id);
        if (command.operation === "reminder") {
          next.searchParams.delete("subject");
          if (!["reservoir_2", "cuttings_1"].includes(command.target)) next.searchParams.set("subject", command.target);
        }
        next.hash = `reminder-${result.id}`;
      }
      if (next.search === location.search) { location.hash = next.hash; location.reload(); }
      else location.assign(next.href);
    });
  });
  const node = (name, attrs = {}, text) => {
    const el = document.createElementNS("http://www.w3.org/2000/svg", name);
    for (const [key, value] of Object.entries(attrs)) el.setAttribute(key, String(value));
    if (text !== undefined) el.textContent = text;
    return el;
  };
  document.querySelectorAll("[data-climate-chart]").forEach(container => {
    const points = JSON.parse(container.dataset.climateChart), sensors = [...new Set(points.map(p => p.sensor))];
    const granularity = container.dataset.climateGranularity || "période";
    if (!sensors.length) { const p = document.createElement("p"); p.textContent = "Aucune synthèse climatique disponible pour ce cycle."; container.append(p); }
    for (const sensor of sensors) {
      const all = points.filter(p => p.sensor === sensor), valid = all.filter(p => p.mean !== null);
      const figure = document.createElement("figure"), caption = document.createElement("figcaption"); figure.className = "card solution-chart";
      const missing = all.filter(p => p.missing);
      caption.textContent = `${all[0].label} (${all[0].unit}) · commun à la serre · synthèse par ${granularity} · ${valid.length} période(s) avec valeur fiable, ${missing.length} lacune(s) sur ${all.length}`;
      const svg = node("svg", {viewBox: "0 0 600 240", role: "img", "aria-label": caption.textContent}); figure.append(caption, svg); container.append(figure);
      const draw = () => {
        svg.replaceChildren();
        const width = svg.getBoundingClientRect().width || 240, right = width - 20;
        svg.setAttribute("viewBox", `0 0 ${width} 255`);
        if (!valid.length) { svg.append(node("text", {x: 30, y: 100}, "Aucune valeur fiable")); return; }
        const start = Math.min(...all.map(p => p.hour)), end = Math.max(...all.map(p => p.hour));
        const min = Math.min(...valid.map(p => p.minimum)), max = Math.max(...valid.map(p => p.maximum));
        const x = p => 65 + (right - 65) * (end === start ? 0.5 : (p.hour - start) / (end - start));
        const y = value => 175 - 120 * (min === max ? 0.5 : (value - min) / (max - min));
        svg.append(node("path", {d: `M65 30V185H${right}`, class: "solution-axis"}), node("text", {x: 0, y: 55}, max.toFixed(1)), node("text", {x: 0, y: 175}, min.toFixed(1)));
        svg.append(node("text", {x: 65, y: 220}, new Date(start*1000).toLocaleDateString("fr-FR")), node("text", {x: right, y: 238, "text-anchor": "end"}, new Date(end*1000).toLocaleDateString("fr-FR")));
        // Les barres min/max et points moyens ne relient jamais une lacune.
        for (const p of valid) {
          const line = node("path", {d: `M${x(p)} ${y(p.minimum)}V${y(p.maximum)}`, class: "solution-range"});
          const dot = node("circle", {cx: x(p), cy: y(p.mean), r: 3, class: "solution-dot"});
          dot.append(node("title", {}, `${p.at} : ${p.mean.toFixed(2)} ${p.unit}, min ${p.minimum}, max ${p.maximum}, ${p.valid_count} valeurs fiables sur ${p.span_hours} h de période, couverture ${(p.coverage*100).toFixed(0)} %`)); svg.append(line, dot);
        }
        // Une période sans agrégat reste une lacune signalée, jamais une valeur nulle tracée.
        for (const p of missing) {
          const tick = node("path", {d: `M${x(p)} 185V193`, class: "climate-gap"});
          tick.append(node("title", {}, `${p.at} : aucun agrégat sur ${p.span_hours} h de période`)); svg.append(tick);
        }
      };
      let lastWidth = 0;
      new ResizeObserver(() => {
        const width = svg.getBoundingClientRect().width;
        if (Math.abs(width - lastWidth) < 1) return;
        lastWidth = width; draw();
      }).observe(svg);
      draw();
    }
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
    const page = target.pathname === "/cultures/cycles" ? "Cycles et rappels" : target.pathname === "/cultures/solutions" ? "Solutions et relevés" : target.pathname === "/cultures" ? "Cultures et archives" : "Fiche de culture";
    const detail = target.searchParams.get("climate_offset");
    return detail === null ? page : `${page} · détail horaire à partir de l’agrégat ${Number(detail) + 1}`;
  };
  const container = document.querySelector("[data-culture-offline-index]");
  if (container) (async () => {
    const entries = await inventory();
    container.textContent = "";
    if (entries === null) { const p = document.createElement("p"); p.textContent = "Inventaire hors ligne indisponible dans ce navigateur."; container.append(p); return; }
    if (!entries.length) { const p = document.createElement("p"); p.textContent = "Aucune page du carnet n’est conservée hors ligne pour l’instant."; container.append(p); return; }
    const list = document.createElement("ul");
    for (const entry of entries.sort((a, b) => b.at - a.at)) {
      const item = document.createElement("li"), link = document.createElement("a");
      link.href = entry.url; link.textContent = label(entry.url);
      item.append(link, document.createTextNode(` · conservée le ${entry.at ? new Date(entry.at).toLocaleString("fr-FR") : "date inconnue"}`));
      list.append(item);
    }
    container.append(list);
    if (!offlineSnapshot) return;
    const known = new Set(entries.map(entry => entry.url));
    document.querySelectorAll("[data-climate-offset], [data-cycle-offset], [data-culture-page]").forEach(link => {
      if (known.has(link.href.split("#")[0])) return;
      link.setAttribute("aria-disabled", "true");
      link.classList.add("culture-unavailable");
      link.append(document.createTextNode(" · non conservé hors ligne"));
      link.addEventListener("click", event => { event.preventDefault(); });
    });
  })();
})();
