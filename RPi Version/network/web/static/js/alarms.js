(() => {
  "use strict";

  const severityLabels = {warning: "Avertissement", error: "Erreur", critical: "Critique"};
  const categoryLabels = {control: "Contrôle", sensor: "Capteur", storage: "Stockage", network: "Réseau", system: "Système"};

  const duration = (seconds) => {
    if (seconds < 60) return `${Math.round(seconds)} s`;
    if (seconds < 3600) return `${Math.round(seconds / 60)} min`;
    if (seconds < 86400) return `${(seconds / 3600).toFixed(1)} h`;
    return `${(seconds / 86400).toFixed(1)} j`;
  };

  const localizeTimes = (root = document) => {
    root.querySelectorAll("time[data-timestamp]").forEach((node) => {
      node.textContent = new Date(Number(node.dataset.timestamp) * 1000).toLocaleString("fr-FR");
    });
    root.querySelectorAll("[data-duration]").forEach((node) => {
      node.textContent = duration(Number(node.dataset.duration));
    });
  };

  const storageKey = "phyto-operator-alias";
  const rememberedAlias = () => {
    try { return window.localStorage.getItem(storageKey) || ""; }
    catch (_error) { return ""; }
  };

  const configureAcknowledgements = (root = document) => {
    root.querySelectorAll(".alarm-ack-form").forEach((form) => {
      if (form.dataset.configured === "true") return;
      form.dataset.configured = "true";
      const input = form.querySelector('input[name="alias"]');
      if (input && rememberedAlias()) input.value = rememberedAlias();
      form.addEventListener("submit", () => {
        if (!input) return;
        try { window.localStorage.setItem(storageKey, input.value); }
        catch (_error) { /* stockage facultatif */ }
      });
    });
  };

  // `value` est soit un texte, soit un `<dd>` déjà construit (quand il porte ses propres
  // classes ou attributs), soit un nœud à placer dans un `<dd>` nu — les trois formes
  // que le gabarit produit.
  const fact = (label, value) => {
    const wrapper = document.createElement("div");
    const term = document.createElement("dt"); term.textContent = label;
    let detail;
    if (value instanceof HTMLElement && value.tagName === "DD") detail = value;
    else {
      detail = document.createElement("dd");
      if (value instanceof Node) detail.append(value); else detail.textContent = value;
    }
    wrapper.append(term, detail);
    return wrapper;
  };

  // Contrat de balisage d'une occurrence — UNE seule définition, partagée par le rendu
  // serveur et le flux vivant :
  //
  //   <article class="alarm-card severity-…" data-alarm-id>
  //     <div class="alarm-card-heading">…</div>
  //     <div class="ui-alarm-summary"><h2/><p/><p/></div>   ← macro `alarm_summary`
  //     <div class="alarm-actions">…</div>                   ← l'action suit l'avis qu'elle exécute
  //     <details [open]><summary>Détails techniques</summary>…</details>
  //   </article>
  //
  // Le serveur le produit par la macro `templates/macros/ui.html`, ce fichier le
  // reconstruit à l'identique. Un fragment HTML servi par une route dédiée aurait été
  // l'autre façon d'avoir une source unique, mais le flux vivant arrive déjà en JSON
  // (`phyto:alarm-feed`) : il aurait fallu une requête HTTP de plus à chaque tick, et un
  // rendu serveur pour un contenu que le client possède déjà. L'équivalence des deux
  // rendus est vérifiée par `tests/ui/dashboard.spec.js` (« le flux vivant rend
  // exactement le balisage du serveur »), qui compare les deux arbres.
  // Date de la copie locale, transmise par `pwa.js` avec le flux (`detail.receivedAt`).
  // Elle n'est jamais remplacée par l'heure courante : dater une copie de « maintenant »
  // dirait exactement le contraire de ce que l'étiquette annonce. Absente, la mention
  // reste exacte, seulement moins précise.
  let dateCopie = null;
  const copieDatee = () => (dateCopie
    ? `Copie datée du ${new Date(dateCopie).toLocaleString("fr-FR")} · état non actualisé`
    : "Copie datée · état non actualisé");

  const alarmSummaryBlock = (alarm) => {
    const block = document.createElement("div"); block.className = "ui-alarm-summary";
    const title = document.createElement("h2"); title.textContent = alarm.title;
    const consequence = document.createElement("p");
    consequence.textContent = `Conséquence : ${alarm.consequence || "—"}`;
    const advice = document.createElement("p");
    advice.textContent = `Action conseillée : ${alarm.advice || "—"}`;
    block.append(title, consequence, advice);
    return block;
  };

  const createAlarmCard = (alarm, source, primary = false) => {
    const card = document.createElement("article");
    card.className = `alarm-card severity-${alarm.severity}`;
    card.dataset.alarmId = alarm.id;

    const heading = document.createElement("div"); heading.className = "alarm-card-heading";
    const labels = document.createElement("div");
    const severity = document.createElement("span"); severity.className = "alarm-severity"; severity.textContent = severityLabels[alarm.severity] || alarm.severity;
    const category = document.createElement("span"); category.className = "alarm-category"; category.textContent = categoryLabels[alarm.category] || alarm.category;
    // « État non confirmé » faisait douter de l'alarme ; le doute porte sur la **fraîcheur**.
    // Le reste de la PWA dit « copie datée », et le glossaire veut la date avec la mention.
    const state = document.createElement("span");
    state.textContent = source === "stored" ? copieDatee() : alarm.acknowledged_ts ? "Active, acquittée" : "Active";
    labels.append(severity, category); heading.append(labels, state);

    card.append(heading, alarmSummaryBlock(alarm));

    // L'occurrence la plus importante — la première de la liste triée — est servie
    // développée, exactement comme le gabarit la rend.
    const technical = document.createElement("details");
    if (primary) technical.open = true;
    const technicalTitle = document.createElement("summary"); technicalTitle.textContent = "Détails techniques"; technical.append(technicalTitle);
    if (alarm.detail) {
      const detail = document.createElement("p"); detail.className = "alarm-detail"; detail.textContent = alarm.detail;
      technical.append(detail);
    }

    const started = document.createElement("time");
    started.className = "num";
    started.dataset.timestamp = String(alarm.started_ts);
    started.textContent = new Date(Number(alarm.started_ts) * 1000).toLocaleString("fr-FR");
    const elapsed = document.createElement("dd");
    elapsed.className = "num";
    elapsed.dataset.duration = String(alarm.duration_seconds || 0);
    elapsed.textContent = duration(Number(alarm.duration_seconds || 0));

    const facts = document.createElement("dl"); facts.className = "alarm-facts";
    facts.append(
      fact("Depuis", started),
      fact("Durée", elapsed),
      fact("Impact", alarm.affects_control ? "Contrôle" : "Auxiliaire")
    );
    technical.append(facts);

    // L'action précède les détails techniques, comme dans le gabarit.
    const actions = document.createElement("div"); actions.className = "alarm-actions";
    const link = document.createElement("a"); link.className = "button button-secondary action-link"; link.href = alarm.link || "/alarms"; link.textContent = "Diagnostiquer";
    actions.append(link);
    if (source === "stored") {
      const stale = document.createElement("span"); stale.className = "acknowledged"; stale.textContent = "Lecture seule hors ligne";
      actions.append(stale);
    } else if (!alarm.acknowledged_ts) {
      const csrf = document.querySelector('meta[name="csrf-token"]')?.content || "";
      const form = document.createElement("form"); form.method = "post"; form.action = "/actions/alarms/ack"; form.className = "alarm-ack-form";
      const token = document.createElement("input"); token.type = "hidden"; token.name = "csrf_token"; token.value = csrf;
      const occurrence = document.createElement("input"); occurrence.type = "hidden"; occurrence.name = "occurrence_id"; occurrence.value = alarm.id;
      const label = document.createElement("label"); label.textContent = "Opérateur ";
      const alias = document.createElement("input"); alias.name = "alias"; alias.maxLength = 32; alias.autocomplete = "nickname"; alias.placeholder = "facultatif";
      label.append(alias);
      const button = document.createElement("button"); button.className = "button"; button.type = "submit"; button.textContent = "Acquitter";
      const explanation = document.createElement("p"); explanation.className = "card-meta"; explanation.textContent = "Acquitter = signaler que vous avez vu l’alarme ; cela ne corrige pas la panne.";
      form.append(token, occurrence, label, button, explanation); actions.append(form);
    } else {
      const acknowledged = document.createElement("span"); acknowledged.className = "acknowledged"; acknowledged.textContent = "Acquittée";
      actions.append(acknowledged);
    }
    card.append(actions, technical);
    configureAcknowledgements(card);
    return card;
  };

  let previousStructure = null;
  const structuralSignature = (alarms, source) => JSON.stringify(alarms.map((alarm) => ({
    id: alarm.id, severity: alarm.severity, category: alarm.category, title: alarm.title,
    detail: alarm.detail, consequence: alarm.consequence, advice: alarm.advice,
    affects_control: alarm.affects_control, link: alarm.link,
    acknowledged_ts: alarm.acknowledged_ts, source,
  })));

  const updateDurations = (list, alarms) => {
    const byId = new Map(alarms.map((alarm) => [String(alarm.id), alarm]));
    list.querySelectorAll("[data-alarm-id]").forEach((card) => {
      const alarm = byId.get(card.dataset.alarmId);
      if (!alarm) return;
      const values = card.querySelectorAll(".alarm-facts dd");
      if (values[1]) values[1].textContent = duration(Number(alarm.duration_seconds || 0));
    });
  };

  // Deux compléments du résumé court appartiennent à cette page : la plus haute gravité et
  // l'horodatage de la dernière occurrence. Les trois premiers éléments de `.alarm-summary`
  // (`strong`, `span`, `small`) restent la propriété de `pwa.js`, qui les tient à jour sur
  // toutes les pages — rien n'est écrit ici deux fois.
  const severityWord = {critical: "critique", error: "erreur", warning: "avertissement"};
  const updateSummaryDetails = (alarms) => {
    const severityNode = document.querySelector(".alarm-summary-severity");
    const latestNode = document.querySelector(".alarm-summary-latest");
    if (severityNode) {
      const highest = alarms[0]?.severity;
      severityNode.textContent = highest
        ? `Plus haute gravité : ${severityWord[highest] || highest}`
        : "Aucune alarme active";
    }
    if (latestNode) {
      const latest = alarms.reduce((value, alarm) => Math.max(value, Number(alarm.started_ts) || 0), 0);
      latestNode.replaceChildren();
      if (!latest) { latestNode.textContent = "Aucune occurrence datée"; return; }
      const stamp = document.createElement("time");
      stamp.className = "num";
      stamp.dataset.timestamp = String(latest);
      stamp.textContent = new Date(latest * 1000).toLocaleString("fr-FR");
      latestNode.append("Dernière occurrence : ", stamp);
    }
  };

  const renderActiveFeed = (feed, source) => {
    const list = document.getElementById("alarm-list");
    if (!list || list.dataset.liveRefresh !== "true") return;
    const severityRank = {critical: 3, error: 2, warning: 1};
    const alarms = [...(feed.alarms || [])].sort((a, b) => (severityRank[b.severity] || 0) - (severityRank[a.severity] || 0) || b.started_ts - a.started_ts);
    const signature = structuralSignature(alarms, source);
    if (signature === previousStructure) {
      updateDurations(list, alarms);
      return;
    }
    const focusedCard = document.activeElement?.closest?.("[data-alarm-id]");
    const focusedId = focusedCard?.dataset.alarmId;
    const focusedInput = focusedId && document.activeElement?.matches?.('input[name="alias"]') ? document.activeElement : null;
    const focusState = focusedInput ? {
      value: focusedInput.value,
      start: focusedInput.selectionStart,
      end: focusedInput.selectionEnd,
    } : null;
    list.replaceChildren();
    alarms.forEach((alarm, index) => list.append(createAlarmCard(alarm, source, index === 0)));
    if (!alarms.length) {
      const empty = document.createElement("article"); empty.className = "card empty-state";
      // Même vocabulaire que les cartes : une lecture hors ligne est une « copie datée »,
      // jamais un « état non confirmé » — le doute porte sur la fraîcheur, pas sur la serre.
      const title = document.createElement("h2");
      title.textContent = source === "stored" ? "Aucune alarme dans cette copie datée" : "Aucune occurrence";
      const copy = document.createElement("p");
      copy.textContent = source === "stored"
        ? `${copieDatee()} : le contrôleur n’a pas répondu, l’état actuel de la serre peut différer.`
        : "Aucune alarme active.";
      empty.append(title, copy); list.append(empty);
    }
    previousStructure = signature;
    updateSummaryDetails(alarms);
    const resultSummary = document.getElementById("alarm-result-summary");
    // Accord français : seul un nombre strictement supérieur à 1 prend le pluriel.
    if (resultSummary) resultSummary.textContent = `${alarms.length} ${alarms.length > 1 ? "résultats" : "résultat"} · actualisation automatique`;
    if (focusState) {
      const replacement = [...list.querySelectorAll("[data-alarm-id]")]
        .find((card) => card.dataset.alarmId === focusedId)?.querySelector('input[name="alias"]');
      if (replacement) {
        replacement.value = focusState.value;
        replacement.focus({preventScroll: true});
        replacement.setSelectionRange(focusState.start, focusState.end);
      }
    }
  };

  localizeTimes();
  configureAcknowledgements();
  document.addEventListener("phyto:alarm-feed", (event) => {
    dateCopie = event.detail.receivedAt ?? null;
    renderActiveFeed(event.detail.feed, event.detail.source);
  });
})();
