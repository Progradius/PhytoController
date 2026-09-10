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
