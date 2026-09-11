"use strict";
const {test, expect, createMother, AxeBuilder} = require("./culture_fixtures");
const {sauf} = require("./profils");

// Comptage des envois : un `POST` vers le carnet est une transaction sur son thread unique.
// La prévalidation ne doit rien écrire, et elle n'est plus rejouée à chaque enregistrement.
const countPosts = page => {
  const posts = [];
  page.on("request", request => {
    if (request.method() === "POST" && request.url().includes("/api/v1/cultures")) posts.push(request.url());
  });
  return posts;
};

test("prévalidation sans écriture, relevé ressemblant confirmé et aides périmées retirées", sauf("Parcours mutateur exercé hors service worker.", "pwa-chromium"), async ({page}, testInfo) => {
  test.setTimeout(90000);
  const posts = countPosts(page);
  const id = await createMother(page, "Mère assistance");
  await expect(page.locator("[data-culture-assistance]")).toContainText("Aucun relevé disponible");
  await page.goto(`/cultures/solutions?target=${id}&kind=reading&view=saisir#saisie`);
  const form = page.locator("#saisie form");
  await form.locator('[name="ph"]').fill("6.2");
  posts.length = 0;
  await form.getByRole("button", {name: "Vérifier avant d’enregistrer"}).click();
  await expect(form.locator(".culture-review")).toContainText("Rien n’est enregistré");
  await expect(page.locator(".solution-journal")).toHaveCount(0);
  // La vérification n'écrit rien : un seul envoi, et il vise la route de prévalidation.
  expect(posts).toEqual([expect.stringContaining("/api/v1/cultures/preview/solution")]);
  await form.locator('button[type="submit"]').filter({hasText: /^Enregistrer/}).click();
  await expect(page.locator(".solution-journal")).toHaveCount(1);
  // Saisie déjà vérifiée : l'enregistrement ne rejoue pas la prévalidation. Un relevé
  // coûte donc au plus deux envois, la recherche de ressemblance comprise.
  expect(posts).toHaveLength(2);
  expect(posts.filter(url => url.includes("/preview/"))).toHaveLength(1);
  await page.goto(`/cultures/solutions?target=${id}&kind=reading&view=saisir#saisie`);
  await form.locator('[name="ph"]').fill("6.2");
  posts.length = 0;
  await form.locator('button[type="submit"]').filter({hasText: /^Enregistrer/}).click();
  await expect(form.locator(".culture-review")).toContainText("Saisie ressemblante");
  await expect(page.locator(".solution-journal")).toHaveCount(1);
  // Premier envoi d'un relevé : la prévalidation cherche les ressemblances, sans écrire.
  expect(posts).toEqual([expect.stringContaining("/api/v1/cultures/preview/solution")]);
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
  await page.screenshot({path: testInfo.outputPath("verification-releve.png"), fullPage: true});
  await form.getByLabel("Je confirme qu’il s’agit d’un autre relevé.").check();
  await form.locator('button[type="submit"]').filter({hasText: /^Enregistrer/}).click();
  await expect(page.locator(".solution-journal")).toHaveCount(2);
  // Ressemblance confirmée : la mutation part sans seconde prévalidation.
  expect(posts).toHaveLength(2);
  expect(posts.filter(url => url.includes("/preview/"))).toHaveLength(1);
  await page.goto(`/cultures/${id}`);
  await expect(page.locator("[data-culture-assistance]")).toContainText("Dernier relevé saisi");
  expect((await new AxeBuilder({page}).analyze()).violations).toEqual([]);
  await page.evaluate(() => window.dispatchEvent(new Event("offline")));
  await expect(page.locator("[data-culture-assistance]")).toBeHidden();
});

test("une saisie modifiée pendant la prévalidation n’est pas envoyée", sauf("Parcours mutateur exercé hors service worker.", "pwa-chromium"), async ({page}, testInfo) => {
  test.setTimeout(90000);
  const id = await createMother(page, "Mère concurrence");
  await page.goto(`/cultures/solutions?target=${id}&kind=reading&view=saisir#saisie`);
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

// Une vérification est une aide, pas un verrou : le carnet occupé ne doit pas empêcher
// d'enregistrer, la mutation refaisant de toute façon toutes les validations.
test("une vérification indisponible n’empêche pas l’enregistrement", sauf("Parcours mutateur exercé hors service worker.", "pwa-chromium"), async ({page}, testInfo) => {
  test.setTimeout(90000);
  const id = await createMother(page, "Mère carnet occupé");
  await page.goto(`/cultures/solutions?target=${id}&kind=reading&view=saisir#saisie`);
  const form = page.locator("#saisie form");
  await form.locator('[name="ph"]').fill("6.4");
  await page.route("**/api/v1/cultures/preview/solution", route => route.fulfill({
    status: 503, contentType: "application/json", body: JSON.stringify({error: "Carnet occupé."})}));
  await form.locator('button[type="submit"]').filter({hasText: /^Enregistrer/}).click();
  await expect(page.locator(".solution-journal")).toHaveCount(1);
});
