(() => {
  "use strict";
  const currentRubric = document.querySelector(".culture-navigation [aria-current=page]");
  if (currentRubric) requestAnimationFrame(() => currentRubric.scrollIntoView({block: "nearest", inline: "nearest"}));
  // Lot E : plages cibles pH/EC. Saisie déclarative uniquement ; aucune commande d'équipement,
  // aucune mise en attente hors ligne et aucun rejeu de mutation.
  document.querySelectorAll("[data-targets-offset]").forEach(link => {
    const query = new URLSearchParams(location.search);
    query.set("offset", link.dataset.targetsOffset);
    link.search = query.toString();
  });
  const exportLink = document.querySelector("[data-targets-export]");
  if (exportLink) {
    const query = new URLSearchParams(location.search);
    const kept = new URLSearchParams({format: "csv"});
    for (const name of ["target", "scope"]) if (query.get(name)) kept.set(name, query.get(name));
    exportLink.search = kept.toString();
  }
  // Une valeur vide reste vide : une borne absente n'est jamais convertie en zéro.
  const decimal = value => (value.trim() === "" ? null : value.trim());
  // Envoi, clé d'idempotence, garde hors ligne et restitution des refus : le socle partagé.
  // Le formulaire n'a plus ni `fetch`, ni clé, ni drapeau d'envoi propres — une panne réseau
  // ou un délai dépassé y est traité comme sur les autres pages du carnet.
  const forms = window.PhytoCultureForms;
  document.querySelectorAll("[data-target-form]").forEach(form => {
    forms.register(form);
    const get = name => form.elements[name]?.value || "";
    form.addEventListener("submit", async event => {
      event.preventDefault();
      const command = {operation: form.dataset.operation, confirm_date: form.elements.confirm_date?.checked || false};
      if (form.dataset.id) Object.assign(command, {id: form.dataset.id, version: Number(form.dataset.version)});
      if (command.operation === "target") {
        Object.assign(command, {target: get("target"), label: get("label"), stage: get("stage"),
          ph_min: decimal(get("ph_min")), ph_max: decimal(get("ph_max")),
          ec_min: decimal(get("ec_min")), ec_max: decimal(get("ec_max")), ec_unit: get("ec_unit"),
          start_at: get("start_at"), start_precision: get("start_precision"),
          end_at: get("end_at") || null, end_precision: get("end_precision"), note: get("note")});
        if (form.dataset.id) command.reason = get("reason");
      } else {
        Object.assign(command, {action: form.dataset.action, reason: get("reason")});
        if (form.dataset.action === "end") Object.assign(command, {end_at: get("end_at"), end_precision: get("end_precision")});
      }
      forms.clearErrors(form);
      forms.status(form, "Enregistrement…");
      const answer = await forms.submitJson(form, "/api/v1/cultures/targets", command);
      // Hors ligne et envoi déjà en vol : le socle a posé son message, la saisie reste intacte.
      if (answer.offline || answer.busy || answer.preview) return;
      if (!answer.ok) {
        const data = answer.data || {};
        // Les champs restent renseignés en cas de refus : la saisie n'est jamais perdue.
        // Sans réponse HTTP il n'y a pas de refus à qualifier : le message du socle dit déjà
        // que la saisie est conservée, l'y répéter en ferait deux.
        forms.showError(form, {...data, error: answer.status
          ? `${data.error} Saisie conservée.${answer.status === 409 ? " Ouvrir cette page dans un nouvel onglet pour consulter la version actuelle." : ""}`
          : data.error});
        return;
      }
      const result = answer.data;
      forms.status(form, "Enregistré. Ouverture de la plage…");
      const next = new URL(location.href);
      next.searchParams.delete("offset");
      next.hash = `target-${result.id}`;
      if (next.search === location.search) { location.hash = next.hash; location.reload(); }
      else location.assign(next.href);
    });
  });
})();
