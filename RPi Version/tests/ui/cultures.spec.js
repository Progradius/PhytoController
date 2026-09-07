const {test: base, expect} = require("@playwright/test");
const {spawn} = require("node:child_process");
const {once} = require("node:events");
const AxeBuilder = require("@axe-core/playwright").default;

// Chaque worker possède son carnet : une occupation en cours s'étend sans date
// de fin et peut chevaucher les autres cycles, même si leurs débuts diffèrent.
const test = base.extend({
  cultureBaseURL: [async ({}, use, workerInfo) => {
    if (process.env.PHYTO_UI_BASE_URL) return use(process.env.PHYTO_UI_BASE_URL);
    const port = 39123 + workerInfo.workerIndex;
    const url = `http://127.0.0.1:${port}`;
    const server = spawn(process.env.PHYTO_TEST_PYTHON || "python3", ["tests/ui_server.py"], {
      env: {...process.env, PHYTO_UI_TEST_PORT: String(port)}, stdio: ["ignore", "pipe", "pipe"],
    });
    let diagnostic = "";
    server.stdout.on("data", data => { diagnostic += data; });
    server.stderr.on("data", data => { diagnostic += data; });
    server.on("error", error => { diagnostic += error.message; });
    const exited = once(server, "close");
    try {
      await expect.poll(async () => {
        if (server.exitCode !== null) throw new Error(`Serveur de carnet arrêté : ${diagnostic}`);
        try { return (await fetch(`${url}/health/ready`)).status; }
        catch { return 0; }
      }, {timeout: 20000, message: "Démarrage du carnet temporaire isolé"}).toBe(200);
      await use(url);
    } finally {
      server.kill("SIGTERM");
      await exited;
    }
  }, {scope: "worker"}],
  baseURL: async ({cultureBaseURL}, use) => use(cultureBaseURL),
});

// Ces scénarios écrivent UNIQUEMENT dans la base temporaire de tests/ui_server.py.
test.beforeEach(async () => {
  test.skip(Boolean(process.env.PHYTO_UI_BASE_URL), "Aucune création de culture sur une cible externe.");
});

const dates = async form => {
  for (const name of ["origin_at", "space_at", "stage_at"]) await form.locator(`[name="${name}"]`).fill("2026-08-01");
};
const createMother = async (page, name) => {
  await page.goto("/cultures");
  const details = page.locator("details.culture-create").filter({hasText: "Ajouter un pied mère"});
  await details.locator("summary").click();
  const form = details.locator("form");
  await form.getByLabel("Nom", {exact: true}).fill(name);
  await dates(form);
  await form.getByRole("button", {name: "Ajouter un pied mère", exact: true}).click();
  await expect(page.getByRole("heading", {level: 1})).toHaveText(name);
  return page.url().split("/").pop();
};

test("lot multi-mères, carnet et correction sur téléphone et bureau", async ({page}, testInfo) => {
  test.skip(testInfo.project.name === "pwa-chromium", "Parcours PWA exercé séparément.");
  const suffix = `${testInfo.project.name}-${Date.now()}`;
  const motherA = await createMother(page, `Mère A ${suffix}`);
  const motherB = await createMother(page, `Mère B ${suffix}`);
  await page.goto("/cultures");
  const details = page.locator("details.culture-create").filter({hasText: "Créer un lot"});
  await details.locator("summary").click();
  const form = details.locator("form");
  await form.getByLabel("Nom", {exact: true}).fill(`Boutures ${suffix}`);
  await form.getByLabel("Origine du lot").selectOption("cutting");
  await form.locator('[name="mother_id"]').selectOption(motherA);
  await form.locator('[name="origin_count"]').fill("3");
  await form.getByRole("button", {name: "Ajouter une origine", exact: true}).click();
  await form.locator('[name="mother_id"]').nth(1).selectOption(motherB);
  await form.locator('[name="origin_count"]').nth(1).fill("5");
  await dates(form);
  await form.getByRole("button", {name: "Créer un lot", exact: true}).click();
  await expect(page.getByRole("heading", {level: 1})).toHaveText(`Boutures ${suffix}`);
  await expect(page.getByText("8 plantes restantes · 8 au départ")).toBeVisible();
  await expect(page.getByText("Enracinement · J", {exact: false})).toBeVisible();
  const lotUrl = page.url();
  const note = page.locator('form[data-culture-event][data-kind="note"]');
  await note.locator("..").locator("summary").click();
  await note.getByLabel("Note", {exact: true}).fill("Observation du lot\nFeuilles suivies");
  await note.getByRole("button", {name: "Note", exact: true}).click();
  await expect(page.locator(".culture-journal .culture-note")).toContainText("Observation du lot");
  const correction = page.locator('form[data-culture-correct][data-kind="note"]');
  await correction.locator("..").locator("summary").click();
  await correction.getByRole("textbox", {name: "Note", exact: true}).fill("Observation corrigée");
  await correction.getByRole("button", {name: "Enregistrer la correction"}).click();
  await expect(page.locator(".culture-journal").filter({hasText: "Observation corrigée"})).toBeVisible();
  await page.getByText("Versions précédentes (1)", {exact: true}).click();
  await expect(page.getByText("Observation du lot", {exact: false})).toBeVisible();
  const overflow = await page.evaluate(() => document.documentElement.scrollWidth - innerWidth);
  expect(overflow).toBeLessThanOrEqual(1);
  const results = await new AxeBuilder({page}).analyze();
  expect(results.violations).toEqual([]);
  if (["desktop-chromium", "mobile-etroit"].includes(testInfo.project.name)) {
    await page.screenshot({path: `/tmp/phyto-culture-${testInfo.project.name}.png`, fullPage: true});
  }
  await page.goto(`/cultures/${motherA}`);
  await expect(page.getByRole("link", {name: `Boutures ${suffix}`})).toHaveAttribute("href", new URL(lotUrl).pathname);
});

test("un échec conserve la note et la nouvelle tentative garde sa clé", async ({page}, testInfo) => {
  test.skip(testInfo.project.name !== "desktop-chromium", "Une vérification réseau suffit.");
  await createMother(page, `Mère réseau ${Date.now()}`);
  const note = page.locator('form[data-culture-event][data-kind="note"]');
  await note.locator("..").locator("summary").click();
  await note.getByLabel("Note", {exact: true}).fill("Ne pas perdre cette note");
  const bodies = [];
  await page.route("**/api/v1/cultures", async route => {
    if (route.request().method() !== "POST") return route.continue();
    bodies.push(route.request().postDataJSON());
    if (bodies.length === 1) return route.abort();
    return route.continue();
  });
  await note.getByRole("button", {name: "Note", exact: true}).click();
  await expect(note.locator("output")).toContainText("Saisie conservée");
  await expect(note.getByLabel("Note", {exact: true})).toHaveValue("Ne pas perdre cette note");
  await note.getByRole("button", {name: "Note", exact: true}).click();
  await expect(page.locator(".culture-journal .culture-note")).toHaveText("Ne pas perdre cette note");
  expect(bodies[0].request_id).toBe(bodies[1].request_id);
});

test("vue cultures sans débordement et accessible", async ({page}, testInfo) => {
  await page.goto("/cultures");
  await expect(page.getByRole("heading", {name: "Cultures", exact: true})).toBeVisible();
  expect(await page.evaluate(() => document.documentElement.scrollWidth - innerWidth)).toBeLessThanOrEqual(1);
  expect((await new AxeBuilder({page}).analyze()).violations).toEqual([]);
});

test("semis, correction d’effectif, transfert, récolte et libération", async ({page}, testInfo) => {
  test.skip(!["desktop-chromium", "mobile-chromium"].includes(testInfo.project.name), "Cycle complet sur deux formats.");
  test.setTimeout(45000);
  const name = `Semis cycle ${testInfo.project.name} ${Date.now()}`;
  await page.goto("/cultures");
  const details = page.locator("details.culture-create").filter({hasText: "Créer un lot"});
  await details.locator("summary").click();
  const form = details.locator("form");
  await form.getByLabel("Nom", {exact: true}).fill(name);
  await form.getByLabel("Origine des semences").fill("Semences A");
  await form.locator('[name="origin_count"]').fill("8");
  await dates(form);
  await form.getByRole("button", {name: "Créer un lot", exact: true}).click();
  await expect(page.getByRole("heading", {level: 1})).toHaveText(name);
  const correction = page.locator('form[data-culture-correct][data-kind="create"]');
  await correction.locator("..").locator("summary").click();
  await correction.getByLabel("Effectif initial").fill("9");
  await correction.getByRole("button", {name: "Enregistrer la correction"}).click();
  await expect(page.getByText("9 plantes restantes · 9 au départ")).toBeVisible();
  const perform = async (kind, date, fill) => {
    const action = page.locator(`form[data-culture-event][data-kind="${kind}"]`);
    await action.locator("..").locator("summary").click();
    await action.locator('[name="effective_at"]').fill(date);
    if (fill) await fill(action);
    const response = page.waitForResponse(r => r.url().endsWith("/api/v1/cultures") && r.request().method() === "POST");
    await action.locator('[type="submit"]').click();
    const received = await response;
    // Après succès, la navigation peut déjà avoir libéré le corps de réponse.
    const error = received.status() === 200 ? "" : await received.text();
    expect(received.status(), error).toBe(200);
    await page.waitForLoadState("domcontentloaded");
  };
  await perform("stage", "2026-08-03", f => f.locator('[name="stage"]').selectOption("vegetatif"));
  await expect(page.getByText("Végétatif · J", {exact: false})).toBeVisible();
  await perform("move", "2026-08-10", f => f.locator('[name="space"]').selectOption("space_2"));
  await expect(page.getByText("Espace 2 · En cours", {exact: true})).toBeVisible();
  await perform("stage", "2026-08-15", f => f.locator('[name="stage"]').selectOption("floraison"));
  await expect(page.getByText("Floraison · J", {exact: false})).toBeVisible();
  await perform("harvest", "2026-09-01", f => f.locator('[name="drying_at"]').fill("2026-09-02"));
  await expect(page.getByText("Séchage · J", {exact: false})).toBeVisible();
  await perform("finish", "2026-09-06", async f => {
    await f.locator('[name="weight_g"]').fill("102,5");
    await f.locator('[name="release"]').check();
  });
  await expect(page.getByText("Espace libéré · Archivé", {exact: true})).toBeVisible();
  await expect(page.getByText("Poids sec : 102.5 g", {exact: true}).first()).toBeVisible();
  await expect(page.getByText("Séchage · J4", {exact: true})).toBeVisible();
  await page.goto("/cultures?archives=1");
  await expect(page.getByRole("link", {name, exact: true})).toBeVisible();
});
