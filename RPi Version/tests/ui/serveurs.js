"use strict";

// Serveurs de test isolés : **un processus neuf par test**, sur un port choisi par le noyau.
//
// L'isolation n'est pas négociable : l'espace 2 du carnet est exclusif et une occupation ouverte
// n'a pas de fin, donc deux scénarios qui partagent une base se disputent l'espace et faussent les
// comptages du journal ; les overrides, le registre d'état et le `ConfigStore` sont en outre des
// singletons de module. Un processus neuf est la seule isolation qui ne dépend d'aucune
// remise à zéro.
//
// Le port vaut `0` : c'est le noyau qui en choisit un libre, et le serveur l'annonce par la ligne
// `PHYTO_UI_READY <port>` (`tests/ui_server.py`), écrite une fois l'écoute ouverte. Deux exécutions
// de la suite, deux sessions ou deux agents ne peuvent donc plus se disputer un port, et la fixture
// n'attend plus un sondage de `/health/ready` cadencé par paliers de `expect.poll` (100, 250, 500,
// puis 1000 ms : en moyenne une demi-seconde perdue par démarrage).
//
// Le `TMPDIR` imposé est un répertoire créé ici et supprimé ici, après la sortie du serveur
// seulement : le serveur écrit sa base dedans tant qu'il vit.

const {spawn} = require("node:child_process");
const {once} = require("node:events");
const fs = require("node:fs");
const os = require("node:os");
const path = require("node:path");

const PRET = /^PHYTO_UI_READY (\d+)$/m;
// Assez pour lire une trace Python complète, pas assez pour qu'un serveur bavard épuise la mémoire.
const DIAGNOSTIC_MAX = 64 * 1024;

const python = () => process.env.PHYTO_TEST_PYTHON || "python3";

/**
 * Démarre `tests/ui_server.py` et résout `{url, arreter}` quand il accepte des requêtes.
 * `environnement` s'ajoute à celui du processus (scénario `PHYTO_UI_MEASURE_SCENARIO`, par exemple).
 */
async function demarrerServeur(environnement = {}, {delai = 45_000} = {}) {
  const scratch = fs.mkdtempSync(path.join(os.tmpdir(), "phyto-ui-fixture-"));
  const serveur = spawn(python(), ["tests/ui_server.py"], {
    env: {...process.env, ...environnement, PHYTO_UI_TEST_PORT: "0", TMPDIR: scratch},
    stdio: ["ignore", "pipe", "pipe"],
  });
  const sortie = once(serveur, "close");
  let diagnostic = "";
  const noter = morceau => { diagnostic = (diagnostic + morceau).slice(-DIAGNOSTIC_MAX); };
  const arreter = async () => {
    if (serveur.exitCode === null && serveur.signalCode === null) serveur.kill("SIGTERM");
    // Un interpréteur introuvable n'a jamais eu de PID : il n'y a pas de sortie à attendre.
    if (serveur.pid !== undefined) await sortie;
    fs.rmSync(scratch, {recursive: true, force: true});
  };
  try {
    const port = await new Promise((resolve, reject) => {
      const minuterie = setTimeout(
        () => reject(new Error(`Démarrage du serveur de test expiré (${delai} ms) :\n${diagnostic}`)), delai);
      serveur.stdout.on("data", morceau => {
        noter(morceau);
        const pret = diagnostic.match(PRET);
        if (pret) { clearTimeout(minuterie); resolve(Number(pret[1])); }
      });
      serveur.stderr.on("data", noter);
      serveur.on("error", erreur => { clearTimeout(minuterie); reject(erreur); });
      serveur.on("close", code => {
        clearTimeout(minuterie);
        reject(new Error(`Serveur de test arrêté avant d'être prêt (code ${code}) :\n${diagnostic}`));
      });
    });
    return {url: `http://127.0.0.1:${port}`, arreter};
  } catch (erreur) {
    await arreter();
    throw erreur;
  }
}

/** Corps de fixture Playwright : un serveur pour la durée du test, arrêté même en cas d'échec. */
const serveurDeTest = environnement => async ({}, use) => {
  const serveur = await demarrerServeur(environnement);
  try {
    await use(serveur.url);
  } finally {
    await serveur.arreter();
  }
};

module.exports = {demarrerServeur, serveurDeTest};
