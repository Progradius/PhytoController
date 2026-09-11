"use strict";
// Dossier de résultats par exécution (`tests/ui/sortie.js`) : le nettoyage ne doit jamais toucher
// le dossier d'une exécution encore vivante — c'est précisément la collision qu'il remplace.
const {test} = require("node:test");
const assert = require("node:assert/strict");
const {spawnSync} = require("node:child_process");
const fs = require("node:fs");
const os = require("node:os");
const path = require("node:path");

const {nettoyerAnciens} = require("../ui/sortie.js");

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
