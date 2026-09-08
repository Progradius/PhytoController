(() => {
  "use strict";
  const csrf = document.querySelector('meta[name="csrf-token"]')?.content;
  const identifier = () => Array.from(crypto.getRandomValues(new Uint8Array(20)), n => n.toString(16).padStart(2, "0")).join("");
  document.querySelectorAll("[data-cycle-offset]").forEach(link => {
    const query = new URLSearchParams(location.search); query.set("offset", link.dataset.cycleOffset); link.search = query.toString();
  });
  document.querySelectorAll("[data-cycle-form], [data-photo-form]").forEach(form => {
    let busy = false, previous = null, key = identifier();
    const get = name => form.elements[name]?.value || "";
    form.addEventListener("submit", async event => {
      event.preventDefault();
      if (busy) return;
      const output = form.querySelector("output"), button = form.querySelector('[type="submit"]');
      if (!navigator.onLine || document.body.classList.contains("is-offline")) { output.textContent = "Hors ligne : saisie conservée dans cette page, aucun envoi en attente."; return; }
      try {
        const photo = form.hasAttribute("data-photo-form");
        const command = {confirm_date: form.elements.confirm_date?.checked || false};
        let body;
        if (photo) {
          const file = form.elements.photo.files[0];
          if (!file || file.size > 5 * 1024 * 1024) throw new Error("Choisir une photo de 5 Mio maximum.");
          Object.assign(command, {subject_id: form.dataset.subject, event_id: form.dataset.event,
            event_revision: Number(form.dataset.revision), caption: get("caption")});
          body = file;
        } else {
          command.operation = form.dataset.operation;
          if (form.dataset.id) Object.assign(command, {id: form.dataset.id, version: Number(form.dataset.version)});
          if (command.operation === "reminder") Object.assign(command, {title: get("title"), target: get("target"), due_date: get("due_date"), interval_days: Number(get("interval_days")), note: get("note")});
          if (command.operation === "reminder_action") Object.assign(command, {action: get("action"), due_date: get("due_date"), note: get("note")});
          if (command.operation === "checklist") Object.assign(command, {subject_id: form.dataset.subject, version: Number(form.dataset.version),
            effective_at: get("effective_at"), note: get("note"), checks: Object.fromEntries(["lighting", "pump", "ventilation"].map(name => [name, form.elements[name].checked]))});
        }
        // L'identité du fichier fait partie de la saisie ; le serveur vérifie aussi son empreinte.
        const signature = JSON.stringify(command) + (photo ? `${body.name}:${body.size}:${body.lastModified}` : "");
        if (previous !== null && previous !== signature) key = identifier();
        previous = signature; command.request_id = key;
        busy = true; button.disabled = true; output.textContent = photo ? "Vérification et enregistrement de la photo…" : "Enregistrement…";
        const controller = new AbortController(), timeout = setTimeout(() => controller.abort(), 45000);
        let response;
        try {
          response = await fetch(photo ? "/api/v1/cultures/photos" : "/api/v1/cultures/cycles", {method: "POST",
            headers: {"X-CSRF-Token": csrf, "Content-Type": photo ? "application/octet-stream" : "application/json",
              ...(photo ? {"X-Culture-Metadata": encodeURIComponent(JSON.stringify(command))} : {})},
            body: photo ? body : JSON.stringify(command), signal: controller.signal});
        } finally { clearTimeout(timeout); }
        const result = await response.json().catch(() => ({error: "Requête refusée. Vérifier la connexion et la taille de l’envoi."}));
        if (!response.ok) throw new Error(`${result.error} Saisie conservée.${response.status === 409 ? " Ouvrir la fiche actuelle dans un nouvel onglet." : ""}`);
        output.textContent = "Enregistré. Actualisation…";
        const next = new URL(location.href);
        if (!photo && command.operation.startsWith("reminder")) {
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
      } catch (error) {
        output.textContent = error instanceof TypeError || error.name === "AbortError" ? "Réponse non reçue. Saisie conservée : réessayer sans modification pour vérifier le même enregistrement." : error.message;
      } finally { busy = false; button.disabled = false; }
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
    if (!sensors.length) { const p = document.createElement("p"); p.textContent = "Aucune synthèse climatique disponible pour ce cycle."; container.append(p); }
    for (const sensor of sensors) {
      const all = points.filter(p => p.sensor === sensor), valid = all.filter(p => p.mean !== null);
      const figure = document.createElement("figure"), caption = document.createElement("figcaption"); figure.className = "card solution-chart";
      caption.textContent = `${all[0].label} (${all[0].unit}) · commun à la serre`;
      const svg = node("svg", {viewBox: "0 0 600 240", role: "img", "aria-label": caption.textContent}); figure.append(caption, svg); container.append(figure);
      if (!valid.length) { svg.append(node("text", {x: 30, y: 100}, "Aucune valeur fiable")); continue; }
      const start = Math.min(...all.map(p => p.hour)), end = Math.max(...all.map(p => p.hour));
      const min = Math.min(...valid.map(p => p.minimum)), max = Math.max(...valid.map(p => p.maximum));
      const x = p => 65 + 470 * (end === start ? 0.5 : (p.hour - start) / (end - start));
      const y = value => 175 - 120 * (min === max ? 0.5 : (value - min) / (max - min));
      svg.append(node("path", {d: "M65 30V185H550", class: "solution-axis"}), node("text", {x: 0, y: 55}, max.toFixed(1)), node("text", {x: 0, y: 175}, min.toFixed(1)));
      svg.append(node("text", {x: 65, y: 220}, new Date(start*1000).toLocaleDateString("fr-FR")), node("text", {x: 450, y: 220}, new Date(end*1000).toLocaleDateString("fr-FR")));
      // Les barres min/max et points moyens ne relient jamais une lacune.
      for (const p of valid) {
        const line = node("path", {d: `M${x(p)} ${y(p.minimum)}V${y(p.maximum)}`, class: "solution-range"});
        const dot = node("circle", {cx: x(p), cy: y(p.mean), r: 3, class: "solution-dot"});
        dot.append(node("title", {}, `${p.at} : ${p.mean.toFixed(2)} ${p.unit}, min ${p.minimum}, max ${p.maximum}, ${p.valid_count} valeurs fiables, couverture ${(p.coverage*100).toFixed(0)} %`)); svg.append(line, dot);
      }
    }
  });
})();
