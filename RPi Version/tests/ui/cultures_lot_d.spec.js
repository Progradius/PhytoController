"use strict";

// Lot D : une case cochée par erreur se corrige puis s'annule sans perdre l'historique,
// un onglet périmé reçoit un conflit et une correction rétrospective du parcours est signalée.
const {test, expect, AxeBuilder} = require("./culture_fixtures");

// Dates locales relatives au jour courant : le carnet refuse toute date future et la
// vérification ne peut pas précéder le début du stade en cours.
const day = offset => {
  const value = new Date();
  value.setDate(value.getDate() - offset);
  return `${value.getFullYear()}-${String(value.getMonth() + 1).padStart(2, "0")}-${String(value.getDate()).padStart(2, "0")}`;
};

const mutate = (page, path, command) => page.evaluate(async ([target, body]) => {
  const response = await fetch(target, {
    method: "POST",
    headers: {"X-CSRF-Token": document.querySelector('meta[name="csrf-token"]').content,
      "Content-Type": "application/json"},
    body: JSON.stringify({...body, request_id: crypto.randomUUID()}),
  });
  return {status: response.status, body: await response.json()};
}, [path, command]);

const submit = async (page, form, path = "/api/v1/cultures/cycles") => {
  const answer = page.waitForResponse(r => r.url().endsWith(path) && r.request().method() === "POST");
  await form.locator('[type="submit"]').click();
  return answer;
};

// La section des vérifications et chaque formulaire vivent dans un <details> replié :
// tant qu'il l'est, son contenu reste hors de l'arbre d'accessibilité.
const openSection = async page => {
  const section = page.locator("details").filter({hasText: "Vérifier les équipements pour le stade"}).first();
  if ((await section.getAttribute("open")) === null) await section.locator(":scope > summary").click();
  await expect(section).toHaveAttribute("open", /.*/);
};
const reveal = async (page, form) => {
  await openSection(page);
  // Le formulaire de saisie est un enfant direct de la section : ne pas la replier.
  const parent = form.locator("..");
  if ((await parent.evaluate(node => node.tagName)) === "DETAILS" && (await parent.getAttribute("open")) === null) {
    await parent.locator(":scope > summary").click();
  }
};

test("vérifications : correction, annulation, historique, conflit d'onglet et de parcours", async ({page}, testInfo) => {
  test.skip(!["desktop-chromium", "mobile-chromium"].includes(testInfo.project.name),
    "Vérifications corrigibles exercées sur deux formats.");
  test.setTimeout(60000);
  const name = `Vérifications ${testInfo.project.name} ${Date.now()}`;
  await page.goto("/cultures");
  // L'espace 1 n'est pas exclusif : ce lot cohabite avec les autres scénarios du même carnet.
  const created = await mutate(page, "/api/v1/cultures", {
    operation: "create", kind: "lot", name, stage: "germination", space: "space_1",
    origin_at: day(7), space_at: day(7), stage_at: day(7),
    origins: [{label: "Semences vérifications", count: 4}],
  });
  expect(created.status, JSON.stringify(created.body)).toBe(200);
  const subject = created.body.subject_id;
  // Les vérifications d'équipement vivent dans la vue « Comparer » de la page ; la vue par
  // défaut est « À faire », dont le panneau frère est `hidden`. La demander explicitement
  // évite de piloter un formulaire hors de l'arbre d'accessibilité.
  const cycles = `/cultures/cycles?subject=${subject}&view=comparer`;
  await page.goto(cycles);

  // 1. Case cochée par erreur : la ventilation n'a pas été vérifiée ce jour-là.
  const entry = page.locator('form[data-operation="checklist"]');
  await reveal(page, entry);
  await entry.locator('[name="lighting"]').check();
  await entry.locator('[name="ventilation"]').check();
  await entry.locator('[name="note"]').fill("Tour de serre du matin");
  const saved = await submit(page, entry);
  expect(saved.status(), saved.status() === 200 ? "" : await saved.text()).toBe(200);
  await page.waitForLoadState("domcontentloaded");

  await openSection(page);
  const card = page.locator("article.culture-checklist");
  await expect(card).toHaveCount(1);
  await expect(card).toContainText("révision 1");
  await expect(card).toContainText("ventilation vérifiée");
  await expect(card).toContainText(`contexte enregistré : Germination · Espace 1 · début du stade`);
  await expect(card.getByRole("alert")).toHaveCount(0);

  // 2. Onglet périmé ouvert AVANT la correction : sa version attendue deviendra caduque.
  const stale = await page.context().newPage();
  await stale.goto(cycles);
  const staleForm = stale.locator('form[data-operation="checklist_cancel"]');
  await reveal(stale, staleForm);
  await staleForm.locator('[name="reason"]').fill("Annulation depuis un onglet resté ouvert");

  // 3. Correction motivée : la case fautive est décochée, l'ancienne version reste lisible.
  const correction = page.locator('form[data-operation="checklist_correct"]');
  await reveal(page, correction);
  await correction.locator('[name="ventilation"]').uncheck();
  await correction.locator('[name="reason"]').fill("Ventilation cochée par erreur");
  const corrected = await submit(page, correction);
  expect(corrected.status(), corrected.status() === 200 ? "" : await corrected.text()).toBe(200);
  await page.waitForLoadState("domcontentloaded");
  await openSection(page);
  await expect(card).toContainText("révision 2");
  await expect(card).toContainText("ventilation à vérifier");
  await expect(card).toContainText("Motif : Ventilation cochée par erreur");
  const history = card.locator("details").filter({hasText: "Historique de la vérification"});
  await history.locator("summary").click();
  await expect(history).toContainText("Révision 1");
  await expect(history).toContainText("ventilation vérifiée");

  // 4. L'onglet périmé reçoit un conflit : rien n'est écrit, la saisie reste dans la page.
  const refused = await submit(stale, staleForm);
  expect(refused.status()).toBe(409);
  await expect(staleForm.locator(".culture-form-errors")).toContainText("actualiser");
  await expect(staleForm.locator(".culture-form-errors")).toContainText("Ouvrir la fiche actuelle dans un nouvel onglet.");
  await expect(staleForm.locator('[name="reason"]')).toHaveValue("Annulation depuis un onglet resté ouvert");
  await stale.close();

  // 5. Correction rétrospective du parcours : le contexte enregistré devient contradictoire
  // et le conflit est signalé sans réécriture silencieuse.
  const detail = await page.evaluate(async id => (await (await fetch(`/api/v1/cultures/${id}`)).json()).subject.version, subject);
  const stage = await mutate(page, "/api/v1/cultures", {
    operation: "event", subject_id: subject, version: detail, kind: "stage",
    effective_at: day(2), payload: {stage: "vegetatif"},
  });
  expect(stage.status, JSON.stringify(stage.body)).toBe(200);
  await page.goto(cycles);
  await openSection(page);
  await expect(card.getByRole("alert")).toContainText("Conflit avec une correction du parcours");
  await expect(card.getByRole("alert")).toContainText("Végétatif");
  await expect(card.getByRole("alert")).toContainText("corriger ou annuler cette vérification");
  // Le contexte enregistré reste celui de la saisie : aucun stade n'a été réécrit.
  await expect(card).toContainText("contexte enregistré : Germination");

  // 6. Annulation motivée : la vérification disparaît des affirmations, pas de l'historique.
  const cancel = page.locator('form[data-operation="checklist_cancel"]');
  await reveal(page, cancel);
  await cancel.locator('[name="reason"]').fill("Vérification finalement attribuée au mauvais lot");
  const cancelled = await submit(page, cancel);
  expect(cancelled.status(), cancelled.status() === 200 ? "" : await cancelled.text()).toBe(200);
  await page.waitForLoadState("domcontentloaded");
  await openSection(page);
  await expect(card).toContainText("ANNULÉE");
  await expect(card).toContainText("Motif : Vérification finalement attribuée au mauvais lot");
  await expect(card.getByRole("alert")).toHaveCount(0);
  await expect(page.locator('form[data-operation="checklist_correct"]')).toHaveCount(0);
  const closed = card.locator("details").filter({hasText: "Historique de la vérification"});
  await closed.locator("summary").click();
  await expect(closed).toContainText("Révision 1");
  await expect(closed).toContainText("Révision 2");

  expect(await page.evaluate(() => document.documentElement.scrollWidth - innerWidth)).toBeLessThanOrEqual(1);
  expect((await new AxeBuilder({page}).analyze()).violations).toEqual([]);
});
