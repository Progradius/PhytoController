"use strict";
// Règle d'arrondi d'affichage (fiche R1.7) : les deux répliques JavaScript de `formatNombre`
// sont confrontées aux **mêmes** vecteurs que `model/nombre.py` (`tests/test_nombre.py`).
// Un test qui figerait une valeur d'un seul côté ne verrait pas une divergence d'arrondi :
// c'est exactement ainsi que `0,015` s'est mis à s'écrire « 0,01 » dans un tableau serveur et
// « 0,02 » dans l'infobulle du même point.
const {test} = require("node:test");
const assert = require("node:assert/strict");
const vm = require("node:vm");
const fs = require("node:fs");

const vecteurs = JSON.parse(fs.readFileSync("tests/fixtures/nombre-vecteurs.json", "utf8"));

// La fonction est définie **dans** l'IIFE de chaque script de page : elle n'est pas
// importable. Son texte est extrait puis évalué seul, ce qui éprouve la définition elle-même
// sans charger le DOM. L'unicité est vérifiée : deux définitions dans un même fichier
// seraient deux règles.
const extraire = (chemin) => {
  const source = fs.readFileSync(chemin, "utf8");
  const debut = source.indexOf("const formatNombre = ");
  assert.ok(debut >= 0, `aucune définition de formatNombre dans ${chemin}`);
  assert.equal(source.indexOf("const formatNombre = ", debut + 1), -1, `deux définitions dans ${chemin}`);
  const marqueur = "\n  };";
  const fin = source.indexOf(marqueur, debut);
  assert.ok(fin > debut, `fin de définition introuvable dans ${chemin}`);
  const contexte = {};
  vm.createContext(contexte);
  return vm.runInContext(`${source.slice(debut, fin + marqueur.length)}\nformatNombre`, contexte);
};

const valeurDuCas = (cas) => {
  if (cas.special === "nan") return NaN;
  if (cas.special === "inf") return Infinity;
  if (cas.special === "-inf") return -Infinity;
  return cas.valeur;
};
const partages = vecteurs.cas.filter((cas) => cas.portee !== "python");

test("culture_analysis.js rend exactement les vecteurs partagés", () => {
  const formatNombre = extraire("network/web/static/js/culture_analysis.js");
  assert.ok(partages.length >= 20, "les vecteurs partagés doivent couvrir les cas limites");
  for (const cas of partages) {
    assert.equal(formatNombre(valeurDuCas(cas), cas.decimales, cas.unite ?? null),
      cas.attendu, `${JSON.stringify(cas)}`);
  }
});

test("history.js rend les mêmes vecteurs que culture_analysis.js", () => {
  const formatNombre = extraire("network/web/static/js/history.js");
  // Cette réplique n'a pas de paramètre d'unité : les cas qui en portent une sont ceux de
  // l'autre réplique, et l'unité n'entre pas dans la règle d'arrondi.
  for (const cas of partages.filter((item) => !item.unite)) {
    assert.equal(formatNombre(valeurDuCas(cas), cas.decimales), cas.attendu, `${JSON.stringify(cas)}`);
  }
});
