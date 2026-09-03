(() => {
  "use strict";

  const sensorStatusLabels = {normal: "normal", degraded: "dégradé", absent: "absent", inconsistent: "incohérent", disabled: "désactivé"};
  const timeLabels = {unknown: "inconnue", reliable: "fiable", unreliable: "non fiable"};
  const networkLabels = {unknown: "inconnu", online: "en ligne", offline: "hors ligne", degraded: "dégradé"};
  let lastGeneratedAt = null;
  let lastReceivedAt = null;
  let fetchFailed = false;
  let storedStateLoaded = false;
  let activeDialogOpener = null;

  const text = (selector, value, root = document) => {
    const node = root.querySelector(selector);
    if (node) node.textContent = value;
  };
  const number = (value, decimals = 1) => value === null || value === undefined || !Number.isFinite(Number(value)) ? "—" : Number(value).toFixed(decimals);
  const formatDuration = (seconds) => {
    if (seconds === null || seconds === undefined) return "—";
    if (seconds < 60) return `${Math.round(seconds)} s`;
    if (seconds < 3600) return `${Math.round(seconds / 60)} min`;
    return `${(seconds / 3600).toFixed(1)} h`;
  };
  const formatAge = (seconds) => {
    if (seconds === null || seconds === undefined) return "Aucune mesure";
    return seconds < 60 ? `Mesurée il y a ${Math.round(seconds)} s` : `Mesurée il y a ${Math.round(seconds / 60)} min`;
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
  const stateLabel = (key, actual) => {
    if (key === "motor" && Number.isFinite(Number(actual))) return `V${Number(actual)}`;
    if (actual === "on" || actual === 1) return "EN MARCHE";
    if (actual === "off" || actual === 0) return "ARRÊTÉ";
    return "INCONNU";
  };
  const requestedLabel = (value) => value === "on" ? "EN MARCHE" : value === "off" ? "ARRÊTÉ" : value === "unknown" || value === undefined || value === null ? "INCONNU" : String(value);
  const countLabel = (count, singular, plural) => `${count} ${count === 1 ? singular : plural}`;

  const updateFreshness = () => {
    const node = document.getElementById("freshness");
    if (!node) return;
    if (fetchFailed) {
      const age = Number.isFinite(lastReceivedAt) ? Math.max(0, Math.round((Date.now() - lastReceivedAt) / 1000)) : null;
      node.textContent = age === null ? "Actualisation interrompue · aucune réception enregistrée" : `Données non actualisées · dernière réception il y a ${age} s`;
      node.className = "freshness is-error";
      return;
    }
    const timestamp = Date.parse(lastGeneratedAt || node.dataset.generatedAt);
    if (Number.isNaN(timestamp)) return;
    const age = Math.max(0, Math.round((Date.now() - timestamp) / 1000));
    node.textContent = age < 2 ? "Données à jour" : `Données reçues il y a ${age} s`;
    node.className = age > 15 ? "freshness is-stale" : "freshness";
  };

  const updateOverview = (state) => {
    const overview = document.getElementById("control-overview");
    if (overview && state.overview) {
      overview.className = `control-overview overview-${state.overview.status || "degraded"}`;
      text("#overview-title", state.overview.title || "État du contrôle");
      text("#overview-detail", state.overview.detail || "État indisponible.");
    }
    const alarmCount = state.alarms?.active_count ?? 0;
    text("#alarm-count", alarmCount);
    text("#alarm-count-label", alarmCount === 1 ? "alarme" : "alarmes");
    text("#time-state", `Heure ${timeLabels[state.time?.state] || state.time?.state || "inconnue"}`);
    text("#network-state", `Réseau ${networkLabels[state.network?.status] || state.network?.status || "inconnu"}`);
    text("#history-state", `Historique ${state.history?.available ? "disponible" : "indisponible"}`);
  };

  const updateGlobalAlarm = (alarms) => {
    let banner = document.getElementById("global-alarm");
    if (!(alarms?.active_count || 0)) { banner?.remove(); return; }
    if (!banner) {
      banner = document.createElement("aside"); banner.id = "global-alarm";
      const title = document.createElement("strong"); const detail = document.createElement("span"); const link = document.createElement("a");
      link.href = "/alarms"; link.textContent = "Examiner"; banner.append(title, detail, link); document.querySelector(".site-header")?.after(banner);
    }
    banner.className = `global-alarm severity-${alarms.highest_severity || "warning"}`;
    text("strong", `${countLabel(alarms.active_count, "alarme active", "alarmes actives")}`, banner);
    text("span", `${alarms.control_count} contrôle · ${alarms.auxiliary_count} auxiliaire`, banner);
  };

  const updateOverrides = (overrides) => {
    const items = new Map((overrides?.items || []).map((item) => [item.target, item]));
    const count = overrides?.active_count || 0;
    let banner = document.getElementById("override-banner");
    if (!count) banner?.remove();
    else {
      if (!banner) {
        banner = document.createElement("aside"); banner.id = "override-banner"; banner.className = "global-alarm severity-override";
        const title = document.createElement("strong"); const detail = document.createElement("span"); const link = document.createElement("a");
        link.href = "/#actionneurs"; link.textContent = "Examiner"; banner.append(title, detail, link); document.querySelector(".site-header")?.after(banner);
      }
      text("strong", `${countLabel(count, "forçage « arrêt » actif", "forçages « arrêt » actifs")}`, banner);
      text("span", "Équipements concernés coupés volontairement — la conduite normale est suspendue", banner);
    }
    document.querySelectorAll("[data-actuator]").forEach((card) => {
      const item = items.get(card.dataset.actuator);
      const forced = Boolean(item);
      const normallyVisible = card.dataset.dashboardVisible === "true";
      card.hidden = !normallyVisible && !forced;
      card.classList.toggle("is-forced", forced);
      card.querySelector(".override-normal")?.toggleAttribute("hidden", forced);
      card.querySelector(".override-active")?.toggleAttribute("hidden", !forced);
      card.querySelector(".override-cut")?.toggleAttribute("hidden", forced);
      card.querySelector(".override-resume")?.toggleAttribute("hidden", !forced);
      card.querySelector(".normally-hidden")?.toggleAttribute("hidden", normallyVisible);
      if (item) {
        text(".override-remaining", `reste ${Math.max(0, Math.floor((item.remaining_seconds || 0) / 60))} min`, card);
        text(".override-reason", item.reason || "Aucune raison renseignée", card);
        card.querySelector(".override-unconfirmed")?.toggleAttribute("hidden", item.confirmed !== false);
      }
    });
    document.getElementById("resume-all-form")?.toggleAttribute("hidden", count === 0);
  };

  const scheduleText = (timer, detailed = false) => {
    if (!timer) return "";
    const prefix = timer.enabled ? "Actif" : "Désactivé";
    if (timer.kind === "daily") return detailed ? `Planning quotidien : ${timer.schedule.start} → ${timer.schedule.stop}.` : `${prefix} · ${timer.schedule.start} → ${timer.schedule.stop}`;
    if (timer.schedule.mode === "journalier") {
      const activations = countLabel(timer.schedule.triggers_per_day, "activation", "activations");
      const period = countLabel(timer.schedule.period_days, "jour", "jours");
      return detailed
        ? `Mode journalier : ${activations}, tous les ${period}, première à ${timer.schedule.first_trigger_hour} h, pendant ${timer.schedule.action_duration_seconds} s.`
        : `${prefix} · ${activations}, tous les ${period}`;
    }
    return detailed
      ? `Mode séquentiel : jour ${timer.schedule.on_time_day} s ON / ${timer.schedule.off_time_day} s OFF · nuit ${timer.schedule.on_time_night} s ON / ${timer.schedule.off_time_night} s OFF.`
      : `${prefix} · cycle séquentiel jour/nuit`;
  };

  const updateActuators = (state) => {
    const timers = new Map((state.timers || []).map((timer) => [timer.equipment_id, timer]));
    Object.entries(state.actuators || {}).forEach(([key, actuator]) => {
      const card = document.querySelector(`[data-actuator="${CSS.escape(key)}"]`); if (!card) return;
      const metadata = actuator.metadata || state.equipment?.[key] || {};
      card.dataset.dashboardVisible = String(metadata.dashboard_visible !== false);
      card.classList.remove("tracking-ok", "tracking-mismatch", "tracking-known_hardware_fault", "tracking-unknown");
      card.classList.add(`tracking-${actuator.tracking || "unknown"}`);
      text(".actuator-name", metadata.display_name || key, card);
      text(".actuator-usage", `${metadata.usage_type || "équipement"}${metadata.zone ? ` · ${metadata.zone}` : ""}`, card);
      text(".actuator-actual", stateLabel(key, actuator.actual), card);
      text(".actuator-requested", requestedLabel(actuator.requested), card);
      text(".actuator-applied", actuator.applied === undefined || actuator.applied === null ? "—" : requestedLabel(actuator.applied), card);
      text(".actuator-reason", actuator.reason || "Motif indisponible", card);
      text(".actuator-since", formatDuration(actuator.since_seconds), card);
      const next = formatNext(actuator.next_transition);
      text(".actuator-next", next, card); text(".actuator-next-detail", next, card);
      const icon = card.querySelector(".equipment-icon use");
      if (icon && metadata.icon) icon.setAttribute("href", `${(icon.getAttribute("href") || "").split("#", 1)[0]}#${metadata.icon}`);
      const timer = timers.get(key); const summary = card.querySelector(".automation-summary"); const detail = card.querySelector(".schedule-detail");
      if (summary) { summary.hidden = !timer; summary.textContent = scheduleText(timer); }
      if (detail) { detail.hidden = !timer; const paragraph = detail.querySelector("p"); if (paragraph) paragraph.textContent = scheduleText(timer, true); }
      const fault = card.querySelector(".known-fault");
      if (fault) { fault.hidden = actuator.tracking !== "known_hardware_fault"; fault.textContent = `Défaut matériel connu : ${metadata.wiring_note || "écart demandé/relu documenté."}`; }
      if (key === "motor") text(".climate-detail", `Seuil de ventilation ${state.climate?.vent_threshold ?? "—"} °C · renouvellement ${state.climate?.renew_minutes_used ?? "—"}/${state.climate?.renew_minutes_quota ?? "—"} min/h · déshumidification ${state.climate?.humidity_minutes_used ?? "—"}/${state.climate?.humidity_minutes_quota ?? "—"} min/h.`, card);
      if (key === "heater") text(".climate-detail", `Arrêt au-dessus de ${actuator.heater_off_threshold ?? state.climate?.heater_off_threshold ?? "—"} °C · durée ON ${actuator.on_seconds ?? 0} s / ${actuator.continuous_limit_seconds ?? "—"} s.`, card);
    });
  };

  const updateStat = (stat) => {
    const card = document.querySelector(`[data-sensor="${CSS.escape(stat.key)}"]`); if (!card) return;
    card.querySelectorAll(".stat-min").forEach((node) => { node.textContent = number(stat.min, stat.decimals ?? 1); });
    card.querySelectorAll(".stat-max").forEach((node) => { node.textContent = number(stat.max, stat.decimals ?? 1); });
    card.querySelectorAll(".stat-min-at").forEach((node) => { node.textContent = stat.min_at ? `le ${stat.min_at}` : ""; });
    card.querySelectorAll(".stat-max-at").forEach((node) => { node.textContent = stat.max_at ? `le ${stat.max_at}` : ""; });
  };

  const updateSensors = (sensors, stats) => {
    (sensors || []).forEach((sensor) => {
      const card = document.querySelector(`[data-sensor="${CSS.escape(sensor.key)}"]`); if (!card) return;
      card.classList.remove("status-normal", "status-degraded", "status-absent", "status-inconsistent", "status-disabled"); card.classList.add(`status-${sensor.status}`);
      text(".sensor-status", sensorStatusLabels[sensor.status] || sensor.status, card);
      text(".sensor-value", number(sensor.value, sensor.decimals), card); text(".metric-unit", sensor.unit, card); text(".sensor-age", formatAge(sensor.age_s), card);
      text(".sensor-raw", `${number(sensor.raw_value, sensor.decimals)} ${sensor.unit}`, card); text(".sensor-observed", `${number(sensor.observed_value, sensor.decimals)} ${sensor.unit}`, card); text(".sensor-trusted", `${number(sensor.value, sensor.decimals)} ${sensor.unit}`, card); text(".sensor-unchanged", `${Math.round(sensor.unchanged_for_s || 0)} s`, card);
      text(".sensor-quality", (sensor.reason_codes || []).join(", ") || "Mesure qualifiée", card);
    });
    (stats || []).forEach(updateStat); text(".section-count", countLabel((sensors || []).length, "mesure", "mesures"));
  };

  const updateClimateSummary = (state) => {
    const sensors = new Map((state.sensors || []).map((sensor) => [sensor.key, sensor]));
    const updateSensor = (name, key) => {
      const item = sensors.get(key); const root = document.querySelector(`[data-climate-summary="${name}"]`);
      if (!root) return;
      text(".climate-summary-value", item ? number(item.value, item.decimals) : "—", root);
      text(".climate-summary-detail", item ? `${sensorStatusLabels[item.status] || item.status} · ${formatAge(item.age_s)}` : "Indisponible", root);
    };
    updateSensor("temperature", "BME280T"); updateSensor("humidity", "BME280H");
    const heater = state.actuators?.heater; const heaterRoot = document.querySelector('[data-climate-summary="heater"]');
    if (heaterRoot) { text(".climate-summary-value", stateLabel("heater", heater?.actual), heaterRoot); text(".climate-summary-detail", heater?.reason || "Motif indisponible", heaterRoot); }
    const motor = state.actuators?.motor; const motorRoot = document.querySelector('[data-climate-summary="motor"]');
    if (motorRoot) { text(".climate-summary-value", stateLabel("motor", motor?.actual), motorRoot); text(".climate-summary-detail", motor?.reason || "Motif indisponible", motorRoot); }
  };

  const updateState = (state, {fresh = true, receivedAt = Date.now()} = {}) => {
    lastGeneratedAt = state.generated_at;
    if (fresh) { lastReceivedAt = receivedAt; fetchFailed = false; }
    updateOverview(state); updateGlobalAlarm(state.alarms); updateActuators(state); updateOverrides(state.overrides); updateSensors(state.sensors, state.stats); updateClimateSummary(state); updateFreshness();
    document.dispatchEvent(new CustomEvent("phyto:history-availability", {detail: {available: Boolean(state.history?.available)}}));
  };

  const refresh = async () => {
    try {
      const response = await fetch("/api/v1/state", {headers: {Accept: "application/json"}, cache: "no-store"});
      await window.PhytoPwa?.markServerContact(); if (!response.ok) throw new Error(`HTTP ${response.status}`);
      const state = await response.json(); const receivedAt = Date.now(); await window.PhytoPwa?.recordNetworkSuccess("state", state, receivedAt); updateState(state, {fresh: true, receivedAt}); return true;
    } catch (error) {
      if (error instanceof TypeError) window.PhytoPwa?.markServerFailure(); fetchFailed = true;
      if (!storedStateLoaded) { storedStateLoaded = true; const stored = await window.PhytoPwa?.loadSnapshot("state"); if (stored?.data) { lastReceivedAt = stored.receivedAt; updateState(stored.data, {fresh: false, receivedAt: stored.receivedAt}); } }
      updateFreshness();
      return false;
    }
  };

  const submitEnhanced = async (form, onSuccess) => {
    const button = form.querySelector('button[type="submit"]'); const errorNode = form.querySelector(".form-error"); const original = button?.textContent;
    if (errorNode) errorNode.hidden = true;
    if (button) { button.disabled = true; button.textContent = "Traitement…"; }
    try {
      const response = await fetch(form.action, {method: "POST", headers: {Accept: "application/json"}, body: new FormData(form)});
      if (!response.ok) throw new Error((await response.text()) || `HTTP ${response.status}`);
      await window.PhytoPwa?.markServerContact(); await onSuccess(await response.json()); return true;
    } catch (error) {
      if (error instanceof TypeError) window.PhytoPwa?.markServerFailure();
      if (errorNode) { errorNode.textContent = error.message || "Action impossible."; errorNode.hidden = false; errorNode.focus?.(); }
      return false;
    } finally { if (button) { button.disabled = false; button.textContent = original; } }
  };

  document.querySelectorAll("[data-override-form]").forEach((form) => form.addEventListener("submit", async (event) => {
    event.preventDefault(); const target = String(new FormData(form).get("target") || "");
    const ok = await submitEnhanced(form, async (payload) => { updateOverrides(payload); document.getElementById("dashboard-action-status").textContent = target === "all" ? "Intervention groupée appliquée." : `Intervention appliquée sur ${target}.`; await refresh(); });
    if (ok) form.closest("dialog")?.close();
  }));
  document.querySelectorAll("[data-stat-form]").forEach((form) => form.addEventListener("submit", async (event) => {
    event.preventDefault(); await submitEnhanced(form, async (payload) => { updateStat(payload); document.getElementById("dashboard-action-status").textContent = `Extrêmes de ${payload.key} réinitialisés.`; });
  }));
  document.querySelectorAll("[data-open-dialog]").forEach((button) => button.addEventListener("click", () => { activeDialogOpener = button; document.getElementById(button.dataset.openDialog)?.showModal(); }));
  document.querySelectorAll(".confirm-dialog").forEach((dialog) => { dialog.addEventListener("click", (event) => { if (event.target === dialog) dialog.close(); }); dialog.addEventListener("close", () => activeDialogOpener?.focus()); });

  updateFreshness();
  window.setInterval(() => { if (document.visibilityState === "visible") updateFreshness(); }, 5000);
  if (window.PhytoPwa?.createAdaptivePoller) window.PhytoPwa.createAdaptivePoller(refresh).start();
  else refresh();
})();
