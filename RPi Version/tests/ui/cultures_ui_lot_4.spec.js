"use strict";
const {test, expect, createMother, AxeBuilder} = require("./culture_fixtures");

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
  await slider.focus(); await slider.press("ArrowRight");
  await expect(figure.getByRole("status")).toContainText("mesure absente");
  await figure.getByRole("button", {name: "Point suivant", exact: true}).click();
  await expect(figure.getByRole("status")).toContainText("6.4");
  const dot = figure.locator("circle").first();
  if (testInfo.project.name.startsWith("mobile")) await dot.tap(); else await dot.click();
  await expect(figure.getByRole("status")).toContainText("6.1");
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
  await expect(figure.getByRole("status")).toContainText("2000 / 2000");
  const readyMs = Date.now() - started;
  await figure.getByText("Tableau des données du graphique", {exact: true}).click();
  await expect(figure.locator("tbody tr")).toHaveCount(2000);
  await testInfo.attach("longue-periode", {body: JSON.stringify({points: pointCount, navigation_et_exploration_ms: readyMs,
    tableau_compris_ms: Date.now() - started}), contentType: "application/json"});

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
  await dialog.getByRole("button", {name: "Photo suivante"}).click();
  await expect(dialog).toContainText("Légende 2");
  await expect(dialog).toContainText("Photo indisponible");
  await dialog.press("ArrowLeft"); await expect(dialog).toContainText("Légende 1");
  await dialog.press("Escape"); await expect(dialog).toBeHidden(); await expect(link).toBeFocused();
});
