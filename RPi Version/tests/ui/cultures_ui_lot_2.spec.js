"use strict";

// Lot UI 2 : les parcours quotidiens du carnet. Un serveur de carnet par test (fixture
// partagée) : l'espace 2 est exclusif et une occupation ouverte n'a pas de fin, donc deux
// scénarios ne peuvent pas partager une base. Aucune de ces vérifications ne touche un
// GPIO, un réglage ou le watchdog : le carnet est déclaratif.
const {test, expect, AxeBuilder, createMother} = require("./culture_fixtures");

// Dates locales : le carnet refuse toute date future, et un rappel « en retard » se
// fabrique avec une échéance d'hier, pas avec une date figée qui vieillirait mal.
const day = offset => {
  const value = new Date();
  value.setDate(value.getDate() - offset);
  return `${value.getFullYear()}-${String(value.getMonth() + 1).padStart(2, "0")}-${String(value.getDate()).padStart(2, "0")}`;
};

// Mutation par l'API, avec le jeton de la page : sert à poser un état de départ
// (rappel en retard, archivage, correction concurrente) sans rejouer un formulaire.
const mutate = (page, path, command) => page.evaluate(async ([target, body]) => {
  const response = await fetch(target, {
    method: "POST",
    headers: {"X-CSRF-Token": document.querySelector('meta[name="csrf-token"]').content,
      "Content-Type": "application/json"},
    body: JSON.stringify({...body, request_id: crypto.randomUUID()}),
  });
  return {status: response.status, body: await response.json()};
}, [path, command]);

const detailOf = async (page, id) => {
  const response = await page.request.get(`/api/v1/cultures/${id}`);
  expect(response.ok(), await response.text()).toBeTruthy();
  return response.json();
};

// PNG 1×1 valide, construit en mémoire : aucune image de l'exploitation n'entre ici.
const PNG_1x1 = Buffer.from(
  "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg==",
  "base64");

// Le formulaire d'observation vit dans un repli de la triade d'en-tête.
const openObservation = async page => {
  const form = page.locator("form[data-culture-observation]");
  const details = page.locator("#observation");
  if ((await details.getAttribute("open")) === null) await details.locator(":scope > summary").click();
  await expect(form).toBeVisible();
  return form;
};

const focusedId = page => page.evaluate(() => document.activeElement?.id || "");

// ---------------------------------------------------------------------------
// 1. Accueil vide
// ---------------------------------------------------------------------------

test("lot UI 2 : un carnet vide guide vers la première culture sans inventer de zéro", async ({page}) => {
  await page.goto("/cultures");
  const agenda = page.locator("#agenda");
  await expect(agenda).toBeVisible();
  await expect(agenda.getByRole("heading", {level: 2})).toContainText("Aujourd’hui");
  // Un carnet sans rappel le dit ; il n'affiche ni « 0 rappel » ni carte vide.
  await expect(agenda).toContainText("Aucun rappel en cours dans le carnet.");
  await expect(agenda).not.toContainText(/\b0\s+rappel/i);
  await expect(page.locator("article.culture-reminder")).toHaveCount(0);
  await expect(agenda).toContainText("Aucune opération enregistrée pour l’instant.");
  for (const label of ["Saisir un relevé", "Noter une observation", "Nouvelle culture"]) {
    await expect(agenda.getByRole("link", {name: label, exact: true})).toBeVisible();
  }
  const first = page.getByRole("link", {name: "Ajouter ma première culture", exact: true});
  await expect(first).toBeVisible();
  await first.click();
  await expect(page.locator("#creer-lot")).toHaveAttribute("open", "");
});

// ---------------------------------------------------------------------------
// 2. Accueil renseigné : un rappel en retard se traite sur place
// ---------------------------------------------------------------------------

test("lot UI 2 : un rappel en retard précède l'occupation, se reporte et se termine depuis l'accueil", async ({page}, testInfo) => {
  test.skip(testInfo.project.name === "pwa-chromium", "Parcours mutateur exercé hors service worker.");
  test.setTimeout(90000);
  // Un éventuel confirm() ne doit pas figer le parcours ; aucun n'est attendu ici.
  page.on("dialog", dialog => dialog.accept());
  const id = await createMother(page, "Mère agenda");
  const created = await mutate(page, "/api/v1/cultures/cycles", {
    operation: "reminder", target: id, title: "Contrôler la mère", due_date: day(1), interval_days: 0,
  });
  expect(created.status, JSON.stringify(created.body)).toBe(200);
  const reminder = created.body.id;

  await page.goto("/cultures");
  const card = page.locator(`#agenda article.culture-reminder#reminder-${reminder}`);
  await expect(card).toBeVisible();
  await expect(card).toHaveAttribute("tabindex", "-1");
  await expect(page.locator("#agenda").getByRole("heading", {name: "En retard", exact: true})).toBeVisible();

  // L'agenda précède l'occupation des espaces : ce qu'il y a à faire d'abord.
  const agendaBox = await card.boundingBox();
  const occupation = await page.locator('section[aria-label="Occupation des espaces"]').boundingBox();
  expect(agendaBox.y).toBeLessThan(occupation.y);

  // « Nouvelle échéance » ne concerne que le report : le champ n'apparaît qu'alors.
  const action = card.locator("select[data-reminder-action]");
  const postpone = card.locator("[data-reminder-postpone]");
  await expect(postpone).toBeHidden();
  await action.selectOption("postponed");
  await expect(postpone).toBeVisible();

  await action.selectOption("done");
  await expect(postpone).toBeHidden();
  await card.locator('[data-cycle-form][data-operation="reminder_action"][data-cycle-return="agenda"]')
    .getByRole("button", {name: "Enregistrer le suivi", exact: true}).click();

  await expect(page).toHaveURL(new RegExp(`#reminder-${reminder}$`));
  const closed = page.locator(`#agenda #reminder-${reminder}`);
  await expect(closed).toBeVisible();
  await expect(closed).toContainText("Fait");
  await expect(closed.locator("form")).toHaveCount(0);
  await expect(page.locator("#agenda").getByRole("heading", {name: "Terminés aujourd’hui", exact: true})).toBeVisible();
  await expect(closed.locator(".culture-added")).toBeVisible();
  expect(await focusedId(page)).toBe(`reminder-${reminder}`);
});

// Ce que W6 mesurait et qui n'était pas tenu : la carte du premier rappel commençait à
// y = 883 px sur mobile-chromium (Pixel 5, 393 × 727), une page et demie sous la ligne de
// flottaison, parce que les trois raccourcis empilés (159 px) précédaient les rappels et
// que le hero de l'accueil en occupait 276. Les rappels passent donc avant les raccourcis
// dans `#agenda`, et `cultures.css` resserre hero, navigation et raccourcis sous 30 rem.
// La carte doit tenir **entière** sous la ligne de flottaison, pas seulement y commencer.
test("lot UI 2 : un rappel en retard est visible sans défilement à 393 px", async ({page}, testInfo) => {
  test.skip(testInfo.project.name !== "mobile-chromium", "Contrainte de hauteur propre au 393 px.");
  const id = await createMother(page, "Mère au-dessus de la ligne");
  const created = await mutate(page, "/api/v1/cultures/cycles", {
    operation: "reminder", target: id, title: "Contrôler la mère", due_date: day(1), interval_days: 0,
  });
  expect(created.status, JSON.stringify(created.body)).toBe(200);
  await page.goto("/cultures");
  const box = await page.locator(`#agenda #reminder-${created.body.id}`).boundingBox();
  expect(box.y + box.height).toBeLessThanOrEqual(page.viewportSize().height);
});

// ---------------------------------------------------------------------------
// 3. Fiche renseignée
// ---------------------------------------------------------------------------

test("lot UI 2 : la fiche montre l'essentiel et l'observation revient sur son entrée", async ({page}, testInfo) => {
  test.skip(testInfo.project.name === "pwa-chromium", "Parcours mutateur exercé hors service worker.");
  test.setTimeout(90000);
  const id = await createMother(page, "Mère fiche dossier");
  const head = page.locator(".culture-head");
  await expect(head).toContainText("Mère fiche dossier");
  await expect(head).toContainText(/\bJ\d+/);
  await expect(head).toContainText("Espace 1");

  await expect(page.getByRole("link", {name: "Relevé", exact: true}))
    .toHaveAttribute("href", `/cultures/solutions?target=${id}&kind=reading#saisie`);
  await expect(page.locator("#observation")).toBeVisible();
  const others = page.locator("details.card.culture-section").filter({hasText: "Autres opérations"});
  await expect(others).toHaveCount(1);
  await expect(others).not.toHaveAttribute("open", "");

  const local = page.locator(".culture-local-links");
  await expect(local.getByRole("link")).toHaveCount(5);
  for (const [label, anchor] of [["Synthèse", "synthese"], ["Journal", "journal"], ["Relevés", "releves"],
                                 ["Photos", "photos"], ["Bilan", "bilan"]]) {
    await local.getByRole("link", {name: label, exact: true}).click();
    await expect(page).toHaveURL(new RegExp(`#${anchor}$`));
    await expect(page.locator(`#${anchor}`)).toBeVisible();
  }

  const form = await openObservation(page);
  await form.getByLabel("Observation", {exact: true}).fill("Feuilles suivies, rien à signaler.");
  await form.getByRole("button", {name: "Enregistrer l’observation", exact: true}).click();

  await expect(page).toHaveURL(/#event-/);
  const entry = page.locator(".culture-journal.card").filter({hasText: "Feuilles suivies"}).first();
  await expect(entry).toBeVisible();
  await expect(entry.locator(".culture-added")).toBeVisible();
  const anchor = await entry.getAttribute("id");
  expect(page.url()).toContain(`#${anchor}`);
  expect(await focusedId(page)).toBe(anchor);
  // La traçabilité reste repliée : elle est disponible, pas imposée.
  await expect(entry.locator("details.culture-trace")).not.toHaveAttribute("open", "");
});

// ---------------------------------------------------------------------------
// 4. Observation + photo, et échec partiel de la seule photo
// ---------------------------------------------------------------------------

test("lot UI 2 : une photo refusée laisse l'observation enregistrée et se rejoue sans doublon", async ({page}, testInfo) => {
  test.skip(testInfo.project.name === "pwa-chromium", "Parcours mutateur exercé hors service worker.");
  test.setTimeout(90000);
  const id = await createMother(page, "Mère photo");

  // Premier envoi : observation + photo acceptées, aperçu local avant tout envoi.
  let form = await openObservation(page);
  await form.getByLabel("Observation", {exact: true}).fill("Première observation illustrée.");
  await form.getByLabel("Légende de la photo", {exact: true}).fill("Cliché synthétique 1×1");
  await form.locator('input[type="file"][name="photo"]')
    .setInputFiles({name: "carnet.png", mimeType: "image/png", buffer: PNG_1x1});
  await expect(form.locator("[data-observation-preview]")).toBeVisible();
  await expect(form.locator("[data-observation-preview] img")).toBeVisible();
  await form.getByRole("button", {name: "Enregistrer l’observation", exact: true}).click();
  await expect(page).toHaveURL(/#event-/);
  await expect(page.locator("#photos figure")).toHaveCount(1);

  // Second envoi : la photo seule est refusée une fois par le réseau simulé.
  let refused = 0;
  await page.route("**/api/v1/cultures/photos", async route => {
    if (refused === 0) {
      refused += 1;
      return route.fulfill({status: 400, contentType: "application/json",
        body: JSON.stringify({error: "Photo invalide."})});
    }
    return route.continue();
  });
  form = await openObservation(page);
  await form.getByLabel("Observation", {exact: true}).fill("Observation dont la photo échoue.");
  await form.getByLabel("Légende de la photo", {exact: true}).fill("Cliché rejoué");
  await form.locator('input[type="file"][name="photo"]')
    .setInputFiles({name: "carnet2.png", mimeType: "image/png", buffer: PNG_1x1});
  await form.getByRole("button", {name: "Enregistrer l’observation", exact: true}).click();

  const summary = form.locator('.culture-form-errors[role="alert"]');
  await expect(summary).toContainText("L’observation est enregistrée");
  await expect(summary).toContainText("Photo invalide.");
  const retry = form.getByRole("button", {name: "Réessayer la photo", exact: true});
  await expect(retry).toBeVisible();
  expect(refused).toBe(1);

  await retry.click();
  await expect(page).toHaveURL(/#event-/);
  await expect(page.locator("#photos figure")).toHaveCount(2);

  // Une seule entrée d'observation par envoi : la note n'a jamais été rejouée.
  const detail = await detailOf(page, id);
  const notes = detail.events.filter(event => event.kind === "note");
  expect(notes).toHaveLength(2);
  expect(notes.filter(event => (event.payload.note || "").includes("photo échoue"))).toHaveLength(1);
});

// ---------------------------------------------------------------------------
// 5. Un refus se lit à côté du champ
// ---------------------------------------------------------------------------

test("lot UI 2 : une date future est refusée au champ, avec résumé, focus et effacement", async ({page}, testInfo) => {
  test.skip(testInfo.project.name === "pwa-chromium", "Parcours mutateur exercé hors service worker.");
  test.setTimeout(90000);
  await createMother(page, "Mère refus daté");
  const form = await openObservation(page);
  await form.getByLabel("Observation", {exact: true}).fill("Observation datée demain par erreur.");
  const date = form.locator('[name="effective_at"]');
  await date.fill(day(-1));
  await form.getByRole("button", {name: "Enregistrer l’observation", exact: true}).click();

  const summary = form.locator('.culture-form-errors[role="alert"]');
  await expect(summary).toBeVisible();
  await expect(summary).toContainText("Une date effective ne peut pas être future.");
  const fieldId = await date.getAttribute("id");
  await expect(summary.locator(`a[href="#${fieldId}"]`)).toBeVisible();
  await expect(date).toHaveAttribute("aria-invalid", "true");
  const described = await date.getAttribute("aria-describedby");
  expect(described).toContain(`${fieldId}-error`);
  for (const token of described.split(/\s+/).filter(Boolean)) {
    await expect(page.locator(`#${token}`)).toHaveCount(1);
  }
  await expect(page.locator(`#${fieldId}-error.field-error`)).toBeVisible();
  expect(await page.evaluate(() => document.activeElement?.name || "")).toBe("effective_at");
  // La saisie est conservée : seule la date est à corriger.
  await expect(form.getByLabel("Observation", {exact: true})).toHaveValue("Observation datée demain par erreur.");

  await date.fill(day(0));
  await expect(date).not.toHaveAttribute("aria-invalid", "true");
  await expect(page.locator(`#${fieldId}-error`)).toHaveCount(0);
  await expect(summary).toHaveCount(0);
});

// ---------------------------------------------------------------------------
// 6. Conflit de version
// ---------------------------------------------------------------------------

test("lot UI 2 : un conflit de version conserve la saisie et n'écrit aucun doublon", async ({page, context}, testInfo) => {
  test.skip(testInfo.project.name !== "desktop-chromium", "Un second onglet suffit sur un seul format.");
  test.setTimeout(90000);
  const id = await createMother(page, "Mère conflit");
  const stale = await context.newPage();
  await stale.goto(`/cultures/${id}`);

  // Le premier onglet écrit : la version du sujet change sous le second.
  const before = await detailOf(page, id);
  const written = await mutate(page, "/api/v1/cultures", {
    operation: "event", subject_id: id, version: before.subject.version, kind: "note",
    effective_at: day(0), precision: "date", payload: {note: "Écriture du premier onglet"},
  });
  expect(written.status, JSON.stringify(written.body)).toBe(200);

  const form = await openObservation(stale);
  await form.getByLabel("Observation", {exact: true}).fill("Saisie de l’onglet périmé");
  await form.getByRole("button", {name: "Enregistrer l’observation", exact: true}).click();

  // Un conflit n'est pas une faute de saisie : la saisie reste, et un lien mène à la
  // fiche à jour. Le message est rendu dans le résumé d'erreur du formulaire, comme tout
  // autre refus ; l'<output> reste réservé à la progression et au hors ligne.
  await expect(form.locator('.culture-form-errors[role="alert"]')
    .getByRole("link", {name: "Ouvrir la fiche actualisée", exact: true})).toBeVisible();
  await expect(form).toContainText("Votre saisie reste dans ce formulaire.");
  await expect(form.getByLabel("Observation", {exact: true})).toHaveValue("Saisie de l’onglet périmé");
  await expect(stale).toHaveURL(new RegExp(`/cultures/${id}$`));

  const after = await detailOf(page, id);
  const notes = after.events.filter(event => event.kind === "note");
  expect(notes).toHaveLength(1);
  expect(notes[0].payload.note).toBe("Écriture du premier onglet");
  await stale.close();
});

// `docs/operations/cultures.md` (« Un refus se lit à côté du champ ») annonce que les refus
// sans champ — conflit de version, carnet indisponible — « restent affichés dans le résumé,
// sans lien mort », l'<output> restant réservé à la progression et au hors ligne.
// `showConflict` passe donc par `showError` et pose son lien dans le résumé : `status()`
// aurait supprimé `.culture-form-errors` pour écrire dans l'<output role="status">.
test("lot UI 2 : un conflit 409 s'affiche dans le résumé d'erreur du formulaire", async ({page}) => {
  const id = await createMother(page, "Mère conflit résumé");
  const detail = await detailOf(page, id);
  await mutate(page, "/api/v1/cultures", {operation: "event", subject_id: id,
    version: detail.subject.version, kind: "note", effective_at: day(0), precision: "date",
    payload: {note: "Écriture concurrente"}});
  const form = await openObservation(page);
  await form.getByLabel("Observation", {exact: true}).fill("Saisie périmée");
  await form.getByRole("button", {name: "Enregistrer l’observation", exact: true}).click();
  await expect(form.locator('.culture-form-errors[role="alert"]')).toContainText("Ouvrir la fiche actualisée");
});

// ---------------------------------------------------------------------------
// 7. Fiche archivée
// ---------------------------------------------------------------------------

test("lot UI 2 : une fiche archivée ne propose plus de progression, seulement la libération", async ({page}, testInfo) => {
  test.skip(testInfo.project.name === "pwa-chromium", "Parcours mutateur exercé hors service worker.");
  test.setTimeout(90000);
  // Un pied mère archivé : plus aucune action de parcours. L'archivage libère l'espace
  // dans le même événement (`model/culture.py:345-350`), une mère archivée n'a donc jamais
  // de libération à proposer — c'est un lot clos sans libération qui la porte, ci-dessous.
  const mother = await createMother(page, "Mère archivée");
  const beforeMother = await detailOf(page, mother);
  const archived = await mutate(page, "/api/v1/cultures", {
    operation: "event", subject_id: mother, version: beforeMother.subject.version, kind: "archive",
    effective_at: day(0), precision: "date", payload: {note: "Fin de la mère"},
  });
  expect(archived.status, JSON.stringify(archived.body)).toBe(200);
  await page.goto(`/cultures/${mother}`);
  await expect(page.locator(".culture-head")).toContainText("Archivé");
  await expect(page.locator(".culture-head")).toContainText("Espace libéré");
  await expect(page.locator("#action-stage")).toHaveCount(0);
  await expect(page.locator("#action-archive")).toHaveCount(0);
  await expect(page.locator("#action-release")).toHaveCount(0);

  // Un lot clos en séchage sans libération : l'espace reste occupé, la fiche le dit.
  const lot = await mutate(page, "/api/v1/cultures", {
    operation: "create", kind: "lot", name: "Lot clos", origin_type: "seed",
    stage: "sechage", space: "space_2", origin_at: day(9), stage_at: day(5), space_at: day(9),
    origins: [{label: "Semences de clôture", count: 3}],
  });
  expect(lot.status, JSON.stringify(lot.body)).toBe(200);
  const id = lot.body.subject_id;
  const beforeFinish = await detailOf(page, id);
  const finished = await mutate(page, "/api/v1/cultures", {
    operation: "event", subject_id: id, version: beforeFinish.subject.version, kind: "finish",
    effective_at: day(0), precision: "date",
    payload: {note: "", weight_g: null, lessons: "", release: false, origin_weights: []},
  });
  expect(finished.status, JSON.stringify(finished.body)).toBe(200);

  await page.goto(`/cultures/${id}`);
  await expect(page.locator(".culture-head")).toContainText("Archivé");
  await expect(page.locator("#action-stage")).toHaveCount(0);
  await expect(page.locator("#action-finish")).toHaveCount(0);
  const release = page.locator("#action-release");
  await expect(release).toBeVisible();
  await expect(release.locator(":scope > summary")).toHaveText("Libérer l’espace");

  const current = await detailOf(page, id);
  const freed = await mutate(page, "/api/v1/cultures", {
    operation: "event", subject_id: id, version: current.subject.version, kind: "release",
    effective_at: day(0), precision: "date", payload: {},
  });
  expect(freed.status, JSON.stringify(freed.body)).toBe(200);

  await page.goto(`/cultures/${id}`);
  await expect(page.locator("#action-release")).toHaveCount(0);
  await expect(page.locator(".culture-head")).toContainText("Espace libéré");
});

// ---------------------------------------------------------------------------
// 8. Solutions : intention visible et refus rattaché au champ
// ---------------------------------------------------------------------------

test("lot UI 2 : une intention de saisie ouvre et présélectionne le formulaire des solutions", async ({page}, testInfo) => {
  test.skip(testInfo.project.name === "pwa-chromium", "Parcours mutateur exercé hors service worker.");
  test.setTimeout(90000);
  // Un renouvellement vise un réservoir : c'est la cible que la page présélectionne.
  await page.goto("/cultures/solutions?target=reservoir_2&kind=renewal#saisie");
  const entry = page.locator("#saisie");
  await expect(entry).toHaveAttribute("open", "");
  await expect(entry.locator(":scope > summary")).toHaveText("Saisir : Renouvellement");
  const intentions = page.locator("[data-solution-intentions]");
  await expect(intentions.locator('a[data-intention="renewal"]')).toHaveAttribute("aria-current", "true");
  await expect(intentions.locator('a[aria-current="true"]')).toHaveCount(1);
  for (const key of ["reading", "water", "topup"]) {
    await expect(intentions.locator(`a[data-intention="${key}"]`)).not.toHaveAttribute("aria-current", "true");
  }

  const form = page.locator("[data-solution-entry]").first();
  await expect(form.locator('[name="target"]')).toHaveValue("reservoir_2");
  await expect(form.locator('[name="kind"]')).toHaveValue("renewal");
  // Un volume est obligatoire pour un renouvellement : le champ l'est aussi côté page.
  await expect(form.locator('[name="volume_l"]')).toHaveAttribute("required", "");

  // Refus du serveur rattaché au champ : un volume illisible désigne `volume_l`.
  await form.locator('[name="volume_l"]').fill("beaucoup");
  await form.getByRole("button", {name: "Enregistrer la saisie"}).click();
  const summary = form.locator('.culture-form-errors[role="alert"]');
  await expect(summary).toBeVisible();
  const volume = form.locator('[name="volume_l"]');
  await expect(volume).toHaveAttribute("aria-invalid", "true");
  const fieldId = await volume.getAttribute("id");
  await expect(summary.locator(`a[href="#${fieldId}"]`)).toBeVisible();
  await expect(page.locator(`#${fieldId}-error.field-error`)).toBeVisible();

  await volume.fill("20");
  await expect(volume).not.toHaveAttribute("aria-invalid", "true");
  await expect(summary).toHaveCount(0);
});

// ---------------------------------------------------------------------------
// 9. Création : « Je démarre » ou « déjà en cours »
// ---------------------------------------------------------------------------

test("lot UI 2 : « Je démarre » déduit stade et dates, « déjà en cours » les rend indépendants", async ({page}, testInfo) => {
  test.skip(testInfo.project.name === "pwa-chromium", "Parcours mutateur exercé hors service worker.");
  test.setTimeout(90000);
  await page.goto("/cultures");
  const details = page.locator("#creer-lot");
  await details.locator(":scope > summary").click();
  const form = details.locator('form[data-culture-create][data-kind="lot"]');
  await expect(form).toHaveAttribute("data-first-stage-seed", "germination");
  await expect(form).toHaveAttribute("data-first-stage-cutting", "enracinement");

  // Mode par défaut : « Je démarre une culture ». La situation actuelle est repliée.
  await expect(form.getByRole("radio", {name: "Je démarre une culture"})).toBeChecked();
  await expect(form.locator("[data-creation-stage]")).toBeHidden();
  await expect(form.locator("[data-creation-stage-date]")).toBeHidden();
  await expect(form.locator("[data-creation-space-date]")).toBeHidden();

  const value = name => form.locator(`[name="${name}"]`).evaluate(el => el.value);
  const origin = day(5);
  await form.getByLabel("Nom", {exact: true}).fill("Semis démarrés");
  await form.locator('[name="origin_label"]').fill("Semences maison");
  await form.locator('[name="origin_count"]').fill("6");
  await form.locator('[name="origin_at"]').fill(origin);
  // La date d'origine est recopiée : rien n'est inventé, une seule date est demandée.
  expect(await value("stage_at")).toBe(origin);
  expect(await value("space_at")).toBe(origin);
  expect(await value("stage")).toBe("germination");

  const lines = form.locator("[data-creation-summary] li");
  await expect(lines.first()).toContainText("Origine");
  await expect(form.locator("[data-creation-summary]")).toContainText("Effectif total — 6 plantes");
  await expect(form.locator("[data-creation-summary]")).toContainText("Semences maison");

  // Bascule : les trois dates redeviennent indépendantes et visibles.
  await form.getByRole("radio", {name: "Elle est déjà en cours"}).check();
  await expect(form.locator("[data-creation-stage]")).toBeVisible();
  await expect(form.locator("[data-creation-stage-date]")).toBeVisible();
  await expect(form.locator("[data-creation-space-date]")).toBeVisible();
  await form.locator('[name="origin_at"]').fill(day(9));
  expect(await value("stage_at")).toBe(origin);
  expect(await value("space_at")).toBe(origin);

  // Retour au mode démarrage puis création : le stade est le premier du parcours semis.
  await form.getByRole("radio", {name: "Je démarre une culture"}).check();
  await form.locator('[name="origin_at"]').fill(origin);
  await form.getByRole("button", {name: "Créer un lot", exact: true}).click();
  await expect(page.getByRole("heading", {level: 1})).toHaveText("Semis démarrés");
  await expect(page.locator(".culture-head")).toContainText("Germination");
  await expect(page.locator(".culture-head")).toContainText("6 plantes restantes");
});

// ---------------------------------------------------------------------------
// 10. Accessibilité, absence de débordement, thèmes et captures
// ---------------------------------------------------------------------------

test("lot UI 2 : accueil, fiche, archives, solutions et état d'erreur restent accessibles", async ({page}, testInfo) => {
  test.skip(!["desktop-chromium", "mobile-chromium"].includes(testInfo.project.name),
    "Axe et captures sur un format bureau et un format téléphone.");
  test.setTimeout(90000);
  const id = await createMother(page, "Mère accessible");
  const detail = await detailOf(page, id);
  const created = await mutate(page, "/api/v1/cultures/cycles", {
    operation: "reminder", target: id, title: "Vérifier l’arrosage", due_date: day(1), interval_days: 0,
  });
  expect(created.status, JSON.stringify(created.body)).toBe(200);
  const noted = await mutate(page, "/api/v1/cultures", {
    operation: "event", subject_id: id, version: detail.subject.version, kind: "note",
    effective_at: day(0), precision: "date", payload: {note: "Observation d’accessibilité"},
  });
  expect(noted.status, JSON.stringify(noted.body)).toBe(200);

  const audit = async (name) => {
    for (const theme of ["", "daylight"]) {
      await page.evaluate(value => document.documentElement.setAttribute("data-theme", value), theme);
      expect((await new AxeBuilder({page}).analyze()).violations, `${name} · ${theme || "normal"}`).toEqual([]);
      expect(await page.evaluate(() => document.documentElement.scrollWidth - innerWidth)).toBeLessThanOrEqual(1);
      await page.screenshot({path: testInfo.outputPath(`${name}-${theme || "normal"}.png`), fullPage: true});
    }
  };

  for (const [name, path] of [["accueil", "/cultures"], ["fiche", `/cultures/${id}`],
                              ["archives", "/cultures?archives=1"],
                              ["solutions", "/cultures/solutions?kind=water#saisie"]]) {
    await page.goto(path);
    await audit(name);
  }

  // État d'erreur de la fiche : le résumé, le champ marqué et son message doivent être
  // aussi corrects que la page au repos.
  await page.goto(`/cultures/${id}`);
  const form = await openObservation(page);
  await form.getByLabel("Observation", {exact: true}).fill("Observation datée demain.");
  await form.locator('[name="effective_at"]').fill(day(-1));
  await form.getByRole("button", {name: "Enregistrer l’observation", exact: true}).click();
  await expect(form.locator('.culture-form-errors[role="alert"]')).toBeVisible();
  await audit("fiche-erreur");
});


// ---------------------------------------------------------------------------
// 11. Remédiation : clonage après refus, refus local chiffré, envoi unique
// ---------------------------------------------------------------------------

// Le clone d'une ligne d'origine héritait du message de refus de la ligne modèle : deux
// éléments portaient le même identifiant, la nouvelle ligne s'affichait refusée sans
// l'être, et sa première saisie effaçait le message de l'ancienne.
test("lot UI 2 : une origine ajoutée après un refus est vierge et n'emporte aucun message", async ({page}, testInfo) => {
  test.skip(testInfo.project.name === "pwa-chromium", "Parcours mutateur exercé hors service worker.");
  test.setTimeout(90000);
  await page.goto("/cultures");
  const details = page.locator("details.culture-create").filter({hasText: "Créer un lot"});
  await details.locator("summary").click();
  const form = details.locator("form");
  await form.getByRole("radio", {name: "Elle est déjà en cours"}).check();
  await form.getByLabel("Nom", {exact: true}).fill("Lot origines clonées");
  await form.getByLabel("Origine des semences").fill("Semences A");
  for (const name of ["origin_at", "stage_at", "space_at"]) await form.locator(`[name="${name}"]`).fill(day(2));
  await form.locator('[name="space"]').selectOption("space_2");

  // Refus serveur simulé sur la première origine : c'est le seul moyen d'obtenir ce refus
  // sans passer par un champ que le navigateur bloque déjà (obligatoire, borné).
  await page.route("**/api/v1/cultures", route => route.fulfill({
    status: 400, contentType: "application/json",
    body: JSON.stringify({error: "Origine obligatoire.", field: "origin_label", index: 0})}));
  await form.getByRole("button", {name: "Créer un lot", exact: true}).click();

  const label = form.locator('.culture-origin').first().locator('[name="origin_label"]');
  await expect(label).toHaveAttribute("aria-invalid", "true");
  const errorId = `${await label.getAttribute("id")}-error`;
  await expect(page.locator(`#${errorId}`)).toHaveCount(1);

  await form.locator("[data-add-origin]").click();
  const rows = form.locator(".culture-origin");
  await expect(rows).toHaveCount(2);
  const added = rows.nth(1);
  await expect(added.locator(".field-error")).toHaveCount(0);
  await expect(added.locator(".field-invalid")).toHaveCount(0);
  await expect(added.locator('[name="origin_label"]')).toHaveValue("");
  await expect(added.locator('[name="origin_label"]')).not.toHaveAttribute("aria-invalid", "true");
  // Un seul élément par identifiant d'erreur, et le message reste sur la ligne refusée.
  await expect(page.locator(`#${errorId}`)).toHaveCount(1);
  await expect(page.locator(".field-error")).toHaveCount(1);
  await added.locator('[name="origin_label"]').fill("Semences B");
  await expect(page.locator(`#${errorId}`)).toHaveCount(1);
  await expect(label).toHaveAttribute("aria-invalid", "true");
});

// Un refus calculé dans le navigateur se lit comme un refus du serveur : au champ, avec
// le focus, y compris dans un repli qu'il faut ouvrir pour le rendre visible.
test("lot UI 2 : un poids invalide est marqué au champ, dans son repli, sans rien envoyer", async ({page}, testInfo) => {
  test.skip(testInfo.project.name === "pwa-chromium", "Parcours mutateur exercé hors service worker.");
  test.setTimeout(90000);
  await page.goto("/cultures");
  const lot = await mutate(page, "/api/v1/cultures", {
    operation: "create", kind: "lot", name: "Lot pesée", origin_type: "seed",
    stage: "sechage", space: "space_2", origin_at: day(9), stage_at: day(5), space_at: day(9),
    origins: [{label: "Semences A", count: 2}, {label: "Semences B", count: 1}],
  });
  expect(lot.status, JSON.stringify(lot.body)).toBe(200);
  await page.goto(`/cultures/${lot.body.subject_id}`);
  let sent = 0;
  page.on("request", request => {
    if (request.method() === "POST" && request.url().includes("/api/v1/cultures")) sent += 1;
  });
  const action = page.locator("#action-finish");
  await action.locator(":scope > summary").click();
  const form = action.locator("form");
  const submit = form.getByRole("button", {name: "Clore le séchage", exact: true});

  await form.locator('[name="weight_g"]').fill("abc");
  await submit.click();
  const summary = form.locator('.culture-form-errors[role="alert"]');
  await expect(summary).toContainText("Poids sec invalide.");
  const weight = form.locator('[name="weight_g"]');
  const weightId = await weight.getAttribute("id");
  await expect(weight).toHaveAttribute("aria-invalid", "true");
  await expect(summary.locator(`a[href="#${weightId}"]`)).toBeVisible();
  expect(await focusedId(page)).toBe(weightId);

  // Deuxième origine refusée : le rang envoyé désigne bien le deuxième champ de la page,
  // et son repli s'ouvre pour que le focus ne se pose pas sur un champ invisible.
  await weight.fill("120");
  const perOrigin = form.locator('[name="origin_weight"]');
  await expect(perOrigin).toHaveCount(2);
  const fold = form.locator('details:has([name="origin_weight"])').first();
  await fold.locator("summary").click();
  await perOrigin.nth(1).fill("nc");
  // Repli refermé avant l'envoi : le refus doit le rouvrir, sinon le focus se poserait sur
  // un champ invisible.
  await fold.locator("summary").click();
  await expect(perOrigin.nth(1)).toBeHidden();
  await submit.click();
  await expect(summary).toContainText("Poids par origine invalide.");
  const originId = await perOrigin.nth(1).getAttribute("id");
  await expect(perOrigin.nth(1)).toHaveAttribute("aria-invalid", "true");
  await expect(perOrigin.nth(0)).not.toHaveAttribute("aria-invalid", "true");
  expect(await focusedId(page)).toBe(originId);
  await expect(perOrigin.nth(1)).toBeVisible();

  // Un refus local ne consomme aucune transaction du carnet.
  expect(sent).toBe(0);
});

// Le chemin nominal ne prévalide plus : chaque saisie coûtait deux transactions
// complètes au thread unique du carnet.
test("lot UI 2 : un enregistrement nominal n'envoie qu'une seule requête", async ({page}, testInfo) => {
  test.skip(testInfo.project.name === "pwa-chromium", "Parcours mutateur exercé hors service worker.");
  test.setTimeout(90000);
  const posts = [];
  page.on("request", request => {
    if (request.method() === "POST" && request.url().includes("/api/v1/cultures")) posts.push(request.url());
  });
  await createMother(page, "Mère envoi unique");
  expect(posts).toEqual([expect.stringContaining("/api/v1/cultures")]);
  expect(posts.filter(url => url.includes("/preview/"))).toHaveLength(0);

  posts.length = 0;
  const form = await openObservation(page);
  await form.getByLabel("Observation", {exact: true}).fill("Observation enregistrée d'un seul envoi.");
  await form.getByRole("button", {name: "Enregistrer l’observation", exact: true}).click();
  await expect(page).toHaveURL(/#event-/);
  expect(posts).toHaveLength(1);
  expect(posts.filter(url => url.includes("/preview/"))).toHaveLength(0);
});
