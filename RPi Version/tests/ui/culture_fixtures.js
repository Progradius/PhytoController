"use strict";

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

module.exports = {test, expect, AxeBuilder, dates, createMother};
