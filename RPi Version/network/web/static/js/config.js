(() => {
  "use strict";
  // Le champ natif reste soumis ; les champs séparés ne servent qu’au repli.
  const padTimePart = (value) => String(value).padStart(2, "0");
  document.querySelectorAll("input[data-compact-time]").forEach((input) => {
    if (input.type === "time" && !input.closest(".field-invalid")) return;
    const field = input.closest(".field");
    const fieldLabel = field?.querySelector(`label[for="${CSS.escape(input.id)}"]`);
    if (!field || !fieldLabel) return;
    const required = input.required;

    // `type=time` vide sa propriété `value` lorsque le serveur réaffiche une
    // saisie refusée (par exemple 25:00). L'attribut conserve, lui, le texte
    // original que l'opérateur doit pouvoir corriger.
    const parts = (input.getAttribute("value") || input.value).split(":", 2);
    const control = document.createElement("div");
    control.className = "compact-time-control";
    control.setAttribute("role", "group");
    fieldLabel.id = `${input.id}-label`;
    control.setAttribute("aria-labelledby", fieldLabel.id);

    const makePart = (kind, label, value, maximum) => {
      const wrapper = document.createElement("label");
      wrapper.className = "compact-time-part";
      const caption = document.createElement("span");
      caption.textContent = label;
      const part = document.createElement("input");
      part.type = "text";
      part.inputMode = "numeric";
      part.autocomplete = "off";
      part.maxLength = 2;
      part.pattern = "[0-9]{1,2}";
      part.value = value;
      part.dataset.timePart = kind;
      part.setAttribute("aria-label", `${fieldLabel.textContent.trim()} : ${label.toLowerCase()}`);
      part.setAttribute("enterkeyhint", kind === "hour" ? "next" : "done");
      wrapper.append(caption, part);
      const validate = () => {
        const numeric = /^\d{1,2}$/.test(part.value) ? Number(part.value) : -1;
        part.setCustomValidity(numeric >= 0 && numeric <= maximum ? "" : `${label} : valeur attendue entre 0 et ${maximum}.`);
      };
      part.addEventListener("input", validate);
      validate();
      return { wrapper, part, validate };
    };

    const hour = makePart("hour", "Heures", parts[0] || "", 23);
    const minute = makePart("minute", "Minutes", parts[1] || "", 59);
    const separator = document.createElement("span");
    separator.className = "compact-time-separator";
    separator.textContent = ":";
    separator.setAttribute("aria-hidden", "true");
    control.append(hour.wrapper, separator, minute.wrapper);

    const sync = (normalize = false) => {
      hour.validate();
      minute.validate();
      const valid = hour.part.validity.valid && minute.part.validity.valid;
      if (normalize && valid) {
        hour.part.value = padTimePart(hour.part.value);
        minute.part.value = padTimePart(minute.part.value);
      }
      input.value = valid
        ? `${padTimePart(hour.part.value)}:${padTimePart(minute.part.value)}`
        : `${hour.part.value}:${minute.part.value}`;
    };
    [hour.part, minute.part].forEach((part) => {
      part.addEventListener("input", () => sync());
      part.addEventListener("change", () => sync(true));
      part.addEventListener("blur", () => sync(true));
      part.addEventListener("focus", () => part.select());
    });

    input.type = "hidden";
    input.removeAttribute("required");
    input.removeAttribute("aria-invalid");
    input.removeAttribute("aria-describedby");
    hour.part.required = required;
    minute.part.required = required;
    if (field.classList.contains("field-invalid")) {
      control.setAttribute("aria-invalid", "true");
      const error = field.querySelector(".field-error");
      if (error?.id) control.setAttribute("aria-describedby", error.id);
    }
    fieldLabel.removeAttribute("for");
    input.after(control);
    sync(true);
  });

  // ── Champs numériques en saisie libre ───────────────────────────────────
  // Mesuré sur Chromium en locale fr-FR (`tests/ui/config.spec.js`) :
  // `type="number"` **efface** la virgule — « 20,5 » y devient « 205 » — et
  // vide silencieusement une saisie non numérique en la déclarant valide. Les
  // champs décimaux (et tout champ que le serveur vient de refuser) sont donc
  // des `type="text"` ; la validation native qu'ils perdent est reproduite ici.
  //
  // La règle du pas est celle du HTML, pas une approximation : la base est
  // `min` s'il existe, sinon la valeur **initiale** du champ, sinon 0. Une
  // autre base refuserait des valeurs que `type="number"` acceptait.
  const frenchNumber = (value) => String(value).replace(".", ",");
  const numericAttribute = (input, name) => {
    const raw = input.getAttribute(name);
    if (raw === null || raw.trim() === "") return null;
    const parsed = Number(raw.replace(",", "."));
    return Number.isFinite(parsed) ? parsed : null;
  };
  const validateNumeric = (input) => {
    const raw = input.value.trim();
    // Un champ vide relève de `required` (ou reste facultatif) : ce n'est pas
    // un nombre mal saisi, et l'annoncer comme tel masquerait la vraie cause.
    if (raw === "") { input.setCustomValidity(""); return; }
    const decimals = input.inputMode === "decimal";
    if (!(decimals ? /^-?\d+([.,]\d+)?$/ : /^-?\d+$/).test(raw)) {
      input.setCustomValidity(decimals
        ? "Saisir un nombre (virgule ou point comme séparateur décimal)."
        : "Saisir un nombre entier.");
      return;
    }
    const value = Number(raw.replace(",", "."));
    const minimum = numericAttribute(input, "min");
    const maximum = numericAttribute(input, "max");
    if (minimum !== null && value < minimum) {
      input.setCustomValidity(`Saisir une valeur supérieure ou égale à ${frenchNumber(minimum)}.`);
      return;
    }
    if (maximum !== null && value > maximum) {
      input.setCustomValidity(`Saisir une valeur inférieure ou égale à ${frenchNumber(maximum)}.`);
      return;
    }
    const step = numericAttribute(input, "step");
    if (step !== null && step > 0) {
      const initial = numericAttribute(input, "value");
      const base = minimum !== null ? minimum : (initial === null ? 0 : initial);
      // Le pas est comparé à l'échelle du pas lui-même : en virgule flottante,
      // (20,5 − (−20)) / 0,1 vaut 405,00000000000006, ce qu'un test d'égalité
      // stricte refuserait.
      const scale = 10 ** (String(step).split(".")[1] || "").length;
      const units = (value * scale - base * scale) / (step * scale);
      if (Math.abs(units - Math.round(units)) > 1e-6) {
        input.setCustomValidity(
          `Saisir un multiple de ${frenchNumber(step)}`
          + (minimum !== null ? ` à partir de ${frenchNumber(minimum)}.` : "."),
        );
        return;
      }
    }
    input.setCustomValidity("");
  };
  document.querySelectorAll("input[data-numeric]").forEach((input) => {
    input.addEventListener("input", () => validateNumeric(input));
    input.addEventListener("change", () => validateNumeric(input));
    validateNumeric(input);
  });

  const simpleForm = document.querySelector('form[action="/conf/simple"]');
  const updateGroupSummaries = () => {
    if (!simpleForm) return;
    const value = name => simpleForm.elements.namedItem(name)?.value || "—";
    const summaries = {
      day: `${value("start_time")} → ${value("stop_time")}`,
      light: `Éclairage 1 : ${value("daily1_start")} → ${value("daily1_stop")} · Éclairage 2 : ${value("daily2_start")} → ${value("daily2_stop")}`,
      climate: `Jour ${value("target_temp_min_day")}–${value("target_temp_max_day")} °C · Nuit ${value("target_temp_min_night")}–${value("target_temp_max_night")} °C`,
    };
    simpleForm.querySelectorAll("[data-config-group-summary]").forEach(node => { node.textContent = summaries[node.dataset.configGroupSummary]; });
  };
  simpleForm?.addEventListener("input", updateGroupSummaries);
  simpleForm?.addEventListener("reset", () => setTimeout(updateGroupSummaries, 0));
  updateGroupSummaries();

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
  const previousDirty = window.PhytoForms?.isDirty;
  window.PhytoForms = {isDirty: () => dirtyForms.size > 0 || Boolean(previousDirty?.())};
  const cancelActions = new WeakMap();
  let activeDirtyForm = null;
  const dirtyBar = document.getElementById("config-dirty-bar");
  const dirtyLabel = document.getElementById("config-dirty-label");
  const reserveDirtySpace = () => {
    const height = dirtyBar?.classList.contains("is-visible") ? Math.ceil(dirtyBar.getBoundingClientRect().height) : 0;
    document.documentElement.style.setProperty("--config-dirty-height", `${height}px`);
  };
  if (dirtyBar && "ResizeObserver" in window) new ResizeObserver(reserveDirtySpace).observe(dirtyBar);
  // Un envoi refusé émet **un** `invalid` par commande fautive, dans l'ordre du
  // document, alors que le navigateur ne focalise que la première. Défiler à
  // chaque événement amenait donc la page sur la **dernière** : la commande
  // focalisée, celle que l'opérateur doit corriger, restait hors écran. Seule
  // la première commande encore refusée du formulaire commande le défilement.
  // `validity.valid` est relu sans `checkValidity()`, qui réémettrait `invalid`.
  document.addEventListener("invalid", (event) => {
    const control = event.target;
    const first = control.form && [...control.form.elements].find(
      (candidate) => candidate.willValidate && !candidate.validity.valid,
    );
    if (first && first !== control) return;
    control.scrollIntoView({block: "center"});
  }, true);

  const warnOnUnload = (event) => { event.preventDefault(); event.returnValue = ""; };
  const formLabel = (form) => form.closest("details")?.querySelector("summary span")?.textContent?.trim() || "Cette section";
  const updateDirtyBar = () => {
    if (!dirtyBar) return;
    if (!activeDirtyForm || !dirtyForms.has(activeDirtyForm)) activeDirtyForm = dirtyForms.values().next().value || null;
    dirtyBar.classList.toggle("is-visible", Boolean(activeDirtyForm));
    if (dirtyLabel && activeDirtyForm) {
      const others = Math.max(0, dirtyForms.size - 1);
      dirtyLabel.textContent = `Modifications · ${formLabel(activeDirtyForm)}${others ? ` · +${others} autre${others > 1 ? "s" : ""}` : ""}`;
    }
  };
  const updateUnloadGuard = () => {
    window.removeEventListener("beforeunload", warnOnUnload);
    if (dirtyForms.size > 0) window.addEventListener("beforeunload", warnOnUnload);
    updateDirtyBar();
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
      cancelActions.set(form, () => cancel.click());
    }
    const refreshDirty = () => {
      const dirty = serialize(form) !== initial;
      if (cancel) cancel.hidden = !dirty;
      if (dirty) { dirtyForms.add(form); activeDirtyForm = form; }
      else dirtyForms.delete(form);
      updateUnloadGuard();
    };
    form.addEventListener("input", refreshDirty);
    form.addEventListener("change", refreshDirty);
    form.addEventListener("submit", () => {
      dirtyForms.delete(form);
      if (activeDirtyForm === form) activeDirtyForm = null;
      updateUnloadGuard();
      const button = form.querySelector("[data-save-button]");
      if (button) { button.disabled = true; button.textContent = "Enregistrement…"; }
    });
  });
  dirtyBar?.querySelector("[data-dirty-cancel]")?.addEventListener("click", () => {
    if (activeDirtyForm) cancelActions.get(activeDirtyForm)?.();
  });
  dirtyBar?.querySelector("[data-dirty-save]")?.addEventListener("click", () => activeDirtyForm?.requestSubmit());
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
      const table = document.createElement("table");
      const caption = table.createCaption(); caption.textContent = "Valeur modifiée → valeur appliquée";
      const head = table.createTHead().insertRow();
      for (const title of ["Champ et valeur précédente", "Valeur appliquée"]) {
        const cell = document.createElement("th"); cell.scope = "col"; cell.textContent = title; head.append(cell);
      }
      const body = table.createTBody();
      [...changes, ...(result.profile_changes || [])].forEach(change => {
        const row = body.insertRow();
        row.insertCell().textContent = change.secret ? change.label : `${change.label} : ${change.from}`;
        row.insertCell().textContent = change.secret ? "Nouvelle valeur masquée" : String(change.to);
      });
      panel.append(table);
    }
    if ((result.profile_changes || []).length) line(panel, "Le tableau inclut les réglages fins ramenés au profil de conduite.", "preview-warning");
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
        const response = await (window.PhytoPwa?.fetchWithTimeout || fetch)("/api/v1/config/preview", {
          method: "POST",
          headers: { "Content-Type": "application/json", "X-CSRF-Token": csrfToken },
          body: JSON.stringify({ section, fields: collect() }),
        }, 6000);
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
  const modeContent = document.querySelector("[data-config-mode-content]");
  const modeLoading = document.querySelector(".config-mode-loading");
  // Le premier champ refusé, pas le bandeau : c'est là que la correction se
  // fait. Un groupe de boutons radio n'est pas focalisable lui-même, on vise
  // donc la première commande qu'il contient.
  //
  // L'appel est **suspendu à la révélation du contenu** : tant que
  // `.config-mode-content.is-pending` est posé, `style.css` masque toute la
  // configuration (`display: none !important`), et un `focus()` sur un élément
  // masqué ne fait rien — la page restait sur `<body>`, le champ fautif hors
  // écran, et le `scrollIntoView({block:"center"})` de la fiche R2.1 sans
  // aucun effet. Une seule fois : `revealModeContent` a plusieurs appelants.
  let invalidFocused = false;
  const focusFirstInvalid = () => {
    if (invalidFocused) return;
    invalidFocused = true;
    const firstInvalid = document.querySelector('[aria-invalid="true"]');
    if (!firstInvalid) {
      document.getElementById("form-errors")?.focus();
      return;
    }
    const target = firstInvalid.matches("input, select, textarea")
      ? firstInvalid
      : firstInvalid.querySelector("input, select, textarea");
    const focusable = target || firstInvalid;
    focusable.closest("details")?.setAttribute("open", "");
    focusable.focus({ preventScroll: true });
    focusable.scrollIntoView({ block: "center" });
  };

  const revealModeContent = () => {
    modeContent?.classList.remove("is-pending");
    if (modeLoading) modeLoading.hidden = true;
    focusFirstInvalid();
  };
  const hashTarget = (() => {
    if (!window.location.hash) return null;
    try { return document.getElementById(decodeURIComponent(window.location.hash.slice(1))); }
    catch (_error) { return null; }
  })();
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
  if (!initialMode && hashTarget) initialMode = hashTarget.closest("[data-config-mode]")?.dataset.configMode || "advanced";
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
      if (!csrfToken) { revealModeContent(); return; }
      try {
        const response = await (window.PhytoPwa?.fetchWithTimeout || fetch)("/api/v1/config/preview", {
          method: "POST",
          headers: { "Content-Type": "application/json", "X-CSRF-Token": csrfToken },
          body: JSON.stringify({ section: "simple", fields: {} }),
        }, 6000);
        if (!response.ok) { revealModeContent(); return; }
        await response.json();
      } catch (_error) {
        revealModeContent();
        return;
      }
      switcher.hidden = false;
      applyMode(initialMode);
      revealModeContent();
      if (hashTarget) {
        let parent = hashTarget;
        while (parent) {
          if (parent.matches?.("details")) parent.open = true;
          parent = parent.parentElement;
        }
        window.requestAnimationFrame(() => hashTarget.scrollIntoView({block: "start"}));
      }
    })();
  }
  else revealModeContent();

  // Sans prévisualisation, le mode Avancé est déjà visible : le lien profond
  // doit tout de même ouvrir sa fiche au lieu de pointer vers un résumé fermé.
  if (hashTarget) {
    let parent = hashTarget;
    while (parent) {
      if (parent.matches?.("details")) parent.open = true;
      parent = parent.parentElement;
    }
  }

})();
