const {test, expect} = require("@playwright/test");
const {historyFixture} = require("./fixtures");

test("référence visuelle du tableau de bord", async ({page}, testInfo) => {
  test.skip(!["desktop-chromium", "mobile-etroit"].includes(testInfo.project.name), "Deux largeurs de référence suffisent.");
  await page.goto("/");
  await page.locator(".freshness").evaluateAll((nodes) => nodes.forEach((node) => { node.textContent = "Mesure récente"; }));
  await expect(page).toHaveScreenshot("dashboard.png", {fullPage: testInfo.project.name === "desktop-chromium", animations: "disabled", maxDiffPixelRatio: 0.01});
});

test("référence visuelle de l’historique enrichi", async ({page}, testInfo) => {
  test.skip(testInfo.project.name !== "desktop-chromium", "Référence détaillée sur grand écran.");
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
