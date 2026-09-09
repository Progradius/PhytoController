(() => {
  "use strict";
  const element = (tag, text, className) => {
    const node = document.createElement(tag);
    if (text) node.textContent = text;
    if (className) node.className = className;
    return node;
  };
  const button = text => { const node = element("button", text, "button button-secondary"); node.type = "button"; return node; };

  // Les données restent celles du graphique : aucune interpolation ni requête auxiliaire.
  // Un seul curseur clavier évite des milliers d'arrêts de tabulation sur les longues périodes.
  window.PhytoCultureAnalysis = {chart(svg, rows, label) {
    if (!rows.length) return () => {};
    const zone = element("div", null, "culture-chart-explorer");
    const controls = element("div", null, "culture-analysis-controls");
    const previous = button("Point précédent"), next = button("Point suivant");
    const rangeLabel = element("label", `Explorer : ${label}`), range = element("input");
    range.type = "range"; range.min = "0"; range.max = String(rows.length - 1); range.value = "0";
    rangeLabel.append(range);
    const output = element("p"); output.setAttribute("role", "status");
    controls.append(previous, next); zone.append(rangeLabel, controls, output);
    svg.after(zone);
    let selected = 0;
    const select = index => {
      selected = Math.max(0, Math.min(rows.length - 1, index)); range.value = String(selected);
      output.textContent = `${selected + 1} / ${rows.length} · ${rows[selected].text}`;
      range.setAttribute("aria-valuetext", output.textContent);
      previous.disabled = selected === 0; next.disabled = selected === rows.length - 1;
      svg.querySelectorAll("[data-analysis-index]").forEach(dot => dot.classList.toggle("culture-selected-point", Number(dot.dataset.analysisIndex) === selected));
    };
    range.addEventListener("input", () => select(Number(range.value)));
    previous.addEventListener("click", () => select(selected - 1)); next.addEventListener("click", () => select(selected + 1));
    svg.addEventListener("click", event => {
      // Coordonnées rendues : le choix reste exact après une rotation du téléphone.
      const candidates = [...svg.querySelectorAll("[data-analysis-index]")];
      let best = null, distance = Infinity;
      for (const dot of candidates) {
        const box = dot.getBoundingClientRect();
        const delta = Math.hypot(box.x + box.width / 2 - event.clientX, box.y + box.height / 2 - event.clientY);
        if (delta < distance) { distance = delta; best = dot; }
      }
      if (best) select(Number(best.dataset.analysisIndex));
    });
    const details = element("details"), summary = element("summary", "Tableau des données du graphique"); details.append(summary);
    // Tableau construit à la demande, borné au même jeu de points que le dessin.
    details.addEventListener("toggle", () => {
      if (!details.open || details.querySelector("table")) return;
      const table = element("table"), caption = element("caption", label), body = element("tbody");
      rows.forEach((row, i) => { const tr = element("tr"), th = element("th", String(i + 1)); th.scope = "row"; tr.append(th, element("td", row.text)); body.append(tr); });
      table.append(caption, body); details.append(table);
    });
    zone.append(details); select(0);
    return () => select(selected);
  }};

  // Dialogue natif : focus contenu, Échap et retour au lien exact, même dans le journal.
  const photos = [...document.querySelectorAll('.culture-photo a[href^="/cultures/photos/"]')];
  if (photos.length && typeof HTMLDialogElement !== "undefined" && typeof HTMLDialogElement.prototype.showModal === "function") {
    const dialog = element("dialog", null, "culture-gallery"), title = element("h2", "Photos du carnet");
    title.id = "culture-gallery-title"; dialog.setAttribute("aria-labelledby", title.id);
    const close = button("Fermer et revenir"), previous = button("Photo précédente"), next = button("Photo suivante");
    const image = element("img"), caption = element("p"), failure = element("p"), context = element("a", "Ouvrir l’entrée liée");
    caption.setAttribute("role", "status"); failure.setAttribute("role", "status");
    const controls = element("div", null, "culture-analysis-controls"); controls.append(previous, next);
    dialog.append(title, close, image, failure, caption, controls, context); document.body.append(dialog);
    let group = [], index = 0, origin = null;
    const show = value => {
      index = Math.max(0, Math.min(group.length - 1, value)); const link = group[index], figure = link.closest("figure");
      failure.textContent = ""; image.src = link.href; image.alt = link.querySelector("img").alt;
      caption.textContent = `${index + 1} / ${group.length} · ${figure.querySelector("figcaption")?.textContent || image.alt}`;
      const related = figure.querySelector('figcaption a'); context.hidden = !related;
      if (related) context.href = related.href;
      previous.disabled = index === 0; next.disabled = index === group.length - 1;
    };
    image.addEventListener("error", () => { failure.textContent = "Photo indisponible. Revenir à la fiche ou choisir une autre photo."; });
    photos.forEach(link => link.addEventListener("click", event => {
      if (event.ctrlKey || event.metaKey || event.shiftKey || event.altKey) return;
      event.preventDefault(); origin = link;
      group = photos.filter(other => other.closest(".culture-grid") === link.closest(".culture-grid"));
      show(group.indexOf(link)); dialog.showModal(); close.focus();
    }));
    close.addEventListener("click", () => dialog.close()); dialog.addEventListener("close", () => origin?.focus());
    previous.addEventListener("click", () => show(index - 1)); next.addEventListener("click", () => show(index + 1));
    context.addEventListener("click", () => dialog.close());
    dialog.addEventListener("keydown", event => {
      if (event.key === "ArrowLeft" || event.key === "ArrowRight") { event.preventDefault(); show(index + (event.key === "ArrowLeft" ? -1 : 1)); }
    });
  }
  const selection = document.querySelector("[data-comparison-selection]");
  if (selection) {
    const query = selection.querySelector('input[type="search"]'), checks = [...selection.querySelectorAll('[name="subject"]')];
    const output = selection.querySelector("output");
    const refresh = () => {
      const count = checks.filter(input => input.checked).length;
      output.textContent = `${count} / 4 cultures sélectionnées`;
      checks.forEach(input => { input.disabled = count >= 4 && !input.checked; input.closest("label").hidden = !input.checked && !input.dataset.search.includes(query.value.toLocaleLowerCase("fr")); });
    };
    query.addEventListener("input", refresh); checks.forEach(input => input.addEventListener("change", refresh)); refresh();
  }
})();
