(() => {
  "use strict";
  // Lot F : saisie des repères d'éclairage. Aucune commande d'équipement, aucune
  // écriture de configuration, aucune mise en attente hors ligne.
  const csrf = document.querySelector('meta[name="csrf-token"]')?.content;
  const identifier = () => Array.from(crypto.getRandomValues(new Uint8Array(20)), n => n.toString(16).padStart(2, "0")).join("");
  const DAY = 1440;
  const PRESETS = {vegetatif: 1080, floraison: 720};
  const duration = minutes => {
    const hours = Math.floor(minutes / 60), rest = minutes % 60;
    return rest ? `${hours} h ${String(rest).padStart(2, "0")}` : `${hours} h`;
  };

  document.querySelectorAll("[data-light-form]").forEach(form => {
    const minutes = form.querySelector("[data-light-minutes]");
    const stage = form.querySelector("[data-light-stage]");
    const preview = form.querySelector("[data-light-preview]");
    const preset = form.querySelector("[data-light-preset]");
    const describe = () => {
      if (!preview || !minutes) return;
      const value = Number(minutes.value);
      preview.textContent = Number.isInteger(value) && value >= 0 && value <= DAY
        ? `${duration(value)} d’éclairage et ${duration(DAY - value)} d’obscurité par jour. Repère informatif : il ne change aucun horaire.`
        : "Durée attendue : de 0 à 1440 minutes, éclairage et obscurité totalisant 24 h.";
    };
    minutes?.addEventListener("input", describe);
    const propose = () => {
      if (!preset) return;
      preset.hidden = !(stage.value in PRESETS);
      if (!preset.hidden) preset.textContent = `Utiliser ${duration(PRESETS[stage.value])} / ${duration(DAY - PRESETS[stage.value])}`;
    };
    stage?.addEventListener("change", propose);
    preset?.addEventListener("click", () => {
      minutes.value = String(PRESETS[stage.value]);
      describe();
    });
    propose();
    describe();

    let busy = false, previous = null, key = identifier();
    const get = name => form.elements[name]?.value || "";
    form.addEventListener("submit", async event => {
      event.preventDefault();
      if (busy) return;
      const output = form.querySelector("output"), button = form.querySelector('[type="submit"]');
      if (!navigator.onLine || document.body.classList.contains("is-offline")) {
        output.textContent = "Hors ligne : saisie conservée dans cette page, aucun envoi en attente.";
        return;
      }
      try {
        const command = {operation: form.dataset.operation, confirm_date: form.elements.confirm_date?.checked || false};
        if (form.dataset.id) Object.assign(command, {id: form.dataset.id, version: Number(form.dataset.version)});
        if (command.operation === "light") {
          const on = Number(get("on_minutes"));
          if (!Number.isInteger(on) || on < 0 || on > DAY) throw new Error("Durée d’éclairage attendue : de 0 à 1440 minutes.");
          Object.assign(command, {scope: get("scope"), subject_id: get("subject_id"), space: get("space"),
            stage: get("stage"), label: get("label"), on_minutes: on, off_minutes: DAY - on,
            start_at: get("start_at"), end_at: get("end_at"), note: get("note")});
        }
        if (command.operation === "light_close") command.end_at = get("end_at");
        if (form.elements.reason) command.reason = get("reason");
        const signature = JSON.stringify(command);
        if (previous !== null && previous !== signature) key = identifier();
        previous = signature; command.request_id = key;
        busy = true; button.disabled = true; output.textContent = "Enregistrement…";
        const controller = new AbortController(), timeout = setTimeout(() => controller.abort(), 45000);
        let response;
        try {
          response = await fetch("/api/v1/cultures/light", {method: "POST",
            headers: {"X-CSRF-Token": csrf, "Content-Type": "application/json"},
            body: JSON.stringify(command), signal: controller.signal});
        } finally { clearTimeout(timeout); }
        const result = await response.json().catch(() => ({error: "Requête refusée. Vérifier la connexion."}));
        if (!response.ok) throw new Error(`${result.error} Saisie conservée.${response.status === 409 ? " Ouvrir la page actuelle dans un nouvel onglet." : ""}`);
        output.textContent = "Enregistré. Actualisation…";
        const next = new URL(location.href);
        next.hash = `repere-${result.id}`;
        if (next.search === location.search) { location.hash = next.hash; location.reload(); }
        else location.assign(next.href);
      } catch (error) {
        output.textContent = error instanceof TypeError || error.name === "AbortError"
          ? "Réponse non reçue. Saisie conservée : réessayer sans modification pour vérifier le même enregistrement."
          : error.message;
      } finally { busy = false; button.disabled = false; }
    });
  });
})();
