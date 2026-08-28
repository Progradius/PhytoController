(() => {
  "use strict";
  const section = document.getElementById("tendances");
  if (!section) return;
  const message = document.getElementById("history-message");
  const colors = ["#50e38a", "#65b9ff", "#ffc857", "#d88cff", "#ff7b7b", "#8ee3ef"];
  let current = null;

  const setup = (canvas) => {
    const ratio = window.devicePixelRatio || 1;
    const width = Math.max(320, canvas.clientWidth || canvas.parentElement.clientWidth - 32);
    const height = Number(canvas.dataset.chartHeight) || 220;
    canvas.width = Math.round(width * ratio); canvas.height = Math.round(height * ratio);
    const context = canvas.getContext("2d"); context.setTransform(ratio, 0, 0, ratio, 0, 0);
    return {context, width, height};
  };
  const frame = (canvas, minimum, maximum, start, end, label) => {
    const {context: ctx, width, height} = setup(canvas);
    const box = {left: 48, right: width - 12, top: 18, bottom: height - 30};
    const range = Math.max(1e-6, maximum - minimum);
    const x = (timestamp) => box.left + (timestamp - start) / (end - start) * (box.right - box.left);
    const y = (value) => box.bottom - (value - minimum) / range * (box.bottom - box.top);
    ctx.clearRect(0, 0, width, height); ctx.font = "11px system-ui"; ctx.fillStyle = "#87968d";
    ctx.strokeStyle = "rgba(176,205,186,.16)"; ctx.lineWidth = 1;
    for (let index = 0; index <= 4; index += 1) {
      const yy = box.top + index / 4 * (box.bottom - box.top); ctx.beginPath(); ctx.moveTo(box.left, yy); ctx.lineTo(box.right, yy); ctx.stroke();
      const value = maximum - index / 4 * range; ctx.fillText(`${value.toFixed(range < 10 ? 1 : 0)}${label}`, 3, yy + 4);
    }
    [0, .5, 1].forEach((portion) => {
      const ts = start + portion * (end - start); const xx = x(ts);
      ctx.fillText(new Date(ts * 1000).toLocaleString("fr-FR", {day: "2-digit", hour: "2-digit", minute: "2-digit"}), Math.max(box.left, Math.min(xx - 42, box.right - 84)), height - 8);
    });
    return {ctx, x, y, box};
  };
  const valuesFor = (data, key) => data.buckets.flatMap((bucket) => {
    const item = bucket.sensors[key]; return item && item.valid_count ? [item.min, item.avg, item.max].filter(Number.isFinite) : [];
  });
  const segments = (data, key) => {
    const result = []; let segment = [];
    data.buckets.forEach((bucket) => {
      const item = bucket.sensors[key]; const point = item && item.valid_count ? {ts: bucket.bucket_start_ts, ...item} : null;
      if (!point || (segment.length && point.ts - segment.at(-1).ts > data.bucket_seconds * 2.5)) { if (segment.length) result.push(segment); segment = []; }
      if (point) segment.push(point);
    });
    if (segment.length) result.push(segment); return result;
  };
  const drawSensorChart = (canvas, data, series, unit, setpoints = false) => {
    let values = series.flatMap((item) => valuesFor(data, item.key));
    if (setpoints) data.buckets.forEach((bucket) => values.push(bucket.setpoints.temp_min, bucket.setpoints.temp_max));
    values = values.filter(Number.isFinite);
    if (!values.length) { const empty = setup(canvas); empty.context.fillStyle = "#87968d"; empty.context.fillText("Aucune mesure valide sur cette période", 20, 40); return; }
    const padding = Math.max(1, (Math.max(...values) - Math.min(...values)) * .12);
    const graph = frame(canvas, Math.min(...values) - padding, Math.max(...values) + padding, data.range_start_ts, data.range_end_ts, unit);
    if (setpoints) {
      const targetSegments = []; let targetSegment = [];
      data.buckets.forEach((bucket) => {
        const valid = Number.isFinite(bucket.setpoints.temp_min) && Number.isFinite(bucket.setpoints.temp_max);
        if (!valid || (targetSegment.length && bucket.bucket_start_ts - targetSegment.at(-1).bucket_start_ts > data.bucket_seconds * 2.5)) { if (targetSegment.length) targetSegments.push(targetSegment); targetSegment = []; }
        if (valid) targetSegment.push(bucket);
      });
      if (targetSegment.length) targetSegments.push(targetSegment);
      targetSegments.forEach((targetPoints) => {
        graph.ctx.fillStyle = "rgba(101,185,255,.09)"; graph.ctx.beginPath();
        targetPoints.forEach((bucket, index) => graph.ctx[index ? "lineTo" : "moveTo"](graph.x(bucket.bucket_start_ts), graph.y(bucket.setpoints.temp_max)));
        [...targetPoints].reverse().forEach((bucket) => graph.ctx.lineTo(graph.x(bucket.bucket_start_ts), graph.y(bucket.setpoints.temp_min))); graph.ctx.closePath(); graph.ctx.fill();
      });
    }
    series.forEach((meta, index) => {
      graph.ctx.fillStyle = colors[index % colors.length];
      graph.ctx.fillText(meta.label, graph.box.left + index * 118, 11);
      segments(data, meta.key).forEach((points) => {
      graph.ctx.fillStyle = `${colors[index % colors.length]}22`; graph.ctx.beginPath();
      points.forEach((point, i) => graph.ctx[i ? "lineTo" : "moveTo"](graph.x(point.ts), graph.y(point.max)));
      [...points].reverse().forEach((point) => graph.ctx.lineTo(graph.x(point.ts), graph.y(point.min))); graph.ctx.closePath(); graph.ctx.fill();
      graph.ctx.strokeStyle = colors[index % colors.length]; graph.ctx.lineWidth = 1.8; graph.ctx.beginPath();
      points.forEach((point, i) => graph.ctx[i ? "lineTo" : "moveTo"](graph.x(point.ts), graph.y(point.avg))); graph.ctx.stroke();
      });
    });
    if (setpoints) ["temp_min", "temp_max"].forEach((key, index) => {
      graph.ctx.strokeStyle = index ? "#ff9d66" : "#72a9ff"; graph.ctx.setLineDash([5, 4]); graph.ctx.beginPath(); let drawing = false;
      let previousTs = null;
      data.buckets.forEach((bucket) => { const value = bucket.setpoints[key]; if (!Number.isFinite(value) || (previousTs !== null && bucket.bucket_start_ts - previousTs > data.bucket_seconds * 2.5)) { drawing = false; previousTs = null; if (!Number.isFinite(value)) return; } graph.ctx[drawing ? "lineTo" : "moveTo"](graph.x(bucket.bucket_start_ts), graph.y(value)); drawing = true; previousTs = bucket.bucket_start_ts; }); graph.ctx.stroke(); graph.ctx.setLineDash([]);
    });
    drawMarkers(graph, data.events);
  };
  const drawMarkers = (graph, events) => (events || []).forEach((event) => {
    const xx = graph.x(event.ts); if (xx < graph.box.left || xx > graph.box.right) return;
    graph.ctx.strokeStyle = event.kind === "alarm" ? "rgba(255,107,107,.65)" : "rgba(255,200,87,.55)"; graph.ctx.lineWidth = 1; graph.ctx.beginPath(); graph.ctx.moveTo(xx, graph.box.top); graph.ctx.lineTo(xx, graph.box.bottom); graph.ctx.stroke();
  });
  const drawActuators = (canvas, data) => {
    const ids = [...new Set(data.buckets.flatMap((bucket) => Object.keys(bucket.actuators)))].sort();
    const graph = frame(canvas, 0, 100, data.range_start_ts, data.range_end_ts, "%");
    ids.forEach((id, index) => { graph.ctx.strokeStyle = colors[index % colors.length]; graph.ctx.lineWidth = 1.7; graph.ctx.beginPath(); let previous = null;
      data.buckets.forEach((bucket) => { const value = bucket.actuators[id]?.on_rate; if (!Number.isFinite(value) || (previous && bucket.bucket_start_ts - previous > data.bucket_seconds * 2.5)) { previous = null; if (!Number.isFinite(value)) return; } graph.ctx[previous === null ? "moveTo" : "lineTo"](graph.x(bucket.bucket_start_ts), graph.y(value * 100)); previous = bucket.bucket_start_ts; }); graph.ctx.stroke();
      graph.ctx.fillStyle = colors[index % colors.length]; graph.ctx.fillText(id, graph.box.left + index * 78, 11);
    }); drawMarkers(graph, data.events);
  };
  const render = (data) => {
    current = data; const temperature = data.series.filter((item) => item.unit.includes("°C")); const humidity = data.series.filter((item) => item.unit.includes("%"));
    drawSensorChart(document.getElementById("temperature-chart"), data, temperature, "°C", true);
    drawSensorChart(document.getElementById("humidity-chart"), data, humidity, "%");
    drawActuators(document.getElementById("actuator-chart"), data);
    const additional = document.getElementById("additional-charts");
    additional.replaceChildren();
    const otherUnits = [...new Set(data.series
      .filter((item) => !item.unit.includes("°C") && !item.unit.includes("%"))
      .map((item) => item.unit))];
    otherUnits.forEach((unit) => {
      const card = document.createElement("article"); card.className = "card chart-card";
      const title = document.createElement("h3"); title.textContent = `Mesures · ${unit}`;
      const canvas = document.createElement("canvas"); canvas.dataset.chartHeight = "240"; canvas.height = 240;
      canvas.setAttribute("aria-label", `Tendances des mesures en ${unit}`);
      card.append(title, canvas); additional.append(card);
      drawSensorChart(canvas, data, data.series.filter((item) => item.unit === unit), unit);
    });
    message.textContent = `${data.buckets.length} intervalle(s) · bandes min/moyenne/max · traits verticaux : alarmes et configuration. Les lacunes ne sont pas interpolées.`;
  };
  const load = async (hours) => { message.textContent = "Chargement de l’historique…";
    try {
      const response = await fetch(`/api/v1/history?hours=${hours}`, {headers: {Accept: "application/json"}, cache: "no-store"});
      await window.PhytoPwa?.markServerContact();
      if (!response.ok) throw new Error(`HTTP ${response.status}`);
      const data = await response.json();
      await window.PhytoPwa?.storeSnapshot("history", data, Date.now());
      render(data);
    }
    catch (error) {
      if (error instanceof TypeError) window.PhytoPwa?.markServerFailure();
      const stored = await window.PhytoPwa?.loadSnapshot("history");
      if (stored?.data) {
        render(stored.data);
        const storedHours = Number(stored.data.hours || hours);
        document.querySelectorAll("[data-hours]").forEach((item) => item.classList.toggle("is-selected", Number(item.dataset.hours) === storedHours));
        const age = Math.max(0, Math.round((Date.now() - stored.receivedAt) / 60000));
        message.textContent = `Historique enregistré il y a ${age} min · données non actualisées, lacunes conservées.`;
      } else {
        message.textContent = `Historique local indisponible (${error.message}). Aucune vue enregistrée ; le contrôle reste actif.`;
      }
    }
  };
  document.querySelectorAll("[data-hours]").forEach((button) => button.addEventListener("click", () => { document.querySelectorAll("[data-hours]").forEach((item) => item.classList.toggle("is-selected", item === button)); load(Number(button.dataset.hours)); }));
  let resizeTimer; window.addEventListener("resize", () => { clearTimeout(resizeTimer); resizeTimer = setTimeout(() => current && render(current), 150); });
  if (section.dataset.historyAvailable === "true") load(24); else message.textContent = "Historique local indisponible. Le contrôle reste actif et InfluxDB n’est pas requis pour cette vue.";
})();
