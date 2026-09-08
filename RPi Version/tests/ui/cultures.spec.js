// Fixture partagée : serveur de carnet temporaire par test, aides de création.
const {test, expect, AxeBuilder, dates, createMother} = require("./culture_fixtures");

test("lot multi-mères, carnet et correction sur téléphone et bureau", async ({page}, testInfo) => {
  test.skip(testInfo.project.name === "pwa-chromium", "Parcours PWA exercé séparément.");
  const suffix = `${testInfo.project.name}-${Date.now()}`;
  const motherA = await createMother(page, `Mère A ${suffix}`);
  const motherB = await createMother(page, `Mère B ${suffix}`);
  await page.goto("/cultures");
  const details = page.locator("details.culture-create").filter({hasText: "Créer un lot"});
  await details.locator("summary").click();
  const form = details.locator("form");
  await form.getByLabel("Nom", {exact: true}).fill(`Boutures ${suffix}`);
  await form.getByLabel("Origine du lot").selectOption("cutting");
  await form.locator('[name="mother_id"]').selectOption(motherA);
  await form.locator('[name="origin_count"]').fill("3");
  await form.getByRole("button", {name: "Ajouter une origine", exact: true}).click();
  await form.locator('[name="mother_id"]').nth(1).selectOption(motherB);
  await form.locator('[name="origin_count"]').nth(1).fill("5");
  await dates(form);
  await form.getByRole("button", {name: "Créer un lot", exact: true}).click();
  await expect(page.getByRole("heading", {level: 1})).toHaveText(`Boutures ${suffix}`);
  await expect(page.getByText("8 plantes restantes · 8 au départ")).toBeVisible();
  await expect(page.getByText("Enracinement · J", {exact: false})).toBeVisible();
  const lotUrl = page.url();
  // Lot UI 2 : la note et sa photo sont un seul parcours, promu dans la triade d'en-tête.
  const note = page.locator("form[data-culture-observation]");
  await note.locator("..").locator("summary").click();
  await note.getByLabel("Observation", {exact: true}).fill("Observation du lot\nFeuilles suivies");
  await note.getByRole("button", {name: "Enregistrer l’observation", exact: true}).click();
  await expect(page.locator(".culture-journal .culture-note")).toContainText("Observation du lot");
  const correction = page.locator('form[data-culture-correct][data-kind="note"]');
  await correction.locator("..").locator("summary").click();
  await correction.getByRole("textbox", {name: "Note", exact: true}).fill("Observation corrigée");
  await correction.getByRole("button", {name: "Enregistrer la correction"}).click();
  await expect(page.locator(".culture-journal").filter({hasText: "Observation corrigée"})).toBeVisible();
  await page.getByText("Versions précédentes (1)", {exact: true}).click();
  await expect(page.getByText("Observation du lot", {exact: false})).toBeVisible();
  const overflow = await page.evaluate(() => document.documentElement.scrollWidth - innerWidth);
  expect(overflow).toBeLessThanOrEqual(1);
  const results = await new AxeBuilder({page}).analyze();
  expect(results.violations).toEqual([]);
  if (["desktop-chromium", "mobile-etroit"].includes(testInfo.project.name)) {
    await page.screenshot({path: `/tmp/phyto-culture-${testInfo.project.name}.png`, fullPage: true});
  }
  await page.goto(`/cultures/${motherA}`);
  await expect(page.getByRole("link", {name: `Boutures ${suffix}`})).toHaveAttribute("href", new URL(lotUrl).pathname);
});

test("un échec conserve la note et la nouvelle tentative garde sa clé", async ({page}, testInfo) => {
  test.skip(testInfo.project.name !== "desktop-chromium", "Une vérification réseau suffit.");
  await createMother(page, `Mère réseau ${Date.now()}`);
  const note = page.locator("form[data-culture-observation]");
  await note.locator("..").locator("summary").click();
  await note.getByLabel("Observation", {exact: true}).fill("Ne pas perdre cette note");
  const bodies = [];
  await page.route("**/api/v1/cultures", async route => {
    if (route.request().method() !== "POST") return route.continue();
    bodies.push(route.request().postDataJSON());
    if (bodies.length === 1) return route.abort();
    return route.continue();
  });
  const send = () => note.getByRole("button", {name: "Enregistrer l’observation", exact: true}).click();
  await send();
  // Le refus est désormais porté par le résumé d'erreur du socle commun, pas par l'état.
  await expect(note.locator(".culture-form-errors")).toContainText("Saisie conservée");
  await expect(note.getByLabel("Observation", {exact: true})).toHaveValue("Ne pas perdre cette note");
  await send();
  await expect(page.locator(".culture-journal .culture-note")).toHaveText("Ne pas perdre cette note");
  expect(bodies[0].request_id).toBe(bodies[1].request_id);
});

test("vue cultures sans débordement et accessible", async ({page}, testInfo) => {
  await page.goto("/cultures");
  await expect(page.getByRole("heading", {name: "Cultures", exact: true})).toBeVisible();
  expect(await page.evaluate(() => document.documentElement.scrollWidth - innerWidth)).toBeLessThanOrEqual(1);
  expect((await new AxeBuilder({page}).analyze()).violations).toEqual([]);
});

test("semis, correction d’effectif, transfert, récolte et libération", async ({page}, testInfo) => {
  test.skip(!["desktop-chromium", "mobile-chromium"].includes(testInfo.project.name), "Cycle complet sur deux formats.");
  test.setTimeout(45000);
  const name = `Semis cycle ${testInfo.project.name} ${Date.now()}`;
  await page.goto("/cultures");
  const details = page.locator("details.culture-create").filter({hasText: "Créer un lot"});
  await details.locator("summary").click();
  const form = details.locator("form");
  await form.getByLabel("Nom", {exact: true}).fill(name);
  await form.getByLabel("Origine des semences").fill("Semences A");
  await form.locator('[name="origin_count"]').fill("8");
  await dates(form);
  await form.getByRole("button", {name: "Créer un lot", exact: true}).click();
  await expect(page.getByRole("heading", {level: 1})).toHaveText(name);
  const correction = page.locator('form[data-culture-correct][data-kind="create"]');
  await correction.locator("..").locator("summary").click();
  await correction.getByLabel("Effectif initial").fill("9");
  await correction.getByRole("button", {name: "Enregistrer la correction"}).click();
  await expect(page.getByText("9 plantes restantes · 9 au départ")).toBeVisible();
  const perform = async (kind, date, fill) => {
    const action = page.locator(`form[data-culture-event][data-kind="${kind}"]`);
    // Lot UI 2 : une opération non promue dans la triade est repliée sous « Autres
    // opérations ». Ouvrir tous les replis qui la portent, pas seulement le sien.
    await action.evaluate(el => {
      for (let node = el.parentElement; node; node = node.parentElement) {
        if (node.tagName === "DETAILS") node.open = true;
      }
    });
    await action.locator('[name="effective_at"]').fill(date);
    if (fill) await fill(action);
    const response = page.waitForResponse(r => r.url().endsWith("/api/v1/cultures") && r.request().method() === "POST");
    await action.locator('[type="submit"]').click();
    const received = await response;
    // Après succès, la navigation peut déjà avoir libéré le corps de réponse.
    const error = received.status() === 200 ? "" : await received.text();
    expect(received.status(), error).toBe(200);
    await page.waitForLoadState("domcontentloaded");
  };
  await perform("stage", "2026-08-03", f => f.locator('[name="stage"]').selectOption("vegetatif"));
  await expect(page.getByText("Végétatif · J", {exact: false})).toBeVisible();
  await perform("move", "2026-08-10", f => f.locator('[name="space"]').selectOption("space_2"));
  await expect(page.getByText("Espace 2 · En cours", {exact: true})).toBeVisible();
  await perform("stage", "2026-08-15", f => f.locator('[name="stage"]').selectOption("floraison"));
  await expect(page.getByText("Floraison · J", {exact: false})).toBeVisible();
  await perform("harvest", "2026-09-01", f => f.locator('[name="drying_at"]').fill("2026-09-02"));
  await expect(page.getByText("Séchage · J", {exact: false})).toBeVisible();
  await perform("finish", "2026-09-06", async f => {
    await f.locator('[name="weight_g"]').fill("102,5");
    await f.locator('[name="release"]').check();
  });
  await expect(page.getByText("Espace libéré · Archivé", {exact: true})).toBeVisible();
  await expect(page.getByText("Poids sec : 102.5 g", {exact: true}).first()).toBeVisible();
  await expect(page.getByText("Séchage · J4", {exact: true})).toBeVisible();
  await page.goto("/cultures?archives=1");
  await expect(page.getByRole("link", {name, exact: true})).toBeVisible();
});

test("solutions : recette, renouvellement, relevé et correction accessibles", async ({page}, testInfo) => {
  test.setTimeout(45000);
  test.skip(testInfo.project.name === "pwa-chromium", "Mutations exercées sur profils sans service worker.");
  await page.goto("/cultures/solutions?target=reservoir_2");
  await expect(page.getByRole("heading", {level: 1})).toHaveText("Solutions et relevés");
  const recipeDetails = page.locator("details").filter({has: page.getByText("Créer une recette", {exact: true})});
  await recipeDetails.locator("summary").click();
  const recipe = recipeDetails.locator("form");
  await recipe.getByLabel("Nom de recette").fill("Recette navigateur");
  await recipe.getByLabel("Volume de référence (L)", {exact: true}).fill("10");
  await recipe.getByLabel("Produit", {exact: true}).fill("Produit témoin");
  await recipe.getByLabel("Quantité", {exact: true}).fill("2,5");
  await recipe.getByRole("button", {name: "Enregistrer la recette"}).click();
  await expect(page.getByText("Recette navigateur · version 1", {exact: true})).toBeVisible();
  await page.locator("#saisie > summary").click();
  const quick = page.locator("[data-solution-entry]").first();
  await quick.getByRole("combobox", {name: "Action", exact: true}).selectOption("renewal");
  await quick.getByLabel("Date effective").fill("2026-08-01");
  await quick.getByLabel("Volume (L)", {exact: true}).fill("20");
  await quick.getByRole("combobox", {name: "Recette", exact: true}).selectOption({label: "Recette navigateur · version 1 · 10.0 L"});
  await expect(quick.locator("[data-recipe-preview]")).toContainText("Produit témoin : 5 mL");
  await quick.getByLabel("J’ai vérifié les quantités affichées.").check();
  await quick.getByRole("button", {name: "Enregistrer la saisie"}).click();
  await expect(page.locator(".solution-journal")).toHaveCount(1);
  await expect(page.locator(".solution-journal")).toContainText("Produit témoin : 5.0 mL");
  await expect(quick.getByLabel("pH", {exact: true})).toHaveValue("");
  await page.locator("#saisie > summary").click();
  await quick.getByLabel("Date effective").fill("2026-08-02");
  await quick.getByLabel("pH", {exact: true}).fill("6,2");
  await quick.getByLabel("EC", {exact: true}).fill("1200");
  await quick.getByRole("combobox", {name: "Unité EC", exact: true}).selectOption("µS/cm");
  await quick.getByRole("button", {name: "Enregistrer la saisie"}).click();
  await expect(page.locator(".solution-journal")).toHaveCount(2);
  await expect(page.locator(".solution-journal").first()).toContainText("EC 1.2 mS/cm");
  await expect(page.locator('svg[data-metric="ph"] circle')).toHaveCount(1);
  const saved = page.locator(".solution-journal").first();
  await saved.getByText("Corriger cette saisie", {exact: true}).click();
  await saved.getByLabel("pH", {exact: true}).fill("6,4");
  await saved.getByRole("button", {name: "Enregistrer la correction"}).click();
  await expect(page.locator(".solution-journal").first()).toContainText("pH 6.4");
  await page.getByText("Versions précédentes (1)", {exact: true}).click();
  await expect(page.locator(".solution-journal").first()).toContainText("pH 6.2");
  expect(await page.evaluate(() => document.documentElement.scrollWidth - innerWidth)).toBeLessThanOrEqual(1);
  expect((await new AxeBuilder({page}).analyze()).violations).toEqual([]);
  await page.screenshot({path: `/tmp/phyto-solutions-${testInfo.project.name}.png`, fullPage: true});
});

test("solutions : panne réseau, conservation des champs et idempotence", async ({page}, testInfo) => {
  test.skip(testInfo.project.name !== "desktop-chromium", "Une vérification réseau suffit.");
  await page.goto("/cultures/solutions?target=cuttings_1");
  await page.locator("#saisie > summary").click();
  const form = page.locator("[data-solution-entry]").first();
  await form.getByRole("combobox", {name: "Action", exact: true}).selectOption("renewal");
  await form.getByLabel("Date effective").fill("2026-08-01");
  await form.getByLabel("Volume (L)", {exact: true}).fill("5");
  const bodies = [];
  await page.route("**/api/v1/cultures/solutions", async route => {
    if (route.request().method() !== "POST") return route.continue();
    bodies.push(route.request().postDataJSON());
    if (bodies.length === 1) return route.abort();
    return route.continue();
  });
  await form.getByRole("button", {name: "Enregistrer la saisie"}).click();
  await expect(form.locator(".culture-form-errors")).toContainText("Saisie conservée");
  await expect(form.getByLabel("Volume (L)", {exact: true})).toHaveValue("5");
  await form.getByRole("button", {name: "Enregistrer la saisie"}).click();
  await expect(page.locator(".solution-journal")).toHaveCount(1);
  expect(bodies[0].request_id).toBe(bodies[1].request_id);
  await page.context().setOffline(true);
  await page.locator("#saisie > summary").click();
  await form.getByLabel("pH", {exact: true}).fill("6,1");
  await form.getByRole("button", {name: "Enregistrer la saisie"}).click();
  await expect(form.locator("output")).toContainText("Hors ligne");
  await page.context().setOffline(false);
  expect(bodies).toHaveLength(2);
});

test("cycles : photo, rappel récurrent et comparaison sur téléphone et bureau", async ({page}, testInfo) => {
  test.skip(!["desktop-chromium", "mobile-etroit"].includes(testInfo.project.name), "Deux formats pour le parcours complet.");
  test.setTimeout(60000);
  const mother = await createMother(page, `Mère carnet ${testInfo.project.name}`);
  const photoForm = page.locator("[data-photo-form]").first();
  await photoForm.locator("..").locator("summary").click();
  await photoForm.getByLabel("Légende", {exact: true}).fill("Image de test du carnet");
  await photoForm.getByLabel("Photo", {exact: true}).setInputFiles({name: "faux.jpg", mimeType: "image/jpeg", buffer: Buffer.from("<svg></svg>")});
  await photoForm.getByRole("button", {name: "Enregistrer la photo"}).click();
  await expect(photoForm.locator("output")).toContainText("Photo invalide");
  await expect(photoForm.getByLabel("Légende", {exact: true})).toHaveValue("Image de test du carnet");
  // Image synthétique issue de la page de test ; aucune photo de l'exploitation.
  const photo = await page.screenshot({type: "jpeg", clip: {x: 0, y: 0, width: 250, height: 150}});
  await photoForm.getByLabel("Photo", {exact: true}).setInputFiles({name: "photo-test.jpg", mimeType: "image/jpeg", buffer: photo});
  await photoForm.getByRole("button", {name: "Enregistrer la photo"}).click();
  await expect(page.getByRole("img", {name: "Image de test du carnet"})).toBeVisible();
  await page.goto(`/cultures/cycles?subject=${mother}`);
  await page.getByText("Créer un rappel", {exact: true}).click();
  const form = page.locator('[data-cycle-form][data-operation="reminder"]').first();
  await form.getByLabel("Rappel", {exact: true}).fill("Contrôler le carnet");
  await form.getByLabel("Échéance", {exact: true}).fill("2026-09-10");
  await form.getByLabel("Récurrence en jours (0 = ponctuel)").fill("2");
  await form.getByRole("button", {name: "Enregistrer le rappel"}).click();
  await expect(page.getByRole("heading", {name: "Contrôler le carnet"})).toBeVisible();
  const action = page.locator('[data-operation="reminder_action"]').first();
  await action.getByRole("combobox", {name: "Action sur le rappel"}).selectOption("postponed");
  await action.getByLabel("Nouvelle échéance (pour reporter)").fill("2026-09-12");
  await action.getByRole("button", {name: "Enregistrer le suivi"}).click();
  await expect(page.getByText("Reporté · échéance 12/09/2026")).toBeVisible();
  await action.getByRole("button", {name: "Enregistrer le suivi"}).click();
  await expect(page.getByRole("heading", {name: "Contrôler le carnet"})).toHaveCount(2);
  await expect(page.getByText("Aucune synthèse climatique disponible pour ce cycle.")).toBeVisible();
  expect(await page.evaluate(() => document.documentElement.scrollWidth - innerWidth)).toBeLessThanOrEqual(1);
  expect((await new AxeBuilder({page}).analyze()).violations).toEqual([]);
  await page.screenshot({path: `/tmp/phyto-cycles-${testInfo.project.name}.png`, fullPage: true});
  await page.locator("#rappels").screenshot({path: `/tmp/phyto-reminders-${testInfo.project.name}.png`});
});

test("cycles : PWA datée en lecture seule et aucune mutation rejouée", async ({page}, testInfo) => {
  test.skip(testInfo.project.name !== "pwa-chromium", "Le service worker est réservé au profil PWA.");
  test.setTimeout(60000);
  const mother = await createMother(page, "Mère PWA carnet");
  await page.evaluate(async () => { await navigator.serviceWorker.ready; });
  await page.goto(`/cultures/cycles?subject=${mother}`);
  await page.getByText("Créer un rappel", {exact: true}).click();
  const form = page.locator('[data-cycle-form][data-operation="reminder"]').first();
  await form.getByLabel("Rappel", {exact: true}).fill("Rappel PWA");
  await form.getByLabel("Échéance", {exact: true}).fill("2026-09-10");
  await form.getByRole("button", {name: "Enregistrer le rappel"}).click();
  await expect(page.getByRole("heading", {name: "Rappel PWA"})).toBeVisible();
  await expect.poll(() => page.evaluate(async () => {
    const names = await caches.keys();
    for (const name of names.filter(n => n.startsWith("phyto-cultures-"))) {
      if (await (await caches.open(name)).match(location.href.split("#")[0])) return true;
    }
    return false;
  })).toBe(true);
  let posts = 0;
  page.on("request", request => { if (request.method() === "POST") posts++; });
  await page.context().setOffline(true);
  await page.reload();
  await expect(page.getByRole("heading", {name: "Rappel PWA"})).toBeVisible();
  await expect(page.locator("#pwa-connection-banner")).toContainText("lecture seule");
  await expect(page.locator('meta[name="phyto-offline-snapshot"]')).toHaveCount(1);
  await expect(page.getByRole("button", {name: "Enregistrer le suivi"})).toBeDisabled();
  const cachedApis = await page.evaluate(async () => {
    const urls = [];
    for (const name of await caches.keys()) for (const key of await (await caches.open(name)).keys()) urls.push(new URL(key.url).pathname);
    return urls.filter(path => path.startsWith("/api/") || path.startsWith("/actions/"));
  });
  expect(cachedApis).toEqual([]);
  await page.context().setOffline(false);
  await page.reload();
  await expect(page.locator('meta[name="phyto-offline-snapshot"]')).toHaveCount(0);
  await expect(page.getByRole("button", {name: "Enregistrer le suivi"})).toBeEnabled();
  expect(posts).toBe(0);
});
