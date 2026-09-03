(() => {
  "use strict";

  // Suivi d'un redémarrage ou d'une extinction.
  //
  // Le serveur répond 202 *avant* de lancer la commande, sinon la requête ne
  // reviendrait jamais. La contrepartie est que le code retour n'arrive plus au
  // navigateur : la détection d'échec vit ici, en observant `/health/live`.
  //
  // Un redémarrage réussi se reconnaît en deux temps — la machine doit d'abord
  // **disparaître**, puis répondre **deux fois** de suite. Exiger une seule
  // réponse annoncerait un retour alors que le processus n'a pas encore été
  // coupé.

  const POLL_MS = 1000;
  const FAILURE_AFTER_MS = 30000;
  const REDIRECT_AFTER_MS = 5000;
  const REQUIRED_ALIVE = 2;

  const section = document.querySelector("[data-system-action]");
  const state = document.getElementById("system-state");
  const failure = document.getElementById("system-failure");
  if (!section || !state) return;

  const action = section.dataset.systemAction === "poweroff" ? "poweroff" : "reboot";
  const startedAt = Date.now();
  let disappeared = false;
  let aliveStreak = 0;
  let finished = false;

  // L'URL laissée dans la barre d'adresse est un GET inerte, en dur : jamais
  // une adresse portant un paramètre d'action qu'un rechargement rejouerait.
  try {
    window.history.replaceState(null, "", "/");
  } catch (error) {
    /* navigateur restrictif : l'URL reste, la page n'en dépend pas */
  }

  const probe = async () => {
    try {
      const response = await (window.PhytoPwa?.fetchWithTimeout || fetch)("/health/live", { cache: "no-store" }, 900);
      if (!response.ok) return null;
      return await response.json();
    } catch (error) {
      return null;
    }
  };

  const finish = (message) => {
    finished = true;
    state.textContent = message;
  };

  const tick = async () => {
    if (finished) return;
    const alive = await probe();

    if (alive === null) {
      disappeared = true;
      aliveStreak = 0;
      state.textContent = action === "reboot"
        ? "Machine hors ligne — redémarrage en cours…"
        : "Machine hors ligne — extinction en cours. Attendez l’arrêt de la LED d’activité.";
      if (action === "poweroff") finish(state.textContent);
      window.setTimeout(tick, POLL_MS);
      return;
    }

    aliveStreak += 1;
    if (disappeared && action === "reboot" && aliveStreak >= REQUIRED_ALIVE) {
      const version = alive.version ? ` (version ${alive.version})` : "";
      finish(`Contrôle revenu${version} — retour au tableau de bord…`);
      window.setTimeout(() => { window.location.href = "/"; }, REDIRECT_AFTER_MS);
      return;
    }

    if (!disappeared && Date.now() - startedAt > FAILURE_AFTER_MS) {
      finish("La machine répond toujours : la commande a probablement échoué.");
      if (failure) failure.hidden = false;
      return;
    }

    if (!disappeared) state.textContent = "Commande transmise, la machine répond encore…";
    window.setTimeout(tick, POLL_MS);
  };

  window.setTimeout(tick, POLL_MS);
})();
