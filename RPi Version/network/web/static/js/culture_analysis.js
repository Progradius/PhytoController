(() => {
  "use strict";
  const element = (tag, text, className) => {
    const node = document.createElement(tag);
    if (text) node.textContent = text;
    if (className) node.className = className;
    return node;
  };
  const button = text => {
    const node = element("button", text, "button button-secondary");
    node.type = "button";
    return node;
  };

  // Consigne d'usage rendue par le fragment lui-même : aucune page ne peut l'oublier,
  // et deux figures ne peuvent pas en donner deux versions différentes.
  const USAGE = "Toucher le graphique pour choisir le point le plus proche, ou utiliser le"
    + " curseur et ses flèches au clavier. Le tableau reprend les valeurs et les absences"
    + " du graphique.";
  // Rayon d'acceptation d'un tap, en pixels CSS. Au-delà, le geste ne vise aucun point :
  // la sélection courante est conservée plutôt que remplacée par un point lointain.
  const TAP_RADIUS_PX = 44;
  // Même clé que `model/culture_text.search_key` : NFD, marques retirées, casse pliée.
  // Sans locale : le verdict ne doit pas dépendre de la langue du navigateur.
  const searchKey = value => String(value ?? "").normalize("NFD").replace(/\p{M}/gu, "").toLowerCase();
  const RANK_HEADER = "Rang";
  const MISSING_CELL = "—";

  // Contrat interne avec les scripts hôtes (solutions, cycles), volontairement minimal :
  //   chart(svg, rows, label, columns) rend l'explorateur et renvoie refresh(positions).
  //   rows[i]      : {text, cells} ; `text` est la phrase du curseur, `cells` les valeurs
  //                  alignées sur `columns` pour le tableau équivalent.
  //   positions[i] : {x, y} dans le repère du `viewBox`, calculé par l'hôte avec ses
  //                  propres x(p)/y(p), ou absent quand le point n'est pas dessiné.
  //                  L'explorateur ne mesure jamais le DOM point par point pour situer.
  // Les données restent celles du graphique : aucune interpolation ni requête auxiliaire.
  // Un seul curseur clavier évite des milliers d'arrêts de tabulation sur les longues périodes.
  window.PhytoCultureAnalysis = {chart(svg, rows, label, columns) {
    if (!rows.length) return () => {};
    const headers = [RANK_HEADER].concat(columns && columns.length ? columns : ["Description"]);
    const zone = element("div", null, "culture-chart-explorer");
    const controls = element("div", null, "culture-analysis-controls");
    const previous = button("Point précédent");
    const next = button("Point suivant");
    const rangeLabel = element("label", `Explorer : ${label}`);
    const range = element("input");
    range.type = "range";
    range.min = "0";
    range.max = String(rows.length - 1);
    range.value = "0";
    rangeLabel.append(range);
    // Une seule annonce, celle du curseur : une région live sur la sortie doublerait
    // chaque déplacement et reparlerait à chaque redessin, rotation du téléphone comprise.
    const output = element("p", null, "culture-analysis-output");
    controls.append(previous, next);
    zone.append(rangeLabel, controls, output, element("p", USAGE, "card-meta"));
    svg.after(zone);
    let selected = 0;
    let marked = null;
    let places = [];
    const nodes = new Map();
    const unmark = node => {
      node.classList.remove("culture-selected-point");
      if (node.dataset.analysisRadius) node.setAttribute("r", node.dataset.analysisRadius);
    };
    const mark = node => {
      node.classList.add("culture-selected-point");
      if (node.tagName !== "circle") return;
      // Rayon posé en attribut : la propriété géométrique CSS `r` manque aux Firefox
      // antérieurs à 128, où la surbrillance d'un point se réduirait au contour.
      if (!node.dataset.analysisRadius) node.dataset.analysisRadius = node.getAttribute("r");
      node.setAttribute("r", String(Number(node.dataset.analysisRadius) + 2));
    };
    // Un seul nœud change d'état par pas de curseur : pas de balayage du dessin entier.
    const paint = () => {
      const node = nodes.get(selected) || null;
      if (marked && marked !== node) unmark(marked);
      marked = node;
      if (node) mark(node);
    };
    const bound = () => {
      if (rows.length === 1) return " · point unique";
      if (selected === 0) return " · premier point";
      if (selected === rows.length - 1) return " · dernier point";
      return "";
    };
    // Bornage dans `select` plutôt que désactivation des boutons : un bouton qui devient
    // `disabled` sous le focus le perd au moment même où il est activé.
    const select = index => {
      const target = Math.max(0, Math.min(rows.length - 1, index));
      const changed = target !== selected || !range.hasAttribute("aria-valuetext");
      selected = target;
      range.value = String(selected);
      if (changed) {
        output.textContent = `${selected + 1} / ${rows.length} · ${rows[selected].text}${bound()}`;
        range.setAttribute("aria-valuetext", output.textContent);
      }
      paint();
    };
    range.addEventListener("input", () => select(Number(range.value)));
    previous.addEventListener("click", () => select(selected - 1));
    next.addEventListener("click", () => select(selected + 1));
    svg.addEventListener("click", event => {
      // Distances calculées dans le repère du `viewBox` puis ramenées en pixels CSS par
      // la matrice de rendu : exact après une rotation, sans lire une boîte par point.
      const matrix = svg.getScreenCTM();
      if (!matrix || !places.length) return;
      const cursor = new DOMPoint(event.clientX, event.clientY).matrixTransform(matrix.inverse());
      let best = -1;
      let distance = Infinity;
      places.forEach((place, index) => {
        if (!place) return;
        const delta = Math.hypot((place.x - cursor.x) * matrix.a, (place.y - cursor.y) * matrix.d);
        if (delta >= distance) return;
        distance = delta;
        best = index;
      });
      if (best < 0 || distance > TAP_RADIUS_PX) return;
      select(best);
    });
    const details = element("details");
    details.append(element("summary", "Tableau des données du graphique"));
    const scroll = element("div", null, "culture-table-scroll");
    scroll.tabIndex = 0;
    // Tableau construit à la demande, borné au même jeu de points que le dessin.
    details.addEventListener("toggle", () => {
      if (!details.open || details.querySelector("table")) return;
      const table = element("table", null, "culture-analysis-table");
      table.append(element("caption", label));
      const head = element("thead");
      const headRow = element("tr");
      headers.forEach(name => {
        const cell = element("th", name);
        cell.scope = "col";
        headRow.append(cell);
      });
      head.append(headRow);
      const fields = headers.slice(1);
      const body = element("tbody");
      rows.forEach((row, index) => {
        const line = element("tr");
        const rank = element("th", String(index + 1));
        rank.scope = "row";
        line.append(rank);
        const cells = row.cells && row.cells.length ? row.cells : [row.text];
        fields.forEach((name, column) => {
          const value = cells[column];
          line.append(element("td", value === undefined || value === null ? MISSING_CELL : value));
        });
        body.append(line);
      });
      table.append(head, body);
      scroll.append(table);
      details.append(scroll);
    });
    zone.append(details);
    select(0);
    // Appelé après chaque dessin : l'index des nœuds est refait, le texte ne l'est pas.
    return positions => {
      nodes.clear();
      svg.querySelectorAll("[data-analysis-index]").forEach(node => {
        nodes.set(Number(node.dataset.analysisIndex), node);
      });
      places = positions || [];
      paint();
    };
  }};

  // Dialogue natif : focus contenu, Échap et retour au lien exact, même dans le journal.
  const photos = [...document.querySelectorAll('.culture-photo a[href^="/cultures/photos/"]')];
  const modal = typeof HTMLDialogElement !== "undefined"
    && typeof HTMLDialogElement.prototype.showModal === "function";
  if (photos.length && modal) {
    const dialog = element("dialog", null, "culture-gallery");
    const title = element("h2", "Photos du carnet");
    title.id = "culture-gallery-title";
    dialog.setAttribute("aria-labelledby", title.id);
    const close = button("Fermer et revenir");
    const previous = button("Photo précédente");
    const next = button("Photo suivante");
    const image = element("img");
    // Une seule région live dans le dialogue : la légende porte aussi l'échec de chargement.
    const caption = element("p");
    caption.setAttribute("role", "status");
    const context = element("a", "Ouvrir l’entrée liée");
    const controls = element("div", null, "culture-analysis-controls");
    controls.append(previous, next);
    dialog.append(title, close, image, caption, controls, context);
    document.body.append(dialog);
    let group = [];
    let index = 0;
    let origin = null;
    const edge = () => {
      if (group.length === 1) return " · photo unique";
      if (index === 0) return " · première photo";
      if (index === group.length - 1) return " · dernière photo";
      return "";
    };
    const show = value => {
      index = Math.max(0, Math.min(group.length - 1, value));
      const link = group[index];
      const figure = link.closest("figure");
      image.hidden = false;
      image.src = link.href;
      image.alt = link.querySelector("img").alt;
      const legend = figure.querySelector("figcaption")?.textContent || image.alt;
      caption.textContent = `${index + 1} / ${group.length} · ${legend}${edge()}`;
      const related = figure.querySelector("figcaption a");
      context.hidden = !related;
      if (related) context.href = related.href;
    };
    image.addEventListener("error", () => {
      // Une image cassée ne reste pas affichée : l'annonce unique du dialogue porte l'échec.
      image.hidden = true;
      caption.textContent += " · Photo indisponible. Revenir à la fiche ou choisir une autre photo.";
    });
    photos.forEach(link => link.addEventListener("click", event => {
      if (event.ctrlKey || event.metaKey || event.shiftKey || event.altKey) return;
      event.preventDefault();
      origin = link;
      group = photos.filter(other => other.closest(".culture-grid") === link.closest(".culture-grid"));
      show(group.indexOf(link));
      dialog.showModal();
      close.focus();
    }));
    close.addEventListener("click", () => dialog.close());
    dialog.addEventListener("close", () => origin?.focus());
    previous.addEventListener("click", () => show(index - 1));
    next.addEventListener("click", () => show(index + 1));
    context.addEventListener("click", () => dialog.close());
    dialog.addEventListener("click", event => {
      // Un clic sur le voile atteint le `dialog` lui-même, jamais son contenu.
      if (event.target === dialog) dialog.close();
    });
    dialog.addEventListener("keydown", event => {
      if (event.key !== "ArrowLeft" && event.key !== "ArrowRight") return;
      event.preventDefault();
      show(index + (event.key === "ArrowLeft" ? -1 : 1));
    });
  }
  const selection = document.querySelector("[data-comparison-selection]");
  if (selection) {
    const query = selection.querySelector('input[type="search"]');
    const checks = [...selection.querySelectorAll('[name="subject"]')];
    const output = selection.querySelector("output");
    const maximum = Number(selection.dataset.comparisonMax) || 4;
    if (!output.id) output.id = "culture-comparison-count";
    // Le plafond est annoncé par le compte, et motivé par la phrase du gabarit quand
    // elle est présente : la case désactivée dit alors pourquoi elle l'est.
    const note = selection.querySelector("[data-comparison-cap]");
    if (note && !note.id) note.id = "culture-comparison-cap";
    const described = note ? `${output.id} ${note.id}` : output.id;
    checks.forEach(input => input.setAttribute("aria-describedby", described));
    const refresh = () => {
      const count = checks.filter(input => input.checked).length;
      output.textContent = `${count} / ${maximum} cultures sélectionnées`;
      const needle = searchKey(query.value);
      checks.forEach(input => {
        input.disabled = count >= maximum && !input.checked;
        const matched = input.dataset.search.includes(needle);
        input.closest("label").hidden = !input.checked && !matched;
      });
    };
    query.addEventListener("input", refresh);
    checks.forEach(input => input.addEventListener("change", refresh));
    refresh();
  }
})();
