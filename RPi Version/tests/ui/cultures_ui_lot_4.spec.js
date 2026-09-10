"use strict";
const {test, expect, createMother, AxeBuilder} = require("./culture_fixtures");

// R2.3 : sous 48 rem, l'exploration d'une figure arrive repliée — curseur, boutons, sortie
// et tableau équivalent, soit 366 px par figure sur un écran de 390 px. Rien n'est retiré :
// le repli est nommé, porte le nombre de points et s'ouvre en une activation. Au-delà de
// 48 rem il est déjà ouvert, et l'aide ci-dessous ne fait rien.
const ouvrirExplorateur = async figure => {
  const repli = figure.locator(".culture-chart-explorer-fold");
  if (await repli.count() && (await repli.getAttribute("open")) === null) {
    await repli.locator(":scope > summary").click();
  }
};

// Points de consultation représentatifs, injectés avant l'exécution des scripts : la mesure
// du milieu est absente et ne doit jamais être dessinée ni comptée comme un zéro.
const routeSolutionChart = (page, count) => page.route("**/cultures/solutions?target=*", async route => {
  const response = await route.fetch();
  let html = await response.text();
  const points = Array.from({length: count}, (_, i) => ({ph: [6.1, null, 6.4][i % 3], ec: null,
    at: new Date(Date.UTC(2024, 0, 1) + i * 86400000).toISOString(), label: "pH",
    target: "Mère courbes", period: null, annotations: []}));
  html = html.replace(/data-chart="[^"]*"/, `data-chart="${JSON.stringify(points).replaceAll('"', '&quot;')}"`);
  await route.fulfill({response, body: html});
});

// R1.6 : à vide, la vue « Analyser » ne rend ni graphique ni légende — elle propose la
// première saisie. Les scénarios d'exploration ont donc besoin d'**une** mesure réelle ;
// les points de consultation, eux, restent injectés dans `data-chart` avant les scripts.
const mesureReelle = async (page, id) => {
  const csrf = await page.locator('meta[name="csrf-token"]').getAttribute("content");
  const response = await page.request.post("/api/v1/cultures/solutions", {
    headers: {"X-CSRF-Token": csrf},
    data: {operation: "entry", request_id: require("node:crypto").randomUUID(), kind: "reading",
      targets: [id], effective_at: "2026-08-02", ph: 6.1}});
  expect(response.ok(), await response.text()).toBeTruthy();
};

test("comparaison alignée, recherche et bilan sans données inventées", async ({page}, testInfo) => {
  test.skip(testInfo.project.name === "pwa-chromium", "Parcours avec mutations et interception HTTP, hors service worker.");
  test.setTimeout(90000);
  const first = await createMother(page, "Mère Alpha");
  const csrf = await page.locator('meta[name="csrf-token"]').getAttribute("content");
  const saved = await page.request.post("/api/v1/cultures/solutions", {headers: {"X-CSRF-Token": csrf},
    data: {operation: "entry", request_id: require("node:crypto").randomUUID(), kind: "reading",
      targets: [first], effective_at: "2026-08-02", ph: 0}});
  expect(saved.ok()).toBe(true);
  const second = await createMother(page, "Mère Bêta");
  await page.goto(`/cultures/cycles?subject=${first}&subject=${second}&view=comparer#comparaison`);
  const table = page.locator(".culture-comparison");
  await expect(table).toContainText("Mère Alpha"); await expect(table).toContainText("Mère Bêta");
  await expect(table).toContainText("0.00 / 0.00 / 0.00");
  await expect(table).toContainText("Aucune mesure"); await expect(table).toContainText("Non renseigné");
  await page.getByLabel("Filtrer les choix affichés").fill("inconnue");
  await expect(page.locator('[data-comparison-selection] input:checked')).toHaveCount(2);
  await expect(page.getByText("2 / 4 cultures sélectionnées", {exact: true})).toBeVisible();
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
  expect((await new AxeBuilder({page}).analyze()).violations).toEqual([]);
  await page.locator("h1").click();
  await page.screenshot({path: testInfo.outputPath("comparaison.png"), fullPage: true});
  await page.evaluate(() => document.documentElement.setAttribute("data-theme", "daylight"));
  expect((await new AxeBuilder({page}).analyze()).violations).toEqual([]);
  await page.locator("h1").click();
  await page.screenshot({path: testInfo.outputPath("comparaison-plein-jour.png"), fullPage: true});
  await page.goto(`/cultures/${first}#bilan`);
  await expect(page.locator("#bilan")).toContainText("jours à ce jour");
  await page.getByRole("link", {name: "Comparer ce bilan à d’autres cultures"}).click();
  await expect(page.locator('[data-comparison-selection] input:checked')).toHaveCount(1);
});

test("courbes explorables au clavier et au toucher, tableau équivalent et lacunes", async ({page}, testInfo) => {
  test.skip(testInfo.project.name === "pwa-chromium", "Parcours avec mutations et interception HTTP, hors service worker.");
  test.setTimeout(90000);
  const id = await createMother(page, "Mère courbes");
  await mesureReelle(page, id);
  // R1.6 : les figures vivent dans la vue « Analyser » ; les deux autres vues sont servies
  // mais `hidden`, donc hors de l'arbre d'accessibilité. La vue est demandée par le lien
  // d'onglet, c'est-à-dire par la même route avec `view=analyser`. `target` reste en tête
  // de la requête : l'interception ci-dessous filtre sur ce préfixe.
  await page.goto(`/cultures/solutions?target=${id}&view=analyser`);
  // Données de consultation représentatives, injectées avant l'exécution des scripts.
  let pointCount = 3;
  await page.route("**/cultures/solutions?target=*", async route => {
    const response = await route.fetch(); let html = await response.text();
    const points = Array.from({length: pointCount}, (_, i) => ({ph: [6.1, null, 6.4][i % 3], ec: null, at: new Date(Date.UTC(2024, 0, 1) + i * 86400000).toISOString(), label: "pH", target: "Mère courbes", period: null, annotations: []}));
    html = html.replace(/data-chart="[^"]*"/, `data-chart="${JSON.stringify(points).replaceAll('"', '&quot;')}"`);
    await route.fulfill({response, body: html});
  });
  await page.reload();
  const figure = page.locator(".solution-chart").first();
  await ouvrirExplorateur(figure);
  const slider = figure.getByRole("slider");
  const output = figure.locator(".culture-analysis-output");
  await slider.focus(); await slider.press("ArrowRight");
  await expect(output).toContainText("mesure absente");
  await figure.getByRole("button", {name: "Point suivant", exact: true}).click();
  // R1.7 : le curseur formate comme la page (`formatNombre`, réplique du filtre `nombre`) —
  // virgule française et décimales bornées. Les points de `data-chart` restent bruts.
  await expect(output).toContainText("6,40");
  const dot = figure.locator("circle").first();
  if (testInfo.project.name.startsWith("mobile")) await dot.tap(); else await dot.click();
  await expect(output).toContainText("6,10");
  await figure.getByText("Tableau des données du graphique", {exact: true}).click();
  await expect(figure.locator("tbody tr")).toHaveCount(3);
  await expect(figure.locator("table")).toContainText("mesure absente");
  expect((await new AxeBuilder({page}).analyze()).violations).toEqual([]);
  await page.screenshot({path: testInfo.outputPath("courbes.png"), fullPage: true});
  // À la borne de restitution : pas de tableau construit tant qu'il reste replié,
  // et un seul curseur permet d'atteindre la fin malgré les valeurs manquantes.
  pointCount = 2000;
  const started = Date.now();
  await page.reload();
  // Le rechargement rend un explorateur neuf : sur un profil étroit il revient replié.
  await expect(figure.locator("table")).toHaveCount(0);
  await ouvrirExplorateur(figure);
  await expect(figure.locator("table")).toHaveCount(0);
  await slider.focus(); await slider.press("End");
  await expect(output).toContainText("2000 / 2000");
  const readyMs = Date.now() - started;
  await figure.getByText("Tableau des données du graphique", {exact: true}).click();
  await expect(figure.locator("tbody tr")).toHaveCount(2000);
  const tableMs = Date.now() - started;
  await testInfo.attach("longue-periode", {body: JSON.stringify({points: pointCount, navigation_et_exploration_ms: readyMs,
    tableau_compris_ms: tableMs}), contentType: "application/json"});
  // R2.4 : la mesure devient une garde. Observé sur ce poste après correction : 1,0 s pour
  // atteindre le dernier point, 2,7 s tableau compris. Les seuils sont posés à environ dix
  // et cinq fois ces valeurs — ils ne qualifient pas la performance d'une machine, ils
  // interdisent le retour du coût quadratique (`indexOf` par point dessiné, balayage du
  // dessin entier à chaque pas du curseur), qui se compte en dizaines de secondes ici.
  expect(readyMs).toBeLessThan(10000);
  expect(tableMs).toBeLessThan(15000);
});

test("galerie : suivant, précédent, Échap et retour au contexte", async ({page}, testInfo) => {
  test.skip(testInfo.project.name === "pwa-chromium", "Parcours avec mutations et interception HTTP, hors service worker.");
  test.setTimeout(90000);
  const id = await createMother(page, "Mère galerie");
  await page.route(`**/cultures/${id}`, async route => {
    const response = await route.fetch(); let html = await response.text();
    const pictures = [1, 2].map(i => `<figure class="culture-photo"><a href="/cultures/photos/test-${i}"><img src="/cultures/photos/test-${i}" alt="Photo ${i}" width="100" height="100"></a><figcaption>Légende ${i} <a href="#bilan">Entrée du journal</a></figcaption></figure>`).join("");
    html = html.replace('<section id="photos"', `<div class="culture-grid">${pictures}</div><section id="photos"`);
    await route.fulfill({response, body: html});
  });
  await page.route("**/cultures/photos/test-*", route => route.request().url().endsWith("test-1")
    ? route.fulfill({contentType: "image/png", body: Buffer.from("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+aN1sAAAAASUVORK5CYII=", "base64")})
    : route.fulfill({status: 404, body: "Photo indisponible"}));
  await page.reload();
  const link = page.getByRole("link", {name: "Photo 1", exact: true});
  await link.click();
  const dialog = page.getByRole("dialog"); await expect(dialog).toBeVisible();
  await expect.poll(() => dialog.locator("img").evaluate(img => img.naturalWidth)).toBe(1);
  const next = dialog.getByRole("button", {name: "Photo suivante"});
  await next.focus(); await next.click();
  await expect(dialog).toContainText("Légende 2");
  await expect(dialog).toContainText("Photo indisponible");
  // R1.1 : le bouton de butée n'est jamais désactivé, il garde le focus et annonce la fin.
  await next.click();
  await expect(next).toBeEnabled(); await expect(next).toBeFocused();
  await expect(dialog).toContainText("dernière photo");
  // R3.6 b : une seule région live, et l'image cassée n'est plus affichée.
  await expect(dialog.getByRole("status")).toHaveCount(1);
  await expect(dialog.locator("img")).toBeHidden();
  // R3.6 g : cible tactile complète. Les libellés sont longs, donc la boîte rendue serait
  // large même sans règle : c'est la contrainte minimale déclarée qui est vérifiée.
  const boxes = await next.evaluate(node => [getComputedStyle(node).minWidth, getComputedStyle(node).minHeight]);
  expect(parseFloat(boxes[0])).toBeGreaterThanOrEqual(44);
  expect(parseFloat(boxes[1])).toBeGreaterThanOrEqual(44);
  await dialog.press("ArrowLeft"); await expect(dialog).toContainText("Légende 1");
  await expect(dialog.locator("img")).toBeVisible();
  // R3.6 d : un clic sur le voile ferme le dialogue et rend le focus au lien d'origine.
  await page.mouse.click(2, 2);
  await expect(dialog).toBeHidden(); await expect(link).toBeFocused();
  await link.click(); await expect(dialog).toBeVisible();
  await dialog.press("Escape"); await expect(dialog).toBeHidden(); await expect(link).toBeFocused();
});

test("explorateur : bornage sans désactivation, tap borné et tableau structuré", async ({page}, testInfo) => {
  test.skip(testInfo.project.name === "pwa-chromium", "Parcours avec interception HTTP, hors service worker.");
  test.setTimeout(90000);
  const id = await createMother(page, "Mère explorateur");
  await mesureReelle(page, id);
  await routeSolutionChart(page, 3);
  await page.goto(`/cultures/solutions?target=${id}&view=analyser`);
  const figure = page.locator(".solution-chart").first();
  await ouvrirExplorateur(figure);
  const output = figure.locator(".culture-analysis-output");
  const previous = figure.getByRole("button", {name: "Point précédent", exact: true});
  const next = figure.getByRole("button", {name: "Point suivant", exact: true});
  // R3.6 a : la sortie n'est plus une région live ; seul `aria-valuetext` annonce.
  await expect(figure.locator('.culture-analysis-output[role="status"]')).toHaveCount(0);
  // P1.3 : une région live masquée, distincte de la sortie visible, porte les gestes qui
  // n'ont pas le curseur sous le focus. Elle est muette tant qu'aucun bouton ni tap n'a servi.
  const announcer = figure.locator('.culture-chart-explorer p.visually-hidden[role="status"]');
  await expect(announcer).toHaveCount(1);
  await expect(announcer).toHaveText("");
  await expect(output).toContainText("1 / 3");
  await expect(output).toContainText("premier point");
  // R1.1 : deux activations à la butée, le bouton reste actif et garde le focus.
  await previous.focus(); await previous.click(); await previous.click();
  await expect(previous).toBeEnabled(); await expect(previous).toBeFocused();
  await expect(output).toContainText("1 / 3");
  await next.click(); await next.click(); await next.click();
  await expect(next).toBeEnabled(); await expect(next).toBeFocused();
  await expect(output).toContainText("3 / 3");
  await expect(output).toContainText("dernier point");
  // P1.3 : le bouton annonce le point atteint dans la région masquée — sans elle, le
  // déplacement était silencieux, `aria-valuetext` n'étant relu que si le curseur a le focus.
  const spoken = await output.textContent();
  await expect(announcer).toHaveText(spoken);
  // … et le curseur au clavier ne la touche pas : il annonce déjà par `aria-valuetext`, une
  // seconde région dirait deux fois le même point.
  const keyboardSlider = figure.getByRole("slider");
  await keyboardSlider.focus();
  await keyboardSlider.press("ArrowLeft");
  await expect(output).toContainText("2 / 3");
  await expect(announcer).toHaveText(spoken);
  await keyboardSlider.press("ArrowRight");
  await expect(output).toContainText("3 / 3");
  // R3.6 g : hauteur ET largeur minimales déclarées, la boîte rendue étant déjà large
  // par la longueur du libellé et ne prouverait donc rien.
  const sizes = await previous.evaluate(node => [getComputedStyle(node).minWidth, getComputedStyle(node).minHeight]);
  expect(parseFloat(sizes[0])).toBeGreaterThanOrEqual(44);
  expect(parseFloat(sizes[1])).toBeGreaterThanOrEqual(44);
  // R1.6 : un geste loin de tout point conserve la sélection courante.
  const svg = figure.locator("svg");
  await svg.click({position: {x: 4, y: 4}});
  await expect(output).toContainText("3 / 3");
  // R1.6 : à dix pixels d'un point, ce point est choisi.
  const dot = figure.locator("circle").first();
  const target = await dot.boundingBox();
  const frame = await svg.boundingBox();
  // Le geste vise le dessin, à dix pixels du point, et non des coordonnées absolues : en
  // paysage 568 × 320 la figure passe sous la barre mobile fixe, et un `mouse.click` brut y
  // atteignait le lien d'accueil de cette barre au lieu du graphique — la page changeait.
  // Une position **relative au `svg`** fait faire à Playwright le défilement et le contrôle
  // de cible : le clic touche le dessin ou échoue en le disant, jamais un autre élément.
  await svg.click({position: {x: target.x + target.width / 2 + 10 - frame.x,
    y: target.y + target.height / 2 - frame.y}});
  await expect(output).toContainText("1 / 3");
  // R4.2 : « un seul arrêt de tabulation ». Aucun point n'est un arrêt — ce qui, à 2 000
  // points, ferait 2 000 tabulations pour traverser une figure — et la zone en compte trois :
  // le curseur puis les deux boutons. La borne des trois pas suffit : un point focalisable
  // s'intercalerait forcément dans les premiers.
  await expect(figure.locator("circle[tabindex]")).toHaveCount(0);
  const slider = figure.getByRole("slider");
  await slider.focus();
  const stops = [];
  for (let step = 0; step < 3; step += 1) {
    await page.keyboard.press("Tab");
    stops.push(await page.evaluate(() => {
      const node = document.activeElement;
      return `${node.tagName.toLowerCase()}:${node.textContent.trim().slice(0, 20)}`;
    }));
  }
  expect(stops.filter(stop => stop.startsWith("circle"))).toEqual([]);
  expect(stops.slice(0, 2)).toEqual(["button:Point précédent", "button:Point suivant"]);
  // R4.2 : la sélection est conservée au redessin. Le changement de largeur déclenche le
  // `ResizeObserver` du dessin, donc de nouveaux nœuds : c'est l'index de donnée, pas le
  // nœud, qui doit survivre — et le texte du curseur ne doit pas être réécrit.
  const announced = await output.textContent();
  const chosen = await figure.locator("circle.culture-selected-point").getAttribute("data-analysis-index");
  const viewport = page.viewportSize();
  await page.setViewportSize({width: viewport.width - 60, height: viewport.height});
  await expect(figure.locator("circle.culture-selected-point")).toHaveCount(1);
  await expect(figure.locator("circle.culture-selected-point")).toHaveAttribute("data-analysis-index", chosen);
  await expect(output).toHaveText(announced);
  await page.setViewportSize(viewport);
  // R3.2 : tableau de données, pas une liste numérotée ; une lacune n'est jamais 0.
  await figure.getByText("Tableau des données du graphique", {exact: true}).click();
  const table = figure.locator("table");
  await expect(table.locator("thead th")).toHaveCount(8);
  await expect(table.locator('thead th[scope="col"]')).toHaveCount(8);
  const gapRow = table.locator("tbody tr").nth(1);
  await expect(gapRow.locator("td").nth(1)).toHaveText("mesure absente");
  await expect(gapRow.locator("td").last()).toHaveText("oui");
  expect((await new AxeBuilder({page}).analyze()).violations).toEqual([]);
});

test("courbe climatique : lacune sélectionnée visible et dessin sans l’explorateur", async ({page}, testInfo) => {
  test.skip(testInfo.project.name === "pwa-chromium", "Parcours avec interception HTTP, hors service worker.");
  test.setTimeout(90000);
  const id = await createMother(page, "Mère climat");
  const climate = [0, 1, 2].map(i => ({sensor: "temperature", label: "Température", unit: "°C",
    at: `2026-08-0${i + 1} 00:00`, hour: 1754006400 + i * 3600, mean: i === 1 ? null : 21 + i,
    minimum: i === 1 ? null : 20 + i, maximum: i === 1 ? null : 22 + i,
    valid_count: i === 1 ? 0 : 60, span_hours: 1, coverage: i === 1 ? 0 : 1, missing: i === 1}));
  await page.route(`**/cultures/cycles?subject=${id}*`, async route => {
    const response = await route.fetch();
    let html = await response.text();
    html = html.replace(/data-climate-chart="[^"]*"/,
      `data-climate-chart="${JSON.stringify(climate).replaceAll('"', '&quot;')}"`);
    await route.fulfill({response, body: html});
  });
  // R2.6 : le panneau « Comparer » de /cultures/cycles est servi mais `hidden` tant que
  // `view=comparer` n'est pas demandé — hors de l'arbre d'accessibilité sans lui.
  await page.goto(`/cultures/cycles?subject=${id}&view=comparer`);
  const figure = page.locator(".solution-chart").first();
  await ouvrirExplorateur(figure);
  const gap = figure.locator("path.climate-gap");
  await expect(gap).toHaveCount(1);
  const plain = await gap.evaluate(node => getComputedStyle(node).strokeWidth);
  // R1.3 : le curseur atteint la lacune et le tracé change réellement d'aspect.
  const slider = figure.getByRole("slider");
  // R4.2 : la courbe climatique a bien son explorateur, et un seul. L'annonce passe par
  // `aria-valuetext` — la sortie n'étant pas une région live, c'est le seul canal.
  await expect(slider).toHaveCount(1);
  await slider.focus(); await slider.press("ArrowRight");
  await expect(figure.locator(".culture-analysis-output")).toContainText("Aucune valeur fiable");
  await expect(slider).toHaveAttribute("aria-valuetext", /2 \/ 3 · .*Aucune valeur fiable/);
  await expect(gap).toHaveClass(/culture-selected-point/);
  const marked = await gap.evaluate(node => getComputedStyle(node).strokeWidth);
  expect(marked).not.toBe(plain);
  // Le rayon d'un cercle est posé en attribut, pas par la propriété CSS `r`.
  await slider.press("ArrowLeft");
  await expect(figure.locator("circle.culture-selected-point")).toHaveAttribute("r", "5");
  // R1.4 : sans l'explorateur, les courbes sont dessinées quand même.
  await page.route("**/culture_analysis.js*", route => route.fulfill({status: 404, body: ""}));
  await page.reload();
  await expect(figure.locator("circle")).toHaveCount(2);
  await expect(figure.locator("path.climate-gap")).toHaveCount(1);
  await expect(page.locator(".culture-chart-explorer")).toHaveCount(0);
});

// Lot C de la remédiation UI 4 : retour de focus du lien de contexte (R1.5), clé de lecture
// et synthèse des courbes de solutions (R3.1, R3.3), bilan des cartes d'archives (R3.5).

const PIXEL = "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+aN1sAAAAASUVORK5CYII=";

test("galerie : le lien de contexte focalise l’ancre, jamais la vignette", async ({page}, testInfo) => {
  test.skip(testInfo.project.name === "pwa-chromium", "Parcours avec mutations et interception HTTP, hors service worker.");
  test.setTimeout(90000);
  const id = await createMother(page, "Mère contexte");
  const detail = await (await page.request.get(`/api/v1/cultures/${id}`)).json();
  const eventId = detail.events[0].id;
  // La légende porte le lien que le gabarit rend désormais : c'est lui que la galerie reprend.
  await page.route(`**/cultures/${id}`, async route => {
    const response = await route.fetch();
    let html = await response.text();
    // Deux destinations : une ancre focalisable (`#event-…`) et une section qui ne l'est pas.
    const picture = (name, href) => `<figure class="culture-photo"><a href="/cultures/photos/test-1"><img src="/cultures/photos/test-1" alt="${name}" width="100" height="100"></a><figcaption>Légende · <a href="${href}">Ouvrir l’entrée liée</a></figcaption></figure>`;
    const figures = picture("Photo contexte", `#event-${eventId}`) + picture("Photo section", "#photos");
    html = html.replace('<section id="photos"', `<div class="culture-grid">${figures}</div><section id="photos"`);
    await route.fulfill({response, body: html});
  });
  await page.route("**/cultures/photos/test-*", route => route.fulfill({contentType: "image/png", body: Buffer.from(PIXEL, "base64")}));
  await page.reload();
  const link = page.getByRole("link", {name: "Photo contexte", exact: true});
  await link.click();
  const dialog = page.getByRole("dialog");
  await expect(dialog).toBeVisible();
  const context = dialog.getByRole("link", {name: "Ouvrir l’entrée liée"});
  // `href` reflété par le DOM : la valeur est résolue en URL absolue de la page courante.
  await expect(context).toHaveAttribute("href", new RegExp(`#event-${eventId}$`));
  // R1.5 a : la fermeture par le lien ne rend pas le focus à la vignette ; c'est l'ancre
  // `tabindex="-1"` visée qui le reçoit, l'élément focalisé étant la confirmation.
  await context.click();
  await expect(dialog).toBeHidden();
  await expect(page.locator(`#event-${eventId}`)).toBeFocused();
  await expect(link).not.toBeFocused();
  // Destination non focalisable : la navigation par fragment n'a personne à focaliser, et
  // c'est là que la re-focalisation de la vignette était visible — elle ramenait la lecture
  // à la photo au lieu de la laisser à l'endroit atteint.
  const other = page.getByRole("link", {name: "Photo section", exact: true});
  await other.click();
  await expect(dialog).toBeVisible();
  await dialog.getByRole("link", {name: "Ouvrir l’entrée liée"}).click();
  await expect(dialog).toBeHidden();
  await expect(other).not.toBeFocused();
  // La fermeture par Échap garde l'autre convention : retour à la vignette.
  await link.click();
  await expect(dialog).toBeVisible();
  await dialog.press("Escape");
  await expect(dialog).toBeHidden();
  await expect(link).toBeFocused();
});

test("courbes de solutions : légende par source et synthèse textuelle", async ({page}, testInfo) => {
  test.skip(testInfo.project.name === "pwa-chromium", "Parcours avec mutations, hors service worker.");
  test.setTimeout(90000);
  const id = await createMother(page, "Mère légende");
  const csrf = await page.locator('meta[name="csrf-token"]').getAttribute("content");
  const entry = data => page.request.post("/api/v1/cultures/solutions",
    {headers: {"X-CSRF-Token": csrf}, data: {operation: "entry",
      request_id: require("node:crypto").randomUUID(), ...data}});
  // Un relevé de réservoir suppose la solution présente : le renouvellement ouvre la période.
  expect((await entry({kind: "renewal", reservoir_id: "reservoir_2", effective_at: "2026-08-01",
    volume_l: 20})).ok()).toBe(true);
  expect((await entry({kind: "reading", reservoir_id: "reservoir_2", effective_at: "2026-08-02",
    ph: 6.1})).ok()).toBe(true);
  expect((await entry({kind: "reading", targets: [id], effective_at: "2026-08-03", ph: 6.5})).ok()).toBe(true);
  // Une troisième source qui ne mesure que l'EC : elle n'a aucun point sur la courbe de pH,
  // sa légende ne doit donc pas la nommer.
  const conductivity = await createMother(page, "Mère EC seule");
  expect((await entry({kind: "reading", targets: [conductivity], effective_at: "2026-08-04",
    ec: 1.8})).ok()).toBe(true);
  await page.goto("/cultures/solutions?view=analyser");
  const figure = page.locator(".solution-chart").first();
  await ouvrirExplorateur(figure);
  // R3.3 : la synthèse vient du serveur ; une absence reste une absence, jamais un zéro.
  await expect(figure.locator("#resume-ph")).toContainText("2 mesures");
  await expect(figure.locator("#resume-ph")).toContainText("minimum 6.10, moyenne 6.30, maximum 6.50");
  const ec = page.locator(".solution-chart").nth(1);
  await expect(ec.locator("#resume-ec")).toContainText("1 mesure");
  await expect(ec.locator("#resume-ec")).not.toContainText("0.00");
  // Les points sans EC restent des lacunes ; aucune moyenne n'est inventée à leur place.
  await expect(ec.locator("#resume-ec")).toContainText("3 lacunes");
  await expect(figure.locator("svg")).toHaveAttribute("aria-describedby", "resume-ph legende-ph");
  // R2.3 : la légende visible garde ce sans quoi la figure ne se lit pas — la grandeur,
  // la bande de plage cible et une entrée par source de **cette** mesure (R3.1). Le
  // vocabulaire des encodages passe dans « Légende complète », un repli qu'on consulte
  // une fois. Ce repli n'est pas désigné par l'`aria-describedby` : le contenu d'un
  // `<details>` fermé n'est pas exposé de la même façon par tous les moteurs.
  const legend = figure.locator("#legende-ph");
  await expect(legend).toBeVisible();
  await expect(legend).toContainText("Plage cible");
  const complete = figure.locator("details.chart-full-legend");
  await expect(complete.locator("summary")).toHaveText("Légende complète");
  await expect(complete).not.toHaveAttribute("open", "");
  await complete.locator("summary").click();
  await expect(complete).toContainText("Bande : plage cible résolue à la date des mesures.");
  await expect(complete).toContainText("Barre verticale : minimum et maximum du jour.");
  await expect(legend).toContainText(/Réservoir de l’espace 2 · solution \w{8}/);
  await expect(legend).toContainText("Mère légende · solution manuelle");
  // Chaque figure a la légende de sa mesure : une source qui n'a que de l'EC n'est pas nommée
  // sous la courbe de pH, où elle ne dessine aucun point.
  await expect(legend).not.toContainText("Mère EC seule");
  const legendEc = ec.locator("#legende-ec");
  await expect(legendEc).toContainText("Mère EC seule · solution manuelle");
  await expect(legendEc).not.toContainText("Mère légende");
  await expect(legendEc).not.toContainText("Réservoir de l’espace 2");
  // Deux sources, deux classes distinctes : jamais la seule couleur, la forme change aussi.
  await expect(figure.locator("circle.solution-source-0")).toHaveCount(1);
  await expect(figure.locator("circle.solution-source-1")).toHaveCount(1);
  const shapes = await figure.locator("circle").evaluateAll(nodes => nodes.map(node => {
    const style = getComputedStyle(node);
    return [style.fill, style.strokeDasharray, style.strokeWidth].join("|");
  }));
  expect(new Set(shapes).size).toBe(2);
  // Le texte du curseur nomme la même source que la légende, et l'identifiant technique de
  // la cible (`reservoir_2`) n'apparaît plus nulle part : le curseur, la légende et la
  // colonne « Cible ou capteur » du tableau disent le même nom.
  const slider = figure.getByRole("slider");
  await slider.focus();
  const cursor = figure.locator(".culture-analysis-output");
  await expect(cursor).toContainText(/Réservoir de l’espace 2 · solution \w{8}/);
  await expect(cursor).not.toContainText("reservoir_2");
  await figure.getByText("Tableau des données du graphique", {exact: true}).click();
  const source = figure.locator("tbody tr").first().locator("td").nth(3);
  await expect(source).toHaveText("Réservoir de l’espace 2");
  await figure.getByText("Tableau des données du graphique", {exact: true}).click();
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
  expect((await new AxeBuilder({page}).analyze()).violations).toEqual([]);
  await page.screenshot({path: testInfo.outputPath("legende-courbes.png"), fullPage: true});
  await page.evaluate(() => document.documentElement.setAttribute("data-theme", "daylight"));
  expect((await new AxeBuilder({page}).analyze()).violations).toEqual([]);
  await page.screenshot({path: testInfo.outputPath("legende-courbes-plein-jour.png"), fullPage: true});
});

test("archives : occupation persistante signalée et durées par stade", async ({page}, testInfo) => {
  test.skip(testInfo.project.name === "pwa-chromium", "Parcours avec mutations, hors service worker.");
  test.setTimeout(90000);
  await page.goto("/cultures");
  const csrf = await page.locator('meta[name="csrf-token"]').getAttribute("content");
  const post = data => page.request.post("/api/v1/cultures", {headers: {"X-CSRF-Token": csrf}, data});
  let saved = await (await post({request_id: require("node:crypto").randomUUID(), operation: "create",
    kind: "lot", name: "Lot archivé", origin_at: "2026-08-01", space_at: "2026-08-01",
    stage_at: "2026-08-01", stage: "floraison", space: "space_2",
    origins: [{label: "Semences A", count: 8}]})).json();
  saved = await (await post({request_id: require("node:crypto").randomUUID(), operation: "event",
    subject_id: saved.subject_id, version: saved.version, kind: "harvest", effective_at: "2026-08-20",
    payload: {drying_at: "2026-08-20", drying_precision: "date"}})).json();
  // Séchage terminé sans libération : le lot est archivé et tient toujours l'espace 2.
  const finished = await post({request_id: require("node:crypto").randomUUID(), operation: "event",
    subject_id: saved.subject_id, version: saved.version, kind: "finish", effective_at: "2026-09-01",
    payload: {release: false, weight_g: 42, lessons: "Séchage lent"}});
  expect(finished.ok()).toBe(true);
  await page.goto("/cultures?archives=1");
  const card = page.locator(".culture-grid .card").filter({hasText: "Lot archivé"});
  await expect(card).toContainText("Espace encore occupé · à libérer : Espace 2");
  await expect(card).toContainText("Durées par stade : Floraison 19 j, Séchage 12 j");
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
  expect((await new AxeBuilder({page}).analyze()).violations).toEqual([]);
  await page.screenshot({path: testInfo.outputPath("archives.png"), fullPage: true});
});

// R4.2 : le sélecteur de comparaison en navigateur — plafond de quatre visible avant l'envoi,
// filtre local qui masque sans recharger, et pagination des choix. Le carnet est semé par
// l'API : quarante-cinq saisies au formulaire ne mesureraient que la vitesse du formulaire,
// et c'est la restitution qui est en cause ici.
test("sélecteur de comparaison : plafond de quatre, filtre local et pagination des choix", async ({page}, testInfo) => {
  test.skip(testInfo.project.name === "pwa-chromium", "Parcours avec mutations, hors service worker.");
  test.setTimeout(180000);
  await page.goto("/cultures");
  const csrf = await page.locator('meta[name="csrf-token"]').getAttribute("content");
  const create = name => page.request.post("/api/v1/cultures", {headers: {"X-CSRF-Token": csrf},
    data: {request_id: require("node:crypto").randomUUID(), operation: "create", kind: "mother",
      name, origin_at: "2026-08-01", space_at: "2026-08-01", stage_at: "2026-08-01",
      stage: "maintien", origins: []}});
  // « Épinard géant » se classe avant les « Zone … » par la clé normalisée du serveur : il
  // reste sur la première page, celle où le filtre local est éprouvé. Quarante-cinq cultures
  // font deux pages de quarante, la seconde en comptant cinq — assez pour cocher quatre
  // cases et en trouver une cinquième refusée.
  const names = ["Épinard géant"].concat(
    Array.from({length: 44}, (_, i) => `Zone ${String(i + 1).padStart(2, "0")}`));
  for (const name of names) expect((await create(name)).ok()).toBe(true);

  await page.goto("/cultures/cycles?view=comparer#comparaison");
  const zone = page.locator("[data-comparison-selection]");
  const boxes = zone.locator('input[name="subject"]');
  const labels = zone.locator("fieldset label");
  await expect(boxes).toHaveCount(40);
  await expect(labels.first()).toContainText("Épinard géant");

  // R4.2 : le filtre client masque réellement des libellés. Sans cette assertion, un filtre
  // qui ne ferait rien laissait le scénario vert.
  const filter = page.getByLabel("Filtrer les choix affichés");
  const before = page.url();
  await filter.fill("inconnue");
  await expect(zone.locator("fieldset label[hidden]")).toHaveCount(40);
  // La clé du navigateur est celle du serveur : « epinard » trouve « Épinard ».
  await filter.fill("epinard");
  await expect(zone.locator("fieldset label[hidden]")).toHaveCount(39);
  await expect(labels.filter({hasText: "Épinard géant"}).first()).toBeVisible();
  // Le champ de filtre n'appartient pas au formulaire : Entrée n'envoie rien et ne navigue
  // pas. Une navigation reperdrait le filtre, qui n'a pas de `name`.
  await filter.press("Enter");
  await expect(zone.locator("fieldset label[hidden]")).toHaveCount(39);
  expect(page.url()).toBe(before);
  await filter.fill("");
  await expect(zone.locator("fieldset label[hidden]")).toHaveCount(0);

  // R1.2 : seconde page des choix, cinq résultats, classés par nom normalisé.
  await page.getByRole("link", {name: "Choix suivants"}).click();
  await expect(page).toHaveURL(/selection_offset=40/);
  await expect(boxes).toHaveCount(5);
  await expect(labels.first()).toContainText("Zone 40");

  // R4.2 : le plafond de quatre est tenu côté client, et la case refusée dit pourquoi.
  for (let index = 0; index < 4; index += 1) await boxes.nth(index).check();
  await expect(zone.locator("output")).toHaveText("4 / 4 cultures sélectionnées");
  // P1.2 : `aria-disabled` et non `disabled`. Une case `disabled` sort de l'ordre de
  // tabulation : son `aria-describedby` — le compte et la phrase qui motive le plafond —
  // n'était jamais annoncé, et le refus restait muet. La case reste donc focalisable et
  // active ; c'est le geste qui est refusé.
  await expect(boxes.nth(4)).toHaveAttribute("aria-disabled", "true");
  // Playwright lit `aria-disabled` comme une désactivation (`toBeEnabled`, actionnabilité
  // du clic) : la preuve porte donc sur la propriété DOM `disabled`, seule à retirer une
  // case du parcours clavier, et le clic contourne la vérification d'actionnabilité.
  await expect(boxes.nth(4)).toHaveJSProperty("disabled", false);
  await boxes.nth(4).focus();
  await expect(boxes.nth(4)).toBeFocused();
  // Cocher la cinquième la décoche aussitôt : le compte ne bouge pas. `click` et non
  // `check`, qui exigerait que la case reste cochée — c'est justement ce qui est refusé.
  await boxes.nth(4).click({force: true});
  await expect(boxes.nth(4)).not.toBeChecked();
  await expect(zone.locator("output")).toHaveText("4 / 4 cultures sélectionnées");
  await expect(zone.locator('input[name="subject"]:checked')).toHaveCount(4);
  const described = await boxes.nth(4).getAttribute("aria-describedby");
  expect(described.split(" ")).toHaveLength(2);
  const targets = await page.evaluate(ids => ids.split(" ").map(id => {
    const node = document.getElementById(id);
    return node && [node.tagName.toLowerCase(), node.hasAttribute("data-comparison-cap")];
  }), described);
  // Le compte, puis la phrase qui motive le plafond : une case désactivée sans explication
  // serait un refus muet.
  expect(targets).toEqual([["output", false], ["p", true]]);
  // Le plafond n'est jamais définitif : libérer une place lève le refus de la cinquième.
  await boxes.nth(0).uncheck();
  await expect(boxes.nth(4)).not.toHaveAttribute("aria-disabled", "true");
  await boxes.nth(0).check();
  await expect(boxes.nth(4)).toHaveAttribute("aria-disabled", "true");

  // R1.2 : cocher depuis la page 2 ne renvoie pas page 1.
  await zone.getByRole("button", {name: "Afficher les cycles"}).click();
  await expect(page).toHaveURL(/selection_offset=40/);
  await expect(boxes).toHaveCount(5);
  await expect(zone.locator('input[name="subject"]:checked')).toHaveCount(4);
  await expect(page.locator(".culture-comparison thead th")).toHaveCount(5);
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
  expect((await new AxeBuilder({page}).analyze()).violations).toEqual([]);
  await page.screenshot({path: testInfo.outputPath("selecteur-comparaison.png"), fullPage: true});
});

// R1.7 : la fixture nommée par la fiche. `1.4 + 0.05` vaut exactement 1,45 en binaire64 ;
// la décomposition qui produit réellement l'artefact est `1.1 + 0.35` = 1.4500000000000002.
// C'est cette valeur-là que la page ne doit jamais montrer, et que l'API doit rendre intacte.
test("R1.7 : la page affiche 1,45 quand la valeur persistée reste 1.4500000000000002", async ({page}, testInfo) => {
  test.skip(testInfo.project.name === "pwa-chromium", "Parcours mutateur exercé hors service worker.");
  test.setTimeout(90000);
  const mesure = 1.1 + 0.35;
  expect(String(mesure)).toBe("1.4500000000000002");

  await page.goto("/cultures/solutions?target=reservoir_2&view=saisir");
  const csrf = await page.locator('meta[name="csrf-token"]').getAttribute("content");
  const post = data => page.request.post("/api/v1/cultures/solutions",
    {headers: {"X-CSRF-Token": csrf}, data: {...data, request_id: require("node:crypto").randomUUID()}});
  // Une solution doit être présente avant qu'un relevé de réservoir ait un sens.
  expect((await post({operation: "entry", kind: "renewal", reservoir_id: "reservoir_2",
    effective_at: "2026-08-01", volume_l: 20})).ok()).toBeTruthy();
  expect((await post({operation: "entry", kind: "reading", reservoir_id: "reservoir_2",
    effective_at: "2026-08-02", ph: 6.1, ec: mesure})).ok()).toBeTruthy();

  await page.goto("/cultures/solutions?target=reservoir_2&view=releves");
  const ligne = page.locator(".solution-journal").first().locator(".solution-entry-line");
  await expect(ligne).toContainText("EC 1,45 mS/cm");
  await expect(ligne).not.toContainText("1.4500000000000002");

  // L'API, elle, ne formate rien : l'arrondi est une affaire de présentation seule.
  const lu = await (await page.request.get("/api/v1/cultures/solutions")).json();
  const releve = lu.items.find(item => item.kind === "reading");
  expect(releve.ec).toBe(mesure);
  // Et le champ de correction repropose la valeur brute, pas la valeur affichée.
  const article = page.locator(".solution-journal").first();
  await article.locator(".solution-entry-details > summary").click();
  await article.getByText("Corriger cette saisie", {exact: true}).click();
  await expect(page.locator('.solution-journal [data-solution-entry] [name="ec"]').first())
    .toHaveValue(String(mesure));
});
