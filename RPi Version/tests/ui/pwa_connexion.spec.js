"use strict";

// Verdict de connexion de la PWA : ce qui fait entrer en « HORS LIGNE », ce qui l'en fait sortir,
// et ce qui n'a pas le droit de l'en faire sortir. Scénarios volontairement temporels : ils
// mesurent des délais réels, `page.clock` fausserait aussi les délais de garde de `fetchWithTimeout`.
const {test, expect} = require("@playwright/test");
const {test: testCarnet, expect: expectCarnet, createMother} = require("./culture_fixtures");

const CIBLE = "desktop-chromium";

// Observe l'apparition de `is-offline` sur `document.body` : une assertion finale ne verrait pas un
// clignotement fugace, alors que les deux MutationObserver du carnet, eux, le verraient.
const guetterHorsLigne = (page) => page.addInitScript(() => {
  window.__horsLigneVu = false;
  const surveiller = () => {
    if (document.body.classList.contains("is-offline")) window.__horsLigneVu = true;
    new MutationObserver(() => {
      if (document.body.classList.contains("is-offline")) window.__horsLigneVu = true;
    }).observe(document.body, {attributes: true, attributeFilter: ["class"]});
  };
  if (document.body) surveiller();
  else document.addEventListener("DOMContentLoaded", surveiller);
});

const horsLigneVu = (page) => page.evaluate(() => window.__horsLigneVu);

const CIBLE_PWA = "pwa-chromium";

// R3.2 — IndexedDB neutralisée : aucune exception, état explicite, et surtout la page
// **entière** reste là. Compter les sections ne prouvait rien (le compte suit le gabarit
// et changeait à chaque ajout de rubrique) ; ce qui compte est que chacune des cinq
// rubriques ait rendu son contenu et qu'aucune n'ait été remplacée par un état d'erreur.
test("l’état PWA préserve la page quand le stockage local est refusé", async ({page}, testInfo) => {
  test.skip(testInfo.project.name !== CIBLE_PWA, "Acceptation R3.2 : profil PWA.");
  await page.addInitScript(() => {
    Object.defineProperty(window, "indexedDB", {configurable: true, get() { throw new Error("refusé"); }});
  });
  const erreurs = [];
  page.on("pageerror", error => erreurs.push(String(error)));
  await page.goto("/app");
  await expect(page.locator("main h1")).toHaveText("Application sur ce téléphone");
  for (const titre of ["Connexion", "Installation", "Lecture hors ligne", "Notifications locales", "Version et disponibilité"]) {
    await expect(page.getByRole("heading", {name: titre, level: 2})).toBeVisible();
  }
  // Portée à `main` : `pwaState` pose aussi l'attribut de diagnostic sur `<html>`, qui
  // répond au même sélecteur sans être une zone d'affichage.
  await expect(page.locator("main [data-pwa-storage-state]")).toContainText("stockage refusé");
  // La rubrique Connexion est renseignée par `app.js`, qui ne dépend d'aucun stockage.
  await expect(page.locator("[data-app-connection]")).toContainText(/HTTPS?/);
  // Et la boucle d'alarmes vit malgré le refus : c'est tout l'objet de la fiche.
  await expect.poll(() => page.evaluate(() => Boolean(window.PhytoPwa))).toBe(true);
  expect(erreurs).toEqual([]);
});

// R3.2 — worker refusé par le serveur : l'interface connectée doit rester entière.
test("un service worker en 500 ne retient ni le poller ni les contrôles", async ({page, context}, testInfo) => {
  test.skip(testInfo.project.name !== CIBLE_PWA, "Acceptation R3.2 : profil PWA.");
  test.setTimeout(45_000);
  // `context.route` et non `page.route` : le script du worker est demandé par le navigateur
  // pour le **contexte**, pas par la page. Vérifié : posée sur la page, l'interception est
  // ignorée et le worker s'installe normalement — le test ne testait alors rien.
  await context.route("**/service-worker.js", route => route.fulfill({
    status: 500, contentType: "text/plain", body: "panne serveur",
  }));
  let alarmes = 0;
  let etats = 0;
  await page.route("**/api/v1/alarms/active**", async route => { alarmes += 1; await route.continue(); });
  await page.route("**/api/v1/state**", async route => { etats += 1; await route.continue(); });

  await page.goto("/");
  await expect(page.locator("#control-overview")).toBeVisible();
  // Les deux boucles tournent : le poller d'alarmes de `pwa.js` et celui du tableau de bord.
  await expect.poll(() => alarmes, {timeout: 15_000}).toBeGreaterThan(0);
  await expect.poll(() => etats, {timeout: 15_000}).toBeGreaterThan(0);
  // L'état d'installation est lisible et dit l'échec, sans bloquer quoi que ce soit.
  await page.goto("/app");
  await expect(page.locator("main [data-pwa-worker-state]")).toContainText("installation échouée");
  // Les contrôles de notification restent actifs : ils ne dépendent pas du worker.
  const status = page.locator("#notification-status");
  await expect(status).not.toHaveText("État des notifications inconnu sans JavaScript.");
  const activer = page.locator("#notification-enable");
  if (await activer.isVisible()) await expect(activer).toBeEnabled();
  await expect(page.locator("main [data-pwa-storage-state]")).toContainText("Stockage local disponible");
});

// R2.4 — aucun cul-de-sac quand `beforeinstallprompt` n'est jamais émis : l'aide de la
// plateforme détectée est affichée. Deux agents utilisateur simulés, un par plateforme.
// `absent` est indispensable : le gabarit sert déjà, sans JavaScript, un texte qui cite
// **les deux** plateformes. Sans cette assertion, le test passerait à l'identique si
// `pwa.js` n'écrivait jamais rien — il ne prouverait que le rendu serveur.
for (const cas of [
  {
    nom: "iPhone",
    userAgent: "Mozilla/5.0 (iPhone; CPU iPhone OS 17_5 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.5 Mobile/15E148 Safari/604.1",
    attendu: "Partager", absent: "Dans le menu du navigateur",
  },
  {
    nom: "Android/Chromium",
    userAgent: "Mozilla/5.0 (Linux; Android 14; Pixel 5) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Mobile Safari/537.36",
    attendu: "Installer l’application", absent: "Partager",
  },
]) {
  test(`sans invite d’installation, l’aide ${cas.nom} reste visible`, async ({browser}, testInfo) => {
    test.skip(testInfo.project.name !== CIBLE, "Contrat de rendu, une cible suffit.");
    // Contexte dédié : l'agent utilisateur ne se change pas sur un contexte déjà ouvert.
    const context = await browser.newContext({
      userAgent: cas.userAgent,
      baseURL: process.env.PHYTO_UI_BASE_URL || "http://127.0.0.1:38123",
    });
    try {
      const page = await context.newPage();
      await page.goto("/app");
      // Aucun `beforeinstallprompt` n'est émis : le bouton reste caché, l'aide, elle, non.
      await expect(page.locator("#pwa-install-button")).toBeHidden();
      const aide = page.locator("[data-pwa-install-help]");
      await expect(aide).toBeVisible();
      await expect(aide).toContainText(cas.attendu);
      // Le texte servi par le gabarit cite les deux plateformes : son remplacement par
      // l'aide de la plateforme détectée se prouve par ce qui a **disparu**.
      await expect(aide).not.toContainText(cas.absent);
      await expect(page.locator("main [data-pwa-install-state]")).toContainText("Application ouverte dans le navigateur");
    } finally {
      await context.close();
    }
  });
}

// R1.5 — la fonction de libellé est pure : trois agents utilisateur réels et le repli
// générique, lus dans la page. Une inversion de branche ou une chaîne devenue
// inatteignable est visible ici, ce qu'aucune lecture du source ne montrait.
test("l’aide de refus des notifications s’adapte au navigateur", async ({page}, testInfo) => {
  test.skip(testInfo.project.name !== CIBLE, "Fonction pure, une cible suffit.");
  await page.goto("/app");
  const libelle = (userAgent, platform, touches) => page.evaluate(
    ([ua, plateforme, points]) => window.PhytoPwa.notificationDenialHelp(ua, plateforme, points),
    [userAgent, platform, touches]);

  expect(await libelle("Mozilla/5.0 (Linux; Android 14; Pixel 5) AppleWebKit/537.36 Chrome/126.0.0.0 Mobile Safari/537.36", "Linux armv8l", 5))
    .toBe("Permission refusée. Réactivez les notifications depuis les paramètres de ce site dans votre navigateur Chromium.");
  expect(await libelle("Mozilla/5.0 (iPhone; CPU iPhone OS 17_5 like Mac OS X) AppleWebKit/605.1.15 Version/17.5 Mobile/15E148 Safari/604.1", "iPhone", 5))
    .toBe("Permission refusée. Réactivez les notifications depuis les réglages Notifications de l’application ajoutée à l’écran d’accueil sur iOS.");
  expect(await libelle("Mozilla/5.0 (Android 14; Mobile; rv:127.0) Gecko/127.0 Firefox/127.0", "Linux armv8l", 5))
    .toBe("Permission refusée. Réactivez les notifications depuis les permissions de ce site dans Firefox.");
  // Repli générique : un navigateur qu'aucune branche ne reconnaît.
  expect(await libelle("Mozilla/5.0 (X11; Linux x86_64) NavigateurInconnu/1.0", "Linux x86_64", 0))
    .toBe("Permission refusée. Réactivez les notifications depuis les permissions de ce site dans votre navigateur.");
  // L'iPad récent se déclare « MacIntel » : seul l'écran tactile le distingue.
  expect(await libelle("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 Version/17.5 Safari/605.1.15", "MacIntel", 5))
    .toContain("écran d’accueil sur iOS");
});

test("un raté isolé ne bascule pas l’interface en lecture seule", async ({page}, testInfo) => {
  test.skip(testInfo.project.name !== CIBLE, "Scénario temporel, une cible suffit.");
  test.setTimeout(45_000);
  await guetterHorsLigne(page);
  const rates = {state: 0, alarms: 0};
  await page.route("**/api/v1/state**", async (route) => {
    if (rates.state++ === 1) await route.abort("connectionfailed");
    else await route.continue();
  });
  await page.route("**/api/v1/alarms/active**", async (route) => {
    if (rates.alarms++ === 1) await route.abort("connectionfailed");
    else await route.continue();
  });

  await page.goto("/");
  await expect(page.locator("#control-overview")).toBeVisible();
  // Un aller-retour de chaque boucle a échoué, puis tout est reparti : rien ne doit paraître.
  await page.waitForTimeout(12_000);
  expect(rates.state).toBeGreaterThan(1);
  await expect(page.locator("#pwa-connection-banner")).toBeHidden();
  expect(await horsLigneVu(page)).toBe(false);
});

test("une vraie coupure est annoncée après une vingtaine de secondes", async ({page}, testInfo) => {
  test.skip(testInfo.project.name !== CIBLE, "Scénario temporel, une cible suffit.");
  test.setTimeout(60_000);
  const etat = {panne: false};
  await page.route("**/api/v1/**", async (route) => {
    if (etat.panne) await route.abort("connectionfailed");
    else await route.continue();
  });
  await page.route("**/health/live**", async (route) => {
    if (etat.panne) await route.abort("connectionfailed");
    else await route.continue();
  });

  await page.goto("/");
  await expect(page.locator("#control-overview")).toBeVisible();
  const banniere = page.locator("#pwa-connection-banner");
  await expect(banniere).toBeHidden();

  const coupeA = Date.now();
  etat.panne = true;
  // Le seuil de silence est à 20 s : à 10 s, rien ne doit encore avoir bougé.
  await page.waitForTimeout(10_000);
  await expect(banniere).toBeHidden();

  await expect(banniere).toBeVisible({timeout: 25_000});
  expect(Date.now() - coupeA).toBeGreaterThan(19_000);
  await expect(banniere).toContainText("HORS LIGNE");
  await expect(page.locator("body")).toHaveClass(/is-offline/);
  await expect(page.getByRole("button", {name: "Couper"}).first()).toBeDisabled();
});

test("la sonde de joignabilité ne retire jamais la bannière", async ({page}, testInfo) => {
  test.skip(testInfo.project.name !== CIBLE, "Scénario temporel, une cible suffit.");
  test.setTimeout(60_000);
  const etat = {panne: false, sondes: 0};
  await page.route("**/api/v1/**", async (route) => {
    if (etat.panne) await route.abort("connectionfailed");
    else await route.continue();
  });
  await page.route("**/health/live**", async (route) => {
    etat.sondes += 1;
    await route.fulfill({status: 200, contentType: "application/json", body: '{"live": true}'});
  });

  await page.goto("/");
  await expect(page.locator("#control-overview")).toBeVisible();
  etat.panne = true;
  const banniere = page.locator("#pwa-connection-banner");
  await expect(banniere).toBeVisible({timeout: 30_000});

  // Le contrôleur est joignable — la sonde le prouve et tourne — mais aucune donnée fraîche n'est
  // arrivée : la bannière reste, conformément à R-WEB-06.
  const avant = etat.sondes;
  await page.waitForTimeout(8_000);
  expect(etat.sondes).toBeGreaterThan(avant);
  await expect(banniere).toBeVisible();
  await expect(page.locator("body")).toHaveClass(/is-offline/);
});

test("le retour du contrôleur retire la bannière en quelques secondes", async ({page}, testInfo) => {
  test.skip(testInfo.project.name !== CIBLE, "Scénario temporel, une cible suffit.");
  test.setTimeout(60_000);
  const etat = {panne: false};
  await page.route("**/api/v1/**", async (route) => {
    if (etat.panne) await route.abort("connectionfailed");
    else await route.continue();
  });

  await page.goto("/");
  await expect(page.locator("#control-overview")).toBeVisible();
  etat.panne = true;
  const banniere = page.locator("#pwa-connection-banner");
  await expect(banniere).toBeVisible({timeout: 30_000});

  // Les boucles métier sont retombées à 30 s d'intervalle : sans le réveil déclenché par la sonde,
  // la bannière survivrait bien plus longtemps que ce délai.
  etat.panne = false;
  const repriseA = Date.now();
  await expect(banniere).toBeHidden({timeout: 10_000});
  expect(Date.now() - repriseA).toBeLessThan(10_000);
});

test("une reprise de l’application réveille immédiatement les boucles", async ({page}, testInfo) => {
  test.skip(testInfo.project.name !== CIBLE, "Scénario temporel, une cible suffit.");
  test.setTimeout(60_000);
  const etat = {panne: false, appels: 0};
  await page.route("**/api/v1/state**", async (route) => {
    etat.appels += 1;
    if (etat.panne) await route.abort("connectionfailed");
    else await route.continue();
  });
  await page.route("**/api/v1/alarms/active**", async (route) => {
    if (etat.panne) await route.abort("connectionfailed");
    else await route.continue();
  });
  // Sonde neutralisée : seul le réveil de reprise peut relancer les boucles.
  await page.route("**/health/live**", (route) => route.abort("connectionfailed"));

  await page.goto("/");
  await expect(page.locator("#control-overview")).toBeVisible();
  etat.panne = true;
  await expect(page.locator("#pwa-connection-banner")).toBeVisible({timeout: 30_000});

  etat.panne = false;
  await page.waitForTimeout(2_000);
  const avant = etat.appels;
  await page.evaluate(() => window.dispatchEvent(new PageTransitionEvent("pageshow", {persisted: true})));
  await expect.poll(() => etat.appels, {timeout: 2_000}).toBeGreaterThan(avant);
});

test("une reprise après un long silence ne peint pas l’interface en rouge", async ({page}, testInfo) => {
  test.skip(testInfo.project.name !== CIBLE, "Scénario temporel, une cible suffit.");
  test.setTimeout(75_000);
  await guetterHorsLigne(page);
  const etat = {panne: false};
  await page.route("**/api/v1/**", async (route) => {
    if (etat.panne) await route.abort("connectionfailed");
    else await route.continue();
  });
  await page.route("**/health/live**", async (route) => {
    if (etat.panne) await route.abort("connectionfailed");
    else await route.continue();
  });

  await page.goto("/");
  await expect(page.locator("#control-overview")).toBeVisible();
  etat.panne = true;
  // 15 s de silence : le seuil de 20 s n'est pas franchi.
  await page.waitForTimeout(15_000);
  expect(await horsLigneVu(page)).toBe(false);

  // La reprise remet le compteur de silence à zéro : sans cela, l'interface passerait au rouge
  // 5 s plus tard, c'est-à-dire à la seconde même où l'opérateur rouvre son application.
  await page.evaluate(() => window.dispatchEvent(new PageTransitionEvent("pageshow", {persisted: true})));
  await page.waitForTimeout(12_000);
  expect(await horsLigneVu(page)).toBe(false);
  await expect(page.locator("#pwa-connection-banner")).toBeHidden();

  // La coupure reste bien annoncée : la reprise décale l'échéance, elle ne l'annule pas.
  await expect(page.locator("#pwa-connection-banner")).toBeVisible({timeout: 20_000});
});

test("une source dégradée le reste tant qu’elle n’a pas répondu", async ({page}, testInfo) => {
  test.skip(testInfo.project.name !== CIBLE, "Scénario temporel, une cible suffit.");
  test.setTimeout(45_000);
  // L'historique auxiliaire répond 503 — une panne prévue par l'architecture, qui ne dégrade pas le
  // contrôle. Les alarmes, elles, répondent parfaitement toutes les cinq secondes.
  const etat = {alarmes: 0};
  await page.route("**/api/v1/history**", (route) => route.fulfill({
    status: 503, contentType: "application/json", body: '{"error": "historique indisponible"}',
  }));
  await page.route("**/api/v1/alarms/active**", async (route) => { etat.alarmes += 1; await route.continue(); });

  await page.goto("/history");
  // Le serveur de test annonce l'historique indisponible : on arme la vue comme le fait déjà la
  // spec du bilan métier, pour que la relecture parte réellement vers `/api/v1/history`.
  await page.evaluate(() => { document.getElementById("tendances").dataset.historyAvailable = "true"; });
  await page.getByRole("button", {name: "Réessayer"}).click();
  const banniere = page.locator("#pwa-connection-banner");
  await expect(banniere).toBeVisible();
  await expect(banniere).toContainText("SERVICE DÉGRADÉ");
  await expect(page.locator("#pwa-connection-detail")).toContainText("Historique momentanément indisponible");

  // Le succès d'une autre source ne lève pas cette dégradation : sans quoi la panne serait affichée
  // cinq secondes puis effacée, et l'interface affirmerait que tout va bien.
  const avant = etat.alarmes;
  await page.waitForTimeout(12_000);
  expect(etat.alarmes).toBeGreaterThan(avant);
  await expect(banniere).toBeVisible();
  await expect(banniere).toContainText("SERVICE DÉGRADÉ");
  await expect(page.locator("body")).not.toHaveClass(/is-offline/);
});

testCarnet("une page du carnet servie du cache ne recharge jamais d’elle-même", async ({page}, testInfo) => {
  testCarnet.skip(testInfo.project.name !== "pwa-chromium", "Le service worker est réservé au profil PWA.");
  testCarnet.setTimeout(60_000);
  await createMother(page, "Mère reprise PWA");
  await page.evaluate(async () => { await navigator.serviceWorker.ready; });
  await page.goto("/cultures/journal");
  await expectCarnet.poll(() => page.evaluate(async () => {
    for (const name of (await caches.keys()).filter((n) => n.startsWith("phyto-cultures-"))) {
      if (await (await caches.open(name)).match(location.href.split("#")[0])) return true;
    }
    return false;
  })).toBe(true);

  await page.context().setOffline(true);
  await page.reload();
  await expectCarnet(page.locator('meta[name="phyto-offline-snapshot"]')).toHaveCount(1);
  await expectCarnet(page.locator("#pwa-connection-banner")).toBeVisible();

  let navigations = 0;
  page.on("framenavigated", (frame) => { if (frame === page.mainFrame()) navigations += 1; });
  await page.context().setOffline(false);

  // Le contrôleur redevient joignable : la page affichée reste une copie datée, donc la bannière
  // reste, aucun rechargement ne part tout seul, et c'est l'opérateur qui décide.
  const bouton = page.locator("#pwa-connection-reload");
  await expectCarnet(bouton).toBeVisible({timeout: 15_000});
  await page.waitForTimeout(8_000);
  expect(navigations).toBe(0);
  await expectCarnet(page.locator("#pwa-connection-banner")).toBeVisible();

  await bouton.click();
  await expectCarnet(page.locator('meta[name="phyto-offline-snapshot"]')).toHaveCount(0);
  await expectCarnet(page.locator("#pwa-connection-banner")).toBeHidden();
});

// ---------------------------------------------------------------------------
// R2.5 — hors ligne : les outils de lecture locale restent vivants, le filtre
// serveur est désactivé avec son message, et toute mutation est refusée.
// ---------------------------------------------------------------------------

// Attend qu'une page du carnet soit réellement conservée par le service worker : c'est la
// seule preuve qu'un rechargement hors ligne rendra une copie et non la coque `/offline`.
const attendreCopie = (page, chemin) => expectCarnet.poll(() => page.evaluate(async (attendu) => {
  const cible = new URL(attendu, location.origin).href;
  for (const name of (await caches.keys()).filter((n) => n.startsWith("phyto-cultures-"))) {
    if (await (await caches.open(name)).match(cible)) return true;
  }
  return false;
}, chemin), {timeout: 20000}).toBe(true);

testCarnet("hors ligne : explorateur vivant, filtre expliqué, envoi refusé", async ({page}, testInfo) => {
  testCarnet.skip(testInfo.project.name !== "pwa-chromium", "Le service worker est réservé au profil PWA.");
  testCarnet.setTimeout(120_000);
  const mother = await createMother(page, "Mère hors ligne");
  const csrf = await page.locator('meta[name="csrf-token"]').getAttribute("content");
  const entry = (data) => page.request.post("/api/v1/cultures/solutions", {
    headers: {"X-CSRF-Token": csrf},
    data: {operation: "entry", request_id: require("node:crypto").randomUUID(), kind: "reading", ...data},
  });
  expectCarnet((await entry({targets: [mother], effective_at: "2026-08-02", ph: 6.1})).ok()).toBe(true);
  expectCarnet((await entry({targets: [mother], effective_at: "2026-08-03", ph: 6.4})).ok()).toBe(true);

  await page.evaluate(async () => { await navigator.serviceWorker.ready; });
  for (const vue of ["saisir", "releves", "analyser"]) {
    await page.goto(`/cultures/solutions?view=${vue}`);
    await attendreCopie(page, `/cultures/solutions?view=${vue}`);
  }

  await page.context().setOffline(true);

  // 1. Explorateur de graphique : il n'est dans aucun formulaire et n'est donc jamais
  // verrouillé. Le curseur doit répondre au clavier, hors ligne comme en ligne.
  await page.goto("/cultures/solutions?view=analyser");
  await expectCarnet(page.locator('meta[name="phyto-offline-snapshot"]')).toHaveCount(1);
  await expectCarnet(page.locator("#pwa-connection-banner")).toBeVisible();
  const figure = page.locator(".solution-chart").first();
  // R2.3 : sous 48 rem l'exploration arrive repliée. Rien n'est retiré — une activation
  // suffit, et le repli fonctionne hors ligne comme le reste de la figure.
  const repli = figure.locator(".culture-chart-explorer-fold");
  if (await repli.count() && (await repli.getAttribute("open")) === null) {
    await repli.locator(":scope > summary").click();
  }
  const curseur = figure.getByRole("slider");
  await expectCarnet(curseur).toBeEnabled();
  const sortie = figure.locator(".culture-analysis-output");
  const avant = await sortie.textContent();
  await curseur.focus();
  await curseur.press("ArrowRight");
  await expectCarnet(sortie).not.toHaveText(String(avant));
  await expectCarnet(figure.getByRole("button", {name: "Point suivant"})).toBeEnabled();

  // 2. Filtre serveur : désactivé, avec son message **à côté** du formulaire.
  await page.goto("/cultures/solutions?view=releves");
  await expectCarnet(page.locator('meta[name="phyto-offline-snapshot"]')).toHaveCount(1);
  const filtre = page.locator("form.solution-filter");
  await expectCarnet(filtre.locator('select[name="target"]')).toBeDisabled();
  const note = page.locator("[data-offline-filter-note]");
  await expectCarnet(note).toHaveText("Filtre indisponible hors ligne : seules les données conservées sont affichées");
  // « À côté » et non « dedans » : le message ne fait pas partie de la zone de saisie.
  expect(await note.first().evaluate((node) => node.closest("form") === null)).toBe(true);
  expect(await filtre.evaluate((node) => node.nextElementSibling?.hasAttribute("data-offline-filter-note"))).toBe(true);

  // 3. Mutation refusée, sans mise en attente ni rejeu. Le formulaire de relevé est un
  // envoi intercepté par le socle : il ne reçoit surtout pas le message des filtres.
  await page.goto("/cultures/solutions?view=saisir");
  await expectCarnet(page.locator('meta[name="phyto-offline-snapshot"]')).toHaveCount(1);
  const saisie = page.locator("form[data-solution-entry]").first();
  expect(await saisie.evaluate((node) => node.nextElementSibling?.hasAttribute("data-offline-filter-note") === true)).toBe(false);
  const envois = [];
  page.on("request", (request) => {
    if (request.method() === "POST") envois.push(request.url());
  });
  await saisie.evaluate((node) => node.requestSubmit());
  await expectCarnet(saisie.locator("output")).toContainText("Hors ligne : saisie conservée dans cette page, aucun envoi mis en attente.");
  expect(envois).toEqual([]);

  // Retour en ligne : le message des filtres disparaît, les contrôles reviennent.
  await page.context().setOffline(false);
  await page.goto("/cultures/solutions?view=releves");
  await expectCarnet(page.locator("[data-offline-filter-note]")).toHaveCount(0);
  await expectCarnet(page.locator('form.solution-filter select[name="target"]')).toBeEnabled();
});
