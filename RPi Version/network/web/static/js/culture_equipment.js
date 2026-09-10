(() => {
  "use strict";
  const currentRubric = document.querySelector(".culture-navigation [aria-current=page]");
  if (currentRubric) requestAnimationFrame(() => currentRubric.scrollIntoView({block: "nearest", inline: "nearest"}));
  // Lot G : saisie des affectations d'équipements. Déclaratif de bout en bout — aucune
  // commande d'équipement, aucune mutation mise en attente et aucun rejeu hors ligne.
  // Envoi, clé d'idempotence, garde hors ligne et restitution des refus : le socle partagé.
  const forms = window.PhytoCultureForms;
  document.querySelectorAll("[data-equipment-form]").forEach(form => {
    forms.register(form);
    const get = name => form.elements[name]?.value.trim() || "";
    form.addEventListener("submit", async event => {
      event.preventDefault();
      const operation = form.dataset.operation;
      const command = {operation, confirm_date: form.elements.confirm_date?.checked || false};
      if (form.dataset.id) Object.assign(command, {id: form.dataset.id, version: Number(form.dataset.version)});
      if (operation === "cancel") command.reason = get("reason");
      else if (operation === "close") Object.assign(command, {end_at: get("end_at"), end_precision: get("end_precision"), reason: get("reason")});
      else {
        const scope = get("scope");
        Object.assign(command, {equipment_id: get("equipment_id"), usage: get("usage"), scope,
          start_at: get("start_at"), start_precision: get("start_precision"),
          end_at: get("end_at"), source: get("source"), note: get("note")});
        // La cible n'est envoyée que pour la portée qui la réclame : une affectation à la
        // serre entière ne traîne ni espace ni réservoir.
        if (scope === "space") command.space = get("space");
        if (scope === "reservoir") command.reservoir_id = get("reservoir_id");
        if (command.end_at) command.end_precision = "date";
        if (operation === "correct") command.reason = get("reason");
      }
      forms.clearErrors(form);
      forms.status(form, "Enregistrement…");
      const answer = await forms.submitJson(form, "/api/v1/cultures/equipment", command, {timeoutMs: 30000});
      // Hors ligne et envoi déjà en vol : le socle a posé son message, la saisie reste intacte.
      if (answer.offline || answer.busy || answer.preview) return;
      if (!answer.ok) {
        const data = answer.data || {};
        forms.showError(form, {...data, error: answer.status
          ? `${data.error} Saisie conservée.${answer.status === 409 ? " Actualiser la page dans un nouvel onglet." : ""}`
          : data.error});
        return;
      }
      forms.status(form, "Enregistré. Actualisation…");
      location.hash = `equipement-${answer.data.equipment_id}`;
      location.reload();
    });
  });
})();
