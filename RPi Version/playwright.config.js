const {defineConfig, devices} = require("@playwright/test");

const {webServerScratchDir} = require("./tests/ui/global_setup.js");

const externalBaseUrl = process.env.PHYTO_UI_BASE_URL;
// `null` quand une cible externe est visée : aucun serveur n'est lancé, donc rien à nettoyer.
const webServerTmpdir = webServerScratchDir();

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
  projects: [
    {name: "desktop-chromium", use: {...devices["Desktop Chrome"]}},
    {name: "mobile-chromium", use: {...devices["Pixel 5"]}},
    {name: "mobile-etroit", use: {viewport: {width: 320, height: 568}, isMobile: true, hasTouch: true}},
    {name: "mobile-paysage", use: {viewport: {width: 568, height: 320}, isMobile: true, hasTouch: true}},
    {name: "pwa-chromium", use: {...devices["Pixel 5"], serviceWorkers: "allow"}},
  ],
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
    command: `trap 'rm -rf "$TMPDIR"' EXIT INT TERM HUP; mkdir -p "$TMPDIR" && ${process.env.PHYTO_TEST_PYTHON || "python3"} tests/ui_server.py`,
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
