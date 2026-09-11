const {defineConfig, devices} = require("@playwright/test");

const {webServerScratchDir} = require("./tests/ui/global_setup.js");
const {PROFILS, exclusions} = require("./tests/ui/profils.js");

const externalBaseUrl = process.env.PHYTO_UI_BASE_URL;
// `null` quand une cible externe est visée : aucun serveur n'est lancé, donc rien à nettoyer.
const webServerTmpdir = webServerScratchDir();

// Chaque profil écarte, avant toute fixture, les tests que `pour()`/`sauf()` lui refusent
// (`tests/ui/profils.js`). Le nom du projet est la clé de ces étiquettes.
// Citation POSIX d'un argument pour `/bin/sh`.
const citer = argument => `'${argument.replace(/'/g, "'\\''")}'`;

const profil = (name, use) => ({name, use, grepInvert: exclusions(name)});

const projects = [
  profil("desktop-chromium", {...devices["Desktop Chrome"]}),
  profil("mobile-chromium", {...devices["Pixel 5"]}),
  profil("mobile-etroit", {viewport: {width: 320, height: 568}, isMobile: true, hasTouch: true}),
  profil("mobile-paysage", {viewport: {width: 568, height: 320}, isMobile: true, hasTouch: true}),
  profil("pwa-chromium", {...devices["Pixel 5"], serviceWorkers: "allow"}),
  // Zoom 200 % (fiche R4.1). Un zoom de page à 200 % ne laisse à la mise en page que la
  // moitié de la largeur CSS, tout en rendant à deux fois la densité : c'est exactement
  // `deviceScaleFactor: 2` sur un viewport de largeur divisée par deux. Un simple
  // `deviceScaleFactor` sans réduction du viewport ne changerait que la densité, pas la
  // mise en page — donc ne testerait rien.
  //
  // La largeur CSS retenue est **320 px**, soit un zoom à 200 % d'un appareil de 640 px.
  // Elle n'est pas choisie pour un modèle de téléphone mais pour deux bornes :
  // WCAG 1.4.10 « Reflow » fixe sa référence à 320 px CSS, et `style.css:27` déclare
  // `body { min-width: 280px }`. Un viewport plus étroit — 196 px, la moitié du Pixel 5 —
  // passe **sous** ce plancher : le document mesure alors 280 px pour 197 px de fenêtre et
  // déborde par construction, sur toutes les pages à la fois. On mesurerait le plancher
  // déclaré du dépôt, pas la capacité des pages à se replier.
  profil("mobile-zoom", {...devices["Pixel 5"], viewport: {width: 320, height: 426}, deviceScaleFactor: 2}),
];
// Une étiquette `@pour-<profil>` ne vaut que si le profil existe : la liste des projets et celle
// de `tests/ui/profils.js` sont une seule vérité, vérifiée au chargement.
if (projects.map(project => project.name).join() !== PROFILS.join()) {
  throw new Error("playwright.config.js : les projets ne correspondent pas à PROFILS (tests/ui/profils.js).");
}

module.exports = defineConfig({
  testDir: "./tests/ui",
  outputDir: "/tmp/phyto-playwright-results",
  timeout: 20_000,
  forbidOnly: true,
  retries: 0,
  reporter: "line",
  globalSetup: require.resolve("./tests/ui/global_setup.js"),
  use: {
    baseURL: externalBaseUrl || "http://127.0.0.1:38123",
    locale: "fr-FR",
    serviceWorkers: "block",
    trace: "retain-on-failure",
  },
  projects,
  webServer: externalBaseUrl ? undefined : {
    // La suite UI suppose un shell POSIX : Playwright lance la commande avec `shell: true`,
    // donc à travers `/bin/sh`.
    //
    // Le `mkdir -p` est indispensable ici et pas dans `globalSetup` : Playwright démarre le
    // `webServer` avant les hooks globaux, et `tempfile.TemporaryDirectory` échoue si `TMPDIR`
    // n'existe pas. Voir `tests/ui/global_setup.js`.
    //
    // La **suppression** est portée par la même commande, et non par un `globalTeardown` : dans
    // l'ordre réel des tâches de Playwright 1.62.1, les teardowns globaux se jouent **avant**
    // l'arrêt du `webServer`, donc un teardown effacerait le répertoire d'un serveur encore
    // vivant — exactement ce que la fixture du carnet s'interdit (`tests/ui/culture_fixtures.js`)
    // —, et il ne serait même jamais atteint si le serveur échouait à démarrer, sa tâche n'ayant
    // pas été enregistrée. Le `trap`, lui, appartient au processus qu'il nettoie : il couvre la
    // fin de session, le Ctrl+C et la mort au démarrage.
    //
    // Les quatre signaux sont nécessaires : vérifié sur un projet jetable, `/bin/sh` (dash) ne
    // joue **pas** le `trap EXIT` quand il meurt d'un signal non capté. Et parce que le shell
    // capte `TERM`, POSIX lui impose de différer le trap jusqu'à la fin de la commande au premier
    // plan : la suppression suit donc la mort du serveur, jamais l'inverse.
    // L'interpréteur est cité : un chemin avec espace (`…/RPi Version/.venv/bin/python`) cassait la commande.
    command: `trap 'rm -rf "$TMPDIR"' EXIT INT TERM HUP; mkdir -p "$TMPDIR" && ${citer(process.env.PHYTO_TEST_PYTHON || "python3")} tests/ui_server.py`,
    env: {TMPDIR: webServerTmpdir},
    port: 38123,
    reuseExistingServer: false,
    timeout: 20_000,
    // Sans cette option, Playwright arrête le serveur par un `SIGKILL` au groupe de processus :
    // aucun `trap` ne s'exécuterait, et le serveur n'aurait jamais l'occasion de s'arrêter
    // proprement (fermeture de la base, finaliseur du `TemporaryDirectory`). Un serveur qui ne
    // sortirait pas dans le délai retombe sur le `SIGKILL` d'avant : c'est une chance offerte,
    // pas une attente sans fin.
    gracefulShutdown: {signal: "SIGTERM", timeout: 5_000},
  },
});
