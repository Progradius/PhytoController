"use strict";

// R3.3 (cycle de mise à jour) et R3.4 (brouillons) avec un **vrai** service worker, sur le
// profil `pwa-chromium`. Les versions précédentes de ces scénarios remplaçaient
// `navigator.serviceWorker` par un stub par page : chaque page avait alors son propre bus,
// donc l'activation depuis une fenêtre ne pouvait par construction rien produire dans
// l'autre — c'est-à-dire exactement ce que la fiche demande de prouver.
//
// Deux **fenêtres** d'un même contexte, et non deux contextes : deux contextes Playwright
// sont deux partitions de stockage, donc deux inscriptions de service worker distinctes,
// qui ne partagent ni version en attente ni `controllerchange`. Le scénario « activation
// depuis la seconde fenêtre » n'existe que dans une seule partition — ce qu'est un
// navigateur avec deux onglets ouverts sur le contrôleur.
const fs = require("node:fs");
const os = require("node:os");
const path = require("node:path");
const {chromium} = require("@playwright/test");
const {test: cultureTest, expect: cultureExpect, createMother} = require("./culture_fixtures");

const PWA = "pwa-chromium";

// Fait apparaître une nouvelle version du worker **sans toucher au serveur**, en
// réinscrivant le même worker sous une URL de script différente dans le même scope : le
// navigateur installe alors ce script et, un client étant contrôlé, le laisse en attente —
// exactement le cycle d'un déploiement. Le code exécuté reste le worker réel du dépôt.
//
// Ce que l'on ne peut PAS faire ici : servir un corps modifié par `context.route`. Mesuré
// sur ce dépôt (Playwright 1.5x, Chromium) — la requête de **vérification de mise à jour**
// d'un worker déjà installé n'est pas routée : le compteur d'interceptions reste à zéro et
// aucune nouvelle version n'apparaît. Seule la toute première requête d'inscription l'est.
const publierNouvelleVersion = (onglet, marque) => onglet.evaluate(async (version) => {
  await navigator.serviceWorker.register(`/service-worker.js?version=${version}`, {scope: "/"});
}, marque);

// Compte les appels à `registration.update()` sans rien changer à leur effet : c'est la
// seule façon d'observer la vérification déclenchée par un retour de veille, la requête
// réseau correspondante n'étant pas observable depuis Playwright.
const espionnerVerifications = (onglet) => onglet.addInitScript(() => {
  window.__verifications = 0;
  const original = ServiceWorkerRegistration.prototype.update;
  ServiceWorkerRegistration.prototype.update = function (...args) {
    window.__verifications += 1;
    return original.apply(this, args);
  };
});

const attendreCopie = (page, chemin) => cultureExpect.poll(() => page.evaluate(async (attendu) => {
  const cible = new URL(attendu, location.origin).href;
  for (const name of await caches.keys()) {
    if (!name.startsWith("phyto-pages-") && !name.startsWith("phyto-cultures-")) continue;
    if (await (await caches.open(name)).match(cible)) return true;
  }
  return false;
}, chemin), {timeout: 20000}).toBe(true);

const versionEnAttente = (page) => page.evaluate(async () => {
  const registration = await navigator.serviceWorker.getRegistration("/");
  return Boolean(registration && registration.waiting);
});

cultureTest("mise à jour : la fenêtre sale garde sa saisie, la fenêtre propre recharge", async ({page, context}, testInfo) => {
  cultureTest.skip(testInfo.project.name !== PWA, "Un vrai service worker est réservé au profil PWA.");
  cultureTest.setTimeout(120_000);

  // Fenêtre A : une fiche de culture avec une saisie non enregistrée.
  await espionnerVerifications(page);
  const mother = await createMother(page, "Mère mise à jour");
  await page.goto(`/cultures/${mother}`);
  await page.evaluate(() => navigator.serviceWorker.ready);
  const details = page.locator("#observation");
  if ((await details.getAttribute("open")) === null) await details.locator(":scope > summary").click();
  const saisie = page.getByLabel("Observation", {exact: true});
  await saisie.fill("Note en cours de rédaction");
  await cultureExpect.poll(() => page.evaluate(() => Boolean(window.PhytoForms?.isDirty()))).toBe(true);
  let navigationsA = 0;
  page.on("framenavigated", (frame) => { if (frame === page.mainFrame()) navigationsA += 1; });

  // Fenêtre B : c'est d'elle que part l'activation.
  const seconde = await context.newPage();
  await seconde.goto("/app");
  await publierNouvelleVersion(seconde, "essai");

  const banniereB = seconde.locator("#pwa-update-banner");
  await cultureExpect(banniereB).toBeVisible({timeout: 30_000});
  await cultureExpect(banniereB).toContainText("Mise à jour disponible");
  // Un seul contrôle « Mettre à jour » par page : la bannière globale, et elle seule.
  await cultureExpect(seconde.getByRole("button", {name: "Mettre à jour"})).toHaveCount(1);
  // La rubrique Version de `/app` affiche le même état sans dupliquer la commande.
  await cultureExpect(seconde.locator("section [data-pwa-update-state]")).toContainText("Mise à jour disponible");

  // A voit aussi la version disponible, sans rien perdre.
  await cultureExpect(page.locator("#pwa-update-banner")).toBeVisible({timeout: 30_000});

  const navigationsAvant = navigationsA;
  await Promise.all([
    seconde.waitForNavigation({timeout: 30_000}),
    seconde.getByRole("button", {name: "Mettre à jour"}).click(),
  ]);

  // A : message explicite, saisie intacte, aucun rechargement.
  await cultureExpect(page.locator("#pwa-update-banner")).toContainText("La mise à jour s’appliquera à la prochaine ouverture");
  await cultureExpect(saisie).toHaveValue("Note en cours de rédaction");
  cultureExpect(navigationsA).toBe(navigationsAvant);
  // B : rechargée sur la nouvelle version.
  await cultureExpect(seconde.locator("main h1")).toHaveText("Application sur ce téléphone");

  // Retour de veille : la page redemande au navigateur s'il existe une version. Sans cela,
  // une PWA restée ouverte des jours ne l'apprendrait qu'au prochain chargement complet.
  const avant = await page.evaluate(() => window.__verifications);
  await page.evaluate(() => document.dispatchEvent(new Event("visibilitychange")));
  await cultureExpect.poll(() => page.evaluate(() => window.__verifications), {timeout: 10_000})
    .toBeGreaterThan(avant);
});

cultureTest("hors ligne : l’ancienne page vit sur ses caches tant que la version attend", async ({page, context}, testInfo) => {
  cultureTest.skip(testInfo.project.name !== PWA, "Un vrai service worker est réservé au profil PWA.");
  cultureTest.setTimeout(120_000);

  await page.goto("/");
  await page.evaluate(() => navigator.serviceWorker.ready);
  await attendreCopie(page, "/");

  await publierNouvelleVersion(page, "hors-ligne");
  await cultureExpect(page.locator("#pwa-update-banner")).toBeVisible({timeout: 30_000});
  cultureExpect(await versionEnAttente(page)).toBe(true);

  // Coupure : la version en attente n'a toujours pas été activée, donc les caches de
  // l'ancienne version sont intacts et c'est bien la page datée qui s'affiche.
  await context.setOffline(true);
  await page.reload();
  await cultureExpect(page.locator('meta[name="phyto-offline-shell"]')).toHaveCount(1);
  await cultureExpect(page.locator("main h1")).toBeVisible();
  await cultureExpect(page.locator("#pwa-connection-banner")).toBeVisible();
  cultureExpect(await versionEnAttente(page)).toBe(true);
  // Aucune activation implicite : la commande reste offerte à l'opérateur.
  await cultureExpect(page.getByRole("button", {name: "Mettre à jour"})).toHaveCount(1);

  await context.setOffline(false);
});

// ---------------------------------------------------------------------------
// R3.4 — brouillons : survie à la fermeture du navigateur, restauration explicite,
// mesure jamais restaurée, version changée refusée.
// ---------------------------------------------------------------------------

// Un contexte **persistant** : c'est la seule façon de prouver ce que la fiche vise —
// « arrêt du navigateur : note récupérable ». `browser.newContext()` ouvre une partition
// neuve, où IndexedDB est vide par construction : réutiliser un `storageState` ne
// transporte que les cookies et le stockage local, jamais IndexedDB. Ici le processus est
// réellement arrêté puis relancé sur le même profil sur disque.
cultureTest("brouillon : survit à la fermeture du navigateur, restauration explicite", async ({page, cultureBaseURL}, testInfo) => {
  cultureTest.skip(testInfo.project.name !== PWA, "Acceptation R3.4 : profil PWA.");
  cultureTest.setTimeout(180_000);
  const mother = await createMother(page, "Mère brouillon");

  const profil = fs.mkdtempSync(path.join(os.tmpdir(), "phyto-pwa-profil-"));
  const ouvrir = () => chromium.launchPersistentContext(profil, {headless: true, baseURL: cultureBaseURL});

  const deplier = async (onglet) => {
    const details = onglet.locator("#observation");
    if ((await details.getAttribute("open")) === null) await details.locator(":scope > summary").click();
  };

  try {
    // 1. Saisie d'une note et d'une mesure, puis arrêt du navigateur.
    let context = await ouvrir();
    let onglet = await context.newPage();
    await onglet.goto(`/cultures/${mother}`);
    await deplier(onglet);
    await onglet.getByLabel("Observation", {exact: true}).fill("Note à retrouver après extinction");
    // Aucun brouillon ne passe par `localStorage` : le stockage doit rester vide.
    await cultureExpect.poll(() => onglet.evaluate(async () => {
      const db = await new Promise((resolve, reject) => {
        const request = indexedDB.open("phyto-culture-drafts", 1);
        request.onsuccess = () => resolve(request.result); request.onerror = () => reject(request.error);
      });
      return await new Promise((resolve, reject) => {
        const get = db.transaction("drafts", "readonly").objectStore("drafts").getAll();
        get.onsuccess = () => resolve(get.result.length); get.onerror = () => reject(get.error);
      });
    }), {timeout: 15_000}).toBeGreaterThan(0);
    const champs = await onglet.evaluate(async () => {
      const db = await new Promise((resolve, reject) => {
        const request = indexedDB.open("phyto-culture-drafts", 1);
        request.onsuccess = () => resolve(request.result); request.onerror = () => reject(request.error);
      });
      return await new Promise((resolve, reject) => {
        const get = db.transaction("drafts", "readonly").objectStore("drafts").getAll();
        get.onsuccess = () => resolve(get.result[0].fields); get.onerror = () => reject(get.error);
      });
    });
    // Exactement les champs inscrits par le gabarit : la note, la date et sa précision.
    // Ni mesure, ni confirmation, ni photo, ni légende — l'inscription est un double
    // opt-in (`data-culture-draft` sur le formulaire, `data-draft-field` sur le champ),
    // donc tout champ non marqué est hors du stockage par construction.
    cultureExpect(champs.map((champ) => champ.name).sort())
      .toEqual(["effective_at", "effective_at_precision", "note"]);
    cultureExpect(await onglet.evaluate(() => localStorage.length)).toBe(0);
    await context.close();

    // 2. Réouverture du **même profil** dans un nouveau processus : la bannière est là,
    // le champ vide, et rien n'a été renvoyé.
    context = await ouvrir();
    onglet = await context.newPage();
    const envois = [];
    onglet.on("request", (request) => { if (request.method() === "POST") envois.push(request.url()); });
    await onglet.goto(`/cultures/${mother}`);
    await deplier(onglet);
    await cultureExpect(onglet.getByText(/Brouillon sur cet appareil/)).toBeVisible({timeout: 15_000});
    await cultureExpect(onglet.getByLabel("Observation", {exact: true})).toHaveValue("");
    await onglet.getByRole("button", {name: "Restaurer le brouillon"}).click();
    await cultureExpect(onglet.getByLabel("Observation", {exact: true})).toHaveValue("Note à retrouver après extinction");
    cultureExpect(envois).toEqual([]);

    // 3. Une version de fiche différente : le brouillon est refusé, pas restauré en douce.
    await onglet.evaluate(async () => {
      const db = await new Promise((resolve, reject) => {
        const request = indexedDB.open("phyto-culture-drafts", 1);
        request.onsuccess = () => resolve(request.result); request.onerror = () => reject(request.error);
      });
      const records = await new Promise((resolve, reject) => {
        const get = db.transaction("drafts", "readonly").objectStore("drafts").getAll();
        get.onsuccess = () => resolve(get.result); get.onerror = () => reject(get.error);
      });
      for (const record of records) {
        await new Promise((resolve, reject) => {
          const remove = db.transaction("drafts", "readwrite").objectStore("drafts").delete(record.key);
          remove.onsuccess = resolve; remove.onerror = () => reject(remove.error);
        });
        record.version = `${record.version}-ancienne`;
        record.key = JSON.stringify([record.formKey, record.target, record.version]);
        await new Promise((resolve, reject) => {
          const put = db.transaction("drafts", "readwrite").objectStore("drafts").put(record);
          put.onsuccess = resolve; put.onerror = () => reject(put.error);
        });
      }
    });
    await onglet.reload();
    await deplier(onglet);
    await cultureExpect(onglet.getByText(/Brouillon refusé/)).toBeVisible({timeout: 15_000});
    await cultureExpect(onglet.getByRole("button", {name: "Restaurer le brouillon"})).toBeHidden();
    await cultureExpect(onglet.getByLabel("Observation", {exact: true})).toHaveValue("");
    await context.close();
  } finally {
    fs.rmSync(profil, {recursive: true, force: true});
  }
});
