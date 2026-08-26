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

  const updateClimate = (climate) => {
    if (!climate) return;
    text("#climate-state", climate.state || "—");
    text("#climate-reason", climate.reason || "En attente du premier cycle de régulation.");
    text(
      "#climate-thresholds",
      climate.vent_threshold === null || climate.vent_threshold === undefined
        ? "—"
        : `Chauffage OFF > ${climate.heater_off_threshold} °C · ventilation ≥ ${climate.vent_threshold} °C`
    );
    text(
      "#climate-budgets",
      `Renouvellement ${climate.renew_minutes_used}/${climate.renew_minutes_quota} min/h · ` +
      `déshumidification ${climate.humidity_minutes_used}/${climate.humidity_minutes_quota} min/h`
    );
  };

  const formatDuration = (seconds) => {
    if (seconds === null || seconds === undefined) return "—";
    if (seconds < 60) return `${Math.round(seconds)} s`;
    if (seconds < 3600) return `${Math.round(seconds / 60)} min`;
    return `${(seconds / 3600).toFixed(1)} h`;
  };

  const formatNext = (next) => {
    if (!next || next.type === "none") return "Aucune transition planifiée";
    if (next.type === "condition") return next.condition || "À la prochaine condition de régulation";
    if (next.type === "safety_deadline") return `Échéance de sécurité dans ${formatDuration(next.in_seconds)}`;
    if (next.in_seconds !== undefined) return `Dans ${formatDuration(next.in_seconds)}`;
    if (next.at) {
      const parsed = Date.parse(next.at);
      return Number.isNaN(parsed) ? `À ${next.at}` : new Date(parsed).toLocaleString("fr-FR");
    }
    return "—";
  };

  const updateActuators = (actuators) => {
    Object.entries(actuators || {}).forEach(([key, actuator]) => {
      const card = document.querySelector(`[data-actuator="${CSS.escape(key)}"]`);
      if (!card) return;
      card.classList.remove("tracking-ok", "tracking-mismatch", "tracking-known_hardware_fault", "tracking-unknown");
      card.classList.add(`tracking-${actuator.tracking || "unknown"}`);
      text(".actuator-name", actuator.metadata?.display_name || key, card);
      const iconUse = card.querySelector(".equipment-icon use");
      if (iconUse && actuator.metadata?.icon) {
        const iconBase = (iconUse.getAttribute("href") || "").split("#", 1)[0];
        iconUse.setAttribute("href", `${iconBase}#${actuator.metadata.icon}`);
      }
      text(".actuator-actual", String(actuator.actual ?? "unknown"), card);
      text(".actuator-requested", String(actuator.requested ?? "unknown"), card);
      text(".actuator-reason", actuator.reason || "Motif indisponible", card);
      text(".actuator-since", formatDuration(actuator.since_seconds), card);
      text(".actuator-next", formatNext(actuator.next_transition), card);
      const fault = card.querySelector(".known-fault");
      if (fault) {
        fault.hidden = actuator.tracking !== "known_hardware_fault";
        fault.textContent = `Défaut matériel connu : ${actuator.metadata?.wiring_note || "écart demandé/relu documenté."}`;
      }
      const progress = card.querySelector(".motor-progress");
      if (progress) { progress.value = Number(actuator.actual) || 0; progress.textContent = `${actuator.actual ?? 0}/4`; }
      if (key === "motor") {
        text(".actuator-details", `Vitesse voulue ${actuator.requested ?? "—"} · appliquée ${actuator.applied ?? "—"} · dwell ${actuator.dwell_remaining_seconds ?? 0} s`, card);
      } else if (key === "heater") {
        text(".actuator-details", `Seuil d’arrêt ${actuator.heater_off_threshold ?? "—"} °C · durée ON ${actuator.on_seconds ?? 0} s / ${actuator.continuous_limit_seconds ?? "—"} s`, card);
      }
    });
  };

  const updateTimers = (timers) => {
    (timers || []).forEach((timer) => {
      const card = document.querySelector(`[data-timer="${CSS.escape(timer.id)}"]`);
      if (!card) return;
      text(".card-kicker span:last-child", timer.enabled ? "Activé" : "Désactivé", card);
      let description;
      if (timer.kind === "daily") {
        description = `${timer.schedule.start} → ${timer.schedule.stop}`;
      } else if (timer.schedule.mode === "journalier") {
        description = `${timer.schedule.triggers_per_day} action(s), tous les ${timer.schedule.period_days} jour(s), dès ${timer.schedule.first_trigger_hour} h`;
      } else {
        description = `Séquentiel · jour ${timer.schedule.on_time_day} s ON / ${timer.schedule.off_time_day} s OFF · nuit ${timer.schedule.on_time_night} s ON / ${timer.schedule.off_time_night} s OFF`;
      }
      text(".timer-description", description, card);
    });
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
    text("#alarm-count", state.alarms?.active_count ?? 0);
    text("#control-alarm-count", state.alarms?.control_count ?? 0);
    text("#aux-alarm-count", state.alarms?.auxiliary_count ?? 0);
    text("#history-state", state.history?.available ? "Disponible" : "Indisponible");
    text("#network-state", state.network?.status || "unknown");
    text("#network-detail", `${state.network?.interface || "Interface inconnue"} · ${state.network?.ipv4 || "sans IPv4"}`);
    let globalAlarm = document.getElementById("global-alarm");
    if ((state.alarms?.active_count || 0) === 0) {
      globalAlarm?.remove();
    } else {
      if (!globalAlarm) {
        globalAlarm = document.createElement("aside"); globalAlarm.id = "global-alarm";
        globalAlarm.setAttribute("aria-live", "polite");
        const title = document.createElement("strong"); const detail = document.createElement("span");
        const link = document.createElement("a"); link.href = "/alarms"; link.textContent = "Examiner";
        globalAlarm.append(title, detail, link); document.querySelector(".site-header")?.after(globalAlarm);
      }
      globalAlarm.className = `global-alarm severity-${state.alarms.highest_severity || "warning"}`;
      text("strong", `${state.alarms.active_count} alarme(s) active(s)`, globalAlarm);
      text("span", `${state.alarms.control_count} contrôle · ${state.alarms.auxiliary_count} auxiliaire`, globalAlarm);
    }
    const timeAlert = state.time.alarm || state.time.daily_timers_suspended;
    const timeBanner = document.getElementById("time-banner");
    if (timeBanner) timeBanner.className = `time-banner ${timeAlert ? "is-alert" : "is-ok"}`;
    text("#time-title", `Heure : ${state.time.state}`);
    text("#time-detail", state.time.daily_timers_suspended
      ? "Minuteries journalières suspendues, reprise de sécurité au plus tard dans 15 minutes."
      : (state.time.alarm || "Horloge exploitable par les ordonnanceurs."));
    Object.entries(state.outputs).forEach(([key, value]) => {
      const badge = document.querySelector(`[data-output="${CSS.escape(key)}"]`);
      if (badge) { badge.textContent = value; badge.className = `state-badge state-${value}`; }
    });
    updateActuators(state.actuators);
    updateClimate(state.climate);
    updateTimers(state.timers);
    state.stats.forEach((stat) => {
      const card = document.querySelector(`[data-stat="${CSS.escape(stat.key)}"]`);
      if (!card) return;
      text(".stat-min", stat.min ?? "—", card); text(".stat-max", stat.max ?? "—", card);
      text(".stat-min-at", stat.min_at ? `le ${stat.min_at}` : "", card);
      text(".stat-max-at", stat.max_at ? `le ${stat.max_at}` : "", card);
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
