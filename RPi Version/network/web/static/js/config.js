(() => {
  "use strict";
  const setConditionalState = (container, visible) => {
    container.hidden = !visible;
    container.querySelectorAll("input, select, textarea, button").forEach((control) => { control.disabled = !visible; });
  };
  document.querySelectorAll("[data-mode-form]").forEach((form) => {
    const update = () => {
      const mode = form.querySelector('input[name="mode"]:checked')?.value;
      form.querySelectorAll("[data-mode-fields]").forEach((container) => setConditionalState(container, container.dataset.modeFields === mode));
    };
    form.querySelectorAll('input[name="mode"]').forEach((radio) => radio.addEventListener("change", update)); update();
  });
  document.querySelectorAll("[data-motor-form]").forEach((form) => {
    const update = () => {
      const mode = form.querySelector('input[name="motor_mode"]:checked')?.value;
      form.querySelectorAll("[data-motor-fields]").forEach((container) => setConditionalState(container, container.dataset.motorFields === mode));
    };
    form.querySelectorAll('input[name="motor_mode"]').forEach((radio) => radio.addEventListener("change", update)); update();
  });
  document.querySelectorAll("[data-reveal]").forEach((button) => button.addEventListener("click", () => {
    const input = document.getElementById(button.dataset.reveal); if (!input) return;
    const reveal = input.type === "password"; input.type = reveal ? "text" : "password";
    button.textContent = reveal ? "Masquer" : "Afficher";
    button.setAttribute("aria-label", reveal ? "Masquer la nouvelle valeur" : "Afficher la nouvelle valeur");
  }));
  document.querySelectorAll("[data-config-form]").forEach((form) => form.addEventListener("submit", () => {
    const button = form.querySelector("[data-save-button]"); if (button) { button.disabled = true; button.textContent = "Enregistrement…"; }
  }));
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
    if (!result.climate_relevant || !result.climate) return;
    const climate = result.climate;
    line(panel, "Arbitrage thermique appliqué :", "preview-title");
    [["day", "Jour"], ["night", "Nuit"]].forEach(([key, label]) => {
      const phase = climate.phases[key];
      if (!phase) return;
      const heater = climate.heater_enabled
        ? `chauffage sous ${decimal(phase.heater_on_at_or_below)} °C, coupé au-dessus de ${decimal(phase.heater_off_above)} °C`
        : "chauffage désactivé";
      line(panel, `${label} · ${heater} · ventilation dès ${decimal(phase.vent_threshold)} °C`);
      if (phase.vent_threshold_raised) {
        line(
          panel,
          `${label} · seuil de ventilation relevé à ${decimal(phase.vent_threshold)} °C : la consigne haute saisie (${decimal(phase.temp_max)} °C) est sous minimum + hystérésis + zone morte. La serre montera d’autant avant de ventiler.`,
          "preview-warning",
        );
      }
      const ladder = (phase.vent_ladder || [])
        .map((rung) => `${decimal(rung.starts_at)} °C → vitesse ${rung.effective_speed}`)
        .join(" · ");
      if (ladder) line(panel, `${label} · paliers : ${ladder}`, "preview-detail");
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
