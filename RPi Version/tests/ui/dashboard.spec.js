const {test, expect} = require("./serveurs");
const AxeBuilder = require("@axe-core/playwright").default;
const {historyFixture, testAlarmeCritique, testServeurJetable} = require("./fixtures");
const {pour, sauf} = require("./profils");

test("le tableau de bord reste compact et navigable", async ({page}) => {
  await page.goto("/");
  await expect(page.locator("#control-overview")).toBeVisible();
  await expect(page.locator("#actionneurs")).toBeVisible();
  // La maintenance est désormais sous un repli fermé (geste rare, R1.2) : l'équivalent de
  // « elle est là » est « son repli est atteignable et l'ouvre ».
  const repliMaintenance = page.locator(".dashboard-fold").filter({hasText: "Maintenance de la serre"});
  await expect(repliMaintenance.locator("summary")).toBeVisible();
  await repliMaintenance.locator("summary").click();
  await expect(page.locator("#maintenance")).toBeVisible();
  const mobile = page.viewportSize().width <= 800;
  const navigation = page.getByRole("navigation", {name: mobile ? "Navigation mobile" : "Navigation principale"});
  await expect(navigation.getByRole("link", {name: mobile ? "Cultures" : "Historique", exact: true})).toBeVisible();
  await expect(page.locator("#climate-summary")).toBeVisible();

  const climateColumns = await page.locator(".climate-actuator-grid").evaluate((grid) => (
    getComputedStyle(grid).gridTemplateColumns.split(" ").length
  ));
  const automationColumns = await page.locator(".automation-actuator-grid").evaluate((grid) => (
    getComputedStyle(grid).gridTemplateColumns.split(" ").length
  ));
  expect(climateColumns).toBe(page.viewportSize().width <= 680 ? 1 : 2);
  if (page.viewportSize().width <= 680) expect(automationColumns).toBe(1);
  // Au-delà, ce n'est pas le nombre de colonnes qui compte mais leur largeur : à quatre
  // colonnes sur 1280 px, chaque ligne compacte tombait à ~300 px et cessait d'être une
  // ligne (nom sous le chevron, transition coupée mot à mot). L'assertion porte donc sur
  // ce qui est réellement exigé.
  else expect(automationColumns).toBeLessThanOrEqual(page.viewportSize().width <= 1280 ? 2 : 4);

  // Au-dessus du point de rupture mobile, la ligne compacte reste une ligne : nom, état et
  // actions sur la même rangée. À 320 px (`mobile-etroit`, `mobile-zoom`) « Sortie cyclique 1 ·
  // ARRÊTÉ » s'enroule légitimement dans le résumé : le critère y est l'absence de débordement
  // horizontal, vérifiée plus haut, pas l'alignement sur une rangée.
  if (page.viewportSize().width > 680) {
    const surUneRangee = await page.locator(".automation-actuator-grid .actuator-card").first().evaluate((carte) => {
      const nom = carte.querySelector(".actuator-name");
      const etat = carte.querySelector(".actuator-actual");
      const actions = carte.querySelector(".equipment-actions");
      const haut = (n) => n.getBoundingClientRect().top;
      return Math.abs(haut(nom) - haut(etat)) <= 2 && Math.abs(haut(nom) - haut(actions)) <= 4;
    });
    expect(surUneRangee, "nom, état et actions doivent rester sur la même rangée").toBe(true);
  }

  const summaryBox = await page.locator("#climate-summary").boundingBox();
  const actuatorsBox = await page.locator("#actionneurs").boundingBox();
  expect(summaryBox.y).toBeLessThan(actuatorsBox.y);

  const overflow = await page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth);
  expect(overflow).toBeLessThanOrEqual(1);

  const firstCard = page.locator(".actuator-card").first();
  const actions = firstCard.locator(".equipment-actions");
  const configure = actions.getByRole("link", {name: "Configurer"});
  const cut = actions.getByRole("button", {name: "Couper"});
  await expect(configure).toBeVisible();
  await expect(cut).toBeVisible();
  // Les deux actions partagent une seule rangée, aucune ne s'étire sur toute la largeur et
  // chacune garde sa cible tactile. (L'ancien « moins de la moitié du conteneur » mesurait
  // un conteneur pleine largeur ; il est désormais dimensionné sur son contenu, à côté de
  // la ligne compacte, et la même intention s'exprime par la rangée partagée.)
  const rangee = await configure.evaluate((lien, bouton) => {
    const a = lien.getBoundingClientRect(), b = bouton.getBoundingClientRect();
    const conteneur = lien.parentElement.getBoundingClientRect();
    return {memeRangee: Math.abs(a.top - b.top) <= 2, aPleineLargeur: a.width >= conteneur.width - 1,
            hauteurMini: Math.min(a.height, b.height)};
  }, await cut.elementHandle());
  expect(rangee.memeRangee, "les deux actions doivent rester côte à côte").toBe(true);
  expect(rangee.aPleineLargeur, "« Configurer » ne doit pas occuper toute la rangée").toBe(false);
  expect(rangee.hauteurMini).toBeGreaterThanOrEqual(44);

  const row = firstCard.locator(".ui-equipment-row");
  if (!(await row.evaluate(node => node.open))) await row.locator(":scope > summary").click();
  const details = firstCard.locator(".equipment-details");
  await expect(details.getByText("Afficher", {exact: true})).toBeVisible();
  await details.locator("summary").click();
  await expect(details).toHaveAttribute("open", "");
  await expect(details.getByText("Masquer", {exact: true})).toBeVisible();
});

test("la page historique porte la vue détaillée", async ({page}) => {
  await page.goto("/history");
  await expect(page.locator("#tendances")).toBeVisible();
  await expect(page.locator("#history-empty-state")).toBeVisible();
  await expect(page.locator("#temperature-chart")).toBeAttached();
  await expect(page.locator("#history-data-body")).toBeAttached();
  await expect(page.getByRole("button", {name: "Réessayer"})).toBeVisible();
});

test("un lien de carte ouvre directement la bonne configuration", async ({page}) => {
  await page.goto("/conf#motor");
  const target = page.locator("#motor");
  await expect(target).toBeVisible();
  await expect(target).toHaveAttribute("open", "");
});

test("la saisie native des horaires conserve le schéma envoyé et la barre de sauvegarde", async ({page}) => {
  await page.goto("/conf#daily-timer-1");
  const source = page.locator('#daily-timer-1 input[name="start_time"]');
  await expect(source).toHaveAttribute("type", "time");
  await source.fill("06:05");
  await expect(source).toHaveValue("06:05");
  await expect(page.locator("#config-dirty-bar")).toBeVisible();
  const overflow = await page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth);
  expect(overflow).toBeLessThanOrEqual(1);
});

test("le thème plein jour est manuel et persistant", async ({page}) => {
  await page.goto("/");
  const mobile = page.viewportSize().width <= 800;
  if (mobile) await page.locator(".mobile-more > summary").click();
  const toggle = page.locator(mobile ? ".mobile-more-panel [data-theme-toggle]" : ".navbar [data-theme-toggle]");
  await toggle.click();
  await expect(page.locator("html")).toHaveAttribute("data-theme", "daylight");
  expect(await page.evaluate(() => localStorage.getItem("phyto.theme"))).toBe("daylight");
  await page.reload();
  await expect(page.locator("html")).toHaveAttribute("data-theme", "daylight");
});

test("les confirmations critiques ont un nom accessible", async ({page}) => {
  await page.goto("/");
  await page.getByRole("button", {name: "Couper"}).first().click();
  const dialog = page.getByRole("dialog");
  await expect(dialog).toBeVisible();
  await expect(dialog).toHaveAccessibleName(/Couper .+ \?/);
  await dialog.getByRole("button", {name: "Annuler"}).click();
});

test("la barre mobile protège une configuration modifiée", async ({page}) => {
  test.skip(page.viewportSize().width > 800, "Comportement propre à la navigation tactile.");
  await page.goto("/conf#life");
  const input = page.locator("#life input[name=stage]");
  await input.fill(`${await input.inputValue()} test`);
  const bar = page.locator("#config-dirty-bar");
  await expect(bar).toBeVisible();
  await expect(bar).toContainText("Stade de culture");
  await bar.getByRole("button", {name: "Annuler"}).click();
  await expect(bar).toBeHidden();
});

test("les pages principales n’ont pas de violation d’accessibilité détectable", async ({page}) => {
  // Quatorze analyses axe (sept pages × deux thèmes) ne tiennent pas dans le délai par
  // défaut d'un test : il est triplé plutôt que de réduire la couverture.
  test.slow();
  const pages = ["/", "/alarms", "/history", "/conf#life", "/console", "/inexistant", "/app"];
  // Les deux thèmes sont parcourus sur **toutes** les pages : la seule violation de
  // contraste de la campagne (onglet courant de la barre mobile) n'existait qu'en plein
  // jour, et une passe limitée au tableau de bord ne l'aurait jamais vue.
  for (const theme of ["dark", "daylight"]) {
    for (const path of pages) {
      await page.goto(path);
      await page.evaluate((t) => window.PhytoTheme.apply(t), theme);
      const results = await new AxeBuilder({page}).withTags(["wcag2a", "wcag2aa", "wcag22aa"]).analyze();
      expect(results.violations, `${path} (${theme}): ${results.violations.map((item) => `${item.id} (${item.nodes.length})`).join(", ")}`).toEqual([]);
    }
  }
});

test("la police de marque est réellement décodable", async ({page}) => {
  await page.goto("/");
  await expect.poll(() => page.evaluate(async () => {
    await document.fonts.ready;
    return document.fonts.check('12px "Visitor"');
  })).toBe(true);
});

// R5.1 : les petits libellés (titres de groupe d'équipements, surtitres, en-têtes de carte)
// passent en police système et ne descendent jamais sous 0,85 rem — y compris sous la
// densité mobile du tableau, qui les ramenait à 0,78 rem (écart E1).
test("les petits libellés restent en police système et à 0,85 rem au moins", async ({page}) => {
  await page.goto("/");
  const libelles = await page.evaluate(() => {
    const rem = parseFloat(getComputedStyle(document.documentElement).fontSize);
    return [...document.querySelectorAll(".actuator-group-title, .eyebrow, .card-kicker")]
      .filter((node) => node.getClientRects().length > 0)
      .map((node) => {
        const style = getComputedStyle(node);
        return {texte: node.textContent.trim(), ratio: parseFloat(style.fontSize) / rem, police: style.fontFamily};
      });
  });
  expect(libelles.some((item) => item.texte), "au moins un petit libellé doit être visible").toBe(true);
  for (const item of libelles) {
    expect(item.ratio, `« ${item.texte} »`).toBeGreaterThanOrEqual(0.85);
    expect(item.police, `« ${item.texte} »`).not.toContain("Visitor");
  }
});

test("un service partiellement indisponible ne simule pas une coupure réseau", async ({page}) => {
  await page.goto("/");
  // L'état injecté est relevé dans le même tour d'exécution : une réponse fraîche du contrôleur
  // remplace légitimement « dégradé » par « en ligne », et les boucles en émettent une toutes les
  // cinq secondes. Assertion par assertion, ce test mesurerait cette course au lieu du rendu.
  const rendu = await page.evaluate(() => {
    window.PhytoPwa.markServerDegraded("Historique momentanément indisponible (HTTP 503).");
    const banniere = document.getElementById("pwa-connection-banner");
    const couper = [...document.querySelectorAll("button")].find((bouton) => bouton.textContent.trim() === "Couper");
    return {
      visible: !banniere.hidden,
      titre: document.getElementById("pwa-connection-title").textContent,
      detail: document.getElementById("pwa-connection-detail").textContent,
      classes: document.body.className,
      couperActive: Boolean(couper) && !couper.disabled,
    };
  });
  expect(rendu.visible).toBe(true);
  expect(rendu.titre).toBe("SERVICE DÉGRADÉ");
  expect(rendu.detail).toContain("Historique momentanément indisponible");
  expect(rendu.classes).toContain("is-degraded");
  expect(rendu.classes).not.toContain("is-offline");
  expect(rendu.couperActive).toBe(true);
});

test("les commandes restent repérables avec les couleurs système forcées", pour("Contrôle ciblé du rendu Windows à contraste élevé.", "desktop-chromium"), async ({page}, testInfo) => {
  await page.emulateMedia({forcedColors: "active"});
  await page.goto("/");
  const action = page.getByRole("button", {name: "Couper"}).first();
  await expect(action).toBeVisible();
  expect(await action.evaluate((node) => getComputedStyle(node).borderStyle)).not.toBe("none");
  const results = await new AxeBuilder({page}).withTags(["wcag2a", "wcag2aa", "wcag22aa"]).disableRules(["color-contrast"]).analyze();
  expect(results.violations, results.violations.map((item) => item.id).join(", ")).toEqual([]);
});

test("les compteurs d’alarme suivent le flux vivant", async ({page}) => {
  await page.goto("/alarms");
  const alarm = {
    id: "live-critical", severity: "critical", category: "control", title: "Surchauffe",
    detail: "Température haute", consequence: "Culture exposée", advice: "Examiner",
    affects_control: true, link: "/alarms", started_ts: Date.now() / 1000,
    duration_seconds: 1, acknowledged_ts: null,
  };
  const chrome = await page.evaluate((item) => {
    window.PhytoPwa.updateAlarmChrome({summary: {active_count: 1, control_count: 1, auxiliary_count: 0, highest_severity: "critical"}, alarms: [item]});
    return {
      summary: document.querySelector(".alarm-summary strong")?.textContent,
      desktop: document.querySelector(".navbar .nav-count")?.textContent,
      mobile: document.querySelector(".mobile-navbar .nav-count")?.textContent,
      title: document.title,
    };
  }, alarm);
  expect(chrome).toMatchObject({summary: "1", desktop: "1", mobile: "1"});
  expect(chrome.title).toMatch(/^\(1\)/);
});

test("l’historique produit un bilan métier et expose les notes", sauf("Le service worker réseau-seulement ne doit pas être court-circuité par une fixture HTTP.", "pwa-chromium"), async ({page}, testInfo) => {
  await page.route("**/api/v1/history?hours=24", (route) => route.fulfill({contentType: "application/json", body: JSON.stringify(historyFixture())}));
  await page.goto("/history");
  await page.evaluate(() => {
    document.getElementById("tendances").dataset.historyAvailable = "true";
    document.getElementById("operator-notes").hidden = false;
  });
  await page.getByRole("button", {name: "Réessayer"}).click();
  await expect(page.locator("#history-insight-grid")).toContainText("Température dans la cible");
  await expect(page.locator("#history-insight-grid")).toContainText("Plus longue excursion");
  await expect(page.locator("#operator-notes")).toBeVisible();
  // R2.3 : la légende courte ne porte plus que les séries ; le repère « note opérateur » reste
  // exposé, dans le « Légende complète » de la carte Températures. L'assertion suit le balisage,
  // elle ne l'abandonne pas — la note doit rester repérable sur le graphique.
  await expect(page.locator("#temperature-legend")).not.toContainText("note opérateur");
  await page.locator(".chart-card:has(#temperature-chart) details.chart-full-legend > summary").click();
  await expect(page.locator("#temperature-legend-full")).toContainText("note opérateur");
});

test("le focus mobile n’est pas masqué par la navigation fixe", async ({page}) => {
  test.skip(page.viewportSize().width > 800, "Comportement propre à la navigation mobile.");
  await page.goto("/");
  // Le bouton visé vit sous le repli « Maintenance » : il faut l'ouvrir pour que le
  // scénario porte encore sur un élément réellement focalisable en bas de page.
  await page.locator(".dashboard-fold").filter({hasText: "Maintenance de la serre"}).locator("summary").click();
  const target = page.locator("#maintenance button").first();
  await target.focus();
  await target.evaluate((node) => node.scrollIntoView({block: "end", behavior: "instant"}));
  await expect.poll(() => page.evaluate(() => {
    const focused = document.activeElement.getBoundingClientRect();
    const navigation = document.querySelector(".mobile-navbar").getBoundingClientRect();
    return focused.bottom - navigation.top;
  })).toBeLessThanOrEqual(1);
});

test("le rafraîchissement d’une alarme conserve la saisie et le focus", async ({page}) => {
  const alarm = {
    id: "test-focus", severity: "warning", category: "control", title: "Test de supervision",
    detail: "État simulé", consequence: "Aucune", advice: "Vérifier", affects_control: true,
    link: "/alarms", started_ts: Date.now() / 1000 - 10, duration_seconds: 10, acknowledged_ts: null,
  };
  await page.route("**/api/v1/alarms/active", (route) => route.fulfill({
    contentType: "application/json",
    body: JSON.stringify({alarms: [alarm]}),
  }));
  await page.goto("/alarms");
  await page.evaluate((item) => document.dispatchEvent(new CustomEvent("phyto:alarm-feed", {detail: {feed: {alarms: [item]}, source: "network"}})), alarm);
  const alias = page.locator('[data-alarm-id="test-focus"] input[name="alias"]');
  await alias.fill("Opérateur test");
  await alias.focus();
  alarm.severity = "critical";
  alarm.duration_seconds = 15;
  await page.evaluate((item) => document.dispatchEvent(new CustomEvent("phyto:alarm-feed", {detail: {feed: {alarms: [item]}, source: "network"}})), alarm);
  await expect(alias).toHaveValue("Opérateur test");
  await expect(alias).toBeFocused();
  await expect(page.locator('[data-alarm-id="test-focus"] .alarm-severity')).toHaveText("Critique");
});

test("la coque PWA reste consultable hors ligne sans mettre les API en cache", pour("Projet avec service worker uniquement.", "pwa-chromium"), async ({page, context}, testInfo) => {
  await page.goto("/");
  await page.evaluate(() => navigator.serviceWorker.ready);
  await page.reload();
  await expect.poll(() => page.evaluate(() => Boolean(navigator.serviceWorker.controller))).toBe(true);
  const names = await page.evaluate(() => caches.keys());
  expect(names.some((name) => name.startsWith("phyto-pages-"))).toBe(true);
  expect(names).not.toContain("phyto-pages");
  const cachedUrls = await page.evaluate(async () => {
    const urls = [];
    for (const name of await caches.keys()) {
      const cache = await caches.open(name);
      urls.push(...(await cache.keys()).map((request) => request.url));
    }
    return urls;
  });
  expect(cachedUrls.every((url) => !new URL(url).pathname.startsWith("/api/"))).toBe(true);
  await context.setOffline(true);
  await page.goto("/history");
  await expect(page.getByRole("heading", {name: "Historique", exact: true})).toBeVisible();
  await expect(page.locator("#pwa-connection-banner")).toBeVisible();
  await expect(page.locator("#pwa-connection-detail")).toContainText("lecture seule");
});

// ---------------------------------------------------------------------------
// R1.1 — Alarmes : la plus importante en tête, développée, lisible sans défilement.
// ---------------------------------------------------------------------------

// Squelette d'un sous-arbre : balises et classes en ordre de document. C'est le contrat
// partagé entre la macro `alarm_summary` (rendu serveur) et `alarms.js` (flux vivant) ;
// une divergence de balisage se voit ici avant de se voir à l'écran.
const SQUELETTE = (node) => {
  const parts = [];
  const walk = (element, depth) => {
    parts.push(`${"  ".repeat(depth)}${element.tagName.toLowerCase()}${element.className ? `.${String(element.className).trim().split(/\s+/).join(".")}` : ""}${element.tagName === "DETAILS" && element.open ? "[open]" : ""}`);
    for (const child of element.children) walk(child, depth + 1);
  };
  walk(node, 0);
  return parts.join("\n");
};

testAlarmeCritique("l’alarme critique est en tête, développée et actionnable sans défilement", pour("Scénario mobile de la fiche : 390 × 844.", "mobile-chromium"), async ({page}, testInfo) => {
  await page.setViewportSize({width: 390, height: 844});
  await page.goto("/alarms");

  const premiere = page.locator(".alarm-card").first();
  await expect(premiere).toHaveClass(/severity-critical/);

  // Les trois lignes : problème, conséquence, action conseillée.
  const resume = premiere.locator(".ui-alarm-summary");
  await expect(resume.locator("h2")).toHaveText("Surchauffe simulée");
  await expect(resume.locator("p").nth(0)).toContainText("Conséquence :");
  await expect(resume.locator("p").nth(1)).toContainText("Action conseillée :");

  // L'occurrence la plus importante est servie développée par le serveur.
  await expect(premiere.locator("details").first()).toHaveAttribute("open", "");

  // Résumé court : nombre d'actives, plus haute gravité, dernière occurrence.
  const sommaire = page.locator(".alarm-summary");
  await expect(sommaire.locator("strong")).toHaveText("1");
  await expect(sommaire.locator(".alarm-summary-severity")).toContainText("Plus haute gravité : critique");
  await expect(sommaire.locator(".alarm-summary-latest time")).toBeVisible();

  // Premier écran : les trois lignes ET l'action tiennent sans défilement.
  const bas = await premiere.evaluate((carte) => {
    const lignes = [...carte.querySelectorAll(".ui-alarm-summary h2, .ui-alarm-summary p")];
    const action = carte.querySelector(".alarm-actions");
    return Math.max(...lignes.map((n) => n.getBoundingClientRect().bottom),
                    action.getBoundingClientRect().bottom);
  });
  expect(bas, `bas de l’action à ${bas} px`).toBeLessThanOrEqual(844);
});

testAlarmeCritique("le flux vivant rend exactement le balisage du serveur", async ({page, request}) => {
  // Le balisage de référence est lu **dans la réponse du serveur**, avant tout script :
  // le relever dans la page vivante aurait pu le comparer à lui-même si `alarms.js` avait
  // déjà repeint la liste au premier sondage — le test aurait alors été vide de sens.
  const htmlServeur = await (await request.get("/alarms")).text();
  expect(htmlServeur, "l’occurrence critique doit être servie par le serveur")
    .toContain('data-alarm-id="measure-critical"');
  expect(htmlServeur).toContain('<div class="ui-alarm-summary">');

  await page.goto("/alarms");
  const carte = page.locator(".alarm-card").first();
  const serveur = await carte.evaluate(SQUELETTE);
  const texteServeur = await carte.locator(".ui-alarm-summary").innerText();

  // Même occurrence, servie cette fois par le flux vivant.
  const flux = await (await page.request.get("/api/v1/alarms/active")).json();
  await page.evaluate((charge) => document.dispatchEvent(
    new CustomEvent("phyto:alarm-feed", {detail: {feed: charge, source: "network"}})), flux);

  const vivant = await carte.evaluate(SQUELETTE);
  expect(vivant).toBe(serveur);
  expect(await carte.locator(".ui-alarm-summary").innerText()).toBe(texteServeur);
});

// ---------------------------------------------------------------------------
// R1.2 — Tableau de bord : aucun défaut masqué par un repli.
// ---------------------------------------------------------------------------

testServeurJetable("une coupure active rend sa ligne ouverte", async ({page}) => {
  await page.setViewportSize({width: 390, height: 844});
  await page.goto("/");

  // Chemin réel de l'opérateur : POST + jeton CSRF + confirmation navigateur.
  await page.locator('[data-actuator="motor"] .override-cut').click();
  const dialogue = page.locator("#override-motor-dialog");
  await expect(dialogue).toBeVisible();
  const [reponse] = await Promise.all([
    page.waitForResponse((r) => r.url().includes("/actions/overrides/create")),
    dialogue.locator(".dialog-confirm-form button[type=submit]").click(),
  ]);
  // Le refus du serveur est nommé ici : sans cela une erreur de commande ressemblait à un
  // défaut d'affichage, et le test devenait intermittent au gré du sondage suivant.
  expect(reponse.status(), await reponse.text()).toBe(200);
  await expect(page.locator('[data-actuator="motor"] .ui-equipment-row')).toHaveAttribute("open", "");

  // Rendu **serveur** : la ligne arrive ouverte, avant tout script.
  const html = await (await page.request.get("/")).text();
  expect(html).toContain('data-equipment="motor" open>');
});

test("un rafraîchissement qui apporte une anomalie ouvre la ligne", sauf("Le service worker réseau-seulement ne doit pas être court-circuité par une fixture HTTP.", "pwa-chromium"), async ({page}, testInfo) => {
  let anomalie = false;
  // L'état est normalisé de bout en bout : sans boucle métier, le serveur de test ne
  // publie aucun actionneur, donc toutes les lignes arrivent déjà ouvertes (« état non
  // relu ») et une assertion sur `open` serait vraie sans rien prouver. La fixture pose
  // donc une serre entièrement nominale, puis n'y change qu'une seule chose.
  await page.route("**/api/v1/state", async (route) => {
    const reponse = await route.fetch();
    const etat = await reponse.json();
    etat.actuators = Object.fromEntries(Object.keys(etat.equipment || {}).map((cle) => [cle, {
      requested: "off", applied: "off", actual: cle === "motor" ? 0 : "off",
      tracking: "ok", reason: "Conduite normale", since_seconds: 60,
      metadata: etat.equipment[cle],
    }]));
    etat.overrides = {...(etat.overrides || {}), active_count: 0, items: []};
    if (anomalie) etat.actuators.daily_1.tracking = "mismatch";
    await route.fulfill({response: reponse, json: etat});
  });

  await page.goto("/");
  const ligne = page.locator('[data-actuator="daily_1"] .ui-equipment-row');
  await page.evaluate(() => document.querySelectorAll(".ui-equipment-row").forEach((n) => { n.open = false; }));
  await expect(ligne).not.toHaveAttribute("open", "");

  anomalie = true;
  await expect(ligne).toHaveAttribute("open", "", {timeout: 15000});
});

test("le premier écran du tableau porte état, fraîcheur, climat et alarme", pour("Scénario mobile de la fiche : 390 × 844.", "mobile-chromium"), async ({page}, testInfo) => {
  await page.setViewportSize({width: 390, height: 844});
  await page.goto("/");
  for (const selecteur of ["#overview-title", "#freshness", '[data-climate-summary="temperature"]',
                           '[data-climate-summary="humidity"]', "#alarm-count"]) {
    const bas = await page.locator(selecteur).evaluate((n) => n.getBoundingClientRect().bottom);
    expect(bas, `${selecteur} à ${bas} px`).toBeLessThanOrEqual(844);
  }
});

test("les rappels du jour du carnet ne restent jamais « en cours de lecture »", async ({page}) => {
  await page.goto("/");
  const bloc = page.locator("[data-priority-reminders]");
  await expect(bloc).toBeVisible();
  await expect(bloc).not.toContainText("en cours de lecture");
  await expect(bloc).toContainText(/Aucun rappel aujourd’hui\.|Carnet indisponible|·/);
});

// ---------------------------------------------------------------------------
// R1.3 — Navigation mobile.
// ---------------------------------------------------------------------------

test("aller-retour Tableau → Cultures → Solutions → retour à 320 px", pour("Garde-fou propre au plus petit écran.", "mobile-etroit"), async ({page}, testInfo) => {
  const barre = page.getByRole("navigation", {name: "Navigation mobile"});

  await page.goto("/");
  await expect(barre.getByRole("link", {name: "Serre", exact: true})).toHaveAttribute("aria-current", "page");

  await barre.getByRole("link", {name: "Cultures", exact: true}).click();
  await expect(page).toHaveURL(/\/cultures$/);
  await expect(barre.getByRole("link", {name: "Cultures", exact: true})).toHaveAttribute("aria-current", "page");

  await page.getByRole("link", {name: "Solutions et relevés"}).first().click();
  await expect(page).toHaveURL(/\/cultures\/solutions/);
  // Toute page `/cultures…` garde l'onglet Cultures actif.
  await expect(barre.getByRole("link", {name: "Cultures", exact: true})).toHaveAttribute("aria-current", "page");

  await barre.getByRole("link", {name: "Serre", exact: true}).click();
  await expect(page).toHaveURL(/\/$/);
  await expect(barre.getByRole("link", {name: "Serre", exact: true})).toHaveAttribute("aria-current", "page");
  // Le focus revient sur l'onglet emprunté (repère `sessionStorage` posé au clic par `pwa.js`),
  // pas en haut du document : le clavier repart de la barre, sans retraverser la page.
  await expect(barre.getByRole("link", {name: "Serre", exact: true})).toBeFocused();
  // La barre reste atteignable sans défilement horizontal au retour.
  const debordement = await page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth);
  expect(debordement).toBeLessThanOrEqual(1);
});

test("barre de saisie et barre basse laissent plus de la moitié de la hauteur utile", pour("Garde-fou mesuré à 320 × 568 et 568 × 320.", "mobile-etroit", "mobile-paysage"), async ({page}, testInfo) => {
  await page.goto("/conf#life");
  const champ = page.locator("#life input[name=stage]");
  await champ.fill(`${await champ.inputValue()} test`);
  await expect(page.locator("#config-dirty-bar")).toBeVisible();
  const mesure = await page.evaluate(() => {
    const hauteur = (selecteur) => {
      const node = document.querySelector(selecteur);
      return node ? node.getBoundingClientRect().height : 0;
    };
    return {
      barres: hauteur("#config-dirty-bar") + hauteur(".mobile-navbar"),
      utile: window.innerHeight,
    };
  });
  expect(mesure.barres, `${mesure.barres} px de barres pour ${mesure.utile} px utiles`)
    .toBeLessThanOrEqual(mesure.utile / 2);
});

// ---------------------------------------------------------------------------
// R1.4 — Console.
// ---------------------------------------------------------------------------

test("sans presse-papiers, la console sélectionne le texte et renvoie vers Exporter", async ({page}) => {
  // Contexte non sécurisé : `navigator.clipboard` n'existe pas en HTTP simple.
  await page.addInitScript(() => {
    Object.defineProperty(navigator, "clipboard", {value: undefined, configurable: true});
  });
  await page.goto("/console");
  const outils = page.locator(".console-tools");
  if (!(await outils.evaluate((node) => node.open))) await outils.locator("summary").click();
  await page.getByRole("button", {name: "Copier"}).click();
  await expect(page.locator("#console-status")).toHaveText("Copie indisponible sur cette connexion, utilisez Exporter");
  // Le repli sélectionne le journal : l'opérateur peut copier à la main.
  const selection = await page.evaluate(() => {
    const choix = window.getSelection();
    const journal = document.getElementById("console-output");
    return {
      plages: choix.rangeCount,
      surLeJournal: choix.rangeCount > 0 && journal.contains(choix.getRangeAt(0).startContainer),
    };
  });
  expect(selection).toEqual({plages: 1, surLeJournal: true});
});

test("les outils de console sont visibles sans JavaScript sur poste", pour("Contrat propre au rendu de poste.", "desktop-chromium"), async ({page}, testInfo) => {
  await page.goto("/console");
  await expect(page.locator("#console-level")).toBeVisible();
  await expect(page.locator("#console-search")).toBeVisible();
  // Le `summary` n'a plus de raison d'être au-dessus du point de rupture.
  await expect(page.locator(".console-tools > summary")).toBeHidden();
});
