(() => {
  "use strict";
  const preview = document.querySelector("[data-history-preview]");
  const section = document.getElementById("tendances");
  if (!section && !preview) return;
  const themeColor = (name, fallback) => getComputedStyle(document.documentElement).getPropertyValue(name).trim() || fallback;
  // Plancher de lisibilité des textes de graphique (fiche R2.2) : 13 px, une seule définition
  // pour les six emplacements qui l'employaient en clair. La taille est en pixels CSS et le
  // contexte est mis à l'échelle du `devicePixelRatio` dans `setup()` : elle reste stable
  // d'un écran à l'autre. Ce qui s'ajuste sous cette taille, c'est la place réservée aux
  // libellés, jamais la police.
  const AXIS_FONT = "13px system-ui";
  const requestWithTimeout = (resource, options, timeout) => window.PhytoPwa?.fetchWithTimeout
    ? window.PhytoPwa.fetchWithTimeout(resource, options, timeout)
    : fetch(resource, options);

  const initPreview = () => {
    const message = document.getElementById("history-preview-message");
    const canvas = document.getElementById("history-preview-chart");
    const dataRoot = preview.querySelector(".history-preview-data");
    const emptyRoot = preview.querySelector(".history-preview-empty");
    let visible = false; let loaded = false; let refreshTimer = null;
    let currentPreview = null;
    let observed = false;
    const showData = (shown) => { if (dataRoot) dataRoot.hidden = !shown; if (emptyRoot) emptyRoot.hidden = shown; if (message) message.hidden = !shown; };
    const format = (value, decimals = 1) => Number.isFinite(value) ? Number(value).toLocaleString("fr-FR", {minimumFractionDigits: decimals, maximumFractionDigits: decimals}) : "—";
    const duration = (seconds) => {
      if (!Number.isFinite(seconds)) return "—";
      const minutes = Math.max(0, Math.round(seconds / 60)); const hours = Math.floor(minutes / 60);
      return hours ? `${hours} h ${String(minutes % 60).padStart(2, "0")} min` : `${minutes} min`;
    };
    const sensorValues = (data, key) => data.buckets.flatMap((bucket) => {
      const item = bucket.sensors[key]; return item?.valid_count ? [item.min, item.avg, item.max].filter(Number.isFinite) : [];
    });
    const summary = (data, key, unit) => {
      const values = sensorValues(data, key); const averages = data.buckets.map((bucket) => bucket.sensors[key]?.avg).filter(Number.isFinite);
      return values.length && averages.length ? `${format(Math.min(...values))} / ${format(averages.reduce((sum, value) => sum + value, 0) / averages.length)} / ${format(Math.max(...values))} ${unit}` : "Aucune donnée";
    };
    const activity = (data, id) => {
      const exact = data.actuator_history?.[id];
      if (exact?.intervals?.length) {
        const coverage = Number(exact.coverage_ratio || 0) * 100; const approximate = exact.duration_precision === "observed" ? "≈ " : "";
        if (id === "motor") {
          const speeds = Object.entries(exact.speed_seconds || {}).filter(([, seconds]) => seconds > 0).map(([speed]) => Number(speed));
          return `${approximate}${duration(exact.on_seconds)} · max V${speeds.length ? Math.max(...speeds) : 0} · couverture ${format(coverage, 0)} %`;
        }
        return `${approximate}${duration(exact.on_seconds)} ON · couverture ${format(coverage, 0)} %`;
      }
      const items = data.buckets.map((bucket) => bucket.actuators[id]).filter((item) => item?.valid_count && Number.isFinite(item.on_rate));
      if (!items.length) return "Aucune observation";
      const rate = items.reduce((sum, item) => sum + item.on_rate, 0) / items.length * 100;
      if (id === "motor") return `${format(rate, 0)} % d’observations actives · agrégé`;
      return `${format(rate, 0)} % d’observations ON · agrégé`;
    };
    const draw = (data, key) => {
      if (!canvas) return;
      const ratio = window.devicePixelRatio || 1; const width = Math.max(1, Math.floor(canvas.clientWidth || 280)); const height = Number(canvas.dataset.chartHeight) || 180;
      canvas.width = Math.round(width * ratio); canvas.height = Math.round(height * ratio); const ctx = canvas.getContext("2d"); ctx.setTransform(ratio, 0, 0, ratio, 0, 0); ctx.clearRect(0, 0, width, height);
      const points = data.buckets.map((bucket) => ({ts: bucket.bucket_start_ts, value: bucket.sensors[key]?.avg, min: bucket.setpoints?.temp_min, max: bucket.setpoints?.temp_max}));
      const values = points.flatMap((point) => [point.value, point.min, point.max]).filter(Number.isFinite);
      if (!values.length) { ctx.fillStyle = themeColor("--chart-muted", "#a0b9aa"); ctx.font = AXIS_FONT; ctx.fillText("Aucune température valide", 16, 36); return; }
      const box = {left: 42, right: width - 8, top: 10, bottom: height - 25}; const low = Math.min(...values) - 1; const high = Math.max(...values) + 1;
      const x = (ts) => box.left + (ts - data.range_start_ts) / Math.max(1, data.range_end_ts - data.range_start_ts) * (box.right - box.left); const y = (value) => box.bottom - (value - low) / Math.max(.1, high - low) * (box.bottom - box.top);
      ctx.font = AXIS_FONT; ctx.fillStyle = themeColor("--chart-muted", "#a0b9aa"); ctx.strokeStyle = themeColor("--chart-grid", "rgba(176,205,186,.16)");
      for (let index = 0; index <= 3; index += 1) { const yy = box.top + index / 3 * (box.bottom - box.top); ctx.beginPath(); ctx.moveTo(box.left, yy); ctx.lineTo(box.right, yy); ctx.stroke(); ctx.fillText(`${(high - index / 3 * (high - low)).toFixed(1)}°`, 2, yy + 3); }
      const target = points.filter((point) => Number.isFinite(point.min) && Number.isFinite(point.max));
      if (target.length) { ctx.fillStyle = `${themeColor("--chart-1", "#65b9ff")}22`; ctx.beginPath(); target.forEach((point, index) => ctx[index ? "lineTo" : "moveTo"](x(point.ts), y(point.max))); [...target].reverse().forEach((point) => ctx.lineTo(x(point.ts), y(point.min))); ctx.closePath(); ctx.fill(); }
      let drawing = false; ctx.strokeStyle = themeColor("--chart-0", "#50e38a"); ctx.lineWidth = 2; ctx.beginPath();
      points.forEach((point) => { if (!Number.isFinite(point.value)) { if (drawing) ctx.stroke(); ctx.beginPath(); drawing = false; return; } ctx[drawing ? "lineTo" : "moveTo"](x(point.ts), y(point.value)); drawing = true; }); if (drawing) ctx.stroke();
    };
    const render = (data, storedAge = null) => {
      currentPreview = data; showData(true);
      const temperature = data.series.find((item) => item.control_role === "climate_temperature") || data.series.find((item) => item.unit?.includes("°C"));
      const humidity = data.series.find((item) => item.control_role === "climate_humidity") || data.series.find((item) => item.unit?.includes("%"));
      if (temperature) draw(data, temperature.key);
      document.getElementById("preview-temperature").textContent = temperature ? summary(data, temperature.key, temperature.unit) : "Aucune donnée";
      document.getElementById("preview-humidity").textContent = humidity ? summary(data, humidity.key, humidity.unit) : "Aucune donnée";
      document.getElementById("preview-heater").textContent = activity(data, "heater"); document.getElementById("preview-motor").textContent = activity(data, "motor");
      message.textContent = storedAge === null ? "Min / moyenne / max · durées issues des changements d’état relevés." : `Vue enregistrée il y a ${storedAge} min · données non actualisées.`;
    };
    const request = async (retry = true) => {
      const response = await requestWithTimeout("/api/v1/history?hours=24", {headers: {Accept: "application/json"}, cache: "no-store"}, 12000);
      if (response.status === 429 && retry) { const seconds = Math.max(1, Number(response.headers.get("Retry-After")) || 2); await new Promise((resolve) => window.setTimeout(resolve, seconds * 1000)); return request(false); }
      if (!response.ok) throw new Error(`HTTP ${response.status}`); return response.json();
    };
    // Garde d'appel en vol : le minuteur de cinq minutes, l'observateur d'intersection et le
    // bouton « Réessayer » peuvent se déclencher ensemble. Une seule requête à la fois.
    let inFlight = false;
    const load = async () => {
      if (inFlight) return;
      if (!visible && loaded) return; inFlight = true; preview.setAttribute("aria-busy", "true");
      try { const data = await request(); await window.PhytoPwa?.markServerContact(Date.now(), "history"); await window.PhytoPwa?.storeSnapshot("history:24", data, Date.now()); render(data); loaded = true; }
      catch (error) { if (window.PhytoPwa?.isTransportError?.(error) || error instanceof TypeError) window.PhytoPwa?.signalerEchecTransport(); else window.PhytoPwa?.markServerDegraded(`Historique momentanément indisponible (${error.message}).`, "history"); const stored = await window.PhytoPwa?.loadSnapshot("history:24") || await window.PhytoPwa?.loadSnapshot("history"); if (stored?.data) render(stored.data, Math.max(0, Math.round((Date.now() - stored.receivedAt) / 60000))); else { showData(false); message.textContent = `Historique local indisponible (${error.message}).`; } }
      finally { inFlight = false; preview.setAttribute("aria-busy", "false"); }
    };
    const observer = new IntersectionObserver((entries) => { visible = entries.some((entry) => entry.isIntersecting); if (visible && !loaded) load(); clearInterval(refreshTimer); if (visible) refreshTimer = window.setInterval(() => { if (!document.hidden) load(); }, 300000); }, {rootMargin: "300px"});
    const setAvailability = (available) => {
      preview.dataset.historyAvailable = String(available);
      if (available) {
        if (!observed) { observer.observe(preview); observed = true; }
        if (visible && !loaded) load();
      } else if (!loaded) {
        showData(false); message.textContent = "Historique local indisponible. Le contrôle reste actif.";
      }
    };
    preview.querySelector("[data-history-preview-retry]")?.addEventListener("click", () => { visible = true; load(); });
    document.addEventListener("phyto:history-availability", (event) => setAvailability(event.detail.available));
    const temperatureKey = () => (currentPreview?.series.find((item) => item.control_role === "climate_temperature")
      || currentPreview?.series.find((item) => item.unit?.includes("°C")))?.key;
    const redraw = () => { const key = temperatureKey(); if (currentPreview && key) draw(currentPreview, key); };
    document.addEventListener("phyto:themechange", redraw);
    setAvailability(preview.dataset.historyAvailable === "true");
    // Un redimensionnement ne remesure qu'un canvas : il ne redemande **rien** au serveur.
    // L'ancienne version rappelait `load()`, donc une requête complète de 24 h d'historique à
    // chaque événement `resize` — et le clavier virtuel d'un téléphone, une rotation ou un
    // simple redimensionnement de fenêtre en émettent des dizaines par seconde. Sans anti-rebond
    // ni garde d'appel en vol, cela empilait autant de requêtes concurrentes sur le contrôleur,
    // qui régule la serre en même temps. Anti-rebond de 150 ms, aligné sur la page complète,
    // et redessin seul à partir des données déjà en mémoire.
    let previewResizeTimer;
    window.addEventListener("resize", () => {
      clearTimeout(previewResizeTimer);
      previewResizeTimer = window.setTimeout(redraw, 150);
    });
  };
  if (preview) initPreview();
  if (!section) return;
  const message = document.getElementById("history-message");
  const tooltip = document.getElementById("history-tooltip");
  const viewPicker = document.querySelector("[data-history-view-picker]");
  const selectionOutput = document.getElementById("history-selection-output");
  const selectionDetail = selectionOutput?.querySelector(".ui-chart-detail");
  const content = section.querySelector(".history-content");
  const emptyState = document.getElementById("history-empty-state");
  const rangeControls = section.querySelector(".history-range");
  const colors = () => [0, 1, 2, 3, 4, 5].map((index) => themeColor(`--chart-${index}`, ["#50e38a", "#65b9ff", "#ffc857", "#d88cff", "#ff7b7b", "#8ee3ef"][index]));
  const showHistoryData = (shown) => { if (content) content.hidden = !shown; if (emptyState) emptyState.hidden = shown; if (rangeControls) rangeControls.hidden = !shown; if (message) message.hidden = !shown; };
  const seriesDashes = [[], [8, 3], [2, 3], [10, 3, 2, 3], [5, 3], [12, 4]];
  // Deux séries superposées doivent rester séparables sans la couleur : au tracé (`seriesDashes`)
  // s'ajoute une forme de marqueur, seule distinction qui survive à un tracé plein contre un autre
  // tracé plein en niveaux de gris. Même ordre que les motifs et que les teintes `--chart-N`.
  const seriesMarkers = ["circle", "square", "triangle", "diamond", "cross", "hexagon"];
  const markerLabels = {circle: "disque", square: "carré", triangle: "triangle", diamond: "losange", cross: "croix", hexagon: "hexagone"};
  const MARKER_RADIUS = 3.4;
  // Un marqueur par tranche de 78 px : assez pour suivre une série, assez rare pour ne pas
  // masquer la courbe. Le décalage par série évite que deux marqueurs se recouvrent exactement.
  const MARKER_SPACING_PX = 78;
  // Déplacement maximal entre l'appui et le relâchement, en pixels CSS : au-delà, le doigt a
  // défilé (`touch-action: pan-y` laisse passer le geste) et rien n'est sélectionné.
  //
  // Ce n'est **pas** le `TAP_RADIUS_PX` de 44 px de `culture_analysis.js`, et la ressemblance des
  // deux noms a de quoi tromper : là-bas le seuil est un rayon d'acceptation autour d'un point
  // discret, un tap trop loin de toute donnée ne visant rien. Ici la courbe est continue — toute
  // abscisse du cadre désigne un seau —, il n'y a donc aucun point à manquer et un rayon
  // d'acceptation n'aurait pas de sens. Ce qui est réellement aligné, c'est la règle commune :
  // un geste qui se déplace n'est pas une sélection.
  const TAP_MAX_DISTANCE_PX = 12;
  const groups = {automation: ["daily_1", "daily_2", "cyclic_1", "cyclic_2"], "climate-actuator": ["heater", "motor"]};
  const fallbackNames = {daily_1: "Éclairage 1", daily_2: "Éclairage 2", cyclic_1: "Sortie cyclique 1", cyclic_2: "Sortie cyclique 2", heater: "Chauffage", motor: "Ventilation"};
  const plots = new Map();
  const hiddenSeries = new Set();
  const hiddenActuators = new Set();
  let current = null;
  // Deux états distincts, et c'est volontaire.
  // `selectedTimestamp` est la sélection **confirmée** (tap, clic, clavier) : elle seule
  // alimente la fiche de la région vivante et survit au redimensionnement.
  // `hoverTimestamp` n'est que le curseur du survol : il déplace le trait et l'infobulle et
  // disparaît quand le pointeur quitte le graphique. Les confondre revenait à laisser un simple
  // survol **armer** une annonce que le redessin suivant (redimensionnement, changement
  // d'indicateur, rechargement périodique) finissait par déclencher.
  let selectedTimestamp = null;
  let hoverTimestamp = null;
  let pointerPosition = null;
  let redrawFrame = null;

  const equipmentName = (id) => current?.equipment?.[id]?.display_name || fallbackNames[id] || id;
  // Convention unique de présentation d'un nombre, commune au filtre Jinja `nombre`
  // (`pages.py`) et à `PhytoCultureAnalysis.formatNombre` (`culture_analysis.js`) — **même nom**
  // que cette dernière : une seule convention ne doit pas s'appeler de deux façons selon la page.
  // virgule française, **aucun séparateur de milliers** (`useGrouping:false`, sans quoi la
  // même mesure s'écrirait « 1 234,5 » ici et « 1234,5 » dans le carnet), décimales bornées
  // à [0 ; 6], et « — » pour toute absence — jamais un zéro. L'arrondi reste en présentation.
  const formatNombre = (value, decimals = 1) => {
    if (value === null || value === undefined || !Number.isFinite(Number(value))) return "—";
    const places = Math.max(0, Math.min(6, Number(decimals)));
    return Number(value).toLocaleString("fr-FR", {useGrouping: false, minimumFractionDigits: places, maximumFractionDigits: places});
  };
  const formatDate = (timestamp, detailed = false) => new Date(timestamp * 1000).toLocaleString("fr-FR", {timeZone: "Europe/Paris", day: "2-digit", month: detailed ? "2-digit" : undefined, hour: "2-digit", minute: "2-digit"});
  const formatDuration = (seconds) => {
    if (!Number.isFinite(seconds)) return "—";
    const minutes = Math.max(0, Math.round(seconds / 60));
    const hours = Math.floor(minutes / 60); const remainder = minutes % 60;
    return hours ? `${hours} h ${String(remainder).padStart(2, "0")} min` : `${remainder} min`;
  };
  const countLabel = (count, singular, plural) => `${count} ${count === 1 ? singular : plural}`;
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
    ctx.fillStyle = themeColor("--chart-muted", "#a0b9aa"); ctx.font = AXIS_FONT;
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
    ctx.clearRect(0, 0, width, height); ctx.font = AXIS_FONT; ctx.lineWidth = 1;
    for (let index = 0; index <= 4; index += 1) {
      const yy = box.top + index / 4 * (box.bottom - box.top);
      ctx.strokeStyle = themeColor("--chart-grid", "rgba(176,205,186,.16)"); ctx.beginPath(); ctx.moveTo(box.left, yy); ctx.lineTo(box.right, yy); ctx.stroke();
      const value = maximum - index / 4 * range;
      ctx.fillStyle = themeColor("--chart-muted", "#a0b9aa"); ctx.fillText(`${value.toFixed(range < 10 ? 1 : 0)}${unit}`, 2, yy + 4);
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
    const alarm = event.kind === "alarm"; const note = event.kind === "operator_note";
    const color = alarm ? themeColor("--red", "#ff6b6b") : note ? themeColor("--blue", "#75baff") : themeColor("--amber", "#ffc857");
    graph.ctx.strokeStyle = color;
    graph.ctx.fillStyle = color; graph.ctx.lineWidth = 1;
    graph.ctx.beginPath(); graph.ctx.moveTo(xx, graph.box.top); graph.ctx.lineTo(xx, graph.box.bottom); graph.ctx.stroke();
    graph.ctx.beginPath();
    if (alarm) { graph.ctx.moveTo(xx, graph.box.top); graph.ctx.lineTo(xx - 4, graph.box.top + 7); graph.ctx.lineTo(xx + 4, graph.box.top + 7); }
    else if (note) { graph.ctx.arc(xx, graph.box.top + 4, 4, 0, Math.PI * 2); }
    else { graph.ctx.moveTo(xx, graph.box.top); graph.ctx.lineTo(xx - 4, graph.box.top + 4); graph.ctx.lineTo(xx, graph.box.top + 8); graph.ctx.lineTo(xx + 4, graph.box.top + 4); }
    graph.ctx.closePath(); graph.ctx.fill();
  });
  const drawCrosshair = (graph) => {
    // Le survol prime à l'affichage — le trait suit le doigt ou la souris — mais il n'est
    // jamais retenu comme sélection.
    const cursor = Number.isFinite(hoverTimestamp) ? hoverTimestamp : selectedTimestamp;
    if (!Number.isFinite(cursor)) return;
    const xx = graph.x(cursor); if (xx < graph.box.left || xx > graph.box.right) return;
    graph.ctx.strokeStyle = themeColor("--chart-crosshair", "rgba(237,247,240,.72)"); graph.ctx.lineWidth = 1; graph.ctx.setLineDash([2, 3]);
    graph.ctx.beginPath(); graph.ctx.moveTo(xx, graph.box.top); graph.ctx.lineTo(xx, graph.box.bottom); graph.ctx.stroke(); graph.ctx.setLineDash([]);
  };
  // Marqueur ponctuel dessiné dans le repère courant. Aucune donnée n'est inventée :
  // le marqueur se pose sur un point réellement mesuré, jamais sur une lacune interpolée.
  const drawMarker = (ctx, shape, cx, cy, radius = MARKER_RADIUS) => {
    ctx.beginPath();
    if (shape === "square") ctx.rect(cx - radius, cy - radius, radius * 2, radius * 2);
    else if (shape === "triangle") { ctx.moveTo(cx, cy - radius * 1.15); ctx.lineTo(cx + radius, cy + radius * .85); ctx.lineTo(cx - radius, cy + radius * .85); ctx.closePath(); }
    else if (shape === "diamond") { ctx.moveTo(cx, cy - radius * 1.2); ctx.lineTo(cx + radius * 1.2, cy); ctx.lineTo(cx, cy + radius * 1.2); ctx.lineTo(cx - radius * 1.2, cy); ctx.closePath(); }
    else if (shape === "cross") { ctx.moveTo(cx - radius, cy - radius); ctx.lineTo(cx + radius, cy + radius); ctx.moveTo(cx + radius, cy - radius); ctx.lineTo(cx - radius, cy + radius); ctx.stroke(); return; }
    else if (shape === "hexagon") { for (let corner = 0; corner < 6; corner += 1) { const angle = Math.PI / 3 * corner - Math.PI / 2; ctx[corner ? "lineTo" : "moveTo"](cx + radius * Math.cos(angle), cy + radius * Math.sin(angle)); } ctx.closePath(); }
    else ctx.arc(cx, cy, radius, 0, Math.PI * 2);
    ctx.fill(); ctx.stroke();
  };
  const drawSeriesMarkers = (graph, points, index, color) => {
    const shape = seriesMarkers[index % seriesMarkers.length];
    const span = Math.max(1, graph.box.right - graph.box.left);
    const step = Math.max(1, Math.round(points.length / Math.max(1, Math.floor(span / MARKER_SPACING_PX))));
    const offset = index % step;
    graph.ctx.setLineDash([]); graph.ctx.lineWidth = 1.6; graph.ctx.strokeStyle = color; graph.ctx.fillStyle = color;
    points.forEach((point, pointIndex) => {
      if ((pointIndex - offset) % step !== 0 || !Number.isFinite(point.avg)) return;
      drawMarker(graph.ctx, shape, graph.x(point.ts), graph.y(point.avg));
    });
  };

  const sensorSummary = (series, unit) => {
    const values = series.flatMap((meta) => valuesFor(meta.key));
    if (!values.length) return "Aucune mesure valide sur cette période.";
    const averages = current.buckets.flatMap((bucket) => series.map((meta) => bucket.sensors[meta.key]?.avg).filter(Number.isFinite));
    return `Min ${formatNombre(Math.min(...values))} ${unit} · moyenne ${formatNombre(averages.reduce((sum, value) => sum + value, 0) / averages.length)} ${unit} · max ${formatNombre(Math.max(...values))} ${unit}.`;
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
      empty.context.fillStyle = themeColor("--chart-muted", "#a0b9aa"); empty.context.font = AXIS_FONT;
      empty.context.fillText(visible.length ? "Aucune mesure valide sur cette période" : "Toutes les séries sont masquées", 16, 35);
      plots.delete(canvas); return;
    }
    const padding = Math.max(unit === "°C" ? 1 : .5, (Math.max(...values) - Math.min(...values)) * .1);
    const graph = sensorFrame(canvas, Math.min(...values) - padding, Math.max(...values) + padding, unit);
    if (options.temperature) {
      setpointSegments(["temp_min", "temp_max"]).forEach((points) => {
        graph.ctx.fillStyle = `${themeColor("--chart-1", "#65b9ff")}1a`; graph.ctx.beginPath();
        points.forEach((bucket, index) => graph.ctx[index ? "lineTo" : "moveTo"](graph.x(bucket.bucket_start_ts), graph.y(bucket.setpoints.temp_max)));
        [...points].reverse().forEach((bucket) => graph.ctx.lineTo(graph.x(bucket.bucket_start_ts), graph.y(bucket.setpoints.temp_min)));
        graph.ctx.closePath(); graph.ctx.fill();
      });
      drawSetpointLine(graph, "heater_off_threshold", themeColor("--chart-2", "#ffc857"), [4, 4]);
      drawSetpointLine(graph, "vent_threshold", themeColor("--chart-3", "#d88cff"), [9, 4]);
    }
    if (options.humidity) drawSetpointLine(graph, "humidity_threshold", themeColor("--chart-2", "#ffc857"), [5, 4]);
    visible.forEach((meta) => {
      const index = Math.max(0, series.findIndex((item) => item.key === meta.key));
      sensorSegments(meta.key).forEach((points) => {
        graph.ctx.fillStyle = `${colors()[index % colors().length]}24`; graph.ctx.beginPath();
        points.forEach((point, pointIndex) => graph.ctx[pointIndex ? "lineTo" : "moveTo"](graph.x(point.ts), graph.y(point.max)));
        [...points].reverse().forEach((point) => graph.ctx.lineTo(graph.x(point.ts), graph.y(point.min)));
        graph.ctx.closePath(); graph.ctx.fill();
        graph.ctx.strokeStyle = colors()[index % colors().length]; graph.ctx.lineWidth = 2; graph.ctx.setLineDash(seriesDashes[index % seriesDashes.length]); graph.ctx.beginPath();
        points.forEach((point, pointIndex) => graph.ctx[pointIndex ? "lineTo" : "moveTo"](graph.x(point.ts), graph.y(point.avg)));
        graph.ctx.stroke(); graph.ctx.setLineDash([]);
        drawSeriesMarkers(graph, points, index, colors()[index % colors().length]);
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
  // La boîte des libellés de piste est **mesurée**, pas devinée : les axes sont passés à 13 px
  // (plancher de la fiche R2.2) alors que la largeur réservée, elle, était restée calée sur
  // l'ancienne police de 11 px — à 320 px, « Sortie cyclique 1 » débordait des 112 px hérités.
  // On demande donc au contexte la largeur réelle des noms affichés, bornée à 45 % de la
  // largeur du graphique pour qu'un nom long ne dévore pas la chronologie ; au-delà de cette
  // borne, `fitText` tronque avec une ellipse. Aucune réduction sous 13 px : la lisibilité de
  // l'axe est le critère, la largeur de la boîte est la variable d'ajustement.
  const timelineFrame = (canvas, laneCount, names = []) => {
    const {context: ctx, width, height} = setup(canvas);
    ctx.font = AXIS_FONT;
    const needed = names.length ? Math.max(...names.map((name) => ctx.measureText(name).width)) + 14 : 0;
    const box = {left: Math.min(Math.max(96, needed), Math.max(104, width * .45)), right: width - 8, top: 12, bottom: height - 29};
    const start = current.range_start_ts; const end = current.range_end_ts;
    const x = (timestamp) => box.left + (timestamp - start) / Math.max(1, end - start) * (box.right - box.left);
    ctx.clearRect(0, 0, width, height); ctx.strokeStyle = themeColor("--chart-grid", "rgba(176,205,186,.16)"); ctx.lineWidth = 1;
    const laneHeight = (box.bottom - box.top) / Math.max(1, laneCount);
    for (let index = 0; index <= laneCount; index += 1) { const yy = box.top + index * laneHeight; ctx.beginPath(); ctx.moveTo(box.left, yy); ctx.lineTo(box.right, yy); ctx.stroke(); }
    timeAxis(ctx, box, height, start, end, x);
    const graph = {ctx, x, box, width, height, start, end, laneHeight}; plots.set(canvas, graph); return graph;
  };
  const drawTimeline = (canvas, ids) => {
    if (!canvas) return;
    const present = ids.filter((id) => current.actuator_history?.[id]?.intervals?.length || current.buckets.some((bucket) => id in bucket.actuators));
    const lanes = present.length ? present : ids;
    const graph = timelineFrame(canvas, lanes.length, lanes.map(equipmentName)); graph.ctx.font = AXIS_FONT;
    if (!lanes.length) {
      graph.ctx.fillStyle = themeColor("--chart-muted", "#a0b9aa"); graph.ctx.font = AXIS_FONT;
      graph.ctx.fillText("Toutes les pistes sont masquées", graph.box.left + 10, graph.box.top + 28);
      drawEvents(graph); drawCrosshair(graph); return;
    }
    lanes.forEach((id, index) => {
      const top = graph.box.top + index * graph.laneHeight + 4; const laneHeight = Math.max(5, graph.laneHeight - 8);
      graph.ctx.fillStyle = `${themeColor("--chart-muted", "#a0b9aa")}0f`; graph.ctx.fillRect(graph.box.left, top, graph.box.right - graph.box.left, laneHeight);
      hatch(graph.ctx, graph.box.left, top, graph.box.right - graph.box.left, laneHeight, `${themeColor("--chart-muted", "#a0b9aa")}33`);
      graph.ctx.fillStyle = themeColor("--chart-label", "#dbe9df"); graph.ctx.fillText(fitText(graph.ctx, equipmentName(id), graph.box.left - 12), 2, top + laneHeight / 2 + 4);
      const exactIntervals = current.actuator_history?.[id]?.intervals || [];
      if (exactIntervals.length) {
        exactIntervals.forEach((interval) => {
          const left = Math.max(graph.box.left, graph.x(interval.start_ts));
          const right = Math.min(graph.box.right, graph.x(interval.end_ts)); const width = Math.max(1, right - left);
          if (right <= graph.box.left || left >= graph.box.right) return;
          if (interval.status !== "ok" || !Number.isFinite(interval.actual)) {
            hatch(graph.ctx, left, top, width, laneHeight, "rgba(255,107,107,.48)"); return;
          }
          graph.ctx.fillStyle = themeColor("--chart-off", "#0d1812"); graph.ctx.fillRect(left, top, width, laneHeight);
          if (id === "motor") {
            const speed = Math.max(0, Math.min(4, Math.round(interval.actual))); const speedColors = [themeColor("--chart-off", "#0d1812"), "#245c42", "#2f8b5a", "#3fbd73", themeColor("--chart-0", "#50e38a")];
            graph.ctx.fillStyle = speedColors[speed]; graph.ctx.fillRect(left, top, width, laneHeight);
            if (width > 18 && speed > 0) { graph.ctx.fillStyle = speed >= 3 ? "#062b15" : "#edf7f0"; graph.ctx.fillText(`V${speed}`, left + 3, top + laneHeight / 2 + 4); }
          } else if (interval.actual > 0) { graph.ctx.fillStyle = themeColor("--chart-0", "#50e38a"); graph.ctx.fillRect(left, top, width, laneHeight); }
          if (interval.boundary_precision === "observed") hatch(graph.ctx, left, top, Math.min(width, 7), laneHeight, "rgba(245,189,79,.78)");
        });
        return;
      }
      current.buckets.forEach((bucket) => {
        const item = bucket.actuators[id]; const left = Math.max(graph.box.left, graph.x(bucket.bucket_start_ts));
        const right = Math.min(graph.box.right, graph.x(bucket.bucket_start_ts + current.bucket_seconds)); const width = Math.max(1, right - left + .5);
        if (!item || !item.valid_count || !Number.isFinite(item.avg_value)) { hatch(graph.ctx, left, top, width, laneHeight, "rgba(160,185,170,.32)"); return; }
        graph.ctx.fillStyle = themeColor("--chart-off", "#0d1812"); graph.ctx.fillRect(left, top, width, laneHeight);
        if (id === "motor") {
          const speed = Math.max(0, Math.min(4, item.avg_value)); const speedColors = [themeColor("--chart-off", "#0d1812"), "#245c42", "#2f8b5a", "#3fbd73", themeColor("--chart-0", "#50e38a")];
          graph.ctx.fillStyle = speedColors[Math.round(speed)]; graph.ctx.fillRect(left, top, width, laneHeight);
          if (item.min_value !== item.max_value) hatch(graph.ctx, left, top, width, laneHeight, "rgba(255,255,255,.42)");
          if (width > 18 && speed > 0) { graph.ctx.fillStyle = speed >= 3 ? "#062b15" : "#edf7f0"; graph.ctx.fillText(`V${Math.round(speed)}`, left + 3, top + laneHeight / 2 + 4); }
          return;
        }
        if (item.on_rate === 1) { graph.ctx.fillStyle = themeColor("--chart-0", "#50e38a"); graph.ctx.fillRect(left, top, width, laneHeight); }
        else if (item.on_rate > 0) { graph.ctx.fillStyle = "rgba(245,189,79,.20)"; graph.ctx.fillRect(left, top, width, laneHeight); hatch(graph.ctx, left, top, width, laneHeight, "rgba(245,189,79,.72)"); }
      });
    });
    drawEvents(graph); drawCrosshair(graph);
  };

  const swatch = (kind, colorClass = "") => element("span", `chart-legend-swatch ${kind} ${colorClass}`);
  const legendItem = (label, kind, colorClass = "") => { const item = element("span", "chart-legend-item"); item.append(swatch(kind, colorClass), document.createTextNode(label)); return item; };
  // Pastille dessinée, et non stylée en CSS : elle rejoue **le** motif (`setLineDash`) et **la**
  // forme de marqueur employés par le tracé. Les classes `series-style-0..2` ne décrivaient que
  // trois variantes pour six motifs : dès la quatrième courbe, la légende montrait le trait d'une
  // autre série.
  const seriesSwatch = (index) => {
    const canvas = document.createElement("canvas");
    canvas.className = "chart-legend-swatch is-plot";
    // Décor : la forme est nommée dans le libellé accessible du bouton, pas relue ici.
    canvas.setAttribute("aria-hidden", "true");
    const ratio = window.devicePixelRatio || 1; const width = 30; const height = 14;
    canvas.width = Math.round(width * ratio); canvas.height = Math.round(height * ratio);
    canvas.style.width = `${width}px`; canvas.style.height = `${height}px`;
    const ctx = canvas.getContext("2d"); ctx.setTransform(ratio, 0, 0, ratio, 0, 0);
    const color = colors()[index % colors().length]; const middle = height / 2;
    ctx.strokeStyle = color; ctx.fillStyle = color; ctx.lineWidth = 2;
    ctx.setLineDash(seriesDashes[index % seriesDashes.length]);
    ctx.beginPath(); ctx.moveTo(0, middle); ctx.lineTo(width, middle); ctx.stroke(); ctx.setLineDash([]);
    drawMarker(ctx, seriesMarkers[index % seriesMarkers.length], width / 2, middle, 3.6);
    return canvas;
  };
  // Légende courte : nom de la série et unité, rien d'autre. Le reste (sources, période,
  // consignes) part dans le « Légende complète » déplié à la demande.
  const legendButton = (meta, index) => {
    const button = element("button", "chart-legend-button"); button.type = "button"; button.dataset.seriesKey = meta.key;
    const shape = markerLabels[seriesMarkers[index % seriesMarkers.length]];
    const visible = meta.unit ? `${meta.label} · ${meta.unit}` : meta.label;
    button.append(seriesSwatch(index), document.createTextNode(visible));
    // Le libellé accessible **commence par** le texte visible (WCAG 2.5.3) et n'y ajoute que la
    // forme du marqueur, seule information que la pastille dessinée porte sans mot.
    button.setAttribute("aria-label", `${visible} · marqueur ${shape}`);
    button.setAttribute("aria-pressed", String(!hiddenSeries.has(meta.key))); return button;
  };
  const legendNote = (text) => element("p", "chart-legend-note", text);
  const periodNote = () => (current
    ? legendNote(`Période affichée : du ${formatDate(current.range_start_ts, true)} au ${formatDate(current.range_end_ts, true)} · ${countLabel(current.buckets.length, "intervalle", "intervalles")} de ${Math.round(current.bucket_seconds / 60)} min.`)
    : legendNote("Période inconnue."));
  const sourceNotes = (series) => series.map((meta, index) => legendNote(`Source « ${meta.label} » : capteur ${meta.key}${meta.unit ? `, en ${meta.unit}` : ""} · tracé et marqueur ${markerLabels[seriesMarkers[index % seriesMarkers.length]]}.`));
  const fillLegend = (id, short, full) => {
    document.getElementById(id)?.replaceChildren(...short);
    document.getElementById(`${id}-full`)?.replaceChildren(...full);
  };
  const buildLegends = (temperature, humidity) => {
    fillLegend("temperature-legend", temperature.map(legendButton), [
      periodNote(), ...sourceNotes(temperature),
      legendItem("plage min–max", "is-band", "series-color-0"), legendItem("zone cible", "is-band", "series-color-1"),
      legendItem("consigne d’arrêt du chauffage", "is-dashed", "series-color-2"), legendItem("consigne de départ de ventilation", "is-long-dash", "series-color-3"),
      legendItem("alarme", "is-event-alarm"), legendItem("configuration", "is-event-config"), legendItem("note opérateur", "is-event-note"),
    ]);
    fillLegend("humidity-legend", humidity.map(legendButton), [
      periodNote(), ...sourceNotes(humidity),
      legendItem("plage min–max", "is-band", "series-color-0"), legendItem("consigne de seuil d’humidité", "is-dashed", "series-color-2"),
      legendItem("alarme", "is-event-alarm"), legendItem("configuration", "is-event-config"), legendItem("note opérateur", "is-event-note"),
    ]);
    fillLegend("automation-legend", [legendItem("en marche", "", "series-color-0"), legendItem("arrêté", "is-off")], [
      periodNote(), legendNote("Source : état GPIO relu à chaque transition ; à défaut, observation minute agrégée."),
      legendItem("ON GPIO relu", "", "series-color-0"), legendItem("OFF GPIO relu", "is-off"),
      legendItem("bascule détectée à la minute", "is-mixed"), legendItem("non couvert", "is-unknown"),
      legendItem("alarme", "is-event-alarm"), legendItem("configuration", "is-event-config"),
    ]);
    fillLegend("climate-actuator-legend", [legendItem("chauffage en marche", "", "series-color-0"), legendItem("arrêté", "is-off"), legendItem("ventilation V1 → V4", "is-band", "series-color-0")], [
      periodNote(), legendNote("Source : état GPIO relu à chaque transition ; à défaut, observation minute agrégée. Les consignes climatiques se lisent sur le graphique des températures."),
      legendItem("chauffage ON relu", "", "series-color-0"), legendItem("arrêt relu", "is-off"), legendItem("ventilation V1 → V4", "is-band", "series-color-0"),
      legendItem("bascule détectée à la minute", "is-mixed"), legendItem("non couvert", "is-unknown"),
      legendItem("alarme", "is-event-alarm"), legendItem("configuration", "is-event-config"),
    ]);
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
        : stats.exact && id === "motor" ? `${stats.approximate ? "≈ " : ""}${formatDuration(stats.activeDuration)} en marche · max V${formatNombre(stats.maximum, 0)} · couverture ${formatNombre(stats.coverage, 0)} %`
          : stats.exact ? `${stats.approximate ? "≈ " : ""}${formatDuration(stats.activeDuration)} ON · ${countLabel(stats.transitions, "bascule", "bascules")} · couverture ${formatNombre(stats.coverage, 0)} %`
            : id === "motor" ? `Moy. V${formatNombre(stats.average)} · max V${formatNombre(stats.maximum, 0)} · active ${formatNombre(stats.active, 0)} %`
              : `${formatNombre(stats.active, 0)} % ON · ${countLabel(stats.transitions, "bascule", "bascules")} · ${stats.currentState}`;
      item.append(element("strong", "", equipmentName(id)), element("span", "", detail)); return item;
    }));
  };

  // Les graphiques créés à la volée entrent dans le sélecteur d'indicateur : sans cela ils
  // restaient visibles en permanence sur téléphone, où l'on ne montre qu'un tracé à la fois.
  // La valeur choisie est conservée quand elle survit à la reconstruction.
  const syncPicker = (options) => {
    if (!viewPicker) return;
    const wanted = viewPicker.value;
    viewPicker.querySelectorAll("option[data-history-dynamic]").forEach((option) => option.remove());
    const last = viewPicker.querySelector('option[value="all"]');
    options.forEach(({value, label}) => {
      const option = element("option", "", label); option.value = value; option.dataset.historyDynamic = "true";
      viewPicker.insertBefore(option, last);
    });
    if ([...viewPicker.options].some((option) => option.value === wanted)) viewPicker.value = wanted;
  };
  const buildAdditionalCharts = (units) => {
    const additional = document.getElementById("additional-charts"); additional.replaceChildren();
    units.forEach((unit, index) => {
      const id = `additional-${index}`; const card = element("article", "card chart-card"); const title = element("h3", "", `Mesures · ${unit}`);
      const legend = element("div", "chart-legend"); legend.id = `${id}-legend`; legend.setAttribute("role", "group"); legend.setAttribute("aria-label", `Légende des mesures en ${unit}`);
      const details = element("details", "chart-full-legend"); details.append(element("summary", "", "Légende complète"));
      const full = element("div", "chart-legend chart-legend-full"); full.id = `${id}-legend-full`; details.append(full);
      const summary = element("p", "chart-summary", ""); summary.id = `${id}-summary`;
      const canvas = document.createElement("canvas"); canvas.dataset.chartHeight = "260"; canvas.dataset.historyChart = id; canvas.dataset.historyUnit = unit; canvas.height = 260; canvas.tabIndex = 0;
      canvas.setAttribute("role", "img"); canvas.setAttribute("aria-label", `Tendances des mesures en ${unit}. Utilisez les flèches gauche et droite pour explorer les valeurs.`); canvas.setAttribute("aria-describedby", summary.id);
      const series = current.series.filter((item) => item.unit === unit);
      card.append(title, legend, details, summary, canvas); additional.append(card);
      fillLegend(legend.id, series.map(legendButton), [
        periodNote(), ...sourceNotes(series),
        legendItem("plage min–max", "is-band", "series-color-0"),
        legendItem("alarme", "is-event-alarm"), legendItem("configuration", "is-event-config"),
      ]);
      summary.textContent = sensorSummary(series, unit);
    });
    syncPicker(units.map((unit, index) => ({value: `additional-${index}`, label: `Mesures · ${unit}`})));
  };
  const buildTable = () => {
    const rows = [];
    current.series.forEach((meta) => {
      const values = valuesFor(meta.key); const averages = current.buckets.map((bucket) => bucket.sensors[meta.key]?.avg).filter(Number.isFinite); if (!values.length) return;
      rows.push([meta.label, "Capteur", `${formatNombre(Math.min(...values), meta.decimals)} ${meta.unit}`, `${formatNombre(averages.reduce((sum, value) => sum + value, 0) / averages.length, meta.decimals)} ${meta.unit}`, `${formatNombre(Math.max(...values), meta.decimals)} ${meta.unit}`, "—"]);
    });
    Object.values(groups).flat().forEach((id) => {
      const stats = actuatorStats(id); if (!stats) return;
      rows.push(id === "motor" ? [equipmentName(id), "Actionneur", `V${formatNombre(stats.minimum, 0)}`, `V${formatNombre(stats.average)}`, `V${formatNombre(stats.maximum, 0)}`, stats.exact ? `${stats.approximate ? "≈ " : ""}${formatDuration(stats.activeDuration)} · couverture ${formatNombre(stats.coverage, 0)} %` : `${formatNombre(stats.active, 0)} %`] : [equipmentName(id), "Actionneur", "ARRÊTÉ", "—", "EN MARCHE", stats.exact ? `${stats.approximate ? "≈ " : ""}${formatDuration(stats.activeDuration)} en marche · ${countLabel(stats.transitions, "bascule", "bascules")} · couverture ${formatNombre(stats.coverage, 0)} %` : `${formatNombre(stats.active, 0)} % en marche · ${countLabel(stats.transitions, "bascule", "bascules")}`]);
    });
    document.getElementById("history-data-body").replaceChildren(...rows.map((values) => {
      const row = document.createElement("tr"); values.forEach((value, index) => { const cell = document.createElement(index ? "td" : "th"); if (!index) cell.scope = "row"; cell.textContent = value; row.append(cell); }); return row;
    }));
  };
  const insight = (label, value, detail, status = "normal") => {
    const item = element("article", `history-insight status-${status}`);
    item.append(element("span", "", label), element("strong", "num", value), element("small", "", detail));
    return item;
  };

  // Indicateurs résumés de la fenêtre affichée, calculés à partir des seaux déjà envoyés par
  // `/api/v1/history` : aucune requête, aucun champ nouveau côté serveur.
  //
  // La moyenne est **pondérée** par `valid_count` — `SUM(avg × valid_count) / SUM(valid_count)` —
  // et jamais une moyenne des moyennes horaires : les seaux ne portent pas tous le même nombre
  // d'échantillons valides, et un seau à un seul relevé pèserait autant qu'un seau plein.
  // Une absence reste une absence : un seau sans `valid_count` est ignoré, il ne vaut pas zéro,
  // et sans aucun échantillon valide l'indicateur affiche « — ».
  const seriesStats = (meta) => {
    if (!meta) return null;
    let minimum = Infinity; let maximum = -Infinity; let total = 0; let count = 0;
    current.buckets.forEach((bucket) => {
      const item = bucket.sensors[meta.key];
      if (!item?.valid_count) return;
      if (Number.isFinite(item.min)) minimum = Math.min(minimum, item.min);
      if (Number.isFinite(item.max)) maximum = Math.max(maximum, item.max);
      if (!Number.isFinite(item.avg)) return;
      total += item.avg * item.valid_count; count += item.valid_count;
    });
    if (!count) return null;
    return {minimum: Number.isFinite(minimum) ? minimum : null, maximum: Number.isFinite(maximum) ? maximum : null, average: total / count, samples: count};
  };
  // Part de lacunes : seaux attendus sur la fenêtre (durée / pas) contre seaux réellement
  // porteurs d'au moins une mesure valide. Une lacune est une absence de mesure, pas une valeur.
  const gapShare = () => {
    const span = current.range_end_ts - current.range_start_ts;
    const expected = Math.round(span / Math.max(1, current.bucket_seconds));
    if (!Number.isFinite(expected) || expected <= 0) return null;
    const observed = current.buckets.filter((bucket) => Object.values(bucket.sensors || {}).some((item) => item?.valid_count)).length;
    return {expected, observed, ratio: Math.max(0, Math.min(1, 1 - observed / expected))};
  };
  const measureInsight = (label, meta, stats) => {
    if (!meta) return insight(label, "—", "Aucune série de cette grandeur sur la période.");
    if (!stats) return insight(label, "—", `${meta.label} : aucune mesure valide sur la période.`, "warning");
    const unit = meta.unit || "";
    return insight(
      `${label} (min / moy. / max)`,
      `${formatNombre(stats.minimum, meta.decimals)} / ${formatNombre(stats.average, meta.decimals)} / ${formatNombre(stats.maximum, meta.decimals)} ${unit}`.trim(),
      `${meta.label} · moyenne pondérée sur ${countLabel(stats.samples, "mesure valide", "mesures valides")}.`,
    );
  };
  const buildMetrics = () => {
    const root = document.getElementById("history-metrics-grid"); if (!root) return;
    const temperature = current.series.find((item) => item.control_role === "climate_temperature") || current.series.find((item) => item.unit?.includes("°C"));
    const humidity = current.series.find((item) => item.control_role === "climate_humidity") || current.series.find((item) => item.unit?.includes("%"));
    const gaps = gapShare();
    root.replaceChildren(
      measureInsight("Température", temperature, temperature ? seriesStats(temperature) : null),
      measureInsight("Humidité", humidity, humidity ? seriesStats(humidity) : null),
      insight(
        "Part de lacunes",
        gaps ? `${formatNombre(gaps.ratio * 100, 1)} %` : "—",
        gaps ? `${countLabel(gaps.expected - gaps.observed, "intervalle sans mesure", "intervalles sans mesure")} sur ${gaps.expected} attendus. Les lacunes ne sont pas interpolées.`
          : "Fenêtre indéterminée.",
        gaps && gaps.ratio > 0.1 ? "warning" : "normal",
      ),
    );
  };
  const buildInsights = () => {
    const root = document.getElementById("history-insight-grid"); if (!root) return;
    const temperature = current.series.find((item) => item.control_role === "climate_temperature") || current.series.find((item) => item.unit?.includes("°C"));
    const points = temperature ? current.buckets.map((bucket) => ({ts: bucket.bucket_start_ts, value: bucket.sensors[temperature.key]?.avg, min: bucket.setpoints?.temp_min, max: bucket.setpoints?.temp_max, quality: bucket.sensor_quality?.[temperature.key] || {}})).filter((point) => [point.value, point.min, point.max].every(Number.isFinite)) : [];
    let within = 0; let below = 0; let above = 0; let longest = 0; let run = 0; let previousTs = null; let previousState = null; let maxDeviation = 0;
    points.forEach((point) => {
      const contiguous = previousTs === null || point.ts - previousTs <= current.bucket_seconds * 2.5;
      const state = point.value < point.min ? "below" : point.value > point.max ? "above" : "within";
      if (state === "within") { within += 1; run = 0; }
      else {
        if (state === "below") below += 1; else above += 1;
        run = contiguous && previousState === state ? run + current.bucket_seconds : current.bucket_seconds;
        longest = Math.max(longest, run);
        maxDeviation = Math.max(maxDeviation, state === "below" ? point.min - point.value : point.value - point.max);
      }
      previousTs = point.ts;
      previousState = state;
    });
    const total = points.length; const targetRate = total ? within / total * 100 : null;
    const heater = actuatorStats("heater"); const motor = actuatorStats("motor");
    const events = current.events || []; const alarmCount = events.filter((event) => event.kind === "alarm").length; const noteCount = events.filter((event) => event.kind === "operator_note").length;
    root.replaceChildren(
      insight("Température dans la cible", total ? `${formatNombre(targetRate, 1)} %` : "—", total ? `${formatDuration(below * current.bucket_seconds)} sous la cible · ${formatDuration(above * current.bucket_seconds)} au-dessus` : "Aucune mesure exploitable", targetRate !== null && targetRate < 90 ? "warning" : "normal"),
      insight("Plus longue excursion", total ? formatDuration(longest) : "—", maxDeviation ? `écart maximal ${formatNombre(maxDeviation, 1)} °C` : "aucune excursion observée", longest > 1800 ? "warning" : "normal"),
      insight("Chauffage", heater ? formatDuration(heater.activeDuration || 0) : "—", heater ? `${countLabel(heater.transitions || 0, "bascule", "bascules")} · couverture ${formatNombre(heater.coverage || 0, 0)} %` : "Aucune observation"),
      insight("Ventilation", motor ? formatDuration(motor.activeDuration || 0) : "—", motor ? `maximum V${formatNombre(motor.maximum || 0, 0)} · couverture ${formatNombre(motor.coverage || 0, 0)} %` : "Aucune observation"),
      insight("Événements", String(alarmCount + noteCount), `${countLabel(alarmCount, "alarme", "alarmes")} · ${countLabel(noteCount, "note opérateur", "notes opérateur")}`, alarmCount ? "warning" : "normal")
    );
    const updated = document.getElementById("history-updated-at");
    if (updated) updated.textContent = `Actualisé à ${new Date().toLocaleTimeString("fr-FR", {hour: "2-digit", minute: "2-digit"})}`;
  };
  const drawAll = () => {
    if (!current) return;
    const temperature = current.series.filter((item) => item.unit.includes("°C")); const humidity = current.series.filter((item) => item.unit.includes("%"));
    drawSensorChart(document.getElementById("temperature-chart"), temperature, "°C", {temperature: true});
    drawSensorChart(document.getElementById("humidity-chart"), humidity, "%", {humidity: true});
    drawTimeline(document.getElementById("automation-chart"), groups.automation.filter((id) => !hiddenActuators.has(id))); drawTimeline(document.getElementById("climate-actuator-chart"), groups["climate-actuator"].filter((id) => !hiddenActuators.has(id)));
    document.querySelectorAll("[data-history-unit]").forEach((canvas) => { const unit = canvas.dataset.historyUnit; drawSensorChart(canvas, current.series.filter((item) => item.unit === unit), unit); });
  };
  // Déclaré **après** `drawAll` : l'ancienne garde `typeof drawAll === "function"` ne protégeait
  // de rien — `typeof` sur une liaison `const` en zone morte lève une `ReferenceError` au lieu
  // de rendre "undefined". L'ordre des déclarations est la vraie réponse ; la garde était un
  // faux filet qui aurait laissé planter le premier déplacement de l'appel.
  const selectChart = (redraw = true) => {
    const selected = viewPicker ? viewPicker.value : "all";
    document.querySelectorAll("canvas[data-history-chart]").forEach((canvas) => {
      const card = canvas.closest(".chart-card");
      if (card) card.dataset.mobileChartHidden = String(selected !== "all" && canvas.dataset.historyChart !== selected);
    });
    // Un graphique redevenu visible a une largeur nulle tant qu'il est masqué : il faut le
    // remesurer, puis rejouer la fiche du point choisi, qui doit survivre au changement de vue.
    if (redraw && current) { drawAll(); refreshSelection(); }
  };
  viewPicker?.addEventListener("change", () => selectChart());
  const render = (data) => {
    current = data; selectedTimestamp = null; hoverTimestamp = null; plots.clear();
    showHistoryData(true);
    const temperature = data.series.filter((item) => item.unit.includes("°C")); const humidity = data.series.filter((item) => item.unit.includes("%"));
    const otherUnits = [...new Set(data.series.filter((item) => !item.unit.includes("°C") && !item.unit.includes("%")).map((item) => item.unit))];
    buildLegends(temperature, humidity); buildAdditionalCharts(otherUnits);
    document.getElementById("temperature-summary").textContent = sensorSummary(temperature, "°C"); document.getElementById("humidity-summary").textContent = sensorSummary(humidity, "%");
    renderGroupSummary(document.getElementById("automation-summary"), groups.automation); renderGroupSummary(document.getElementById("climate-actuator-summary"), groups["climate-actuator"]);
    buildTable(); buildMetrics(); buildInsights(); selectChart(false); drawAll(); refreshSelection();
    const exactCount = Object.values(data.actuator_history || {}).filter((item) => item.intervals?.length).length;
    message.textContent = `${countLabel(data.buckets.length, "intervalle", "intervalles")} de ${Math.round(data.bucket_seconds / 60)} min · courbes : moyenne et plage min–max · ${countLabel(exactCount, "actionneur", "actionneurs")} avec changements d’état relevés. Les lacunes ne sont pas interpolées.`;
  };

  const nearestBucketIndex = (timestamp) => {
    if (!current?.buckets.length) return -1;
    let low = 0; let high = current.buckets.length - 1;
    while (low < high) { const middle = Math.floor((low + high) / 2); if (current.buckets[middle].bucket_start_ts < timestamp) low = middle + 1; else high = middle; }
    return low > 0 && Math.abs(current.buckets[low - 1].bucket_start_ts - timestamp) < Math.abs(current.buckets[low].bucket_start_ts - timestamp) ? low - 1 : low;
  };
  const selectedDetails = (bucket) => {
    const entries = [];
    current.series.forEach((meta) => { const item = bucket.sensors[meta.key]; entries.push([meta.label, item?.valid_count ? `${formatNombre(item.avg, meta.decimals)} ${meta.unit}` : "inconnue"]); });
    Object.values(groups).flat().forEach((id) => {
      const item = bucket.actuators[id]; let value = "inconnu";
      const interval = (current.actuator_history?.[id]?.intervals || []).find((entry) => entry.start_ts <= bucket.bucket_start_ts && entry.end_ts > bucket.bucket_start_ts);
      if (interval?.status === "ok" && Number.isFinite(interval.actual)) {
        value = id === "motor" ? `V${formatNombre(interval.actual, 0)} (GPIO relu)` : `${interval.actual > 0 ? "EN MARCHE" : "ARRÊTÉ"} (GPIO relu)`;
      } else if (item?.valid_count && Number.isFinite(item.avg_value)) {
        if (id === "motor") value = item.min_value === item.max_value ? `V${formatNombre(item.avg_value, 0)}` : `V${formatNombre(item.min_value, 0)} à V${formatNombre(item.max_value, 0)}`;
        else value = item.on_rate === 1 ? "EN MARCHE" : item.on_rate === 0 ? "ARRÊTÉ" : "mixte dans l’intervalle";
      }
      entries.push([equipmentName(id), value]);
    });
    const events = (current.events || []).filter((event) => Math.abs(event.ts - bucket.bucket_start_ts) <= current.bucket_seconds / 2);
    if (events.length) entries.push(["Événement", events.map((event) => event.kind === "alarm" ? "alarme" : event.kind === "operator_note" ? `note : ${event.payload?.note || "observation"}` : "configuration").join(", ")]);
    return entries;
  };
  // Fiche du point choisi, écrite **dans** le conteneur rendu par la macro `chart_detail` :
  // un `<p>` de titre et un `dl` de couples `dt`/`dd`, jamais une phrase à plat.
  //
  // Le conteneur ne bouge pas : il est rendu une fois par le gabarit, à une position fixe sous
  // les tracés. Déplacer un nœud `aria-live` (l'ancien `.after(selectionOutput)`) le retire du
  // document puis l'y remet, et selon le lecteur d'écran l'annonce est perdue ou doublée.
  //
  // L'écriture est **conditionnée à un changement réel** de contenu : un redessin, un
  // redimensionnement ou un rechargement périodique qui retombe sur le même point ne touche
  // pas au DOM, donc ne fait pas reparler la région atomique.
  // Même texte que celui rendu par le gabarit (`chart_detail`) : la signature de départ décrit
  // donc l'état déjà présent dans le document, et le premier rendu de la page ne réécrit rien.
  const EMPTY_SELECTION_LABEL = "Aucun point sélectionné";
  let detailSignature = JSON.stringify([EMPTY_SELECTION_LABEL, []]);
  const writeSelectionDetail = (label, entries) => {
    if (!selectionDetail) return;
    const signature = JSON.stringify([label, entries]);
    if (signature === detailSignature) return;
    detailSignature = signature;
    const title = selectionDetail.querySelector("p"); const list = selectionDetail.querySelector("dl");
    if (title) title.textContent = label;
    if (list) list.replaceChildren(...entries.flatMap(([name, value]) => [element("dt", "", name), element("dd", "num", value)]));
  };
  const clearSelectionDetail = () => writeSelectionDetail(EMPTY_SELECTION_LABEL, []);
  // `announce` distingue la sélection confirmée du simple survol. Elle ne se contente pas de
  // taire l'annonce : elle décide **lequel des deux états** est écrit. Un survol ne touche donc
  // ni à `selectedTimestamp` ni à la fiche, et ne peut plus armer une annonce différée.
  const showSelection = (timestamp, position = null, announce = false) => {
    const index = nearestBucketIndex(timestamp); if (index < 0) return;
    const bucket = current.buckets[index];
    if (announce) { selectedTimestamp = bucket.bucket_start_ts; hoverTimestamp = null; }
    else hoverTimestamp = bucket.bucket_start_ts;
    pointerPosition = position || pointerPosition;
    const details = selectedDetails(bucket); const title = element("strong", "", formatDate(bucket.bucket_start_ts, true)); const list = document.createElement("dl");
    details.forEach(([label, value]) => list.append(element("dt", "", label), element("dd", "", value))); tooltip.replaceChildren(title, list); tooltip.hidden = false;
    const point = pointerPosition || {x: window.innerWidth / 2, y: 80}; const tooltipWidth = Math.min(304, window.innerWidth - 16);
    tooltip.style.left = `${Math.max(8, Math.min(point.x + 14, window.innerWidth - tooltipWidth - 8))}px`;
    tooltip.style.top = `${Math.max(8, Math.min(point.y + 14, window.innerHeight - Math.min(tooltip.offsetHeight || 300, window.innerHeight - 16) - 8))}px`;
    if (announce) writeSelectionDetail(`Point sélectionné : ${formatDate(bucket.bucket_start_ts, true)}`, details);
    drawAll();
  };
  // Rejoué après un redessin de mise en page (redimensionnement, changement d'indicateur) :
  // l'horodatage retenu est un index de seau, pas une position en pixels, donc le point
  // survit au changement de taille et la fiche affiche le même horodatage qu'avant.
  const refreshSelection = () => {
    if (!current || !Number.isFinite(selectedTimestamp)) { clearSelectionDetail(); return; }
    const index = nearestBucketIndex(selectedTimestamp); if (index < 0) { clearSelectionDetail(); return; }
    const bucket = current.buckets[index];
    writeSelectionDetail(`Point sélectionné : ${formatDate(bucket.bucket_start_ts, true)}`, selectedDetails(bucket));
  };
  const scheduleSelection = (event, canvas, announce = false) => {
    const graph = plots.get(canvas); if (!graph) return;
    const rect = canvas.getBoundingClientRect(); const localX = event.clientX - rect.left;
    const timestamp = graph.start + (localX - graph.box.left) / Math.max(1, graph.box.right - graph.box.left) * (graph.end - graph.start);
    pointerPosition = {x: event.clientX, y: event.clientY}; if (redrawFrame !== null) cancelAnimationFrame(redrawFrame);
    redrawFrame = requestAnimationFrame(() => { redrawFrame = null; showSelection(Math.max(graph.start, Math.min(graph.end, timestamp)), pointerPosition, announce); });
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
  section.addEventListener("pointermove", (event) => { const canvas = event.target.closest("canvas[data-history-chart]"); if (canvas && event.pointerType !== "touch") scheduleSelection(event, canvas); });
  let touchStart = null;
  section.addEventListener("pointerdown", event => {
    const canvas = event.target.closest("canvas[data-history-chart]");
    if (!canvas) return;
    // Un appui de souris ou de stylet est une sélection confirmée, au même titre qu'un tap :
    // seul le survol (`pointermove`) reste une exploration muette.
    if (event.pointerType === "touch") touchStart = {x: event.clientX, y: event.clientY, canvas};
    else scheduleSelection(event, canvas, true);
  });
  section.addEventListener("pointercancel", () => { touchStart = null; });
  section.addEventListener("pointerup", event => {
    if (touchStart && Math.hypot(event.clientX - touchStart.x, event.clientY - touchStart.y) <= TAP_MAX_DISTANCE_PX) scheduleSelection(event, touchStart.canvas, true);
    touchStart = null;
  });
  // Le curseur de survol meurt avec le survol : il ne reste pas armé derrière l'infobulle.
  section.addEventListener("pointerleave", () => { tooltip.hidden = true; pointerPosition = null; hoverTimestamp = null; drawAll(); });
  section.addEventListener("keydown", (event) => {
    const canvas = event.target.closest("canvas[data-history-chart]"); if (!canvas || !current?.buckets.length) return;
    if (event.key === "Escape") { selectedTimestamp = null; hoverTimestamp = null; tooltip.hidden = true; clearSelectionDetail(); drawAll(); return; }
    if (!["ArrowLeft", "ArrowRight", "Home", "End"].includes(event.key)) return;
    event.preventDefault(); let index = Number.isFinite(selectedTimestamp) ? nearestBucketIndex(selectedTimestamp) : current.buckets.length - 1;
    if (event.key === "ArrowLeft") index -= 1; if (event.key === "ArrowRight") index += 1; if (event.key === "Home") index = 0; if (event.key === "End") index = current.buckets.length - 1;
    index = Math.max(0, Math.min(current.buckets.length - 1, index)); const rect = canvas.getBoundingClientRect();
    showSelection(current.buckets[index].bucket_start_ts, {x: rect.left + rect.width / 2, y: rect.top + 30}, true);
  });

  const fetchHistory = async (hours, retry = true) => {
    const response = await requestWithTimeout(`/api/v1/history?hours=${hours}`, {headers: {Accept: "application/json"}, cache: "no-store"}, 12000);
    if (response.status === 429 && retry) {
      const retryAfter = Math.min(5, Math.max(1, Number(response.headers.get("Retry-After")) || 1));
      await new Promise((resolve) => window.setTimeout(resolve, retryAfter * 1000));
      return fetchHistory(hours, false);
    }
    return response;
  };

  const load = async (hours) => {
    message.textContent = "Chargement de l’historique…"; tooltip.hidden = true; section.setAttribute("aria-busy", "true");
    try {
      const response = await fetchHistory(hours);
      if (!response.ok) throw new Error(`HTTP ${response.status}`); await window.PhytoPwa?.markServerContact(Date.now(), "history"); const data = await response.json(); await window.PhytoPwa?.storeSnapshot(`history:${hours}`, data, Date.now()); render(data);
    } catch (error) {
      if (window.PhytoPwa?.isTransportError?.(error) || error instanceof TypeError) window.PhytoPwa?.signalerEchecTransport();
      else window.PhytoPwa?.markServerDegraded(`Historique momentanément indisponible (${error.message}).`, "history");
      const stored = await window.PhytoPwa?.loadSnapshot(`history:${hours}`) || await window.PhytoPwa?.loadSnapshot("history");
      if (stored?.data) {
        render(stored.data); const storedHours = Number(stored.data.hours || hours); document.querySelectorAll("[data-hours]").forEach((item) => { const selected = Number(item.dataset.hours) === storedHours; item.classList.toggle("is-selected", selected); item.setAttribute("aria-pressed", String(selected)); });
        const age = Math.max(0, Math.round((Date.now() - stored.receivedAt) / 60000)); message.textContent = `Historique enregistré il y a ${age} min · données non actualisées, lacunes conservées.`;
      } else { showHistoryData(false); message.textContent = `Historique local indisponible (${error.message}). Aucune vue enregistrée ; le contrôle reste actif.`; }
    } finally {
      section.setAttribute("aria-busy", "false");
    }
  };
  let currentHours = 24;
  document.querySelectorAll("[data-hours]").forEach((button) => button.addEventListener("click", () => { currentHours = Number(button.dataset.hours); document.querySelectorAll("[data-hours]").forEach((item) => { const selected = item === button; item.classList.toggle("is-selected", selected); item.setAttribute("aria-pressed", String(selected)); }); load(currentHours); }));
  section.querySelector("[data-history-retry]")?.addEventListener("click", () => load(24));
  document.addEventListener("phyto:themechange", drawAll);
  // Le redimensionnement remesure les tracés **et** réaffiche la fiche du point choisi :
  // `selectedTimestamp` est un horodatage de seau, pas une abscisse, donc le point survit à la
  // rotation du téléphone et la fiche montre le même horodatage qu'avant.
  let resizeTimer; window.addEventListener("resize", () => { clearTimeout(resizeTimer); resizeTimer = setTimeout(() => { if (!current) return; selectChart(false); drawAll(); refreshSelection(); }, 150); });
  window.setInterval(() => { if (!document.hidden && current) load(currentHours); }, 300000);
  const noteForm = document.querySelector("[data-history-note-form]");
  noteForm?.addEventListener("submit", async (event) => {
    event.preventDefault(); const button = noteForm.querySelector('button[type="submit"]'); const status = noteForm.querySelector(".form-status");
    button.disabled = true; status.textContent = "Enregistrement…";
    try {
      const response = await requestWithTimeout(noteForm.action, {method: "POST", headers: {Accept: "application/json"}, body: new FormData(noteForm)}, 10000);
      if (!response.ok) throw new Error((await response.text()) || `HTTP ${response.status}`);
      await window.PhytoPwa?.markServerContact(); noteForm.querySelector('input[name="note"]').value = ""; status.textContent = "Note ajoutée à l’historique."; await load(currentHours);
    } catch (error) {
      // L'échec d'une note est rapporté à son formulaire : ce n'est pas la dégradation d'un service
      // surveillé, et l'inscrire dans le bandeau global y laisserait un message que rien ne lève.
      if (window.PhytoPwa?.isTransportError?.(error) || error instanceof TypeError) window.PhytoPwa?.signalerEchecTransport();
      status.textContent = error.message || "Note non enregistrée.";
    } finally { button.disabled = false; }
  });
  if (section.dataset.historyAvailable === "true") load(24); else { showHistoryData(false); message.textContent = "Historique local indisponible. Le contrôle reste actif et InfluxDB n’est pas requis pour cette vue."; }
  selectChart();
})();
