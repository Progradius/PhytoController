(() => {
  "use strict";
  const currentRubric = document.querySelector(".culture-navigation [aria-current=page]");
  if (currentRubric) requestAnimationFrame(() => currentRubric.scrollIntoView({block: "nearest", inline: "nearest"}));
  // Lot H : saisie, correction et photo d'une observation d'espace, plus l'inventaire daté
  // des pages du carnet conservées hors ligne. Aucune mutation n'est mise en attente.
  // La pagination conserve les filtres : seul le décalage change dans l'adresse courante.
  document.querySelectorAll("[data-journal-offset]").forEach(link => {
    const query = new URLSearchParams(location.search);
    query.set("offset", link.dataset.journalOffset);
    query.delete("focus");
    link.search = query.toString();
  });
  // Envoi, clé d'idempotence, garde hors ligne et restitution des refus : le socle partagé.
  // L'observation et sa photo suivent désormais le même chemin que le reste du carnet ;
  // le texte des messages, lui, ne change pas.
  const forms = window.PhytoCultureForms;
  document.querySelectorAll("[data-journal-form], [data-journal-photo]").forEach(form => {
    forms.register(form);
    const get = name => form.elements[name]?.value || "";
    form.addEventListener("submit", async event => {
      event.preventDefault();
      const photo = form.hasAttribute("data-journal-photo");
      const command = {confirm_date: form.elements.confirm_date?.checked || false};
      let file = null;
      if (photo) {
        file = form.elements.photo.files[0];
        // Refus local : il désigne le champ fautif comme n'importe quel refus du serveur.
        if (!file || file.size > 5 * 1024 * 1024) {
          forms.showError(form, {error: "Choisir une photo de 5 Mio maximum.", field: "photo"});
          return;
        }
        Object.assign(command, {space_event_id: form.dataset.id, space_event_revision: Number(form.dataset.version),
          caption: get("caption")});
      } else {
        command.operation = form.dataset.operation;
        Object.assign(command, {effective_at: get("effective_at"), note: get("note")});
        if (command.operation === "space_event") Object.assign(command, {space: get("space"), kind: get("kind"), precision: get("precision")});
        else Object.assign(command, {id: form.dataset.id, version: Number(form.dataset.version),
          reason: get("reason"), cancelled: form.elements.cancelled?.checked || false});
      }
      forms.clearErrors(form);
      forms.status(form, photo ? "Vérification et enregistrement de la photo…" : "Enregistrement…");
      // La clé d'idempotence est celle du socle : elle survit à un renvoi identique et change
      // dès que la saisie — ou le fichier choisi — change.
      const answer = photo
        ? await forms.submitBinary(form, "/api/v1/cultures/journal/photos", file, command, {timeoutMs: 45000})
        : await forms.submitJson(form, "/api/v1/cultures/journal", command, {timeoutMs: 45000});
      // Hors ligne et envoi déjà en vol : le socle a posé son message, la saisie reste intacte.
      if (answer.offline || answer.busy || answer.preview) return;
      if (!answer.ok) {
        const data = answer.data || {};
        // Sans réponse HTTP il n'y a pas de refus à qualifier : le message du socle dit déjà
        // que la saisie est conservée, l'y répéter en ferait deux.
        forms.showError(form, {...data, error: answer.status
          ? `${data.error} Saisie conservée.${answer.status === 409 ? " Ouvrir la version actuelle dans un nouvel onglet." : ""}`
          : data.error});
        return;
      }
      const result = answer.data;
      forms.status(form, "Enregistré. Actualisation…");
      // Les filtres restent ceux de la page ; seul le repère d'opération est ajouté pour
      // retrouver l'entrée à travers la pagination.
      const next = new URL(location.href);
      next.searchParams.delete("offset");
      next.searchParams.set("focus", photo ? form.dataset.id : result.id);
      next.hash = `entry-${photo ? form.dataset.id : result.id}`;
      if (next.search === location.search) { location.hash = next.hash; location.reload(); }
      else location.assign(next.href);
    });
  });
  // L'inventaire daté des pages conservées hors ligne appartient à `app.js`, chargé sur
  // toutes les pages : il est le seul à écrire dans `[data-culture-offline-index]` et à
  // marquer les liens non conservés. Deux scripts y écrivaient en concurrence sur cette
  // page — les liens de pagination portent désormais `data-culture-page`, que l'inventaire
  // partagé connaît déjà.
})();
