(() => {
  "use strict";

  let lastGeneratedAt = null;
  let fetchFailed = false;

  const text = (selector, value, root = document) => {
    const node = root.querySelector(selector);
    if (node) node.textContent = value;
  };

  const formatAge = (seconds) => {
    if (seconds === null || seconds === undefined) return "Aucune mesure";
    if (seconds < 60) return `Mesurée il y a ${Math.round(seconds)} s`;
    return `Mesurée il y a ${Math.round(seconds / 60)} min`;
  };

  const updateFreshness = () => {
    const node = document.getElementById("freshness");
    if (!node) return;
    if (fetchFailed) {
      node.textContent = "Actualisation interrompue · nouvelle tentative automatique";
      node.className = "freshness is-error";
      return;
    }
    const timestamp = Date.parse(lastGeneratedAt || node.dataset.generatedAt);
    if (Number.isNaN(timestamp)) return;
    const age = Math.max(0, Math.round((Date.now() - timestamp) / 1000));
    node.textContent = age < 2 ? "Données à jour" : `Données reçues il y a ${age} s`;
    node.className = age > 15 ? "freshness is-stale" : "freshness";
  };

  const createSensorCard = (sensor) => {
    const card = document.createElement("article");
    card.className = `card sensor-card status-${sensor.status}`;
    card.dataset.sensor = sensor.key;

    const kicker = document.createElement("div");
    kicker.className = "card-kicker";
    const key = document.createElement("span");
    key.textContent = sensor.key;
    const status = document.createElement("span");
    status.className = "sensor-status";
    status.textContent = sensor.status;
    kicker.append(key, status);

    const title = document.createElement("h3");
    title.textContent = sensor.label;
    const metric = document.createElement("p");
    metric.className = "metric";
    const value = document.createElement("span");
    value.className = "sensor-value";
    const unit = document.createElement("span");
    unit.className = "metric-unit";
    metric.append(value, " ", unit);
    const age = document.createElement("p");
    age.className = "card-meta sensor-age";
    card.append(kicker, title, metric, age);
    return card;
  };

  const updateSensors = (sensors) => {
    const grid = document.getElementById("sensor-grid");
    if (!grid) return;
    const activeKeys = new Set(sensors.map((sensor) => sensor.key));
    grid.querySelectorAll("[data-sensor]").forEach((card) => {
      if (!activeKeys.has(card.dataset.sensor)) card.remove();
    });
    grid.querySelector(".empty-state")?.remove();
    sensors.forEach((sensor) => {
      let card = grid.querySelector(`[data-sensor="${CSS.escape(sensor.key)}"]`);
      if (!card) { card = createSensorCard(sensor); grid.append(card); }
      card.className = `card sensor-card status-${sensor.status}`;
      text(".sensor-status", sensor.status, card);
      const value = sensor.value === null ? "—" : Number(sensor.value).toFixed(sensor.decimals);
      text(".sensor-value", value, card);
      text(".metric-unit", sensor.unit, card);
      text(".sensor-age", formatAge(sensor.age_s), card);
    });
    if (!sensors.length) {
      const empty = document.createElement("article");
      empty.className = "card empty-state";
      const title = document.createElement("h3"); title.textContent = "Aucun capteur actif";
      const copy = document.createElement("p"); copy.textContent = "Activez les capteurs depuis la configuration.";
      empty.append(title, copy); grid.append(empty);
    }
    text(".section-count", `${sensors.length} mesure(s)`);
  };

  const updateState = (state) => {
    lastGeneratedAt = state.generated_at;
    fetchFailed = false;
    const alarm = state.health.heater_alarm;
    const healthy = state.health.healthy && !alarm;
    const banner = document.getElementById("health-banner");
    if (banner) banner.className = `health-banner ${healthy ? "is-ok" : "is-alert"}`;
    text("#health-title", healthy ? "Système opérationnel" : "Attention requise");
    text("#health-detail", alarm || (state.health.healthy ? "Toutes les tâches supervisées répondent." : "Une tâche supervisée est en défaut."));
    Object.entries(state.outputs).forEach(([key, value]) => {
      const badge = document.querySelector(`[data-output="${CSS.escape(key)}"]`);
      if (badge) { badge.textContent = value; badge.className = `state-badge state-${value}`; }
    });
    const progress = document.getElementById("motor-progress");
    if (progress) { progress.value = state.motor.speed; progress.textContent = `${state.motor.percent} %`; }
    text("#motor-level", `Niveau ${state.motor.speed}/4`);
    state.stats.forEach((stat) => {
      const card = document.querySelector(`[data-stat="${CSS.escape(stat.key)}"]`);
      if (!card) return;
      text(".stat-min", stat.min ?? "—", card); text(".stat-max", stat.max ?? "—", card);
    });
    updateSensors(state.sensors);
    updateFreshness();
  };

  const refresh = async () => {
    try {
      const response = await fetch("/api/v1/state", { headers: { Accept: "application/json" }, cache: "no-store" });
      if (!response.ok) throw new Error(`HTTP ${response.status}`);
      updateState(await response.json());
    } catch (_error) {
      fetchFailed = true;
      updateFreshness();
    }
  };

  document.querySelectorAll("[data-open-dialog]").forEach((button) => {
    button.addEventListener("click", () => document.getElementById(button.dataset.openDialog)?.showModal());
  });
  document.querySelectorAll(".confirm-dialog").forEach((dialog) => {
    dialog.addEventListener("click", (event) => { if (event.target === dialog) dialog.close(); });
  });

  updateFreshness();
  window.setInterval(updateFreshness, 1000);
  window.setInterval(refresh, 5000);
  refresh();
})();
