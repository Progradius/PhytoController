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

  const fact = (label, value) => {
    const wrapper = document.createElement("div");
    const term = document.createElement("dt"); term.textContent = label;
    const detail = document.createElement("dd"); detail.textContent = value;
    wrapper.append(term, detail);
    return wrapper;
  };

  const createAlarmCard = (alarm, source) => {
    const card = document.createElement("article");
    card.className = `alarm-card severity-${alarm.severity}`;
    card.dataset.alarmId = alarm.id;

    const heading = document.createElement("div"); heading.className = "alarm-card-heading";
    const labels = document.createElement("div");
    const severity = document.createElement("span"); severity.className = "alarm-severity"; severity.textContent = severityLabels[alarm.severity] || alarm.severity;
    const category = document.createElement("span"); category.className = "alarm-category"; category.textContent = categoryLabels[alarm.category] || alarm.category;
    const state = document.createElement("span"); state.textContent = source === "stored" ? "État non confirmé" : "Active";
    labels.append(severity, category); heading.append(labels, state);

    const title = document.createElement("h2"); title.textContent = alarm.title;
    card.append(heading, title);
    if (alarm.detail) {
      const detail = document.createElement("p"); detail.className = "alarm-detail"; detail.textContent = alarm.detail;
      card.append(detail);
    }

    const facts = document.createElement("dl"); facts.className = "alarm-facts";
    facts.append(
      fact("Depuis", new Date(Number(alarm.started_ts) * 1000).toLocaleString("fr-FR")),
      fact("Durée", duration(Number(alarm.duration_seconds || 0))),
      fact("Impact", alarm.affects_control ? "Contrôle" : "Auxiliaire")
    );
    card.append(facts);

    const consequence = document.createElement("p");
    const consequenceLabel = document.createElement("strong"); consequenceLabel.textContent = "Conséquence : ";
    consequence.append(consequenceLabel, alarm.consequence || "—");
    const advice = document.createElement("p");
    const adviceLabel = document.createElement("strong"); adviceLabel.textContent = "Action conseillée : ";
    advice.append(adviceLabel, alarm.advice || "—");
    card.append(consequence, advice);

    const actions = document.createElement("div"); actions.className = "alarm-actions";
    const link = document.createElement("a"); link.className = "button button-secondary"; link.href = alarm.link || "/alarms"; link.textContent = "Diagnostiquer";
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
      form.append(token, occurrence, label, button); actions.append(form);
    } else {
      const acknowledged = document.createElement("span"); acknowledged.className = "acknowledged"; acknowledged.textContent = "Acquittée";
      actions.append(acknowledged);
    }
    card.append(actions);
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

  const renderActiveFeed = (feed, source) => {
    const list = document.getElementById("alarm-list");
    if (!list || list.dataset.liveRefresh !== "true") return;
    const alarms = feed.alarms || [];
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
    for (const alarm of alarms) list.append(createAlarmCard(alarm, source));
    if (!alarms.length) {
      const empty = document.createElement("article"); empty.className = "card empty-state";
      const title = document.createElement("h2"); title.textContent = source === "stored" ? "Aucune alarme dans le dernier état connu" : "Aucune occurrence";
      const copy = document.createElement("p"); copy.textContent = source === "stored" ? "Cet état reste non confirmé tant que le contrôleur ne répond pas." : "Aucune alarme active.";
      empty.append(title, copy); list.append(empty);
    }
    previousStructure = signature;
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
    renderActiveFeed(event.detail.feed, event.detail.source);
  });
})();
