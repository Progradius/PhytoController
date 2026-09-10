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
  // La consigne vaut pour la page, pas pour chaque figure : deux courbes sur une même page
  // en donnaient deux copies, que le lecteur d'écran relit et que l'œil doit écarter.
  let usageShown = false;

  // Contrat interne avec les scripts hôtes (solutions, cycles), volontairement minimal :
  //   chart(svg, rows, label, columns) rend l'explorateur et renvoie refresh(positions).
  //   rows[i]      : {text, cells} ; `text` est la phrase du curseur, `cells` les valeurs
  //                  alignées sur `columns` pour le tableau équivalent.
  //   positions[i] : {x, y} dans le repère du `viewBox`, calculé par l'hôte avec ses
  //                  propres x(p)/y(p), ou absent quand le point n'est pas dessiné.
  //                  L'explorateur ne mesure jamais le DOM point par point pour situer.
  // Les données restent celles du graphique : aucune interpolation ni requête auxiliaire.
  // Un seul curseur clavier évite des milliers d'arrêts de tabulation sur les longues périodes.
  // Réplique exacte du filtre Jinja `nombre` (network/web/pages.py) : virgule française,
  // décimales bornées à [0, 6], `—` pour une absence ou un non-fini, unité optionnelle.
  // `useGrouping:false` est la convention du dépôt et **doit** le rester : le filtre
  // serveur formate avec `f"{n:.{p}f}"`, qui ne groupe pas les milliers. Grouper ici
  // ferait lire `1 234,5` au curseur d'une courbe et `1234,5` dans la page qui la porte,
  // pour la même mesure. Un séparateur de milliers d'un côté seulement est un écart
  // visible, pas un détail de style.
  const formatNombre = (value, decimals, unit = null) => {
    if (value === null || value === undefined || !Number.isFinite(Number(value))) return "—";
    const places = Math.max(0, Math.min(6, Number(decimals)));
    const result = Number(value).toLocaleString("fr-FR", {useGrouping:false, minimumFractionDigits:places, maximumFractionDigits:places});
    return unit ? `${result} ${unit}` : result;
  };
  window.PhytoCultureAnalysis = {formatNombre, chart(svg, rows, label, columns) {
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
    // Sortie visible, jamais live : une région live posée ici doublerait chaque déplacement
    // du curseur et reparlerait à chaque redessin, rotation du téléphone comprise.
    const output = element("p", null, "culture-analysis-output");
    // Annonce des gestes qui n'ont pas le curseur sous le doigt ni sous le focus : un bouton
    // et un tap ne déclenchent aucune relecture de `aria-valuetext`, donc le déplacement
    // resterait muet. Région masquée et distincte de la sortie visible, qui n'est jamais
    // live : le curseur au clavier annoncerait sinon deux fois le même point.
    const announcer = element("p", null, "visually-hidden");
    announcer.setAttribute("role", "status");
    controls.append(previous, next);
    zone.append(rangeLabel, controls, output, announcer);
    if (!usageShown) {
      zone.append(element("p", USAGE, "card-meta"));
      usageShown = true;
    }
    // R2.3 : sous 48 rem, l'exploration est repliée par défaut. Réglages, curseur, sortie et
    // tableau équivalent représentaient à eux seuls 366 px par figure sur un écran de 390 px,
    // soit plus du tiers de la vue Analyser — pour un outil qu'on ouvre quand on veut lire un
    // point précis, pas pour survoler deux courbes. Rien n'est retiré : le repli est nommé,
    // il porte le nombre de points, et son contenu est le même à une activation près. Au-delà
    // de 48 rem la place existe et l'explorateur reste ouvert, comme avant.
    const fold = element("details", null, "culture-chart-explorer-fold");
    fold.append(element("summary", `Explorer point par point (${rows.length})`));
    fold.append(zone);
    fold.open = !(typeof matchMedia === "function" && matchMedia("(max-width: 47.99rem)").matches);
    svg.after(fold);
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
    const select = (index, options) => {
      const target = Math.max(0, Math.min(rows.length - 1, index));
      const changed = target !== selected || !range.hasAttribute("aria-valuetext");
      selected = target;
      range.value = String(selected);
      if (changed) {
        output.textContent = `${selected + 1} / ${rows.length} · ${rows[selected].text}${bound()}`;
        range.setAttribute("aria-valuetext", output.textContent);
      }
      // `announce` n'est vrai que pour un geste hors curseur : ni l'événement `input` du
      // curseur, ni un redessin ne reparlent.
      if (options && options.announce) announcer.textContent = output.textContent;
      paint();
    };
    range.addEventListener("input", () => select(Number(range.value)));
    previous.addEventListener("click", () => select(selected - 1, {announce: true}));
    next.addEventListener("click", () => select(selected + 1, {announce: true}));
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
      select(best, {announce: true});
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
    // Le rembourrage vit sur cette enveloppe et non sur le `dialog` : posé sur le dialogue,
    // il en fait une zone cliquable qui n'est aucun de ses enfants, et le clic y atteignait
    // `event.target === dialog`, donc fermait la galerie à côté de l'image.
    const body = element("div", null, "culture-gallery-body");
    body.append(title, close, image, caption, controls, context);
    dialog.append(body);
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
    // Échap, bouton « Fermer et revenir » et clic sur le voile ramènent le focus à la
    // vignette : rien n'a été ouvert, la lecture reprend où elle s'est arrêtée. Le lien de
    // contexte, lui, emmène ailleurs ; y ramener le focus contredirait la convention du
    // lot 2, où l'élément focalisé **est** la confirmation de l'endroit atteint.
    let followed = false;
    close.addEventListener("click", () => dialog.close());
    dialog.addEventListener("close", () => {
      const back = followed ? null : origin;
      followed = false;
      back?.focus();
    });
    previous.addEventListener("click", () => show(index - 1));
    next.addEventListener("click", () => show(index + 1));
    context.addEventListener("click", event => {
      if (event.ctrlKey || event.metaKey || event.shiftKey || event.altKey) return;
      const destination = new URL(context.href, location.href);
      const here = destination.pathname === location.pathname && destination.search === location.search;
      // Même page et aucun fragment : rien ne se passera, ni navigation ni défilement ni
      // ancre à focaliser. Neutraliser le retour laisserait alors le focus sur `body`, sans
      // destination atteinte à annoncer ; la lecture reprend donc sur la vignette.
      followed = !here || Boolean(destination.hash);
      dialog.close();
      // Vers une autre page (journal → fiche), la navigation fait le travail. Sur la même
      // page, un dialogue qui se ferme ne laisse ni défilement ni focus au fragment : c'est
      // donc ici que l'ancre `tabindex="-1"` reçoit le focus, quand elle existe.
      if (!here || !destination.hash) return;
      const anchor = document.getElementById(destination.hash.slice(1));
      if (!anchor) return;
      event.preventDefault();
      location.hash = destination.hash;
      anchor.focus();
    });
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
    // Même garde que pour l'explorateur : un bloc rendu sans son champ de filtre ou sans sa
    // sortie n'est pas une raison d'interrompre le script de la page.
    if (!output || !query) return;
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
        // `aria-disabled` et non `disabled` : une case désactivée sort de l'ordre de
        // tabulation, donc son `aria-describedby` — le compte et la phrase qui motive le
        // plafond — n'est jamais annoncé, et le refus reste muet. La case garde le focus,
        // et c'est le gestionnaire `change` qui refuse la cinquième sélection.
        if (count >= maximum && !input.checked) input.setAttribute("aria-disabled", "true");
        else input.removeAttribute("aria-disabled");
        const matched = input.dataset.search.includes(needle);
        input.closest("label").hidden = !input.checked && !matched;
      });
    };
    query.addEventListener("input", refresh);
    checks.forEach(input => input.addEventListener("change", () => {
      // Le plafond est appliqué au geste : cocher au-delà décoche aussitôt, le compte
      // reste « 4 / 4 » et l'explication reste annoncée par la case elle-même.
      if (input.checked && checks.filter(box => box.checked).length > maximum) input.checked = false;
      refresh();
    }));
    refresh();
  }
})();
