// Supprime le répertoire temporaire imposé au serveur du `webServer` (voir `global_setup.js`).
//
// Les gardes sont volontairement étroites : le teardown ne doit jamais pouvoir effacer un
// répertoire qu'il n'a pas nommé lui-même. Il exige que le chemin vienne de
// `webServerScratchDir()`, qu'il soit un enfant direct de `os.tmpdir()`, qu'il porte le
// préfixe `phyto-ui-webserver-` et qu'il existe. Les répertoires des autres agents et les
// `/tmp/phyto-ui-*` historiques ne portent pas ce préfixe et restent intacts.

const fs = require("fs");
const os = require("os");
const path = require("path");

const {webServerScratchDir, SCRATCH_PREFIX} = require("./global_setup.js");

module.exports = async function globalTeardown() {
  const scratch = webServerScratchDir();
  if (!scratch) {
    return;
  }
  const resolved = path.resolve(scratch);
  const base = path.basename(resolved);
  if (path.resolve(path.dirname(resolved)) !== path.resolve(os.tmpdir())) {
    return;
  }
  if (!base.startsWith(SCRATCH_PREFIX) || base === SCRATCH_PREFIX) {
    return;
  }
  if (!fs.existsSync(resolved)) {
    return;
  }
  fs.rmSync(resolved, {recursive: true, force: true});
};
