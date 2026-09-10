"use strict";

const {test, expect, AxeBuilder, createMother} = require("./culture_fixtures");
const {randomUUID} = require("node:crypto");

const navigation = page => page.getByRole("navigation", {name: "Navigation du carnet", exact: true});

test("lot UI 1 : fiche, relevé, cycles et ressources conservent la culture", async ({page}, testInfo) => {
  test.setTimeout(90000);
  const id = await createMother(page, "Mère contexte UI");
  await navigation(page).getByRole("link", {name: "Solutions et relevés", exact: true}).click();
  await expect(page).toHaveURL(new RegExp(`target=${id}`));
  await expect(navigation(page).locator('[aria-current="page"]')).toHaveText("Solutions et relevés");
  // R1.6 : le lien du carnet mène à la vue « Saisir » (cible sans relevé), dont le bloc de
  // saisie **est** l'objet : il arrive déplié. Le `<details>` reste là pour pouvoir le
  // replier, mais l'ouvrir d'un clic n'a plus de sens — ce clic le refermerait.
  await expect(page.locator("#saisie")).toHaveAttribute("open", "");
  const form = page.locator("[data-solution-entry]").first();
  await expect(form).toBeVisible();
  await expect(form.locator('[name="target"]')).toHaveValue(id);
  await expect(form.locator('[name="ph"]')).toHaveValue("");
  await form.locator('[name="ph"]').fill("6,2");
  await form.getByRole("button", {name: "Enregistrer la saisie"}).click();
  // R1.7 : l'affichage passe par le filtre `nombre` (virgule française, deux décimales) ;
  // la valeur persistée reste 6.2, c'est l'API qui en fait foi.
  await expect(page.locator(".solution-journal")).toContainText("pH 6,20");
  await expect(page).toHaveURL(new RegExp(`target=${id}`));
  await navigation(page).getByRole("link", {name: "Cycles et rappels", exact: true}).click();
  await expect(page).toHaveURL(new RegExp(`subject=${id}`));
  await expect(page.locator('[data-comparison-selection] input[name="subject"]:checked')).toHaveValue(id);
  // R2.6 : rappels et comparaison ne sont plus deux sections empilées mais deux vues de la
  // même route. « Les rappels d'abord » ne se mesure donc plus en pixels — cela se lit dans
  // le défaut : on arrive sur « À faire », et « Comparer » est le second lien de la barre.
  // La comparaison reste atteignable sans JS, et la sélection de culture y est conservée.
  const vues = page.locator(".culture-view-tabs a");
  await expect(vues).toHaveText(["À faire", "Comparer"]);
  await expect(page.locator('.culture-view-tabs a[aria-current="page"]')).toHaveText("À faire");
  await expect(page.locator("#rappels")).toBeVisible();
  await expect(page.getByText("Comparer les cycles", {exact: true})).toBeHidden();
  await vues.filter({hasText: "Comparer"}).click();
  await expect(page).toHaveURL(new RegExp(`subject=${id}.*view=comparer`));
  await expect(page.getByText("Comparer les cycles", {exact: true})).toBeVisible();
  await expect(page.locator("#rappels")).toBeHidden();
  await expect(page.locator('[data-comparison-selection] input[name="subject"]:checked')).toHaveValue(id);
  for (const [label, section] of [["Plages cibles", "targets"], ["Journal", "journal"], ["Repères d’éclairage", "light"], ["Équipements", "equipment"]]) {
    await navigation(page).getByRole("link", {name: label, exact: true}).click();
    await expect(page).toHaveURL(new RegExp(`/cultures/${section}\\?(target|subject)=${id}`));
    await expect(navigation(page).getByRole("link")).toHaveCount(7);
    await expect(navigation(page).locator('[aria-current="page"]')).toHaveText(label);
    await expect(page.locator(".culture-context a").first()).toHaveAttribute("href", `/cultures/${id}`);
  }
  await page.locator(".culture-context a").first().click();
  await expect(page.getByRole("heading", {level: 1})).toHaveText("Mère contexte UI");
  await navigation(page).getByRole("link", {name: "Solutions et relevés", exact: true}).click();
  await page.locator(".culture-context").getByRole("link", {name: "Vue globale", exact: true}).click();
  await expect(page).toHaveURL(/\/cultures\/solutions$/);
  await expect(page.locator('.solution-filter [name="target"]')).toHaveValue("");
  await page.goto("/cultures/solutions?target=reservoir_2");
  await expect(navigation(page).getByRole("link", {name: "Cycles et rappels · vue globale", exact: true})).toHaveAttribute("href", "/cultures/cycles");
  await page.goto("/cultures/journal?target=space_2");
  await expect(page.locator(".culture-context")).toContainText("Espace 2");
  await expect(navigation(page).getByRole("link", {name: "Solutions et relevés · vue globale", exact: true})).toHaveAttribute("href", "/cultures/solutions");
});

test("lot UI 1 : correction de stade sans écrasement et préréglage explicite", async ({page}) => {
  await page.goto("/cultures/light");
  const csrf = await page.locator('meta[name="csrf-token"]').getAttribute("content");
  const response = await page.request.post("/api/v1/cultures/light", {
    headers: {"X-CSRF-Token": csrf},
    data: {operation: "light", request_id: randomUUID(), scope: "global", label: "Durée personnalisée", stage: "vegetatif", on_minutes: 960, off_minutes: 480, start_at: "2026-08-01", confirm_date: true},
  });
  expect(response.ok(), await response.text()).toBeTruthy();
  const result = await response.json();
  await page.reload();
  const item = page.locator(`#repere-${result.id}`);
  await item.getByText("Corriger ce repère", {exact: true}).click();
  const form = item.locator('[data-operation="light"]');
  await form.locator('[name="stage"]').selectOption("floraison");
  await expect(form.locator('[name="on_minutes"]')).toHaveValue("960");
  await expect(form.locator("[data-light-preview]")).toContainText("16 h d’éclairage");
  await form.locator('[name="reason"]').fill("Corriger uniquement le stade");
  await form.getByRole("button", {name: "Corriger le repère", exact: true}).click();
  await expect(item).toContainText("16 h / 8 h");
  await item.getByText("Corriger ce repère", {exact: true}).click();
  await form.getByRole("button", {name: "Utiliser 12 h / 12 h", exact: true}).click();
  await expect(form.locator('[name="on_minutes"]')).toHaveValue("720");
  await form.locator('[name="on_minutes"]').fill("900");
  await form.locator('[name="stage"]').selectOption("vegetatif");
  await expect(form.locator('[name="on_minutes"]')).toHaveValue("900");
});

test("lot UI 1 : lecture compacte, graduations et plein jour", async ({page}, testInfo) => {
  test.setTimeout(90000);
  // R1.6 : les courbes sont servies dans la vue « Analyser ». Les graduations se mesurent
  // donc sur cette vue-là ; les deux autres blocs restent servis mais `hidden`.
  await page.goto("/cultures/solutions?target=reservoir_2&view=analyser");
  const csrf = await page.locator('meta[name="csrf-token"]').getAttribute("content");
  const response = await page.request.post("/api/v1/cultures/solutions", {
    headers: {"X-CSRF-Token": csrf},
    data: {request_id: randomUUID(), operation: "entry", kind: "renewal", volume_l: 20, reservoir_id: "reservoir_2", effective_at: "2026-08-05", precision: "date", ph: 6.2, ec: 1.4, confirm_date: true},
  });
  expect(response.ok(), await response.text()).toBeTruthy();
  await page.reload();
  for (const width of [393, 320, 1440]) {
    await page.setViewportSize({width, height: 900});
    await expect.poll(() => page.locator('svg[data-metric="ph"] text').first().evaluate(el => {
      return parseFloat(getComputedStyle(el).fontSize) * el.getScreenCTM().a;
    })).toBeGreaterThanOrEqual(13.5);
    expect(await page.evaluate(() => document.documentElement.scrollWidth - innerWidth)).toBeLessThanOrEqual(1);
  }
  for (const path of ["solutions?target=reservoir_2", "targets", "journal", "cycles", "light", "equipment", ""]) {
    await page.setViewportSize({width: 393, height: 851});
    await page.goto(`/cultures${path ? '/' + path : ''}`);
    if (path === "targets") await expect(page.locator('.culture-new-entry form')).not.toBeVisible();
    if (path === "journal") {
      const operations = await page.getByRole("heading", {name: "Opérations du carnet"}).boundingBox();
      expect(operations.y).toBeLessThan(1000);
    }
    for (const theme of ["", "daylight"]) {
      await page.evaluate(theme => document.documentElement.setAttribute("data-theme", theme), theme);
      expect((await new AxeBuilder({page}).analyze()).violations).toEqual([]);
      expect(await page.evaluate(() => document.documentElement.scrollWidth - innerWidth)).toBeLessThanOrEqual(1);
      if (testInfo.project.name === "mobile-chromium") await page.screenshot({path: testInfo.outputPath(`${path.split('?')[0] || 'cultures'}-${theme || 'normal'}.png`), fullPage: true});
    }
  }
});

test("lot UI 1 : climat renseigné et lacune restent lisibles après rotation", async ({page}, testInfo) => {
  test.skip(testInfo.project.name === "pwa-chromium", "La substitution HTML du jeu fictif exige un navigateur sans service worker.");
  test.setTimeout(60000);
  const id = await createMother(page, "Mère climat fictif");
  // Jeu de présentation synthétique : aucun historique matériel n'est fabriqué en base.
  const points = [0, 1, 2].map(index => ({sensor: "bme280t", label: "Température fictive", unit: "°C",
    hour: 1785542400 + index * 3600, at: `2026-08-01T0${index}:00:00Z`, span_hours: 1,
    mean: index === 1 ? null : 20 + index, minimum: 19 + index, maximum: 21 + index,
    valid_count: index === 1 ? 0 : 60, coverage: index === 1 ? 0 : 1, missing: index === 1}));
  await page.route(`**/cultures/cycles?subject=${id}`, async route => {
    const response = await route.fetch();
    const body = (await response.text()).replace('data-climate-chart="[]"',
      `data-climate-chart="${JSON.stringify(points).replaceAll('"', '&quot;')}"`);
    await route.fulfill({response, body});
  });
  await page.goto(`/cultures/cycles?subject=${id}`);
  const svg = page.locator('[data-climate-chart] svg');
  await expect(svg.locator("circle")).toHaveCount(2);
  await expect(svg.locator(".climate-gap")).toHaveCount(1);
  for (const width of [320, 568, 1440]) {
    await page.setViewportSize({width, height: 900});
    await expect.poll(() => svg.locator("text").first().evaluate(el =>
      parseFloat(getComputedStyle(el).fontSize) * el.getScreenCTM().a)).toBeGreaterThanOrEqual(13.5);
    const bounds = await svg.evaluate(el => ({width: el.viewBox.baseVal.width,
      points: [...el.querySelectorAll("circle")].map(point => Number(point.getAttribute("cx")))}));
    expect(Math.max(...bounds.points)).toBeLessThan(bounds.width);
  }
});
