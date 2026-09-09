(() => {
  "use strict";
  // Lot F : saisie des repères d'éclairage. Aucune commande d'équipement, aucune
  // écriture de configuration, aucune mise en attente hors ligne.
  const DAY = 1440;
  const PRESETS = {vegetatif: 1080, floraison: 720};
  const duration = minutes => {
    const hours = Math.floor(minutes / 60), rest = minutes % 60;
    return rest ? `${hours} h ${String(rest).padStart(2, "0")}` : `${hours} h`;
  };

  // Envoi, clé d'idempotence, garde hors ligne et restitution des refus : le socle partagé.
  const forms = window.PhytoCultureForms;

  document.querySelectorAll("[data-light-form]").forEach(form => {
    forms.register(form);
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

    const get = name => form.elements[name]?.value || "";
    form.addEventListener("submit", async event => {
      event.preventDefault();
      const command = {operation: form.dataset.operation, confirm_date: form.elements.confirm_date?.checked || false};
      if (form.dataset.id) Object.assign(command, {id: form.dataset.id, version: Number(form.dataset.version)});
      if (command.operation === "light") {
        const on = Number(get("on_minutes"));
        // Refus local : il désigne le champ fautif comme n'importe quel refus du serveur.
        if (!Number.isInteger(on) || on < 0 || on > DAY) {
          forms.showError(form, {error: "Durée d’éclairage attendue : de 0 à 1440 minutes.", field: "on_minutes"});
          return;
        }
        Object.assign(command, {scope: get("scope"), subject_id: get("subject_id"), space: get("space"),
          stage: get("stage"), label: get("label"), on_minutes: on, off_minutes: DAY - on,
          start_at: get("start_at"), end_at: get("end_at"), note: get("note")});
      }
      if (command.operation === "light_close") command.end_at = get("end_at");
      if (form.elements.reason) command.reason = get("reason");
      forms.clearErrors(form);
      forms.status(form, "Enregistrement…");
      const answer = await forms.submitJson(form, "/api/v1/cultures/light", command, {timeoutMs: 45000});
      // Hors ligne et envoi déjà en vol : le socle a posé son message, la saisie reste intacte.
      if (answer.offline || answer.busy || answer.preview) return;
      if (!answer.ok) {
        const data = answer.data || {};
        forms.showError(form, {...data, error: answer.status
          ? `${data.error} Saisie conservée.${answer.status === 409 ? " Ouvrir la page actuelle dans un nouvel onglet." : ""}`
          : data.error});
        return;
      }
      const result = answer.data;
      forms.status(form, "Enregistré. Actualisation…");
      const next = new URL(location.href);
      next.hash = `repere-${result.id}`;
      if (next.search === location.search) { location.hash = next.hash; location.reload(); }
      else location.assign(next.href);
    });
  });
})();
