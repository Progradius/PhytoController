"use strict";

// Lot F : repères d'éclairage informatifs, écart aux horaires configurés,
// équipement désactivé, état opérationnel indisponible et consultation hors ligne.
const {test, expect, AxeBuilder, createMother} = require("./culture_fixtures");

// Chaque scénario vise une cible distincte : deux repères de même portée, même cible
// et même stade se chevaucheraient, et le carnet du worker est partagé entre les tests.
const enregistrer = async (page, {label, minutes, scope, space, stage}) => {
  const details = page.locator("details").filter({hasText: "Enregistrer un repère"}).first();
  await details.locator("summary").click();
  const form = details.locator("form");
  await form.getByLabel("Nom du repère").fill(label);
  if (scope) await form.locator('select[name="scope"]').selectOption({label: scope});
  if (space) await form.locator('select[name="space"]').selectOption({label: space});
  if (stage) await form.locator('select[name="stage"]').selectOption({label: stage});
  await form.locator('input[name="on_minutes"]').fill(String(minutes));
  await form.getByRole("button", {name: "Enregistrer le repère"}).click();
};

test("repères : écart informatif, minuterie désactivée et horaires inchangés", async ({page, request}, testInfo) => {
  test.skip(testInfo.project.name === "pwa-chromium", "Parcours hors ligne exercé séparément.");
  await createMother(page, "Mère repères éclairage");
  const before = (await (await request.get("/api/v1/state")).json());
  await page.goto("/cultures/light");
  await expect(page.getByRole("heading", {level: 1})).toHaveText("Repères d’éclairage");
  await expect(page.getByText("ne prouve pas le fonctionnement physique")).toBeVisible();
  // Les deux minuteries de la configuration de test sont désactivées : c'est dit.
  await expect(page.getByText("Minuterie quotidienne 1 désactivée").first()).toBeVisible();
  await expect(page.getByText("Aucun repère enregistré pour cette culture à cette date")).toBeVisible();
  await enregistrer(page, {label: "Végétatif 18/6", minutes: 1080});
  await expect(page.getByRole("heading", {name: "Végétatif 18/6"})).toBeVisible();
  const carte = page.locator(".culture-light-card").filter({hasText: "Mère repères éclairage"});
  await expect(carte).toContainText("18 h / 6 h");
  await expect(carte).toContainText("08:00 → 20:00");
  await expect(carte).toContainText("−6 h d’éclairage configuré");
  await expect(carte.getByRole("link", {name: "Ouvrir les réglages de l’éclairage 1"})).toHaveAttribute("href", "/conf#daily-timer-1");
  // Un repère ne change ni les horaires configurés, ni les sorties.
  const after = (await (await request.get("/api/v1/state")).json());
  expect(after.timers).toEqual(before.timers);
  expect(after.outputs).toEqual(before.outputs);
  expect(after.day_night).toEqual(before.day_night);
  expect(await page.evaluate(() => document.documentElement.scrollWidth - innerWidth)).toBeLessThanOrEqual(1);
  expect((await new AxeBuilder({page}).analyze()).violations).toEqual([]);
});

test("repères : état opérationnel indisponible et correction tracée", async ({page}, testInfo) => {
  test.skip(testInfo.project.name === "pwa-chromium", "Parcours hors ligne exercé séparément.");
  await createMother(page, "Mère correction repère");
  await page.goto("/cultures/light");
  // Sans publication des boucles de contrôle, l'absence d'état est explicite.
  await expect(page.getByText("État opérationnel indisponible").first()).toBeVisible();
  await enregistrer(page, {label: "Repère à corriger", minutes: 720,
                           scope: "Un espace", space: "Espace 2", stage: "Floraison"});
  const article = page.locator("article.culture-journal").filter({hasText: "Repère à corriger"}).first();
  await expect(article).toContainText("12 h / 12 h");
  const correction = article.locator("details").filter({hasText: "Corriger ce repère"});
  await correction.locator("summary").click();
  const form = correction.locator("form");
  await form.getByLabel("Éclairage par jour, en minutes").fill("1080");
  await form.getByLabel("Motif de la correction").fill("Passage en végétatif");
  await form.getByRole("button", {name: "Corriger le repère"}).click();
  await expect(page.locator("article.culture-journal").filter({hasText: "Repère à corriger"}).first()).toContainText("18 h / 6 h");
  const historique = page.locator("details").filter({hasText: "Versions précédentes"}).first();
  await historique.locator("summary").click();
  await expect(historique).toContainText("720 min d’éclairage");
});

test("repères : consultation datée hors ligne, aucune mutation rejouée", async ({page}, testInfo) => {
  test.skip(testInfo.project.name !== "pwa-chromium", "Le service worker est réservé au profil PWA.");
  test.setTimeout(60000);
  await createMother(page, "Mère hors ligne lot F");
  await page.evaluate(async () => { await navigator.serviceWorker.ready; });
  await page.goto("/cultures/light");
  await enregistrer(page, {label: "Repère hors ligne", minutes: 1080,
                           scope: "Un espace", space: "Espace 2", stage: "Végétatif"});
  await expect(page.getByRole("heading", {name: "Repère hors ligne"})).toBeVisible();
  await expect.poll(() => page.evaluate(async () => {
    for (const name of (await caches.keys()).filter(n => n.startsWith("phyto-cultures-"))) {
      if (await (await caches.open(name)).match(location.href.split("#")[0])) return true;
    }
    return false;
  })).toBe(true);
  let posts = 0;
  page.on("request", requete => { if (requete.method() === "POST") posts++; });
  await page.context().setOffline(true);
  await page.reload();
  await expect(page.locator("#pwa-connection-banner")).toContainText("lecture seule");
  await expect(page.getByRole("heading", {name: "Repère hors ligne"})).toBeVisible();
  // Hors ligne, une saisie n'est ni envoyée ni mise en attente.
  const article = page.locator("article.culture-journal").filter({hasText: "Repère hors ligne"}).first();
  const annulation = article.locator("form").filter({hasText: "Motif de l’annulation"});
  await expect(annulation.getByRole("button", {name: "Annuler le repère"})).toBeDisabled();
  await expect(annulation.locator('input[name="reason"]')).toBeDisabled();
  await page.context().setOffline(false);
  await page.reload();
  await expect(page.locator('meta[name="phyto-offline-snapshot"]')).toHaveCount(0);
  await expect(page.getByRole("heading", {name: "Repère hors ligne"})).toBeVisible();
  expect(posts).toBe(0);
});
