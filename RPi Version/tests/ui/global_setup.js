// Répertoire temporaire du serveur lancé par `webServer` dans `playwright.config.js`.
//
// `tests/ui_server.py` crée un `tempfile.TemporaryDirectory(prefix="phyto-ui-")` qu'il ne
// nettoie jamais : Playwright tue le serveur en fin de session, donc ni `atexit` ni le
// finaliseur de `TemporaryDirectory` ne s'exécutent. Chaque exécution laissait ainsi un
// `/tmp/phyto-ui-*` de plus. Comme `TemporaryDirectory` honore `TMPDIR`, il suffit de lui
// imposer un répertoire qui nous appartient et de le supprimer nous-mêmes — c'est déjà ce
// que fait la fixture du carnet (`tests/ui/culture_fixtures.js`), ici pour le serveur unique
// et partagé du `webServer`.
//
// Le chemin est **déterministe** (dérivé du PID) et non stocké : `playwright.config.js` est
// réévaluée dans chaque worker (vérifié sur @playwright/test 1.62.1), donc mémoriser un
// `mkdtempSync` dans la config créerait un répertoire par worker. Le teardown, lui, tourne
// dans le processus principal, celui-là même qui a évalué la config en premier : il retrouve
// donc le chemin en appelant simplement cette fonction.
//
// Ordre réel des tâches de Playwright 1.62.1 (`createGlobalSetupTasks`) :
// `clear output` → `plugin setup` (c'est là que le `webServer` démarre) → `globalSetup`.
// Le serveur démarre donc **avant** ce fichier : c'est `webServer.command` qui crée le
// répertoire (`mkdir -p "$TMPDIR"`), juste avant le serveur qui en a besoin. Le `mkdirSync`
// ci-dessous est idempotent ; il garantit l'invariant « le répertoire existe » si cet ordre
// interne venait à changer.

const fs = require("fs");
const os = require("os");
const path = require("path");

const SCRATCH_PREFIX = "phyto-ui-webserver-";

/**
 * Répertoire temporaire imposé au serveur du `webServer`, ou `null` quand la suite vise une
 * cible externe (`PHYTO_UI_BASE_URL`) : dans ce cas aucun serveur n'est lancé, donc rien
 * n'est créé ni supprimé.
 */
function webServerScratchDir() {
  if (process.env.PHYTO_UI_BASE_URL) {
    return null;
  }
  return path.join(os.tmpdir(), `${SCRATCH_PREFIX}${process.pid}`);
}

module.exports = async function globalSetup() {
  const scratch = webServerScratchDir();
  if (scratch) {
    fs.mkdirSync(scratch, {recursive: true});
  }
};

module.exports.webServerScratchDir = webServerScratchDir;
module.exports.SCRATCH_PREFIX = SCRATCH_PREFIX;
