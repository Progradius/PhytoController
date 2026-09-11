const {defineConfig, devices} = require("@playwright/test");

const {PROFILS, exclusions} = require("./tests/ui/profils.js");
const {dossierDeSortie} = require("./tests/ui/sortie.js");

// Chaque profil écarte, avant toute fixture, les tests que `pour()`/`sauf()` lui refusent
// (`tests/ui/profils.js`). Le nom du projet est la clé de ces étiquettes.
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
  // Un dossier par exécution : deux exécutions simultanées ne s'effacent pas (`tests/ui/sortie.js`).
  outputDir: dossierDeSortie(),
  timeout: 20_000,
  forbidOnly: true,
  retries: 0,
  reporter: "line",
  // Aucune `baseURL` ici ni `webServer` : chaque test reçoit son propre serveur, ou la cible
  // `PHYTO_UI_BASE_URL`, par la fixture `baseURL` de `tests/ui/serveurs.js`.
  use: {
    locale: "fr-FR",
    serviceWorkers: "block",
    trace: "retain-on-failure",
  },
  projects,
});
