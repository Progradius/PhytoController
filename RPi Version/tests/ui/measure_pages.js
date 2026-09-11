"use strict";
// Outil de mesure versionné (fiche R0.1), volontairement hors suite Playwright : il ne
// contient aucune assertion, il produit un JSON comparable à celui de l'audit du
// 9 septembre 2026 (`docs/images/audit-web-mobile-pwa-2026-09-09/measures.json`).
//
// Format de sortie : chaque entrée conserve **exactement** les clés de l'audit
// (`route`, `width`, `status`, `height`, `scrollWidth`, `dom`, `headings`, `smallTargets`,
// `resources`, `axe`, `errors`) et n'ajoute que des clés supplémentaires (`state`, `theme`,
// `viewport`, `carnet`, `mainVisibleMs`, `memory`, `actions`, `namedTargets`, `timings`, et
// les entrées `state: "premier_ecran"`). Aucune clé de l'audit n'est renommée :
// `scripts/compare-measures.py` compare donc les deux fichiers directement, sur la passe au
// carnet vide, la seule qui suit le protocole de l'audit (« Carnet des pages nominales »).
//
// Rejouer une révision ancienne (fiche R0.1, « rejouer le script sur la baseline ») :
//
//   git worktree add --detach <dossier> 8023123
//   PHYTO_TEST_PYTHON=.venv/bin/python PHYTO_MEASURE_ROOT="<dossier>/RPi Version" \
//     PHYTO_MEASURE_PERIMETRE=audit PHYTO_MEASURE_DIR=<sortie> npm run measure:ui
//
// Une cible fournie (`PHYTO_UI_BASE_URL`) reste strictement en lecture : les scénarios qui
// ouvrent, refusent ou enregistrent une saisie sont alors omis, et toute méthode autre que
// GET/HEAD est refusée au niveau du routage.
const {chromium} = require("@playwright/test");
const {AxeBuilder, createMother} = require("./culture_fixtures");
const {spawn} = require("node:child_process");
const {once} = require("node:events");
const crypto = require("node:crypto");
const fs = require("node:fs");
const os = require("node:os");
const path = require("node:path");

// Les douze pages de l'audit, dans son ordre : ce sont elles que le comparateur confronte.
const ROUTES = ["/", "/alarms", "/history", "/conf", "/console", "/cultures", "/cultures/solutions",
  "/cultures/cycles", "/cultures/targets", "/cultures/light", "/cultures/equipment", "/cultures/journal"];
// Vues nommées par une acceptation chiffrée du plan. Solutions garde ses trois vues sous une
// seule route (`?view=`), donc mesurer `/cultures/solutions` ne dit rien de R1.6 ni de R2.3 :
// la page par défaut n'est ni la liste des relevés ni l'explorateur. Elles sont mesurées ici
// pour que l'acceptation se lise dans le JSON versionné, et non dans une sonde jetable.
const VUES_ACCEPTATION = ["/cultures/solutions?view=releves", "/cultures/solutions?view=analyser"];
// Port dédié à la mesure : la suite Playwright réserve 38123 et les fixtures du carnet
// 39123 + rang du worker. Deux exécutions ne doivent jamais se disputer un port ni une base.
const PORT = Number(process.env.PHYTO_UI_MEASURE_PORT || 40123);
const CRITICAL_PORT = PORT + 1;
// Seuil de l'audit : une cible est « petite » dès qu'une de ses deux dimensions est sous
// 44 px. C'est un repère de confort, pas la limite WCAG 2.2 (24 px), évaluée à part.
const COMFORT_TARGET_PX = 44;
const WCAG_TARGET_PX = 24;
const THEMES = ["dark", "daylight"];
// Le formulaire de **saisie** de Solutions, et lui seul : chaque relevé du journal porte
// aussi un `form[data-solution-entry]`, mais de correction, avec un `data-id`. Sans cette
// distinction le sélecteur en désigne sept et la mesure vise une correction au hasard.
const SAISIE_FORM = "form[data-solution-entry]:not([data-id])";
const widths = () => (process.env.PHYTO_MEASURE_WIDTHS || "320,390,1440").split(",").map(Number).filter(Number.isFinite);
// Fenêtres **de l'audit** (`docs/development/audit-web-mobile-pwa-2026-09-09.md`, « Trois
// largeurs : 320 et 390 px, hauteur 844 px ; bureau 1440 × 900 »). La hauteur de fenêtre
// n'est pas un détail de présentation : `height` vaut `scrollHeight`, qui ne descend jamais
// sous la hauteur de la fenêtre, et la console se dimensionne sur elle. Sur la baseline,
// 320 × 568 et 1440 × 844 donnaient `/history` à 736 et 844 px (audit : 844 et 900) et
// `/console` à −13,7 % et −3,1 % — un écart de protocole, pas de page, qui interdisait tout
// rejeu à ±2 %. Chaque entrée consigne désormais sa fenêtre (`viewport`).
// `PHYTO_MEASURE_HEIGHT` impose une autre hauteur (ex. 568 pour un petit téléphone) : l'entrée
// le dit, et le comparateur refuse de confronter deux fenêtres différentes.
const AUDIT_HEIGHTS = {320: 844, 390: 844, 1440: 900};
const viewportFor = width => ({width,
  height: Number(process.env.PHYTO_MEASURE_HEIGHT) || AUDIT_HEIGHTS[width] || 844});
// Carnet des pages nominales, consigné dans la clé `carnet` de chaque entrée `state: "page"` :
//
// * `vide` — le protocole des 36 visites de l'audit : un `tests/ui_server.py` neuf, sans aucune
//   culture. Prouvé par le rejeu de la baseline (`rejeu-baseline-8023123.md` dans
//   `docs/images/remediation-web-mobile-pwa-2026-09-09/`) : carnet vide, les 36 hauteurs sont
//   reproduites à ±2 % ; avec une mère et six relevés, 12 d'entre elles s'écartent de 15 à 174 %.
//   Seule cette passe se compare à l'audit.
// * `rempli` — une mère et six relevés (fixture de la fiche R0.1), sur lesquels portent les
//   vues d'acceptation, les états ouverts et les scénarios annexes.
// * `externe` — cible `PHYTO_UI_BASE_URL`, dont le carnet n'est ni connu ni modifiable.
//
// Périmètre : `complet` (défaut) mesure les deux carnets, ou `audit`, qui ne rejoue **que** la
// matrice des 36 visites sur le carnet vide (12 pages × 3 largeurs, deux thèmes), sans états
// ouverts, contrastes ni scénarios annexes. C'est le mode du rejeu d'une révision ancienne : ses
// gabarits ne portent pas les formulaires et les vues que les scénarios annexes supposent.
const PERIMETRE = process.env.PHYTO_MEASURE_PERIMETRE || "complet";
if (!["complet", "audit"].includes(PERIMETRE)) throw new Error("PHYTO_MEASURE_PERIMETRE vaut « complet » ou « audit ».");
// Arbre servi : par défaut le répertoire courant. `PHYTO_MEASURE_ROOT` désigne un autre arbre
// du dépôt — une extraction de la baseline, par exemple — dont `tests/ui_server.py` est lancé
// tel quel, dans son propre répertoire : l'outil mesure ainsi une révision ancienne sans y
// être recopié.
const SERVED_ROOT = path.resolve(process.env.PHYTO_MEASURE_ROOT || process.cwd());

// Actions fréquentes nommées (fiche R5.3). `:subject` est remplacé par la fiche créée par
// les fabriques ; ces lignes sont donc omises sur une cible externe, où rien n'est créé.
// `scenario` dit dans quel état de la serre l'action existe : « Acquitter » n'a pas de
// sens sans alarme, « Reprendre » pas sans coupure en cours. Les mesurer dans l'état
// nominal ne prouverait qu'une chose — qu'on les y a cherchées au mauvais moment.
const NAMED_ACTIONS = [
  {route: "/", label: "Couper", scenario: "nominal"},
  {route: "/", label: "Configurer", scenario: "nominal"},
  {route: "/console", label: "Exporter", scenario: "nominal"},
  {route: "/cultures", label: "Saisir un relevé", scenario: "nominal"},
  {route: "/cultures/:subject", label: "Saisir un relevé", scenario: "nominal"},
  {route: "/cultures/:subject", label: "Observation / photo", scenario: "nominal"},
  // Les exports de Solutions vivent dans la vue « Analyser » : les chercher sur la vue par
  // défaut ne mesurerait qu'une section `hidden`.
  {route: "/cultures/solutions?view=analyser", label: "Exporter les relevés et interventions CSV du filtre", scenario: "nominal"},
  {route: "/cultures/solutions?view=analyser", label: "Base SQLite seule (sans photos)", scenario: "nominal"},
  {route: "/cultures/journal", label: "Exporter ce filtre en CSV", scenario: "nominal"},
  {route: "/cultures/targets", label: "Exporter les plages cibles CSV", scenario: "nominal"},
  // « Reprendre » demande une coupure active : aucun scénario du serveur de test n'en
  // pose, elle reste donc à mesurer sur appareil (grille Q01 de la qualification).
  {route: "/alarms", label: "Acquitter", scenario: "critical"},
];

function externalBaseURL() {
  if (!process.env.PHYTO_UI_BASE_URL) return null;
  const value = new URL(process.env.PHYTO_UI_BASE_URL);
  if (!["http:", "https:"].includes(value.protocol) || value.username || value.password || value.pathname !== "/" || value.search || value.hash) {
    throw new Error("PHYTO_UI_BASE_URL doit être une origine HTTP(S) nue, sans identifiant ni chemin.");
  }
  return value.origin;
}

// ---------------------------------------------------------------------------
// Serveur de mesure. Un seul serveur vit à la fois : le scénario « alarme critique »
// n'est démarré qu'après l'arrêt du serveur nominal, parce que `PHYTO_UI_MEASURE_SCENARIO`
// est lu au démarrage du processus serveur et ne peut pas changer en cours de route.
//
// Le garde-fou « un serveur par test » de `tests/ui/culture_fixtures.js` protège des tests
// **parallèles** : l'espace 2 du carnet est exclusif et une occupation ouverte n'a pas de
// fin, donc deux workers Playwright qui partagent une base se disputent cet espace et
// faussent les comptages du journal. Ici il n'y a ni worker ni parallélisme : un seul
// processus visite les pages l'une après l'autre et une seule mère est créée. Un serveur
// unique est donc sûr, et c'est même la seule façon de comparer les hauteurs des douze
// pages sur un carnet identique.
// ---------------------------------------------------------------------------
async function startServer(port, extraEnv) {
  const scratch = fs.mkdtempSync(path.join(os.tmpdir(), "phyto-measure-"));
  if (!fs.existsSync(path.join(SERVED_ROOT, "tests", "ui_server.py"))) {
    throw new Error(`Aucun tests/ui_server.py sous ${SERVED_ROOT} (PHYTO_MEASURE_ROOT).`);
  }
  // Un interpréteur désigné par un chemin relatif (`.venv/bin/python`) l'est depuis le
  // répertoire d'où l'outil est lancé, pas depuis l'arbre servi : il est donc résolu avant
  // le changement de répertoire du serveur. Un nom nu (`python3`) reste cherché dans `PATH`.
  const python = process.env.PHYTO_TEST_PYTHON || "python3";
  const child = spawn(python.includes(path.sep) ? path.resolve(python) : python, ["tests/ui_server.py"], {
    cwd: SERVED_ROOT,
    env: {...process.env, ...extraEnv, TMPDIR: scratch, PHYTO_UI_TEST_PORT: String(port)},
    stdio: ["ignore", "ignore", "inherit"],
  });
  const exited = once(child, "close");
  const url = `http://127.0.0.1:${port}`;
  let ready = false;
  for (let i = 0; i < 450 && !ready; i++) {
    if (child.exitCode !== null) throw new Error(`Serveur de mesure arrêté (port ${port})`);
    try { ready = (await fetch(`${url}/health/ready`)).ok; } catch { /* pas encore à l'écoute */ }
    if (!ready) await new Promise(resolve => setTimeout(resolve, 100));
  }
  if (!ready) throw new Error(`Démarrage du serveur de mesure expiré (port ${port})`);
  return {
    url,
    async stop() {
      child.kill("SIGTERM");
      await exited;
      fs.rmSync(scratch, {recursive: true, force: true});
    },
  };
}

/**
 * Garde de sortie posée sur **tout** contexte : aucune origine tierce, et aucune méthode
 * mutante sur une cible externe. Elle s'applique aussi aux redirections, aux sous-ressources
 * et aux `fetch`. Définie au niveau du module pour qu'aucun contexte créé hors de `main()`
 * ne puisse l'oublier.
 */
const guardContext = (context, baseURL, external) => context.route("**/*", route => {
  const request = route.request();
  if (new URL(request.url()).origin !== baseURL || (external && !["GET", "HEAD"].includes(request.method()))) {
    return route.abort();
  }
  return route.continue();
});

async function populate(page) {
  const subject = await createMother(page, "Mère mesures");
  const csrf = await page.locator('meta[name="csrf-token"]').getAttribute("content");
  for (let i = 0; i < 6; i++) {
    const response = await page.request.post("/api/v1/cultures/solutions", {headers: {"X-CSRF-Token": csrf}, data: {
      operation: "entry", request_id: crypto.randomUUID(), kind: "reading", targets: [subject],
      effective_at: `2026-08-0${i + 2}`, ph: 5.8 + i / 10, ec: 1.2 + i / 10,
    }});
    if (!response.ok()) throw new Error(`Fixture refusée : ${await response.text()}`);
  }
  return subject;
}

// ---------------------------------------------------------------------------
// Mesures dans la page
// ---------------------------------------------------------------------------

// Script évalué dans la page : il ne dépend d'aucune variable de Node.
const PAGE_MEASURE = ({comfort, wcag}) => {
  const visible = node => {
    const rect = node.getBoundingClientRect();
    if (rect.width <= 0 && rect.height <= 0) return false;
    const style = getComputedStyle(node);
    return style.visibility !== "hidden" && style.display !== "none";
  };
  const label = node => (node.textContent || "").trim()
    || node.getAttribute("aria-label") || node.getAttribute("name") || node.getAttribute("title") || "";
  const interactive = [...document.querySelectorAll(
    'a[href], button, summary, [role="button"], [role="link"], input:not([type="hidden"]), select, textarea')].filter(visible);
  const boxes = interactive.map(node => {
    const rect = node.getBoundingClientRect();
    return {text: label(node), w: Math.round(rect.width), h: Math.round(rect.height)};
  });
  return {
    height: document.documentElement.scrollHeight,
    scrollWidth: document.documentElement.scrollWidth,
    dom: document.querySelectorAll("*").length,
    headings: [...document.querySelectorAll("h1,h2")].map(node => ({
      text: node.textContent.trim(), y: Math.round(node.getBoundingClientRect().top + scrollY)})),
    // Critère de l'audit conservé à l'identique : une dimension sous 44 px suffit.
    smallTargets: boxes.filter(item => item.w < comfort || item.h < comfort),
    // Cibles réellement sous le minimum WCAG 2.2 AA : distinct du repère de confort.
    wcagTargets: boxes.filter(item => item.w < wcag || item.h < wcag),
    resources: performance.getEntriesByType("resource").map(entry => {
      let name = entry.name;
      try { name = new URL(entry.name).pathname; } catch { /* nom déjà relatif */ }
      return {name, size: entry.transferSize || entry.encodedBodySize || 0};
    }),
    actions: [...document.querySelectorAll(".action-link")].filter(visible).map(node => {
      const rect = node.getBoundingClientRect();
      return {text: label(node), width: Math.round(rect.width), height: Math.round(rect.height)};
    }),
  };
};

async function jsMemory(page) {
  const precise = await page.evaluate(async () => {
    if (!performance.measureUserAgentSpecificMemory) return null;
    try { const value = await performance.measureUserAgentSpecificMemory(); return {bytes: value.bytes, source: "measureUserAgentSpecificMemory"}; }
    catch { return null; }
  });
  if (precise) return precise;
  return page.evaluate(() => (performance.memory
    ? {bytes: performance.memory.usedJSHeapSize, source: "performance.memory"} : null));
}

/**
 * Une entrée de mesure, au format de l'audit.
 *
 * `mainVisibleMs` est **toujours** relevé avant axe : il vaut `performance.now()` pris
 * côté page dès que `main` est visible, c'est-à-dire le temps écoulé depuis le
 * `navigationStart` de ce document. Une mesure prise après `analyze()` inclurait les
 * secondes d'axe et ne mesurerait plus la visibilité du contenu principal.
 */
async function collect(page, entry, options = {}) {
  await page.evaluate(() => document.fonts.ready.then(() => true));
  await page.evaluate(value => { document.documentElement.dataset.theme = value; }, entry.theme);
  const measure = await page.evaluate(PAGE_MEASURE, {comfort: COMFORT_TARGET_PX, wcag: WCAG_TARGET_PX});
  const memory = await jsMemory(page);
  const axe = await new AxeBuilder({page}).withTags(["wcag2a", "wcag2aa", "wcag22aa"]).analyze();
  return {
    route: entry.route, width: entry.width, status: entry.status ?? 200,
    height: measure.height, scrollWidth: measure.scrollWidth, dom: measure.dom,
    headings: measure.headings, smallTargets: measure.smallTargets,
    resources: measure.resources, axe: axe.violations, errors: entry.errors || [],
    // Ajouts hors format d'audit.
    state: entry.state, theme: entry.theme, mainVisibleMs: entry.mainVisibleMs ?? null,
    // Fenêtre et carnet de la mesure : sans eux, deux hauteurs relevées selon deux protocoles
    // différents se comparent sans que rien ne le signale.
    viewport: page.viewportSize(), ...(entry.carnet ? {carnet: entry.carnet} : {}),
    memory, actions: measure.actions, wcagTargets: measure.wcagTargets,
    ...(options.extra || {}),
  };
}

/** Ouvre une route, vide le tampon d'erreurs et relève le temps de visibilité de `main`. */
async function openRoute(page, route, errors) {
  errors.length = 0;
  const response = await page.goto(route);
  await page.locator("main").waitFor({state: "visible"});
  const mainVisibleMs = await page.evaluate(() => performance.now());
  return {status: response ? response.status() : 200, mainVisibleMs};
}

// ---------------------------------------------------------------------------
// Contrastes (fiche R5.2)
// ---------------------------------------------------------------------------
const CONTRAST_SCRIPT = () => {
  const parse = value => {
    const match = String(value).match(/rgba?\(([^)]+)\)/);
    if (!match) return null;
    const parts = match[1].split(/[\s,/]+/).filter(Boolean).map(Number);
    if (parts.length < 3 || parts.some(Number.isNaN)) return null;
    return {r: parts[0], g: parts[1], b: parts[2], a: parts.length > 3 ? parts[3] : 1};
  };
  const over = (top, bottom) => ({
    r: top.r * top.a + bottom.r * (1 - top.a),
    g: top.g * top.a + bottom.g * (1 - top.a),
    b: top.b * top.a + bottom.b * (1 - top.a),
    a: 1,
  });
  const luminance = color => {
    const channel = value => {
      const v = value / 255;
      return v <= 0.03928 ? v / 12.92 : Math.pow((v + 0.055) / 1.055, 2.4);
    };
    return 0.2126 * channel(color.r) + 0.7152 * channel(color.g) + 0.0722 * channel(color.b);
  };
  const ratio = (a, b) => {
    const la = luminance(a);
    const lb = luminance(b);
    return (Math.max(la, lb) + 0.05) / (Math.min(la, lb) + 0.05);
  };
  const hex = color => `#${[color.r, color.g, color.b].map(v => Math.round(v).toString(16).padStart(2, "0")).join("")}`;
  // Fond effectif : on remonte les ancêtres jusqu'à un fond opaque, en composant les
  // couches translucides rencontrées.
  //
  // Un dégradé n'interrompt **pas** la remontée. Le dépôt superpose partout des dégradés
  // très légers (`body` : un radial à 9-18 % sur `var(--bg)` ; `.card` : un linéaire à 2 %)
  // au-dessus d'un aplat, et la couleur de fond calculée est justement cet aplat. Abandonner
  // à la première image faisait disparaître du rapport toute paire dont les ancêtres sont
  // transparents jusqu'à `body` — c'est ainsi que l'onglet « Plus » de la barre mobile, que
  // axe relève à 4,32:1 en plein jour, ne figurait nulle part. Le fond est donc approché par
  // sa couche solide, et le sample est marqué `approximate` pour que la lecture le sache.
  const background = node => {
    const layers = [];
    let approximate = false;
    let current = node;
    while (current) {
      const style = getComputedStyle(current);
      if (style.backgroundImage && style.backgroundImage !== "none") approximate = true;
      const color = parse(style.backgroundColor);
      if (color && color.a > 0) {
        layers.push(color);
        if (color.a >= 1) break;
      }
      current = current.parentElement;
    }
    if (!layers.length || layers[layers.length - 1].a < 1) layers.push({r: 255, g: 255, b: 255, a: 1});
    let result = layers[layers.length - 1];
    for (let i = layers.length - 2; i >= 0; i--) result = over(layers[i], result);
    return {color: result, approximate};
  };
  const visible = node => {
    const rect = node.getBoundingClientRect();
    if (rect.width <= 0 || rect.height <= 0) return false;
    const style = getComputedStyle(node);
    return style.visibility !== "hidden" && style.opacity !== "0";
  };
  // Aucune fusion ici : le script de page **relève**, Node fusionne. La clé de fusion
  // n'existe donc qu'à un seul endroit (`cleContraste`), au lieu d'être recopiée des deux
  // côtés du pont — deux copies qui auraient divergé au premier ajout de critère.
  const releves = [];
  const add = sample => { releves.push({...sample, count: 1}); };
  for (const node of document.querySelectorAll("body *")) {
    if (!visible(node)) continue;
    const own = [...node.childNodes].some(child => child.nodeType === 3 && child.textContent.trim().length);
    const style = getComputedStyle(node);
    const back = background(node);
    if (own && back.color) {
      const color = parse(style.color);
      if (color) {
        const front = color.a < 1 ? over(color, back.color) : color;
        const fontPx = parseFloat(style.fontSize) || 16;
        const weight = Number(style.fontWeight) || (style.fontWeight === "bold" ? 700 : 400);
        const bold = weight >= 700;
        // Grand texte au sens WCAG : ≥ 24 px, ou ≥ 18,66 px en gras.
        const large = fontPx >= 24 || (bold && fontPx >= 18.66);
        add({
          kind: "texte", tag: node.tagName.toLowerCase(),
          text: (node.textContent || "").trim().slice(0, 60),
          color: hex(front), background: hex(back.color), fontPx: Math.round(fontPx * 10) / 10,
          bold, threshold: large ? 3 : 4.5, ratio: Math.round(ratio(front, back.color) * 100) / 100,
          approximate: back.approximate,
        });
      }
    }
    if (node.matches('button, input, select, textarea, [role="button"], [role="switch"], [role="checkbox"]')) {
      // WCAG 1.4.11 « contraste non textuel » : ce qui doit ressortir, c'est la **limite
      // visible du contrôle contre la surface qui l'entoure**. Le fond est donc calculé à
      // partir du parent, jamais du contrôle lui-même : comparer la bordure d'un bouton à
      // son propre remplissage donne 1:1 sur tout bouton plein, c'est-à-dire un faux échec.
      // Les radios CSS de 1 px du dépôt n'ont aucune limite visible à contraster : ce que
      // l'œil et le doigt visent est leur `label`, déjà mesuré comme texte. Les compter
      // ici produirait un échec permanent sur un élément que personne ne voit — c'est la
      // même exception que l'audit pose pour la taille des cibles.
      const boite = node.getBoundingClientRect();
      const around = (boite.width >= 4 && boite.height >= 4 && node.parentElement)
        ? background(node.parentElement) : {color: null};
      const border = parse(style.borderTopColor);
      const width = parseFloat(style.borderTopWidth) || 0;
      const own = parse(style.backgroundColor);
      // Limite du contrôle : sa bordure si elle est dessinée, sinon son propre aplat.
      //
      // Un contrôle sans bordure d'auteur **et** rendu nativement (`appearance` non forcée
      // à `none` : case à cocher, radio, curseur du système) est dessiné par la plateforme.
      // Son contraste n'appartient pas à la feuille de style du dépôt et 1.4.11 l'exempte ;
      // le mesurer produisait deux faux échecs permanents, sur lesquels rien n'est actionnable.
      const authored = Boolean(border && border.a > 0 && width > 0);
      const natif = (style.appearance || "auto") !== "none";
      const edge = authored ? border : (!natif && own && own.a > 0 ? own : null);
      if (edge && around.color) {
        const front = edge.a < 1 ? over(edge, around.color) : edge;
        add({
          kind: "composant", tag: node.tagName.toLowerCase(),
          text: (node.getAttribute("name") || node.textContent || "").trim().slice(0, 60),
          color: hex(front), background: hex(around.color), fontPx: null, bold: false,
          threshold: 3, ratio: Math.round(ratio(front, around.color) * 100) / 100,
          approximate: around.approximate,
        });
      }
    }
  }
  return releves.map(sample => ({...sample, pass: sample.ratio >= sample.threshold}));
};

/**
 * Clé de fusion d'un relevé de contraste — **définition unique**.
 *
 * `tag` en fait partie : sans lui, une paire de couleurs partagée par un `input` et un
 * `select` ne nommerait qu'un des deux, au hasard du parcours du DOM.
 */
const cleContraste = sample =>
  `${sample.kind}|${sample.tag}|${sample.color}|${sample.background}|${sample.fontPx}|${sample.bold}`;

// Matrices de Machado (2009), sévérité 1,0, appliquées en RVB **linéaire**.
const CVD_MATRICES = {
  deuteranopie: [[0.367322, 0.860646, -0.227968], [0.280085, 0.672501, 0.047413], [-0.011820, 0.042940, 0.968881]],
  protanopie: [[0.152286, 1.052583, -0.204868], [0.114503, 0.786281, 0.099216], [-0.003882, -0.048116, 1.051998]],
};
const toLinear = v => { const s = v / 255; return s <= 0.04045 ? s / 12.92 : Math.pow((s + 0.055) / 1.055, 2.4); };
const fromLinear = v => {
  const clamped = Math.max(0, Math.min(1, v));
  const s = clamped <= 0.0031308 ? clamped * 12.92 : 1.055 * Math.pow(clamped, 1 / 2.4) - 0.055;
  return Math.round(s * 255);
};
const hexToRgb = value => {
  const clean = value.trim().replace("#", "");
  const full = clean.length === 3 ? [...clean].map(c => c + c).join("") : clean;
  return [0, 2, 4].map(i => parseInt(full.slice(i, i + 2), 16));
};
const simulate = (rgb, matrix) => {
  const linear = rgb.map(toLinear);
  return matrix.map(row => fromLinear(row[0] * linear[0] + row[1] * linear[1] + row[2] * linear[2]));
};
const rgbToLab = rgb => {
  const [r, g, b] = rgb.map(toLinear);
  const x = (0.4124 * r + 0.3576 * g + 0.1805 * b) / 0.95047;
  const y = 0.2126 * r + 0.7152 * g + 0.0722 * b;
  const z = (0.0193 * r + 0.1192 * g + 0.9505 * b) / 1.08883;
  const f = t => (t > 0.008856 ? Math.cbrt(t) : 7.787 * t + 16 / 116);
  return [116 * f(y) - 16, 500 * (f(x) - f(y)), 200 * (f(y) - f(z))];
};
const deltaE = (a, b) => {
  const la = rgbToLab(a);
  const lb = rgbToLab(b);
  return Math.round(Math.hypot(la[0] - lb[0], la[1] - lb[1], la[2] - lb[2]) * 10) / 10;
};
const toHex = rgb => `#${rgb.map(v => v.toString(16).padStart(2, "0")).join("")}`;

/**
 * Palettes de séries lues dans la page rendue (valeurs calculées, thème courant).
 *
 * Deux groupes **distincts**, jamais fusionnés : les six couleurs de série de `history.js`
 * et les encres de source de `culture_analysis.js`/`cultures.css`. Les mélanger ferait
 * apparaître des paires à ΔE nul qui ne sont que des alias de la même couleur
 * (`--chart-0` et `--green` valent le même vert) : deux noms, une seule série à l'écran.
 */
async function seriesPalette(page) {
  return page.evaluate(() => {
    const style = getComputedStyle(document.documentElement);
    const lire = names => {
      const named = {};
      for (const name of names) {
        const value = style.getPropertyValue(name).trim();
        if (value) named[name] = value;
      }
      return named;
    };
    return {
      history: lire(["--chart-0", "--chart-1", "--chart-2", "--chart-3", "--chart-4", "--chart-5"]),
      solutions: lire(["--blue", "--amber", "--red", "--green", "--muted"]),
    };
  });
}

/** Rapport deutéranopie/protanopie d'un groupe de séries, groupe par groupe. */
function cvdReport(palettes) {
  const report = {};
  for (const [groupe, palette] of Object.entries(palettes)) report[groupe] = cvdGroup(palette);
  return report;
}

/** Écart ΔE minimal entre deux séries d'un même groupe, en vision normale puis simulée. */
function cvdGroup(palette) {
  const entries = Object.entries(palette)
    .filter(([, value]) => /^#[0-9a-fA-F]{3}([0-9a-fA-F]{3})?$/.test(value.trim()))
    .map(([name, value]) => ({name, hex: value.trim(), rgb: hexToRgb(value)}));
  const views = {normale: null, ...CVD_MATRICES};
  const result = {series: entries.map(item => ({name: item.name, hex: item.hex})), views: {}};
  for (const [view, matrix] of Object.entries(views)) {
    const shown = entries.map(item => ({...item, seen: matrix ? simulate(item.rgb, matrix) : item.rgb}));
    const pairs = [];
    for (let i = 0; i < shown.length; i++) {
      for (let j = i + 1; j < shown.length; j++) {
        pairs.push({a: shown[i].name, b: shown[j].name, deltaE: deltaE(shown[i].seen, shown[j].seen)});
      }
    }
    pairs.sort((x, y) => x.deltaE - y.deltaE);
    result.views[view] = {
      simulated: shown.map(item => ({name: item.name, hex: toHex(item.seen)})),
      // ΔE (CIE76) faible : deux séries que **la couleur seule** ne sépare plus. Le seuil
      // nomme un risque, il ne tranche pas — c'est le tracé et le marqueur qui décident.
      closest: pairs.slice(0, 8),
      minDeltaE: pairs.length ? pairs[0].deltaE : null,
    };
  }
  return result;
}

function contrastMarkdown(reports, cvd) {
  const lines = ["# Rapport de contrastes et de perception des couleurs (R5.2)", "",
    `Produit par \`npm run measure:ui\` le ${new Date().toISOString()}.`, "",
    "Seuils : 4,5:1 pour le texte courant, 3:1 pour le grand texte (≥ 24 px, ou ≥ 18,66 px en gras)",
    "et pour la limite visible des composants de saisie contre la surface qui les entoure",
    "(WCAG 1.4.11). Le fond effectif est composé en remontant les ancêtres. Une paire marquée",
    "« ~ » traverse un dégradé : il est approché par sa couche solide, les dégradés du dépôt",
    "étant des teintes de 2 à 18 % posées sur un aplat. Les contrôles de moins de 4 px de côté",
    "(radios CSS masquées) ne sont pas comptés : leur affordance visible est leur `label`.",
    ""];
  for (const [theme, samples] of Object.entries(reports)) {
    const failures = samples.filter(sample => !sample.pass);
    lines.push(`## Thème \`${theme}\``, "",
      `${samples.length} paires distinctes mesurées, ${failures.length} sous le seuil.`, "");
    if (!failures.length) {
      lines.push("Aucune paire sous le seuil.", "");
      continue;
    }
    lines.push("| Type | Élément | Texte | Encre | Fond | Taille | Ratio | Seuil | Occurrences |",
      "| --- | --- | --- | --- | --- | ---: | ---: | ---: | ---: |");
    for (const item of failures.slice().sort((a, b) => a.ratio - b.ratio)) {
      const text = String(item.text || "").replace(/\s+/g, " ").replace(/\|/g, "/").slice(0, 40);
      const fond = `\`${item.background}\`${item.approximate ? " ~" : ""}`;
      lines.push(`| ${item.kind} | \`${item.tag}\` | ${text} | \`${item.color}\` | ${fond} | ${item.fontPx === null ? "—" : item.fontPx} | ${item.ratio} | ${item.threshold} | ${item.count} |`);
    }
    lines.push("");
  }
  lines.push("## Palette de séries en deutéranopie et protanopie", "",
    "Simulation Machado (2009), sévérité 1,0, en RVB linéaire ; écart ΔE (CIE76) entre séries.",
    "Un ΔE faible signale deux séries que la couleur seule ne sépare plus : elles doivent rester",
    "distinguées par le tracé (plein, tirets, pointillés) et par leur marqueur.", "");
  for (const [theme, report] of Object.entries(cvd)) {
    for (const [groupe, data] of Object.entries(report)) {
      const couleurs = data.series.map(item => `\`${item.name}\` ${item.hex}`).join(" · ");
      lines.push(`### Thème \`${theme}\` — groupe \`${groupe}\``, "", couleurs || "_palette vide_", "",
        "| Vue | ΔE minimal | Paire la plus proche |", "| --- | ---: | --- |");
      for (const [view, vue] of Object.entries(data.views)) {
        const closest = vue.closest[0];
        lines.push(`| ${view} | ${vue.minDeltaE === null ? "—" : vue.minDeltaE} | ${closest ? `\`${closest.a}\` / \`${closest.b}\`` : "—"} |`);
      }
      lines.push("");
    }
  }
  return lines.join("\n") + "\n";
}

// ---------------------------------------------------------------------------
// États ouverts, hors ligne, zoom, temps locaux
// ---------------------------------------------------------------------------

/**
 * Choisit la première cible réelle du sélecteur `target`, qui est `required` : sans elle,
 * la validation native refuse l'envoi et aucune réponse du serveur n'est jamais mesurée.
 */
async function chooseTarget(form, preferred = null) {
  const select = form.locator('select[name="target"]');
  if (!await select.count()) return false;
  // La cible **préférée** est la mère créée par les fabriques. Prendre la première option
  // venue désigne le réservoir de l'espace 2, dont un relevé exige au préalable une
  // solution déclarée : la saisie serait refusée pour une raison sans rapport avec la mesure.
  const value = await select.locator("option").evaluateAll((options, wanted) => {
    const exact = wanted && options.find(option => option.value === wanted);
    return (exact || options.find(option => option.value) || {}).value || "";
  }, preferred);
  if (!value) return false;
  await select.selectOption(value);
  return true;
}

/** Formulaire de relevé ouvert puis refusé, avec le temps d'ouverture réellement chronométré. */
async function formStates(page, width, errors, results) {
  // Ouverture d'un formulaire : temps entre le clic qui l'ouvre et la visibilité du
  // premier champ. La page est d'abord ouverte fermée, sans `view=saisir`.
  errors.length = 0;
  await page.goto("/cultures/solutions");
  await page.locator("main").waitFor({state: "visible"});
  let openMs = null;
  const opener = page.locator('a[href*="view=saisir"]').first();
  if (await opener.count()) {
    const started = Date.now();
    await opener.click();
    await page.locator(`${SAISIE_FORM} input[name="effective_at"]`).waitFor({state: "visible"});
    openMs = Date.now() - started;
  }

  await page.goto("/cultures/solutions?view=saisir");
  await page.locator("main").waitFor({state: "visible"});
  const mainVisibleMs = await page.evaluate(() => performance.now());
  const route = page.url().replace(new URL(page.url()).origin, "");
  const form = page.locator(SAISIE_FORM);
  await form.locator('input[name="effective_at"]').waitFor({state: "visible"});
  for (const theme of THEMES) {
    results.push(await collect(page, {route, width, theme, state: "formulaire_releve_ouvert",
      errors: [...errors], mainVisibleMs}, {extra: {timings: {ouvertureFormulaireMs: openMs}}}));
  }

  // Refus **du serveur**, rattaché à un champ. Vider un champ `required` ne produirait
  // rien : la validation native du navigateur bloquerait l'envoi avant tout aller-retour,
  // et l'état mesuré serait une bulle du navigateur, pas le refus de l'application.
  await chooseTarget(form);
  await form.locator('input[name="ph"]').fill("abcd");
  await form.getByRole("button", {name: "Enregistrer la saisie"}).click();
  await form.locator(".culture-form-errors").first().waitFor({state: "visible"});
  for (const theme of THEMES) {
    results.push(await collect(page, {route, width, theme, state: "formulaire_releve_refuse", errors: [...errors]}));
  }
}

/**
 * Bannière hors ligne réellement mesurée : contexte à `serviceWorkers: "allow"`, page
 * précachée par le service worker, puis `context.setOffline(true)`.
 *
 * Le verdict de connexion de `pwa.js` n'est pas instantané : il attend l'échec du budget
 * de ses sondes (une vingtaine de secondes). L'attente est donc longue par construction,
 * et un budget dépassé est consigné comme tel — jamais maquillé en réussite.
 */
async function offlineState(browser, baseURL, external, width, results) {
  const context = await browser.newContext({baseURL, viewport: viewportFor(width), serviceWorkers: "allow"});
  // Le contexte hors ligne est gardé comme les autres : c'est le seul qui autorise un
  // service worker, donc celui où une requête sortante échapperait le plus facilement à
  // la surveillance. L'oubli de cette garde privait la mesure hors ligne du garde-fou
  // « aucune requête sortante » que la fiche R0.1 impose à tout le script.
  await guardContext(context, baseURL, external);
  const errors = [];
  try {
    const page = await context.newPage();
    page.on("console", message => { if (message.type() === "error") errors.push(message.text()); });
    page.on("pageerror", error => errors.push(String(error.message || error)));
    await page.goto("/");
    await page.locator("main").waitFor({state: "visible"});
    const registered = await page.evaluate(async () => {
      if (!navigator.serviceWorker) return false;
      try {
        const registration = await navigator.serviceWorker.ready;
        return Boolean(registration.active);
      } catch { return false; }
    });
    if (!registered) {
      results.push({width, state: "banniere_hors_ligne", skipped: "aucun service worker actif dans ce navigateur"});
      return;
    }
    // Le service worker chauffe « / », « /history », « /alarms » et « /app » à
    // l'installation ; un court délai laisse ces requêtes aboutir avant la coupure.
    await page.waitForTimeout(3000);
    await context.setOffline(true);
    errors.length = 0;
    await page.goto("/").catch(() => null);
    const banner = page.locator("#pwa-connection-banner");
    try {
      await banner.waitFor({state: "visible", timeout: 60000});
    } catch {
      results.push({width, state: "banniere_hors_ligne", skipped: "bannière non apparue dans le budget de 60 s"});
      return;
    }
    const mainVisibleMs = await page.evaluate(() => performance.now());
    const readOnly = await page.evaluate(() => ({
      bodyOffline: document.body.classList.contains("is-offline"),
      banner: (document.getElementById("pwa-connection-banner")?.textContent || "").replace(/\s+/g, " ").trim(),
      controlsStillEnabled: [...document.querySelectorAll("form input, form select, form textarea, form button")]
        .filter(node => !node.disabled).length,
    }));
    for (const theme of THEMES) {
      results.push(await collect(page, {route: "/", width, theme, state: "banniere_hors_ligne",
        errors: [...errors], mainVisibleMs}, {extra: {offline: readOnly}}));
    }
  } finally {
    await context.setOffline(false).catch(() => null);
    await context.close();
  }
}

/** Temps d'interaction locaux : première interaction sur graphique, retour après enregistrement. */
async function localTimings(page, subject, width, results) {
  // Une mesure manquante est consignée avec **sa raison** : un `null` nu ne dit pas si
  // l'interface a changé, si la fixture était vide, ou si le geste a manqué sa cible.
  const timings = {premiereInteractionGraphiqueMs: null, retourApresEnregistrementMs: null,
    raisons: {}};
  // Vue « Analyser » : les trois vues de Solutions sont gardées par `hidden`, donc les
  // courbes n'ont aucune boîte mesurable tant que la page reste sur la vue par défaut.
  await page.goto(`/cultures/solutions?target=${encodeURIComponent(subject)}&view=analyser`);
  await page.locator("main").waitFor({state: "visible"});
  const svg = page.locator(".solution-chart svg").first();
  const output = page.locator(".culture-analysis-output").first();
  if (!await svg.count() || !await output.count()) {
    timings.raisons.graphique = "aucun graphique de solutions ou aucun explorateur sur la page";
  } else {
    const before = ((await output.textContent()) || "").trim();
    const points = svg.locator("circle");
    const total = await points.count();
    // Le geste vise un **point réellement tracé**, pas le centre géométrique de la figure :
    // l'explorateur n'accepte un tap que dans un rayon de 44 px d'un point, et le centre
    // d'un nuage n'est pas un point.
    //
    // Et il vise le **dernier** point, jamais le premier : l'explorateur démarre sur
    // l'index 0, donc un clic sur le premier point ne change rien et `select()` sort sans
    // rien réécrire. On mesurerait alors une absence de changement, pas une interaction.
    const gestures = [];
    if (total > 1) gestures.push({nom: "clic sur le dernier point", cible: points.nth(total - 1)});
    // Repli pour une figure à point unique : le bouton de l'explorateur est lui aussi une
    // première interaction sur le graphique, et le JSON dit lequel des deux a été mesuré.
    gestures.push({nom: "bouton « Point suivant »", cible: page.getByRole("button", {name: "Point suivant"}).first()});

    for (const geste of gestures) {
      if (!await geste.cible.count()) continue;
      // Défilement **avant** la lecture de la boîte : sur un téléphone les courbes sont
      // largement sous la ligne de flottaison, et `boundingBox()` rendrait alors des
      // coordonnées hors du viewport — le clic partirait à côté, silencieusement.
      await geste.cible.scrollIntoViewIfNeeded().catch(() => null);
      const box = await geste.cible.boundingBox();
      if (!box) continue;
      const started = Date.now();
      await page.mouse.click(box.x + box.width / 2, box.y + box.height / 2);
      try {
        // Attente du **changement** du détail, jamais de sa simple présence : la sortie de
        // l'explorateur est déjà visible avant le clic, une attente de visibilité
        // renverrait donc zéro sans qu'aucun point n'ait été sélectionné.
        await page.waitForFunction(previous => {
          const node = document.querySelector(".culture-analysis-output");
          return Boolean(node) && node.textContent.trim() !== previous;
        }, before, {timeout: 5000});
        timings.premiereInteractionGraphiqueMs = Date.now() - started;
        timings.geste = geste.nom;
        break;
      } catch {
        timings.raisons.graphique = `le détail n'a pas changé après ${geste.nom} (points tracés : ${total})`;
      }
    }
    if (timings.premiereInteractionGraphiqueMs !== null) delete timings.raisons.graphique;
  }

  // Retour après enregistrement : un relevé valide, puis l'ancre `event-{id}` focalisée.
  await page.goto(`/cultures/solutions?target=${encodeURIComponent(subject)}&view=saisir#saisie`);
  await page.locator("main").waitFor({state: "visible"});
  const form = page.locator(SAISIE_FORM);
  const date = form.locator('input[name="effective_at"]');
  const ph = form.locator('input[name="ph"]');
  if (!await date.count() || !await ph.count()) {
    timings.raisons.enregistrement = "formulaire de saisie absent de la page";
  } else {
    await chooseTarget(form, subject);
    // Une saisie **distincte par largeur**. Le serveur vit toute l'exécution : réécrire
    // trois fois le même relevé fait légitimement apparaître le panneau « Vérification
    // avant enregistrement » (rapprochement de relevés ressemblants, `culture_forms.js`),
    // qui prend le focus au lieu de l'ancre. Ce n'est pas un défaut du carnet — une
    // ressemblance n'est jamais une interdiction, elle demande une confirmation — mais
    // c'en était un de la mesure : elle ne chronométrait plus un enregistrement nominal.
    const rang = widths().indexOf(width);
    await date.fill(`2026-08-${String(9 + Math.max(0, rang)).padStart(2, "0")}`);
    await ph.fill(String(6.1 + Math.max(0, rang) / 10));
    const started = Date.now();
    await form.getByRole("button", {name: "Enregistrer la saisie"}).click();
    try {
      // L'élément focalisé **est** la confirmation (convention du dépôt) : c'est donc lui
      // qu'on attend, pas un message.
      await page.waitForFunction(() => {
        const focused = document.activeElement;
        return Boolean(focused && /^(event|entry)-/.test(focused.id || ""));
      }, undefined, {timeout: 15000});
      timings.retourApresEnregistrementMs = Date.now() - started;
    } catch {
      const diagnostic = await page.evaluate(() => ({
        focus: document.activeElement ? `${document.activeElement.tagName.toLowerCase()}#${document.activeElement.id || ""}.${document.activeElement.className || ""}` : "aucun",
        refus: (document.querySelector(".culture-form-errors")?.textContent || "").replace(/\s+/g, " ").trim().slice(0, 120),
      }));
      timings.raisons.enregistrement = diagnostic.refus
        ? `saisie refusée : ${diagnostic.refus}`
        : `aucune ancre event-/entry- focalisée (focus sur ${diagnostic.focus})`;
    }
  }
  results.push({width, state: "temps_locaux", timings});
}

/**
 * Localise des éléments dans la page **telle qu'elle s'affiche à l'arrivée** et dit s'ils
 * tiennent dans le premier écran. Évalué dans la page : aucune variable de Node.
 *
 * Un élément se désigne par `selector` (et `index`, rang parmi les correspondances) et/ou par
 * `label`, texte exact d'un contrôle (`a[href]`, `button`, `summary`, `[role="button"]` quand
 * aucun sélecteur n'est donné). Trois constats distincts, jamais confondus :
 *
 * * `present` — dans le document ;
 * * `rendu` — réellement visible : boîte de plus de 2 px de côté, ni `visibility: hidden`, ni
 *   `display: none`, ni `clip-path` (un `<details>` fermé ou `hidden` n'a pas de boîte, et un
 *   texte `.visually-hidden` en a une de 1 × 1 px, qui ne se voit pas) ;
 * * `dansPremierEcran` — sa boîte **entière** tient dans la zone utile de la fenêtre, à la
 *   position de défilement d'arrivée : la fenêtre moins les barres fixes ou collantes qui la
 *   recouvrent en haut et en bas (barre de navigation mobile, bandeau hors ligne). Une barre
 *   n'est retranchée que si elle ne contient pas l'élément lui-même. `premierEcran` détaille
 *   la boîte, la zone utile et le recouvrement partiel.
 */
const LOCATE_SCRIPT = ({items}) => {
  const vh = innerHeight;
  const vw = innerWidth;
  // Barres qui recouvrent le contenu : `fixed` ou `sticky`, au moins la moitié de la largeur,
  // moins de la moitié de la hauteur, et collées au bord haut ou bas de la fenêtre.
  const barres = [];
  for (const node of document.querySelectorAll("body *")) {
    const style = getComputedStyle(node);
    if (style.position !== "fixed" && style.position !== "sticky") continue;
    if (style.visibility === "hidden" || style.display === "none") continue;
    const r = node.getBoundingClientRect();
    if (r.width < vw / 2 || r.height <= 0 || r.height >= vh / 2 || r.bottom <= 0 || r.top >= vh) continue;
    if (r.top <= 1) barres.push({node, bord: "haut", limite: r.bottom});
    else if (r.bottom >= vh - 1) barres.push({node, bord: "bas", limite: r.top});
  }
  // « Rendu » ne peut pas se contenter d'une boîte non nulle : le dépôt masque des textes
  // destinés aux seules aides techniques par `.visually-hidden` (1 × 1 px, `clip`/`clip-path`),
  // qui reste une boîte positive dans le coin haut de l'écran. Les compter ferait passer un
  // libellé invisible pour un élément « dans le premier écran » — le constat le plus favorable
  // possible, et faux. Seuil à 2 px : aucune cible lisible ne mesure moins.
  const rendu = node => {
    const r = node.getBoundingClientRect();
    if (r.width <= 2 || r.height <= 2) return false;
    const style = getComputedStyle(node);
    if (style.clipPath && style.clipPath !== "none") return false;
    return style.visibility !== "hidden" && style.display !== "none";
  };
  const texte = node => (node.textContent || "").replace(/\s+/g, " ").trim();
  return items.map(item => {
    const candidats = [...document.querySelectorAll(item.selector || 'a[href], button, summary, [role="button"]')]
      .filter(node => item.label === undefined || texte(node) === item.label);
    const present = item.index === undefined ? candidats : candidats.slice(item.index, item.index + 1);
    const shown = present.filter(rendu);
    if (!present.length) return {...item, present: false, rendu: false, dansPremierEcran: false};
    if (!shown.length) return {...item, present: true, rendu: false, count: present.length, dansPremierEcran: false};
    const node = shown[0];
    const r = node.getBoundingClientRect();
    let haut = 0;
    let bas = vh;
    for (const barre of barres) {
      if (barre.node.contains(node)) continue;
      if (barre.bord === "haut") haut = Math.max(haut, barre.limite);
      else bas = Math.min(bas, barre.limite);
    }
    const entier = r.top >= haut - 0.5 && r.bottom <= bas + 0.5 && r.left >= -0.5 && r.right <= vw + 0.5;
    const partiel = Math.min(r.bottom, bas) > Math.max(r.top, haut) && Math.min(r.right, vw) > Math.max(r.left, 0);
    return {...item, present: true, rendu: true, count: shown.length, texte: texte(node).slice(0, 80),
      w: Math.round(r.width), h: Math.round(r.height), dansPremierEcran: entier,
      premierEcran: {entier, partiel, haut: Math.round(r.top), bas: Math.round(r.bottom), defilement: Math.round(scrollY),
        zone: {haut: Math.round(haut), bas: Math.round(bas)}}};
  });
};

/** Cibles nommées de la fiche R5.3, confrontées au repère 44 px et au minimum WCAG 24 px. */
async function namedTargets(page, subject, width, results, scenario = "nominal") {
  const measured = [];
  const wanted = NAMED_ACTIONS
    .filter(item => item.scenario === scenario)
    .filter(item => subject || !item.route.includes(":subject"));
  if (!wanted.length) return;
  const routes = [...new Set(wanted.map(item => item.route))];
  for (const route of routes) {
    const url = subject ? route.replace(":subject", encodeURIComponent(subject)) : route;
    await page.goto(url);
    await page.locator("main").waitFor({state: "visible"});
    const items = wanted.filter(item => item.route === route).map(item => ({label: item.label}));
    const located = await page.evaluate(LOCATE_SCRIPT, {items});
    // Format historique conservé : `visible` signifie « rendu » (boîte non nulle), et non
    // « dans la fenêtre » — c'est la clé que lisent les rapports déjà publiés. La présence
    // dans le premier écran est une clé **à part**, `dansPremierEcran`, détaillée par
    // `premierEcran`. « Absente du document » et « présente mais repliée » restent deux
    // constats différents : les confondre ferait passer un `details` fermé pour un libellé
    // disparu, et inversement.
    measured.push(...located.map(item => {
      if (!item.present) return {route, label: item.label, present: false, visible: false, dansPremierEcran: false};
      if (!item.rendu) return {route, label: item.label, present: true, visible: false, count: item.count, dansPremierEcran: false};
      return {route, label: item.label, present: true, visible: true, count: item.count, w: item.w, h: item.h,
        confort44: item.w >= COMFORT_TARGET_PX && item.h >= COMFORT_TARGET_PX,
        wcag24: item.w >= WCAG_TARGET_PX && item.h >= WCAG_TARGET_PX,
        dansPremierEcran: item.dansPremierEcran, premierEcran: item.premierEcran};
    }));
  }
  const describe = item => {
    if (!item.present) return "absente du document";
    if (!item.visible) return "présente mais non affichée à cette largeur";
    return `${item.w}×${item.h}`;
  };
  results.push({
    width, state: "cibles_nommees", scenario, namedTargets: measured,
    // Une cible non trouvée est consignée telle quelle : ce n'est pas une réussite.
    failures: measured.filter(item => !item.visible || !item.confort44)
      .map(item => `${item.route} · ${item.label} (${describe(item)})`),
  });
}

// Premier écran nommé par une acceptation (écart E6). Chaque scénario porte la fiche, la route
// (`:subject` = la mère des fabriques) et les éléments qui doivent tenir dans le premier écran.
// L'acceptation se lit à 390 × 844 ; les autres largeurs sont relevées pour information.
const PREMIER_ECRAN_LARGEUR_ACCEPTATION = 390;
const PREMIER_ECRAN = [
  // R1.2 : « état, fraîcheur, T/RH et alarme visibles sans défilement » sur le tableau de bord.
  {fiche: "R1.2", route: "/", elements: [
    {nom: "état de conduite", selector: "#overview-title"},
    {nom: "fraîcheur de l'état", selector: "#freshness"},
    {nom: "température", selector: ".climate-summary-item", index: 0},
    {nom: "humidité", selector: ".climate-summary-item", index: 1},
    {nom: "alarmes actives", selector: "[data-priority-alarms]"},
  ]},
  // R2.8 et écart E5 : « recherche visible sans défilement », et « Opérations du carnet » que
  // l'index des copies hors ligne repoussait sous le premier écran. La hauteur d'une entrée
  // (`h` de la première `.ui-journal-entry`) est la référence de toute comparaison future.
  {fiche: "R2.8", route: "/cultures/journal", elements: [
    {nom: "recherche du journal", selector: "[name=\"q\"]"},
    {nom: "titre « Opérations du carnet »", selector: "h2", label: "Opérations du carnet"},
    {nom: "première entrée du journal", selector: ".ui-journal-entry", index: 0},
  ]},
  // R1.8 : « nom, espace, stade, âge ; puis les deux actions principales ». Les faits sont les
  // trois premiers `li` de l'en-tête compact de la fiche, dans cet ordre (`cultures.html`).
  {fiche: "R1.8", route: "/cultures/:subject", elements: [
    {nom: "nom", selector: ".ui-compact-header h1"},
    {nom: "espace", selector: ".ui-compact-header .ui-facts li", index: 0},
    {nom: "stade", selector: ".ui-compact-header .ui-facts li", index: 1},
    {nom: "âge", selector: ".ui-compact-header .ui-facts li", index: 2},
    {nom: "action « Saisir un relevé »", label: "Saisir un relevé"},
    {nom: "action « Observation / photo »", label: "Observation / photo"},
  ]},
  // R2.7 : « sur Plages, la plage applicable et sa source sont visibles dans le premier
  // écran » — mesuré **avec** une cible consultée, qui porte une plage directe (fabrique
  // `declareTarget`). Sans cible, la section n'affiche qu'un état vide.
  {fiche: "R2.7", route: "/cultures/targets?target=:subject", elements: [
    {nom: "titre « Appliqué maintenant »", selector: "#applique h2"},
    {nom: "plage applicable", selector: "#applique [data-target-applied]"},
    {nom: "source de la plage", selector: "#applique [data-target-source]"},
  ]},
];

// R1.1 : « la première alarme critique et son action sont visibles sans défilement ». Ce
// scénario n'existe que devant une alarme : il est relevé sur le serveur `critical`, jamais
// sur le serveur nominal, où la liste est vide.
const PREMIER_ECRAN_CRITIQUE = [
  {fiche: "R1.1", route: "/alarms", elements: [
    {nom: "alarme la plus grave", selector: ".alarm-card .ui-alarm-summary h2"},
    {nom: "action conseillée", selector: ".alarm-card .ui-alarm-summary p", index: 1},
    {nom: "action « Diagnostiquer »", label: "Diagnostiquer"},
    {nom: "action « Acquitter »", label: "Acquitter"},
  ]},
];

/**
 * Plage cible directe sur la mère, pour le scénario R2.7. Posée **après** les deux passes de
 * pages : les créer avant changerait la hauteur nominale de `/cultures/targets` et de la fiche,
 * donc la comparabilité avec les mesures précédentes. Ouverte au 1er août, sans fin : elle
 * s'applique à la date du jour du serveur quel que soit le jour d'exécution.
 */
async function declareTarget(page, subject) {
  await page.goto("/cultures/targets");
  const csrf = await page.locator('meta[name="csrf-token"]').getAttribute("content");
  const response = await page.request.post("/api/v1/cultures/targets", {headers: {"X-CSRF-Token": csrf}, data: {
    operation: "target", request_id: crypto.randomUUID(), target: subject, label: "Plage de mesure",
    start_at: "2026-08-01", ph_min: "5,8", ph_max: "6,4", ec_min: "1,2", ec_max: "1,8",
  }});
  if (!response.ok()) throw new Error(`Plage cible refusée : ${await response.text()}`);
}

/** Présence dans le premier écran des éléments nommés par une acceptation, à une largeur. */
async function firstScreen(page, subject, width, results, scenarios = PREMIER_ECRAN, carnet = "rempli") {
  for (const scenario of scenarios) {
    const route = subject ? scenario.route.replace(":subject", encodeURIComponent(subject)) : scenario.route;
    await page.goto(route);
    await page.locator("main").waitFor({state: "visible"});
    await page.evaluate(() => document.fonts.ready.then(() => true));
    const elements = await page.evaluate(LOCATE_SCRIPT, {items: scenario.elements});
    // Défilement d'arrivée : une ancre, un `autofocus` ou une restauration de position
    // donneraient un « premier écran » qui n'en est pas un — la page serait déjà défilée. Il
    // entre donc dans les échecs, au même titre qu'un élément hors zone utile.
    const defilement = await page.evaluate(() => Math.round(scrollY));
    results.push({
      width, state: "premier_ecran", fiche: scenario.fiche, route, viewport: page.viewportSize(),
      carnet, acceptation: width === PREMIER_ECRAN_LARGEUR_ACCEPTATION, elements, defilement,
      // Un élément absent, replié, masqué aux yeux ou hors du premier écran est consigné tel
      // quel, et une page déjà défilée à l'arrivée l'est aussi.
      failures: [
        ...(defilement ? [`page défilée de ${defilement} px à l'arrivée : le premier écran mesuré n'est pas celui de l'arrivée`] : []),
        ...elements.filter(item => !item.dansPremierEcran).map(item => `${item.nom} (${!item.present
          ? "absent du document" : !item.rendu ? "présent mais non affiché"
            : `y ${item.premierEcran.haut}–${item.premierEcran.bas}, zone utile ${item.premierEcran.zone.haut}–${item.premierEcran.zone.bas}`})`),
      ],
    });
  }
}

// ---------------------------------------------------------------------------
// Programme principal
// ---------------------------------------------------------------------------
async function main() {
  const external = Boolean(process.env.PHYTO_UI_BASE_URL);
  const output = process.env.PHYTO_MEASURE_DIR || "test-results/measure-ui";
  fs.mkdirSync(output, {recursive: true});
  const results = [];
  const contrasts = {};
  const cvd = {};
  let browser;
  let server = null;
  try {
    if (!external) server = await startServer(PORT, {});
    const baseURL = externalBaseURL() || server.url;
    browser = await chromium.launch();

    const guard = context => guardContext(context, baseURL, external);

    const openContext = async width => {
      const context = await browser.newContext({baseURL, viewport: viewportFor(width), serviceWorkers: "block"});
      await guard(context);
      const page = await context.newPage();
      const errors = [];
      page.on("console", message => { if (message.type() === "error") errors.push(message.text()); });
      page.on("pageerror", error => errors.push(String(error.message || error)));
      return {context, page, errors};
    };
    const measurePages = async (page, errors, routes, width, carnet) => {
      for (const route of routes) {
        const opened = await openRoute(page, route, errors);
        for (const theme of THEMES) {
          results.push(await collect(page, {route, width, theme, state: "page", carnet,
            status: opened.status, mainVisibleMs: opened.mainVisibleMs, errors: [...errors]}));
          if (process.env.PHYTO_MEASURE_SCREENSHOTS === "1") {
            const nom = route.replaceAll("/", "_").replaceAll("?", "-").replaceAll("=", "-") || "home";
            const suffixe = carnet === "vide" ? "-carnet-vide" : "";
            await page.screenshot({path: path.join(output, `${width}-${theme}-${nom}${suffixe}.png`), fullPage: true});
          }
        }
      }
    };

    // Passe 1 — la matrice de l'audit, sur le carnet **vide** d'un serveur neuf : c'est la
    // seule passe comparable à `docs/images/audit-web-mobile-pwa-2026-09-09/measures.json`.
    // Elle précède toute création de culture, sans quoi le carnet ne serait plus vide.
    // Sur une cible externe, le carnet est celui du Pi : une seule passe, marquée `externe`.
    for (const width of widths()) {
      if (PERIMETRE === "complet" && external) break;
      const {context, page, errors} = await openContext(width);
      await measurePages(page, errors, ROUTES, width, external ? "externe" : "vide");
      await context.close();
    }

    let subject = null;
    // Passe 2 — carnet rempli, vues d'acceptation, états ouverts et scénarios annexes.
    for (const width of PERIMETRE === "complet" ? widths() : []) {
      const {context, page, errors} = await openContext(width);
      if (!external && !subject) subject = await populate(page);
      await measurePages(page, errors, ROUTES.concat(VUES_ACCEPTATION), width, external ? "externe" : "rempli");

      // Contrastes : relevés une seule fois, à la largeur mobile de référence, en
      // parcourant les douze pages pour couvrir les paires réellement rendues.
      if (width === 390) {
        for (const theme of THEMES) {
          const merged = new Map();
          for (const route of ROUTES) {
            await page.goto(route);
            await page.locator("main").waitFor({state: "visible"});
            await page.evaluate(value => { document.documentElement.dataset.theme = value; }, theme);
            for (const sample of await page.evaluate(CONTRAST_SCRIPT)) {
              const key = cleContraste(sample);
              const known = merged.get(key);
              if (known) known.count += sample.count;
              else merged.set(key, {...sample});
            }
          }
          contrasts[theme] = [...merged.values()];
          cvd[theme] = cvdReport(await seriesPalette(page));
        }
      }

      // Menu « Plus » ouvert.
      const openedHome = await openRoute(page, "/", errors);
      const more = page.locator(".mobile-more > summary");
      if (await more.isVisible()) {
        const started = Date.now();
        await more.click();
        await page.locator(".mobile-more-panel").waitFor({state: "visible"}).catch(() => null);
        const menuMs = Date.now() - started;
        for (const theme of THEMES) {
          results.push(await collect(page, {route: "/", width, theme, state: "menu_plus_ouvert",
            errors: [...errors], mainVisibleMs: openedHome.mainVisibleMs},
            {extra: {timings: {ouvertureMenuMs: menuMs}}}));
        }
      } else {
        results.push({width, state: "menu_plus_ouvert", skipped: "menu mobile absent à cette largeur"});
      }

      // Zoom 200 % — état 1 : agrandissement de la police seule.
      const zoomed = await openRoute(page, "/", errors);
      await page.evaluate(() => { document.documentElement.style.fontSize = "200%"; });
      for (const theme of THEMES) {
        results.push(await collect(page, {route: "/", width, theme, state: "zoom_200_police",
          errors: [...errors], mainVisibleMs: zoomed.mainVisibleMs}));
      }

      await namedTargets(page, subject, width, results);
      // `formStates` n'écrit rien : sa saisie est **refusée**. « Temps locaux », lui,
      // enregistre un relevé : il est repoussé après les pages de **toutes** les largeurs,
      // sans quoi le relevé écrit à 320 px grossirait le journal mesuré à 390 px.
      if (!external) {
        await formStates(page, width, errors, results);
      } else {
        for (const state of ["formulaire_releve_ouvert", "formulaire_releve_refuse", "temps_locaux"]) {
          results.push({width, state, skipped: "cible externe en lecture seule"});
        }
      }
      await context.close();

      // Zoom 200 % — état 2 : échelle de rendu. `deviceScaleFactor` est une option de
      // contexte : il faut donc un contexte dédié. Une page zoomée à 200 % ne dispose que
      // de la moitié de la largeur CSS, d'où le viewport divisé par deux.
      const zoomContext = await browser.newContext({
        baseURL, viewport: {width: Math.round(width / 2), height: Math.round(viewportFor(width).height / 2)},
        deviceScaleFactor: 2, serviceWorkers: "block"});
      await guard(zoomContext);
      const zoomPage = await zoomContext.newPage();
      const zoomErrors = [];
      zoomPage.on("console", message => { if (message.type() === "error") zoomErrors.push(message.text()); });
      zoomPage.on("pageerror", error => zoomErrors.push(String(error.message || error)));
      const zoomOpened = await openRoute(zoomPage, "/", zoomErrors);
      for (const theme of THEMES) {
        results.push(await collect(zoomPage, {route: "/", width, theme, state: "zoom_200_echelle",
          errors: [...zoomErrors], mainVisibleMs: zoomOpened.mainVisibleMs},
        {extra: {deviceScaleFactor: 2, cssViewportWidth: Math.round(width / 2)}}));
      }
      await zoomContext.close();

      // Bannière hors ligne : uniquement en local. Un service worker ne s'installe pas sur
      // une cible dont on ne maîtrise ni le certificat ni le cycle de vie, et une coupure
      // provoquée sur le Pi ne serait plus une lecture.
      if (!external) await offlineState(browser, baseURL, external, width, results);
      else results.push({width, state: "banniere_hors_ligne", skipped: "cible externe : aucune installation de service worker"});
    }

    // Temps d'interaction locaux : un relevé y est **enregistré**, donc après les pages.
    if (!external && subject && PERIMETRE === "complet") {
      for (const width of widths()) {
        const {context, page} = await openContext(width);
        await localTimings(page, subject, width, results);
        await context.close();
      }
    }

    // Passe 3 — premier écran des fiches R1.8 et R2.7 (écart E6), sur le carnet rempli
    // augmenté d'une plage cible directe (et des relevés que « temps locaux » a enregistrés,
    // un par largeur : ils n'entrent pas dans l'en-tête de la fiche ni dans la section
    // « Appliqué maintenant »). Rien n'est créé sur une cible externe.
    if (PERIMETRE === "complet") {
      if (external || !subject) {
        for (const width of widths()) {
          results.push({width, state: "premier_ecran", skipped: "cible externe : aucune fiche ni plage créée"});
        }
      } else {
        for (const width of widths()) {
          const {context, page} = await openContext(width);
          if (width === widths()[0]) await declareTarget(page, subject);
          await firstScreen(page, subject, width, results);
          await context.close();
        }
      }
    }

    // Scénario « alarme critique » (`tests/ui_server.py`). Le serveur nominal est arrêté
    // d'abord : `PHYTO_UI_MEASURE_SCENARIO` est lu au démarrage du processus serveur.
    if (!external && PERIMETRE === "complet") {
      await server.stop();
      server = await startServer(CRITICAL_PORT, {PHYTO_UI_MEASURE_SCENARIO: "critical"});
      const criticalURL = server.url;
      for (const width of widths()) {
        const context = await browser.newContext({baseURL: criticalURL, viewport: viewportFor(width), serviceWorkers: "block"});
        await context.route("**/*", route => (new URL(route.request().url()).origin !== criticalURL
          ? route.abort() : route.continue()));
        const page = await context.newPage();
        const errors = [];
        page.on("console", message => { if (message.type() === "error") errors.push(message.text()); });
        page.on("pageerror", error => errors.push(String(error.message || error)));
        for (const route of ["/", "/alarms"]) {
          const opened = await openRoute(page, route, errors);
          for (const theme of THEMES) {
            results.push(await collect(page, {route, width, theme, state: "alarme_critique",
              status: opened.status, mainVisibleMs: opened.mainVisibleMs, errors: [...errors]}));
          }
        }
        // « Acquitter » n'existe que devant une alarme : c'est ici, et nulle part ailleurs,
        // qu'elle peut être mesurée.
        await namedTargets(page, null, width, results, "critical");
        // R1.1 : premier écran de l'alarme la plus grave, ici aussi et nulle part ailleurs.
        await firstScreen(page, null, width, results, PREMIER_ECRAN_CRITIQUE, "vide");
        await context.close();
      }
    }
  } finally {
    if (browser) await browser.close();
    if (server) await server.stop();
  }

  // Écriture unique, en fin de course : un fichier réécrit à chaque page n'est jamais
  // qu'un fichier partiel de plus, et il est réécrit en entier à chaque fois.
  fs.writeFileSync(path.join(output, "measures.json"), JSON.stringify(results, null, 2) + "\n");
  for (const [theme, samples] of Object.entries(contrasts)) {
    fs.writeFileSync(path.join(output, `contrastes-${theme}.json`),
      JSON.stringify({theme, samples, series: cvd[theme]}, null, 2) + "\n");
  }
  if (Object.keys(contrasts).length) {
    fs.writeFileSync(path.join(output, "contrastes.md"), contrastMarkdown(contrasts, cvd));
  }
}

main().catch(error => { process.stderr.write(`${error.stack}\n`); process.exitCode = 1; });
