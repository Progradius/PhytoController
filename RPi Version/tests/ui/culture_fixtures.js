"use strict";

const {test: base, expect, servir} = require("./serveurs");
const AxeBuilder = require("@axe-core/playwright").default;

// Chaque test possède son carnet : l'espace 2 est exclusif et une occupation en
// cours s'étend sans date de fin, donc deux scénarios ne peuvent pas partager une
// base sans se disputer l'espace ni fausser les comptages du journal.
const test = base.extend({
  cultureBaseURL: [async ({zygote}, use) => {
    // La garde vit DANS la fixture, jamais dans un `test.beforeEach` de module : le cache
    // CommonJS n'exécute ce fichier qu'une fois par worker, donc un hook de module ne
    // s'attacherait qu'au premier fichier de spec chargé et laisserait les suivants écrire
    // dans le carnet visé par PHYTO_UI_BASE_URL — un carnet de production, le cas échéant.
    // Ici la garde est traversée par chaque test qui demande la fixture, quel que soit son
    // fichier. Ces scénarios écrivent UNIQUEMENT dans la base temporaire de tests/ui_server.py.
    test.skip(Boolean(process.env.PHYTO_UI_BASE_URL), "Aucune création de culture sur une cible externe.");
    // Un serveur neuf pour ce seul test (`tests/ui/serveurs.js`), démarré après la garde.
    await servir(zygote, {}, use);
  // Le démarrage du serveur (interpréteur, schéma, WAL) a son propre délai, distinct du
  // délai du test : sous contention (suite complète, autre charge sur la machine) il a
  // dépassé les 20 s du délai global et faisait échouer des scénarios sans rapport.
  }, {scope: "test", timeout: 60000}],
  baseURL: async ({cultureBaseURL}, use) => use(cultureBaseURL),
});

// Trois dates saisies à la main = une culture déjà en cours. Le mode « Je démarre une
// culture » ne demande que la date d'origine et replie les deux autres, qu'il recopie :
// la reprise est donc choisie explicitement avant de les remplir.
const dates = async form => {
  await form.getByRole("radio", {name: "Elle est déjà en cours"}).check();
  for (const name of ["origin_at", "space_at", "stage_at"]) await form.locator(`[name="${name}"]`).fill("2026-08-01");
};
const createMother = async (page, name) => {
  await page.goto("/cultures");
  const details = page.locator("details.culture-create").filter({hasText: "Ajouter un pied mère"});
  await details.locator("summary").click();
  const form = details.locator("form");
  await form.getByLabel("Nom", {exact: true}).fill(name);
  await dates(form);
  await form.getByRole("button", {name: "Ajouter un pied mère", exact: true}).click();
  await expect(page.getByRole("heading", {level: 1})).toHaveText(name);
  return page.url().split("/").pop();
};

// PNG 1×1 valide, construit en mémoire : aucune image de l'exploitation n'entre ici.
// Partagé par toutes les specs photo, pour qu'un même octet soit envoyé partout.
const PNG_1x1 = Buffer.from(
  "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg==",
  "base64");

module.exports = {test, expect, AxeBuilder, dates, createMother, PNG_1x1};
