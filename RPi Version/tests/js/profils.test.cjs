"use strict";
// Choix déclaratif des profils (`tests/ui/profils.js`). Le motif `grepInvert` d'un projet est la
// seule barrière entre un test et un profil : une erreur dans ce motif retirerait des tests en
// silence — ils ne seraient ni exécutés, ni listés, ni comptés comme ignorés. Les chaînes éprouvées
// ici ont la forme exacte que Playwright évalue : chemin de titres, titre, puis étiquettes.
const {test} = require("node:test");
const assert = require("node:assert/strict");

const {PROFILS, pour, sauf, exclusions} = require("../ui/profils.js");

// Reproduit `_grepTitleWithTags()` de Playwright : titres joints par des espaces, étiquettes à la fin.
const titre = (details = {tag: []}) => ["carnet.spec.js", "un parcours"].concat(details.tag).join(" ");
const exclu = (profil, details) => exclusions(profil).test(titre(details));

test("un test sans étiquette de profil tourne partout", () => {
  for (const profil of PROFILS) assert.equal(exclu(profil), false, profil);
});

test("pour() ne garde que les profils nommés", () => {
  const details = pour("Deux formats suffisent.", "desktop-chromium", "mobile-chromium");
  const gardes = PROFILS.filter(profil => !exclu(profil, details));
  assert.deepEqual(gardes, ["desktop-chromium", "mobile-chromium"]);
});

test("sauf() écarte les profils nommés et garde tous les autres, y compris un profil futur", () => {
  const details = sauf("Parcours hors service worker.", "pwa-chromium");
  const gardes = PROFILS.filter(profil => !exclu(profil, details));
  assert.deepEqual(gardes, PROFILS.filter(profil => profil !== "pwa-chromium"));
  // L'étiquette ne nomme que l'exclusion : aucun profil n'y est figé.
  assert.deepEqual(details.tag, ["@sauf-pwa-chromium"]);
});

test("un nom de profil n'en valide pas un autre qui le prolonge", () => {
  const motif = exclusions("mobile-chromium");
  assert.equal(motif.test(titre({tag: ["@pour-mobile-chromium-bis"]})), true);
  assert.equal(motif.test(titre({tag: ["@sauf-mobile-chromium-bis"]})), false);
});

test("un titre sur plusieurs lignes garde ses étiquettes", () => {
  const details = pour("Une cible suffit.", "desktop-chromium");
  const chaine = ["carnet.spec.js", "un parcours\nsur deux lignes"].concat(details.tag).join(" ");
  assert.equal(exclusions("desktop-chromium").test(chaine), false);
  assert.equal(exclusions("mobile-chromium").test(chaine), true);
});

test("la raison du choix reste attachée au test", () => {
  assert.deepEqual(pour("Une cible suffit.", "desktop-chromium").annotation,
    {type: "profils", description: "Une cible suffit."});
});

test("un profil inconnu ou une liste vide casse le chargement de la spec", () => {
  assert.throws(() => pour("faute de frappe", "desktop-chromiun"), /profil inconnu « desktop-chromiun »/);
  assert.throws(() => sauf("vide"), /au moins un profil/);
  assert.throws(() => exclusions("safari"), /profil inconnu/);
});

test("la liste des projets de playwright.config.js est celle de PROFILS", () => {
  const config = require("../../playwright.config.js");
  assert.deepEqual(config.projects.map(projet => projet.name), [...PROFILS]);
  for (const projet of config.projects) assert.equal(String(projet.grepInvert), String(exclusions(projet.name)));
});
