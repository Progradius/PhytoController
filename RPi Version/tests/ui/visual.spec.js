const {test, expect} = require("./serveurs");
const {historyFixture} = require("./fixtures");
const {pour} = require("./profils");

test("référence visuelle du tableau de bord", pour("Deux largeurs de référence suffisent.", "desktop-chromium", "mobile-etroit"), async ({page}, testInfo) => {
  await page.route("**/api/v1/cultures", route => route.fulfill({contentType: "application/json", body: JSON.stringify({occupants: [], clock_reliable: true})}));
  await page.goto("/");
  await expect(page.locator("[data-culture-preview]")).toContainText("Aucune occupation déclarée");
  await page.locator("[data-culture-updated]").evaluate(node => { node.textContent = "Carnet actualisé récemment"; });
  await page.locator(".freshness").evaluateAll((nodes) => nodes.forEach((node) => { node.textContent = "Mesure récente"; }));
  await expect(page).toHaveScreenshot("dashboard.png", {fullPage: testInfo.project.name === "desktop-chromium", animations: "disabled", maxDiffPixelRatio: 0.01});
});

test("référence visuelle de l’historique enrichi", pour("Référence détaillée sur grand écran.", "desktop-chromium"), async ({page}, testInfo) => {
  await page.route("**/api/v1/history?hours=24", (route) => route.fulfill({contentType: "application/json", body: JSON.stringify(historyFixture())}));
  await page.goto("/history");
  await page.evaluate(() => {
    document.getElementById("tendances").dataset.historyAvailable = "true";
    document.getElementById("operator-notes").hidden = false;
  });
  await page.getByRole("button", {name: "Réessayer"}).click();
  await expect(page.locator("#history-insight-grid")).toContainText("Température dans la cible");
  await page.locator("#history-updated-at").evaluate((node) => { node.textContent = "Actualisé récemment"; });
  await expect(page).toHaveScreenshot("history.png", {fullPage: true, animations: "disabled", maxDiffPixelRatio: 0.01});
});
