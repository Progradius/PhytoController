(() => {
  "use strict";

  const DB_NAME = "phyto-pwa";
  const DB_VERSION = 1;
  const MAX_SEEN_ALARMS = 500;
  const SEVERITY_RANK = {warning: 0, error: 1, critical: 2};

  // Verdict de connexion : une seule grandeur, le silence. Un compteur d'échecs n'aurait pas de
  // dénominateur commun entre des boucles de cadences différentes, et une page où une seule boucle
  // vit n'atteindrait jamais son seuil. Le seuil dépasse les ~16 s que met le back-off à rattraper
  // un raté isolé : un paquet perdu ne peut donc plus peindre l'interface en rouge.
  const SEUIL_SILENCE_MS = 20000;
  const BATTEMENT_EN_LIGNE_MS = 5000;
  const BATTEMENT_HORS_LIGNE_MS = 2000;
  const BATTEMENT_HORS_LIGNE_LONG_MS = 15000;
  const RALENTISSEMENT_APRES_MS = 180000;
  const DELAI_SONDE_MS = 1200;
  const PEREMPTION_SONDE_MS = 5000;
  const MIN_REVEIL_MS = 5000;
  const RAFRAICHIR_AGE_MS = 30000;

  let databasePromise = null;
  let lastContactAt = null;
  let connectionState = "unknown";
  // Une dégradation appartient à sa source, jamais à l'interface entière : l'historique auxiliaire
  // peut être indisponible pendant que l'état et les alarmes répondent parfaitement. Un scalaire
  // global rendait cette panne invisible — le premier succès venu, de n'importe quelle boucle,
  // effaçait le bandeau, et une panne durable ne se voyait plus que par un éclair de cinq secondes.
  const degradations = new Map();
  // Deux horloges qui répondent à deux questions différentes : lastContactAt dit l'âge de la donnée
  // affichée, silenceDepuis dit depuis quand le contrôleur ne répond plus rien du tout (5xx compris).
  let silenceDepuis = Date.now();
  let horsLigneDepuis = null;
  let dernierEchecTransportAt = null;
  let dernierReveilAt = 0;
  let dernierRafraichissementAge = 0;
  let rechargementPropose = false;
  const cachedCultureDocument = document.querySelector('meta[name="phyto-offline-snapshot"]');
  const cultureSnapshotAt = Number(cachedCultureDocument?.content) || null;
  // Marqué par le service worker : la navigation elle-même a échoué. Une preuve, pas une suspicion —
  // c'est la seule situation où un échec de transport suffit à annoncer « hors ligne » sans délai.
  const documentEnCache = cachedCultureDocument || document.querySelector('meta[name="phyto-offline-shell"]');
  let contactedThisPage = false;
  let deferredInstallPrompt = null;
  let serviceWorkerRegistration = null;
  let lastAlarmFeed = null;
  let notificationEnabled = false;
  let alarmSeen = {};
  let alarmSeenInitialized = false;
  const baseDocumentTitle = document.title.replace(/^\(\d+\)\s+/, "");

  const pwaState = (kind, message) => {
    document.documentElement.dataset[`pwa${kind[0].toUpperCase()}${kind.slice(1)}State`] = message;
    document.querySelectorAll(`[data-pwa-${kind}-state]`).forEach(node => {
      // L'attribut de diagnostic posé sur <html> correspond lui aussi au sélecteur. Il ne s'agit
      // jamais d'une zone d'affichage : remplacer son texte détruirait le document entier.
      if (node !== document.documentElement) node.textContent = message;
    });
  };
  const storageUnavailable = () => pwaState("storage", "Lecture hors ligne indisponible : stockage refusé ou saturé.");
  let waitingWorker = null;
  let hadController = Boolean(navigator.serviceWorker?.controller);
  const showUpdate = (message, available = false) => {
    pwaState("update", message);
    const banner = document.getElementById("pwa-update-banner");
    if (banner) banner.hidden = false;
    document.querySelectorAll("[data-pwa-update]").forEach(button => { button.hidden = !available; });
  };
  // `register()` et `serviceWorker.ready` désignent la **même** inscription : les deux
  // promesses la livrent, et observer deux fois ajouterait à chaque fois un écouteur
  // `updatefound` et un écouteur `visibilitychange` de plus, avec des fermetures
  // distinctes que rien ne retire — une fuite sur une page ouverte des heures, et un
  // `inspect()` joué deux fois par événement.
  const observed = new WeakSet();
  const observeRegistration = registration => {
    serviceWorkerRegistration = registration;
    if (observed.has(registration)) return;
    observed.add(registration);
    const inspect = () => {
      if (registration.waiting && navigator.serviceWorker.controller) {
        waitingWorker = registration.waiting;
        showUpdate("Mise à jour disponible", true);
      }
      if (registration.active) registration.active.postMessage({type: "version"});
      else pwaState("worker", "Installation en cours : lecture hors ligne pas encore prête");
    };
    const watch = () => {
      inspect();
      registration.installing?.addEventListener("statechange", inspect);
    };
    registration.addEventListener("updatefound", watch);
    watch();
    document.addEventListener("visibilitychange", () => {
      if (document.visibilityState !== "visible") return;
      inspect();
      // Un retour de veille est le seul moment où une PWA restée ouverte des jours peut
      // apprendre qu'une version l'attend : sans cette demande, l'opérateur ne la verrait
      // qu'au prochain chargement complet. `update()` ne fait que **chercher** ; elle
      // n'active rien, le worker en attente restant soumis au bouton « Mettre à jour ».
      try { registration.update?.()?.catch?.(() => {}); } catch (_error) { /* Inscription disparue. */ }
    });
  };

  const announce = (message, urgent = false) => {
    // La région polie est celle de la macro partagée `network_state()`. Le repli sur
    // l'ancien identifiant n'est pas décoratif : `announce` sert aussi les pages d'erreur
    // et tout gabarit qui n'étendrait pas `base.html`.
    const node = urgent
      ? document.getElementById("global-live-alert")
      : document.querySelector("[data-network-state]") || document.getElementById("global-live-status");
    if (!node || !message) return;
    node.textContent = "";
    window.requestAnimationFrame(() => { node.textContent = message; });
  };

  const registrePollers = [];

  const createAdaptivePoller = (callback, {interval = 5000, maximum = 30000} = {}) => {
    let timer = null;
    let failures = 0;
    let running = false;
    let stopped = false;
    const clear = () => { if (timer !== null) window.clearTimeout(timer); timer = null; };
    const schedule = (delay = interval) => {
      clear();
      if (!stopped && document.visibilityState === "visible") timer = window.setTimeout(run, delay);
    };
    const run = async () => {
      if (running || stopped || document.visibilityState !== "visible") return;
      running = true;
      try {
        const success = await callback();
        failures = success === false ? failures + 1 : 0;
      } catch (_error) {
        failures += 1;
      } finally {
        running = false;
        const delay = failures ? Math.min(maximum, interval * (2 ** Math.min(failures - 1, 3))) : interval;
        schedule(delay);
      }
    };
    const resume = () => {
      if (document.visibilityState !== "visible" || stopped) { clear(); return; }
      clear(); run();
    };
    // Un réveil remet le back-off à zéro : sans cela, une boucle retombée à 30 s d'intervalle
    // resterait muette une demi-minute alors que le contrôleur est de nouveau joignable.
    const reveiller = () => { failures = 0; resume(); };
    document.addEventListener("visibilitychange", resume);
    window.addEventListener("online", resume);
    const poller = {start: resume, reveiller, stop: () => { stopped = true; clear(); }};
    registrePollers.push(poller);
    return poller;
  };

  const reveillerPollers = () => { for (const poller of registrePollers) poller.reveiller(); };

  const fetchWithTimeout = async (resource, options = {}, timeout = 6000) => {
    const controller = new AbortController();
    const externalSignal = options.signal;
    const abort = () => controller.abort(externalSignal?.reason);
    if (externalSignal?.aborted) abort();
    else externalSignal?.addEventListener("abort", abort, {once: true});
    const timer = window.setTimeout(() => controller.abort(new DOMException("Délai dépassé", "TimeoutError")), timeout);
    try {
      return await fetch(resource, {...options, signal: controller.signal});
    } finally {
      window.clearTimeout(timer);
      externalSignal?.removeEventListener("abort", abort);
    }
  };

  const isTransportError = (error) => (
    error instanceof TypeError || error?.name === "AbortError" || error?.name === "TimeoutError"
  );

  const openDatabase = () => {
    if (!databasePromise) {
      databasePromise = new Promise((resolve, reject) => {
        const request = indexedDB.open(DB_NAME, DB_VERSION);
        let settled = false;
        request.onupgradeneeded = () => {
          const db = request.result;
          if (!db.objectStoreNames.contains("snapshots")) db.createObjectStore("snapshots", {keyPath: "key"});
          if (!db.objectStoreNames.contains("preferences")) db.createObjectStore("preferences", {keyPath: "key"});
        };
        const fail = error => {
          if (settled) return;
          settled = true;
          window.clearTimeout(timer);
          reject(error);
        };
        const timer = window.setTimeout(() => fail(new Error("Stockage indisponible")), 2000);
        request.onblocked = () => fail(new Error("Stockage bloqué"));
        request.onsuccess = () => {
          if (settled) { request.result.close(); return; }
          settled = true;
          window.clearTimeout(timer);
          pwaState("storage", "Stockage local disponible");
          resolve(request.result);
        };
        request.onerror = () => fail(request.error);
      });
    }
    return databasePromise;
  };

  const readRecord = async (storeName, key) => {
    try {
      const db = await openDatabase();
      return await new Promise((resolve, reject) => {
        const request = db.transaction(storeName, "readonly").objectStore(storeName).get(key);
        request.onsuccess = () => resolve(request.result || null);
        request.onerror = () => reject(request.error);
      });
    } catch (_error) {
      storageUnavailable();
      return null;
    }
  };

  const writeRecord = async (storeName, value) => {
    try {
      const db = await openDatabase();
      await new Promise((resolve, reject) => {
        const request = db.transaction(storeName, "readwrite").objectStore(storeName).put(value);
        request.onsuccess = () => resolve();
        request.onerror = () => reject(request.error);
      });
    } catch (_error) {
      storageUnavailable();
      // Le stockage hors ligne est une amélioration : son échec ne doit jamais
      // casser l'interface vivante.
    }
  };

  const storeSnapshot = async (key, data, receivedAt = Date.now()) => {
    await writeRecord("snapshots", {key, data, receivedAt});
  };

  const loadSnapshot = (key) => readRecord("snapshots", key);
  const getPreference = async (key, fallback = null) => (await readRecord("preferences", key))?.value ?? fallback;
  const setPreference = (key, value) => writeRecord("preferences", {key, value});

  const formatElapsed = (timestamp) => {
    if (!Number.isFinite(timestamp)) return "à une date inconnue";
    const seconds = Math.max(0, Math.round((Date.now() - timestamp) / 1000));
    if (seconds < 60) return `il y a ${seconds} s`;
    if (seconds < 3600) return `il y a ${Math.round(seconds / 60)} min`;
    if (seconds < 86400) return `il y a ${(seconds / 3600).toFixed(1)} h`;
    return `il y a ${(seconds / 86400).toFixed(1)} j`;
  };

  const FILTRE_HORS_LIGNE = "Filtre indisponible hors ligne : seules les données conservées sont affichées";

  const noteDuFormulaire = (form) => {
    const next = form.nextElementSibling;
    return next?.matches?.("[data-offline-filter-note]") ? next : null;
  };

  // Le message appartient au **formulaire**, pas à ses contrôles : il est posé une seule
  // fois, dans une passe distincte, et **à côté** du formulaire. Inséré dedans, il entrait
  // dans la zone de saisie — un texte au milieu des champs — alors qu'il commente le
  // formulaire entier.
  const appliquerNotesFiltre = (disabled) => {
    document.querySelectorAll("form").forEach((form) => {
      // Un filtre serveur est un formulaire GET qui **navigue** réellement. Les formulaires
      // du carnet sont eux aussi en GET faute d'attribut `method`, mais le socle les
      // intercepte : ce sont des envois, pas des filtres, et leur coller « Filtre
      // indisponible hors ligne » serait un contresens. Le socle les marque de sa clé
      // (`data-form-key`) ; un gabarit peut aussi déclarer un filtre sans ambiguïté.
      const filtreServeur = form.hasAttribute("data-offline-filter") || (
        form.method.toLowerCase() === "get" &&
        !form.hasAttribute("data-offline-local") &&
        !form.dataset.formKey
      );
      const existante = noteDuFormulaire(form);
      if (!disabled || !filtreServeur) { existante?.remove(); return; }
      if (existante) return;
      const note = document.createElement("p");
      note.dataset.offlineFilterNote = "";
      note.className = "notice";
      note.textContent = FILTRE_HORS_LIGNE;
      form.after(note);
    });
  };

  // Le message part dans une tâche différée, jamais dans celle du verrou : sur une page
  // servie par le cache, `pwa.js` s'exécute **avant** les scripts de page, donc avant que
  // le socle du carnet n'ait marqué ses formulaires. Posé aussitôt, le message se serait
  // affiché sous chacun d'eux. Le verrou des contrôles, lui, reste immédiat — c'est lui
  // qui protège, le message ne fait qu'expliquer.
  let noteTimer = null;
  const planifierNotesFiltre = (disabled) => {
    if (noteTimer !== null) window.clearTimeout(noteTimer);
    noteTimer = window.setTimeout(() => { noteTimer = null; appliquerNotesFiltre(disabled); }, 0);
  };

  const setControlsDisabled = (disabled) => {
    planifierNotesFiltre(disabled);
    document.querySelectorAll("form input, form select, form textarea, form button, button[data-requires-online]").forEach((control) => {
      // Seuls les contrôles locaux de lecture explicitement inscrits échappent au verrou :
      // recherche dans les lignes déjà chargées, explorateur de graphique, sélection de
      // série, onglets de vue. Un envoi reste un envoi, même dans un outil local.
      const form = control.closest("form");
      // Un `<form method="dialog">` ne va nulle part : il ne fait que fermer la boîte de
      // dialogue. Désactiver son bouton « Annuler » hors ligne enfermait l'opérateur dans
      // une confirmation qu'il ne pouvait plus quitter, alors que la commande elle-même
      // reste bloquée par le formulaire d'envoi voisin.
      if (form?.method.toLowerCase() === "dialog") return;
      const local = control.hasAttribute("data-offline-local") || control.closest("[data-offline-local]") !== null;
      if (local && (!form || form.method.toLowerCase() === "get") && !control.matches('[type="submit"]')) return;
      if (disabled && !control.disabled) {
        control.disabled = true;
        control.dataset.pwaDisabled = "true";
      } else if (!disabled && control.dataset.pwaDisabled === "true") {
        control.disabled = false;
        delete control.dataset.pwaDisabled;
      }
    });
  };

  const detailDegradation = () => {
    const messages = [...degradations.values()].filter(Boolean);
    if (messages.length === 0) return "Le contrôleur répond, mais certaines données ne sont pas disponibles.";
    if (messages.length === 1) return messages[0];
    return `${messages.length} services dégradés · ${messages.join(" · ")}`;
  };

  // Empreinte de l'ensemble des dégradations : c'est elle qui décide d'une annonce, pas un message
  // isolé — sans quoi une source qui retombe en panne toutes les cinq secondes réannoncerait sans fin.
  const signatureDegradations = () => [...degradations].map(([source, message]) => `${source}:${message}`).sort().join("|");

  const updateConnectionBanner = () => {
    const banner = document.getElementById("pwa-connection-banner");
    const title = document.getElementById("pwa-connection-title");
    const detail = document.getElementById("pwa-connection-detail");
    if (!banner || !title || !detail) return;
    const unavailable = connectionState === "offline";
    const degraded = connectionState === "degraded";
    banner.hidden = !unavailable && !degraded;
    banner.classList.toggle("is-degraded", degraded);
    document.body.classList.toggle("is-offline", unavailable);
    document.body.classList.toggle("is-degraded", degraded);
    if (unavailable) {
      title.textContent = "HORS LIGNE";
      // Une fois le rechargement proposé, le détail porte cette proposition : ne pas la recouvrir.
      if (!rechargementPropose) {
        detail.textContent = lastContactAt
          ? `Données datant au mieux de ${formatElapsed(lastContactAt)} · non actualisées · lecture seule`
          : "Âge des données inconnu · données non actualisées · lecture seule";
      }
      setControlsDisabled(true);
    } else if (degraded) {
      title.textContent = "SERVICE DÉGRADÉ";
      detail.textContent = detailDegradation();
      setControlsDisabled(false);
    } else {
      setControlsDisabled(false);
    }
  };

  // La page affichée vient du cache : elle reste datée même si le contrôleur redevient joignable.
  // On propose donc un rechargement explicite au lieu de le déclencher — un rechargement automatique
  // est armé par une réponse d'API alors que c'est la navigation qui doit réussir, et les deux
  // peuvent diverger : en réseau battant, cela bouclait, et cela détruisait l'état de la page.
  const afficherRechargement = () => {
    if (rechargementPropose) return;
    const bouton = document.getElementById("pwa-connection-reload");
    const detail = document.getElementById("pwa-connection-detail");
    if (!bouton) return;
    rechargementPropose = true;
    bouton.hidden = false;
    if (detail) detail.textContent = "Contrôleur de nouveau joignable · la page affichée reste une copie datée";
    announce("Contrôleur de nouveau joignable. Rechargez la page pour revenir aux données à jour.");
  };

  // Seul endroit qui fait entrer en « hors ligne ». La sortie appartient exclusivement à
  // markServerContact : seule une réponse métier fraîche retire la bannière.
  const evaluerConnexion = () => {
    if (connectionState === "offline") {
      // Ne rafraîchir que l'âge affiché, et rarement : updateConnectionBanner balaie tout le DOM des
      // formulaires et réécrit body.class, que deux MutationObserver du carnet surveillent.
      if (!rechargementPropose && Date.now() - dernierRafraichissementAge >= RAFRAICHIR_AGE_MS) {
        dernierRafraichissementAge = Date.now();
        updateConnectionBanner();
      }
      return;
    }
    // Sur une page servie par le cache, le premier échec de transport confirme une navigation déjà
    // ratée : rien à débattre. Sur une page servie par le réseau, il faut attendre le silence.
    const jamaisJoint = documentEnCache !== null && !contactedThisPage && dernierEchecTransportAt !== null;
    if (!jamaisJoint && Date.now() - silenceDepuis <= SEUIL_SILENCE_MS) return;
    connectionState = "offline";
    // Le silence prime sur toute dégradation : plus rien ne répond, donc plus rien n'est su. Les
    // sources qui étaient en panne le signaleront de nouveau dès qu'elles reparleront.
    degradations.clear();
    horsLigneDepuis = Date.now();
    dernierRafraichissementAge = Date.now();
    updateConnectionBanner();
    announce("Connexion au contrôleur interrompue. Les données affichées ne sont plus actualisées.");
  };

  // `source` nomme la boucle qui a obtenu la réponse. Un succès ne lève que **sa** dégradation :
  // une réponse fraîche de l'état ne prouve rien sur l'historique. Sans source — une action
  // opérateur ponctuelle — le contact atteste la joignabilité et ne lève rien du tout.
  const markServerContact = async (receivedAt = Date.now(), source = null) => {
    silenceDepuis = Date.now();
    if (cachedCultureDocument) { afficherRechargement(); return; }
    const wasUnavailable = connectionState === "offline" || connectionState === "degraded";
    contactedThisPage = true;
    if (source) degradations.delete(source);
    connectionState = degradations.size ? "degraded" : "online";
    horsLigneDepuis = null;
    lastContactAt = receivedAt;
    await setPreference("lastContactAt", receivedAt);
    updateConnectionBanner();
    if (wasUnavailable && connectionState === "online") announce("Connexion au contrôleur rétablie.");
  };

  // Un signalement, pas un verdict : c'est evaluerConnexion qui tranche, sur le temps de silence.
  const signalerEchecTransport = () => {
    dernierEchecTransportAt = Date.now();
    evaluerConnexion();
  };

  // `source` est la boucle surveillée qui se dit dégradée. Une dégradation reste inscrite jusqu'à
  // ce que **cette** source réponde correctement : c'est ce qui rend une panne durable observable.
  const markServerDegraded = (detail = "", source = "global") => {
    if (cachedCultureDocument) return;
    const avant = signatureDegradations();
    contactedThisPage = true;
    // Un HTTP non-OK est une réponse fraîche du contrôleur, donc une preuve de joignabilité : il
    // rompt le silence sans rien prouver sur la fraîcheur de la donnée, que lastContactAt seul porte.
    silenceDepuis = Date.now();
    degradations.set(source, detail);
    connectionState = "degraded";
    horsLigneDepuis = null;
    updateConnectionBanner();
    if (signatureDegradations() !== avant) announce(detailDegradation());
  };

  const sonderJoignabilite = async () => {
    const emiseA = Date.now();
    let joignable = false;
    try {
      // On ne lit que le statut, jamais le corps : /health/live reste une sonde de liveness.
      const response = await fetchWithTimeout("/health/live", {cache: "no-store"}, DELAI_SONDE_MS);
      joignable = response.ok;
    } catch (_error) {
      joignable = false;
    }
    // Une sonde partie avant un gel de la page résout après la reprise avec une vérité périmée.
    if (!joignable || Date.now() - emiseA > PEREMPTION_SONDE_MS) return;
    if (Date.now() - dernierReveilAt < MIN_REVEIL_MS) return;
    dernierReveilAt = Date.now();
    // La sonde ne retire jamais la bannière ; elle réveille les boucles métier, dont la réponse
    // fraîche le fera. Un portail captif qui répond 200 à tout ne peut donc rien affirmer ici.
    if (cachedCultureDocument) afficherRechargement();
    reveillerPollers();
  };

  let battementTimer = null;
  const planifierBattement = (delai) => {
    if (battementTimer !== null) window.clearTimeout(battementTimer);
    battementTimer = window.setTimeout(battement, delai);
  };

  // Une seule boucle auto-replanifiée, jamais un setInterval : deux battements ne peuvent pas se
  // chevaucher. Inerte page masquée — un verdict n'a d'utilité que devant un œil humain, et une
  // sonde d'arrière-plan serait de toute façon étranglée par le navigateur. C'est reprendre() qui
  // rattrape la reprise, pas un sondage continu.
  async function battement() {
    battementTimer = null;
    if (document.visibilityState !== "visible") return;
    evaluerConnexion();
    if (connectionState === "offline") await sonderJoignabilite();
    const horsLigne = connectionState === "offline";
    const prolonge = horsLigne && horsLigneDepuis !== null && Date.now() - horsLigneDepuis > RALENTISSEMENT_APRES_MS;
    planifierBattement(
      horsLigne ? (prolonge ? BATTEMENT_HORS_LIGNE_LONG_MS : BATTEMENT_HORS_LIGNE_MS) : BATTEMENT_EN_LIGNE_MS,
    );
  }

  let pageAbsente = false;
  const noterAbsence = () => { if (document.visibilityState !== "visible") pageAbsente = true; };

  // Une reprise n'est pas un simple retour de focus : les boucles sont suspendues par la visibilité,
  // donc une page qui n'a jamais été masquée n'a aucun retard à rattraper, et la relancer ne ferait
  // que rejouer des requêtes. Seuls comptent une absence constatée, une restauration depuis le cache
  // de navigation, et le retour de `navigator.onLine` — trois transitions, pas un état.
  const reprendre = (event) => {
    if (document.visibilityState !== "visible") return;
    if (!pageAbsente && !event?.persisted && event?.type !== "online") return;
    pageAbsente = false;
    // Le silence ne se mesure que pendant qu'on sonde vraiment : sans cette remise à zéro, une
    // application rouverte après plusieurs minutes passerait au rouge à la seconde de sa reprise.
    silenceDepuis = Date.now();
    reveillerPollers();
    planifierBattement(0);
  };

  // La clé du snapshot nomme déjà la source : elle sert telle quelle à lever sa dégradation.
  const recordNetworkSuccess = async (key, data, receivedAt = Date.now()) => {
    await Promise.all([storeSnapshot(key, data, receivedAt), markServerContact(receivedAt, key)]);
  };

  window.PhytoPwa = {
    loadSnapshot,
    markServerContact,
    markServerDegraded,
    signalerEchecTransport,
    isTransportError,
    fetchWithTimeout,
    recordNetworkSuccess,
    storeSnapshot,
    createAdaptivePoller,
    announce,
  };

  const configureSecureNotice = () => {
    const notice = document.getElementById("pwa-security-notice");
    const link = document.getElementById("pwa-security-link");
    if (!notice || window.isSecureContext) return;
    const configured = document.querySelector('meta[name="phyto-secure-url"]')?.content;
    if (link && configured) link.href = configured;
    notice.hidden = false;
  };

  // iPhone, iPod ou iPad. L'iPad récent se déclare « MacIntel » : seul un écran tactile
  // (`maxTouchPoints`) le sépare d'un ordinateur de bureau. Une seule définition, partagée
  // par l'aide d'installation et par l'aide de refus des notifications.
  const appareilApple = (userAgent = "", platform = "", maxTouchPoints = 0) => (
    /iPhone|iPad|iPod/.test(String(userAgent)) || (platform === "MacIntel" && Number(maxTouchPoints) > 1)
  );

  // Fonction **pure**, comme `notificationDenialHelp` : l'aide d'installation affichée quand
  // aucune invite `beforeinstallprompt` n'existe (fiche R2.4). Elle ne promet rien que la
  // plateforme ne fasse : sur iOS et iPadOS, l'ouverture comme web app d'un site ajouté à
  // l'écran d'accueil est le comportement du système depuis la version 26 — le texte le
  // dit tel quel et laisse la vérification sur appareil à la qualification (R4.1).
  const installationHelp = (userAgent = "", platform = "", maxTouchPoints = 0, secure = true) => {
    if (!secure) return "Ouvrez l’adresse HTTPS du contrôleur et approuvez son certificat local avant l’installation.";
    if (appareilApple(userAgent, platform, maxTouchPoints)) {
      return "Sur iPhone ou iPad : ouvrez cette page dans Safari, puis Partager (ou menu ⋯ → Partager) → Sur l’écran d’accueil. "
        + "Depuis iOS et iPadOS 26, un site ajouté à l’écran d’accueil s’ouvre comme une web app, sans la barre de Safari.";
    }
    if (/Firefox/.test(String(userAgent))) return "Dans Firefox Android : menu → Installer. Sur ordinateur, utilisez un raccourci vers cette page.";
    return "Dans le menu du navigateur, choisissez Installer l’application ou Ajouter à l’écran d’accueil.";
  };
  window.PhytoPwa.installationHelp = installationHelp;

  const configureInstallation = () => {
    const button = document.getElementById("pwa-install-button");
    if (!button) return;
    const standalone = window.matchMedia("(display-mode: standalone)").matches || navigator.standalone === true;
    pwaState("install", standalone ? "Application installée" : "Application ouverte dans le navigateur");
    const help = installationHelp(navigator.userAgent, navigator.platform, navigator.maxTouchPoints, window.isSecureContext);
    document.querySelectorAll("[data-pwa-install-help]").forEach(node => { node.textContent = help; });
    if (standalone || !window.isSecureContext) return;
    window.addEventListener("beforeinstallprompt", (event) => {
      event.preventDefault();
      deferredInstallPrompt = event;
      button.hidden = false;
    });
    button.addEventListener("click", async () => {
      if (!deferredInstallPrompt) return;
      button.disabled = true;
      await deferredInstallPrompt.prompt();
      await deferredInstallPrompt.userChoice;
      deferredInstallPrompt = null;
      button.hidden = true;
      button.disabled = false;
    });
    window.addEventListener("appinstalled", () => {
      deferredInstallPrompt = null;
      button.hidden = true;
    });
  };

  const notificationEligible = (alarm) => (
    alarm?.acknowledged_ts === null &&
    (alarm.affects_control === true || alarm.severity === "critical")
  );

  const alarmSummaryFromFeed = (feed) => {
    if (feed?.summary) return feed.summary;
    const alarms = feed?.alarms || [];
    const rank = {warning: 0, error: 1, critical: 2};
    const highest = alarms.reduce((value, alarm) => (
      !value || (rank[alarm.severity] ?? -1) > (rank[value] ?? -1) ? alarm.severity : value
    ), null);
    return {
      active_count: alarms.length,
      unacknowledged_count: alarms.filter((alarm) => alarm.acknowledged_ts == null).length,
      control_count: alarms.filter((alarm) => alarm.affects_control === true).length,
      auxiliary_count: alarms.filter((alarm) => alarm.affects_control !== true).length,
      highest_severity: highest,
    };
  };

  const updateAlarmChrome = (feed) => {
    const summary = alarmSummaryFromFeed(feed);
    const count = Number(summary.active_count || 0);
    document.querySelectorAll('nav a[href="/alarms"]').forEach((link) => {
      let badge = link.querySelector(".nav-count");
      if (!count) { badge?.remove(); return; }
      if (!badge) {
        badge = document.createElement("span");
        badge.className = "nav-count";
        link.append(" ", badge);
      }
      badge.textContent = String(count);
      badge.setAttribute("aria-label", `${count} ${count > 1 ? "alarmes actives" : "alarme active"}`);
    });

    const pageSummary = document.querySelector(".alarm-summary");
    if (pageSummary) {
      const strong = pageSummary.querySelector("strong");
      const label = pageSummary.querySelector("span");
      const detail = pageSummary.querySelector("small");
      if (strong) strong.textContent = String(count);
      // Accord français : seul un nombre strictement supérieur à 1 prend la marque du pluriel.
      if (label) label.textContent = count > 1 ? "actives" : "active";
      if (detail) detail.textContent = `${summary.control_count || 0} contrôle · ${summary.auxiliary_count || 0} auxiliaire`;
    }

    let banner = document.getElementById("global-alarm");
    // Sur la page des alarmes, le bandeau renverrait à la page déjà ouverte : il n'est ni
    // construit ni entretenu (le résumé de la page porte déjà ces chiffres), au lieu d'être
    // construit à chaque tick puis masqué par une règle CSS.
    const surPageAlarmes = Boolean(document.getElementById("alarm-list"));
    if (!count || surPageAlarmes) banner?.remove();
    else {
      if (!banner) {
        banner = document.createElement("aside");
        banner.id = "global-alarm";
        banner.append(document.createElement("strong"), document.createElement("span"), document.createElement("a"));
        const anchor = document.getElementById("override-banner") || document.querySelector(".site-header");
        anchor?.after(banner);
      }
      banner.className = `global-alarm severity-${summary.highest_severity || "warning"}`;
      banner.querySelector("strong").textContent = `${count} ${count > 1 ? "alarmes actives" : "alarme active"}`;
      banner.querySelector("span").textContent = `${summary.control_count || 0} contrôle · ${summary.auxiliary_count || 0} auxiliaire`;
      const link = banner.querySelector("a"); link.href = "/alarms"; link.textContent = "Examiner";
    }
    document.title = count ? `(${count}) ${baseDocumentTitle}` : baseDocumentTitle;
  };
  window.PhytoPwa.updateAlarmChrome = updateAlarmChrome;

  const trimSeenAlarms = () => {
    const entries = Object.entries(alarmSeen);
    if (entries.length <= MAX_SEEN_ALARMS) return;
    entries.sort((left, right) => Number(right[1].observedAt || 0) - Number(left[1].observedAt || 0));
    alarmSeen = Object.fromEntries(entries.slice(0, MAX_SEEN_ALARMS));
  };

  const showAlarmNotification = async (alarm, escalated) => {
    if (
      !serviceWorkerRegistration ||
      !("Notification" in window) ||
      Notification.permission !== "granted"
    ) return;
    const kind = alarm.severity === "critical" ? "alarme critique" : "alarme de contrôle";
    await serviceWorkerRegistration.showNotification(`PhytoController — ${kind}`, {
      body: alarm.title || "Une alarme requiert votre attention.",
      icon: "/static/icons/pwa-192.png",
      badge: "/static/icons/pwa-192.png",
      tag: `phyto-alarm-${alarm.id}`,
      renotify: Boolean(escalated),
      data: {url: alarm.link || "/alarms"},
    });
  };

  // `receivedAt` est la date de réception de la réponse qui a produit ce jeu d'alarmes.
  // Elle n'accompagne qu'une copie relue du stockage : une page qui dit « copie datée »
  // doit pouvoir dire **de quand**, et ne l'invente jamais quand elle l'ignore.
  const processAlarmFeed = async (feed, source, receivedAt = null) => {
    const previousFeed = lastAlarmFeed;
    lastAlarmFeed = feed;
    updateAlarmChrome(feed);
    document.dispatchEvent(new CustomEvent("phyto:alarm-feed", {detail: {feed, source, receivedAt}}));
    if (source !== "network") return;

    await storeSnapshot("active-alarms", feed, Date.now());
    if (previousFeed) {
      const previous = new Map((previousFeed.alarms || []).map((alarm) => [alarm.id, alarm]));
      for (const alarm of feed.alarms || []) {
        const old = previous.get(alarm.id);
        const escalated = Boolean(old && SEVERITY_RANK[alarm.severity] > SEVERITY_RANK[old.severity]);
        if (!old || escalated) {
          announce(`${escalated ? "Alarme aggravée" : "Nouvelle alarme"} : ${alarm.title || "attention requise"}.`, alarm.severity === "critical");
        }
      }
    }
    if (
      !notificationEnabled ||
      !("Notification" in window) ||
      Notification.permission !== "granted"
    ) return;

    if (!alarmSeenInitialized) {
      for (const alarm of feed.alarms || []) {
        alarmSeen[alarm.id] = {severity: alarm.severity, observedAt: Date.now()};
      }
      alarmSeenInitialized = true;
      trimSeenAlarms();
      await Promise.all([
        setPreference("alarmSeen", alarmSeen),
        setPreference("alarmSeenInitialized", true),
      ]);
      return;
    }

    for (const alarm of feed.alarms || []) {
      const previous = alarmSeen[alarm.id];
      const escalated = Boolean(
        previous &&
        SEVERITY_RANK[alarm.severity] > SEVERITY_RANK[previous.severity]
      );
      if (notificationEligible(alarm) && (!previous || escalated)) {
        await showAlarmNotification(alarm, escalated);
      }
      alarmSeen[alarm.id] = {severity: alarm.severity, observedAt: Date.now()};
    }
    trimSeenAlarms();
    await setPreference("alarmSeen", alarmSeen);
  };

  const fetchAlarmFeed = async () => {
    try {
      const response = await fetchWithTimeout("/api/v1/alarms/active", {
        headers: {Accept: "application/json"},
        cache: "no-store",
      }, 6000);
      if (!response.ok) {
        markServerDegraded(`Alarmes momentanément indisponibles (HTTP ${response.status}).`, "alarms");
        throw new Error(`HTTP ${response.status}`);
      }
      await markServerContact(Date.now(), "alarms");
      await processAlarmFeed(await response.json(), "network");
      return true;
    } catch (error) {
      if (isTransportError(error)) signalerEchecTransport();
      const stored = await loadSnapshot("active-alarms");
      if (stored?.data) await processAlarmFeed(stored.data, "stored", stored.receivedAt);
      return false;
    }
  };

  // Fonction **pure** : elle ne lit ni `navigator`, ni le DOM, ni l'horloge. C'est ce qui
  // la rend vérifiable — un test peut lui présenter trois agents utilisateur et lire le
  // libellé rendu, ce qu'une chaîne de ternaires enfouie dans un rendu ne permettait pas.
  // Aucune promesse de Web Push : on ne dit jamais que la notification arrivera
  // application fermée. La détection iPhone/iPad est `appareilApple`, commune à l'aide
  // d'installation.
  const notificationDenialHelp = (userAgent = "", platform = "", maxTouchPoints = 0) => {
    const ua = String(userAgent);
    const settings = appareilApple(ua, platform, maxTouchPoints)
      ? "les réglages Notifications de l’application ajoutée à l’écran d’accueil sur iOS"
      : /Firefox/.test(ua) ? "les permissions de ce site dans Firefox"
      : /Chrome|Chromium|Edg/.test(ua) ? "les paramètres de ce site dans votre navigateur Chromium"
      : /Safari/.test(ua) ? "les préférences Sites web → Notifications de Safari"
      : "les permissions de ce site dans votre navigateur";
    return `Permission refusée. Réactivez les notifications depuis ${settings}.`;
  };
  // Exposée pour être éprouvée telle quelle : c'est la seule façon de prouver qu'un agent
  // utilisateur donné produit bien son libellé, et qu'aucune branche n'est inatteignable.
  window.PhytoPwa.notificationDenialHelp = notificationDenialHelp;

  const updateNotificationControls = () => {
    const enable = document.getElementById("notification-enable");
    const disable = document.getElementById("notification-disable");
    const status = document.getElementById("notification-status");
    if (!enable || !disable || !status) return;

    const supported = window.isSecureContext && "Notification" in window && "serviceWorker" in navigator;
    if (!supported) {
      status.textContent = "Notifications indisponibles : ouvrez la version HTTPS dans un navigateur compatible.";
      enable.hidden = true;
      disable.hidden = true;
      return;
    }
    if (Notification.permission === "denied") {
      status.textContent = notificationDenialHelp(navigator.userAgent, navigator.platform, navigator.maxTouchPoints);
      enable.hidden = true;
      disable.hidden = true;
      return;
    }
    if (notificationEnabled && Notification.permission === "granted") {
      status.textContent = "Notifications actives lorsque l’application est ouverte au premier plan et connectée au contrôleur. Le système peut les suspendre en arrière-plan ; ce n’est pas une alerte à distance.";
      enable.hidden = true;
      disable.hidden = false;
      return;
    }
    status.textContent = "Notifications désactivées sur ce terminal.";
    enable.hidden = false;
    disable.hidden = true;
  };

  const configureNotificationControls = () => {
    const enable = document.getElementById("notification-enable");
    const disable = document.getElementById("notification-disable");
    if (!enable || !disable) return;

    enable.addEventListener("click", async () => {
      const permission = await Notification.requestPermission();
      if (permission === "granted") {
        if (!lastAlarmFeed) await fetchAlarmFeed();
        for (const alarm of lastAlarmFeed?.alarms || []) {
          alarmSeen[alarm.id] = {severity: alarm.severity, observedAt: Date.now()};
        }
        alarmSeenInitialized = true;
        notificationEnabled = true;
        trimSeenAlarms();
        await Promise.all([
          setPreference("notificationsEnabled", true),
          setPreference("alarmSeen", alarmSeen),
          setPreference("alarmSeenInitialized", true),
        ]);
      }
      updateNotificationControls();
    });

    disable.addEventListener("click", async () => {
      notificationEnabled = false;
      await setPreference("notificationsEnabled", false);
      updateNotificationControls();
    });
  };

  // Les préférences sont un **confort**, jamais une condition : elles ne décident que de
  // l'âge affiché avant le premier contact et de l'état des notifications. Un stockage
  // lent ou refusé les fait attendre jusqu'à 2 s ; les tenir devant le poller d'alarmes et
  // les contrôles retenait donc l'interface connectée pour rien. Elles sont lues en
  // parallèle et rattrapent l'état déjà établi au lieu de l'écraser.
  const chargerPreferences = async () => {
    const [contact, enabled, seen, initialized] = await Promise.all([
      getPreference("lastContactAt", null),
      getPreference("notificationsEnabled", false),
      getPreference("alarmSeen", {}),
      getPreference("alarmSeenInitialized", false),
    ]);
    // Une réponse fraîche arrivée pendant la lecture fait autorité : la préférence n'est
    // qu'un repli tant qu'aucun contact n'a eu lieu sur cette page.
    if (lastContactAt === null) lastContactAt = contact;
    if (!alarmSeenInitialized) { alarmSeen = seen; alarmSeenInitialized = initialized; }
    // Activé en dernier : tant que ce drapeau est faux, `processAlarmFeed` n'ouvre aucune
    // notification et ne touche pas au registre des alarmes déjà vues.
    notificationEnabled = enabled;
    updateNotificationControls();
    updateConnectionBanner();
  };

  const initialize = () => {
    configureSecureNotice();
    configureInstallation();
    // Aucun `await` devant ce qui suit : les contrôles de notification, le poller et la
    // bannière n'ont besoin ni du stockage ni du service worker. La lecture des
    // préférences part ici et rattrapera l'interface quand elle aboutira.
    chargerPreferences().catch(() => { /* Le stockage est une amélioration, pas un prérequis. */ });

    document.getElementById("pwa-connection-reload")?.addEventListener("click", () => {
      window.location.reload();
    });

    // 1. Contrôles de notification : ils n'ont besoin que de la permission du navigateur.
    configureNotificationControls();
    updateNotificationControls();
    // 2. Boucle d'alarmes : c'est elle qui fait vivre l'interface connectée.
    createAdaptivePoller(fetchAlarmFeed).start();

    // 3. Reprise de l'application : c'est ce réveil, et non un sondage d'arrière-plan, qui rend la
    // main en une seconde quand l'opérateur rouvre la PWA. « online » ne suffit pas : sur mobile,
    // navigator.onLine ne passe le plus souvent jamais à false. « controllerchange » est
    // délibérément absent : un changement de service worker dit qu'une version a pris la main,
    // jamais que le contrôleur est de nouveau joignable — ce n'est pas une reprise.
    window.addEventListener("pagehide", () => { pageAbsente = true; });
    document.addEventListener("visibilitychange", noterAbsence);
    window.addEventListener("pageshow", reprendre);
    window.addEventListener("focus", reprendre);
    window.addEventListener("online", reprendre);
    document.addEventListener("visibilitychange", reprendre);
    // 4. Bannière de connexion : premier battement.
    planifierBattement(0);

    // 5. Enfin le service worker. L'enregistrement ne conditionne rien et n'est donc jamais attendu ici :
    // `serviceWorker.ready` peut ne jamais se régler (worker bloqué, installation sans fin), et il
    // emportait alors la surveillance de connexion et la boucle d'alarmes, qui le suivaient.
    // Son seul consommateur, showAlarmNotification, sait déjà faire avec une inscription absente.
    if (window.isSecureContext && "serviceWorker" in navigator) {
      pwaState("worker", "Installation en cours : lecture hors ligne pas encore prête");
      navigator.serviceWorker.register("/service-worker.js", {scope: "/"})
        .then(observeRegistration)
        .catch(() => { serviceWorkerRegistration = null; pwaState("worker", "Lecture hors ligne indisponible : installation échouée"); });
      navigator.serviceWorker.ready.then(observeRegistration).catch(() => {});
      navigator.serviceWorker.addEventListener("controllerchange", () => {
        if (!hadController) { hadController = true; return; }
        if (window.PhytoForms?.isDirty()) {
          showUpdate("La mise à jour s’appliquera à la prochaine ouverture");
        } else window.location.reload();
      });
      navigator.serviceWorker.addEventListener("message", event => {
        if (event.data?.type === "version" && typeof event.data.version === "string") {
          pwaState("worker", `Lecture hors ligne prête · version active ${event.data.version}`);
        }
      });
    } else {
      pwaState("worker", "Lecture hors ligne indisponible : connexion HTTPS et navigateur compatible requis");
    }

    document.querySelectorAll("[data-pwa-update]").forEach(button => button.addEventListener("click", () => {
      if (waitingWorker) waitingWorker.postMessage({type: "activer"});
    }));

    // Barre mobile : l'onglet emprunté redevient le point de départ du clavier après la
    // navigation. Sans cela, chaque aller-retour renvoyait le focus en haut du document et
    // obligeait à retraverser toute la page pour changer de rubrique.
    //
    // Le focus n'est rendu qu'à l'onglet portant `aria-current="page"`, donc **effectivement
    // atteint** : une redirection vers une autre page ne vole pas le focus. La clé est
    // consommée dans tous les cas. La comparaison se fait sur la valeur de l'attribut, jamais
    // par un sélecteur construit : `CSS.escape` produit un échappement d'identifiant, dont la
    // place dans une valeur d'attribut entre guillemets n'a rien d'évident. Le stockage de
    // session est facultatif — refusé, le repère est simplement perdu.
    const NAV_KEY = "phyto.nav.onglet";
    // Les onglets directs **et** les liens du panneau « Plus » : une rubrique atteinte
    // depuis « Plus » (Historique, Configuration, Console, Application) mérite le même
    // retour de focus qu'un onglet de premier rang.
    const onglets = [...document.querySelectorAll(".mobile-navbar a")];
    for (const lien of onglets) {
      lien.addEventListener("click", () => {
        try { sessionStorage.setItem(NAV_KEY, lien.getAttribute("href")); }
        catch (_error) { /* Stockage facultatif. */ }
      });
    }
    try {
      const attendu = sessionStorage.getItem(NAV_KEY);
      if (attendu) {
        sessionStorage.removeItem(NAV_KEY);
        const cible = onglets
          .find(lien => lien.getAttribute("href") === attendu && lien.getAttribute("aria-current") === "page");
        // Un lien du panneau « Plus » est dans un `<details>` refermé à l'arrivée : il
        // n'est ni visible ni focalisable. Le point de départ du clavier est alors le
        // `<summary>` qui y mène, seul élément réellement présent à l'écran. Ouvrir le
        // panneau d'office montrerait un menu que l'opérateur n'a pas redemandé.
        const repli = cible?.closest("details.mobile-more");
        (repli && !repli.open ? repli.querySelector("summary") : cible)?.focus({preventScroll: true});
      }
    } catch (_error) { /* Stockage facultatif. */ }

    const more = document.querySelector(".mobile-more");
    document.addEventListener("click", (event) => {
      if (more?.open && !more.contains(event.target)) more.open = false;
    });
    document.addEventListener("keydown", (event) => {
      if (event.key === "Escape" && more?.open) {
        more.open = false;
        more.querySelector("summary")?.focus();
      }
    });
  };

  // Le meta phyto-offline-snapshot est la preuve que la navigation elle-même a échoué, pas une
  // suspicion : pas d'hystérésis sur une preuve, la page est hors ligne dès son affichage.
  if (cachedCultureDocument) {
    lastContactAt = cultureSnapshotAt; connectionState = "offline";
    horsLigneDepuis = Date.now(); dernierRafraichissementAge = Date.now();
    updateConnectionBanner();
  }
  initialize();
})();
