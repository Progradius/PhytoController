(() => {
  "use strict";
  const section = document.getElementById("tendances");
  if (!section) return;
  const message = document.getElementById("history-message");
  const tooltip = document.getElementById("history-tooltip");
  const selectionOutput = document.getElementById("history-selection-output");
  const colors = ["#50e38a", "#65b9ff", "#ffc857", "#d88cff", "#ff7b7b", "#8ee3ef"];
  const seriesDashes = [[], [8, 3], [2, 3], [10, 3, 2, 3], [5, 3], [12, 4]];
  const groups = {automation: ["daily_1", "daily_2", "cyclic_1", "cyclic_2"], "climate-actuator": ["heater", "motor"]};
  const fallbackNames = {daily_1: "Éclairage 1", daily_2: "Éclairage 2", cyclic_1: "Sortie cyclique 1", cyclic_2: "Sortie cyclique 2", heater: "Chauffage", motor: "Ventilation"};
  const plots = new Map();
  const hiddenSeries = new Set();
  const hiddenActuators = new Set();
  let current = null;
  let selectedTimestamp = null;
  let pointerPosition = null;
  let redrawFrame = null;

  const equipmentName = (id) => current?.equipment?.[id]?.display_name || fallbackNames[id] || id;
  const formatNumber = (value, decimals = 1) => Number.isFinite(value) ? Number(value).toLocaleString("fr-FR", {minimumFractionDigits: decimals, maximumFractionDigits: decimals}) : "—";
  const formatDate = (timestamp, detailed = false) => new Date(timestamp * 1000).toLocaleString("fr-FR", {timeZone: "Europe/Paris", day: "2-digit", month: detailed ? "2-digit" : undefined, hour: "2-digit", minute: "2-digit"});
  const formatDuration = (seconds) => {
    if (!Number.isFinite(seconds)) return "—";
    const minutes = Math.max(0, Math.round(seconds / 60));
    const hours = Math.floor(minutes / 60); const remainder = minutes % 60;
    return hours ? `${hours} h ${String(remainder).padStart(2, "0")} min` : `${remainder} min`;
  };
  const element = (tag, className, text) => {
    const node = document.createElement(tag);
    if (className) node.className = className;
    if (text !== undefined) node.textContent = text;
    return node;
  };

  const setup = (canvas) => {
    const ratio = window.devicePixelRatio || 1;
    const width = Math.max(1, Math.floor(canvas.clientWidth || canvas.parentElement?.clientWidth || 280));
    const height = Number(canvas.dataset.chartHeight) || 220;
    canvas.width = Math.round(width * ratio);
    canvas.height = Math.round(height * ratio);
    const context = canvas.getContext("2d");
    context.setTransform(ratio, 0, 0, ratio, 0, 0);
    return {context, width, height};
  };

  const timeAxis = (ctx, box, height, start, end, x) => {
    const count = box.right - box.left < 460 ? 3 : 5;
    ctx.fillStyle = "#a0b9aa"; ctx.font = "11px system-ui";
    for (let index = 0; index < count; index += 1) {
      const timestamp = start + index / (count - 1) * (end - start);
      const label = formatDate(timestamp);
      const xx = x(timestamp); const measured = ctx.measureText(label).width;
      ctx.fillText(label, Math.max(box.left, Math.min(xx - measured / 2, box.right - measured)), height - 7);
    }
  };

  const sensorFrame = (canvas, minimum, maximum, unit) => {
    const {context: ctx, width, height} = setup(canvas);
    const box = {left: width < 390 ? 43 : 49, right: width - 8, top: 10, bottom: height - 29};
    const range = Math.max(1e-6, maximum - minimum);
    const start = current.range_start_ts; const end = current.range_end_ts;
    const x = (timestamp) => box.left + (timestamp - start) / Math.max(1, end - start) * (box.right - box.left);
    const y = (value) => box.bottom - (value - minimum) / range * (box.bottom - box.top);
    ctx.clearRect(0, 0, width, height); ctx.font = "11px system-ui"; ctx.lineWidth = 1;
    for (let index = 0; index <= 4; index += 1) {
      const yy = box.top + index / 4 * (box.bottom - box.top);
      ctx.strokeStyle = "rgba(176,205,186,.16)"; ctx.beginPath(); ctx.moveTo(box.left, yy); ctx.lineTo(box.right, yy); ctx.stroke();
      const value = maximum - index / 4 * range;
      ctx.fillStyle = "#a0b9aa"; ctx.fillText(`${value.toFixed(range < 10 ? 1 : 0)}${unit}`, 2, yy + 4);
    }
    timeAxis(ctx, box, height, start, end, x);
    const graph = {ctx, x, y, box, width, height, start, end}; plots.set(canvas, graph); return graph;
  };

  const valuesFor = (key) => current.buckets.flatMap((bucket) => {
    const item = bucket.sensors[key];
    return item?.valid_count ? [item.min, item.avg, item.max].filter(Number.isFinite) : [];
  });
  const sensorSegments = (key) => {
    const result = []; let segment = [];
    current.buckets.forEach((bucket) => {
      const item = bucket.sensors[key];
      const point = item?.valid_count ? {ts: bucket.bucket_start_ts, ...item} : null;
      if (!point || (segment.length && point.ts - segment.at(-1).ts > current.bucket_seconds * 2.5)) {
        if (segment.length) result.push(segment); segment = [];
      }
      if (point) segment.push(point);
    });
    if (segment.length) result.push(segment); return result;
  };
  const setpointSegments = (keys) => {
    const result = []; let segment = [];
    current.buckets.forEach((bucket) => {
      const valid = keys.every((key) => Number.isFinite(bucket.setpoints[key]));
      if (!valid || (segment.length && bucket.bucket_start_ts - segment.at(-1).bucket_start_ts > current.bucket_seconds * 2.5)) {
        if (segment.length) result.push(segment); segment = [];
      }
      if (valid) segment.push(bucket);
    });
    if (segment.length) result.push(segment); return result;
  };
  const drawSetpointLine = (graph, key, color, dash) => {
    graph.ctx.strokeStyle = color; graph.ctx.lineWidth = 1.4; graph.ctx.setLineDash(dash);
    setpointSegments([key]).forEach((points) => {
      graph.ctx.beginPath();
      points.forEach((bucket, index) => graph.ctx[index ? "lineTo" : "moveTo"](graph.x(bucket.bucket_start_ts), graph.y(bucket.setpoints[key])));
      graph.ctx.stroke();
    });
    graph.ctx.setLineDash([]);
  };
  const drawEvents = (graph) => (current.events || []).forEach((event) => {
    const xx = graph.x(event.ts); if (xx < graph.box.left || xx > graph.box.right) return;
    const alarm = event.kind === "alarm";
    graph.ctx.strokeStyle = alarm ? "rgba(255,107,107,.82)" : "rgba(255,200,87,.78)";
    graph.ctx.fillStyle = alarm ? "#ff6b6b" : "#ffc857"; graph.ctx.lineWidth = 1;
    graph.ctx.beginPath(); graph.ctx.moveTo(xx, graph.box.top); graph.ctx.lineTo(xx, graph.box.bottom); graph.ctx.stroke();
    graph.ctx.beginPath();
    if (alarm) { graph.ctx.moveTo(xx, graph.box.top); graph.ctx.lineTo(xx - 4, graph.box.top + 7); graph.ctx.lineTo(xx + 4, graph.box.top + 7); }
    else { graph.ctx.moveTo(xx, graph.box.top); graph.ctx.lineTo(xx - 4, graph.box.top + 4); graph.ctx.lineTo(xx, graph.box.top + 8); graph.ctx.lineTo(xx + 4, graph.box.top + 4); }
    graph.ctx.closePath(); graph.ctx.fill();
  });
  const drawCrosshair = (graph) => {
    if (!Number.isFinite(selectedTimestamp)) return;
    const xx = graph.x(selectedTimestamp); if (xx < graph.box.left || xx > graph.box.right) return;
    graph.ctx.strokeStyle = "rgba(237,247,240,.72)"; graph.ctx.lineWidth = 1; graph.ctx.setLineDash([2, 3]);
    graph.ctx.beginPath(); graph.ctx.moveTo(xx, graph.box.top); graph.ctx.lineTo(xx, graph.box.bottom); graph.ctx.stroke(); graph.ctx.setLineDash([]);
  };
  const sensorSummary = (series, unit) => {
    const values = series.flatMap((meta) => valuesFor(meta.key));
    if (!values.length) return "Aucune mesure valide sur cette période.";
    const averages = current.buckets.flatMap((bucket) => series.map((meta) => bucket.sensors[meta.key]?.avg).filter(Number.isFinite));
    return `Min ${formatNumber(Math.min(...values))} ${unit} · moyenne ${formatNumber(averages.reduce((sum, value) => sum + value, 0) / averages.length)} ${unit} · max ${formatNumber(Math.max(...values))} ${unit}.`;
  };

  const drawSensorChart = (canvas, series, unit, options = {}) => {
    if (!canvas) return;
    const visible = series.filter((meta) => !hiddenSeries.has(meta.key));
    let values = visible.flatMap((meta) => valuesFor(meta.key));
    if (options.temperature) current.buckets.forEach((bucket) => values.push(bucket.setpoints.temp_min, bucket.setpoints.temp_max, bucket.setpoints.heater_off_threshold, bucket.setpoints.vent_threshold));
    if (options.humidity) current.buckets.forEach((bucket) => values.push(bucket.setpoints.humidity_threshold));
    values = values.filter(Number.isFinite);
    if (!values.length) {
      const empty = setup(canvas); empty.context.clearRect(0, 0, empty.width, empty.height);
      empty.context.fillStyle = "#a0b9aa"; empty.context.font = "13px system-ui";
      empty.context.fillText(visible.length ? "Aucune mesure valide sur cette période" : "Toutes les séries sont masquées", 16, 35);
      plots.delete(canvas); return;
    }
    const padding = Math.max(unit === "°C" ? 1 : .5, (Math.max(...values) - Math.min(...values)) * .1);
    const graph = sensorFrame(canvas, Math.min(...values) - padding, Math.max(...values) + padding, unit);
    if (options.temperature) {
      setpointSegments(["temp_min", "temp_max"]).forEach((points) => {
        graph.ctx.fillStyle = "rgba(101,185,255,.10)"; graph.ctx.beginPath();
        points.forEach((bucket, index) => graph.ctx[index ? "lineTo" : "moveTo"](graph.x(bucket.bucket_start_ts), graph.y(bucket.setpoints.temp_max)));
        [...points].reverse().forEach((bucket) => graph.ctx.lineTo(graph.x(bucket.bucket_start_ts), graph.y(bucket.setpoints.temp_min)));
        graph.ctx.closePath(); graph.ctx.fill();
      });
      drawSetpointLine(graph, "heater_off_threshold", "#ffc857", [4, 4]);
      drawSetpointLine(graph, "vent_threshold", "#d88cff", [9, 4]);
    }
    if (options.humidity) drawSetpointLine(graph, "humidity_threshold", "#ffc857", [5, 4]);
    visible.forEach((meta) => {
      const index = Math.max(0, series.findIndex((item) => item.key === meta.key));
      sensorSegments(meta.key).forEach((points) => {
        graph.ctx.fillStyle = `${colors[index % colors.length]}24`; graph.ctx.beginPath();
        points.forEach((point, pointIndex) => graph.ctx[pointIndex ? "lineTo" : "moveTo"](graph.x(point.ts), graph.y(point.max)));
        [...points].reverse().forEach((point) => graph.ctx.lineTo(graph.x(point.ts), graph.y(point.min)));
        graph.ctx.closePath(); graph.ctx.fill();
        graph.ctx.strokeStyle = colors[index % colors.length]; graph.ctx.lineWidth = 2; graph.ctx.setLineDash(seriesDashes[index % seriesDashes.length]); graph.ctx.beginPath();
        points.forEach((point, pointIndex) => graph.ctx[pointIndex ? "lineTo" : "moveTo"](graph.x(point.ts), graph.y(point.avg)));
        graph.ctx.stroke(); graph.ctx.setLineDash([]);
      });
    });
    drawEvents(graph); drawCrosshair(graph);
  };

  const hatch = (ctx, left, top, width, height, color) => {
    ctx.save(); ctx.beginPath(); ctx.rect(left, top, width, height); ctx.clip(); ctx.strokeStyle = color; ctx.lineWidth = 1;
    for (let offset = -height; offset < width + height; offset += 7) { ctx.beginPath(); ctx.moveTo(left + offset, top + height); ctx.lineTo(left + offset + height, top); ctx.stroke(); }
    ctx.restore();
  };
  const fitText = (ctx, value, maximumWidth) => {
    if (ctx.measureText(value).width <= maximumWidth) return value;
    let result = value; while (result.length > 2 && ctx.measureText(`${result}…`).width > maximumWidth) result = result.slice(0, -1);
    return `${result}…`;
  };
  const timelineFrame = (canvas, laneCount) => {
    const {context: ctx, width, height} = setup(canvas);
    const box = {left: width < 430 ? Math.min(112, width * .36) : 158, right: width - 8, top: 12, bottom: height - 29};
    const start = current.range_start_ts; const end = current.range_end_ts;
    const x = (timestamp) => box.left + (timestamp - start) / Math.max(1, end - start) * (box.right - box.left);
    ctx.clearRect(0, 0, width, height); ctx.strokeStyle = "rgba(176,205,186,.16)"; ctx.lineWidth = 1;
    const laneHeight = (box.bottom - box.top) / Math.max(1, laneCount);
    for (let index = 0; index <= laneCount; index += 1) { const yy = box.top + index * laneHeight; ctx.beginPath(); ctx.moveTo(box.left, yy); ctx.lineTo(box.right, yy); ctx.stroke(); }
    timeAxis(ctx, box, height, start, end, x);
    const graph = {ctx, x, box, width, height, start, end, laneHeight}; plots.set(canvas, graph); return graph;
  };
  const drawTimeline = (canvas, ids) => {
    if (!canvas) return;
    const present = ids.filter((id) => current.actuator_history?.[id]?.intervals?.length || current.buckets.some((bucket) => id in bucket.actuators));
    const lanes = present.length ? present : ids;
    const graph = timelineFrame(canvas, lanes.length); graph.ctx.font = `${graph.width < 430 ? 10 : 11}px system-ui`;
    if (!lanes.length) {
      graph.ctx.fillStyle = "#a0b9aa"; graph.ctx.font = "13px system-ui";
      graph.ctx.fillText("Toutes les pistes sont masquées", graph.box.left + 10, graph.box.top + 28);
      drawEvents(graph); drawCrosshair(graph); return;
    }
    lanes.forEach((id, index) => {
      const top = graph.box.top + index * graph.laneHeight + 4; const laneHeight = Math.max(5, graph.laneHeight - 8);
      graph.ctx.fillStyle = "rgba(160,185,170,.06)"; graph.ctx.fillRect(graph.box.left, top, graph.box.right - graph.box.left, laneHeight);
      hatch(graph.ctx, graph.box.left, top, graph.box.right - graph.box.left, laneHeight, "rgba(160,185,170,.20)");
      graph.ctx.fillStyle = "#dbe9df"; graph.ctx.fillText(fitText(graph.ctx, equipmentName(id), graph.box.left - 12), 2, top + laneHeight / 2 + 4);
      const exactIntervals = current.actuator_history?.[id]?.intervals || [];
      if (exactIntervals.length) {
        exactIntervals.forEach((interval) => {
          const left = Math.max(graph.box.left, graph.x(interval.start_ts));
          const right = Math.min(graph.box.right, graph.x(interval.end_ts)); const width = Math.max(1, right - left);
          if (right <= graph.box.left || left >= graph.box.right) return;
          if (interval.status !== "ok" || !Number.isFinite(interval.actual)) {
            hatch(graph.ctx, left, top, width, laneHeight, "rgba(255,107,107,.48)"); return;
          }
          graph.ctx.fillStyle = "#0d1812"; graph.ctx.fillRect(left, top, width, laneHeight);
          if (id === "motor") {
            const speed = Math.max(0, Math.min(4, Math.round(interval.actual))); const speedColors = ["rgba(160,185,170,.05)", "#245c42", "#2f8b5a", "#3fbd73", "#50e38a"];
            graph.ctx.fillStyle = speedColors[speed]; graph.ctx.fillRect(left, top, width, laneHeight);
            if (width > 18 && speed > 0) { graph.ctx.fillStyle = speed >= 3 ? "#062b15" : "#edf7f0"; graph.ctx.fillText(`V${speed}`, left + 3, top + laneHeight / 2 + 4); }
          } else if (interval.actual > 0) { graph.ctx.fillStyle = "#50e38a"; graph.ctx.fillRect(left, top, width, laneHeight); }
          if (interval.boundary_precision === "observed") hatch(graph.ctx, left, top, Math.min(width, 7), laneHeight, "rgba(245,189,79,.78)");
        });
        return;
      }
      current.buckets.forEach((bucket) => {
        const item = bucket.actuators[id]; const left = Math.max(graph.box.left, graph.x(bucket.bucket_start_ts));
        const right = Math.min(graph.box.right, graph.x(bucket.bucket_start_ts + current.bucket_seconds)); const width = Math.max(1, right - left + .5);
        if (!item || !item.valid_count || !Number.isFinite(item.avg_value)) { hatch(graph.ctx, left, top, width, laneHeight, "rgba(160,185,170,.32)"); return; }
        graph.ctx.fillStyle = "#0d1812"; graph.ctx.fillRect(left, top, width, laneHeight);
        if (id === "motor") {
          const speed = Math.max(0, Math.min(4, item.avg_value)); const speedColors = ["rgba(160,185,170,.05)", "#245c42", "#2f8b5a", "#3fbd73", "#50e38a"];
          graph.ctx.fillStyle = speedColors[Math.round(speed)]; graph.ctx.fillRect(left, top, width, laneHeight);
          if (item.min_value !== item.max_value) hatch(graph.ctx, left, top, width, laneHeight, "rgba(255,255,255,.42)");
          if (width > 18 && speed > 0) { graph.ctx.fillStyle = speed >= 3 ? "#062b15" : "#edf7f0"; graph.ctx.fillText(`V${Math.round(speed)}`, left + 3, top + laneHeight / 2 + 4); }
          return;
        }
        if (item.on_rate === 1) { graph.ctx.fillStyle = "#50e38a"; graph.ctx.fillRect(left, top, width, laneHeight); }
        else if (item.on_rate > 0) { graph.ctx.fillStyle = "rgba(245,189,79,.20)"; graph.ctx.fillRect(left, top, width, laneHeight); hatch(graph.ctx, left, top, width, laneHeight, "rgba(245,189,79,.72)"); }
      });
    });
    drawEvents(graph); drawCrosshair(graph);
  };

  const swatch = (kind, colorClass = "") => element("span", `chart-legend-swatch ${kind} ${colorClass}`);
  const legendItem = (label, kind, colorClass = "") => { const item = element("span", "chart-legend-item"); item.append(swatch(kind, colorClass), document.createTextNode(label)); return item; };
  const legendButton = (meta, index) => {
    const button = element("button", "chart-legend-button", meta.label); button.type = "button"; button.dataset.seriesKey = meta.key;
    button.setAttribute("aria-pressed", String(!hiddenSeries.has(meta.key))); button.prepend(swatch("is-line", `series-color-${index % colors.length} series-style-${index % 3}`)); return button;
  };
  const buildLegends = (temperature, humidity) => {
    document.getElementById("temperature-legend").replaceChildren(...temperature.map(legendButton), legendItem("plage min–max", "is-band", "series-color-0"), legendItem("zone cible", "is-band", "series-color-1"), legendItem("arrêt chauffage", "is-dashed", "series-color-2"), legendItem("départ ventilation", "is-long-dash", "series-color-3"), legendItem("alarme", "is-event-alarm"), legendItem("configuration", "is-event-config"));
    document.getElementById("humidity-legend").replaceChildren(...humidity.map(legendButton), legendItem("plage min–max", "is-band", "series-color-0"), legendItem("seuil humidité", "is-dashed", "series-color-2"), legendItem("alarme", "is-event-alarm"), legendItem("configuration", "is-event-config"));
    document.getElementById("automation-legend").replaceChildren(legendItem("ON GPIO relu", "", "series-color-0"), legendItem("OFF GPIO relu", "is-off"), legendItem("bascule détectée à la minute", "is-mixed"), legendItem("non couvert", "is-unknown"), legendItem("alarme", "is-event-alarm"), legendItem("configuration", "is-event-config"));
    document.getElementById("climate-actuator-legend").replaceChildren(legendItem("chauffage ON relu", "", "series-color-0"), legendItem("arrêt relu", "is-off"), legendItem("ventilation V1 → V4", "is-band", "series-color-0"), legendItem("bascule détectée à la minute", "is-mixed"), legendItem("non couvert", "is-unknown"), legendItem("alarme", "is-event-alarm"), legendItem("configuration", "is-event-config"));
  };

  const actuatorStats = (id) => {
    const history = current.actuator_history?.[id];
    if (history?.intervals?.length) {
      const valid = history.intervals.filter((interval) => interval.status === "ok" && Number.isFinite(interval.actual));
      const coverage = Number(history.coverage_ratio || 0) * 100;
      const active = history.covered_seconds ? history.on_seconds / history.covered_seconds * 100 : 0;
      const last = valid.at(-1);
      const approximate = history.duration_precision === "observed";
      if (id === "motor") {
        const speeds = Object.entries(history.speed_seconds || {}).filter(([, duration]) => duration > 0).map(([speed]) => Number(speed));
        const weighted = Object.entries(history.speed_seconds || {}).reduce((sum, [speed, duration]) => sum + Number(speed) * duration, 0);
        return {exact: true, approximate, minimum: speeds.length ? Math.min(...speeds) : 0, average: history.covered_seconds ? weighted / history.covered_seconds : 0, maximum: speeds.length ? Math.max(...speeds) : 0, active, activeDuration: history.on_seconds, coverage, transitions: history.transition_count, currentState: last ? `V${last.actual}` : "inconnu"};
      }
      return {exact: true, approximate, active, activeDuration: history.on_seconds, coverage, transitions: history.transition_count, currentState: last ? (last.actual > 0 ? "ON" : "OFF") : "inconnu"};
    }
    const points = current.buckets.map((bucket) => ({ts: bucket.bucket_start_ts, item: bucket.actuators[id]})).filter((point) => point.item?.valid_count);
    if (!points.length) return null;
    const items = points.map((point) => point.item);
    if (id === "motor") {
      const values = items.map((item) => item.avg_value).filter(Number.isFinite);
      const rates = items.map((item) => item.on_rate).filter(Number.isFinite);
      if (!values.length || !rates.length) return null;
      return {minimum: Math.min(...values), average: values.reduce((sum, value) => sum + value, 0) / values.length, maximum: Math.max(...values), active: rates.reduce((sum, value) => sum + value, 0) / rates.length * 100};
    }
    const rates = items.map((item) => item.on_rate).filter(Number.isFinite); const states = rates.map((value) => value > 0);
    if (!rates.length) return null;
    const transitions = states.slice(1).filter((state, index) => state !== states[index] && points[index + 1].ts - points[index].ts <= current.bucket_seconds * 2.5).length;
    return {active: rates.reduce((sum, value) => sum + value, 0) / rates.length * 100, transitions, currentState: states.at(-1) ? "ON" : "OFF"};
  };
  const renderGroupSummary = (container, ids) => {
    container.replaceChildren(...ids.map((id) => {
      const stats = actuatorStats(id); const item = element("button", "chart-summary-item"); item.type = "button"; item.dataset.actuatorKey = id; item.setAttribute("aria-pressed", String(!hiddenActuators.has(id)));
      const detail = !stats ? "Aucune observation"
        : stats.exact && id === "motor" ? `${stats.approximate ? "≈ " : ""}${formatDuration(stats.activeDuration)} en marche · max V${formatNumber(stats.maximum, 0)} · couverture ${formatNumber(stats.coverage, 0)} %`
          : stats.exact ? `${stats.approximate ? "≈ " : ""}${formatDuration(stats.activeDuration)} ON · ${stats.transitions} bascule(s) · couverture ${formatNumber(stats.coverage, 0)} %`
            : id === "motor" ? `Moy. V${formatNumber(stats.average)} · max V${formatNumber(stats.maximum, 0)} · active ${formatNumber(stats.active, 0)} %`
              : `${formatNumber(stats.active, 0)} % ON · ${stats.transitions} bascule(s) · ${stats.currentState}`;
      item.append(element("strong", "", equipmentName(id)), element("span", "", detail)); return item;
    }));
  };

  const buildAdditionalCharts = (units) => {
    const additional = document.getElementById("additional-charts"); additional.replaceChildren();
    units.forEach((unit, index) => {
      const id = `additional-${index}`; const card = element("article", "card chart-card"); const title = element("h3", "", `Mesures · ${unit}`);
      const legend = element("div", "chart-legend"); legend.id = `${id}-legend`; legend.setAttribute("role", "group"); legend.setAttribute("aria-label", `Légende des mesures en ${unit}`);
      const summary = element("p", "chart-summary", ""); summary.id = `${id}-summary`;
      const canvas = document.createElement("canvas"); canvas.dataset.chartHeight = "260"; canvas.dataset.historyChart = "sensor-additional"; canvas.dataset.historyUnit = unit; canvas.height = 260; canvas.tabIndex = 0;
      canvas.setAttribute("role", "img"); canvas.setAttribute("aria-label", `Tendances des mesures en ${unit}. Utilisez les flèches gauche et droite pour explorer les valeurs.`); canvas.setAttribute("aria-describedby", summary.id);
      const series = current.series.filter((item) => item.unit === unit);
      legend.replaceChildren(...series.map(legendButton), legendItem("plage min–max", "is-band", "series-color-0"), legendItem("alarme", "is-event-alarm"), legendItem("configuration", "is-event-config"));
      summary.textContent = sensorSummary(series, unit); card.append(title, legend, summary, canvas); additional.append(card);
    });
  };
  const buildTable = () => {
    const rows = [];
    current.series.forEach((meta) => {
      const values = valuesFor(meta.key); const averages = current.buckets.map((bucket) => bucket.sensors[meta.key]?.avg).filter(Number.isFinite); if (!values.length) return;
      rows.push([meta.label, "Capteur", `${formatNumber(Math.min(...values), meta.decimals)} ${meta.unit}`, `${formatNumber(averages.reduce((sum, value) => sum + value, 0) / averages.length, meta.decimals)} ${meta.unit}`, `${formatNumber(Math.max(...values), meta.decimals)} ${meta.unit}`, "—"]);
    });
    Object.values(groups).flat().forEach((id) => {
      const stats = actuatorStats(id); if (!stats) return;
      rows.push(id === "motor" ? [equipmentName(id), "Actionneur", `V${formatNumber(stats.minimum, 0)}`, `V${formatNumber(stats.average)}`, `V${formatNumber(stats.maximum, 0)}`, stats.exact ? `${stats.approximate ? "≈ " : ""}${formatDuration(stats.activeDuration)} · couverture ${formatNumber(stats.coverage, 0)} %` : `${formatNumber(stats.active, 0)} %`] : [equipmentName(id), "Actionneur", "OFF", "—", "ON", stats.exact ? `${stats.approximate ? "≈ " : ""}${formatDuration(stats.activeDuration)} ON · ${stats.transitions} bascule(s) · couverture ${formatNumber(stats.coverage, 0)} %` : `${formatNumber(stats.active, 0)} % ON · ${stats.transitions} bascule(s)`]);
    });
    document.getElementById("history-data-body").replaceChildren(...rows.map((values) => {
      const row = document.createElement("tr"); values.forEach((value, index) => { const cell = document.createElement(index ? "td" : "th"); if (!index) cell.scope = "row"; cell.textContent = value; row.append(cell); }); return row;
    }));
  };
  const drawAll = () => {
    if (!current) return;
    const temperature = current.series.filter((item) => item.unit.includes("°C")); const humidity = current.series.filter((item) => item.unit.includes("%"));
    drawSensorChart(document.getElementById("temperature-chart"), temperature, "°C", {temperature: true});
    drawSensorChart(document.getElementById("humidity-chart"), humidity, "%", {humidity: true});
    drawTimeline(document.getElementById("automation-chart"), groups.automation.filter((id) => !hiddenActuators.has(id))); drawTimeline(document.getElementById("climate-actuator-chart"), groups["climate-actuator"].filter((id) => !hiddenActuators.has(id)));
    document.querySelectorAll("[data-history-unit]").forEach((canvas) => { const unit = canvas.dataset.historyUnit; drawSensorChart(canvas, current.series.filter((item) => item.unit === unit), unit); });
  };
  const render = (data) => {
    current = data; selectedTimestamp = null; plots.clear();
    const temperature = data.series.filter((item) => item.unit.includes("°C")); const humidity = data.series.filter((item) => item.unit.includes("%"));
    const otherUnits = [...new Set(data.series.filter((item) => !item.unit.includes("°C") && !item.unit.includes("%")).map((item) => item.unit))];
    buildLegends(temperature, humidity); buildAdditionalCharts(otherUnits);
    document.getElementById("temperature-summary").textContent = sensorSummary(temperature, "°C"); document.getElementById("humidity-summary").textContent = sensorSummary(humidity, "%");
    renderGroupSummary(document.getElementById("automation-summary"), groups.automation); renderGroupSummary(document.getElementById("climate-actuator-summary"), groups["climate-actuator"]);
    buildTable(); drawAll();
    const exactCount = Object.values(data.actuator_history || {}).filter((item) => item.intervals?.length).length;
    message.textContent = `${data.buckets.length} intervalle(s) de ${Math.round(data.bucket_seconds / 60)} min · courbes : moyenne et plage min–max · ${exactCount} actionneur(s) avec transitions GPIO relues. Les lacunes ne sont pas interpolées.`;
  };

  const nearestBucketIndex = (timestamp) => {
    if (!current?.buckets.length) return -1;
    let low = 0; let high = current.buckets.length - 1;
    while (low < high) { const middle = Math.floor((low + high) / 2); if (current.buckets[middle].bucket_start_ts < timestamp) low = middle + 1; else high = middle; }
    return low > 0 && Math.abs(current.buckets[low - 1].bucket_start_ts - timestamp) < Math.abs(current.buckets[low].bucket_start_ts - timestamp) ? low - 1 : low;
  };
  const selectedDetails = (bucket) => {
    const entries = [];
    current.series.forEach((meta) => { const item = bucket.sensors[meta.key]; entries.push([meta.label, item?.valid_count ? `${formatNumber(item.avg, meta.decimals)} ${meta.unit}` : "inconnue"]); });
    Object.values(groups).flat().forEach((id) => {
      const item = bucket.actuators[id]; let value = "inconnu";
      const interval = (current.actuator_history?.[id]?.intervals || []).find((entry) => entry.start_ts <= bucket.bucket_start_ts && entry.end_ts > bucket.bucket_start_ts);
      if (interval?.status === "ok" && Number.isFinite(interval.actual)) {
        value = id === "motor" ? `V${formatNumber(interval.actual, 0)} (GPIO relu)` : `${interval.actual > 0 ? "ON" : "OFF"} (GPIO relu)`;
      } else if (item?.valid_count && Number.isFinite(item.avg_value)) {
        if (id === "motor") value = item.min_value === item.max_value ? `V${formatNumber(item.avg_value, 0)}` : `V${formatNumber(item.min_value, 0)} à V${formatNumber(item.max_value, 0)}`;
        else value = item.on_rate === 1 ? "ON" : item.on_rate === 0 ? "OFF" : "mixte dans l’intervalle";
      }
      entries.push([equipmentName(id), value]);
    });
    const events = (current.events || []).filter((event) => Math.abs(event.ts - bucket.bucket_start_ts) <= current.bucket_seconds / 2);
    if (events.length) entries.push(["Événement", events.map((event) => event.kind === "alarm" ? "alarme" : "configuration").join(", ")]);
    return entries;
  };
  const showSelection = (timestamp, position = null, announce = false) => {
    const index = nearestBucketIndex(timestamp); if (index < 0) return;
    const bucket = current.buckets[index]; selectedTimestamp = bucket.bucket_start_ts; pointerPosition = position || pointerPosition;
    const details = selectedDetails(bucket); const title = element("strong", "", formatDate(bucket.bucket_start_ts, true)); const list = document.createElement("dl");
    details.forEach(([label, value]) => list.append(element("dt", "", label), element("dd", "", value))); tooltip.replaceChildren(title, list); tooltip.hidden = false;
    const point = pointerPosition || {x: window.innerWidth / 2, y: 80}; const tooltipWidth = Math.min(304, window.innerWidth - 16);
    tooltip.style.left = `${Math.max(8, Math.min(point.x + 14, window.innerWidth - tooltipWidth - 8))}px`;
    tooltip.style.top = `${Math.max(8, Math.min(point.y + 14, window.innerHeight - Math.min(tooltip.offsetHeight || 300, window.innerHeight - 16) - 8))}px`;
    if (announce) selectionOutput.textContent = `${formatDate(bucket.bucket_start_ts, true)}. ${details.map(([label, value]) => `${label} : ${value}`).join(". ")}`;
    drawAll();
  };
  const scheduleSelection = (event, canvas) => {
    const graph = plots.get(canvas); if (!graph) return;
    const rect = canvas.getBoundingClientRect(); const localX = event.clientX - rect.left;
    const timestamp = graph.start + (localX - graph.box.left) / Math.max(1, graph.box.right - graph.box.left) * (graph.end - graph.start);
    pointerPosition = {x: event.clientX, y: event.clientY}; if (redrawFrame !== null) cancelAnimationFrame(redrawFrame);
    redrawFrame = requestAnimationFrame(() => { redrawFrame = null; showSelection(Math.max(graph.start, Math.min(graph.end, timestamp)), pointerPosition); });
  };

  section.addEventListener("click", (event) => {
    const actuatorButton = event.target.closest("[data-actuator-key]");
    if (actuatorButton) {
      const id = actuatorButton.dataset.actuatorKey; if (hiddenActuators.has(id)) hiddenActuators.delete(id); else hiddenActuators.add(id);
      actuatorButton.setAttribute("aria-pressed", String(!hiddenActuators.has(id))); drawAll(); return;
    }
    const button = event.target.closest("[data-series-key]"); if (!button) return;
    const key = button.dataset.seriesKey; if (hiddenSeries.has(key)) hiddenSeries.delete(key); else hiddenSeries.add(key);
    document.querySelectorAll(`[data-series-key="${CSS.escape(key)}"]`).forEach((item) => item.setAttribute("aria-pressed", String(!hiddenSeries.has(key)))); drawAll();
  });
  section.addEventListener("pointermove", (event) => { const canvas = event.target.closest("canvas[data-history-chart]"); if (canvas) scheduleSelection(event, canvas); });
  section.addEventListener("pointerdown", (event) => { const canvas = event.target.closest("canvas[data-history-chart]"); if (canvas) scheduleSelection(event, canvas); });
  section.addEventListener("pointerleave", () => { tooltip.hidden = true; pointerPosition = null; });
  section.addEventListener("keydown", (event) => {
    const canvas = event.target.closest("canvas[data-history-chart]"); if (!canvas || !current?.buckets.length) return;
    if (event.key === "Escape") { selectedTimestamp = null; tooltip.hidden = true; selectionOutput.textContent = "Sélection effacée."; drawAll(); return; }
    if (!["ArrowLeft", "ArrowRight", "Home", "End"].includes(event.key)) return;
    event.preventDefault(); let index = Number.isFinite(selectedTimestamp) ? nearestBucketIndex(selectedTimestamp) : current.buckets.length - 1;
    if (event.key === "ArrowLeft") index -= 1; if (event.key === "ArrowRight") index += 1; if (event.key === "Home") index = 0; if (event.key === "End") index = current.buckets.length - 1;
    index = Math.max(0, Math.min(current.buckets.length - 1, index)); const rect = canvas.getBoundingClientRect();
    showSelection(current.buckets[index].bucket_start_ts, {x: rect.left + rect.width / 2, y: rect.top + 30}, true);
  });

  const load = async (hours) => {
    message.textContent = "Chargement de l’historique…"; tooltip.hidden = true; section.setAttribute("aria-busy", "true");
    try {
      const response = await fetch(`/api/v1/history?hours=${hours}`, {headers: {Accept: "application/json"}, cache: "no-store"}); await window.PhytoPwa?.markServerContact();
      if (!response.ok) throw new Error(`HTTP ${response.status}`); const data = await response.json(); await window.PhytoPwa?.storeSnapshot("history", data, Date.now()); render(data);
    } catch (error) {
      if (error instanceof TypeError) window.PhytoPwa?.markServerFailure(); const stored = await window.PhytoPwa?.loadSnapshot("history");
      if (stored?.data) {
        render(stored.data); const storedHours = Number(stored.data.hours || hours); document.querySelectorAll("[data-hours]").forEach((item) => { const selected = Number(item.dataset.hours) === storedHours; item.classList.toggle("is-selected", selected); item.setAttribute("aria-pressed", String(selected)); });
        const age = Math.max(0, Math.round((Date.now() - stored.receivedAt) / 60000)); message.textContent = `Historique enregistré il y a ${age} min · données non actualisées, lacunes conservées.`;
      } else message.textContent = `Historique local indisponible (${error.message}). Aucune vue enregistrée ; le contrôle reste actif.`;
    } finally {
      section.setAttribute("aria-busy", "false");
    }
  };
  document.querySelectorAll("[data-hours]").forEach((button) => button.addEventListener("click", () => { document.querySelectorAll("[data-hours]").forEach((item) => { const selected = item === button; item.classList.toggle("is-selected", selected); item.setAttribute("aria-pressed", String(selected)); }); load(Number(button.dataset.hours)); }));
  let resizeTimer; window.addEventListener("resize", () => { clearTimeout(resizeTimer); resizeTimer = setTimeout(() => current && drawAll(), 150); });
  if (section.dataset.historyAvailable === "true") load(24); else message.textContent = "Historique local indisponible. Le contrôle reste actif et InfluxDB n’est pas requis pour cette vue.";
})();
