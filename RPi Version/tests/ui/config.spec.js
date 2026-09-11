"use strict";

// Fiche R2.1 « Configuration lisible ». Aucune de ces specs n'enregistre de section :
// les seuls POST joués sont **refusés** (422) et la prévisualisation n'écrit jamais.
// Chaque test a de toute façon son propre serveur (`tests/ui/serveurs.js`) : le limiteur de
// prévisualisation de `/conf`, commun à tout un processus, ne peut plus opposer deux tests.

const {test, expect} = require("./serveurs");

const CHAMP_DECIMAL = "#target_temp_min_day";
const DERNIER_CHAMP = "#min_dwell_seconds";

const ouvrirClimat = async (page) => {
  await page.goto("/conf#temperature");
  await expect(page.locator("#temperature")).toHaveAttribute("open", "");
  await expect(page.locator(CHAMP_DECIMAL)).toBeVisible();
};

test("Chromium efface la virgule d'un type=number : le champ décimal reste en texte", async ({page}) => {
  // Mesure **réelle**, c'est elle qui justifie le choix de conception du gabarit.
  // Si un Chromium futur accepte la virgule, cette spec tombe : c'est le signal
  // attendu pour revenir à `type="number"`, pas un test à réécrire pour passer.
  await ouvrirClimat(page);
  const temoin = page.locator("#temoin-number");
  await page.evaluate(() => {
    const input = document.createElement("input");
    input.id = "temoin-number";
    input.type = "number";
    input.step = "0.1";
    document.querySelector("#temperature form").append(input);
  });
  await temoin.pressSequentially("20,5");
  expect(await temoin.inputValue()).toBe("205");
  await temoin.fill("");
  await temoin.pressSequentially("abc");
  expect(await temoin.inputValue()).toBe("");
  expect(await temoin.evaluate((node) => node.validity.valid)).toBe(true);
  await temoin.evaluate((node) => node.remove());

  // Le champ réel, lui, conserve la saisie et son contrat de validation.
  await expect(page.locator(CHAMP_DECIMAL)).toHaveAttribute("type", "text");
  await expect(page.locator(CHAMP_DECIMAL)).toHaveAttribute("inputmode", "decimal");
});

test("la virgule est acceptée et une saisie non numérique est refusée avant l'envoi", async ({page}) => {
  await ouvrirClimat(page);
  const champ = page.locator(CHAMP_DECIMAL);

  await champ.fill("20,5");
  await expect(champ).toHaveValue("20,5");
  expect(await champ.evaluate((node) => node.validity.valid)).toBe(true);

  await champ.fill("abc");
  // La saisie fautive reste **visible** : c'est tout ce que `type="number"` perd.
  await expect(champ).toHaveValue("abc");
  const refus = await champ.evaluate((node) => ({
    valide: node.validity.valid,
    message: node.validationMessage,
  }));
  expect(refus.valide).toBe(false);
  expect(refus.message).toContain("virgule ou point");

  const url = page.url();
  await page.locator("#temperature [data-save-button]").click();
  expect(page.url()).toBe(url);

  // Les bornes natives sont rejouées à l'identique, pas seulement le format.
  await champ.fill("99");
  expect(await champ.evaluate((node) => node.validationMessage))
    .toContain("inférieure ou égale à 60");
  await champ.fill("20,55");
  expect(await champ.evaluate((node) => node.validationMessage))
    .toContain("multiple de 0,1");
  await champ.fill("20,5");
  expect(await champ.evaluate((node) => node.validity.valid)).toBe(true);
});

test("deux champs refusés : la page suit le premier, celui qui est focalisé", async ({page}) => {
  await ouvrirClimat(page);
  await page.locator(CHAMP_DECIMAL).fill("abc");
  await page.locator("#absolute_floor_temp").fill("abc");

  const url = page.url();
  await page.locator("#temperature [data-save-button]").click();
  expect(page.url()).toBe(url);

  // Le navigateur focalise la **première** commande refusée : si le défilement
  // suit la dernière, l'opérateur corrige un champ qu'il ne voit pas.
  await expect.poll(() => page.evaluate(() => {
    const actif = document.activeElement;
    const boite = actif.getBoundingClientRect();
    return {
      id: actif.id,
      visible: boite.top >= 0 && boite.bottom <= window.innerHeight,
    };
  })).toEqual({id: "target_temp_min_day", visible: true});
});

test("le dernier champ d'une section n'est pas recouvert par la barre de sauvegarde", async ({page}) => {
  await ouvrirClimat(page);
  await page.locator(CHAMP_DECIMAL).fill("20,5");
  const barre = page.locator("#config-dirty-bar");
  await expect(barre).toBeVisible();

  // `scroll-margin-bottom` n'existe que pendant le focus : focaliser d'abord,
  // faire défiler ensuite — l'inverse mesurerait une marge absente.
  await page.locator(DERNIER_CHAMP).evaluate((node) => {
    node.focus({preventScroll: true});
    node.scrollIntoView({block: "nearest", behavior: "instant"});
  });
  await expect.poll(() => page.evaluate(() => {
    const champ = document.activeElement.getBoundingClientRect();
    const barre = document.getElementById("config-dirty-bar").getBoundingClientRect();
    return champ.bottom - barre.top;
  })).toBeLessThanOrEqual(0);
});

test("un refus serveur focalise le champ fautif, le centre et le laisse dégagé", async ({page}) => {
  await ouvrirClimat(page);
  // `form.submit()` court-circuite volontairement la validation du navigateur :
  // c'est le refus **serveur** qui est mesuré ici, pas celui du gabarit.
  const navigation = page.waitForURL("**/conf/temperature");
  await page.evaluate(() => {
    const form = document.querySelector("#temperature form");
    form.querySelector("#hysteresis_offset").value = "abc";
    form.submit();
  }).catch(() => { /* la navigation détruit le contexte : c'est l'effet attendu */ });
  await navigation;
  await expect(page.locator("#hysteresis_offset")).toHaveValue("abc");
  await expect(page.locator("#hysteresis_offset-error")).toBeVisible();

  const lireMesure = () => page.evaluate(() => {
    const actif = document.activeElement;
    const champ = actif.getBoundingClientRect();
    const barres = [...document.querySelectorAll(".mobile-navbar, .config-dirty-bar")]
      .filter((node) => getComputedStyle(node).position === "fixed"
        && getComputedStyle(node).display !== "none")
      .map((node) => node.getBoundingClientRect());
    return {
      id: actif.id,
      haut: champ.top,
      bas: champ.bottom,
      hauteur: window.innerHeight,
      centre: Math.abs((champ.top + champ.bottom) / 2 - window.innerHeight / 2),
      recouvrement: Math.max(0, ...barres.map((barre) => champ.bottom - barre.top), 0),
    };
  });
  // `scroll-behavior: smooth` anime le recentrage : la mesure se prend une fois
  // le défilement stabilisé, pas au premier rendu après la navigation.
  await expect.poll(async () => (await lireMesure()).id).toBe("hysteresis_offset");
  await expect.poll(async () => {
    const {haut, bas, hauteur, recouvrement, centre} = await lireMesure();
    return haut >= 0 && bas <= hauteur && recouvrement <= 0 && centre <= hauteur / 4;
  }, {message: "Champ refusé visible, dégagé des barres fixes et recentré"}).toBe(true);
});

test("le tableau avant sauvegarde nomme la valeur appliquée après normalisation", async ({page}) => {
  await ouvrirClimat(page);
  await page.locator(CHAMP_DECIMAL).fill("20,5");
  const tableau = page.locator("#temperature .preview-panel table");
  await expect(tableau).toBeVisible({timeout: 15000});
  await expect(tableau.locator("caption")).toHaveText("Valeur modifiée → valeur appliquée");
  await expect(tableau.locator("thead th")).toHaveText([
    "Champ et valeur précédente", "Valeur appliquée",
  ]);
  // Normalisation réelle : la virgule saisie ressort en valeur numérique.
  const ligne = tableau.locator("tbody tr", {hasText: "Jour · minimum"});
  await expect(ligne.locator("td").nth(1)).toHaveText("20.5");
});

test("les résumés de groupe sont tenus à jour à la saisie", async ({page}) => {
  await page.goto("/conf");
  await expect(page.locator("[data-mode-switch]")).toBeVisible({timeout: 15000});
  await page.locator('[data-set-mode="simple"]').click();
  const resume = page.locator('[data-config-group-summary="day"]');
  await expect(resume).toBeVisible();
  await expect(resume).toHaveText(/^\d{2}:\d{2} → \d{2}:\d{2}$/);

  const debut = page.locator("#simple-day-start");
  await debut.fill("07:30");
  await expect(resume).toHaveText(/^07:30 → \d{2}:\d{2}$/);
  await expect(page.locator('[data-config-group-summary="climate"]')).toContainText("Jour ");
});

test("les valeurs numériques et les actions autonomes portent leur classe", async ({page}) => {
  await page.goto("/conf#systeme");
  await expect(page.locator(".gpio-list dd.num").first()).toBeAttached();
  await expect(page.locator("#daily-timer-1 .summary-value.num")).toBeAttached();

  const liens = page.locator(".config-toc a.action-link");
  await expect(liens).toHaveCount(7);
  const hauteurs = await liens.evaluateAll((noeuds) => noeuds.map((noeud) => {
    const boite = noeud.getBoundingClientRect();
    return [boite.height, boite.width];
  }));
  for (const [hauteur, largeur] of hauteurs) {
    expect(hauteur).toBeGreaterThanOrEqual(44);
    expect(largeur).toBeGreaterThanOrEqual(44);
  }
});

test("l'index de recherche est présent, inerte et sans interface visible", async ({page}) => {
  await page.goto("/conf");
  const gabarit = page.locator("#config-search-index");
  await expect(gabarit).toBeAttached();
  const index = await gabarit.evaluate((node) => {
    const entrees = [...node.content.querySelectorAll("span")];
    return {
      total: entrees.length,
      climat: entrees.some((entree) => entree.dataset.section === "temperature"
        && entree.dataset.field === "target_temp_min_day"
        && entree.dataset.label === "Jour · minimum"),
      rendu: node.getClientRects().length,
    };
  });
  expect(index.total).toBeGreaterThan(100);
  expect(index.climat).toBe(true);
  expect(index.rendu).toBe(0);
  await expect(page.locator('input[type="search"]')).toHaveCount(0);
});

test.describe("sans JavaScript", () => {
  test.use({javaScriptEnabled: false});

  test("le serveur rend lui-même les résumés de groupe", async ({page}) => {
    await page.goto("/conf");
    const jour = await page.locator('[data-config-group-summary="day"]').textContent();
    const eclairage = await page.locator('[data-config-group-summary="light"]').textContent();
    const climat = await page.locator('[data-config-group-summary="climate"]').textContent();
    // Aucun « résumé disponible après chargement » : la valeur est là dès le HTML.
    expect(jour.trim()).toMatch(/^\d{2}:\d{2} → \d{2}:\d{2}$/);
    expect(eclairage.trim()).toMatch(/^Éclairage 1 : \d{2}:\d{2} → \d{2}:\d{2} · Éclairage 2 : \d{2}:\d{2} → \d{2}:\d{2}$/);
    expect(climat.trim()).toMatch(/^Jour [\d.]+–[\d.]+ °C · Nuit [\d.]+–[\d.]+ °C$/);
  });

  test("le champ décimal garde son clavier et son motif sans script", async ({page}) => {
    await page.goto("/conf");
    const champ = page.locator(CHAMP_DECIMAL);
    await expect(champ).toHaveAttribute("inputmode", "decimal");
    await expect(champ).toHaveAttribute("pattern", "-?[0-9]+([.,][0-9]+)?");
    await expect(champ).toHaveAttribute("step", "0.1");
    await expect(champ).toHaveAttribute("min", "-20");
    await expect(champ).toHaveAttribute("max", "60");
  });
});
