const {test, expect} = require("./serveurs");
const AxeBuilder = require("@axe-core/playwright").default;
const fs = require("fs");
const path = require("path");
const {historyFixture} = require("./fixtures");
const {pour} = require("./profils");

// Acceptation des fiches R2.2 (exploration tactile de l'historique), R2.3 (légende courte puis
// « Légende complète ») et R5.2 (séries distinguables sans la couleur).
//
// La fixture de `tests/ui_server.py` déclare l'historique **indisponible** — le serveur de test
// n'ouvre aucune base opérateur. La page rend donc son état vide, avec son bouton « Réessayer » :
// on interpose la réponse de `/api/v1/history` (`historyFixture`, déjà partagée avec
// `dashboard.spec.js` et `visual.spec.js`) et on déclenche ce bouton. Aucune mutation, aucune
// écriture serveur : la page d'historique est en lecture seule.
const prepare = async (page) => {
  await page.route("**/api/v1/history?hours=24", (route) => route.fulfill({
    contentType: "application/json", body: JSON.stringify(historyFixture()),
  }));
  await page.goto("/history");
  await page.evaluate(() => { document.getElementById("tendances").dataset.historyAvailable = "true"; });
  await page.getByRole("button", {name: "Réessayer"}).click();
  await expect(page.locator("#history-metrics-grid")).toContainText("Température");
};

const detailTitle = (page) => page.locator("#history-selection-output .ui-chart-detail p").first();

// `touchscreen.tap` et `mouse.move` visent des coordonnées **de fenêtre**, alors que
// `boundingBox()` peut situer le graphique bien plus bas dans la page (≈ 1 585 px sur téléphone).
// Sans ce défilement préalable, le geste tombe hors de la fenêtre et n'émet aucun événement.
const chartBox = async (page, selector) => {
  const canvas = page.locator(selector);
  await canvas.scrollIntoViewIfNeeded();
  return canvas.boundingBox();
};

// Emplacement de la région vivante : classe du parent et rang dans ce parent. Un `<output>`
// `aria-live` retiré puis réinséré perd ou double son annonce — la fiche exige qu'il ne bouge pas.
const outputPlace = (page) => page.evaluate(() => {
  const node = document.getElementById("history-selection-output");
  return {parent: node.parentElement.className, index: [...node.parentElement.children].indexOf(node)};
});

test("le point choisi survit au redimensionnement et garde le même horodatage", pour("Acceptation tactile de la fiche R2.2.", "mobile-chromium"), async ({page}, testInfo) => {
  await prepare(page);
  const canvas = page.locator("#temperature-chart");
  await expect(canvas).toBeVisible();
  await expect(detailTitle(page)).toHaveText("Aucun point sélectionné");

  const box = await chartBox(page, "#temperature-chart");
  await page.touchscreen.tap(box.x + box.width * 0.62, box.y + box.height / 2);
  await expect(detailTitle(page)).toContainText("Point sélectionné :");
  const chosen = await detailTitle(page).textContent();
  // La fiche porte bien des couples `dt`/`dd`, et non une phrase à plat.
  await expect(page.locator("#history-selection-output .ui-chart-detail dl dt").first()).toBeVisible();

  // Le redessin est différé de 150 ms : on attend que le canvas ait réellement été remesuré,
  // sans quoi l'assertion passerait avant le redimensionnement et ne prouverait rien.
  const bitmapWidth = () => page.locator("#temperature-chart").evaluate((node) => node.width);
  const viewport = page.viewportSize();
  const before = await bitmapWidth();
  await page.setViewportSize({width: 360, height: viewport.height});
  await expect.poll(bitmapWidth).not.toBe(before);
  await expect(detailTitle(page)).toHaveText(chosen);

  const narrow = await bitmapWidth();
  await page.setViewportSize({width: 412, height: viewport.height});
  await expect.poll(bitmapWidth).not.toBe(narrow);
  await expect(detailTitle(page)).toHaveText(chosen);
});

test("le défilement vertical reste possible pendant un toucher sur le graphique", pour("Garde-fou tactile de la fiche R2.2.", "mobile-chromium"), async ({page}, testInfo) => {
  await prepare(page);
  const touchAction = await page.locator("#temperature-chart").evaluate((node) => getComputedStyle(node).touchAction);
  expect(touchAction).toBe("pan-y");
});

test("la région vivante du détail n’est jamais déplacée dans le DOM", pour("Acceptation de la fiche R2.2.", "mobile-chromium"), async ({page}, testInfo) => {
  await prepare(page);
  const before = await outputPlace(page);
  const box = await chartBox(page, "#temperature-chart");
  await page.touchscreen.tap(box.x + box.width * 0.4, box.y + box.height / 2);
  await expect(detailTitle(page)).toContainText("Point sélectionné :");
  expect(await outputPlace(page)).toEqual(before);

  await page.locator("[data-history-view-picker]").selectOption("humidity");
  await expect(page.locator(".chart-card:has(#humidity-chart)")).toBeVisible();
  expect(await outputPlace(page)).toEqual(before);
});

test("le sélecteur d’indicateur ne laisse qu’un tracé à la fois sous 700 px", pour("Comportement propre au téléphone (fiche R2.2).", "mobile-chromium"), async ({page}, testInfo) => {
  await prepare(page);
  expect(page.viewportSize().width).toBeLessThan(700);
  const picker = page.locator("[data-history-view-picker]");
  await expect(picker).toBeVisible();
  // L'option par défaut est déclarée dans le gabarit : plus de repli inatteignable côté script.
  await expect(picker).toHaveValue("temperature");
  await expect(page.locator(".chart-card:has(#temperature-chart)")).toBeVisible();
  await expect(page.locator(".chart-card:has(#humidity-chart)")).toBeHidden();
  await expect(page.locator(".chart-card:has(#automation-chart)")).toBeHidden();

  await picker.selectOption("humidity");
  await expect(page.locator(".chart-card:has(#humidity-chart)")).toBeVisible();
  await expect(page.locator(".chart-card:has(#temperature-chart)")).toBeHidden();

  await picker.selectOption("all");
  await expect(page.locator(".chart-card:has(#temperature-chart)")).toBeVisible();
  await expect(page.locator(".chart-card:has(#humidity-chart)")).toBeVisible();
});

test("les indicateurs résumés précèdent les tracés et n’inventent aucune valeur", pour("Acceptation de la fiche R2.2.", "mobile-chromium"), async ({page}, testInfo) => {
  await prepare(page);
  const grid = page.locator("#history-metrics-grid");
  await expect(grid.locator(".history-insight")).toHaveCount(3);
  await expect(grid).toContainText("Température");
  await expect(grid).toContainText("Humidité");
  await expect(grid).toContainText("Part de lacunes");

  // Chaque valeur est un nombre présenté à la convention du dépôt (virgule, sans séparateur de
  // milliers) ou l'absence explicite « — » : jamais un zéro de remplissage.
  const values = await grid.locator("strong.num").allTextContents();
  expect(values).toHaveLength(3);
  values.forEach((value) => expect(value).toMatch(/^(—|[\d,]+( \/ [\d,]+)*( ?(°C|%))?)$/));

  // Les indicateurs sont bien **avant** les tracés dans l'ordre du document.
  const order = await page.evaluate(() => {
    const metrics = document.getElementById("history-metrics-grid");
    const grid = document.querySelector(".history-grid");
    return metrics.compareDocumentPosition(grid) & Node.DOCUMENT_POSITION_FOLLOWING ? "avant" : "après";
  });
  expect(order).toBe("avant");
});

test("la légende reste courte et renvoie ses sources dans « Légende complète »", pour("Acceptation de la fiche R2.3.", "mobile-chromium"), async ({page}, testInfo) => {
  await prepare(page);
  const short = page.locator("#temperature-legend");
  await expect(short).toContainText("Température air · °C");
  // Ni période, ni source, ni consigne dans la légende courte.
  await expect(short).not.toContainText("Période affichée");
  await expect(short).not.toContainText("consigne");

  const details = page.locator(".chart-card:has(#temperature-chart) details.chart-full-legend");
  await expect(details.locator("summary")).toHaveText("Légende complète");
  await details.locator("summary").click();
  const full = page.locator("#temperature-legend-full");
  await expect(full).toContainText("Période affichée");
  await expect(full).toContainText("Source « Température air » : capteur BME280T");
  await expect(full).toContainText("consigne d’arrêt du chauffage");

  // La pastille de la légende est dessinée avec le même motif et le même marqueur que le tracé.
  await expect(short.locator("button[data-series-key] canvas.chart-legend-swatch")).toHaveCount(1);
  await expect(short.locator("button[data-series-key]")).toHaveAttribute("aria-label", /marqueur (disque|carré|triangle|losange|croix|hexagone)/);
});

test("un survol n’arme aucune annonce et ne devient pas une sélection", pour("Le survol n'existe qu'au pointeur fin.", "desktop-chromium"), async ({page}, testInfo) => {
  await prepare(page);
  const canvas = page.locator("#temperature-chart");
  const box = await chartBox(page, "#temperature-chart");
  // Le survol déplace le curseur et l'infobulle…
  await page.mouse.move(box.x + box.width * 0.3, box.y + box.height / 2);
  await page.mouse.move(box.x + box.width * 0.7, box.y + box.height / 2);
  await expect(page.locator("#history-tooltip")).toBeVisible();
  // …mais la fiche de la région vivante reste vide : rien n'a été confirmé.
  await expect(detailTitle(page)).toHaveText("Aucun point sélectionné");

  // Et le survol ne doit pas non plus **armer** une annonce que le redessin déclencherait.
  // Un redimensionnement rejoue la fiche : après un simple survol, elle doit rester vide.
  // (Le sélecteur d'indicateur est en `display:none` au-delà de 700 px, d'où le redessin par
  //  redimensionnement plutôt que par changement de vue.)
  await page.mouse.move(0, 0);
  const bitmap = () => canvas.evaluate((node) => node.width);
  const before = await bitmap();
  const viewport = page.viewportSize();
  await page.setViewportSize({width: viewport.width - 120, height: viewport.height});
  await expect.poll(bitmap).not.toBe(before);
  await expect(detailTitle(page)).toHaveText("Aucun point sélectionné");

  // Un clic, lui, est une sélection confirmée.
  await page.mouse.click(box.x + box.width * 0.5, box.y + box.height / 2);
  await expect(detailTitle(page)).toContainText("Point sélectionné :");
});

test("la légende des hachures reste hors du repli, comme description des chronologies", pour("Contrôle de balisage, indépendant de la largeur.", "desktop-chromium"), async ({page}, testInfo) => {
  await prepare(page);
  // Cible d'`aria-describedby` des deux chronologies : elle doit être lisible sans déplier quoi
  // que ce soit — un contenu de `<details>` fermé n'est pas restitué.
  const note = page.locator("#history-observation-note");
  await expect(note).toBeVisible();
  await expect(note).toContainText("hachures jaunes");
  expect(await note.evaluate((node) => Boolean(node.closest("details")))).toBe(false);
  for (const id of ["automation-chart", "climate-actuator-chart"]) {
    const described = await page.locator(`#${id}`).getAttribute("aria-describedby");
    expect(described).toContain("history-observation-note");
  }
});

test("l’historique rendu ne présente pas de violation d’accessibilité détectable", pour("Un profil suffit pour l'axe de la page rendue.", "mobile-chromium"), async ({page}, testInfo) => {
  await prepare(page);
  const results = await new AxeBuilder({page}).withTags(["wcag2a", "wcag2aa", "wcag22aa"]).analyze();
  expect(results.violations, results.violations.map((item) => `${item.id} (${item.nodes.length})`).join(", ")).toEqual([]);
});

test("capture des séries en niveaux de gris", pour("Une largeur de référence suffit.", "mobile-chromium"), async ({page}, testInfo) => {
  test.skip(!process.env.PHYTO_CAPTURE, "Capture de preuve : lancer avec PHYTO_CAPTURE=1.");
  await prepare(page);
  await page.locator("[data-history-view-picker]").selectOption("all");
  await expect(page.locator(".chart-card:has(#temperature-chart)")).toBeVisible();
  // `page.addStyleTag` insérerait un `<style>` en ligne, que la CSP du serveur (`style-src 'self'`,
  // sans `unsafe-inline`) refuse. La propriété CSSOM `style.filter` n'est pas soumise à cette
  // restriction et produit exactement le même rendu monochrome.
  await page.evaluate(() => { document.documentElement.style.filter = "grayscale(1)"; });
  // Sortie par défaut : le dossier de résultats de Playwright, non versionné. La capture
  // **publiée** (`docs/images/remediation-web-mobile-pwa-2026-09-09/`) ne se réécrit que
  // volontairement, par `npm run measure:capture-gris`, qui désigne son dossier par
  // `PHYTO_CAPTURE_DIR` : un test qui écrit dans un fichier versionné salit l'arbre à chaque
  // exécution et remplace une preuve sans que personne l'ait décidé.
  const destination = process.env.PHYTO_CAPTURE_DIR
    ? path.resolve(process.env.PHYTO_CAPTURE_DIR, "history-niveaux-de-gris.png")
    : testInfo.outputPath("history-niveaux-de-gris.png");
  fs.mkdirSync(path.dirname(destination), {recursive: true});
  await page.locator(".chart-card:has(#temperature-chart)").screenshot({path: destination, animations: "disabled"});
  await testInfo.attach("history-niveaux-de-gris", {path: destination, contentType: "image/png"});
});
