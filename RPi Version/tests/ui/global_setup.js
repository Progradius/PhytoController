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
// `mkdtempSync` dans la config créerait un répertoire par worker. Seul le processus principal
// lance le `webServer`, et c'est son PID qui nomme le répertoire.
//
// Ordre réel des tâches de Playwright 1.62.1 (`createGlobalSetupTasks`) :
// `clear output` → `plugin setup` (c'est là que le `webServer` démarre) → `globalSetup`.
// Le serveur démarre donc **avant** ce fichier : c'est `webServer.command` qui crée le
// répertoire (`mkdir -p "$TMPDIR"`), juste avant le serveur qui en a besoin. Le `mkdirSync`
// ci-dessous est idempotent ; il garantit l'invariant « le répertoire existe » si cet ordre
// interne venait à changer.
//
// La suppression n'appartient pas à un hook global : elle est portée par le `trap` de la
// commande du `webServer`, seul point du dispositif qui se déclenche **après** la mort du
// serveur et qui survit à un serveur mort au démarrage. Voir `playwright.config.js`.

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
