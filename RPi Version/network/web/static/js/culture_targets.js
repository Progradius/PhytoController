(() => {
  "use strict";
  // Lot E : plages cibles pH/EC. Saisie déclarative uniquement ; aucune commande d'équipement,
  // aucune mise en attente hors ligne et aucun rejeu de mutation.
  const csrf = document.querySelector('meta[name="csrf-token"]')?.content;
  const requestId = () => Array.from(crypto.getRandomValues(new Uint8Array(20)), n => n.toString(16).padStart(2, "0")).join("");
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
  document.querySelectorAll("[data-target-form]").forEach(form => {
    const output = form.querySelector("output");
    const get = name => form.elements[name]?.value || "";
    let busy = false, previous = null, key = requestId();
    form.addEventListener("submit", async event => {
      event.preventDefault();
      if (busy) return;
      if (!navigator.onLine || document.body.classList.contains("is-offline")) {
        output.textContent = "Hors ligne : saisie conservée dans cette page, aucun envoi mis en attente.";
        return;
      }
      const button = form.querySelector('[type="submit"]');
      try {
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
        const body = JSON.stringify(command);
        if (previous !== null && previous !== body) key = requestId();
        previous = body; command.request_id = key;
        busy = true; button.disabled = true; output.textContent = "Enregistrement…";
        const controller = new AbortController(), timeout = setTimeout(() => controller.abort(), 15000);
        let response;
        try {
          response = await fetch("/api/v1/cultures/targets", {method: "POST",
            headers: {"Content-Type": "application/json", "X-CSRF-Token": csrf},
            body: JSON.stringify(command), signal: controller.signal});
        } finally { clearTimeout(timeout); }
        const result = await response.json().catch(() => ({error: "Requête refusée. Vérifier la connexion."}));
        // Les champs restent renseignés en cas de refus : la saisie n'est jamais perdue.
        if (!response.ok) throw new Error(`${result.error} Saisie conservée.${response.status === 409 ? " Ouvrir cette page dans un nouvel onglet pour consulter la version actuelle." : ""}`);
        output.textContent = "Enregistré. Ouverture de la plage…";
        const next = new URL(location.href);
        next.searchParams.delete("offset");
        next.hash = `target-${result.id}`;
        if (next.search === location.search) { location.hash = next.hash; location.reload(); }
        else location.assign(next.href);
      } catch (error) {
        output.textContent = error.name === "AbortError" || error instanceof TypeError
          ? "Réponse non reçue. Saisie conservée : réessayer sans modification pour vérifier le même enregistrement."
          : error.message;
      } finally { busy = false; button.disabled = false; }
    });
  });
})();
