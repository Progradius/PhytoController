(() => {
  "use strict";
  // Socle commun des formulaires du carnet de cultures : identifiants stables, envoi
  // JSON ou binaire avec les mêmes gardes qu'auparavant, et restitution des refus au
  // champ concerné. Ce module ne commande aucun équipement, n'écrit aucune
  // configuration et ne met aucune mutation en attente hors ligne.
  const OFFLINE = "Hors ligne : saisie conservée dans cette page, aucun envoi mis en attente.";
  const NO_ANSWER = "Réponse non reçue. Saisie conservée : réessayez sans la modifier pour vérifier le même enregistrement.";
  const REFUSED = "Requête refusée ; vérifier la connexion et actualiser le jeton si nécessaire.";
  const BUSY = "Un envoi est déjà en cours pour ce formulaire.";
  const SUMMARY_TITLE = "La saisie n’a pas été enregistrée.";

  let counter = 0;
  const bound = new WeakSet();   // contrôles dont l'effacement à la saisie est déjà branché
  const busy = new WeakSet();    // formulaires dont un envoi est en vol
  const reviewOnly = new WeakMap();
  const reviews = new WeakMap();
  const keys = new WeakMap();    // formulaire → {signature, value} de la clé d'idempotence

  const csrf = () => document.querySelector('meta[name="csrf-token"]')?.content;
  const isOffline = () => !navigator.onLine || document.body.classList.contains("is-offline");
  const identifier = () =>
    Array.from(crypto.getRandomValues(new Uint8Array(20)), n => n.toString(16).padStart(2, "0")).join("");

  const outputOf = form => form.querySelector("output");
  const prefixOf = form => form.dataset.formKey || "";
  const sanitize = name => String(name).replace(/[^A-Za-z0-9_-]/g, "-");

  const controlsOf = form =>
    Array.from(form.elements).filter(
      el => el.name && ["INPUT", "SELECT", "TEXTAREA"].includes(el.tagName)
    );

  // --- Identifiants -------------------------------------------------------

  // Les formulaires du carnet sont répétés (une entrée par ligne) et clonés (origines) :
  // l'identifiant porte donc le rang du formulaire dans la page, puis le rang du contrôle
  // parmi ceux qui partagent son `name`. Un `id` posé par le gabarit n'est jamais écrasé ;
  // seuls ceux que ce module a générés (marqués dans le jeu de données) sont recalculés,
  // ce qui rend `register` rejouable après un clonage.
  function register(form) {
    if (!form || form.tagName !== "FORM") return form;
    if (!form.dataset.formKey) form.dataset.formKey = `cf-${++counter}`;
    if (!form.dataset.cfReview && form.matches("[data-culture-create], [data-culture-event], [data-culture-correct], [data-culture-backfill], .solution-form")) {
      form.dataset.cfReview = "1";
      const button = document.createElement("button");
      button.type = "button";
      button.className = "button button-secondary";
      button.textContent = "Vérifier avant d’enregistrer";
      form.querySelector('[type="submit"]')?.after(button);
      let verifying = false;
      button.addEventListener("click", () => {
        verifying = true;
        try { form.requestSubmit(); } finally { verifying = false; }
      });
      form.addEventListener("submit", () => reviewOnly.set(form, verifying), true);
      const invalidate = () => {
        reviews.delete(form);
        form.querySelector(".culture-review")?.remove();
      };
      form.addEventListener("input", invalidate);
      form.addEventListener("change", invalidate);
    }
    const prefix = form.dataset.formKey;
    const list = controlsOf(form);
    const totals = new Map();
    for (const control of list) totals.set(control.name, (totals.get(control.name) || 0) + 1);
    const ranks = new Map();
    for (const control of list) {
      const rank = ranks.get(control.name) || 0;
      ranks.set(control.name, rank + 1);
      if (!control.id || control.dataset.cfGenerated === "1") {
        const base = `${prefix}-${sanitize(control.name)}`;
        control.id = totals.get(control.name) > 1 ? `${base}-${rank}` : base;
        control.dataset.cfGenerated = "1";
      }
      if (!bound.has(control)) {
        bound.add(control);
        const clear = () => clearField(control);
        control.addEventListener("input", clear);
        control.addEventListener("change", clear);
      }
    }
    return form;
  }

  // Le serveur nomme le champ par son attribut `name` et, pour les groupes répétés,
  // par son rang. L'identifiant suffixé est cherché en premier, puis le simple :
  // un `index` sur un champ unique reste résolu.
  function locate(form, field, index) {
    if (!field) return null;
    const prefix = prefixOf(form);
    if (!prefix) return null;
    const base = `${prefix}-${sanitize(field)}`;
    const candidates = index === undefined || index === null
      ? [base, `${base}-0`]
      : [`${base}-${index}`, base];
    for (const id of candidates) {
      const control = form.querySelector(`#${CSS.escape(id)}`);
      if (control) return control;
    }
    return null;
  }

  // --- Erreurs ------------------------------------------------------------

  const labelOf = control => {
    const label = control.closest("label");
    return label && label.contains(control) ? label : null;
  };

  function mark(control, message) {
    const label = labelOf(control);
    const errorId = `${control.id}-error`;
    let note = document.getElementById(errorId);
    if (!note) {
      // Le message va **dans** le <label> enveloppant, en dernier : posé après lui, il
      // deviendrait une cellule de plus dans une grille de champs et se retrouverait à côté
      // du champ refusé au lieu de rester sous lui. Un <span> parce qu'un <p> est interdit
      // dans un <label>. `unmark`/`clearField` le retrouvent par son identifiant.
      note = document.createElement(label ? "span" : "p");
      note.className = "field-error";
      note.id = errorId;
      if (label) label.append(note);
      else control.after(note);
    }
    // Jamais d'injection : le message du serveur reste du texte.
    note.textContent = message;
    control.setAttribute("aria-invalid", "true");
    if (control.dataset.describedbyBase === undefined) {
      control.dataset.describedbyBase = control.getAttribute("aria-describedby") || "";
    }
    const base = control.dataset.describedbyBase;
    control.setAttribute("aria-describedby", base ? `${base} ${errorId}` : errorId);
    label?.classList.add("field-invalid");
  }

  function unmark(control) {
    document.getElementById(`${control.id}-error`)?.remove();
    control.removeAttribute("aria-invalid");
    const base = control.dataset.describedbyBase;
    if (base) control.setAttribute("aria-describedby", base);
    else control.removeAttribute("aria-describedby");
    delete control.dataset.describedbyBase;
    labelOf(control)?.classList.remove("field-invalid");
  }

  // L'effacement d'un champ conserve le résumé tant qu'un autre champ reste refusé :
  // seule l'entrée correspondante en disparaît.
  function clearField(control) {
    if (!control || !control.hasAttribute("aria-invalid")) return;
    const id = control.id;
    const form = control.form;
    unmark(control);
    const summary = form?.querySelector(".culture-form-errors");
    if (!summary) return;
    summary.querySelector(`a[href="#${CSS.escape(id)}"]`)?.closest("li")?.remove();
    if (!summary.querySelector("li")) summary.remove();
  }

  function clearErrors(form) {
    if (!form) return;
    form.querySelector(".culture-form-errors")?.remove();
    for (const control of controlsOf(form)) {
      if (control.hasAttribute("aria-invalid")) unmark(control);
    }
  }

  // Un champ refusé peut se trouver dans un repli ou une section masquée : on l'ouvre
  // avant de le viser, sans quoi le focus se poserait sur un élément invisible.
  function reveal(element) {
    for (let node = element; node && node !== document.body; node = node.parentElement) {
      if (node.tagName === "DETAILS") node.open = true;
      if (node.hasAttribute("hidden")) node.hidden = false;
    }
  }

  function focusOn(element) {
    reveal(element);
    element.focus({preventScroll: true});
    element.scrollIntoView({block: "center"});
  }

  function showErrors(form, errors) {
    if (!form) return null;
    register(form);
    clearErrors(form);
    const items = (Array.isArray(errors) ? errors : [errors]).filter(Boolean);
    if (!items.length) return null;

    const summary = document.createElement("div");
    summary.className = "notice error culture-form-errors";
    summary.setAttribute("role", "alert");
    summary.tabIndex = -1;
    summary.id = `${prefixOf(form)}-errors`;
    const title = document.createElement("h3");
    title.textContent = SUMMARY_TITLE;
    const list = document.createElement("ul");
    summary.append(title, list);

    let first = null;
    for (const item of items) {
      const message = String(item?.error || REFUSED);
      const control = locate(form, item?.field, item?.index);
      const row = document.createElement("li");
      if (control) {
        mark(control, message);
        const link = document.createElement("a");
        link.href = `#${control.id}`;
        link.textContent = message;
        link.addEventListener("click", event => {
          event.preventDefault();
          focusOn(control);
        });
        row.append(link);
        if (!first) first = control;
      } else {
        // Champ inconnu (refus global, conflit, service indisponible) : message sans lien mort.
        row.textContent = message;
      }
      list.append(row);
    }

    form.prepend(summary);
    // Le résumé porte l'annonce : la zone d'état du formulaire est vidée pour ne pas
    // laisser deux messages concurrents.
    const output = outputOf(form);
    if (output) output.textContent = "";
    focusOn(first || summary);
    return summary;
  }

  const showError = (form, error) => showErrors(form, [error]);

  function status(form, text) {
    if (!form) return;
    form.querySelector(".culture-form-errors")?.remove();
    const output = outputOf(form);
    if (output) output.textContent = text === undefined || text === null ? "" : String(text);
  }

  // --- Envois -------------------------------------------------------------

  const submitButton = form => form.querySelector('[type="submit"]');

  // La clé d'idempotence est conservée tant que la saisie ne change pas : un même envoi
  // rejoué après une réponse perdue vérifie l'enregistrement au lieu d'en créer un
  // second. `crypto.randomUUID` n'existe pas hors contexte sécurisé (LAN en HTTP).
  function requestKey(form, signature) {
    const memo = keys.get(form);
    if (!memo || memo.signature !== signature) {
      const fresh = {signature, value: identifier()};
      keys.set(form, fresh);
      return fresh.value;
    }
    return memo.value;
  }

  async function send(form, url, {headers, body, timeoutMs}) {
    if (isOffline()) {
      status(form, OFFLINE);
      return {ok: false, status: 0, data: {error: OFFLINE}, aborted: false, offline: true};
    }
    if (busy.has(form)) {
      return {ok: false, status: 0, data: {error: BUSY}, aborted: false, busy: true};
    }
    busy.add(form);
    const button = submitButton(form);
    if (button) button.disabled = true;
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), timeoutMs);
    try {
      const response = await fetch(url, {
        method: "POST",
        headers: {"X-CSRF-Token": csrf(), ...headers},
        body,
        signal: controller.signal,
      });
      const data = await response.json().catch(() => ({error: REFUSED}));
      return {ok: response.ok, status: response.status, data, aborted: false};
    } catch (error) {
      const aborted = error.name === "AbortError";
      if (!aborted && !(error instanceof TypeError)) {
        return {ok: false, status: 0, data: {error: error.message}, aborted: false};
      }
      return {ok: false, status: 0, data: {error: NO_ANSWER}, aborted};
    } finally {
      clearTimeout(timer);
      busy.delete(form);
      if (button) button.disabled = false;
    }
  }

  async function submitJson(form, url, body, options = {}) {
    register(form);
    const command = {...body};
    let changed = false;
    const change = () => { changed = true; };
    const signature = JSON.stringify(command);
    command.request_id = requestKey(form, signature);
    const domain = url === "/api/v1/cultures" ? "culture" : url === "/api/v1/cultures/solutions" ? "solution" : null;
    if (domain) {
      form.addEventListener("input", change);
      form.addEventListener("change", change);
      const checked = await send(form, `/api/v1/cultures/preview/${domain}`, {
        headers: {"Content-Type": "application/json"}, body: JSON.stringify(command),
        timeoutMs: options.timeoutMs ?? 15000,
      });
      form.removeEventListener("input", change);
      form.removeEventListener("change", change);
      if (changed) {
        status(form, "Saisie modifiée pendant la vérification : vérifiez à nouveau avant d’enregistrer.");
        return {ok: false, preview: true};
      }
      if (!checked.ok) return checked;
      if (isOffline()) {
        status(form, OFFLINE);
        return {ok: false, offline: true};
      }
      // Une réponse tardive ne peut qualifier une saisie modifiée pendant la requête.
      // Les événements de saisie invalident également toute confirmation précédente.
      const previous = reviews.get(form);
      const matches = JSON.stringify(checked.data.similar || []);
      const acknowledged = previous?.signature === signature && previous?.matches === matches && previous?.confirmed;
      if (reviewOnly.get(form) || (checked.data.similar?.length && !acknowledged)) {
        form.querySelector(".culture-review")?.remove();
        const panel = document.createElement("section");
        panel.className = "notice culture-review";
        panel.tabIndex = -1;
        const title = document.createElement("h3");
        title.textContent = "Vérification avant enregistrement";
        panel.append(title);
        for (const line of checked.data.summary || []) {
          const p = document.createElement("p"); p.textContent = line; panel.append(p);
        }
        const memo = {signature, matches, confirmed: false};
        reviews.set(form, memo);
        if (checked.data.similar?.length) {
          const explanation = document.createElement("p");
          explanation.textContent = `Saisie ressemblante : vérifiez les entrées ci-dessous. ${checked.data.similar_scope} Une ressemblance ne prouve pas un doublon.`;
          panel.append(explanation);
          for (const entry of checked.data.similar) {
            const link = document.createElement("a");
            link.href = `/cultures/solutions?entry=${encodeURIComponent(entry.id)}#entry-${encodeURIComponent(entry.id)}`;
            link.target = "_blank"; link.rel = "noopener";
            link.textContent = `${entry.effective_at} · pH ${entry.ph ?? "—"} · EC ${entry.ec ?? "—"} mS/cm`;
            const p = document.createElement("p"); p.append(link); panel.append(p);
          }
          const label = document.createElement("label"); label.className = "culture-confirm";
          const check = document.createElement("input"); check.type = "checkbox";
          // Ce choix n'est pas une donnée métier et n'invalide pas le formulaire.
          for (const event of ["input", "change"]) check.addEventListener(event, e => e.stopPropagation());
          check.addEventListener("change", () => { memo.confirmed = check.checked; });
          label.append(check, " Je confirme qu’il s’agit d’un autre relevé."); panel.append(label);
        }
        const note = document.createElement("p");
        note.textContent = "Rien n’est enregistré. Utilisez le bouton d’enregistrement pour confirmer ; le serveur vérifiera à nouveau le carnet.";
        panel.append(note); form.prepend(panel); status(form, ""); focusOn(panel);
        setTimeout(() => {
          if (reviews.get(form) !== memo) return;
          reviews.delete(form); panel.remove();
          status(form, "Vérification expirée : vérifiez à nouveau les données du carnet avant d’enregistrer.");
        }, 30000);
        reviewOnly.delete(form);
        return {ok: false, preview: true};
      }
    }
    return send(form, url, {
      headers: {"Content-Type": "application/json"},
      body: JSON.stringify(command),
      timeoutMs: options.timeoutMs ?? 15000,
    });
  }

  async function submitBinary(form, url, blob, metadata, options = {}) {
    register(form);
    const command = {...metadata};
    // L'identité du fichier fait partie de la saisie : une autre photo est un autre envoi.
    const signature =
      JSON.stringify(command) + `|${blob?.name || ""}:${blob?.size || 0}:${blob?.lastModified || 0}`;
    command.request_id = requestKey(form, signature);
    return send(form, url, {
      headers: {
        "Content-Type": "application/octet-stream",
        "X-Culture-Metadata": encodeURIComponent(JSON.stringify(command)),
      },
      body: blob,
      timeoutMs: options.timeoutMs ?? 45000,
    });
  }

  const clearReviews = () => {
    document.querySelectorAll(".culture-review").forEach(panel => {
      const form = panel.closest("form");
      reviews.delete(form); panel.remove();
    });
  };
  addEventListener("offline", clearReviews);
  new MutationObserver(() => { if (isOffline()) clearReviews(); })
    .observe(document.body, {attributes: true, attributeFilter: ["class"]});

  window.PhytoCultureForms = {
    register,
    submitJson,
    submitBinary,
    showError,
    showErrors,
    clearErrors,
    clearField,
    status,
  };
})();
