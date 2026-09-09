(() => {
  "use strict";
  // Ce script est aussi chargé par le tableau de bord, où aucun formulaire du carnet
  // n'existe : le socle partagé n'y est pas nécessaire et son absence ne doit rien casser.
  const forms = window.PhytoCultureForms;
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

  // Aides éphémères : retirées à expiration, hors ligne, à l'échec et pendant l'actualisation.
  const assistance = document.querySelector("[data-culture-assistance]");
  if (assistance) {
    let generation = 0;
    let expiry;
    let lastRun = 0;
    // Deux requêtes ne peuvent pas se suivre à moins de 30 s : chaque appel coûte au
    // serveur une projection complète du carnet sur son thread unique, et une fiche laissée
    // ouverte occupait ce thread en continu.
    const MIN_INTERVAL_MS = 30000;
    // Version de fiche déjà affichée : le serveur s'en sert pour répondre « inchangé »
    // sans relire le carnet. Vider le panneau la rend caduque — il n'y a plus rien
    // d'affiché à confirmer.
    let shown = null;
    const clear = () => { generation++; shown = null; assistance.replaceChildren(); assistance.hidden = true; clearTimeout(expiry); };
    const refresh = async () => {
      if (!navigator.onLine || document.body.classList.contains("is-offline") || document.visibilityState === "hidden") return;
      lastRun = performance.now();
      const current = ++generation;
      const started = performance.now();
      const controller = new AbortController();
      const timeout = setTimeout(() => controller.abort(), 15000);
      try {
        const query = shown === null ? "" : `?version=${encodeURIComponent(shown)}`;
        const response = await fetch(`/api/v1/cultures/assistance/${encodeURIComponent(assistance.dataset.cultureAssistance)}${query}`, {cache: "no-store", signal: controller.signal});
        if (!response.ok) return;
        const data = await response.json();
        if (current !== generation || !navigator.onLine || document.body.classList.contains("is-offline")) return;
        const remaining = data.valid_for_seconds * 1000 - (performance.now() - started);
        if (remaining <= 0) return;
        // Fiche inchangée : le serveur n'a rien recalculé et le panneau affiché reste
        // exact. Seule sa validité repart, sans reconstruction ni clignotement.
        if (data.unchanged) { clearTimeout(expiry); expiry = setTimeout(clear, remaining); return; }
        // Les aides sont construites à part puis substituées d'un bloc : vider le panneau
        // avant d'avoir la réponse le faisait clignoter à chaque actualisation.
        const fresh = document.createDocumentFragment();
        const title = document.createElement("h2"); title.textContent = "Pour cette culture";
        fresh.append(title);
        for (const item of data.items) {
          const article = document.createElement("article"); article.className = "card";
          const h = document.createElement("h3"); h.textContent = `${item.category} · ${item.target}`;
          const p = document.createElement("p"); p.textContent = item.reason;
          const link = document.createElement("a"); link.href = item.href; link.textContent = item.action;
          const details = document.createElement("details");
          const summary = document.createElement("summary"); summary.textContent = "Source et validité";
          // Le jeton de fraîcheur du carnet est opaque : il sert au serveur, il ne se lit
          // pas. Ce qui s'affiche reste le fait daté et la validité de l'aide.
          const fact = document.createElement("p"); fact.textContent = `Fait daté du ${item.fact_date}. ${item.expires_when}`;
          details.append(summary, fact); article.append(h, p, link, details); fresh.append(article);
        }
        clearTimeout(expiry);
        assistance.replaceChildren(fresh);
        assistance.hidden = !data.items.length;
        shown = data.version ?? null;
        expiry = setTimeout(clear, remaining);
      } catch { if (current === generation) clear(); }
      finally { clearTimeout(timeout); }
    };
    // Plus d'intervalle : l'actualisation suit l'attention de l'opérateur — chargement,
    // retour sur l'onglet, retour de focus — et jamais plus d'une fois par 30 s.
    const schedule = () => {
      if (document.visibilityState === "hidden") return;
      if (performance.now() - lastRun < MIN_INTERVAL_MS) return;
      refresh();
    };
    refresh();
    addEventListener("focus", schedule); addEventListener("offline", clear);
    document.addEventListener("visibilitychange", schedule);
    new MutationObserver(() => { if (document.body.classList.contains("is-offline")) clear(); })
      .observe(document.body, {attributes: true, attributeFilter: ["class"]});
  }

  const stamp = (form, name) => {
    const input = form.elements[name];
    const value = input.value;
    const precision = form.elements[`${name}_precision`].value;
    return {value: precision === "instant" ? (input.dataset.renderedInstant === value ? input.dataset.instant : new Date(value).toISOString()) : value, precision};
  };
  // Le serveur numérote les poids par origine dans **la liste qu'il a reçue**, or celle-ci
  // est filtrée : les origines laissées vides n'y figurent pas. Sans cette table, un refus
  // sur le deuxième poids envoyé désignerait le deuxième champ de la page, qui peut être un
  // autre. `sent[i]` retient donc le rang DOM du contrôle à l'origine du i-ème envoi.
  const sentRanks = new WeakMap();
  const SENT_FIELDS = {origin_weight: "origin_weights"};
  const translate = (form, data) => {
    if (!data || !SENT_FIELDS[data.field] || typeof data.index !== "number") return data;
    const rank = sentRanks.get(form)?.[SENT_FIELDS[data.field]]?.[data.index];
    if (rank !== undefined) return {...data, index: rank};
    // Aucune ligne de la page ne correspond au rang refusé : marquer la n-ième de la page
    // désignerait un champ que l'opérateur n'a pas saisi. Le message reste alors global.
    const {field: _field, index: _index, ...rest} = data;
    return rest;
  };

  // Refus côté client : il désigne le champ fautif exactement comme un refus du serveur.
  const invalid = (message, field, index) => Object.assign(new Error(message), {field, index});
  const refuse = (form, error) => forms.showError(form, {error: error.message, field: error.field, index: error.index});

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
      if (weight !== null && !Number.isFinite(weight)) throw invalid("Poids sec invalide.", "weight_g");
      const ranks = [];
      const weights = [];
      Array.from(form.querySelectorAll("[data-origin-weight]")).forEach((input, rank) => {
        if (!input.value.trim()) return;
        const value = Number(input.value.replace(",", "."));
        if (!Number.isFinite(value)) throw invalid("Poids par origine invalide.", "origin_weight", rank);
        ranks.push(rank);
        weights.push({origin_id: input.dataset.originWeight, weight_g: value});
      });
      sentRanks.set(form, {origin_weights: ranks});
      Object.assign(data, {weight_g: weight, release: form.elements.release.checked, lessons: get("lessons"),
        origin_weights: weights});
    }
    return data;
  };

  // Un conflit de version n'est pas une faute de saisie : la saisie reste dans le
  // formulaire et l'opérateur ouvre la fiche à jour dans un autre onglet.
  // Le refus passe par le résumé d'erreur comme tous les autres : `status()` écrit dans la
  // zone d'état, que le socle vide au refus suivant, et le conflit y serait le seul message
  // que le formulaire n'annonce pas.
  const showConflict = (form, message) => {
    const summary = forms.showError(form, {error: `${message} Votre saisie reste dans ce formulaire.`});
    if (!summary) return;
    const link = document.createElement("a");
    link.href = location.href; link.target = "_blank"; link.rel = "noopener";
    link.textContent = "Ouvrir la fiche actualisée";
    (summary.querySelector("li:last-of-type") || summary).append(" ", link);
  };

  // Destination après un enregistrement : l'entrée créée quand le serveur la nomme,
  // la fiche seule sinon (création, reprise, étape passée n'en désignent aucune).
  // Quand seule l'ancre change, `assign` ne recharge rien : la fiche resterait celle
  // d'avant l'enregistrement, avec la nouvelle entrée absente et les compteurs périmés.
  // `anchor` prime sur l'entrée créée : après une transition guidée, ce qu'il faut lire en
  // premier n'est pas la ligne ajoutée au journal mais les vérifications du nouveau stade.
  // L'élément focalisé reste la confirmation, il change seulement de place.
  const openEntry = (subjectId, eventId, anchor) => {
    const target = new URL(`/cultures/${encodeURIComponent(subjectId)}`, location.href);
    if (anchor) target.hash = anchor;
    else if (eventId) target.hash = `event-${encodeURIComponent(eventId)}`;
    if (target.pathname === location.pathname && target.search === location.search) {
      location.hash = target.hash;
      location.reload();
    } else {
      location.assign(target.href);
    }
  };

  document.querySelectorAll("[data-culture-create], [data-culture-event], [data-culture-correct], [data-culture-backfill]").forEach(form => {
    forms.register(form);
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
    // Stades acceptés et premier stade du parcours : lus sur le formulaire, jamais
    // recalculés ici. Le serveur les a rendus par type d'origine (`data-stages-*`,
    // `data-first-stage-*`) depuis les règles pures ; ce script ne fait que masquer ce qui
    // n'appartient pas au type choisi. Dupliquer la règle « semis / bouture » dans le
    // navigateur, comme auparavant, c'était deux vérités à maintenir.
    const creationSpec = () => {
      const type = form.elements.origin_type?.value || form.dataset.kind || "";
      const suffix = type.charAt(0).toUpperCase() + type.slice(1);
      return {stages: (form.dataset[`stages${suffix}`] || "").split(",").filter(Boolean),
              first: form.dataset[`firstStage${suffix}`] || form.dataset.firstStage || ""};
    };
    const syncOrigins = () => {
      const cutting = form.elements.origin_type?.value === "cutting";
      form.querySelectorAll("[data-seed]").forEach(el => { el.hidden = cutting; el.querySelector("input").required = !cutting; });
      form.querySelectorAll("[data-cutting]").forEach(el => { el.hidden = !cutting; el.querySelector("select").required = cutting; });
      const stage = form.elements.stage;
      if (stage && form.dataset.firstStage) {
        const spec = creationSpec();
        for (const option of stage.options) {
          option.disabled = !spec.stages.includes(option.value);
          option.hidden = option.disabled;
        }
        if (stage.selectedOptions[0]?.disabled && spec.first) stage.value = spec.first;
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
      // La ligne modèle peut porter un refus : le clone hériterait de son message, de son
      // identifiant et de son marquage. Une ligne neuve est une ligne vierge.
      forms.resetField(row);
      row.querySelectorAll("[id]").forEach(node => { if (node.dataset.cfGenerated === "1") { delete node.dataset.cfGenerated; node.removeAttribute("id"); } });
      list.append(row); syncOrigins();
      // Les contrôles clonés n'ont pas encore d'identifiant : sans ce rappel, une erreur
      // portant sur la deuxième origine ne trouverait aucun champ à désigner.
      forms.register(form);
    });
    form.addEventListener("click", event => {
      if (event.target.closest("[data-remove-origin]") && form.querySelectorAll(".culture-origin").length > 1) {
        event.target.closest(".culture-origin").remove();
      }
    });
    syncOrigins();

    // --- Création : « Je démarre une culture » ou « Elle est déjà en cours » ---
    // Le formulaire complet reste la vérité : sans script tout est visible et la saisie est
    // celle d'avant. Le mode « Je démarre » ne fait que replier ce qu'une seule date suffit
    // à déduire — le premier stade du parcours, sa date et celle de l'entrée dans l'espace.
    // Rien n'est inventé : une date d'origine vide recopie du vide.
    if (form.hasAttribute("data-culture-create")) {
      const summary = form.querySelector("[data-creation-summary]");
      const derived = ["[data-creation-stage]", "[data-creation-stage-date]",
                       "[data-creation-space-date]", "[data-creation-note]"]
        .map(selector => form.querySelector(selector)).filter(Boolean);
      const starting = () => form.elements.situation?.value === "new";

      // Libellés de la frise : ceux des <option> rendues par le serveur, jamais une table
      // de correspondance recopiée ici.
      const optionLabel = (control) => control?.selectedOptions?.[0]?.textContent.trim() || "";
      const dateText = (name) => {
        const raw = form.elements[name]?.value || "";
        if (!raw) return "date non renseignée";
        const shown = raw.length === 10 ? raw.split("-").reverse().join("/") : new Date(raw).toLocaleString("fr-FR");
        const precision = optionLabel(form.elements[`${name}_precision`]);
        return precision ? `${shown} (${precision.toLowerCase()})` : shown;
      };
      // Ordre de la frise = ordre du formulaire. Un stade daté avant l'origine s'y lit tel
      // quel : réordonner en silence cacherait précisément la saisie à corriger.
      const buildSummary = () => {
        if (!summary) return;
        const lines = [`Origine — ${dateText("origin_at")}`,
                       `${optionLabel(form.elements.stage) || "Stade"} — ${dateText("stage_at")}`,
                       `${optionLabel(form.elements.space) || "Espace"} — ${dateText("space_at")}`];
        const rows = Array.from(form.querySelectorAll(".culture-origin"));
        if (rows.length) {
          const cutting = form.elements.origin_type?.value === "cutting";
          let total = 0;
          const origins = rows.map(row => {
            const count = Number(row.querySelector('[name="origin_count"]')?.value || 0);
            if (Number.isFinite(count)) total += count;
            // « semis » est invariable ; « bouture » s'accorde.
            const noun = cutting ? (count > 1 ? "boutures" : "bouture") : "semis";
            const mother = row.querySelector('[name="mother_id"]');
            const label = cutting
              ? (mother?.value ? optionLabel(mother) : "")
              : (row.querySelector('[name="origin_label"]')?.value.trim() || "");
            return label ? `${count} ${noun} · ${label}` : `${count} ${noun}, origine non renseignée`;
          });
          lines.push(`Effectif total — ${total} plante${total > 1 ? "s" : ""}`, ...origins);
        }
        summary.replaceChildren(...lines.map(text => {
          const item = document.createElement("li");
          item.textContent = text;
          return item;
        }));
        // La section est rendue masquée : son titre ne doit apparaître qu'avec la frise.
        summary.closest(".culture-creation-summary")?.removeAttribute("hidden");
      };
      // Recopie de la date d'origine : uniquement en mode « Je démarre », précision et type
      // de champ compris, pour que la reprise ne se retrouve jamais avec une date déduite.
      const copyOrigin = () => {
        if (!starting()) return;
        const origin = form.elements.origin_at, originPrecision = form.elements.origin_at_precision;
        for (const name of ["stage_at", "space_at"]) {
          const target = form.elements[name], precision = form.elements[`${name}_precision`];
          if (!target || !origin) continue;
          if (precision && originPrecision) {
            precision.value = originPrecision.value;
            target.type = precision.value === "instant" ? "datetime-local" : "date";
          }
          target.value = origin.value;
        }
      };
      const applyMode = () => {
        const start = starting();
        for (const block of derived) block.hidden = start;
        const stage = form.elements.stage, first = creationSpec().first;
        if (start && stage && first) stage.value = first;
        copyOrigin();
        buildSummary();
      };
      form.querySelectorAll('[name="situation"]').forEach(radio => radio.addEventListener("change", applyMode));
      form.elements.origin_at?.addEventListener("input", copyOrigin);
      form.elements.origin_at_precision?.addEventListener("change", copyOrigin);
      form.addEventListener("input", buildSummary);
      form.addEventListener("change", buildSummary);
      // Ajout ou retrait d'une origine : leurs gestionnaires sont enregistrés plus haut, la
      // frise se reconstruit donc sur un formulaire déjà à jour.
      form.addEventListener("click", buildSummary);
      applyMode();
    }

    form.addEventListener("submit", async event => {
      event.preventDefault();
      let command;
      try {
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
        } else if (form.hasAttribute("data-culture-backfill")) {
          // Une étape passée est un événement daté avant le stade courant : elle ne le remplace pas.
          const effective = stamp(form, "effective_at");
          const mode = form.dataset.mode;
          command = {operation: "backfill", subject_id: form.dataset.subject, version: Number(form.dataset.version),
            steps: [{kind: mode, effective_at: effective.value, precision: effective.precision,
              payload: mode === "stage" ? {stage: form.elements.stage.value} : {space: form.elements.space.value},
              reason: form.elements.reason.value}]};
        } else {
          const effective = stamp(form, "effective_at");
          command = {operation: form.hasAttribute("data-culture-correct") ? "correct" : "event",
            subject_id: form.dataset.subject, version: Number(form.dataset.version), kind: form.dataset.kind,
            effective_at: effective.value, precision: effective.precision, payload: payload(form)};
          if (command.operation === "correct") Object.assign(command, {event_id: form.dataset.event,
            cancelled: form.elements.cancelled?.checked || false, reason: form.elements.reason.value});
        }
        command.confirm_date = form.elements.confirm_date?.checked || false;
      } catch (error) {
        refuse(form, error);
        return;
      }
      // Transition guidée : le marquage vient du serveur (`data-guided`, règle pure
      // `fiche_actions`). Le socle demande alors la vérification et n'écrit qu'ensuite.
      const guided = form.hasAttribute("data-guided");
      forms.status(form, "Enregistrement…");
      const result = await forms.submitJson(form, "/api/v1/cultures", command,
        guided ? {guided: true} : {});
      if (result.offline || result.busy || result.preview) return;
      if (!result.ok) {
        if (result.status === 409) showConflict(form, result.data.error);
        else forms.showError(form, translate(form, result.data));
        return;
      }
      forms.status(form, "Enregistré. Ouverture de la fiche…");
      openEntry(result.data.subject_id, result.data.event_id, guided ? "verifications" : null);
    });
  });

  // --- Observation et photo en un seul parcours -----------------------------
  // Deux requêtes séquentielles : l'observation d'abord, la photo ensuite et
  // seulement si l'entrée existe. Un refus de photo ne peut donc jamais effacer une
  // observation déjà enregistrée ; il ne reste plus qu'à réessayer la photo.
  document.querySelectorAll("[data-culture-observation]").forEach(form => {
    forms.register(form);
    const file = form.elements.photo;
    const preview = form.querySelector("[data-observation-preview]");
    const button = form.querySelector('[type="submit"]');
    let objectUrl = null;
    const clearPreview = () => {
      if (objectUrl) { URL.revokeObjectURL(objectUrl); objectUrl = null; }
      preview.replaceChildren();
      preview.hidden = true;
    };
    file?.addEventListener("change", () => {
      clearPreview();
      const chosen = file.files[0];
      if (!chosen) return;
      objectUrl = URL.createObjectURL(chosen);
      const image = document.createElement("img");
      image.src = objectUrl;
      image.alt = "Aperçu local de la photo choisie, avant tout envoi.";
      preview.append(image);
      preview.hidden = false;
    });
    const lockObservation = (retry) => {
      for (const name of ["note", "effective_at", "effective_at_precision"]) {
        const control = form.elements[name];
        if (control) control.disabled = true;
      }
      if (retry) { button.textContent = "Réessayer la photo"; return; }
      // Conflit de révision : réessayer avec la même révision mémorisée ne peut donner qu'un
      // second refus. L'entrée, elle, existe : la photo s'ajoute depuis la fiche rechargée.
      const link = document.createElement("a");
      link.className = button.className;
      link.href = `/cultures/${encodeURIComponent(form.dataset.subject)}#event-${encodeURIComponent(form.dataset.eventId)}`;
      link.textContent = "Recharger la fiche";
      button.replaceWith(link);
    };
    const sendPhoto = async (chosen) => {
      forms.status(form, "Envoi de la photo…");
      const result = await forms.submitBinary(form, "/api/v1/cultures/photos", chosen, {
        subject_id: form.dataset.subject, event_id: form.dataset.eventId,
        event_revision: Number(form.dataset.eventRevision),
        caption: form.elements.caption?.value || "",
        confirm_date: form.elements.confirm_date?.checked || false});
      if (result.offline || result.busy || result.preview) {
        // L'observation, elle, est enregistrée : annoncer « aucun envoi mis en attente »
        // sans le dire contredirait l'état réel du carnet.
        forms.showError(form, {error: "Note enregistrée. Photo non envoyée : réessayer quand le réseau revient."});
        return false;
      }
      if (!result.ok) {
        const conflict = result.status === 409;
        lockObservation(!conflict);
        forms.showError(form, {error: conflict
          ? "L’observation est enregistrée ; la fiche a changé entre-temps : rechargez-la puis ajoutez la photo depuis l’entrée."
          : `L’observation est enregistrée ; la photo n’a pas été acceptée : ${result.data.error}`});
        return false;
      }
      return true;
    };
    form.addEventListener("submit", async event => {
      event.preventDefault();
      const chosen = file?.files[0] || null;
      if (chosen && chosen.size > 5 * 1024 * 1024) {
        forms.showError(form, {error: "Choisir une photo de 5 Mio maximum.", field: "photo"});
        return;
      }
      // Reprise après un refus de photo : l'entrée existe déjà, seule la photo repart.
      if (form.dataset.eventId) {
        if (!chosen) {
          forms.showError(form, {error: "Choisir une photo à envoyer, ou recharger la fiche.", field: "photo"});
          return;
        }
        if (await sendPhoto(chosen)) openEntry(form.dataset.subject, form.dataset.eventId);
        return;
      }
      let effective;
      try {
        effective = stamp(form, "effective_at");
      } catch (error) {
        refuse(form, error);
        return;
      }
      forms.status(form, "Enregistrement de l’observation…");
      const result = await forms.submitJson(form, "/api/v1/cultures", {
        operation: "event", subject_id: form.dataset.subject, version: Number(form.dataset.version),
        kind: "note", effective_at: effective.value, precision: effective.precision,
        payload: {note: form.elements.note.value},
        confirm_date: form.elements.confirm_date?.checked || false});
      if (result.offline || result.busy || result.preview) return;
      if (!result.ok) {
        if (result.status === 409) showConflict(form, result.data.error);
        else forms.showError(form, result.data);
        return;
      }
      const saved = result.data;
      // Sans identifiant d'entrée, aucune ancre honnête et aucune photo rattachable.
      if (!saved.event_id) { openEntry(saved.subject_id, null); return; }
      form.dataset.eventId = saved.event_id;
      form.dataset.eventRevision = saved.event_revision;
      // L'entrée existe : la note ne peut plus être réécrite depuis ce formulaire, et cela
      // vaut avant l'envoi de la photo — un échec hors ligne n'y changerait rien.
      if (chosen) {
        lockObservation(true);
        if (!(await sendPhoto(chosen))) return;
      }
      clearPreview();
      openEntry(saved.subject_id, saved.event_id);
    });
  });

  // --- Accueil : filtre local de la liste ----------------------------------
  // Le pliage de la zone de report des rappels vit désormais dans `culture_cycles.js`, qui
  // porte déjà l'envoi de ces formulaires et que les deux pages concernées chargent :
  // l'accueil et la page des cycles ont la même carte de rappel, elles n'en ont qu'un seul
  // comportement.

  const searchBlock = document.querySelector("[data-culture-search-block]");
  const search = document.querySelector("[data-culture-search]");
  if (searchBlock && search) {
    // Raffinement local des cartes déjà rendues, en plus de la recherche serveur portée par
    // le formulaire lui-même : aucune requête à la frappe, et la soumission reste ce qui va
    // chercher au-delà de la page courante.
    const cards = Array.from(document.querySelectorAll("[data-culture-item]"));
    const count = document.querySelector("[data-culture-search-count]");
    search.addEventListener("input", () => {
      const needle = search.value.trim().toLowerCase();
      let shown = 0;
      for (const card of cards) {
        const match = !needle || card.dataset.cultureItem.toLowerCase().includes(needle);
        card.hidden = !match;
        if (match) shown += 1;
      }
      count.textContent = needle ? `${shown} culture(s) affichée(s) sur ${cards.length} de cette page.` : "";
    });
  }

  // --- Retour sur l'entrée ou le rappel visé --------------------------------
  // L'élément focalisé est la confirmation : pas d'annonce supplémentaire, mais ses
  // replis sont ouverts pour qu'il ne reçoive jamais le focus en restant invisible.
  // Le dévoilement est celui du socle (`reveal`) : replis `<details>` et conteneurs
  // `data-cf-collapsible` seulement. Ouvrir tout ancêtre `hidden` faisait apparaître un
  // bloc qu'une règle de page avait retiré de la saisie — type d'origine, mode « Je
  // démarre » —, sans jamais le refermer.
  const focusTarget = () => {
    const id = decodeURIComponent(location.hash.slice(1));
    if (!id) return;
    const target = document.getElementById(id);
    if (!target || target.tabIndex !== -1) return;
    forms?.reveal(target);
    target.querySelector(":scope > .culture-added")?.removeAttribute("hidden");
    target.focus({preventScroll: true});
    target.scrollIntoView({block: "center"});
  };
  focusTarget();
  window.addEventListener("hashchange", focusTarget);
})();
