"use strict";
const {test, expect, createMother, AxeBuilder} = require("./culture_fixtures");

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
  await page.goto(`/cultures/cycles?subject=${first}&subject=${second}#comparaison`);
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
  await page.goto(`/cultures/solutions?target=${id}`);
  // Données de consultation représentatives, injectées avant l'exécution des scripts.
  let pointCount = 3;
  await page.route("**/cultures/solutions?target=*", async route => {
    const response = await route.fetch(); let html = await response.text();
    const points = Array.from({length: pointCount}, (_, i) => ({ph: [6.1, null, 6.4][i % 3], ec: null, at: new Date(Date.UTC(2024, 0, 1) + i * 86400000).toISOString(), label: "pH", target: "Mère courbes", period: null, annotations: []}));
    html = html.replace(/data-chart="[^"]*"/, `data-chart="${JSON.stringify(points).replaceAll('"', '&quot;')}"`);
    await route.fulfill({response, body: html});
  });
  await page.reload();
  const figure = page.locator(".solution-chart").first(), slider = figure.getByRole("slider");
  const output = figure.locator(".culture-analysis-output");
  await slider.focus(); await slider.press("ArrowRight");
  await expect(output).toContainText("mesure absente");
  await figure.getByRole("button", {name: "Point suivant", exact: true}).click();
  await expect(output).toContainText("6.4");
  const dot = figure.locator("circle").first();
  if (testInfo.project.name.startsWith("mobile")) await dot.tap(); else await dot.click();
  await expect(output).toContainText("6.1");
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
  await routeSolutionChart(page, 3);
  await page.goto(`/cultures/solutions?target=${id}`);
  const figure = page.locator(".solution-chart").first();
  const output = figure.locator(".culture-analysis-output");
  const previous = figure.getByRole("button", {name: "Point précédent", exact: true});
  const next = figure.getByRole("button", {name: "Point suivant", exact: true});
  // R3.6 a : la sortie n'est plus une région live ; seul `aria-valuetext` annonce.
  await expect(figure.locator('.culture-analysis-output[role="status"]')).toHaveCount(0);
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
  await page.mouse.click(target.x + target.width / 2 + 10, target.y + target.height / 2);
  await expect(output).toContainText("1 / 3");
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
  await page.goto(`/cultures/cycles?subject=${id}`);
  const figure = page.locator(".solution-chart").first();
  const gap = figure.locator("path.climate-gap");
  await expect(gap).toHaveCount(1);
  const plain = await gap.evaluate(node => getComputedStyle(node).strokeWidth);
  // R1.3 : le curseur atteint la lacune et le tracé change réellement d'aspect.
  const slider = figure.getByRole("slider");
  await slider.focus(); await slider.press("ArrowRight");
  await expect(figure.locator(".culture-analysis-output")).toContainText("Aucune valeur fiable");
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
