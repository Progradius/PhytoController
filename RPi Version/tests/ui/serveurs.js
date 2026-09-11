"use strict";

// Serveurs de test isolés : **un processus neuf par test**, sur un port choisi par le noyau.
//
// L'isolation n'est pas négociable : l'espace 2 du carnet est exclusif et une occupation ouverte
// n'a pas de fin, donc deux scénarios qui partagent une base se disputent l'espace et faussent les
// comptages du journal ; les overrides, le registre d'état, le `ConfigStore` et le limiteur de
// prévisualisation de `/conf` sont en outre des états de processus. Un processus neuf est la seule
// isolation qui ne dépend d'aucune remise à zéro.
//
// Ce processus neuf ne coûte plus un interpréteur : chaque worker Playwright garde un **zygote**
// (`tests/ui_server.py --zygote`) qui a importé l'applicatif une fois pour toutes et duplique un
// serveur par test — `fork()` + `build_app()`, ≈ 20 ms au lieu de 0,3 s (ext4) à 8 s (`/mnt/c`,
// sous charge). Voir le protocole dans `tests/ui_server.py`.
//
// Conséquence : **tous** les tests ont leur serveur, y compris ceux qui ne font que lire. Il n'y a
// plus de `webServer` partagé, donc plus de port réservé, plus d'état commun entre workers, et deux
// exécutions de la suite peuvent tourner en même temps sur la même machine.
//
// Le `TMPDIR` de chaque serveur est un répertoire créé ici et supprimé ici, après la sortie du
// serveur seulement : le serveur écrit sa base dedans tant qu'il vit.

const {test: base, expect} = require("@playwright/test");
const {spawn} = require("node:child_process");
const {once} = require("node:events");
const fs = require("node:fs");
const os = require("node:os");
const path = require("node:path");

const PREFIXE = "PHYTO_UI_ZYGOTE ";
// Assez pour lire une trace Python complète, pas assez pour qu'un serveur bavard épuise la mémoire.
const DIAGNOSTIC_MAX = 64 * 1024;
const DELAI_DEMARRAGE = 45_000;

const python = () => process.env.PHYTO_TEST_PYTHON || "python3";

/** Pilote du zygote d'un worker. Démarré à la première demande, jamais s'il n'y en a aucune. */
class Zygote {
  constructor() {
    this.processus = null;
    this.suivant = 1;
    this.attentes = new Map(); // id de demande → fonction qui reçoit ses messages
    this.diagnostic = "";
    this.panne = null; // raison de la mort du zygote : toute demande ultérieure échoue aussitôt
  }

  noter(texte) {
    this.diagnostic = (this.diagnostic + texte).slice(-DIAGNOSTIC_MAX);
  }

  lancer() {
    if (this.processus) return;
    const processus = spawn(python(), ["tests/ui_server.py", "--zygote"], {stdio: ["pipe", "pipe", "pipe"]});
    this.processus = processus;
    this.sortie = once(processus, "close");
    let tampon = "";
    processus.stdout.setEncoding("utf8");
    processus.stdout.on("data", morceau => {
      tampon += morceau;
      let fin;
      while ((fin = tampon.indexOf("\n")) >= 0) {
        const ligne = tampon.slice(0, fin);
        tampon = tampon.slice(fin + 1);
        if (!ligne.startsWith(PREFIXE)) { this.noter(ligne + "\n"); continue; }
        const message = JSON.parse(ligne.slice(PREFIXE.length));
        this.attentes.get(message.id)?.(message);
      }
    });
    processus.stderr.on("data", morceau => this.noter(String(morceau)));
    const echec = raison => {
      const erreur = new Error(`Zygote des serveurs de test ${raison} :\n${this.diagnostic}`);
      this.panne = erreur;
      for (const recevoir of [...this.attentes.values()]) recevoir({erreur});
    };
    // Écrire dans un zygote mort lève EPIPE sur stdin : l'échec est déjà rapporté par « close ».
    processus.stdin.on("error", () => {});
    processus.on("error", erreur => echec(`introuvable (${erreur.message})`));
    processus.on("close", code => echec(`arrêté (code ${code})`));
  }

  envoyer(message) {
    if (this.panne) throw this.panne;
    this.processus.stdin.write(JSON.stringify(message) + "\n");
  }

  /** Demande un serveur neuf ; résout `{pid, port}` quand il accepte des requêtes. */
  demarrer(environnement) {
    this.lancer();
    const id = this.suivant++;
    return new Promise((resolve, reject) => {
      let pid = null;
      const fin = erreur => {
        clearTimeout(minuterie);
        this.attentes.delete(id);
        if (erreur) {
          // Un enfant déjà dupliqué est rendu au zygote, qui l'arrête : aucun serveur perdu.
          if (pid !== null) this.arreter(pid).catch(() => {});
          reject(erreur);
        }
      };
      const minuterie = setTimeout(
        () => fin(new Error(`Démarrage du serveur de test expiré (${DELAI_DEMARRAGE} ms) :\n${this.diagnostic}`)),
        DELAI_DEMARRAGE);
      this.attentes.set(id, message => {
        if (message.erreur) return fin(message.erreur);
        if ("pid" in message) { pid = message.pid; return; }
        if ("mort" in message) {
          pid = null;
          return fin(new Error(`Serveur de test arrêté avant d'être prêt (code ${message.mort}) :\n${this.diagnostic}`));
        }
        if ("port" in message) { fin(); resolve({pid, port: message.port}); }
      });
      try { this.envoyer({op: "demarrer", id, env: environnement}); } catch (erreur) { fin(erreur); }
    });
  }

  /** Arrête un serveur et attend sa sortie (SIGTERM, puis SIGKILL passé 10 s côté zygote). */
  arreter(pid) {
    const id = this.suivant++;
    return new Promise((resolve, reject) => {
      this.attentes.set(id, message => {
        if (message.erreur) { this.attentes.delete(id); return reject(message.erreur); }
        if ("code" in message) { this.attentes.delete(id); resolve(message.code); }
      });
      try { this.envoyer({op: "arreter", id, pid}); } catch (erreur) { this.attentes.delete(id); reject(erreur); }
    });
  }

  /** Fin du worker : la fin de stdin fait arrêter au zygote tout serveur restant, puis sortir. */
  async fermer() {
    if (!this.processus) return;
    this.processus.stdin.end();
    await this.sortie;
  }
}

/** Un serveur neuf pour la durée d'un test, arrêté même en cas d'échec ; `use` reçoit son URL. */
const servir = async (zygote, environnement, use) => {
  const scratch = fs.mkdtempSync(path.join(os.tmpdir(), "phyto-ui-fixture-"));
  try {
    const {pid, port} = await zygote.demarrer({...environnement, TMPDIR: scratch});
    try {
      await use(`http://127.0.0.1:${port}`);
    } finally {
      await zygote.arreter(pid);
    }
  } finally {
    fs.rmSync(scratch, {recursive: true, force: true});
  }
};

const test = base.extend({
  // Portée worker : le zygote vit autant que le worker, et meurt avec lui (fin de stdin, ou
  // PR_SET_PDEATHSIG côté serveurs si le worker est tué).
  zygote: [async ({}, use) => {
    const zygote = new Zygote();
    try {
      await use(zygote);
    } finally {
      await zygote.fermer();
    }
  }, {scope: "worker", timeout: 60_000}],

  // Chaque test a son serveur. Contre une cible externe (`PHYTO_UI_BASE_URL`), aucun serveur n'est
  // démarré : la cible est servie telle quelle, en lecture — les fixtures qui écrivent (carnet,
  // serveur jetable) s'ignorent elles-mêmes dans ce cas.
  baseURL: [async ({zygote}, use) => {
    if (process.env.PHYTO_UI_BASE_URL) return use(process.env.PHYTO_UI_BASE_URL);
    await servir(zygote, {}, use);
  }, {scope: "test", timeout: 60_000}],
});

module.exports = {test, expect, servir};
