const {test, expect} = require("@playwright/test");
const AxeBuilder = require("@axe-core/playwright").default;
const {historyFixture} = require("./fixtures");

test("le tableau de bord reste compact et navigable", async ({page}) => {
  await page.goto("/");
  await expect(page.locator("#control-overview")).toBeVisible();
  await expect(page.locator("#actionneurs")).toBeVisible();
  await expect(page.locator("#maintenance")).toBeVisible();
  const mobile = page.viewportSize().width <= 800;
  const navigation = page.getByRole("navigation", {name: mobile ? "Navigation mobile" : "Navigation principale"});
  await expect(navigation.getByRole("link", {name: "Historique", exact: true})).toBeVisible();
  await expect(page.locator("#climate-summary")).toBeVisible();

  const climateColumns = await page.locator(".climate-actuator-grid").evaluate((grid) => (
    getComputedStyle(grid).gridTemplateColumns.split(" ").length
  ));
  const automationColumns = await page.locator(".automation-actuator-grid").evaluate((grid) => (
    getComputedStyle(grid).gridTemplateColumns.split(" ").length
  ));
  expect(climateColumns).toBe(page.viewportSize().width <= 680 ? 1 : 2);
  if (page.viewportSize().width <= 680) expect(automationColumns).toBe(1);
  else if (page.viewportSize().width <= 1050) expect(automationColumns).toBe(2);
  else expect(automationColumns).toBeGreaterThanOrEqual(3);

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
  expect(await configure.evaluate((button, container) => (
    button.getBoundingClientRect().width < container.getBoundingClientRect().width / 2
  ), await actions.elementHandle())).toBe(true);

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

test("la saisie des horaires reste intégrée à la page sur mobile", async ({page}) => {
  await page.goto("/conf#daily-timer-1");
  const section = page.locator("#daily-timer-1");
  const source = section.locator('input[name="start_time"]');
  const control = section.locator(".compact-time-control").first();
  await expect(control).toBeVisible();
  await expect(source).toHaveAttribute("type", "hidden");

  const hours = control.getByRole("textbox", {name: /heures/});
  const minutes = control.getByRole("textbox", {name: /minutes/});
  await hours.fill("6");
  await minutes.fill("5");
  await minutes.blur();
  await expect(hours).toHaveValue("06");
  await expect(minutes).toHaveValue("05");
  await expect(source).toHaveValue("06:05");

  const overflow = await page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth);
  expect(overflow).toBeLessThanOrEqual(1);
  if (page.viewportSize().width <= 800) {
    await expect(page.locator("#config-dirty-bar")).toBeVisible();
  }
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
  for (const path of ["/", "/alarms", "/history", "/conf#life"]) {
    await page.goto(path);
    const results = await new AxeBuilder({page}).withTags(["wcag2a", "wcag2aa", "wcag22aa"]).analyze();
    expect(results.violations, `${path}: ${results.violations.map((item) => `${item.id} (${item.nodes.length})`).join(", ")}`).toEqual([]);
  }
  await page.goto("/");
  await page.evaluate(() => window.PhytoTheme.apply("daylight"));
  const daylight = await new AxeBuilder({page}).withTags(["wcag2a", "wcag2aa", "wcag22aa"]).analyze();
  expect(daylight.violations, `plein jour: ${daylight.violations.map((item) => `${item.id} (${item.nodes.length})`).join(", ")}`).toEqual([]);
});

test("la police de marque est réellement décodable", async ({page}) => {
  await page.goto("/");
  await expect.poll(() => page.evaluate(async () => {
    await document.fonts.ready;
    return document.fonts.check('12px "Visitor"');
  })).toBe(true);
});

test("un service partiellement indisponible ne simule pas une coupure réseau", async ({page}) => {
  await page.goto("/");
  await page.evaluate(() => window.PhytoPwa.markServerDegraded("Historique momentanément indisponible (HTTP 503)."));
  const banner = page.locator("#pwa-connection-banner");
  await expect(banner).toBeVisible();
  await expect(banner).toContainText("SERVICE DÉGRADÉ");
  await expect(page.locator("body")).toHaveClass(/is-degraded/);
  await expect(page.locator("body")).not.toHaveClass(/is-offline/);
  await expect(page.getByRole("button", {name: "Couper"}).first()).toBeEnabled();
});

test("les commandes restent repérables avec les couleurs système forcées", async ({page}, testInfo) => {
  test.skip(testInfo.project.name !== "desktop-chromium", "Contrôle ciblé du rendu Windows à contraste élevé.");
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

test("l’historique produit un bilan métier et expose les notes", async ({page}, testInfo) => {
  test.skip(testInfo.project.name === "pwa-chromium", "Le service worker réseau-seulement ne doit pas être court-circuité par une fixture HTTP.");
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
  await expect(page.locator("#temperature-legend")).toContainText("note opérateur");
});

test("le focus mobile n’est pas masqué par la navigation fixe", async ({page}) => {
  test.skip(page.viewportSize().width > 800, "Comportement propre à la navigation mobile.");
  await page.goto("/");
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

test("la coque PWA reste consultable hors ligne sans mettre les API en cache", async ({page, context}, testInfo) => {
  test.skip(testInfo.project.name !== "pwa-chromium", "Projet avec service worker uniquement.");
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
