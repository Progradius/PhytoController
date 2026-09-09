"use strict";

// Remédiation R3.4 du lot UI 4 : recherche libre du journal transversal et filtres
// rapides 7 / 30 jours. Tout y est en GET : aucune mutation nouvelle, aucune persistance,
// aucune règle métier en JS — les deux fenêtres sont calculées par le serveur à partir de
// l'unique date du carnet.
const {test, expect, AxeBuilder, createMother} = require("./culture_fixtures");

const observe = async (page, note, space = "Espace 2") => {
  const details = page.locator("details").filter({hasText: "Enregistrer une observation d’espace"}).first();
  await details.locator("summary").click();
  const form = details.locator("form");
  await form.getByLabel("Espace observé").selectOption({label: space});
  await form.getByLabel("Observation", {exact: true}).fill(note);
  await form.getByRole("button", {name: "Enregistrer l’observation"}).click();
  await expect(page.getByText(note, {exact: false}).first()).toBeVisible();
};

// La date du carnet est celle que le serveur propose à la saisie : la lire ici évite d'en
// recalculer une seconde côté spec, qui divergerait au passage de minuit ou de fuseau.
const journalToday = async page => {
  const details = page.locator("details").filter({hasText: "Enregistrer une observation d’espace"}).first();
  await details.locator("summary").click();
  return details.locator('form [name="effective_at"]').inputValue();
};

const shift = (day, days) => {
  const moment = new Date(`${day}T12:00:00Z`);
  moment.setUTCDate(moment.getUTCDate() - days);
  return moment.toISOString().slice(0, 10);
};

test("journal : recherche insensible aux accents, bornée et combinée aux filtres", async ({page}, testInfo) => {
  test.skip(testInfo.project.name === "pwa-chromium", "Parcours avec mutations, hors service worker.");
  test.setTimeout(90000);
  await createMother(page, "Épinard géant");
  await page.goto("/cultures/journal");
  await observe(page, "Épinard tacheté sur le bac de droite");
  await observe(page, "Bac rincé, dosage à 100% du volume", "Espace 1");

  const filters = page.locator("details.culture-filters");
  await filters.locator("summary").click();
  const search = filters.getByLabel("Rechercher");
  await expect(search).toHaveAttribute("maxlength", "120");
  // « epinard » trouve « Épinard » : la normalisation est faite en SQL, des deux côtés.
  await search.fill("epinard");
  await filters.getByRole("button", {name: "Afficher le journal"}).click();
  const entries = page.locator("article.culture-journal-entry");
  await expect(entries.filter({hasText: "Épinard tacheté"})).toHaveCount(1);
  await expect(entries.filter({hasText: "Bac rincé"})).toHaveCount(0);
  // La recherche est reconduite dans la page : elle n'est pas perdue à l'affichage.
  await expect(page.locator('details.culture-filters [name="q"]')).toHaveValue("epinard");
  expect(new URL(page.url()).searchParams.get("q")).toBe("epinard");

  // Le joker `%` du texte cherché est littéral : il ne ramène pas tout le journal.
  await page.goto("/cultures/journal?q=100%25");
  await expect(entries).toHaveCount(1);
  await expect(entries.first()).toContainText("dosage à 100%");
  await page.goto("/cultures/journal?q=%25");
  await expect(entries).toHaveCount(1);

  // Une saisie déraisonnable n'est ni une erreur serveur ni une page cassée : elle est
  // bornée à 120 caractères et la page reste lisible.
  const response = await page.goto(`/cultures/journal?q=${"z".repeat(400)}`);
  expect(response.status()).toBe(200);
  await expect(page.getByText("Aucune opération pour ce filtre")).toBeVisible();
  await expect(page.locator('details.culture-filters [name="q"]')).toHaveValue("z".repeat(120));

  // La recherche se combine aux autres filtres au lieu de les remplacer.
  // « bac » figure dans les deux notes ; seule la cible départage.
  await page.goto("/cultures/journal?q=bac&target=space_1");
  await expect(entries).toHaveCount(1);
  await expect(entries.first()).toContainText("Bac rincé");
  await page.goto("/cultures/journal?q=bac&target=space_2");
  await expect(entries).toHaveCount(1);
  await expect(entries.first()).toContainText("Épinard tacheté");
  await page.goto("/cultures/journal?q=rinc%C3%A9&target=space_2");
  await expect(entries).toHaveCount(0);
  expect((await new AxeBuilder({page}).analyze()).violations).toEqual([]);
});

test("journal : filtres rapides 7 et 30 jours calculés sur la date du carnet", async ({page}, testInfo) => {
  test.skip(testInfo.project.name === "pwa-chromium", "Parcours avec mutations, hors service worker.");
  test.setTimeout(90000);
  await page.goto("/cultures/journal");
  await observe(page, "Épinard tacheté sur le bac de droite");
  const today = await journalToday(page);

  await page.goto("/cultures/journal?q=epinard&target=space_2");
  const quick = page.getByRole("navigation", {name: "Périodes rapides"});
  // Les deux raccourcis remplissent start/end à partir de la seule date du carnet, et
  // reconduisent la recherche et la cible courantes : la page ne perd aucun filtre.
  for (const [label, days] of [["7 jours", 7], ["30 jours", 30]]) {
    const href = await quick.getByRole("link", {name: label, exact: true}).getAttribute("href");
    const params = new URL(href, page.url()).searchParams;
    expect(params.get("end")).toBe(today);
    expect(params.get("start")).toBe(shift(today, days - 1));
    expect(params.get("q")).toBe("epinard");
    expect(params.get("target")).toBe("space_2");
  }
  await quick.getByRole("link", {name: "7 jours", exact: true}).click();
  const filters = page.locator("details.culture-filters");
  await filters.locator("summary").click();
  await expect(filters.locator('[name="start"]')).toHaveValue(shift(today, 6));
  await expect(filters.locator('[name="end"]')).toHaveValue(today);
  await expect(filters.locator('[name="q"]')).toHaveValue("epinard");
  await expect(page.locator("article.culture-journal-entry")).toHaveCount(1);

  // « Toute la période » retire les deux dates sans toucher au reste du filtre.
  await quick.getByRole("link", {name: "Toute la période", exact: true}).click();
  const params = new URL(page.url()).searchParams;
  expect(params.has("start")).toBe(false);
  expect(params.has("end")).toBe(false);
  expect(params.get("q")).toBe("epinard");
  expect(params.get("target")).toBe("space_2");
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
  expect((await new AxeBuilder({page}).analyze()).violations).toEqual([]);
  await page.screenshot({path: testInfo.outputPath("journal-periodes-rapides.png"), fullPage: true});
});
