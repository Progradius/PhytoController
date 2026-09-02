const {test, expect} = require("@playwright/test");

test("le tableau de bord reste compact et navigable", async ({page}, testInfo) => {
  await page.goto("/");
  await expect(page.locator("#control-overview")).toBeVisible();
  await expect(page.locator("#actionneurs")).toBeVisible();
  await expect(page.locator("#maintenance")).toBeVisible();
  await expect(page.getByRole("navigation").getByRole("link", {name: "Historique", exact: true})).toBeVisible();

  const columns = await page.locator("#actuator-grid").evaluate((grid) => (
    getComputedStyle(grid).gridTemplateColumns.split(" ").length
  ));
  expect(columns).toBe(testInfo.project.name.startsWith("mobile") ? 1 : 3);

  const overflow = await page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth);
  expect(overflow).toBeLessThanOrEqual(1);
});

test("la page historique porte la vue détaillée", async ({page}) => {
  await page.goto("/history");
  await expect(page.locator("#tendances")).toBeVisible();
  await expect(page.locator("#temperature-chart")).toBeVisible();
  await expect(page.locator("#history-data-body")).toBeAttached();
});

test("un lien de carte ouvre directement la bonne configuration", async ({page}) => {
  await page.goto("/conf#motor");
  const target = page.locator("#motor");
  await expect(target).toBeVisible();
  await expect(target).toHaveAttribute("open", "");
});
