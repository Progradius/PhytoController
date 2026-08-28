(() => {
  "use strict";
  const setConditionalState = (container, visible) => {
    container.hidden = !visible;
    container.querySelectorAll("input, select, textarea, button").forEach((control) => { control.disabled = !visible; });
  };
  const refreshConditionals = [];
  document.querySelectorAll("[data-mode-form]").forEach((form) => {
    const update = () => {
      const mode = form.querySelector('input[name="mode"]:checked')?.value;
      form.querySelectorAll("[data-mode-fields]").forEach((container) => setConditionalState(container, container.dataset.modeFields === mode));
    };
    form.querySelectorAll('input[name="mode"]').forEach((radio) => radio.addEventListener("change", update));
    refreshConditionals.push(update); update();
  });
  document.querySelectorAll("[data-motor-form]").forEach((form) => {
    const update = () => {
      const mode = form.querySelector('input[name="motor_mode"]:checked')?.value;
      form.querySelectorAll("[data-motor-fields]").forEach((container) => setConditionalState(container, container.dataset.motorFields === mode));
    };
    form.querySelectorAll('input[name="motor_mode"]').forEach((radio) => radio.addEventListener("change", update));
    refreshConditionals.push(update); update();
  });
  document.querySelectorAll("[data-reveal]").forEach((button) => button.addEventListener("click", () => {
    const input = document.getElementById(button.dataset.reveal); if (!input) return;
    const reveal = input.type === "password"; input.type = reveal ? "text" : "password";
    button.textContent = reveal ? "Masquer" : "Afficher";
    button.setAttribute("aria-label", reveal ? "Masquer la nouvelle valeur" : "Afficher la nouvelle valeur");
  }));
  // ── Suivi des modifications non enregistrées ────────────────────────────
  // Seules les différences **réelles** comptent : taper une valeur puis la
  // remettre ne doit ni allumer le bouton d'annulation ni retenir la page.
  const dirtyForms = new Set();
  const warnOnUnload = (event) => { event.preventDefault(); event.returnValue = ""; };
  const updateUnloadGuard = () => {
    window.removeEventListener("beforeunload", warnOnUnload);
    if (dirtyForms.size > 0) window.addEventListener("beforeunload", warnOnUnload);
  };
  const serialize = (form) => {
    const entries = [];
    new FormData(form).forEach((value, key) => {
      if (key !== "csrf_token") entries.push(`${key}=${String(value)}`);
    });
    entries.sort();
    return JSON.stringify(entries);
  };

  document.querySelectorAll("[data-config-form]").forEach((form) => {
    const anchor = form.querySelector("[data-save-button]");
    const initial = serialize(form);
    const snapshot = new Map();
    form.querySelectorAll("input, select, textarea").forEach((control) => {
      snapshot.set(control, control.type === "radio" || control.type === "checkbox" ? control.checked : control.value);
    });
    let cancel = null;
    if (anchor) {
      cancel = document.createElement("button");
      cancel.type = "button";
      cancel.className = "button button-secondary";
      cancel.textContent = "Annuler les modifications";
      cancel.hidden = true;
      anchor.after(cancel);
      cancel.addEventListener("click", () => {
        snapshot.forEach((value, control) => {
          if (control.type === "radio" || control.type === "checkbox") control.checked = value;
          else control.value = value;
        });
        refreshConditionals.forEach((update) => update());
        // Un `input` synthétique relance la vérification d'écarts et la
        // prévisualisation sans que ce bloc ait à les connaître.
        form.dispatchEvent(new Event("input", { bubbles: true }));
      });
    }
    const refreshDirty = () => {
      const dirty = serialize(form) !== initial;
      if (cancel) cancel.hidden = !dirty;
      if (dirty) dirtyForms.add(form); else dirtyForms.delete(form);
      updateUnloadGuard();
    };
    form.addEventListener("input", refreshDirty);
    form.addEventListener("change", refreshDirty);
    form.addEventListener("submit", () => {
      dirtyForms.clear();
      updateUnloadGuard();
      const button = form.querySelector("[data-save-button]");
      if (button) { button.disabled = true; button.textContent = "Enregistrement…"; }
    });
  });
  // ── Prévisualisation serveur ────────────────────────────────────────────
  // Aucune formule thermique ici : le serveur rejoue `settings_from_config`
  // et renvoie les seuils effectifs. Le seuil de ventilation peut dépasser la
  // consigne haute saisie de l'hystérésis plus la zone morte, et c'est
  // précisément ce que le formulaire seul ne dit pas.
  const csrfToken = document.querySelector('input[name="csrf_token"]')?.value || "";
  const decimal = (value) => (typeof value === "number" ? value.toFixed(1).replace(".", ",") : String(value ?? "—"));
  const line = (parent, text, className) => {
    const node = document.createElement("p");
    node.className = className || "preview-line";
    node.textContent = text;
    parent.appendChild(node);
    return node;
  };

  // Le serveur n'accepte qu'une prévisualisation à la fois et impose un
  // intervalle minimum : une file unique évite de lui répondre 429 en boucle.
  let queued = null;
  let queueTimer = null;
  let running = false;
  const pump = async () => {
    if (running || !queued) return;
    const job = queued;
    queued = null;
    running = true;
    try {
      await job();
    } finally {
      running = false;
      if (queued) { clearTimeout(queueTimer); queueTimer = setTimeout(pump, 450); }
    }
  };
  const enqueue = (job) => { queued = job; clearTimeout(queueTimer); queueTimer = setTimeout(pump, 450); };

  const renderPreview = (panel, result) => {
    panel.textContent = "";
    panel.hidden = false;
    if (!result.valid) {
      line(panel, "Cette saisie serait refusée :", "preview-title");
      const list = document.createElement("ul");
      Object.values(result.errors || {}).forEach((message) => {
        const item = document.createElement("li");
        item.textContent = message;
        list.appendChild(item);
      });
      panel.appendChild(list);
      return;
    }
    const changes = result.changes || [];
    if (changes.length === 0) {
      line(panel, "Aucun écart avec la configuration enregistrée.", "preview-title");
    } else {
      line(panel, `${changes.length} champ${changes.length > 1 ? "s" : ""} serai${changes.length > 1 ? "ent" : "t"} modifié${changes.length > 1 ? "s" : ""} :`, "preview-title");
      const list = document.createElement("ul");
      changes.forEach((change) => {
        const item = document.createElement("li");
        item.textContent = change.secret
          ? `${change.label} : nouvelle valeur (masquée)`
          : `${change.label} : ${change.from} → ${change.to}`;
        list.appendChild(item);
      });
      panel.appendChild(list);
    }
    const profile = result.profile_changes || [];
    if (profile.length > 0) {
      line(panel, "Réglages fins ramenés au profil de conduite :", "preview-warning");
      const list = document.createElement("ul");
      profile.forEach((change) => {
        const item = document.createElement("li");
        item.textContent = `${change.label} : ${change.from} → ${change.to}`;
        list.appendChild(item);
      });
      panel.appendChild(list);
    }
    if (result.apply_note) line(panel, result.apply_note, "preview-detail");
    if (!result.climate_relevant || !result.climate) return;
    const climate = result.climate;
    line(panel, "Arbitrage thermique appliqué :", "preview-title");
    [["day", "Jour"], ["night", "Nuit"]].forEach(([key, label]) => {
      const phase = climate.phases[key];
      if (!phase) return;
      const heater = climate.heater_enabled
        ? `chauffage allumé à ${decimal(phase.heater_on_at_or_below)} °C ou moins, coupé au-dessus de ${decimal(phase.heater_off_above)} °C (hystérésis ${decimal(phase.heater_hysteresis)} °C)`
        : "chauffage désactivé";
      line(panel, `${label} · ${heater} · ventilation dès ${decimal(phase.vent_threshold)} °C`);
      if (phase.vent_threshold_raised) {
        line(
          panel,
          `${label} · seuil de ventilation relevé à ${decimal(phase.vent_threshold)} °C : la consigne haute saisie (${decimal(phase.temp_max)} °C) est sous minimum + hystérésis + zone morte. La serre montera jusqu’à ${decimal(phase.vent_threshold)} °C avant de ventiler, soit ${decimal(phase.vent_threshold - phase.temp_max)} °C de plus que la consigne.`,
          "preview-warning",
        );
      }
      const rungs = phase.vent_ladder || [];
      const ladder = rungs
        .map((rung) => `${decimal(rung.starts_at)} °C → vitesse ${rung.effective_speed}`)
        .join(" · ");
      if (ladder) line(panel, `${label} · paliers : ${ladder}`, "preview-detail");
      // Sans cette ligne, l'hystérésis des paliers reste invisible : le seuil
      // d'engagement seul laisse croire qu'un dixième de degré suffit à
      // redescendre d'un cran, ce qui ferait battre le relais.
      if (rungs.length > 0) {
        const releases = rungs.map((rung) => decimal(rung.releases_below)).join(" / ");
        line(
          panel,
          `${label} · un palier ne redescend que sous ${releases} °C (relâchement ${decimal(phase.vent_release)} °C) et jamais avant ${phase.min_dwell_seconds} s de maintien.`,
          "preview-detail",
        );
      }
    });
  };

  document.querySelectorAll("[data-config-form]").forEach((form) => {
    const match = /\/conf\/([^/?#]+)$/.exec(form.getAttribute("action") || "");
    if (!match || !csrfToken) return;
    const section = decodeURIComponent(match[1]);
    const anchor = form.querySelector("[data-save-button]");
    if (!anchor) return;
    const panel = document.createElement("div");
    panel.className = "preview-panel";
    panel.setAttribute("role", "status");
    panel.hidden = true;
    anchor.parentNode.insertBefore(panel, anchor);
    let supported = true;

    const collect = () => {
      const fields = {};
      new FormData(form).forEach((value, key) => {
        if (key === "csrf_token" || typeof value !== "string") return;
        // Un secret ne part pas dans une requête de confort : il n'a rien à
        // faire dans un corps que l'opérateur n'a pas explicitement enregistré.
        if (form.querySelector(`[name="${CSS.escape(key)}"]`)?.dataset.secret !== undefined) return;
        fields[key] = value;
      });
      return fields;
    };

    const request = async () => {
      if (!supported) return;
      try {
        const response = await fetch("/api/v1/config/preview", {
          method: "POST",
          headers: { "Content-Type": "application/json", "X-CSRF-Token": csrfToken },
          body: JSON.stringify({ section, fields: collect() }),
        });
        if (response.status === 400) { supported = false; panel.hidden = true; return; }
        if (response.status === 429) { enqueue(request); return; }
        if (!response.ok) return;
        renderPreview(panel, await response.json());
      } catch (_error) {
        // La prévisualisation est un confort : une coupure réseau ne doit
        // jamais empêcher d'enregistrer la section.
      }
    };

    form.addEventListener("input", () => enqueue(request));
    form.addEventListener("change", () => enqueue(request));
  });

  // ── Mode d'affichage Simple / Avancé ───────────────────────────────────
  // Le mode Simple écrit de vrais paramètres thermiques : il ne s'affiche que
  // si la prévisualisation répond, seule à rendre visible le seuil de
  // ventilation effectif. Sans elle, l'opérateur reste sur le mode avancé, où
  // chaque valeur est saisie explicitement.
  const MODE_KEY = "phyto.conf.mode";
  const switcher = document.querySelector("[data-mode-switch]");
  const applyMode = (mode) => {
    document.querySelectorAll("[data-config-mode]").forEach((node) => {
      node.hidden = node.dataset.configMode !== mode;
    });
    switcher?.querySelectorAll("[data-set-mode]").forEach((button) => {
      button.setAttribute("aria-pressed", String(button.dataset.setMode === mode));
    });
  };
  // Une section refusée impose son propre mode : masquer le champ fautif au
  // profit d'une préférence enregistrée rendrait l'erreur introuvable.
  const refused = document.querySelector('[aria-invalid="true"]');
  let initialMode = refused ? (refused.closest("[data-config-mode]")?.dataset.configMode || "advanced") : "";
  if (!initialMode) {
    initialMode = "simple";
    try { if (localStorage.getItem(MODE_KEY) === "advanced") initialMode = "advanced"; } catch (_error) { /* stockage indisponible */ }
  }
  if (switcher) {
    switcher.querySelectorAll("[data-set-mode]").forEach((button) => button.addEventListener("click", () => {
      const mode = button.dataset.setMode;
      applyMode(mode);
      try { localStorage.setItem(MODE_KEY, mode); } catch (_error) { /* stockage indisponible */ }
    }));
    (async () => {
      if (!csrfToken) return;
      try {
        const response = await fetch("/api/v1/config/preview", {
          method: "POST",
          headers: { "Content-Type": "application/json", "X-CSRF-Token": csrfToken },
          body: JSON.stringify({ section: "simple", fields: {} }),
        });
        if (!response.ok) return;
        await response.json();
      } catch (_error) {
        return;
      }
      switcher.hidden = false;
      applyMode(initialMode);
    })();
  }

  // Le premier champ refusé, pas le bandeau : c'est là que la correction se
  // fait. Un groupe de boutons radio n'est pas focalisable lui-même, on vise
  // donc la première commande qu'il contient.
  const firstInvalid = document.querySelector('[aria-invalid="true"]');
  if (firstInvalid) {
    const target = firstInvalid.matches("input, select, textarea")
      ? firstInvalid
      : firstInvalid.querySelector("input, select, textarea");
    const focusable = target || firstInvalid;
    focusable.closest("details")?.setAttribute("open", "");
    focusable.focus({ preventScroll: true });
    focusable.scrollIntoView({ block: "center" });
  } else {
    document.getElementById("form-errors")?.focus();
  }
})();
