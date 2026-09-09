"use strict";
const {test, expect, createMother, AxeBuilder} = require("./culture_fixtures");

test("prévalidation sans écriture, relevé ressemblant confirmé et aides périmées retirées", async ({page}, testInfo) => {
  const id = await createMother(page, "Mère assistance");
  await expect(page.locator("[data-culture-assistance]")).toContainText("Aucun relevé disponible");
  await page.goto(`/cultures/solutions?target=${id}&kind=reading#saisie`);
  const form = page.locator("#saisie form");
  await form.locator('[name="ph"]').fill("6.2");
  await form.getByRole("button", {name: "Vérifier avant d’enregistrer"}).click();
  await expect(form.locator(".culture-review")).toContainText("Rien n’est enregistré");
  await expect(page.locator(".solution-journal")).toHaveCount(0);
  await form.locator('button[type="submit"]').filter({hasText: /^Enregistrer/}).click();
  await expect(page.locator(".solution-journal")).toHaveCount(1);
  await page.goto(`/cultures/solutions?target=${id}&kind=reading#saisie`);
  await form.locator('[name="ph"]').fill("6.2");
  await form.locator('button[type="submit"]').filter({hasText: /^Enregistrer/}).click();
  await expect(form.locator(".culture-review")).toContainText("Saisie ressemblante");
  await expect(page.locator(".solution-journal")).toHaveCount(1);
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
  await page.screenshot({path: testInfo.outputPath("verification-releve.png"), fullPage: true});
  await form.getByLabel("Je confirme qu’il s’agit d’un autre relevé.").check();
  await form.locator('button[type="submit"]').filter({hasText: /^Enregistrer/}).click();
  await expect(page.locator(".solution-journal")).toHaveCount(2);
  await page.goto(`/cultures/${id}`);
  await expect(page.locator("[data-culture-assistance]")).toContainText("Dernier relevé saisi");
  expect((await new AxeBuilder({page}).analyze()).violations).toEqual([]);
  await page.evaluate(() => window.dispatchEvent(new Event("offline")));
  await expect(page.locator("[data-culture-assistance]")).toBeHidden();
});

test("une saisie modifiée pendant la prévalidation n’est pas envoyée", async ({page}) => {
  const id = await createMother(page, "Mère concurrence");
  await page.goto(`/cultures/solutions?target=${id}&kind=reading#saisie`);
  const form = page.locator("#saisie form");
  await form.locator('[name="ph"]').fill("6.1");
  let release;
  let received;
  const requested = new Promise(resolve => { received = resolve; });
  const pending = new Promise(resolve => { release = resolve; });
  await page.route("**/api/v1/cultures/preview/solution", async route => {
    const response = await route.fetch();
    received(); await pending; await route.fulfill({response});
  });
  await form.locator('button[type="submit"]').filter({hasText: /^Enregistrer/}).click();
  await requested;
  await form.locator('[name="ph"]').fill("6.3");
  release();
  await expect(form.locator("output")).toContainText("Saisie modifiée pendant la vérification");
  await expect(page.locator(".solution-journal")).toHaveCount(0);
  await expect(form.locator('[name="ph"]')).toHaveValue("6.3");
});
