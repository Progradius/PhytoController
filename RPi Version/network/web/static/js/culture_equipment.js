(() => {
  "use strict";
  // Lot G : saisie des affectations d'équipements. Déclaratif de bout en bout — aucune
  // commande d'équipement, aucune mutation mise en attente et aucun rejeu hors ligne.
  const csrf = document.querySelector('meta[name="csrf-token"]')?.content;
  const identifier = () => Array.from(crypto.getRandomValues(new Uint8Array(20)), n => n.toString(16).padStart(2, "0")).join("");
  // Socle partagé : identifiants de champs et restitution des refus au champ concerné.
  const forms = window.PhytoCultureForms;
  const refuser = (form, output, message, result) => {
    if (forms) forms.showError(form, {...result, error: message});
    else output.textContent = message;
  };
  document.querySelectorAll("[data-equipment-form]").forEach(form => {
    forms?.register(form);
    let busy = false, previous = null, key = identifier();
    const get = name => form.elements[name]?.value.trim() || "";
    form.addEventListener("submit", async event => {
      event.preventDefault();
      if (busy) return;
      const output = form.querySelector("output"), button = form.querySelector('[type="submit"]');
      if (!navigator.onLine || document.body.classList.contains("is-offline")) {
        output.textContent = "Hors ligne : saisie conservée dans cette page, aucun envoi en attente.";
        return;
      }
      forms?.clearErrors(form);
      try {
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
        const signature = JSON.stringify(command);
        if (previous !== null && previous !== signature) key = identifier();
        previous = signature; command.request_id = key;
        busy = true; button.disabled = true; output.textContent = "Enregistrement…";
        const controller = new AbortController(), timeout = setTimeout(() => controller.abort(), 30000);
        let response;
        try {
          response = await fetch("/api/v1/cultures/equipment", {method: "POST",
            headers: {"X-CSRF-Token": csrf, "Content-Type": "application/json"},
            body: JSON.stringify(command), signal: controller.signal});
        } finally { clearTimeout(timeout); }
        const result = await response.json().catch(() => ({error: "Requête refusée. Vérifier la connexion."}));
        if (!response.ok) {
          refuser(form, output,
            `${result.error} Saisie conservée.${response.status === 409 ? " Actualiser la page dans un nouvel onglet." : ""}`,
            result);
          return;
        }
        output.textContent = "Enregistré. Actualisation…";
        location.hash = `equipement-${result.equipment_id}`;
        location.reload();
      } catch (error) {
        output.textContent = error instanceof TypeError || error.name === "AbortError"
          ? "Réponse non reçue. Saisie conservée : réessayer sans modification pour vérifier le même enregistrement."
          : error.message;
      } finally { busy = false; button.disabled = false; }
    });
  });
})();
