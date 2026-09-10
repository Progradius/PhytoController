"use strict";

// Passe « photos » : aperçu local avant tout envoi sur les trois formulaires photo du
// carnet, et progression réelle de l'envoi binaire. Un serveur de carnet par test
// (fixture partagée) : l'espace 2 est exclusif et une occupation ouverte n'a pas de fin.
// Rien ici ne touche un GPIO, un réglage, un override ou le watchdog ; l'aperçu, en
// particulier, n'émet aucune requête.
const {test, expect, AxeBuilder, createMother, PNG_1x1} = require("./culture_fixtures");

const photo = name => ({name, mimeType: "image/png", buffer: PNG_1x1});

// Une observation d'espace : c'est la seule entrée du journal qui porte un formulaire
// photo (`item.source == 'space_event' and item.editable`).
const observe = async (page, note) => {
  await page.goto("/cultures/journal");
  const details = page.locator("details").filter({hasText: "Enregistrer une observation d’espace"}).first();
  await details.locator("summary").click();
  const form = details.locator("form");
  await form.getByLabel("Espace observé").selectOption({label: "Espace 2"});
  await form.getByLabel("Observation", {exact: true}).fill(note);
  await form.getByRole("button", {name: "Enregistrer l’observation"}).click();
  await expect(page.getByText(note, {exact: false}).first()).toBeVisible();
};

// Le formulaire photo de la première entrée du journal, son repli ouvert.
const journalPhotoForm = async page => {
  const entry = page.locator("article.culture-journal-entry").first();
  const details = entry.locator("details").filter({hasText: "Ajouter une photo à cette observation"});
  await details.locator("summary").click();
  const form = details.locator("form[data-journal-photo]");
  await expect(form).toBeVisible();
  return {entry, form};
};

// Le formulaire d'observation de la fiche vit dans un repli de la triade d'en-tête.
const observationForm = async page => {
  const details = page.locator("#observation");
  if ((await details.getAttribute("open")) === null) await details.locator(":scope > summary").click();
  const form = page.locator("form[data-culture-observation]");
  await expect(form).toBeVisible();
  return form;
};

// Le formulaire « Ajouter une photo à cette entrée », sous une entrée non annulée.
const entryPhotoForm = async page => {
  const details = page.locator("details").filter({hasText: "Ajouter une photo à cette entrée"}).first();
  await details.locator("summary").click();
  const form = details.locator("form[data-photo-form]");
  await expect(form).toBeVisible();
  return form;
};

// L'aperçu doit être une image réellement décodée par le navigateur, pas seulement un
// élément visible : une URL d'objet refusée par la politique de sécurité de contenu
// laisserait un `<img>` cassé, donc visible et vide. `naturalWidth` tranche.
const expectDecoded = async locator => {
  await expect(locator).toBeVisible();
  await expect(locator).not.toHaveAttribute("alt", "");
  await expect.poll(async () => locator.evaluate(node => node.naturalWidth),
    {message: "L’aperçu local doit être décodé par le navigateur"}).toBeGreaterThan(0);
};

// ---------------------------------------------------------------------------
// T1. Envoi réel d'une photo par la route binaire, depuis le journal
// ---------------------------------------------------------------------------

test("photos : une photo part réellement par la route binaire depuis le journal", async ({page}, testInfo) => {
  test.skip(testInfo.project.name === "pwa-chromium", "Parcours mutateur exercé hors service worker.");
  test.setTimeout(90000);
  await createMother(page, "Mère photos T1");
  await observe(page, "Bac rincé avant bouturage");

  let {entry, form} = await journalPhotoForm(page);
  await expect(entry.locator("figure.culture-photo img")).toHaveCount(0);
  await form.locator('input[type="file"][name="photo"]').setInputFiles(photo("carnet.png"));
  await form.getByLabel("Légende", {exact: true}).fill("Cliché synthétique 1×1");
  await form.getByRole("button", {name: "Envoyer la photo"}).click();

  // Le retour après enregistrement vise l'entrée : c'est la confirmation. L'ancre seule
  // ne prouve rien (l'observation en a déjà posé une) ; la galerie de l'entrée, si.
  entry = page.locator("article.culture-journal-entry").first();
  await expect(entry.locator("figure.culture-photo img")).toHaveCount(1);
  await expect(entry.locator("figure.culture-photo figcaption").first())
    .toContainText("Cliché synthétique 1×1");
});

// ---------------------------------------------------------------------------
// T2. Aperçu local sur les trois formulaires photo, sans le moindre envoi
// ---------------------------------------------------------------------------

test("photos : l’aperçu local s’affiche sur les trois formulaires sans rien envoyer", async ({page}, testInfo) => {
  test.skip(testInfo.project.name === "pwa-chromium", "Parcours mutateur exercé hors service worker.");
  test.setTimeout(90000);
  const mother = await createMother(page, "Mère photos T2");
  await observe(page, "Observation à illustrer");

  // Les envois de préparation sont derrière nous : seul ce qui suit est observé.
  const posts = [];
  page.on("request", request => {
    if (request.method() === "POST" && request.url().includes("/api/v1/cultures")) posts.push(request.url());
  });

  // 1. Journal : photo d'une observation d'espace.
  const {form: journal} = await journalPhotoForm(page);
  await journal.locator('input[type="file"][name="photo"]').setInputFiles(photo("journal.png"));
  await expectDecoded(journal.locator("[data-culture-photo-preview] img"));

  // 2. Fiche : observation et photo en une fois.
  await page.goto(`/cultures/${mother}`);
  const observation = await observationForm(page);
  await observation.locator('input[type="file"][name="photo"]').setInputFiles(photo("fiche.png"));
  await expectDecoded(observation.locator("[data-culture-photo-preview] img"));

  // 3. Fiche : photo ajoutée à une entrée déjà écrite.
  const added = await entryPhotoForm(page);
  await added.locator('input[type="file"][name="photo"]').setInputFiles(photo("entree.png"));
  await expectDecoded(added.locator("[data-culture-photo-preview] img"));

  // L'aperçu est une lecture locale : aucune mutation, aucune mise en attente.
  expect(posts).toEqual([]);
  expect(await page.evaluate(() => document.documentElement.scrollWidth - innerWidth)).toBeLessThanOrEqual(1);
});

// ---------------------------------------------------------------------------
// T3. Changer de fichier remplace l'aperçu au lieu de l'empiler
// ---------------------------------------------------------------------------

test("photos : changer de fichier remplace l’aperçu", async ({page}, testInfo) => {
  test.skip(testInfo.project.name !== "desktop-chromium", "Règle de rendu sans dépendance au gabarit.");
  test.setTimeout(90000);
  await createMother(page, "Mère photos T3");
  await observe(page, "Observation à réillustrer");
  const {form} = await journalPhotoForm(page);
  const file = form.locator('input[type="file"][name="photo"]');
  const images = form.locator("[data-culture-photo-preview] img");

  await file.setInputFiles(photo("premiere.png"));
  await expectDecoded(images);
  const first = await images.getAttribute("src");

  await file.setInputFiles(photo("seconde.png"));
  // La révocation de l'URL précédente n'est pas observable depuis la page : seule
  // l'absence d'empilement et la nouvelle URL le sont. Le reste est vérifié par lecture
  // du socle, qui révoque avant de recréer, à la remise à zéro et au départ de la page.
  await expect(images).toHaveCount(1);
  await expectDecoded(images);
  expect(await images.getAttribute("src")).not.toBe(first);

  // La zone appartient au **champ**, pas au formulaire : elle est le frère suivant du
  // `<label>` enveloppant de ce champ-là. Cherchée dans tout le formulaire, deux champs
  // photo d'un même formulaire se partageraient la première trouvée et le second
  // effacerait l'aperçu du premier. Le nom accessible du champ reste « Photo » seul :
  // rien n'est entré dans le label, ni l'aperçu ni un message.
  await expect(form.getByLabel("Photo", {exact: true})).toHaveCount(1);
  expect(await file.evaluate(node => {
    const next = node.closest("label")?.nextElementSibling;
    return next?.tagName === "FIGURE" && next.hasAttribute("data-culture-photo-preview");
  })).toBe(true);
});

test("photos : caméra, image existante et reprise pilotent le même champ", async ({page}, testInfo) => {
  test.skip(testInfo.project.name !== "desktop-chromium", "Contrat du socle, une cible suffit.");
  test.setTimeout(90000);
  await createMother(page, "Mère photos choix");
  await observe(page, "Observation avec choix de source");
  const {form} = await journalPhotoForm(page);
  const file = form.locator('input[type="file"][name="photo"]');
  const camera = form.getByRole("button", {name: "Prendre une photo"});
  const library = form.getByRole("button", {name: "Choisir une image existante"});
  await expect(camera).toBeVisible(); await expect(library).toBeVisible();

  // `capture` n'est **jamais** dans le HTML servi : présent, un appui direct sur le champ
  // ouvrirait la caméra sur iOS/Android et le choix d'une image existante serait imposé de
  // passer par le bouton — y compris avant l'exécution du JavaScript, c'est-à-dire
  // exactement ce que la fiche interdit. L'attribut n'est posé que par le bouton.
  await expect(file).not.toHaveAttribute("capture");

  await file.evaluate(node => { node.click = () => { window.__photoClick = (window.__photoClick || 0) + 1; }; });
  await library.click();
  await expect(file).not.toHaveAttribute("capture");
  await camera.click();
  await expect(file).toHaveAttribute("capture", "environment");
  expect(await page.evaluate(() => window.__photoClick)).toBe(2);

  await file.setInputFiles(photo("premiere.png"));
  await expect(form.getByRole("button", {name: "Reprendre la photo"})).toBeVisible();
  await file.setInputFiles(photo("reprise.png"));
  await expect(form.locator("[data-culture-photo-preview] img")).toHaveCount(1);

  // Une remise à zéro vide le champ : le bouton ne peut plus proposer « Reprendre ».
  await form.evaluate(node => node.reset());
  await expect(form.getByRole("button", {name: "Prendre une photo"})).toBeVisible();
  await expect(form.locator("[data-culture-photo-preview] img")).toHaveCount(0);
});

// ---------------------------------------------------------------------------
// T8. Reprise sans doublon : la clé d'idempotence survit au changement de photo
// ---------------------------------------------------------------------------

test("photos : reprendre la photo ne crée ni seconde note ni seconde clé", async ({page}, testInfo) => {
  test.skip(testInfo.project.name !== "desktop-chromium", "Contrat du socle, une cible suffit.");
  test.setTimeout(90000);
  const mother = await createMother(page, "Mère photos reprise");
  await page.goto(`/cultures/${mother}`);

  // L'observation part par `/api/v1/cultures` (JSON), la photo par `/api/v1/cultures/photos`
  // (binaire) : deux actes successifs du **même** formulaire. La clé de l'observation ne
  // doit dépendre que de son texte, jamais du fichier choisi.
  const clesObservation = [];
  await page.route("**/api/v1/cultures", async route => {
    if (route.request().method() !== "POST") { await route.continue(); return; }
    clesObservation.push(JSON.parse(route.request().postData()).request_id);
    // Premier envoi refusé par le réseau : la saisie reste, la clé aussi.
    if (clesObservation.length === 1) { await route.abort("failed"); return; }
    await route.continue();
  });

  const form = await observationForm(page);
  await form.getByLabel("Observation", {exact: true}).fill("Bac observé, photo à reprendre");
  const file = form.locator('input[type="file"][name="photo"]');
  await file.setInputFiles(photo("premiere.png"));
  await form.getByRole("button", {name: "Enregistrer l’observation"}).click();
  await expect(form.locator('.culture-form-errors[role="alert"]')).toBeVisible();

  // Reprise : le fichier change, le texte non.
  await file.setInputFiles(photo("reprise.png"));
  await expect(form.locator("[data-culture-photo-preview] img")).toHaveCount(1);
  await form.getByRole("button", {name: "Enregistrer l’observation"}).click();

  await expect.poll(() => clesObservation.length, {timeout: 20000}).toBe(2);
  // Même clé : si la première réponse s'était perdue, le serveur reconnaîtrait le même
  // enregistrement au lieu d'en créer un second.
  expect(clesObservation[1]).toBe(clesObservation[0]);

  // Le succès ramène la fiche sur l'entrée créée : c'est la confirmation, et c'est aussi
  // la fin de la navigation — un `goto` lancé ici entrerait en concurrence avec elle.
  await expect(page).toHaveURL(/#event-/, {timeout: 20000});
  // Et une seule entrée dans le carnet, quelles que soient les deux photos choisies. La
  // note apparaît aussi ailleurs sur la fiche (agenda du jour) : ce qui se compte ici est
  // l'**entrée** du journal, pas une occurrence de texte.
  await expect(page.locator('article[id^="event-"]').filter({hasText: "Bac observé, photo à reprendre"}))
    .toHaveCount(1);
});

// ---------------------------------------------------------------------------
// T9. Refus de taille : le message nomme la limite
// ---------------------------------------------------------------------------

test("photos : une photo trop lourde est refusée par un message qui nomme la limite", async ({page}, testInfo) => {
  test.skip(testInfo.project.name === "pwa-chromium", "Parcours mutateur exercé hors service worker.");
  test.setTimeout(90000);
  await createMother(page, "Mère photos refus");
  await observe(page, "Observation dont la photo est trop lourde");

  // 6 Mio : au-dessus des 5 Mio acceptés. Le refus vient du serveur HTTP, en texte brut,
  // avant même que le carnet ne soit consulté — c'est le socle qui doit nommer la limite.
  const trop = {name: "trop-lourde.png", mimeType: "image/png", buffer: Buffer.alloc(6 * 1024 * 1024, 7)};
  const {form} = await journalPhotoForm(page);
  await form.locator('input[type="file"][name="photo"]').setInputFiles(trop);
  await form.getByRole("button", {name: "Envoyer la photo"}).click();

  const refus = form.locator('.culture-form-errors[role="alert"]');
  await expect(refus).toBeVisible({timeout: 30000});
  await expect(refus).toContainText("5 Mio");
  // Rien n'a été enregistré et le formulaire reste utilisable pour reprendre la photo.
  await expect(form.getByRole("button", {name: "Envoyer la photo"})).toBeEnabled();
  await expect(form.locator("progress")).toHaveCount(0);
});

// ---------------------------------------------------------------------------
// T4. Progression réelle pendant un envoi retenu
// ---------------------------------------------------------------------------

test("photos : la progression d’envoi s’affiche puis disparaît", async ({page}, testInfo) => {
  test.skip(testInfo.project.name === "pwa-chromium", "Parcours mutateur exercé hors service worker.");
  test.setTimeout(90000);
  await createMother(page, "Mère photos T4");
  await observe(page, "Observation avec envoi retenu");

  // La réponse est retenue une seconde et demie : l'état d'envoi est alors observable.
  await page.route("**/api/v1/cultures/journal/photos", async route => {
    await new Promise(resolve => setTimeout(resolve, 1500));
    await route.fulfill({status: 200, contentType: "application/json",
      body: JSON.stringify({saved: true, id: "photo-simulee"})});
  });

  const {form} = await journalPhotoForm(page);
  await form.locator('input[type="file"][name="photo"]').setInputFiles(photo("progression.png"));
  await form.getByRole("button", {name: "Envoyer la photo"}).click();

  // Assertion d'état, jamais d'un pourcentage précis : le nombre d'événements de
  // progression dépend de la pile réseau et un seuil chiffré serait un test instable.
  // Une requête retenue par `page.route` n'atteint jamais la pile réseau du navigateur :
  // Chromium n'émet alors aucun événement `xhr.upload`, et le pourcentage n'est pas
  // observable ici. Ce qui l'est — et ce qui compte — est l'état posé par le socle :
  // la barre est là, indéterminée, et le texte annoncé de la région `aria-live` reste
  // celui de l'appelant, sans quoi chaque pour cent serait annoncé.
  const bar = form.locator("output progress");
  await expect(bar).toBeVisible();
  await expect(bar).toHaveAttribute("aria-label", "Progression de l’envoi de la photo");
  expect(await bar.evaluate(node => node.position)).toBe(-1);
  await expect(form.locator("output")).toContainText("enregistrement de la photo");

  // La réponse arrive : la page recharge sur l'entrée, sans barre ni bouton bloqué.
  await expect(page).toHaveURL(/#entry-/);
  await expect(page.locator("progress")).toHaveCount(0);
});

// ---------------------------------------------------------------------------
// T5. Échec réseau : refus annoncé, saisie conservée, formulaire réutilisable
// ---------------------------------------------------------------------------

test("photos : un échec réseau conserve la saisie et rend le formulaire", async ({page}, testInfo) => {
  test.skip(testInfo.project.name === "pwa-chromium", "Parcours mutateur exercé hors service worker.");
  test.setTimeout(90000);
  await createMother(page, "Mère photos T5");
  await observe(page, "Observation dont la photo échoue");
  await page.route("**/api/v1/cultures/journal/photos", route => route.abort("failed"));

  const {form} = await journalPhotoForm(page);
  await form.locator('input[type="file"][name="photo"]').setInputFiles(photo("perdue.png"));
  await form.getByLabel("Légende", {exact: true}).fill("Légende à conserver");
  const submit = form.getByRole("button", {name: "Envoyer la photo"});
  await submit.click();

  // Le refus est annoncé par le résumé du socle, et rien n'est mis en attente.
  await expect(form.locator('.culture-form-errors[role="alert"]')).toBeVisible();
  // La saisie reste intacte : la clé d'idempotence aussi, donc un renvoi vérifie le même
  // enregistrement au lieu d'en créer un second.
  await expect(form.locator('input[name="caption"]')).toHaveValue("Légende à conserver");
  await expect(form.locator("progress")).toHaveCount(0);
  await expect(form.locator("[data-culture-photo-preview] img")).toHaveCount(1);
  // `disabled`, pas `aria-disabled` : un bouton seulement marqué resterait cliquable.
  await expect(submit).toBeEnabled();
});

// ---------------------------------------------------------------------------
// T6. Accessibilité de la page pendant un aperçu et un envoi en cours
// ---------------------------------------------------------------------------

test("photos : aperçu affiché et envoi en cours ne créent aucune violation d’accessibilité", async ({page}, testInfo) => {
  test.skip(testInfo.project.name === "pwa-chromium", "Parcours mutateur exercé hors service worker.");
  test.setTimeout(90000);
  await createMother(page, "Mère photos T6");
  await observe(page, "Observation auditée");

  let release;
  const held = new Promise(resolve => { release = resolve; });
  await page.route("**/api/v1/cultures/journal/photos", async route => {
    await held;
    await route.abort("failed");
  });

  const {form} = await journalPhotoForm(page);
  await form.locator('input[type="file"][name="photo"]').setInputFiles(photo("axe.png"));
  await expectDecoded(form.locator("[data-culture-photo-preview] img"));
  await form.getByRole("button", {name: "Envoyer la photo"}).click();
  await expect(form.locator("output progress")).toBeVisible();

  expect((await new AxeBuilder({page}).analyze()).violations).toEqual([]);
  expect(await page.evaluate(() => document.documentElement.scrollWidth - innerWidth)).toBeLessThanOrEqual(1);
  release();
  await expect(form.locator('.culture-form-errors[role="alert"]')).toBeVisible();
});

// ---------------------------------------------------------------------------
// T7. Un second envoi pendant le premier ne crée pas de seconde barre
// ---------------------------------------------------------------------------

test("photos : un second envoi pendant le premier ne crée pas de seconde barre", async ({page}, testInfo) => {
  test.skip(testInfo.project.name !== "desktop-chromium", "Règle du socle, indépendante du profil.");
  test.setTimeout(90000);
  await createMother(page, "Mère photos T7");
  await observe(page, "Observation à double envoi");

  let release;
  const held = new Promise(resolve => { release = resolve; });
  await page.route("**/api/v1/cultures/journal/photos", async route => {
    await held;
    await route.abort("failed");
  });

  const {form} = await journalPhotoForm(page);
  await form.locator('input[type="file"][name="photo"]').setInputFiles(photo("double.png"));

  // Ce qui se compte ici est une **création**, pas un état : la barre du second envoi,
  // si elle naissait, serait retirée par le `finally` de ce même envoi refusé, donc
  // invisible à toute assertion d'état. Seul un observateur de mutations sépare « créée
  // une fois » de « créée deux fois puis retirée ».
  await page.evaluate(() => {
    window.__phytoBarInsertions = 0;
    new MutationObserver(records => {
      for (const record of records) {
        for (const node of record.addedNodes) {
          if (node.nodeName === "PROGRESS") window.__phytoBarInsertions += 1;
        }
      }
    }).observe(document.body, {childList: true, subtree: true});
  });

  // Le bouton d'envoi est `disabled` pendant l'envoi : un `click()` ne partirait pas et
  // ne prouverait rien. Le second départ est donc demandé au formulaire lui-même, ce qui
  // emprunte exactement le chemin d'un double envoi et exerce la garde `busy` du socle.
  await form.evaluate(node => node.requestSubmit());
  await expect(form.locator("output progress")).toHaveCount(1);
  await form.evaluate(node => node.requestSubmit());

  // Une seule création : la barre naît **après** les gardes. Créée avant, l'envoi refusé
  // par `busy` en aurait fabriqué une seconde.
  expect(await page.evaluate(() => window.__phytoBarInsertions)).toBe(1);

  release();
  await expect(form.locator('.culture-form-errors[role="alert"]')).toBeVisible();
  await expect(form.locator("progress")).toHaveCount(0);
  await expect(form.locator(".culture-upload-readout")).toHaveCount(0);
});
