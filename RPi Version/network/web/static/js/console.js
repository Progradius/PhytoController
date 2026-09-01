(() => {
  "use strict";

  // Console de diagnostic. Deux règles gouvernent ce fichier :
  //
  //  1. le tampon client est **borné** — l'ancienne version faisait
  //     `output.textContent += ...` sans limite, donc un DOM qui grossissait
  //     tant que la page restait ouverte ;
  //  2. **jamais `innerHTML`**, y compris pour le surlignage de recherche : le
  //     flux contient des messages arbitraires. Tout passe par
  //     `createElement` et `textContent`.

  const MAX_RECORDS = 2000;
  const LEVELS = ["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"];

  const output = document.getElementById("console-output");
  const state = document.getElementById("connection-state");
  if (!output || !state) return;

  const levelSelect = document.getElementById("console-level");
  const componentSelect = document.getElementById("console-component");
  const searchInput = document.getElementById("console-search");
  const counters = document.getElementById("console-counters");
  const pauseButton = document.getElementById("console-pause");
  const followButton = document.getElementById("console-follow");
  const copyButton = document.getElementById("console-copy");
  const downloadButton = document.getElementById("console-download");
  const clearButton = document.getElementById("console-clear");

  const records = [];
  const components = new Set();
  let paused = false;
  let follow = true;
  let pendingWhilePaused = 0;

  // Liens d'alarme : /console?level=warning&component=phyto.influx&q=timeout
  const params = new URLSearchParams(window.location.search);
  const applyParam = (node, name, transform) => {
    const raw = params.get(name);
    if (!node || raw === null) return;
    const value = transform ? transform(raw) : raw;
    if (node.tagName === "SELECT" && !Array.from(node.options).some((o) => o.value === value)) {
      if (name !== "component") return;
      const option = document.createElement("option");
      option.value = value;
      option.textContent = value;
      node.append(option);
    }
    node.value = value;
  };
  applyParam(levelSelect, "level", (v) => v.toUpperCase());
  applyParam(componentSelect, "component");
  applyParam(searchInput, "q");

  const levelRank = (level) => {
    const index = LEVELS.indexOf(level);
    return index === -1 ? 1 : index;
  };

  const matches = (record) => {
    if (levelRank(record.level) < levelRank(levelSelect ? levelSelect.value : "INFO")) return false;
    const component = componentSelect ? componentSelect.value : "";
    if (component && record.logger !== component) return false;
    const needle = (searchInput ? searchInput.value : "").trim().toLowerCase();
    if (needle && !record.message.toLowerCase().includes(needle)) return false;
    return true;
  };

  const stamp = (ts) => {
    const date = new Date((ts || 0) * 1000);
    return Number.isNaN(date.getTime()) ? "--:--:--" : date.toLocaleTimeString("fr-FR");
  };

  const asText = (record) =>
    `${stamp(record.ts)} [${record.level}] [${record.logger}] ${record.message}`;

  const lineNode = (record) => {
    const line = document.createElement("span");
    line.className = `console-line level-${record.level.toLowerCase()}`;
    line.textContent = `${asText(record)}\n`;
    return line;
  };

  const visibleRecords = () => records.filter(matches);

  const updateCounters = (shown) => {
    if (!counters) return;
    const tally = { WARNING: 0, ERROR: 0, CRITICAL: 0 };
    records.forEach((record) => {
      if (record.level in tally) tally[record.level] += 1;
    });
    const parts = [
      `${shown} ligne(s) affichée(s) sur ${records.length}`,
      `${tally.WARNING} avertissement(s)`,
      `${tally.ERROR + tally.CRITICAL} erreur(s)`,
    ];
    if (paused && pendingWhilePaused) parts.push(`${pendingWhilePaused} en attente`);
    counters.textContent = parts.join(" · ");
  };

  const scrollIfFollowing = () => {
    if (follow) output.scrollTop = output.scrollHeight;
  };

  const render = () => {
    const shown = visibleRecords();
    const fragment = document.createDocumentFragment();
    shown.forEach((record) => fragment.append(lineNode(record)));
    output.textContent = "";
    output.append(fragment);
    updateCounters(shown.length);
    scrollIfFollowing();
  };

  const appendComponent = (logger) => {
    if (!componentSelect || components.has(logger)) return;
    components.add(logger);
    const option = document.createElement("option");
    option.value = logger;
    option.textContent = logger;
    componentSelect.append(option);
  };

  const push = (record) => {
    records.push(record);
    if (records.length > MAX_RECORDS) records.splice(0, records.length - MAX_RECORDS);
    appendComponent(record.logger);
    if (paused) {
      // Le flux continue d'alimenter le tampon : seul le rendu est gelé.
      pendingWhilePaused += 1;
      updateCounters(output.childElementCount);
      return;
    }
    if (!matches(record)) {
      updateCounters(output.childElementCount);
      return;
    }
    output.append(lineNode(record));
    while (output.childElementCount > MAX_RECORDS) output.firstElementChild.remove();
    updateCounters(output.childElementCount);
    scrollIfFollowing();
  };

  const stream = new EventSource("/console/stream");
  stream.onopen = () => {
    state.textContent = "Connectée";
    state.className = "connection-state is-online";
  };
  stream.onmessage = (event) => {
    let record;
    try {
      record = JSON.parse(event.data);
    } catch (error) {
      record = { ts: Date.now() / 1000, level: "INFO", logger: "phyto", message: String(event.data) };
    }
    if (!record || typeof record.message !== "string") return;
    record.level = String(record.level || "INFO").toUpperCase();
    record.logger = String(record.logger || "phyto");
    push(record);
  };
  stream.onerror = () => {
    state.textContent = "Reconnexion…";
    state.className = "connection-state is-offline";
  };

  [levelSelect, componentSelect].forEach((node) => node?.addEventListener("change", render));
  searchInput?.addEventListener("input", render);

  pauseButton?.addEventListener("click", () => {
    paused = !paused;
    pauseButton.textContent = paused ? "Reprendre" : "Pause";
    pauseButton.setAttribute("aria-pressed", String(paused));
    if (!paused) {
      pendingWhilePaused = 0;
      render();
    }
  });

  followButton?.addEventListener("click", () => {
    follow = !follow;
    followButton.setAttribute("aria-pressed", String(follow));
    followButton.textContent = follow ? "Suivi auto" : "Suivi figé";
    scrollIfFollowing();
  });

  output.addEventListener("scroll", () => {
    // Remonter dans l'historique suspend le suivi sans le désarmer pour de bon.
    if (!follow) return;
    const distance = output.scrollHeight - output.scrollTop - output.clientHeight;
    if (distance > 120) {
      follow = false;
      if (followButton) {
        followButton.setAttribute("aria-pressed", "false");
        followButton.textContent = "Suivi figé";
      }
    }
  });

  const filteredText = () => visibleRecords().map(asText).join("\n");

  copyButton?.addEventListener("click", async () => {
    try {
      await navigator.clipboard.writeText(filteredText());
      copyButton.textContent = "Copié";
    } catch (error) {
      copyButton.textContent = "Copie refusée";
    }
    window.setTimeout(() => { copyButton.textContent = "Copier"; }, 2000);
  });

  downloadButton?.addEventListener("click", () => {
    const blob = new Blob([`${filteredText()}\n`], { type: "text/plain;charset=utf-8" });
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    const now = new Date();
    const pad = (value) => String(value).padStart(2, "0");
    link.href = url;
    link.download = `phyto-console-${now.getFullYear()}${pad(now.getMonth() + 1)}${pad(now.getDate())}`
      + `-${pad(now.getHours())}${pad(now.getMinutes())}${pad(now.getSeconds())}.log`;
    link.click();
    URL.revokeObjectURL(url);
  });

  clearButton?.addEventListener("click", () => {
    // La vue seulement : le tampon serveur n'est jamais touché depuis ici.
    records.length = 0;
    pendingWhilePaused = 0;
    render();
  });

  render();
})();
