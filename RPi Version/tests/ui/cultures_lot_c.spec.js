// Lot C : compléter dans le navigateur un parcours repris en cours de cycle.
const {test, expect, AxeBuilder} = require("./culture_fixtures");

// Dates choisies après la libération de l'espace 2 des autres scénarios du même carnet.
const ORIGIN = "2026-09-01";
const MOVE = "2026-09-02";
const STAGE = "2026-09-03";
const CURRENT = "2026-09-07";

test("reprise en floraison : étapes et occupation passées complétées", async ({page}, testInfo) => {
  test.skip(!["desktop-chromium", "mobile-chromium"].includes(testInfo.project.name), "Reprise exercée sur deux formats.");
  test.setTimeout(45000);
  const name = `Reprise ${testInfo.project.name} ${Date.now()}`;
  await page.goto("/cultures");
  const details = page.locator("details.culture-create").filter({hasText: "Créer un lot"});
  await details.locator("summary").click();
  const form = details.locator("form");
  await form.getByLabel("Nom", {exact: true}).fill(name);
  await form.getByLabel("Origine des semences").fill("Semences reprise");
  await form.locator('[name="origin_count"]').fill("6");
  await form.locator('[name="origin_at"]').fill(ORIGIN);
  await form.locator('[name="stage"]').selectOption("floraison");
  await form.locator('[name="stage_at"]').fill(CURRENT);
  await form.locator('[name="space"]').selectOption("space_2");
  await form.locator('[name="space_at"]').fill(CURRENT);
  await form.getByRole("button", {name: "Créer un lot", exact: true}).click();
  await expect(page.getByRole("heading", {level: 1})).toHaveText(name);
  await expect(page.getByText("Floraison · J", {exact: false})).toBeVisible();
  const counter = await page.locator(".culture-counter strong").first().textContent();

  const backfill = async (mode, date, fill) => {
    const entry = page.locator(`form[data-culture-backfill][data-mode="${mode}"]`);
    await entry.locator("..").locator(":scope > summary").click();
    await entry.locator('[name="effective_at"]').fill(date);
    if (fill) await fill(entry);
    const answer = page.waitForResponse(r => r.url().endsWith("/api/v1/cultures") && r.request().method() === "POST");
    await entry.locator('[type="submit"]').click();
    return {entry, answer: await answer};
  };

  const stage = await backfill("stage", STAGE, f => f.locator('[name="stage"]').selectOption("vegetatif"));
  expect(stage.answer.status(), stage.answer.status() === 200 ? "" : await stage.answer.text()).toBe(200);
  await page.waitForLoadState("domcontentloaded");
  const move = await backfill("move", MOVE, f => f.locator('[name="space"]').selectOption("space_1"));
  expect(move.answer.status(), move.answer.status() === 200 ? "" : await move.answer.text()).toBe(200);
  await page.waitForLoadState("domcontentloaded");

  // Le stade courant, son compteur et l'occupation actuelle sont inchangés.
  await expect(page.locator(".culture-counter strong").first()).toHaveText(counter);
  await expect(page.getByText("Espace 2 · En cours", {exact: true})).toBeVisible();
  const parcours = page.locator("article.card", {hasText: "Parcours"}).locator("ol li");
  await expect(parcours).toHaveCount(2);
  await expect(parcours.first()).toContainText("Végétatif · 03/09/2026 → 07/09/2026 · 4 jours");
  await expect(parcours.last()).toContainText("Floraison · 07/09/2026 → en cours");
  await expect(page.locator('form[data-culture-backfill][data-mode="stage"] [name="stage"] option'))
    .toHaveText(["Germination"]);

  // Chronologie impossible : refus sans écriture ni navigation, la saisie reste dans le formulaire.
  const refused = await backfill("stage", CURRENT, f => f.locator('[name="stage"]').selectOption("germination"));
  expect(refused.answer.status()).toBe(400);
  // Lot UI 2 : un refus s'affiche dans le résumé d'erreur du socle commun, pas dans l'état.
  await expect(refused.entry.locator(".culture-form-errors")).toContainText("précéder");
  await expect(refused.entry.locator('[name="effective_at"]')).toHaveValue(CURRENT);
  await expect(page.locator("article.card", {hasText: "Parcours"}).locator("ol li")).toHaveCount(2);

  expect(await page.evaluate(() => document.documentElement.scrollWidth - innerWidth)).toBeLessThanOrEqual(1);
  expect((await new AxeBuilder({page}).analyze()).violations).toEqual([]);
});
