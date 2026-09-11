// Lot E : plages cibles pH/EC facultatives, historisées et contextualisées.
const {test, expect, AxeBuilder, createMother} = require("./culture_fixtures");
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
  // Le premier écran est vérifié à 390 × 844 par le test dédié en fin de fichier (et par
  // `npm run measure:ui`) : ce scénario tourne sur tous les profils, où aucun seuil fixe ne
  // voudrait dire la même chose.
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

// R2.7 (écart E8) : avec une cible consultée qui porte une plage directe, à 390 × 844, le titre
// « Appliqué maintenant », la plage et sa source tiennent **entières** dans la zone utile du
// premier écran — la fenêtre moins la barre basse fixe, comme dans `measure_pages.js`. Ils
// étaient à y = 857, 888 et 914, sous la barre. La portée, qui ne filtre que la liste, vit
// désormais avec elle : son filtre reconduit la cible et la date, et inversement.
test("plages cibles : la plage appliquée et sa source dans le premier écran d’un téléphone", async ({page}, testInfo) => {
  test.skip(testInfo.project.name !== "mobile-chromium", "Critère de premier écran à 390 × 844, mesuré sur le profil mobile de référence.");
  test.setTimeout(90000);
  const subject = await createMother(page, "Mère premier écran");
  await page.goto("/cultures/targets");
  const csrf = await page.locator('meta[name="csrf-token"]').getAttribute("content");
  await post(page, "/api/v1/cultures/targets", csrf, {operation: "target", target: subject, label: "Plage directe",
    start_at: "2026-08-01", ph_min: "5,8", ph_max: "6,4", ec_min: "1,2", ec_max: "1,8"});
  await page.setViewportSize({width: 390, height: 844});
  await page.goto(`/cultures/targets?target=${encodeURIComponent(subject)}`);
  await expect(page.locator("#applique [data-target-source]")).toHaveText("cible directe");
  await page.evaluate(() => document.fonts.ready.then(() => true));
  const mesure = await page.evaluate(() => {
    const barres = [...document.querySelectorAll("body *")].filter(node => {
      const style = getComputedStyle(node), r = node.getBoundingClientRect();
      return (style.position === "fixed" || style.position === "sticky") && style.display !== "none"
        && r.width >= innerWidth / 2 && r.height > 0 && r.height < innerHeight / 2 && r.bottom >= innerHeight - 1 && r.top < innerHeight;
    });
    const bas = Math.min(innerHeight, ...barres.map(node => node.getBoundingClientRect().top));
    const boite = selector => {
      const r = document.querySelector(selector).getBoundingClientRect();
      return {haut: Math.round(r.top), bas: Math.round(r.bottom)};
    };
    return {defilement: scrollY, hauteur: innerHeight, zoneBas: Math.round(bas),
      titre: boite("#applique h2"), plage: boite("#applique [data-target-applied]"), source: boite("#applique [data-target-source]")};
  });
  await testInfo.attach("premier-ecran-plages", {body: JSON.stringify(mesure), contentType: "application/json"});
  expect(mesure.defilement).toBe(0);
  expect(mesure.hauteur).toBe(844);
  // La barre basse existe bien à cette largeur : sans elle, le critère serait trop facile.
  expect(mesure.zoneBas).toBeLessThan(844);
  for (const nom of ["titre", "plage", "source"]) {
    expect(mesure[nom].haut, nom).toBeGreaterThanOrEqual(0);
    expect(mesure[nom].bas, `${nom} : ${JSON.stringify(mesure)}`).toBeLessThanOrEqual(mesure.zoneBas);
  }

  // Rien n'a été retiré : la portée filtre toujours la liste, depuis la liste, en gardant la
  // cible consultée ; et le sélecteur de tête reconduit la portée choisie.
  const portee = page.locator("#plages form[method=\"get\"]");
  await portee.getByLabel("Portée affichée").selectOption("reservoir");
  await portee.getByRole("button", {name: "Filtrer la liste"}).click();
  await expect(page).toHaveURL(/scope=reservoir/);
  expect(new URL(page.url()).searchParams.get("target")).toBe(subject);
  await expect(page.locator("#applique [data-target-source]")).toHaveText("cible directe");
  await expect(page.locator(".target-item")).toHaveCount(0);
  await expect(page.locator('#selection input[type="hidden"][name="scope"]')).toHaveValue("reservoir");
  await page.locator("#selection").getByRole("button", {name: "Afficher"}).click();
  expect(new URL(page.url()).searchParams.get("scope")).toBe("reservoir");
  expect((await new AxeBuilder({page}).analyze()).violations).toEqual([]);
});
