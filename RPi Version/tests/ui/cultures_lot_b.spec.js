"use strict";

// Lot B : synthèse de cycle bornée, détail horaire paginé et consultation hors ligne datée.
const {test, expect, AxeBuilder, createMother} = require("./culture_fixtures");
const {pour, sauf} = require("./profils");

test("cycles : synthèse bornée, granularité affichée et détail horaire séparé", sauf("Parcours hors ligne exercé séparément.", "pwa-chromium"), async ({page}, testInfo) => {
  const mother = await createMother(page, "Mère cycles longs");
  // R2.6 : le panneau « Comparer » de /cultures/cycles est servi mais `hidden` tant que
  // `view=comparer` n'est pas demandé — hors de l'arbre d'accessibilité sans lui.
  await page.goto(`/cultures/cycles?subject=${mother}&view=comparer`);
  const climate = page.locator(".culture-section").filter({hasText: "Climat commun à la serre"}).first();
  await expect(climate).toContainText(/Synthèse par (heure|jour|semaine|quatre semaines)/);
  await expect(climate).toContainText("périodes sans agrégat");
  await expect(climate).toContainText("jamais d’une moyenne de moyennes horaires");
  // Le tableau détaillé est paginé et séparé du graphique : aucune ligne dupliquée en masse.
  const detail = page.locator("#detail-horaire");
  await expect(detail.locator("summary")).toContainText("Détail horaire paginé · 0 agrégats en base");
  await detail.locator("summary").click();
  await expect(detail).toContainText("Aucun agrégat horaire sur cette page.");
  await expect(page.locator("[data-climate-offset]")).toHaveCount(0);
  const inventory = page.locator(".culture-offline-index");
  await inventory.locator("summary").click();
  await expect(inventory.locator("[data-culture-offline-index]")).toContainText(/conservée le|Aucune page du carnet|Inventaire hors ligne indisponible/);
  expect(await page.evaluate(() => document.documentElement.scrollWidth - innerWidth)).toBeLessThanOrEqual(1);
  expect((await new AxeBuilder({page}).analyze()).violations).toEqual([]);
});

test("cycles : comparaison de plusieurs cycles bornée sans détail horaire", sauf("Parcours hors ligne exercé séparément.", "pwa-chromium"), async ({page}, testInfo) => {
  const first = await createMother(page, "Mère comparée A");
  const second = await createMother(page, "Mère comparée B");
  // R2.6 : le panneau « Comparer » de /cultures/cycles est servi mais `hidden` tant que
  // `view=comparer` n'est pas demandé — hors de l'arbre d'accessibilité sans lui.
  await page.goto(`/cultures/cycles?subject=${first}&subject=${second}&view=comparer`);
  const sections = page.locator(".culture-section").filter({hasText: "Climat commun à la serre"});
  await expect(sections).toHaveCount(2);
  await expect(sections.first()).toContainText(/Synthèse par (heure|jour|semaine|quatre semaines)/);
  await expect(page.locator("#detail-horaire")).toHaveCount(0);
  await expect(page.getByText("Le détail horaire s’affiche en sélectionnant une seule culture.").first()).toBeVisible();
  await expect(page.getByRole("link", {name: "Ouvrir le détail horaire de Mère comparée A"})).toBeVisible();
});

test("cycles : synthèse datée hors ligne, détail non conservé signalé, aucune mutation rejouée", pour("Le service worker est réservé au profil PWA.", "pwa-chromium"), async ({page}, testInfo) => {
  test.setTimeout(60000);
  const mother = await createMother(page, "Mère hors ligne lot B");
  await page.evaluate(async () => { await navigator.serviceWorker.ready; });
  // R2.6 : le panneau « Comparer » de /cultures/cycles est servi mais `hidden` tant que
  // `view=comparer` n'est pas demandé — hors de l'arbre d'accessibilité sans lui.
  await page.goto(`/cultures/cycles?subject=${mother}&view=comparer`);
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
  const climate = page.locator(".culture-section").filter({hasText: "Climat commun à la serre"}).first();
  await expect(climate).toContainText(/Synthèse par (heure|jour|semaine|quatre semaines)/);
  const inventory = page.locator(".culture-offline-index");
  await inventory.locator("summary").click();
  const entries = inventory.locator("[data-culture-offline-index] li");
  await expect(entries.filter({hasText: "Cycles et rappels"})).toContainText("conservée le");
  // Une page du carnet jamais visitée n'est pas conservée : le lien le dit au lieu d'échouer.
  const unavailable = page.getByRole("link", {name: /Solutions et relevés/});
  await expect(unavailable).toHaveClass(/culture-unavailable/);
  await expect(unavailable).toContainText("non conservé hors ligne");
  await unavailable.click({force: true});
  await expect(page.locator('meta[name="phyto-offline-snapshot"]')).toHaveCount(1);
  const cachedApis = await page.evaluate(async () => {
    const urls = [];
    for (const name of await caches.keys()) for (const key of await (await caches.open(name)).keys()) urls.push(new URL(key.url).pathname);
    return urls.filter(path => path.startsWith("/api/") || path.startsWith("/actions/"));
  });
  expect(cachedApis).toEqual([]);
  await page.context().setOffline(false);
  await page.reload();
  await expect(page.locator('meta[name="phyto-offline-snapshot"]')).toHaveCount(0);
  await expect(page.getByRole("link", {name: /Solutions et relevés/})).not.toHaveClass(/culture-unavailable/);
  expect(posts).toBe(0);
});
