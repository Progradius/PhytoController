"use strict";

// Dossier de résultats Playwright **propre à une exécution**.
//
// Playwright vide son `outputDir` au début de chaque exécution. Tant qu'il était fixe
// (`/tmp/phyto-playwright-results`), une seconde exécution lancée pendant la première effaçait
// les traces, captures et fichiers `testInfo.outputPath()` de celle-ci en plein vol. Les serveurs
// de test n'ayant plus de port réservé, deux exécutions simultanées sont désormais possibles : le
// dossier de résultats ne doit pas être le dernier point de collision.
//
// Le dossier est nommé d'après le PID du processus principal. `playwright.config.js` est réévalué
// dans chaque worker ; le processus principal pose donc `PHYTO_UI_RUN_ID` avant de lancer les
// workers, qui en héritent et retrouvent le même dossier.
//
// Deux conséquences traitées ici :
// * `--last-failed` lit `.last-run.json` dans l'`outputDir` du premier projet, qui change à chaque
//   exécution : sans fichier trouvé, Playwright **rejoue toute la suite** sans le signaler. Le
//   fichier de dernière exécution est donc fixé hors de ces dossiers, un par checkout
//   (`PLAYWRIGHT_LAST_RUN_OUTPUT_FILE`, lue par Playwright après le chargement de la config) ;
// * les dossiers des exécutions terminées sont supprimés par `nettoyerAnciens()`, appelé depuis le
//   `globalSetup` — donc seulement au début d'une **vraie** exécution, jamais par un simple
//   chargement de la config (`npm run test:js` en charge une). La trace d'un échec reste ainsi
//   disponible jusqu'à l'exécution suivante, comme avec le dossier fixe.

const crypto = require("node:crypto");
const fs = require("node:fs");
const os = require("node:os");
const path = require("node:path");

const PREFIXE = "phyto-playwright-results-";

const vivant = pid => {
  try {
    process.kill(pid, 0);
    return true;
  } catch (erreur) {
    return erreur.code === "EPERM"; // existe, mais appartient à un autre utilisateur
  }
};

/** Supprime les dossiers de résultats dont l'exécution n'existe plus. */
const nettoyerAnciens = (racine = os.tmpdir()) => {
  for (const nom of fs.readdirSync(racine)) {
    const correspondance = nom.match(/^phyto-playwright-results-(\d+)$/);
    if (correspondance && !vivant(Number(correspondance[1]))) {
      fs.rmSync(path.join(racine, nom), {recursive: true, force: true});
    }
  }
};

/** Fichier `--last-failed` de ce checkout : stable d'une exécution à l'autre. */
const fichierDerniereExecution = racineDepot => {
  const empreinte = crypto.createHash("sha1").update(path.resolve(racineDepot)).digest("hex").slice(0, 12);
  return path.join(os.tmpdir(), `phyto-playwright-last-run-${empreinte}.json`);
};

/** `outputDir` de l'exécution courante ; appelé par le processus principal comme par les workers. */
const dossierDeSortie = () => {
  // Processus principal : premier à évaluer la configuration, avant tout worker.
  process.env.PHYTO_UI_RUN_ID ||= String(process.pid);
  return path.join(os.tmpdir(), `${PREFIXE}${process.env.PHYTO_UI_RUN_ID}`);
};

module.exports = {dossierDeSortie, fichierDerniereExecution, nettoyerAnciens};
