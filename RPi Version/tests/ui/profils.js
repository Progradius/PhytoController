"use strict";

// Profils de la suite navigateur et choix, **déclaratif**, des profils d'un test.
//
// Un test ne décide plus de son profil dans son corps (`test.skip(testInfo.project.name …)`) :
// à ce stade, Playwright a déjà instancié toutes ses fixtures — navigateur, contexte et, pour le
// carnet, un serveur Python complet — pour les jeter aussitôt. Sur la suite complète, cela faisait
// 190 serveurs démarrés pour des tests ignorés. Le choix se porte désormais **à la déclaration** :
//
//   test("titre", pour("Deux formats suffisent.", "desktop-chromium", "mobile-chromium"), async …)
//   test("titre", sauf("Parcours hors service worker.", "pwa-chromium"), async …)
//
// Ces deux fonctions posent des étiquettes (`@pour-<profil>`, `@sauf-<profil>`) que le `grepInvert`
// de chaque projet (voir `exclusions()` et `playwright.config.js`) évalue **avant** toute fixture :
// un test exclu d'un profil n'y est ni planifié, ni listé, ni compté comme ignoré.
//
// La raison, qui figurait dans le message du `test.skip`, est conservée en annotation « profils » :
// elle reste lisible dans le code et dans les rapports.
//
// `sauf()` exprime une exclusion, pas une liste figée : un profil ajouté plus tard hérite des tests
// « sauf PWA », exactement comme le faisait `testInfo.project.name === "pwa-chromium"`.
//
// Les exclusions qui dépendent d'une donnée d'exécution (`page.viewportSize()`, `PHYTO_CAPTURE`)
// et la garde « cible externe » du carnet (`PHYTO_UI_BASE_URL`, dans la fixture) restent des
// `test.skip` : elles ne sont pas des choix de profil.

const PROFILS = Object.freeze([
  "desktop-chromium",
  "mobile-chromium",
  "mobile-etroit",
  "mobile-paysage",
  "pwa-chromium",
  "mobile-zoom",
]);

const verifier = (fonction, profils) => {
  if (!profils.length) throw new Error(`${fonction}() : au moins un profil attendu.`);
  for (const profil of profils) {
    // Une faute de frappe exclurait le test de **tous** les profils sans le moindre signal :
    // elle doit casser le chargement de la spec.
    if (!PROFILS.includes(profil)) throw new Error(`${fonction}() : profil inconnu « ${profil} ».`);
  }
};

const details = (raison, prefixe, profils) => ({
  tag: profils.map(profil => `@${prefixe}-${profil}`),
  annotation: {type: "profils", description: raison},
});

/** Le test ne s'exécute **que** sur ces profils. */
const pour = (raison, ...profils) => {
  verifier("pour", profils);
  return details(raison, "pour", profils);
};

/** Le test s'exécute sur tous les profils **sauf** ceux-ci. */
const sauf = (raison, ...profils) => {
  verifier("sauf", profils);
  return details(raison, "sauf", profils);
};

// Fin d'étiquette : un nom de profil n'est jamais le préfixe d'un autre (`mobile-chromium` ne doit
// pas valider `@pour-mobile-chromium-bis`, s'il existait un jour).
const FIN = "(?![\\w-])";

/**
 * Motif `grepInvert` du projet `profil` : écarte un test marqué `@sauf-<profil>`, ou marqué d'au
 * moins un `@pour-…` sans l'être de `@pour-<profil>`. Playwright l'évalue sur « chemin de titres,
 * titre, étiquettes », avant toute fixture.
 */
const exclusions = profil => {
  verifier("exclusions", [profil]);
  return new RegExp(`@sauf-${profil}${FIN}|^(?!.*@pour-${profil}${FIN}).*@pour-`);
};

module.exports = {PROFILS, pour, sauf, exclusions};
