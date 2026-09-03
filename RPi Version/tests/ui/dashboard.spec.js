const {test, expect} = require("@playwright/test");
const AxeBuilder = require("@axe-core/playwright").default;

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
    const results = await new AxeBuilder({page}).withTags(["wcag2a", "wcag2aa"]).analyze();
    expect(results.violations, `${path}: ${results.violations.map((item) => `${item.id} (${item.nodes.length})`).join(", ")}`).toEqual([]);
  }
  await page.goto("/");
  await page.evaluate(() => window.PhytoTheme.apply("daylight"));
  const daylight = await new AxeBuilder({page}).withTags(["wcag2a", "wcag2aa"]).analyze();
  expect(daylight.violations, `plein jour: ${daylight.violations.map((item) => `${item.id} (${item.nodes.length})`).join(", ")}`).toEqual([]);
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
