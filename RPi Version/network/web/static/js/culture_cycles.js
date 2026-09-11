(() => {
  "use strict";
  const currentRubric = document.querySelector(".culture-navigation [aria-current=page]");
  if (currentRubric) requestAnimationFrame(() => currentRubric.scrollIntoView({block: "nearest", inline: "nearest"}));
  // Un lien d'assistance ouvre la vérification du bon sujet, sans cocher de case.
  const openChecks = () => {
    if (!location.hash.startsWith("#verifications-")) return;
    // Le fragment est encodé dans l'URL comme dans les autres pages du carnet : un
    // identifiant de sujet non ASCII s'y lit percent-encodé, jamais tel quel.
    let node = null;
    try { node = document.getElementById(decodeURIComponent(location.hash.slice(1))); } catch { node = null; }
    if (node?.tagName === "DETAILS") { node.open = true; node.querySelector("summary")?.focus(); }
  };
  openChecks(); addEventListener("hashchange", openChecks);
  // Envoi, clé d'idempotence et restitution des refus : le socle partagé. Les rappels, les
  // vérifications et les photos rendaient auparavant leurs refus dans la seule zone d'état,
  // sans champ désigné ni annonce ; le texte des messages, lui, ne change pas.
  const forms = window.PhytoCultureForms;
  document.querySelectorAll("[data-selection-offset]").forEach(link => {
    const query = new URLSearchParams(location.search); query.set("selection_offset", link.dataset.selectionOffset);
    link.search = query.toString(); link.hash = "comparaison";
    link.addEventListener("click", () => {
      query.delete("subject");
      document.querySelectorAll('[data-comparison-selection] [name="subject"]:checked').forEach(input => query.append("subject", input.value));
      link.search = query.toString();
    });
  });
  document.querySelectorAll("[data-cycle-offset]").forEach(link => {
    const query = new URLSearchParams(location.search); query.set("offset", link.dataset.cycleOffset); link.search = query.toString();
  });
  document.querySelectorAll("[data-climate-offset]").forEach(link => {
    const query = new URLSearchParams(location.search); query.set("climate_offset", link.dataset.climateOffset);
    query.delete("climate_at"); link.search = query.toString();
  });
  // Carte de rappel : « Fait » et « Reporter » sont deux boutons d'envoi du même
  // formulaire, sur l'accueil comme sur cette page. Le champ de nouvelle échéance est rendu
  // visible — sans script, personne ne l'ouvrirait —, c'est donc ici qu'il est replié : le
  // premier clic sur « Reporter » l'ouvre et y pose le focus sans rien envoyer, le suivant
  // envoie. Annuler le clic suffit à retenir l'envoi, il n'y a rien à mémoriser.
  // Le bouton par défaut du formulaire (soumission implicite) est le « Reporter » masqué du
  // gabarit ; il n'est pas ce bouton visible, d'où le `:not([hidden])`.
  document.querySelectorAll('[data-operation="reminder_action"]').forEach(form => {
    const zone = form.querySelector("[data-reminder-postpone]");
    const postpone = form.querySelector('[data-reminder-action="postponed"]:not([hidden])');
    if (!zone || !postpone) return;
    zone.hidden = true;
    postpone.addEventListener("click", event => {
      if (!zone.hidden) return;
      event.preventDefault();
      zone.hidden = false;
      zone.querySelector("input")?.focus();
    });
  });
  document.querySelectorAll("[data-cycle-form], [data-photo-form]").forEach(form => {
    forms.register(form);
    const get = name => form.elements[name]?.value || "";
    form.addEventListener("submit", async event => {
      event.preventDefault();
      // Un suivi de rappel n'a de sens que déclenché par l'un de ses boutons d'action :
      // « Fait », « Reporter » ou « Annuler ». Une soumission sans bouton nommé — un
      // navigateur qui n'en désigne aucun, un script tiers — prendrait l'action du premier
      // bouton d'envoi, et clore un rappel n'a pas de retour en arrière. Mieux vaut
      // redemander le geste que d'en deviner un.
      if (form.dataset.operation === "reminder_action"
          && !event.submitter?.hasAttribute("data-reminder-action")) {
        forms.showError(form, {error: "Choisir « Fait » ou « Reporter »."});
        return;
      }
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
        // Deux boutons « Fait » / « Reporter » portent le nom `action` : la valeur est celle
        // du bouton déclencheur, jamais celle d'une collection de contrôles homonymes.
        if (command.operation === "reminder_action") Object.assign(command, {action: event.submitter?.value || get("action"), due_date: get("due_date"), note: get("note")});
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
  // Règle d'arrondi unique côté navigateur : `formatNombre` de `culture_analysis.js` (virgule
  // française, décimales bornées, pas de séparateur de milliers). Le dessin ne dépend pourtant
  // jamais de cet asset : s'il manque (précache partiel, 404 après déploiement), les textes du
  // dessin reprennent **les mêmes options** `toLocaleString`, jamais la valeur brute.
  const nombre = (value, decimals) => {
    if (window.PhytoCultureAnalysis?.formatNombre) return window.PhytoCultureAnalysis.formatNombre(value, decimals);
    if (value === null || value === undefined || !Number.isFinite(Number(value))) return "—";
    return Number(value).toLocaleString("fr-FR", {useGrouping: false, minimumFractionDigits: decimals, maximumFractionDigits: decimals});
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
      // Tableau équivalent : mêmes colonnes que les courbes de solutions ; une période sans
      // agrégat s'écrit « mesure absente », jamais 0.
      const columns = ["Date", "Valeur", "Unité", "Cible ou capteur", "Période", "Agrégats", "Lacune"];
      const cells = p => [
        p.at,
        p.mean === null ? "mesure absente" : nombre(p.mean, 2),
        p.unit,
        `${p.label} · commun à la serre`,
        `${p.span_hours} h`,
        p.mean === null
          ? "aucun agrégat"
          : `min ${nombre(p.minimum, 2)}, max ${nombre(p.maximum, 2)}, ${p.valid_count} valeurs fiables, couverture ${nombre(p.coverage * 100, 0)} %`,
        p.missing ? "oui" : "non",
      ];
      const rows = all.map(p => ({cells: cells(p), text: `${p.at} · ${p.mean === null ? "Aucune valeur fiable — lacune" : `${nombre(p.mean, 2)} ${p.unit}, min ${nombre(p.minimum, 2)}, max ${nombre(p.maximum, 2)}`} · ${p.valid_count} valeurs fiables sur ${p.span_hours} h · couverture ${nombre(p.coverage * 100, 0)} %`}));
      // Le dessin ne dépend jamais de l'explorateur : un asset manquant ne doit pas
      // interrompre ce script, qui rend aussi l'inventaire hors ligne plus bas.
      const refreshSelection = window.PhytoCultureAnalysis?.chart?.(svg, rows, caption.textContent, columns) ?? (() => {});
      const draw = () => {
        svg.replaceChildren();
        const width = svg.getBoundingClientRect().width || 240, right = width - 20;
        svg.setAttribute("viewBox", `0 0 ${width} 255`);
        if (!valid.length) { svg.append(node("text", {x: 30, y: 100}, "Aucune valeur fiable")); refreshSelection([]); return; }
        const start = Math.min(...all.map(p => p.hour)), end = Math.max(...all.map(p => p.hour));
        const min = Math.min(...valid.map(p => p.minimum)), max = Math.max(...valid.map(p => p.maximum));
        const x = p => 65 + (right - 65) * (end === start ? 0.5 : (p.hour - start) / (end - start));
        const y = value => 175 - 120 * (min === max ? 0.5 : (value - min) / (max - min));
        svg.append(node("path", {d: `M65 30V185H${right}`, class: "solution-axis"}), node("text", {x: 0, y: 55}, nombre(max, 1)), node("text", {x: 0, y: 175}, nombre(min, 1)));
        svg.append(node("text", {x: 65, y: 220}, new Date(start*1000).toLocaleDateString("fr-FR")), node("text", {x: right, y: 238, "text-anchor": "end"}, new Date(end*1000).toLocaleDateString("fr-FR")));
        // Les barres min/max et points moyens ne relient jamais une lacune. L'index vient
        // de la boucle : `all.indexOf(p)` coûtait un balayage complet par point dessiné.
        const places = [];
        all.forEach((p, i) => {
          if (p.mean === null) return;
          const line = node("path", {d: `M${x(p)} ${y(p.minimum)}V${y(p.maximum)}`, class: "solution-range"});
          const dot = node("circle", {cx: x(p), cy: y(p.mean), r: 3, class: "solution-dot", "data-analysis-index": i});
          dot.append(node("title", {}, `${p.at} : ${nombre(p.mean, 2)} ${p.unit}, min ${nombre(p.minimum, 2)}, max ${nombre(p.maximum, 2)}, ${p.valid_count} valeurs fiables sur ${p.span_hours} h de période, couverture ${nombre(p.coverage * 100, 0)} %`)); svg.append(line, dot);
          places[i] = {x: x(p), y: y(p.mean)};
        });
        // Une période sans agrégat reste une lacune signalée, jamais une valeur nulle tracée.
        all.forEach((p, i) => {
          if (!p.missing) return;
          const tick = node("path", {d: `M${x(p)} 185V193`, class: "climate-gap", "data-analysis-index": i});
          tick.append(node("title", {}, `${p.at} : aucun agrégat sur ${p.span_hours} h de période`)); svg.append(tick);
          places[i] = {x: x(p), y: 189};
        });
        refreshSelection(places);
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
})();
