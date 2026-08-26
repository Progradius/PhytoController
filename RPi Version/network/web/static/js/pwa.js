(() => {
  "use strict";

  const DB_NAME = "phyto-pwa";
  const DB_VERSION = 1;
  const MAX_SEEN_ALARMS = 500;
  const SEVERITY_RANK = {warning: 0, error: 1, critical: 2};

  let databasePromise = null;
  let lastContactAt = null;
  let connectionFailed = false;
  let offlineAtBoot = false;
  let contactedThisPage = false;
  let deferredInstallPrompt = null;
  let serviceWorkerRegistration = null;
  let lastAlarmFeed = null;
  let notificationEnabled = false;
  let alarmSeen = {};
  let alarmSeenInitialized = false;

  const openDatabase = () => {
    if (!databasePromise) {
      databasePromise = new Promise((resolve, reject) => {
        const request = indexedDB.open(DB_NAME, DB_VERSION);
        request.onupgradeneeded = () => {
          const db = request.result;
          if (!db.objectStoreNames.contains("snapshots")) db.createObjectStore("snapshots", {keyPath: "key"});
          if (!db.objectStoreNames.contains("preferences")) db.createObjectStore("preferences", {keyPath: "key"});
        };
        request.onsuccess = () => resolve(request.result);
        request.onerror = () => reject(request.error);
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

  const setControlsDisabled = (disabled) => {
    document.querySelectorAll("form input, form select, form textarea, form button").forEach((control) => {
      if (disabled && !control.disabled) {
        control.disabled = true;
        control.dataset.pwaDisabled = "true";
      } else if (!disabled && control.dataset.pwaDisabled === "true") {
        control.disabled = false;
        delete control.dataset.pwaDisabled;
      }
    });
  };

  const updateConnectionBanner = () => {
    const banner = document.getElementById("pwa-connection-banner");
    const detail = document.getElementById("pwa-connection-detail");
    if (!banner || !detail) return;
    banner.hidden = !connectionFailed;
    document.body.classList.toggle("is-offline", connectionFailed);
    if (connectionFailed) {
      detail.textContent = lastContactAt
        ? `Données datant au mieux de ${formatElapsed(lastContactAt)} · non actualisées · lecture seule`
        : "Âge des données inconnu · données non actualisées · lecture seule";
      setControlsDisabled(true);
    } else {
      setControlsDisabled(false);
    }
  };

  const markServerContact = async (receivedAt = Date.now()) => {
    const wasOffline = connectionFailed;
    contactedThisPage = true;
    connectionFailed = false;
    lastContactAt = receivedAt;
    await setPreference("lastContactAt", receivedAt);
    updateConnectionBanner();
    if (wasOffline && offlineAtBoot && !sessionStorage.getItem("phyto-pwa-reconnected")) {
      sessionStorage.setItem("phyto-pwa-reconnected", "1");
      window.location.reload();
    }
  };

  const markServerFailure = () => {
    if (!contactedThisPage) offlineAtBoot = true;
    connectionFailed = true;
    updateConnectionBanner();
  };

  const recordNetworkSuccess = async (key, data, receivedAt = Date.now()) => {
    await Promise.all([storeSnapshot(key, data, receivedAt), markServerContact(receivedAt)]);
  };

  window.PhytoPwa = {
    loadSnapshot,
    markServerContact,
    markServerFailure,
    recordNetworkSuccess,
    storeSnapshot,
  };

  const configureSecureNotice = () => {
    const notice = document.getElementById("pwa-security-notice");
    const link = document.getElementById("pwa-security-link");
    if (!notice || window.isSecureContext) return;
    const configured = document.querySelector('meta[name="phyto-secure-url"]')?.content;
    if (link && configured) link.href = configured;
    notice.hidden = false;
  };

  const configureInstallation = () => {
    const button = document.getElementById("pwa-install-button");
    if (!button) return;
    const standalone = window.matchMedia("(display-mode: standalone)").matches;
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

  const processAlarmFeed = async (feed, source) => {
    lastAlarmFeed = feed;
    document.dispatchEvent(new CustomEvent("phyto:alarm-feed", {detail: {feed, source}}));
    if (source !== "network") return;

    await storeSnapshot("active-alarms", feed, Date.now());
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
      const response = await fetch("/api/v1/alarms/active", {
        headers: {Accept: "application/json"},
        cache: "no-store",
      });
      await markServerContact();
      if (!response.ok) throw new Error(`HTTP ${response.status}`);
      await processAlarmFeed(await response.json(), "network");
    } catch (error) {
      if (error instanceof TypeError) markServerFailure();
      const stored = await loadSnapshot("active-alarms");
      if (stored?.data) await processAlarmFeed(stored.data, "stored");
    }
  };

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
      status.textContent = "Permission refusée. Réactivez les notifications depuis les réglages du site dans Chrome.";
      enable.hidden = true;
      disable.hidden = true;
      return;
    }
    if (notificationEnabled && Notification.permission === "granted") {
      status.textContent = "Notifications actives sur ce terminal tant que la PWA reste active.";
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

  const initialize = async () => {
    configureSecureNotice();
    configureInstallation();
    lastContactAt = await getPreference("lastContactAt", null);
    notificationEnabled = await getPreference("notificationsEnabled", false);
    alarmSeen = await getPreference("alarmSeen", {});
    alarmSeenInitialized = await getPreference("alarmSeenInitialized", false);

    if (sessionStorage.getItem("phyto-pwa-reconnected")) {
      sessionStorage.removeItem("phyto-pwa-reconnected");
    }

    if (window.isSecureContext && "serviceWorker" in navigator) {
      try {
        serviceWorkerRegistration = await navigator.serviceWorker.register("/service-worker.js", {scope: "/"});
        serviceWorkerRegistration = await navigator.serviceWorker.ready;
      } catch (_error) {
        serviceWorkerRegistration = null;
      }
    }

    configureNotificationControls();
    updateNotificationControls();
    await fetchAlarmFeed();
    window.setInterval(fetchAlarmFeed, 5000);
    window.setInterval(updateConnectionBanner, 1000);
    document.addEventListener("visibilitychange", () => {
      if (document.visibilityState === "visible") fetchAlarmFeed();
    });
    window.addEventListener("online", fetchAlarmFeed);
  };

  initialize();
})();
