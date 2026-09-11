"use strict";

// Début d'une exécution : suppression des dossiers de résultats des exécutions terminées
// (`tests/ui/sortie.js`). Ici et nulle part ailleurs : le `globalSetup` ne tourne que dans le
// processus principal d'une vraie exécution, alors que la config est chargée par chaque worker et
// par tout outil qui la lit.

const {nettoyerAnciens} = require("./sortie");

module.exports = async function globalSetup() {
  nettoyerAnciens();
};
