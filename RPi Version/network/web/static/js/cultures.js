(() => {
  "use strict";
  const csrf = document.querySelector('meta[name="csrf-token"]')?.content;
  const zoneNotice = document.querySelector("[data-device-timezone]");
  if (zoneNotice) zoneNotice.textContent = `Heures précises : fuseau de cet appareil (${Intl.DateTimeFormat().resolvedOptions().timeZone}). Les dates seules ne sont pas converties.`;
  const preview = document.querySelector("[data-culture-preview]");
  const previewTime = document.querySelector("[data-culture-updated]");
  const refreshPreview = async () => {
    if (!preview || document.visibilityState === "hidden") return;
    try {
      const response = await fetch("/api/v1/cultures", {cache: "no-store"});
      if (!response.ok) throw new Error();
      const data = await response.json();
      preview.replaceChildren();
      for (const [id, label] of [["space_1", "Espace 1"], ["space_2", "Espace 2"]]) {
        const card = document.createElement("article"); card.className = "card";
        const title = document.createElement("h3"); title.textContent = label; card.append(title);
        const occupants = data.occupants.filter(item => item.space === id);
        if (!occupants.length) { const p = document.createElement("p"); p.textContent = "Aucune occupation déclarée."; card.append(p); }
        for (const item of occupants) {
          const p = document.createElement("p"), link = document.createElement("a");
          link.href = `/cultures/${encodeURIComponent(item.id)}`; link.textContent = item.name;
          p.append(link, ` · ${item.stage_label}${item.age ? ` · J${item.age.days} (${item.age.weeks} sem. + ${item.age.remaining_days} j)` : ""}${item.archived ? " · à libérer" : ""}`); card.append(p);
          if (item.latest_reading) {
            const reading = item.latest_reading, measure = document.createElement("p");
            const d = reading.effective_at.length === 10 ? reading.effective_at.split("-").reverse().join("/") : new Date(reading.effective_at).toLocaleString("fr-FR");
            measure.textContent = `Dernier relevé : ${d} · pH ${reading.ph ?? "—"} · EC ${reading.ec ?? "—"} mS/cm`;
            card.append(measure);
          }
        }
        const quick = document.createElement("a"); quick.href = `/cultures/solutions?target=${id === "space_1" ? "cuttings_1" : "reservoir_2"}`;
        quick.textContent = "Saisir un relevé"; card.append(quick);
        preview.append(card);
      }
      previewTime.textContent = `Carnet actualisé à ${new Date().toLocaleTimeString("fr-FR")}${data.clock_reliable ? "" : " · horloge non synchronisée, compteurs à vérifier"}`;
    } catch (_error) {
      previewTime.textContent = "Carnet non actualisé ; les éventuelles données affichées sont anciennes.";
      if (preview.textContent.includes("Chargement")) preview.textContent = "Carnet indisponible. Le contrôle reste actif.";
    }
  };
  if (preview) { refreshPreview(); setInterval(refreshPreview, 60000); window.addEventListener("focus", refreshPreview); }
  // Fonctionne aussi sur HTTP LAN, où randomUUID n'est pas toujours exposé.
  const requestId = () => Array.from(crypto.getRandomValues(new Uint8Array(20)), n => n.toString(16).padStart(2, "0")).join("");
  const stamp = (form, name) => {
    const input = form.elements[name];
    const value = input.value;
    const precision = form.elements[`${name}_precision`].value;
    return {value: precision === "instant" ? (input.dataset.renderedInstant === value ? input.dataset.instant : new Date(value).toISOString()) : value, precision};
  };
  const payload = (form) => {
    const kind = form.dataset.kind;
    const get = name => form.elements[name]?.value || "";
    const data = {};
    if (kind === "create" && form.querySelector("[data-origins]")) data.origins = Array.from(form.querySelectorAll(".culture-origin"), row => ({
      id: row.dataset.originId, mother_id: row.querySelector('[name="mother_id"]')?.value || null,
      label: row.querySelector('[name="origin_label"]')?.value || "", count: Number(row.querySelector('[name="origin_count"]').value),
    }));
    if (["note", "loss", "harvest", "finish", "archive"].includes(kind)) data.note = get("note");
    if (kind === "stage") data.stage = get("stage");
    if (kind === "move") data.space = get("space");
    if (kind === "harvest") {
      const drying = stamp(form, "drying_at");
      Object.assign(data, {drying_at: drying.value, drying_precision: drying.precision});
    }
    if (kind === "identity") Object.assign(data, {name: get("name"), variety: get("variety")});
    if (kind === "loss") Object.assign(data, {count: Number(get("count")), origin_id: get("origin_id")});
    if (kind === "finish") {
      const raw = get("weight_g").trim();
      const weight = raw ? Number(raw.replace(",", ".")) : null;
      if (weight !== null && !Number.isFinite(weight)) throw new Error("Poids sec invalide.");
      Object.assign(data, {weight_g: weight, release: form.elements.release.checked});
    }
    return data;
  };
  document.querySelectorAll(".culture-form").forEach(form => {
    form.querySelectorAll("input[data-instant]").forEach(input => {
      const d = new Date(input.dataset.instant);
      input.step = "any";
      input.value = new Date(d.getTime() - d.getTimezoneOffset() * 60000).toISOString().slice(0, 23);
      input.dataset.renderedInstant = input.value;
    });
    form.querySelectorAll('select[name$="_precision"]').forEach(select => select.addEventListener("change", () => {
      const input = form.elements[select.name.replace(/_precision$/, "")];
      const previous = input.value;
      input.type = select.value === "instant" ? "datetime-local" : "date";
      input.value = select.value === "instant" ? (previous.length === 10 ? `${previous}T12:00` : previous) : previous.slice(0, 10);
    }));
    const syncOrigins = () => {
      const cutting = form.elements.origin_type?.value === "cutting";
      form.querySelectorAll("[data-seed]").forEach(el => { el.hidden = cutting; el.querySelector("input").required = !cutting; });
      form.querySelectorAll("[data-cutting]").forEach(el => { el.hidden = !cutting; el.querySelector("select").required = cutting; });
      const stage = form.elements.stage;
      if (stage && form.elements.origin_type) {
        for (const option of stage.options) {
          option.disabled = cutting ? option.value === "germination" : option.value === "enracinement";
        }
        if (stage.selectedOptions[0]?.disabled) stage.value = cutting ? "enracinement" : "germination";
      }
    };
    form.elements.origin_type?.addEventListener("change", syncOrigins);
    form.querySelector("[data-add-origin]")?.addEventListener("click", () => {
      const list = form.querySelector("[data-origins]");
      if (list.children.length >= 50) return;
      const row = list.firstElementChild.cloneNode(true);
      row.querySelector('input[name="origin_label"]').value = "";
      row.querySelector('input[name="origin_count"]').value = "1";
      row.querySelector("select").value = "";
      list.append(row); syncOrigins();
    });
    form.addEventListener("click", event => {
      if (event.target.closest("[data-remove-origin]") && form.querySelectorAll(".culture-origin").length > 1) {
        event.target.closest(".culture-origin").remove();
      }
    });
    syncOrigins();
    let previousBody = null;
    let key = requestId();
    let busy = false;
    form.addEventListener("submit", async event => {
      event.preventDefault();
      if (busy) return;
      const output = form.querySelector("output");
      const button = form.querySelector('[type="submit"]');
      if (!navigator.onLine || document.body.classList.contains("is-offline")) { output.textContent = "Hors ligne : saisie conservée dans cette page, aucun envoi mis en attente."; return; }
      try {
        let command;
        if (form.hasAttribute("data-culture-create")) {
          const origin = stamp(form, "origin_at"), stage = stamp(form, "stage_at"), space = stamp(form, "space_at");
          command = {operation: "create", kind: form.dataset.kind, name: form.elements.name.value,
            variety: form.elements.variety.value, origin_at: origin.value, origin_precision: origin.precision,
            stage: form.elements.stage.value, stage_at: stage.value, stage_precision: stage.precision,
            space: form.elements.space.value, space_at: space.value, space_precision: space.precision};
          if (form.dataset.kind === "lot") {
            command.origin_type = form.elements.origin_type.value;
            command.origins = Array.from(form.querySelectorAll(".culture-origin"), row => ({
              mother_id: command.origin_type === "cutting" ? row.querySelector("select").value : null,
              label: command.origin_type === "seed" ? row.querySelector('[name="origin_label"]').value : "",
              count: Number(row.querySelector('[name="origin_count"]').value),
            }));
          }
        } else {
          const effective = stamp(form, "effective_at");
          command = {operation: form.hasAttribute("data-culture-correct") ? "correct" : "event",
            subject_id: form.dataset.subject, version: Number(form.dataset.version), kind: form.dataset.kind,
            effective_at: effective.value, precision: effective.precision, payload: payload(form)};
          if (command.operation === "correct") Object.assign(command, {event_id: form.dataset.event,
            cancelled: form.elements.cancelled?.checked || false, reason: form.elements.reason.value});
        }
        command.confirm_date = form.elements.confirm_date?.checked || false;
        const body = JSON.stringify(command);
        if (previousBody !== null && previousBody !== body) key = requestId();
        previousBody = body;
        command.request_id = key;
        busy = true; button.disabled = true; output.textContent = "Enregistrement…";
        const controller = new AbortController();
        const timeout = setTimeout(() => controller.abort(), 15000);
        let response;
        try {
          response = await fetch("/api/v1/cultures", {method: "POST", headers: {"Content-Type": "application/json", "X-CSRF-Token": csrf}, body: JSON.stringify(command), signal: controller.signal});
        } finally { clearTimeout(timeout); }
        const result = await response.json().catch(() => ({error: "Requête refusée ; vérifier la connexion et actualiser le jeton si nécessaire."}));
        if (!response.ok) {
          if (response.status === 409) {
            output.textContent = `${result.error} Votre saisie reste dans ce formulaire. `;
            const link = document.createElement("a"); link.href = location.href; link.target = "_blank"; link.rel = "noopener"; link.textContent = "Ouvrir la fiche actualisée"; output.append(link);
            return;
          }
          throw new Error(result.error);
        }
        output.textContent = "Enregistré. Ouverture de la fiche…";
        location.assign(`/cultures/${encodeURIComponent(result.subject_id)}`);
      } catch (error) {
        output.textContent = error.name === "AbortError" || error instanceof TypeError ? "Réponse non reçue. Saisie conservée : réessayez sans la modifier pour vérifier le même enregistrement." : error.message;
      } finally { busy = false; button.disabled = false; }
    });
  });
})();
