"use strict";
// Dossier de résultats par exécution (`tests/ui/sortie.js`) : le nettoyage ne doit jamais toucher
// le dossier d'une exécution encore vivante — c'est précisément la collision qu'il remplace.
const {test} = require("node:test");
const assert = require("node:assert/strict");
const {spawnSync} = require("node:child_process");
const fs = require("node:fs");
const os = require("node:os");
const path = require("node:path");

const {fichierDerniereExecution, nettoyerAnciens} = require("../ui/sortie.js");

test("seuls les dossiers d'exécutions terminées sont supprimés", () => {
  const racine = fs.mkdtempSync(path.join(os.tmpdir(), "phyto-sortie-"));
  try {
    // Un PID certainement mort : celui d'un processus qui vient de se terminer.
    const mort = spawnSync(process.execPath, ["-e", ""]).pid;
    for (const nom of [`phyto-playwright-results-${process.pid}`, `phyto-playwright-results-${mort}`,
      "phyto-playwright-results", "autre-dossier"]) {
      fs.mkdirSync(path.join(racine, nom));
    }
    nettoyerAnciens(racine);
    assert.deepEqual(fs.readdirSync(racine).sort(),
      ["autre-dossier", "phyto-playwright-results", `phyto-playwright-results-${process.pid}`].sort());
  } finally {
    fs.rmSync(racine, {recursive: true, force: true});
  }
});

test("charger la config n'efface rien : seul le globalSetup nettoie", () => {
  // `npm run test:js` charge la config (tests/js/profils.test.cjs) : il ne doit pas supprimer les
  // traces de la dernière exécution Playwright.
  const mort = spawnSync(process.execPath, ["-e", ""]).pid;
  const dossier = path.join(os.tmpdir(), `phyto-playwright-results-${mort}`);
  fs.mkdirSync(dossier, {recursive: true});
  try {
    const charge = spawnSync(process.execPath, ["-e", 'require("./playwright.config.js")'], {encoding: "utf8"});
    assert.equal(charge.status, 0, charge.stderr);
    assert.equal(fs.existsSync(dossier), true);
  } finally {
    fs.rmSync(dossier, {recursive: true, force: true});
  }
});

test("le fichier --last-failed est stable par checkout et distinct entre checkouts", () => {
  assert.equal(fichierDerniereExecution("/a/b"), fichierDerniereExecution("/a/b/"));
  assert.notEqual(fichierDerniereExecution("/a/b"), fichierDerniereExecution("/a/c"));
  assert.match(path.basename(fichierDerniereExecution("/a/b")), /^phyto-playwright-last-run-[0-9a-f]{12}\.json$/);
});
