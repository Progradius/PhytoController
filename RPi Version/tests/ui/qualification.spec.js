"use strict";
// Qualification automatisable de la fiche R4.1 : la part de la grille
// `docs/development/qualification-mobile-pwa.md` qui est reproductible sans appareil réel.
//
// Ce fichier ne remplace **aucune** ligne de la grille opérateur : VoiceOver/TalkBack, le
// clavier virtuel réel, l'encoche, l'installation avec certificat et la mémoire d'un
// téléphone restent hors de portée d'un navigateur piloté. Ce qui est ici, et seulement
// cela, est marqué « automatisé » dans la table de correspondance du document.
//
// Méthode du « focus non masqué » (WCAG 2.2 AA, 2.4.11) : on ne se contente pas de vérifier
// qu'un élément est « visible » — Playwright le juge visible même sous une barre fixe. On
// mesure le **recouvrement** entre la boîte de l'élément focalisé et celle de chaque barre
// fixe réellement affichée. Un recouvrement non nul est un échec.
const {test, expect} = require("@playwright/test");
const {test: testCarnet, expect: expectCarnet, createMother} = require("./culture_fixtures");
const {testAlarmeCritique} = require("./fixtures");
const crypto = require("node:crypto");
const AxeBuilder = require("@axe-core/playwright").default;
const {pour} = require("./profils");

const TAGS = ["wcag2a", "wcag2aa", "wcag22aa"];
// Hauteur retranchée au viewport pour simuler l'apparition d'un clavier virtuel. Un vrai
// clavier ne redimensionne pas toujours le viewport visuel, mais il réduit toujours la
// surface utile : c'est cette réduction que l'on reproduit.
const CLAVIER_PX = 300;
// Le formulaire de **saisie** de Solutions, et lui seul : chaque relevé du journal porte
// aussi un `form[data-solution-entry]`, mais de correction, avec un `data-id`.
const SAISIE_FORM = "form[data-solution-entry]:not([data-id])";

const BARRES_FIXES = ["#pwa-connection-banner", ".mobile-navbar", ".mobile-more-panel",
  "#config-dirty-bar", ".config-toc", ".action-toast"];

/**
 * Focalise l'élément d'`id` donné et mesure, **dans le même passage**, le recouvrement de
 * sa boîte par chaque barre fixe réellement affichée.
 *
 * Le focus et la mesure ne sont pas séparés en deux `evaluate` : entre deux allers-retours,
 * le socle des formulaires du carnet réenregistre ses champs et le focus retombait sur
 * `body`, ce qui faisait échouer la mesure sur un artefact du test, pas sur un défaut de
 * l'interface. Un opérateur, lui, touche le champ : le focus y est acquis.
 */
const recouvrementsApresFocus = (page, id) => page.evaluate(({id, selecteurs}) => {
  const cible = document.getElementById(id);
  if (!cible) return {erreur: `élément « ${id} » introuvable`};
  cible.scrollIntoView({block: "center", behavior: "instant"});
  cible.focus();
  const actif = document.activeElement;
  if (actif !== cible) {
    const nom = actif && actif !== document.body ? `${actif.tagName.toLowerCase()}#${actif.id || ""}` : "body";
    return {erreur: `le focus n'est pas resté sur « ${id} » : il est sur ${nom}`};
  }
  const boite = cible.getBoundingClientRect();
  const recouvrements = [];
  // Une barre ne masque que si elle **peint et reçoit le doigt**. Le test de recouvrement
  // ne peut donc pas se contenter de `display !== none` et d'une boîte non nulle :
  // mesuré sur Pixel 5, `.mobile-more-panel` d'un `<details>` fermé rapporte
  // `display: grid`, `visibility: visible` et une boîte de 304 × 315 au milieu de l'écran,
  // alors que Chromium n'en peint pas le contenu et que `elementFromPoint` en son centre
  // rend un élément de la page — le panneau n'intercepte rien. Sans ce test de survol, un
  // panneau replié passerait pour une barre qui masque le focus.
  const survole = node => {
    const barre = node.getBoundingClientRect();
    const dessus = document.elementFromPoint(
      Math.round(barre.left + barre.width / 2), Math.round(barre.top + barre.height / 2));
    return Boolean(dessus) && (dessus === node || node.contains(dessus));
  };
  for (const selecteur of selecteurs) {
    for (const node of document.querySelectorAll(selecteur)) {
      const style = getComputedStyle(node);
      if (node.hidden || style.display === "none" || style.visibility === "hidden") continue;
      if (!["fixed", "sticky"].includes(style.position)) continue;
      if (node.checkVisibility && !node.checkVisibility({checkOpacity: true, checkVisibilityCSS: true})) continue;
      const barre = node.getBoundingClientRect();
      if (barre.width <= 0 || barre.height <= 0) continue;
      if (!survole(node)) continue;
      const largeur = Math.max(0, Math.min(boite.right, barre.right) - Math.max(boite.left, barre.left));
      const hauteur = Math.max(0, Math.min(boite.bottom, barre.bottom) - Math.max(boite.top, barre.top));
      const aire = Math.round(largeur * hauteur);
      if (aire > 0) recouvrements.push({barre: selecteur, cible: id, aire});
    }
  }
  return {recouvrements};
}, {id, selecteurs: BARRES_FIXES});

/** Réduit la hauteur du viewport comme le ferait un clavier virtuel. */
const ouvrirClavier = async page => {
  const viewport = page.viewportSize();
  if (!viewport) return null;
  await page.setViewportSize({width: viewport.width, height: Math.max(200, viewport.height - CLAVIER_PX)});
  return viewport;
};

// ---------------------------------------------------------------------------
// R0.3 — « axe vert sur une page témoin par macro »
//
// La macro est cherchée dans le **DOM rendu**, jamais dans le gabarit : c'est la macro
// partagée qui pose la classe `.ui-*`, donc sa présence dans la page prouve que la page
// l'utilise vraiment, et pas qu'elle a recopié son balisage.
// ---------------------------------------------------------------------------
const verifierTemoin = async (page, expecter, temoin) => {
  await expecter(page.locator("main")).toBeVisible();
  await expecter(page.locator(temoin.classe),
    `${temoin.route} n'utilise pas la macro ${temoin.macro}`).not.toHaveCount(0);
  const resultat = await new AxeBuilder({page}).withTags(TAGS).analyze();
  expecter(resultat.violations).toEqual([]);
};

// Témoins visibles sans donnée particulière : le serveur partagé de la suite suffit.
const TEMOINS = [
  {macro: "compact_header", route: "/", classe: ".ui-compact-header"},
  {macro: "equipment_row", route: "/", classe: ".ui-equipment-row"},
  {macro: "field_group", route: "/conf", classe: ".ui-field-group"},
  {macro: "empty_state", route: "/cultures/solutions", classe: ".ui-empty-state"},
  {macro: "chart_detail", route: "/history", classe: ".ui-chart-detail"},
  {macro: "network_state", route: "/", classe: ".ui-network-state"},
];

for (const temoin of TEMOINS) {
  test(`R0.3 · ${temoin.macro} : page témoin ${temoin.route} verte à axe`, pour("Une cible suffit pour le contrat des macros.", "desktop-chromium"), async ({page}, testInfo) => {
    await page.goto(temoin.route);
    await verifierTemoin(page, expect, temoin);
  });
}

// `alarm_summary` ne rend **que** devant une alarme : sur le serveur nominal, `/alarms` est
// une page vide et chercher la macro n'y prouverait rien. Serveur dédié au scénario
// d'alarme critique de `tests/ui_server.py`.
testAlarmeCritique("R0.3 · alarm_summary : page témoin /alarms verte à axe", pour("Une cible suffit pour le contrat des macros.", "desktop-chromium"), async ({page}, testInfo) => {
  await page.goto("/alarms");
  await verifierTemoin(page, expect, {macro: "alarm_summary", route: "/alarms", classe: ".ui-alarm-summary"});
});

// `journal_entry` ne rend que s'il existe une opération dans le carnet. Un serveur par
// test : le carnet est muté ici, et l'espace 2 est exclusif.
testCarnet("R0.3 · journal_entry : page témoin /cultures/journal verte à axe", pour("Une cible suffit pour le contrat des macros.", "desktop-chromium"), async ({page}, testInfo) => {
  const subject = await createMother(page, "Mère journal témoin");
  const csrf = await page.locator('meta[name="csrf-token"]').getAttribute("content");
  // Un relevé suffit à peupler la vue `culture_journal` : une ligne par opération.
  const reponse = await page.request.post("/api/v1/cultures/solutions", {
    headers: {"X-CSRF-Token": csrf},
    data: {operation: "entry", request_id: crypto.randomUUID(), kind: "reading",
      targets: [subject], effective_at: "2026-08-02", ph: 6.1, ec: 1.4},
  });
  expectCarnet(reponse.ok(), `fixture de journal refusée : ${await reponse.text()}`).toBe(true);

  await page.goto("/cultures/journal");
  await verifierTemoin(page, expectCarnet, {macro: "journal_entry", route: "/cultures/journal", classe: ".ui-journal-entry"});
});

// ---------------------------------------------------------------------------
// Q09 — focus non masqué par les barres fixes, clavier virtuel simulé
// ---------------------------------------------------------------------------

test("Q09 · le dernier champ de Configuration reste dégagé sous la barre d’enregistrement", async ({page}) => {
  await page.goto("/conf");
  await expect(page.locator("main")).toBeVisible();
  await ouvrirClavier(page);

  // Toutes les sections sont dépliées : `/conf` n'en ouvre qu'une, donc le dernier champ du
  // document est sinon dans un `<details>` replié — invisible, et sans boîte à mesurer. Le
  // pire cas visé par Q09 est justement le champ le plus bas d'une page entièrement ouverte.
  await page.evaluate(() => {
    document.querySelectorAll("details.config-section").forEach(node => { node.open = true; });
  });

  // La barre n'apparaît qu'une fois le formulaire modifié : on provoque une modification
  // réelle plutôt que de forcer la classe, sinon on testerait un état que l'utilisateur
  // ne rencontre jamais.
  const nomDuDernier = await page.evaluate(() => {
    const champs = [...document.querySelectorAll(
      'form input:not([type=hidden]):not([disabled]), form select:not([disabled]), form textarea:not([disabled])')];
    // Dernier champ qui **prend réellement le focus** : une boîte non nulle ne suffit pas,
    // `visibility: hidden` en laisse une tout en retirant l'élément de la tabulation.
    for (let i = champs.length - 1; i >= 0; i--) {
      const cible = champs[i];
      const rect = cible.getBoundingClientRect();
      if (rect.width <= 0 || rect.height <= 0) continue;
      const style = getComputedStyle(cible);
      if (style.visibility === "hidden" || style.display === "none") continue;
      cible.focus();
      if (document.activeElement !== cible) continue;
      cible.id = cible.id || "q09-dernier-champ";
      // Modification réelle, puis les deux événements que `config.js` écoute.
      if (cible.type === "checkbox" || cible.type === "radio") cible.checked = !cible.checked;
      else if (cible.tagName === "SELECT") cible.selectedIndex = Math.max(0, cible.options.length - 1);
      else cible.value = cible.value === "1" ? "2" : "1";
      cible.dispatchEvent(new Event("input", {bubbles: true}));
      cible.dispatchEvent(new Event("change", {bubbles: true}));
      return cible.id;
    }
    return null;
  });
  expect(nomDuDernier, "aucun champ focalisable sur /conf").not.toBeNull();

  await expect(page.locator("#config-dirty-bar")).toHaveClass(/is-visible/, {timeout: 5000});
  // Défilement, focus et mesure **dans la page** : l'actionnabilité de Playwright attendrait
  // une stabilité que la barre fixe, qui se pose et repousse le contenu, n'offre pas tout de
  // suite. Ce qui est qualifié ici est une géométrie, pas une action.
  const mesure = await recouvrementsApresFocus(page, nomDuDernier);
  expect(mesure.erreur, mesure.erreur).toBeUndefined();
  expect(mesure.recouvrements).toEqual([]);
});

testCarnet("Q09 · le dernier champ d’un relevé reste dégagé sous les barres basses", async ({page}) => {
  await createMother(page, "Mère qualification");
  await page.goto("/cultures/solutions?view=saisir#saisie");
  await expectCarnet(page.locator("main")).toBeVisible();
  await ouvrirClavier(page);

  const form = page.locator(SAISIE_FORM);
  await expectCarnet(form).toBeVisible();

  // Le formulaire de saisie masque une partie de ses champs selon l'action choisie : le
  // dernier champ **du DOM** est souvent invisible. On vise le dernier champ réellement
  // affiché, puis le bouton d'enregistrement.
  for (const quoi of ["champ", "bouton"]) {
    const id = await form.evaluate((node, quoi) => {
      const cibles = quoi === "champ"
        ? [...node.querySelectorAll('input:not([type=hidden]):not([disabled]), select:not([disabled]), textarea:not([disabled])')]
        : [...node.querySelectorAll("button[type=submit]:not([disabled])")];
      // On remonte depuis la fin jusqu'au dernier élément qui **prend réellement le focus**.
      // Une boîte non nulle ne suffit pas : `visibility: hidden` laisse une boîte mesurable
      // mais retire l'élément de l'ordre de tabulation, et `focus()` y retombe sur `body`.
      // Or Q09 parle du dernier champ que l'opérateur peut atteindre au clavier.
      for (let i = cibles.length - 1; i >= 0; i--) {
        const cible = cibles[i];
        const rect = cible.getBoundingClientRect();
        if (rect.width <= 0 || rect.height <= 0) continue;
        const style = getComputedStyle(cible);
        if (style.visibility === "hidden" || style.display === "none") continue;
        cible.focus();
        if (document.activeElement !== cible) continue;
        cible.id = cible.id || `q09-releve-${quoi}`;
        return cible.id;
      }
      return null;
    }, quoi);
    expectCarnet(id, `aucun ${quoi} focalisable dans le formulaire de saisie`).not.toBeNull();
    const mesure = await recouvrementsApresFocus(page, id);
    expectCarnet(mesure.erreur, mesure.erreur).toBeUndefined();
    expectCarnet(mesure.recouvrements).toEqual([]);
  }
});

// ---------------------------------------------------------------------------
// États ouverts, refusés et dialogues (part « axe ne couvre pas les états ouverts »)
// ---------------------------------------------------------------------------

testCarnet("un formulaire de relevé ouvert puis refusé reste vert à axe et nomme le champ fautif", async ({page}) => {
  await createMother(page, "Mère états ouverts");
  await page.goto("/cultures/solutions?view=saisir#saisie");
  const form = page.locator(SAISIE_FORM);
  await expectCarnet(form).toBeVisible();

  const ouvert = await new AxeBuilder({page}).withTags(TAGS).analyze();
  expectCarnet(ouvert.violations).toEqual([]);

  // Refus **du serveur**, rattaché à un champ. Vider un champ `required` ne prouverait
  // rien : la validation native bloquerait l'envoi et l'état observé serait une bulle du
  // navigateur, pas le refus de l'application ni son résumé d'erreurs.
  const cible = form.locator('select[name="target"]');
  const valeur = await cible.locator("option").evaluateAll(
    options => (options.find(option => option.value) || {}).value || "");
  expectCarnet(valeur, "aucune cible sélectionnable dans le formulaire de saisie").not.toBe("");
  await cible.selectOption(valeur);
  await form.locator('input[name="ph"]').fill("abcd");
  await form.getByRole("button", {name: "Enregistrer la saisie"}).click();
  const erreurs = form.locator(".culture-form-errors").first();
  await expectCarnet(erreurs).toBeVisible();

  const refuse = await new AxeBuilder({page}).withTags(TAGS).analyze();
  expectCarnet(refuse.violations).toEqual([]);
  // Le refus se rattache au contrôle par son `name` : c'est le contrat du socle
  // `culture_forms.js`, pas un `id` deviné.
  const nommes = await page.locator("[aria-invalid=true]").count();
  expectCarnet(nommes).toBeGreaterThan(0);
});

test("le dialogue de coupure est vert à axe et piège le focus", async ({page}) => {
  await page.goto("/");
  await expect(page.locator("main")).toBeVisible();
  const ouvrir = page.locator("button.override-cut").first();
  await expect(ouvrir).toBeVisible();
  await ouvrir.click();

  const dialogue = page.locator("dialog.confirm-dialog[open]").first();
  await expect(dialogue).toBeVisible();
  const resultat = await new AxeBuilder({page}).withTags(TAGS).analyze();
  expect(resultat.violations).toEqual([]);

  // Focus piégé. `dashboard.js` ouvre par `showModal()` (et non `show()`) : le piège est
  // donc celui du navigateur. Ce qu'il garantit, c'est que le focus n'atteint **jamais** un
  // élément de la page derrière le dialogue — pas qu'il reste en permanence sur un nœud du
  // dialogue : en fin de cycle, Chromium passe par la barre d'outils du navigateur, et
  // `document.activeElement` retombe alors sur `body`. Exiger « toujours dans le dialogue »
  // faisait échouer le test sur ce passage parfaitement correct.
  // `:not([type=hidden]):not([disabled])` : sans cette précision, les deux `input` cachés
  // (`csrf_token`, `target`) sont comptés et la boucle tourne 9 fois pour 4 arrêts réels.
  const interactifs = await dialogue.locator(
    "a[href], button:not([disabled]), input:not([type=hidden]):not([disabled]), select:not([disabled]), textarea:not([disabled])").count();
  for (let i = 0; i < interactifs + 3; i++) {
    await page.keyboard.press("Tab");
    const place = await page.evaluate(() => {
      const ouvert = document.querySelector("dialog.confirm-dialog[open]");
      const actif = document.activeElement;
      if (!ouvert) return "dialogue fermé";
      // Le bouclage d'un dialogue modal passe une fois par <body> : ce n'est pas une sortie.
      if (!actif || actif === document.body || actif === document.documentElement) return "body";
      if (ouvert.contains(actif)) return "dialogue";
      return `${actif.tagName.toLowerCase()}${actif.id ? `#${actif.id}` : ""}`;
    });
    expect(["dialogue", "body"], `tabulation ${i + 1} : le focus a atteint « ${place} », derrière le dialogue`)
      .toContain(place);
  }

  // Échappement : le dialogue se ferme et rien n'a été commandé.
  await page.keyboard.press("Escape");
  await expect(dialogue).toBeHidden();
});

// ---------------------------------------------------------------------------
// Q08 — bannière hors ligne et lecture seule (profil `pwa-chromium`)
// ---------------------------------------------------------------------------

test("hors ligne : la bannière est visible et l’interface passe en lecture seule", pour("Un service worker est nécessaire pour servir la copie.", "pwa-chromium"), async ({page, context}, testInfo) => {
  test.skip(Boolean(process.env.PHYTO_UI_BASE_URL), "Aucune coupure provoquée sur une cible externe.");
  test.setTimeout(120_000);

  await page.goto("/");
  await expect(page.locator("main")).toBeVisible();
  const actif = await page.evaluate(async () => {
    if (!navigator.serviceWorker) return false;
    const registration = await navigator.serviceWorker.ready;
    return Boolean(registration.active);
  });
  expect(actif, "aucun service worker actif : la copie hors ligne ne peut pas être servie").toBe(true);
  // Le service worker chauffe « / », « /history », « /alarms » et « /app » à l'installation.
  await page.waitForTimeout(3_000);

  await context.setOffline(true);
  try {
    await page.goto("/").catch(() => null);
    const banniere = page.locator("#pwa-connection-banner");
    await expect(banniere).toBeVisible({timeout: 90_000});
    await expect(banniere).toContainText("HORS LIGNE");
    await expect(page.locator("body")).toHaveClass(/is-offline/);

    // Lecture seule : plus aucune commande mutante n'est activable. Les contrôles d'un
    // formulaire GET explicitement local restent utilisables — c'est le contrat de `pwa.js`.
    const mutantsActifs = await page.evaluate(() => [...document.querySelectorAll(
      "form[method='post'] button, form[method='post'] input, button[data-requires-online]")]
      .filter(node => !node.disabled).length);
    expect(mutantsActifs, "une commande reste activable hors ligne").toBe(0);
  } finally {
    await context.setOffline(false);
  }
});

// ---------------------------------------------------------------------------
// Zoom 200 % (projet `mobile-zoom`)
// ---------------------------------------------------------------------------

const ROUTES_ZOOM = ["/", "/alarms", "/conf", "/cultures", "/history"];

for (const route of ROUTES_ZOOM) {
  test(`zoom 200 % · ${route} ne défile pas horizontalement et garde ses cibles ≥ 24 px`, pour("Mesure propre au profil de zoom.", "mobile-zoom"), async ({page}, testInfo) => {
    await page.goto(route);
    await expect(page.locator("main")).toBeVisible();

    const mesure = await page.evaluate(() => {
      const visible = node => {
        const rect = node.getBoundingClientRect();
        if (rect.width <= 0 || rect.height <= 0) return false;
        const style = getComputedStyle(node);
        return style.visibility !== "hidden" && style.display !== "none";
      };
      // Exception WCAG 2.2 « target-size-minimum », clause *inline* : un **lien** placé
      // dans une phrase suit le flux du texte, sa hauteur est celle de la ligne, et
      // l'exiger à 24 px casserait le paragraphe. L'exception vaut pour `a`, pas pour un
      // bouton ni un `summary`, qui restent des cibles autonomes où qu'ils soient.
      const lienDansLeTexte = node => node.tagName === "A" && Boolean(node.closest("p, li, figcaption, dd, blockquote"));
      const petites = [...document.querySelectorAll('a[href], button, summary, [role="button"]')]
        .filter(visible)
        .filter(node => !lienDansLeTexte(node))
        .map(node => {
          const rect = node.getBoundingClientRect();
          return {texte: (node.textContent || "").replace(/\s+/g, " ").trim().slice(0, 40),
            w: Math.round(rect.width), h: Math.round(rect.height)};
        })
        .filter(item => item.w < 24 || item.h < 24);
      return {
        scrollWidth: document.documentElement.scrollWidth,
        clientWidth: document.documentElement.clientWidth,
        petites: petites.slice(0, 20),
      };
    });

    // Une tolérance d'un pixel absorbe les arrondis de rendu ; au-delà, la page déborde.
    expect(mesure.scrollWidth, `${route} déborde horizontalement`).toBeLessThanOrEqual(mesure.clientWidth + 1);
    expect(mesure.petites, `${route} : cibles sous 24 px en zoom 200 %`).toEqual([]);
  });
}

// Zoom **de la police** à 200 % : c'est le second geste de l'agrandissement, distinct du zoom
// de page mesuré ci-dessus (`deviceScaleFactor` sur un viewport réduit). Il ne change pas la
// largeur de la fenêtre, seulement la taille de tous les textes — donc tout ce qui est mesuré
// en `rem` ou dicté par la taille minimale d'un contenu. C'est ce scénario qui a fait défiler
// le tableau de bord horizontalement (465 px pour une fenêtre de 390) : le corps de la page ne
// doit jamais défiler ainsi ; seuls un tableau, un diagramme ou un bloc de code débordent,
// dans leur propre conteneur à défilement.
const ROUTES_ZOOM_POLICE = ["/", "/alarms", "/history", "/conf", "/console", "/cultures",
  "/cultures/solutions", "/cultures/cycles", "/cultures/targets", "/cultures/light",
  "/cultures/equipment", "/cultures/journal", "/app", "/offline"];

for (const route of ROUTES_ZOOM_POLICE) {
  test(`zoom 200 % de la police · ${route} ne fait pas défiler le corps horizontalement`, pour("Mesure propre au profil de zoom.", "mobile-zoom"), async ({page}, testInfo) => {
    await page.goto(route);
    await expect(page.locator("main")).toBeVisible();
    await page.evaluate(() => { document.documentElement.style.fontSize = "200%"; });
    await page.evaluate(() => document.fonts.ready.then(() => true));

    const mesure = await page.evaluate(() => {
      const limite = document.documentElement.clientWidth;
      // Un conteneur à défilement propre a le droit de porter un contenu plus large que lui :
      // ce qui est interdit, c'est que le **corps** défile.
      const dansUnConteneurDefilant = node => {
        for (let parent = node.parentElement; parent && parent !== document.body; parent = parent.parentElement) {
          if (["auto", "scroll"].includes(getComputedStyle(parent).overflowX)) return true;
        }
        return false;
      };
      const debordants = [...document.querySelectorAll("body *")]
        .filter(node => {
          const rect = node.getBoundingClientRect();
          if (rect.width <= 0 || rect.right <= limite + 0.5) return false;
          return !dansUnConteneurDefilant(node);
        })
        .map(node => `${node.tagName.toLowerCase()}.${String(node.className || "").trim().split(/\s+/)[0] || ""}`
          + ` → ${Math.round(node.getBoundingClientRect().right)} px`);
      return {scrollWidth: document.documentElement.scrollWidth, clientWidth: limite,
        debordants: [...new Set(debordants)].slice(0, 8)};
    });

    expect(mesure.debordants, `${route} : éléments hors de la fenêtre au zoom 200 % de la police`).toEqual([]);
    // Une tolérance d'un pixel absorbe les arrondis de rendu ; au-delà, la page déborde.
    expect(mesure.scrollWidth, `${route} déborde horizontalement (zoom 200 % de la police)`)
      .toBeLessThanOrEqual(mesure.clientWidth + 1);
  });
}

test("zoom 200 % · le menu mobile « Plus » reste ouvrable et ses entrées atteignables", pour("Mesure propre au profil de zoom.", "mobile-zoom"), async ({page}, testInfo) => {
  await page.goto("/");
  const plus = page.locator(".mobile-more > summary");
  await expect(plus).toBeVisible();
  await plus.click();
  const panneau = page.locator(".mobile-more-panel");
  await expect(panneau).toBeVisible();

  const debordement = await page.evaluate(() => {
    const node = document.querySelector(".mobile-more-panel");
    const rect = node.getBoundingClientRect();
    return {gauche: Math.round(rect.left), droite: Math.round(rect.right),
      largeur: document.documentElement.clientWidth};
  });
  expect(debordement.gauche).toBeGreaterThanOrEqual(0);
  expect(debordement.droite).toBeLessThanOrEqual(debordement.largeur + 1);
});
