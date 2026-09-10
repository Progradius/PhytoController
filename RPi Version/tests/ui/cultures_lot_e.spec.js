// Lot E : plages cibles pH/EC facultatives, historisées et contextualisées.
const {test, expect, AxeBuilder} = require("./culture_fixtures");
const {randomUUID} = require("node:crypto");

const post = async (page, path, csrf, command) => {
  const response = await page.request.post(path, {
    headers: {"X-CSRF-Token": csrf, "Content-Type": "application/json"},
    data: {request_id: randomUUID(), ...command},
  });
  expect(response.ok(), await response.text()).toBeTruthy();
  return response.json();
};

test("plages cibles : saisie facultative, historique et contexte des relevés", async ({page}, testInfo) => {
  test.setTimeout(120000);
  test.skip(testInfo.project.name === "pwa-chromium", "Mutations exercées sur profils sans service worker.");
  await page.goto("/cultures/targets");
  const csrf = await page.locator('meta[name="csrf-token"]').getAttribute("content");
  await expect(page.getByRole("heading", {level: 1})).toHaveText("Plages cibles pH et EC");
  await expect(page.getByText("Aucune plage cible pour ce filtre")).toBeVisible();

  // Saisie pH seul, à la virgule décimale, sur le réservoir de l'espace 2.
  await page.locator(".culture-new-entry > summary").click();
  const form = page.locator("[data-target-form][data-operation='target']").first();
  await form.getByRole("combobox", {name: "Cible de la plage"}).selectOption("reservoir_2");
  await form.getByLabel("Intitulé de la plage").fill("Végétatif");
  await form.getByLabel("pH minimum").fill("5,8");
  await form.getByLabel("pH maximum").fill("6,4");
  await form.getByLabel("Début de validité").fill("2026-08-01");
  await form.getByRole("button", {name: "Enregistrer la plage cible"}).click();
  const article = page.locator(".target-item").first();
  await expect(article).toContainText("pH 5,80 à 6,40");
  await expect(article).toContainText("EC — à —");
  const identifier = (await article.getAttribute("id")).replace("target-", "");

  // Refus : une seconde plage recouvrant la même cible ne peut pas coexister.
  await page.locator(".culture-new-entry > summary").click();
  const again = page.locator("[data-target-form][data-operation='target']").first();
  await again.getByRole("combobox", {name: "Cible de la plage"}).selectOption("reservoir_2");
  await again.getByLabel("pH minimum").fill("6,0");
  await again.getByLabel("Début de validité").fill("2026-08-05");
  await again.getByRole("button", {name: "Enregistrer la plage cible"}).click();
  await expect(again.locator(".culture-form-errors")).toContainText("chevauchent");
  // Champs conservés après refus : la saisie n'est jamais perdue.
  await expect(again.getByLabel("pH minimum")).toHaveValue("6,0");

  // R2.7 : sélecteur d'abord, puis la plage applicable et sa source, puis le déclaré.
  // La mesure « premier écran » appartient au script de mesure (`npm run measure:ui`) :
  // cette spec tourne aussi à 196 px, où aucun seuil fixe ne voudrait dire la même chose.
  await page.goto("/cultures/targets?target=reservoir_2");
  const applique = page.locator("#applique");
  await expect(applique.getByRole("heading", {name: "Appliqué maintenant"})).toBeVisible();
  await expect(applique.locator("[data-target-source]")).toHaveText("réservoir");
  await expect(applique).toContainText("pH 5,80 à 6,40");
  await expect(applique.getByRole("group").filter({hasText: "Comment cette valeur est choisie"})).toHaveCount(1);
  // Les faits datés de la cascade sont écrits, même quand ils sont vides : aucune
  // solution n'est encore déclarée sur ce réservoir à cette étape du scénario.
  await expect(applique.locator("[data-target-feeding]"))
    .toHaveText("Aucun sujet alimenté par cette solution à cette date.");
  const hauts = await page.evaluate(() => ["selection", "applique", "plages"]
    .map(id => document.getElementById(id).getBoundingClientRect().top));
  expect(hauts[0]).toBeLessThan(hauts[1]);
  expect(hauts[1]).toBeLessThan(hauts[2]);
  // Aucune rétroactivité : avant le début de la plage, aucune source n'est nommée.
  await page.goto("/cultures/targets?target=reservoir_2&at=2026-07-01");
  await expect(page.locator("[data-target-source]")).toHaveCount(0);
  await expect(page.getByText("Aucune plage applicable à cette date")).toBeVisible();
  await page.goto("/cultures/targets?target=reservoir_2");

  // Clôture de validité, puis seconde période avec ses propres bornes.
  const item = page.locator(`#target-${identifier}`);
  await item.locator("summary").filter({hasText: "Clore la validité"}).click();
  const closing = item.locator("[data-target-form][data-action='end']");
  await closing.getByLabel("Dernier jour de validité").fill("2026-08-10");
  await closing.getByLabel("Motif").fill("Passage en floraison");
  await closing.getByRole("button", {name: "Clore la validité"}).click();
  await expect(page.locator(`#target-${identifier}`)).toContainText("au 10/08/2026");

  const second = await post(page, "/api/v1/cultures/targets", csrf, {operation: "target",
    target: "reservoir_2", label: "Floraison", start_at: "2026-08-10", ph_min: "6,0", ph_max: "6,6",
    ec_min: "1,2", ec_max: "1,8"});

  // Correction traçable de la seconde plage ; la première garde ses bornes.
  // Requête distincte : un simple changement d'ancre ne rechargerait pas la page.
  await page.goto("/cultures/targets?scope=reservoir");
  const later = page.locator(`#target-${second.id}`);
  await later.locator("summary").filter({hasText: "Corriger cette plage"}).click();
  const correction = later.locator("[data-target-form][data-operation='target']");
  await correction.getByLabel("pH maximum").fill("6,8");
  await correction.getByLabel("Motif de la correction").fill("Relevé de laboratoire");
  await correction.getByRole("button", {name: "Enregistrer la correction"}).click();
  await expect(page.locator(`#target-${second.id}`)).toContainText("pH 6,00 à 6,80");
  await page.locator(`#target-${second.id}`).locator("summary").filter({hasText: "Versions précédentes"}).click();
  await expect(page.locator(`#target-${second.id}`)).toContainText("Version 1");
  await expect(page.locator(`#target-${identifier}`)).toContainText("pH 5,80 à 6,40");

  // Contexte sur les relevés : chaque mesure porte la plage de sa propre période.
  await post(page, "/api/v1/cultures/solutions", csrf, {operation: "entry", kind: "renewal",
    reservoir_id: "reservoir_2", effective_at: "2026-08-05", volume_l: 20, ph: "6,1"});
  await post(page, "/api/v1/cultures/solutions", csrf, {operation: "entry", kind: "reading",
    reservoir_id: "reservoir_2", effective_at: "2026-08-15", ph: "6,3"});
  await post(page, "/api/v1/cultures/solutions", csrf, {operation: "entry", kind: "renewal",
    reservoir_id: "cuttings_1", effective_at: "2026-08-05", volume_l: 5});
  await post(page, "/api/v1/cultures/solutions", csrf, {operation: "entry", kind: "reading",
    reservoir_id: "cuttings_1", effective_at: "2026-08-15", ph: "6,3"});
  await page.goto("/cultures/solutions?view=releves&target=reservoir_2");
  const entries = page.locator(".solution-journal");
  // Les bornes du journal passent par le filtre `nombre` : virgule et deux décimales.
  await expect(entries.first()).toContainText("Plage cible : pH 6,00 à 6,80");
  await expect(entries.nth(1)).toContainText("Plage cible : pH 5,80 à 6,40");
  // Une cible sans plage reste sans plage : aucune bande par défaut n'est inventée.
  await page.goto("/cultures/solutions?view=releves&target=cuttings_1");
  await expect(page.locator(".solution-journal").first()).toContainText("Aucune plage cible à cette date");
  await expect(page.locator(".solution-target-band")).toHaveCount(0);

  await page.goto("/cultures/solutions?view=analyser&target=reservoir_2");
  // Les bandes ne couvrent que les périodes réellement résolues.
  await expect(page.locator("svg[data-metric='ph'] .solution-target-band").first()).toBeVisible();
  await expect(page.locator("svg[data-metric='ec'] .solution-target-band")).toHaveCount(0);

  // Export : deux colonnes de cible résolue à la date de chaque relevé.
  const csv = await (await page.request.get("/api/v1/cultures/solutions/export?target=reservoir_2")).text();
  expect(csv).toContain("ph_cible");
  expect(csv).toContain("6.0 à 6.8");
  const targetsCsv = await (await page.request.get("/api/v1/cultures/targets/export?format=csv")).text();
  expect(targetsCsv).toContain("ec_min_mS_cm");

  // Annulation traçable : la plage sort de la résolution sans disparaître du carnet.
  await page.goto("/cultures/targets?target=reservoir_2");
  const cancelling = page.locator(`#target-${second.id}`);
  await cancelling.locator("summary").filter({hasText: "Annuler cette plage"}).click();
  const cancelForm = cancelling.locator("[data-target-form][data-action='cancel']");
  await cancelForm.getByLabel("Motif de l’annulation").fill("Saisie en double");
  await cancelForm.getByRole("button", {name: "Annuler la plage"}).click();
  await expect(page.locator(`#target-${second.id}`)).toContainText("annulée");
  await page.goto("/cultures/solutions?view=releves&target=reservoir_2");
  await expect(page.locator(".solution-journal").first()).toContainText("Aucune plage cible à cette date");

  expect(await page.evaluate(() => document.documentElement.scrollWidth - innerWidth)).toBeLessThanOrEqual(1);
  expect((await new AxeBuilder({page}).analyze()).violations).toEqual([]);
});
