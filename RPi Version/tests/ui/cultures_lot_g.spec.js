// Lot G : affectations d'équipements datées, changement d'usage de cyclic_2 et contexte résolu.
const {test, expect, AxeBuilder} = require("./culture_fixtures");
const {pour} = require("./profils");

const START = "2026-06-01";
const SWITCH = "2026-07-01";

const post = async (page, form, name) => {
  const answer = page.waitForResponse(r => r.url().endsWith("/api/v1/cultures/equipment") && r.request().method() === "POST");
  await form.getByRole("button", {name}).click();
  return await answer;
};

const open = async form => {
  const summary = form.locator("..").locator(":scope > summary");
  if (await summary.count()) await summary.click();
};

// La page se recharge elle-même après une écriture : chaque étape attend une condition
// de la page rechargée avant d'agir, plutôt qu'un simple état de chargement.
const windows = (page, equipmentId) => page.locator(`#equipement-${equipmentId} section.equipment-window`);

// Le carnet temporaire est partagé par les scénarios du même worker, et les six identifiants
// d'équipement sont fixes : chaque scénario libère ce qu'il a déclaré.
const release = async (page, equipmentId) => {
  for (let guard = 0; guard < 6; guard += 1) {
    await page.goto(`/cultures/equipment?equipment=${equipmentId}`);
    const forms = page.locator(`#equipement-${equipmentId} form[data-equipment-form][data-operation="cancel"]`);
    const count = await forms.count();
    if (!count) return;
    const form = forms.first();
    await open(form);
    await form.locator('[name="reason"]').fill("Nettoyage du scénario de test");
    expect((await post(page, form, "Annuler l’affectation")).status()).toBe(200);
    await expect(forms).toHaveCount(count - 1);
  }
};

const declare = async (page, {equipment, usage, scope, target, start}) => {
  const form = page.locator('form[data-equipment-form][data-operation="link"]').first();
  await open(form);
  await form.locator('[name="equipment_id"]').selectOption(equipment);
  await form.locator('[name="usage"]').fill(usage);
  await form.locator('[name="scope"]').selectOption(scope);
  if (scope === "space") await form.locator('[name="space"]').selectOption(target);
  if (scope === "reservoir") await form.locator('[name="reservoir_id"]').selectOption(target);
  await form.locator('[name="start_at"]').fill(start);
  return {form, answer: await post(page, form, "Déclarer l’affectation")};
};

// Ouverture répétable de la seule saisie d'un jour donné : le rechargement déclenché par
// la page ne doit pas transformer une navigation en course, et le corps de la réponse
// n'est pas relisible une fois la navigation partie.
const showDay = async (page, day) => {
  await expect.poll(async () => {
    try {
      await page.goto(`/cultures/solutions?view=releves&kind=renewal&start=${day}&end=${day}`);
      return await page.locator("article.solution-journal").count();
    } catch (_error) { return 0; }
  }, {timeout: 20000, message: "Ouverture de la saisie enregistrée"}).toBe(1);
  return page.locator("article.solution-journal").first();
};

test("changement d'usage de cyclic_2 : périodes successives et contexte résolu à la date", pour("Affectations exercées sur deux formats.", "desktop-chromium", "mobile-chromium"), async ({page}, testInfo) => {
  test.setTimeout(60000);
  const first = `Irrigation ${testInfo.project.name}`;
  const second = `Brumisation ${testInfo.project.name}`;
  await release(page, "cyclic_2");

  await page.goto("/cultures/equipment");
  await expect(page.getByRole("heading", {level: 1})).toHaveText("Affectations d’équipements");
  // R2.7 : les affectations sont le premier bloc après le sélecteur, le catalogue est replié.
  const hauts = await page.evaluate(() => ["selection", "affectations", "applique", "catalogue"]
    .map(id => document.getElementById(id).getBoundingClientRect().top));
  expect(hauts[0]).toBeLessThan(hauts[1]);
  expect(hauts[1]).toBeLessThan(hauts[2]);
  expect(hauts[2]).toBeLessThan(hauts[3]);
  const catalogue = page.locator("#catalogue");
  expect(await catalogue.evaluate(element => element.open)).toBe(false);
  await catalogue.locator(":scope > summary").click();
  // Le catalogue courant est une lecture seule : aucun champ de saisie dans son tableau.
  await expect(catalogue.getByRole("cell", {name: "cyclic_2", exact: true})).toBeVisible();
  await expect(catalogue.locator("input, select, textarea")).toHaveCount(0);

  const created = await declare(page, {equipment: "cyclic_2", usage: first, scope: "space", target: "space_2", start: START});
  expect(created.answer.status(), created.answer.status() === 200 ? "" : await created.answer.text()).toBe(200);
  await expect(windows(page, "cyclic_2")).toHaveCount(1);

  // Une seconde affectation qui recouvre la première est refusée, sans écriture.
  const overlap = await declare(page, {equipment: "cyclic_2", usage: second, scope: "space", target: "space_1", start: "2026-06-15"});
  expect(overlap.answer.status()).toBe(400);
  await expect(overlap.form.locator(".culture-form-errors")).toContainText("recouvrent");
  await expect(windows(page, "cyclic_2")).toHaveCount(1);

  // Clore la période puis ouvrir la suivante : deux usages successifs cohabitent.
  const closeForms = page.locator('form[data-equipment-form][data-operation="close"]');
  const close = closeForms.first();
  await open(close);
  await close.locator('[name="end_at"]').fill(SWITCH);
  const closed = await post(page, close, "Clore l’affectation");
  expect(closed.status(), closed.status() === 200 ? "" : await closed.text()).toBe(200);
  await expect(closeForms).toHaveCount(0);

  const opened = await declare(page, {equipment: "cyclic_2", usage: second, scope: "space", target: "space_1", start: SWITCH});
  expect(opened.answer.status(), opened.answer.status() === 200 ? "" : await opened.answer.text()).toBe(200);
  await expect(windows(page, "cyclic_2")).toHaveCount(2);
  // Le libellé du catalogue est copié à la saisie, et affiché comme tel.
  await expect(page.locator("#equipement-cyclic_2")).toContainText("contexte copié à la saisie : Sortie cyclique 2");

  // Résolution rétrospective : chaque date retrouve l'usage réellement déclaré, et
  // l'indication courte de la source reste contre la valeur.
  await page.goto("/cultures/equipment?at=2026-06-15");
  await expect(page.locator("[data-equipment-resolved]")).toContainText(first);
  await expect(page.locator("#applique .culture-source").first()).toHaveText(`affectation du ${START.split("-").reverse().join("/")}`);
  await expect(page.locator('#selection input[name="at"]')).toHaveValue("2026-06-15");
  await page.goto("/cultures/equipment?at=2026-07-15");
  await expect(page.locator("[data-equipment-resolved]")).toContainText(second);
  // Jamais de repli sur le catalogue d'aujourd'hui : hors fenêtre, la valeur est inconnue.
  await page.goto("/cultures/equipment?at=2026-05-01");
  await expect(page.locator("[data-equipment-resolved]")).toContainText("Association inconnue à cette date");
  await expect(page.locator("#applique .culture-source")).toHaveText("inconnu");
  await page.goto("/cultures/equipment");

  expect(await page.evaluate(() => document.documentElement.scrollWidth - innerWidth)).toBeLessThanOrEqual(1);
  expect((await new AxeBuilder({page}).analyze()).violations).toEqual([]);
  await release(page, "cyclic_2");
});

test("une intervention affiche le contexte d'équipement résolu à sa propre date", pour("Contexte exercé sur deux formats.", "desktop-chromium", "mobile-chromium"), async ({page}, testInfo) => {
  test.setTimeout(60000);
  const usage = `Renouvellement ${testInfo.project.name}`;
  // Date propre au format : deux renouvellements au même instant sont refusés à dessein.
  const day = testInfo.project.name === "mobile-chromium" ? "2026-06-06" : "2026-06-05";
  await release(page, "cyclic_1");

  // Une intervention saisie sans affectation déclarée porte sa propre copie de catalogue.
  await page.goto("/cultures/solutions?view=saisir");
  const entry = page.locator("form[data-solution-entry]").first();
  await expect(entry).toBeVisible();
  await entry.locator('[name="kind"]').selectOption("renewal");
  await entry.locator('[name="target"]').selectOption("reservoir_2");
  await entry.locator('[name="effective_at"]').fill(day);
  await entry.locator('[name="volume_l"]').fill("20");
  const saved = page.waitForResponse(r => r.url().endsWith("/api/v1/cultures/solutions") && r.request().method() === "POST");
  await entry.getByRole("button", {name: "Enregistrer la saisie"}).click();
  expect((await saved).status()).toBe(200);

  const article = await showDay(page, day);
  await article.locator("details.solution-entry-details > summary").click();
  const context = article.locator("[data-equipment-context]");
  await expect(context).toBeVisible();
  expect(["snapshot", "unknown"]).toContain(await context.getAttribute("data-equipment-context"));

  // Après déclaration d'une affectation couvrant la date, la provenance devient datée.
  await page.goto("/cultures/equipment");
  const created = await declare(page, {equipment: "cyclic_1", usage, scope: "reservoir", target: "reservoir_2", start: START});
  expect(created.answer.status(), created.answer.status() === 200 ? "" : await created.answer.text()).toBe(200);
  await expect(windows(page, "cyclic_1")).toHaveCount(1);

  const resolved = await showDay(page, day);
  await resolved.locator("details.solution-entry-details > summary").click();
  await expect(resolved.locator('[data-equipment-context="link"]')).toContainText(usage);

  expect(await page.evaluate(() => document.documentElement.scrollWidth - innerWidth)).toBeLessThanOrEqual(1);
  expect((await new AxeBuilder({page}).analyze()).violations).toEqual([]);
  await release(page, "cyclic_1");
});
