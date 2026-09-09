(() => {
  "use strict";
  const forms = window.PhytoCultureForms;
  const params = new URLSearchParams(location.search);
  // La saisie s'ouvre sur l'ancre habituelle et sur une intention choisie en tête de page.
  const openEntry = () => {
    if (location.hash === "#saisie" || params.has("kind")) document.querySelector("#saisie")?.setAttribute("open", "");
  };
  addEventListener("hashchange", openEntry);
  openEntry();
  // Retour sur une entrée : l'élément visé porte le focus, il est la confirmation.
  const focusHash = () => {
    if (!location.hash || location.hash === "#saisie") return;
    let node = null;
    try { node = document.getElementById(decodeURIComponent(location.hash.slice(1))); } catch { node = null; }
    if (!node || node.tabIndex !== -1) return;
    for (let parent = node.parentElement; parent && parent !== document.body; parent = parent.parentElement) {
      if (parent.tagName === "DETAILS") parent.open = true;
    }
    node.focus({preventScroll: true});
    node.scrollIntoView({block: "center"});
  };
  focusHash();
  // Refus attribuable à un champ : le socle le relie au contrôle nommé par le serveur.
  const invalid = (message, field, index) => Object.assign(new Error(message), {field, index});
  const decimal = (value, field, index) => {
    if (!value.trim()) return null;
    const result = Number(value.replace(",", "."));
    if (!Number.isFinite(result)) throw invalid("Nombre invalide ; la virgule décimale est acceptée.", field, index);
    return result;
  };
  document.querySelectorAll("[data-solution-offset]").forEach(link => {
    const query = new URLSearchParams(params); query.set("offset", link.dataset.solutionOffset); link.search = query.toString();
  });
  const exportLink = document.querySelector("[data-solution-export]");
  if (exportLink) { const query = new URLSearchParams(params); query.delete("offset"); exportLink.search = query.toString(); }
  document.querySelectorAll("[data-measure-age]").forEach(el => {
    const days = Math.max(0, Math.floor((Date.now() - Date.parse(el.dataset.measureAge)) / 86400000));
    el.textContent = `· il y a environ ${days} jour(s)`;
  });
  document.querySelectorAll(".solution-form").forEach(form => {
    forms.register(form);
    const get = name => form.elements[name]?.value || "";
    // Le serveur numérote les ingrédients dans **la liste qu'il a reçue**, filtrée des lignes
    // vides : `sentProducts[i]` retient le rang DOM de la ligne à l'origine du i-ème envoi.
    // Sans cette table, un refus sur le deuxième produit envoyé désignerait le deuxième
    // produit de la page, qui peut en être un autre. Les refus locaux, eux, portent déjà le
    // rang DOM et n'ont rien à traduire.
    let sentProducts = [];
    const products = () => {
      sentProducts = [];
      const list = [];
      Array.from(form.querySelectorAll("[data-product]")).forEach((row, rank) => {
        const entry = {product: row.querySelector('[name="product"]').value,
          quantity: decimal(row.querySelector('[name="quantity"]').value, "quantity", rank),
          unit: row.querySelector('[name="unit"]').value};
        if (!entry.product.trim() && entry.quantity === null) return;
        sentProducts.push(rank);
        list.push(entry);
      });
      return list;
    };
    const effective = form.elements.effective_at;
    if (effective?.dataset.instant) {
      const d = new Date(effective.dataset.instant);
      effective.step = "any";
      effective.value = new Date(d.getTime() - d.getTimezoneOffset() * 60000).toISOString().slice(0, 23);
      effective.dataset.rendered = effective.value;
    }
    form.elements.precision?.addEventListener("change", () => {
      const old = effective.value;
      effective.type = get("precision") === "instant" ? "datetime-local" : "date";
      effective.value = get("precision") === "instant" ? (old.length === 10 ? `${old}T12:00` : old) : old.slice(0, 10);
    });
    const preview = () => {
      const recipe = form.elements.recipe_id?.selectedOptions[0];
      const check = form.elements.confirm_recipe;
      if (!check) return;
      check.checked = false;
      check.required = Boolean(recipe?.value);
      form.querySelector("[data-recipe-confirm]").hidden = !recipe?.value;
      form.querySelector("[data-products]").hidden = Boolean(recipe?.value);
      const node = form.querySelector("[data-recipe-preview]");
      node.textContent = "";
      if (!recipe?.value) return;
      try {
        const volume = decimal(get("volume_l"));
        node.textContent = volume > 0 ? JSON.parse(recipe.dataset.ingredients).map(p => `${p.product} : ${Number((p.quantity * (volume / Number(recipe.dataset.volume))).toPrecision(12))} ${p.unit}`).join(" · ") : "Renseigner un volume positif pour calculer les quantités.";
      } catch (error) { node.textContent = error.message; }
    };
    const sync = () => {
      if (!form.elements.kind) return;
      const kind = get("kind"), target = form.elements.target.selectedOptions[0];
      const preparation = !["reading", "topup"].includes(kind);
      form.querySelector("[data-preparation]").hidden = !preparation;
      form.querySelector("[data-mothers]").hidden = !["reading", "water"].includes(kind) || target?.dataset.subjectKind !== "mother";
      if (["renewal", "topup"].includes(kind)) form.elements.volume_l.closest("details").open = true;
      if (preparation) form.querySelector("[data-preparation]").open = true;
      if (!preparation && form.elements.recipe_id.value) { form.elements.recipe_id.value = ""; preview(); }
      form.elements.volume_l.required = ["renewal", "topup"].includes(kind);
    };
    // Recherche bornée d'intervention : le select ne contient jamais tout le carnet.
    const lookup = form.querySelector("[data-intervention-lookup]");
    const select = form.elements.intervention_id;
    if (lookup && select) {
      const status = lookup.querySelector("[data-intervention-status]");
      const search = lookup.querySelector('[name="intervention_search"]');
      const kinds = JSON.parse(lookup.dataset.kinds || "{}");
      const size = Number(lookup.dataset.page) || 200;
      let offset = 0, busyLookup = false;
      const describe = item => `${kinds[item.kind] || item.kind} · ${item.effective_at} · ${item.target_label} · ${item.id.slice(0, 8)}`;
      const load = async step => {
        if (busyLookup) return;
        const next = Math.max(0, step === null ? 0 : offset + step * size);
        busyLookup = true; status.textContent = "Recherche des interventions…";
        try {
          const query = new URLSearchParams({interventions: search.value, interventions_offset: String(next)});
          const response = await fetch(`/api/v1/cultures/solutions?${query}`, {headers: {Accept: "application/json"}});
          const data = await response.json().catch(() => ({error: "Réponse illisible."}));
          if (!response.ok) throw new Error(data.error || "Recherche refusée.");
          offset = data.interventions_offset;
          const kept = select.selectedOptions[0];
          const keep = kept && kept.value ? {value: kept.value, text: kept.textContent} : null;
          select.textContent = "";
          select.append(new Option("Sans lien", ""));
          const seen = new Set();
          data.interventions.forEach(item => { seen.add(item.id); select.append(new Option(describe(item), item.id)); });
          // L'association en cours reste proposée même absente de la fenêtre affichée.
          if (keep && !seen.has(keep.value)) select.append(new Option(keep.text, keep.value));
          select.value = keep ? keep.value : "";
          const last = Math.min(data.interventions_total, offset + size);
          status.textContent = data.interventions_total
            ? `${data.interventions_total} intervention(s) trouvée(s) · affichées ${offset + 1} à ${last}, de la plus récente à la plus ancienne.`
            : "Aucune intervention pour cette recherche ; l’association en cours reste conservée.";
        } catch (error) {
          status.textContent = error instanceof TypeError ? "Recherche non aboutie : l’association en cours est conservée." : error.message;
        } finally { busyLookup = false; }
      };
      lookup.querySelector("[data-intervention-find]").addEventListener("click", () => load(null));
      lookup.querySelectorAll("[data-intervention-page]").forEach(button => {
        button.addEventListener("click", () => load(Number(button.dataset.interventionPage)));
      });
      search.addEventListener("keydown", event => { if (event.key === "Enter") { event.preventDefault(); load(null); } });
    }
    form.elements.kind?.addEventListener("change", sync);
    form.elements.target?.addEventListener("change", sync);
    form.elements.recipe_id?.addEventListener("change", preview);
    form.elements.volume_l?.addEventListener("input", preview);
    form.querySelector("[data-add-product]").addEventListener("click", () => {
      const list = form.querySelector("[data-product-list]");
      if (list.children.length >= 40) return;
      const row = list.firstElementChild.cloneNode(true);
      // La ligne modèle peut porter un refus : sans ce nettoyage le clone afficherait le
      // message de l'ancienne ligne, avec son identifiant en double.
      forms.resetField(row);
      row.querySelectorAll("input").forEach(input => { input.value = ""; delete input.dataset.cfGenerated; input.removeAttribute("id"); });
      list.append(row);
      // Les identifiants sont recalculés pour que le refus d'un produit vise la bonne ligne.
      forms.register(form);
    });
    form.addEventListener("click", event => {
      const button = event.target.closest("[data-remove-product]");
      if (button && form.querySelectorAll("[data-product]").length > 1) button.closest("[data-product]").remove();
      else if (button) button.closest("[data-product]").querySelectorAll("input").forEach(input => { input.value = ""; });
    });
    sync();
    form.addEventListener("submit", async event => {
      event.preventDefault();
      let command;
      try {
        command = {operation: form.hasAttribute("data-solution-recipe") ? "recipe" : form.dataset.id ? "correct" : "entry",
          confirm_date: form.elements.confirm_date?.checked || false};
        if (form.dataset.id) Object.assign(command, {id: form.dataset.id, version: Number(form.dataset.version)});
        if (command.operation === "recipe") Object.assign(command, {name: get("name"), volume_l: decimal(get("volume_l"), "volume_l"), ingredients: products()});
        else {
          const selected = form.elements.target.selectedOptions[0];
          const reservoir = selected.hasAttribute("data-reservoir");
          const targets = reservoir ? [] : [get("target")];
          if (!form.querySelector("[data-mothers]").hidden) form.querySelectorAll('[name="mother"]:checked').forEach(input => { if (!targets.includes(input.value)) targets.push(input.value); });
          Object.assign(command, {kind: get("kind"), reservoir_id: reservoir ? get("target") : null, targets,
            effective_at: get("precision") === "instant" ? (effective.dataset.rendered === effective.value ? effective.dataset.instant : new Date(effective.value).toISOString()) : effective.value,
            precision: get("precision"), ph: decimal(get("ph"), "ph"), ec: decimal(get("ec"), "ec"), ec_unit: get("ec_unit"),
            temperature_c: decimal(get("temperature_c"), "temperature_c"), volume_l: decimal(get("volume_l"), "volume_l"), context: get("context"),
            intervention_id: get("intervention_id") || null, compensation: get("compensation"), note: get("note"),
            ingredients: form.querySelector("[data-preparation]").hidden ? [] : products()});
          const recipe = form.elements.recipe_id.selectedOptions[0];
          if (recipe.value) {
            if (!form.elements.confirm_recipe.checked) throw invalid("Vérifier les quantités avant validation.", "confirm_recipe");
            // Les ingrédients viennent alors de la recette, pas des lignes de la page :
            // aucun rang DOM à traduire, et la table doit cesser de désigner les anciennes.
            sentProducts = [];
            Object.assign(command, {recipe_id: recipe.value, recipe_revision: Number(recipe.dataset.revision),
              ingredients: JSON.parse(recipe.dataset.ingredients).map(p => ({...p, quantity: p.quantity * (command.volume_l / Number(recipe.dataset.volume))}))});
          }
          if (form.dataset.id) Object.assign(command, {cancelled: form.elements.cancelled.checked, reason: get("reason")});
        }
      } catch (error) {
        forms.showError(form, {error: error.message, field: error.field, index: error.index});
        return;
      }
      forms.status(form, "Enregistrement…");
      const answer = await forms.submitJson(form, "/api/v1/cultures/solutions", command);
      // Hors ligne et envoi déjà en vol : le socle a posé son message, la saisie reste intacte.
      if (answer.offline || answer.busy || answer.preview) return;
      if (!answer.ok) {
        const data = answer.data || {};
        // Un refus d'ingrédient est numéroté dans la liste envoyée. Quand elle vient de la
        // recette, aucune ligne de la page ne le porte : marquer la n-ième ligne de saisie
        // libre désignerait un champ étranger au refus. C'est le choix de la recette qui
        // porte alors le message.
        const ingredient = ["product", "quantity", "unit"].includes(data.field) && typeof data.index === "number";
        const rank = ingredient ? sentProducts[data.index] : undefined;
        const {field: refusedField, index: refusedIndex, ...rest} = data;
        const placed = !ingredient ? {field: refusedField, index: refusedIndex}
          : rank !== undefined ? {field: refusedField, index: rank}
          : command.recipe_id ? {field: "recipe_id"} : {};
        forms.showError(form, {...rest, ...placed,
          error: `${data.error} Saisie conservée.${answer.status === 409 ? " Ouvrir cette page dans un nouvel onglet pour consulter la version actuelle." : ""}`});
        return;
      }
      const result = answer.data;
      forms.status(form, "Enregistré. Ouverture de l’entrée…");
      const next = new URL(location.href); next.searchParams.delete("offset"); next.searchParams.delete("entry"); next.searchParams.delete("kind");
      next.searchParams.delete("start"); next.searchParams.delete("end");
      if (command.operation !== "recipe") next.searchParams.set("target", command.reservoir_id || command.targets[0]);
      next.hash = command.operation === "recipe" ? "recettes" : `entry-${result.id}`;
      // L'entrée peut être rétrospective ; la page serveur choisit sa pagination.
      if (command.operation !== "recipe") next.searchParams.set("entry", result.id);
      if (next.pathname === location.pathname && next.search === location.search) {
        location.hash = next.hash; location.reload();
      } else location.assign(next.href);
    });
  });
  const charts = document.querySelector("[data-solution-charts]");
  const points = JSON.parse(charts?.dataset.chart || "[]");
  const stages = JSON.parse(charts?.dataset.stages || "[]");
  const svgNode = (name, attributes, text) => {
    const el = document.createElementNS("http://www.w3.org/2000/svg", name);
    Object.entries(attributes).forEach(([key, value]) => el.setAttribute(key, String(value)));
    if (text !== undefined) el.textContent = text; return el;
  };
  // Lot E : bandes de référence des plages cibles, fournies par période résolue.
  const bands = JSON.parse(charts?.dataset.targetBands || "[]");
  document.querySelectorAll("svg[data-metric]").forEach(svg => {
    const metric = svg.dataset.metric;
    const describe = p => `${p.label} : ${p[metric] === null ? 'mesure absente' : p[metric]} ${metric === 'ec' ? 'mS/cm' : ''} · ${p.at} · ${p.target} · solution ${p.period || "manuelle"}${p[metric + "_count"] ? ` · ${p[metric + "_count"]} mesures, min ${p[metric + "_min"]}, max ${p[metric + "_max"]}` : ""} · ${p.annotations.join(', ')}`;
    // Tableau équivalent : une colonne par nature de donnée. Une lacune s'écrit
    // « mesure absente » dans la colonne valeur, jamais 0.
    const columns = ["Date", "Valeur", "Unité", "Cible ou capteur", "Période", "Agrégats", "Lacune"];
    const cells = p => [
      p.at,
      p[metric] === null ? "mesure absente" : String(p[metric]),
      metric === "ec" ? "mS/cm" : "sans unité",
      p.target,
      p.period || "manuelle",
      p[metric + "_count"]
        ? `${p[metric + "_count"]} mesures, min ${p[metric + "_min"]}, max ${p[metric + "_max"]}`
        : "aucun agrégat",
      p[metric] === null ? "oui" : "non",
    ];
    const rows = points.map(p => ({text: describe(p), cells: cells(p)}));
    // Le dessin ne dépend jamais de l'explorateur : un asset manquant (précache partiel,
    // 404 après déploiement) ne doit pas priver la page de ses courbes.
    const refreshSelection = window.PhytoCultureAnalysis?.chart?.(svg, rows,
      svg.getAttribute("aria-label"), columns) ?? (() => {});
    const draw = () => {
      svg.replaceChildren();
      const width = svg.getBoundingClientRect().width || 240;
      svg.setAttribute("viewBox", `0 0 ${width} 220`);
      const right = width - 20, span = right - 60;
      const metric = svg.dataset.metric, measured = points.filter(p => p[metric] !== null);
      if (!measured.length) { svg.append(svgNode("text", {x: 30, y: 100}, "Aucune mesure")); refreshSelection([]); return; }
      const times = points.map(p => Date.parse(p.at)), low = Math.min(...times), high = Math.max(...times);
      // Lot E : les bornes cibles n'écrasent pas l'échelle des mesures ; elles l'élargissent
      // seulement quand elles sont présentes, pour rester lisibles sans déformer la courbe.
      const metricBands = bands.filter(b => b[metric + "_min"] !== null || b[metric + "_max"] !== null);
      const bandValues = metricBands.flatMap(b => [b[metric + "_min"], b[metric + "_max"]].filter(v => v !== null && v !== undefined));
      const values = measured.flatMap(p => [p[metric + "_min"] ?? p[metric], p[metric + "_max"] ?? p[metric]]).concat(bandValues), min = Math.min(...values), max = Math.max(...values);
      const x = p => 60 + span * (high === low ? 0.5 : (Date.parse(p.at) - low) / (high - low));
      const y = p => 160 - 115 * (max === min ? 0.5 : (p[metric] - min) / (max - min));
      svg.append(svgNode("path", {d: `M60 25V170H${right}`, class: "solution-axis"}));
      svg.append(svgNode("text", {x: 4, y: 45}, max.toFixed(2)), svgNode("text", {x: 4, y: 160}, min.toFixed(2)));
      // Lot E : bandes de référence, tracées avant les mesures pour rester en arrière-plan.
      // Elles ne couvrent que la période où la plage a été résolue : aucune extrapolation.
      const xAt = at => 60 + span * (high === low ? 0.5 : (Date.parse(at) - low) / (high - low));
      const yValue = value => 160 - 115 * (max === min ? 0.5 : (value - min) / (max - min));
      metricBands.forEach(band => {
        const left = xAt(band.start), right = Math.max(xAt(band.end), left + 4);
        const lower = band[metric + "_min"], upper = band[metric + "_max"];
        const title = `Plage cible ${band.label || ""} · ${lower === null || lower === undefined ? "sans minimum" : lower} à ${upper === null || upper === undefined ? "sans maximum" : upper}`;
        if (lower !== null && lower !== undefined && upper !== null && upper !== undefined) {
          const rect = svgNode("rect", {x: left, y: yValue(upper), width: right - left,
            height: Math.max(yValue(lower) - yValue(upper), 1), class: "solution-target-band"});
          rect.append(svgNode("title", {}, title)); svg.append(rect);
          return;
        }
        // Une seule borne reste une seule borne : jamais complétée par une valeur inventée.
        const bound = lower !== null && lower !== undefined ? lower : upper;
        const edge = svgNode("path", {d: `M${left} ${yValue(bound)}H${right}`, class: "solution-target-edge"});
        edge.append(svgNode("title", {}, title)); svg.append(edge);
      });
      const date = value => new Date(value).toLocaleDateString("fr-FR", {day: "2-digit", month: "2-digit"});
      svg.append(svgNode("text", {x: 60, y: 205}, date(low)), svgNode("text", {x: right, y: 205, "text-anchor": "end"}, date(high)));
      points.filter(p => p.annotations.length).forEach(p => {
        const line = svgNode("path", {d: `M${x(p)} 25V170`, class: p.annotations.includes("Renouvellement") ? "solution-renewal" : "solution-marker"});
        line.append(svgNode("title", {}, `${p.annotations.join(", ")} · ${p.at}`));
        svg.append(line);
      });
      stages.forEach(p => {
        const line = svgNode("path", {d: `M${x(p)} 25V170`, class: "solution-stage"});
        line.append(svgNode("title", {}, `${p.label} · ${p.at}`)); svg.append(line);
      });
      // L'index vient de la boucle : `points.indexOf(p)` coûtait jusqu'à 4·10⁶ comparaisons
      // par redessin à la borne de 2 000 points.
      const places = [];
      points.forEach((p, i) => {
        if (p[metric] === null) return;
        if (p[metric + "_count"]) {
          svg.append(svgNode("path", {d: `M${x(p)} ${y({...p, [metric]: p[metric + "_min"]})}V${y({...p, [metric]: p[metric + "_max"]})}`, class: "solution-range"}));
        }
        // Une classe supplémentaire par cible ou période viendra s'ajouter ici sans
        // toucher au reste du dessin ni à la position transmise à l'explorateur.
        const classes = ["solution-dot"];
        const dot = svgNode("circle", {cx: x(p), cy: y(p), r: 5, class: classes.join(" "), "data-analysis-index": i});
        dot.append(svgNode("title", {}, `${p.label} : ${p[metric]} · ${p.at} · ${p.target} · solution ${p.period || "manuelle"}${p[metric + "_count"] ? ` · ${p[metric + "_count"]} mesures, min ${p[metric + "_min"]}, max ${p[metric + "_max"]}` : ""}`)); svg.append(dot);
        places[i] = {x: x(p), y: y(p)};
      });
      refreshSelection(places);
    };
    let lastWidth = 0;
    new ResizeObserver(() => {
      const width = svg.getBoundingClientRect().width;
      if (Math.abs(width - lastWidth) < 1) return;
      lastWidth = width; draw();
    }).observe(svg);
    draw();
  });
})();
