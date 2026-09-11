// Lot A : correction d'un relevé dont l'intervention est devenue ancienne.
const {test, expect, AxeBuilder} = require("./culture_fixtures");
const {randomUUID} = require("node:crypto");
const {sauf} = require("./profils");

const post = async (page, csrf, command) => {
  const response = await page.request.post("/api/v1/cultures/solutions", {
    headers: {"X-CSRF-Token": csrf, "Content-Type": "application/json"},
    data: {request_id: randomUUID(), ...command},
  });
  expect(response.ok(), await response.text()).toBeTruthy();
  return response.json();
};

test("relevé ancien : lien conservé, recherche bornée et refus sans doublon", sauf("Mutations exercées sur profils sans service worker.", "pwa-chromium"), async ({page}, testInfo) => {
  test.setTimeout(180000);
  await page.goto("/cultures/solutions");
  const csrf = await page.locator('meta[name="csrf-token"]').getAttribute("content");
  const renewal = await post(page, csrf, {operation: "entry", kind: "renewal", reservoir_id: "reservoir_2",
    effective_at: "2026-08-01", volume_l: 20});
  await post(page, csrf, {operation: "entry", kind: "renewal", reservoir_id: "cuttings_1",
    effective_at: "2026-08-01", volume_l: 5});
  const reading = await post(page, csrf, {operation: "entry", kind: "reading", reservoir_id: "reservoir_2",
    effective_at: "2026-08-01", ph: 6, intervention_id: renewal.id, context: "after"});
  // Plus de 200 interventions ultérieures, sur deux cibles : le lien sort de la fenêtre proposée.
  for (let index = 0; index < 201; index += 1) {
    await post(page, csrf, {operation: "entry", kind: "topup",
      reservoir_id: index % 2 ? "reservoir_2" : "cuttings_1",
      effective_at: `2026-08-${String((index % 28) + 1).padStart(2, "0")}`, volume_l: 1});
  }
  const lookup = await (await page.request.get("/api/v1/cultures/solutions?interventions=")).json();
  expect(lookup.interventions_total).toBe(203);
  expect(lookup.interventions.some(item => item.id === renewal.id)).toBeFalsy();

  await page.goto(`/cultures/solutions?entry=${reading.id}#entry-${reading.id}`);
  const article = page.locator(`#entry-${reading.id}`);
  await expect(article).toContainText("Après intervention");
  // R1.6 : un relevé se lit en une ligne ; contexte, traçabilité et correction vivent dans
  // son repli « Détails ». Le lien `?entry=…#entry-…` amène bien sur l'entrée, dans la vue
  // « Relevés » ; c'est l'opérateur qui déplie ce qu'il veut corriger.
  await article.locator(".solution-entry-details > summary").click();
  await article.getByText("Corriger cette saisie", {exact: true}).click();
  const correction = article.locator("form.solution-form");
  // L'intervention associée reste proposée et sélectionnée malgré son ancienneté.
  await expect(correction.locator('[name="intervention_id"]')).toHaveValue(renewal.id);
  await correction.getByLabel("pH", {exact: true}).fill("6,5");
  await correction.getByRole("button", {name: "Enregistrer la correction"}).click();
  const corrected = page.locator(`#entry-${reading.id}`);
  // R1.7 : la valeur affichée passe par le filtre `nombre` (virgule, deux décimales) ;
  // la valeur persistée, elle, reste 6.5 — c'est l'API qui en fait foi.
  await expect(corrected).toContainText("pH 6,50");
  await corrected.locator(".solution-entry-details > summary").click();
  await expect(corrected.getByRole("link", {name: `Intervention ${renewal.id.slice(0, 8)}`})).toBeVisible();

  // Saisie rétrospective : la recherche bornée retrouve l'intervention ancienne. C'est une
  // saisie neuve, donc la vue « Saisir » — l'enregistrement précédent a laissé la page sur
  // « Relevés », où le bloc de saisie est servi mais `hidden`.
  await page.goto("/cultures/solutions?view=saisir");
  const saisie = page.locator("#saisie");
  if ((await saisie.getAttribute("open")) === null) await saisie.locator(":scope > summary").click();
  const quick = page.locator("[data-solution-entry]").first();
  await expect(quick).toBeVisible();
  await quick.getByText("Température, volume, contexte et note", {exact: true}).click();
  await quick.getByLabel("Retrouver une intervention ancienne").fill(renewal.id.slice(0, 8));
  await quick.getByRole("button", {name: "Rechercher", exact: true}).click();
  await expect(quick.locator("[data-intervention-status]")).toContainText("1 intervention(s) trouvée(s)");
  await expect(quick.locator('[name="intervention_id"] option')).toHaveCount(2);
  await quick.locator('[name="intervention_id"]').selectOption(renewal.id);

  // Association incohérente : refus sans écriture, champs conservés, aucune duplication.
  const before = (await (await page.request.get("/api/v1/cultures/solutions")).json()).total;
  await quick.getByRole("combobox", {name: "Cible", exact: true}).selectOption("cuttings_1");
  await quick.getByLabel("pH", {exact: true}).fill("6,1");
  await quick.getByRole("combobox", {name: "Contexte du relevé", exact: true}).selectOption("after");
  for (let attempt = 0; attempt < 2; attempt += 1) {
    await quick.getByRole("button", {name: "Enregistrer la saisie"}).click();
    await expect(quick.locator(".culture-form-errors")).toContainText("Saisie conservée");
    await expect(quick.getByLabel("pH", {exact: true})).toHaveValue("6,1");
  }
  const after = (await (await page.request.get("/api/v1/cultures/solutions")).json()).total;
  expect(after).toBe(before);

  expect(await page.evaluate(() => document.documentElement.scrollWidth - innerWidth)).toBeLessThanOrEqual(1);
  expect((await new AxeBuilder({page}).analyze()).violations).toEqual([]);
});
