"use strict";

// Lot H : journal transversal filtrable, observations d'espace corrigibles et
// consultation datée en lecture seule des pages conservées par la PWA.
const {test, expect, AxeBuilder, createMother} = require("./culture_fixtures");

const observe = async (page, {space = "Espace 2", note}) => {
  const details = page.locator("details").filter({hasText: "Enregistrer une observation d’espace"}).first();
  await details.locator("summary").click();
  const form = details.locator("form");
  await form.getByLabel("Espace observé").selectOption({label: space});
  await form.getByLabel("Observation", {exact: true}).fill(note);
  await form.getByRole("button", {name: "Enregistrer l’observation"}).click();
  await expect(page.getByText(note, {exact: false}).first()).toBeVisible();
};

test("journal : observation d’un espace vide, filtre et correction tracée", async ({page}, testInfo) => {
  test.skip(testInfo.project.name === "pwa-chromium", "Parcours hors ligne exercé séparément.");
  test.setTimeout(60000);
  const mother = await createMother(page, "Mère journal lot H");
  await page.goto("/cultures/journal");
  await expect(page.getByRole("heading", {level: 1})).toHaveText("Journal du carnet");
  // Le journal réunit déjà les opérations de culture : origine, déplacement et stade.
  await expect(page.locator("article.culture-journal-entry")).toHaveCount(3);
  await observe(page, {note: "Espace 2 vide, bac désinfecté"});

  // L'observation vise l'espace : elle n'a créé aucune plante.
  await page.goto("/cultures");
  await expect(page.getByRole("link", {name: "Mère journal lot H"}).first()).toBeVisible();

  await page.goto("/cultures/journal?target=space_2");
  const entries = page.locator("article.culture-journal-entry");
  await expect(entries).toHaveCount(1);
  await expect(entries.first()).toContainText("Espace · Observation");
  await expect(entries.first()).toContainText("Espace 2 vide, bac désinfecté");

  // Les interventions d'une mère se retrouvent par la même chronologie.
  await page.goto(`/cultures/journal?target=${mother}`);
  await expect(page.locator("article.culture-journal-entry")).toHaveCount(3);
  await expect(page.getByRole("link", {name: "Exporter ce filtre en CSV"})).toBeVisible();

  await page.goto("/cultures/journal?target=space_2");
  const correction = entries.first().locator("details").filter({hasText: "Corriger ou annuler cette observation"});
  await correction.locator("summary").click();
  const form = correction.locator("form");
  await form.getByLabel("Observation corrigée").fill("Espace 2 vide, bac désinfecté et rincé");
  await form.getByLabel("Motif de la correction").fill("Précision apportée");
  await form.getByRole("button", {name: "Enregistrer la correction"}).click();
  await expect(page.getByText("Espace 2 vide, bac désinfecté et rincé").first()).toBeVisible();
  // Le motif porte la version courante ; la version précédente reste consultable.
  await expect(entries.first()).toContainText("Motif : Précision apportée");
  const history = page.locator("details").filter({hasText: "Versions précédentes"}).first();
  await history.locator("summary").click();
  await expect(history).toContainText("Version 1");
  await expect(history).toContainText("Espace 2 vide, bac désinfecté");

  expect(await page.evaluate(() => document.documentElement.scrollWidth - innerWidth)).toBeLessThanOrEqual(1);
  expect((await new AxeBuilder({page}).analyze()).violations).toEqual([]);
});

test("journal : un filtre refusé conserve les champs saisis", async ({page}, testInfo) => {
  test.skip(testInfo.project.name === "pwa-chromium", "Parcours hors ligne exercé séparément.");
  const response = await page.goto("/cultures/journal?start=2026-09-05&end=2026-09-01&type=space_event:incident");
  expect(response.status()).toBe(400);
  await expect(page.locator("p.culture-warning")).toContainText("précède son début");
  await expect(page.locator('[name="start"]')).toHaveValue("2026-09-05");
  await expect(page.locator('[name="end"]')).toHaveValue("2026-09-01");
  await expect(page.locator('[name="type"]')).toHaveValue("space_event:incident");
  expect((await new AxeBuilder({page}).analyze()).violations).toEqual([]);
});

test("journal : consultation datée hors ligne, sans mutation rejouée", async ({page}, testInfo) => {
  test.skip(testInfo.project.name !== "pwa-chromium", "Le service worker est réservé au profil PWA.");
  test.setTimeout(60000);
  await createMother(page, "Mère hors ligne lot H");
  await page.evaluate(async () => { await navigator.serviceWorker.ready; });
  await page.goto("/cultures/journal");
  await observe(page, {space: "Espace 1", note: "Contrôle hors ligne du lot H"});
  await page.goto("/cultures/journal");
  await expect.poll(() => page.evaluate(async () => {
    for (const name of (await caches.keys()).filter(n => n.startsWith("phyto-cultures-"))) {
      if (await (await caches.open(name)).match(location.href.split("#")[0])) return true;
    }
    return false;
  })).toBe(true);
  let posts = 0;
  page.on("request", request => { if (request.method() === "POST") posts++; });
  await page.context().setOffline(true);
  await page.reload();
  await expect(page.locator("#pwa-connection-banner")).toContainText("lecture seule");
  await expect(page.locator('meta[name="phyto-offline-snapshot"]')).toHaveCount(1);
  await expect(page.getByText("Contrôle hors ligne du lot H").first()).toBeVisible();
  const inventory = page.locator(".culture-offline-index");
  await inventory.locator("summary").click();
  const entries = inventory.locator("[data-culture-offline-index] li");
  await expect(entries.filter({hasText: "Journal du carnet"}).first()).toContainText("conservée le");
  // Une page du carnet jamais visitée le dit au lieu d'échouer.
  const unavailable = page.getByRole("link", {name: /Cycles et rappels/});
  await expect(unavailable).toHaveClass(/culture-unavailable/);
  await unavailable.click({force: true});
  await expect(page.locator('meta[name="phyto-offline-snapshot"]')).toHaveCount(1);
  const cachedApis = await page.evaluate(async () => {
    const urls = [];
    for (const name of await caches.keys()) for (const key of await (await caches.open(name)).keys()) urls.push(new URL(key.url).pathname);
    return urls.filter(path => path.startsWith("/api/") || path.startsWith("/actions/"));
  });
  expect(cachedApis).toEqual([]);
  // Hors ligne la consultation reste en lecture seule : la saisie est désactivée,
  // rien n'est mis en file d'attente et aucune observation n'est rejouée.
  const details = page.locator("details").filter({hasText: "Enregistrer une observation d’espace"}).first();
  await details.locator("summary").click();
  const form = details.locator("form");
  await expect(form.getByLabel("Observation", {exact: true})).toBeDisabled();
  await expect(form.getByRole("button", {name: "Enregistrer l’observation"})).toBeDisabled();
  await page.context().setOffline(false);
  await page.reload();
  await expect(page.locator('meta[name="phyto-offline-snapshot"]')).toHaveCount(0);
  await expect(page.locator("article.culture-journal-entry")).toHaveCount(4);
  expect(posts).toBe(0);
});
