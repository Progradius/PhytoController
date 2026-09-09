"use strict";

const {test: base, expect} = require("@playwright/test");
const {spawn} = require("node:child_process");
const {once} = require("node:events");
const fs = require("node:fs");
const os = require("node:os");
const path = require("node:path");
const AxeBuilder = require("@axe-core/playwright").default;

// Chaque test possède son carnet : l'espace 2 est exclusif et une occupation en
// cours s'étend sans date de fin, donc deux scénarios ne peuvent pas partager une
// base sans se disputer l'espace ni fausser les comptages du journal.
const test = base.extend({
  cultureBaseURL: [async ({}, use, testInfo) => {
    // La garde vit DANS la fixture, jamais dans un `test.beforeEach` de module : le cache
    // CommonJS n'exécute ce fichier qu'une fois par worker, donc un hook de module ne
    // s'attacherait qu'au premier fichier de spec chargé et laisserait les suivants écrire
    // dans le carnet visé par PHYTO_UI_BASE_URL — un carnet de production, le cas échéant.
    // Ici la garde est traversée par chaque test qui demande la fixture, quel que soit son
    // fichier. Ces scénarios écrivent UNIQUEMENT dans la base temporaire de tests/ui_server.py.
    test.skip(Boolean(process.env.PHYTO_UI_BASE_URL), "Aucune création de culture sur une cible externe.");
    const port = 39123 + testInfo.workerIndex;
    const url = `http://127.0.0.1:${port}`;
    // `tests/ui_server.py` pose sa configuration et sa base dans un `TemporaryDirectory`,
    // dont le nettoyage est un `atexit` : le SIGTERM de fin de test ne l'exécute jamais et le
    // poste accumulait un `/tmp/phyto-ui-*` vide par scénario (≈ 160 constatés le 9 septembre
    // 2026). La fixture lui impose donc SON répertoire par `TMPDIR` — que `tempfile` de CPython
    // consulte en premier — et ne supprime que celui-là, créé par elle et par personne d'autre :
    // aucun répertoire préexistant n'est touché, même s'il porte le même préfixe.
    const scratch = fs.mkdtempSync(path.join(os.tmpdir(), "phyto-ui-fixture-"));
    const server = spawn(process.env.PHYTO_TEST_PYTHON || "python3", ["tests/ui_server.py"], {
      env: {...process.env, PHYTO_UI_TEST_PORT: String(port), TMPDIR: scratch},
      stdio: ["ignore", "pipe", "pipe"],
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
      }, {timeout: 45000, message: "Démarrage du carnet temporaire isolé"}).toBe(200);
      await use(url);
    } finally {
      server.kill("SIGTERM");
      await exited;
      // Après la sortie du serveur seulement : supprimer plus tôt laisserait le processus
      // écrire dans un répertoire disparu, et la base est encore ouverte tant qu'il vit.
      fs.rmSync(scratch, {recursive: true, force: true});
    }
  // Le démarrage du serveur (interpréteur, schéma, WAL) a son propre délai, distinct du
  // délai du test : sous contention (suite complète, autre charge sur la machine) il a
  // dépassé les 20 s du délai global et faisait échouer des scénarios sans rapport.
  }, {scope: "test", timeout: 60000}],
  baseURL: async ({cultureBaseURL}, use) => use(cultureBaseURL),
});

// Trois dates saisies à la main = une culture déjà en cours. Le mode « Je démarre une
// culture » ne demande que la date d'origine et replie les deux autres, qu'il recopie :
// la reprise est donc choisie explicitement avant de les remplir.
const dates = async form => {
  await form.getByRole("radio", {name: "Elle est déjà en cours"}).check();
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

// PNG 1×1 valide, construit en mémoire : aucune image de l'exploitation n'entre ici.
// Partagé par toutes les specs photo, pour qu'un même octet soit envoyé partout.
const PNG_1x1 = Buffer.from(
  "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg==",
  "base64");

module.exports = {test, expect, AxeBuilder, dates, createMother, PNG_1x1};
