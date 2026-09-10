(() => {
  "use strict";
  const revealRubric = () => {
    const current = document.querySelector('.culture-navigation [aria-current="page"]');
    const navigation = current?.closest("nav");
    if (current && navigation) navigation.scrollLeft = Math.max(0, current.offsetLeft - navigation.offsetLeft - (navigation.clientWidth - current.offsetWidth) / 2);
  };
  revealRubric(); window.addEventListener("pageshow", revealRubric);
  // Socle commun des formulaires du carnet de cultures : identifiants stables, envoi
  // JSON ou binaire avec les mêmes gardes qu'auparavant, et restitution des refus au
  // champ concerné. Ce module ne commande aucun équipement, n'écrit aucune
  // configuration et ne met aucune mutation en attente hors ligne.
  const OFFLINE = "Hors ligne : saisie conservée dans cette page, aucun envoi mis en attente.";
  const NO_ANSWER = "Réponse non reçue. Saisie conservée : réessayez sans la modifier pour vérifier le même enregistrement.";
  const REFUSED = "Requête refusée ; vérifier la connexion et actualiser le jeton si nécessaire.";
  const BUSY = "Un envoi est déjà en cours pour ce formulaire.";
  const SUMMARY_TITLE = "La saisie n’a pas été enregistrée.";
  const PREVIEW_DOWN = "Vérification indisponible : enregistrement envoyé, le serveur revérifie le carnet.";
  const CONFIRM_MATCH = "Confirmez qu’il s’agit d’un autre relevé avant d’enregistrer.";
  const LEAVING = "Une saisie n’a pas été enregistrée.";
  const PREVIEW_VALIDITY_MS = 30000;
  // Délai d'un envoi binaire : une photo de 5 Mio sur le Wi-Fi d'une serre est longue.
  // Partagé par `submitBinary` et `sendUpload`, pour que le transport ne puisse pas
  // rester sans délai si l'appelant en oubliait un.
  const UPLOAD_TIMEOUT_MS = 45000;
  // Refus rendus en texte brut par le serveur HTTP, avant que le carnet ne soit consulté :
  // ils nomment ici la limite, comme le font déjà les refus JSON du carnet.
  const UPLOAD_REFUSALS = {
    408: "Envoi trop lent : aucune photo n’a été enregistrée. Réessayez la même saisie sans la modifier.",
    413: "Photo refusée : 5 Mio maximum par envoi. Reprenez la photo ou choisissez une image plus légère.",
    415: "Photo refusée : envoyez un fichier JPEG, PNG ou WebP non animé.",
  };

  let counter = 0;
  const bound = new WeakSet();   // contrôles dont l'effacement à la saisie est déjà branché
  const busy = new WeakSet();    // formulaires dont un envoi est en vol
  const reviewOnly = new WeakMap();
  const reviews = new WeakMap();
  const reviewTimers = new WeakMap(); // formulaire → minuteur de péremption de sa vérification
  const keys = new WeakMap();    // formulaire → {signature, value} de la clé d'idempotence
  const guarded = new Set();     // formulaires suivis pour la protection des saisies en cours
  const baselines = new WeakMap(); // formulaire → empreinte de sa saisie initiale
  const settled = new WeakSet(); // formulaires dont la saisie est enregistrée : plus de garde
  const touched = new WeakSet(); // formulaires réellement saisis par l'opérateur

  const csrf = () => document.querySelector('meta[name="csrf-token"]')?.content;
  const isOffline = () => !navigator.onLine || document.body.classList.contains("is-offline");
  const identifier = () =>
    Array.from(crypto.getRandomValues(new Uint8Array(20)), n => n.toString(16).padStart(2, "0")).join("");

  const annulerPeremption = form => {
    const timer = reviewTimers.get(form);
    if (timer === undefined) return;
    clearTimeout(timer);
    reviewTimers.delete(form);
  };

  const outputOf = form => form.querySelector("output");
  const prefixOf = form => form.dataset.formKey || "";
  const sanitize = name => String(name).replace(/[^A-Za-z0-9_-]/g, "-");

  const controlsOf = form =>
    Array.from(form.elements).filter(
      el => el.name && ["INPUT", "SELECT", "TEXTAREA"].includes(el.tagName)
    );

  // --- Saisies non terminées ----------------------------------------------

  // Chaque enregistrement du carnet recharge la page : une saisie encore ouverte dans un
  // autre formulaire disparaîtrait sans un mot. L'empreinte compare la saisie courante à
  // celle du chargement ; un formulaire enregistré (ou en cours d'envoi) est hors garde,
  // sans quoi la navigation qui suit un succès demanderait elle-même confirmation.
  const imprint = form => JSON.stringify(controlsOf(form).map(control => {
    if (control.type === "checkbox" || control.type === "radio") return control.checked ? 1 : 0;
    if (control.type === "file") return control.files?.length || 0;
    return control.value;
  }));

  // La garde ne s'arme que sur une saisie réelle de l'opérateur : les pages du carnet
  // réécrivent des champs au chargement (dates rendues dans le fuseau de l'appareil, mode
  // « Je démarre » qui recopie la date d'origine), et une empreinte prise avant ces
  // réécritures ferait croire à une saisie en cours sur chaque fiche ouverte. L'empreinte
  // est donc reprise à la fin de la tâche de chargement, et seule une modification issue
  // d'un événement de confiance rend le formulaire comparable.
  const guard = form => {
    if (guarded.has(form)) return;
    guarded.add(form);
    baselines.set(form, imprint(form));
    setTimeout(() => { if (!touched.has(form)) baselines.set(form, imprint(form)); }, 0);
    const touch = event => { if (event.isTrusted) touched.add(form); };
    form.addEventListener("input", touch);
    form.addEventListener("change", touch);
  };

  const disarm = form => {
    settled.add(form);
    guarded.delete(form);
    return discardDraft(form);
  };

  const pending = () => {
    for (const form of guarded) {
      if (!form.isConnected || settled.has(form) || busy.has(form) || !touched.has(form)) continue;
      if (imprint(form) !== baselines.get(form)) return true;
    }
    return false;
  };

  const previousDirty = window.PhytoForms?.isDirty;
  // Un envoi en cours protège aussi la page lors d’une activation de worker.
  window.PhytoForms = {isDirty: () => pending() || [...guarded].some(form => busy.has(form)) || Boolean(previousDirty?.())};

  // Brouillons : inscription explicite du formulaire ET des champs. Aucune mesure,
  // confirmation, photo ni commande ne peut entrer dans ce stockage auxiliaire.
  const DRAFT_TTL_MS = 86400000;   // 24 h : au-delà, la fiche a presque toujours bougé.
  // Plafond explicite, comme les 20 pages et les 40 photos de la PWA : un brouillon est du
  // texte d'opérateur en clair sur l'appareil, il n'a pas à s'accumuler sans borne. Le plus
  // ancien est évincé — c'est celui dont la fiche a le plus de chances d'avoir changé.
  const DRAFT_MAX = 50;
  const draftBindings = new WeakMap();
  let draftsDatabase;
  const draftDb = () => {
    if (!draftsDatabase) draftsDatabase = new Promise((resolve, reject) => {
      const request = indexedDB.open("phyto-culture-drafts", 1);
      let settled = false;
      const fail = error => {
        if (settled) return;
        settled = true; clearTimeout(timer); reject(error);
      };
      const timer = setTimeout(() => fail(new Error("Stockage indisponible")), 2000);
      request.onupgradeneeded = () => request.result.createObjectStore("drafts", {keyPath: "key"});
      request.onsuccess = () => {
        if (settled) { request.result.close(); return; }
        settled = true; clearTimeout(timer); resolve(request.result);
      };
      request.onerror = () => fail(request.error);
      request.onblocked = () => fail(new Error("Stockage bloqué"));
    });
    return draftsDatabase;
  };
  // L'expiration n'est vérifiée qu'à l'affichage d'une bannière : un brouillon d'une fiche
  // jamais rouverte ne se supprimerait donc nulle part. La purge se fait une fois par page,
  // à l'ouverture de la base, et ne bloque personne — elle est chaînée après la résolution.
  let draftsPurged = false;
  const purgeDrafts = async () => {
    if (draftsPurged) return;
    draftsPurged = true;
    const records = await draftOperation("getAll");
    const fresh = [];
    for (const record of records) {
      if (Date.now() - Number(record.at || 0) > DRAFT_TTL_MS) await draftOperation("delete", record.key);
      else fresh.push(record);
    }
    fresh.sort((left, right) => Number(right.at || 0) - Number(left.at || 0));
    for (const record of fresh.slice(DRAFT_MAX)) await draftOperation("delete", record.key);
  };
  const draftOperation = async (method, value) => {
    const db = await draftDb();
    return new Promise((resolve, reject) => {
      const tx = db.transaction("drafts", ["get", "getAll"].includes(method) ? "readonly" : "readwrite");
      const request = tx.objectStore("drafts")[method](value);
      tx.oncomplete = () => resolve(request.result);
      tx.onerror = () => reject(tx.error);
      tx.onabort = () => reject(tx.error);
    });
  };
  const draftControls = form => controlsOf(form).filter(control =>
    control.hasAttribute("data-draft-field") && !control.hasAttribute("data-secret") &&
    (control.tagName === "TEXTAREA" || control.tagName === "SELECT" ||
      (control.tagName === "INPUT" && ["text", "date", "datetime-local"].includes(control.type))) &&
    !/password|secret|confirm|csrf|token|ph$|ec$|volume|temperature/i.test(control.name));
  const draftContext = form => ({target: form.dataset.draftTarget || "", version: form.dataset.draftVersion || ""});
  // `discarded` est la garde anti-course, et elle n'a de sens que parce que la suppression
  // passe par la **même** file que les écritures : une frappe peut avoir mis un `put` en
  // vol au moment où l'opérateur supprime le brouillon (ou l'enregistre). Sans cette garde,
  // ce `put` s'exécuterait après le `delete` et ressusciterait un brouillon que personne ne
  // veut plus. Une frappe ultérieure remet `discarded` à faux, de façon synchrone : la
  // suppression n'interdit pas de recommencer une saisie.
  const discardDraft = async form => {
    const binding = draftBindings.get(form);
    if (!binding) return;
    binding.discarded = true;
    binding.queue = binding.queue
      .catch(() => {})
      .then(() => draftOperation("delete", binding.key))
      .catch(() => { /* Auxiliaire : une suppression impossible ne casse rien. */ });
    await binding.queue;
    binding.banner.hidden = true;
  };
  function registerDraft(form) {
    if (!form.dataset.cultureDraft || draftBindings.has(form) || !location.pathname.startsWith("/cultures")) return;
    const context = draftContext(form);
    const key = JSON.stringify([form.dataset.cultureDraft, context.target, context.version]);
    const banner = document.createElement("aside"); banner.className = "notice"; banner.hidden = true;
    banner.dataset.cultureDraftNotice = "";
    const message = document.createElement("p");
    const restore = document.createElement("button"); restore.type = "button";
    restore.textContent = "Restaurer le brouillon"; restore.className = "button button-secondary";
    const discard = document.createElement("button"); discard.type = "button";
    discard.textContent = "Supprimer le brouillon"; discard.className = "button button-secondary";
    banner.append(message, restore, discard);
    // La bannière doit être **découvrable** : les formulaires du carnet vivent le plus
    // souvent dans un `<details>` replié, où un `prepend` la rendrait invisible tant que
    // l'opérateur n'a pas déplié le bloc — exactement l'inverse de la promesse « note
    // récupérable après un arrêt du navigateur ». Le gabarit désigne donc l'emplacement
    // par `[data-culture-draft-banner="<clé>"]`, hors du repli ; à défaut, la bannière
    // reste en tête du formulaire. Le conteneur est cherché par comparaison de valeurs,
    // jamais par un sélecteur construit : une clé de formulaire est une donnée du gabarit,
    // pas un identifiant CSS. Une page qui répète le même formulaire (une fiche par ligne)
    // désigne l'emplacement par `data-draft-target` ; sans cible déclarée, le premier
    // emplacement portant la clé sert.
    const slots = [...document.querySelectorAll("[data-culture-draft-banner]")]
      .filter(node => node.dataset.cultureDraftBanner === form.dataset.cultureDraft);
    const slot = slots.find(node => node.dataset.draftTarget === context.target) || slots.find(node => node.dataset.draftTarget === undefined);
    if (slot) slot.append(banner); else form.prepend(banner);
    const binding = {key, banner, queue: Promise.resolve(), discarded: false}; draftBindings.set(form, binding);
    let saved = null;
    const unavailable = () => { banner.hidden = false; restore.hidden = true; message.textContent = "Brouillon local indisponible : stockage refusé ou saturé. La saisie reste dans cette page."; };
    const save = event => {
      if (!event.isTrusted || settled.has(form)) return;
      if (!draftControls(form).includes(event.target)) return;
      // Synchrone, avant toute mise en file : l'opérateur saisit de nouveau, le brouillon
      // redevient légitime même s'il venait d'être supprimé.
      binding.discarded = false;
      const fields = draftControls(form).map(control => ({name: control.name, value: control.value}));
      const record = {key, formKey: form.dataset.cultureDraft, ...draftContext(form), fields, at: Date.now()};
      binding.queue = binding.queue.catch(() => {}).then(() => {
        // Une suppression ou un enregistrement réussi arrivés entre-temps rendent cette
        // écriture sans objet : la laisser passer ferait réapparaître le brouillon.
        if (binding.discarded) return undefined;
        return draftOperation("put", record);
      }).catch(unavailable);
    };
    form.addEventListener("input", save); form.addEventListener("change", save);
    discard.addEventListener("click", () => discardDraft(form));
    restore.addEventListener("click", () => {
      const now = draftContext(form);
      if (!saved || now.target !== saved.target || now.version !== saved.version || Date.now() - saved.at > DRAFT_TTL_MS) {
        message.textContent = "Brouillon refusé : la cible ou la version de la fiche a changé, ou le brouillon a expiré.";
        restore.hidden = true; return;
      }
      const controls = draftControls(form);
      // Valider toutes les sélections et dates avant de modifier le moindre champ.
      const valid = saved.fields.every(field => {
        const control = controls.find(item => item.name === field.name);
        if (!control) return false;
        if (control.tagName === "SELECT" && ![...control.options].some(option => option.value === field.value && !option.disabled)) return false;
        const probe = control.cloneNode(true); probe.value = field.value;
        return probe.value === field.value && probe.checkValidity();
      });
      if (!valid) { message.textContent = "Brouillon refusé : vérifiez la cible et la date, devenues indisponibles ou invalides."; restore.hidden = true; return; }
      saved.fields.forEach(field => { controls.find(control => control.name === field.name).value = field.value; });
      keys.delete(form); reviews.delete(form); touched.add(form); settled.delete(form);
      form.dispatchEvent(new Event("input", {bubbles: true}));
      message.textContent = "Brouillon restauré, non enregistré. Vérifiez la cible et la date avant d’enregistrer en ligne.";
      restore.hidden = true;
    });
    // Cas nominal : une lecture par clé, pas un balayage de toute la base à chaque
    // formulaire inscrit. Le `getAll` ne sert qu'au message « brouillon d'une autre
    // version », et prend alors le plus récent — avec plusieurs versions périmées, le
    // premier venu aurait pu être le plus ancien.
    draftOperation("get", key).then(found => found || draftOperation("getAll").then(records => records
      .filter(item => item.formKey === form.dataset.cultureDraft && item.target === context.target)
      .sort((left, right) => Number(right.at || 0) - Number(left.at || 0))[0] || null)).then(record => {
      purgeDrafts().catch(() => { /* Auxiliaire : une purge impossible ne casse rien. */ });
      if (!record || touched.has(form)) return;
      saved = record; banner.hidden = false;
      if (Date.now() - record.at > DRAFT_TTL_MS || record.version !== context.version) {
        message.textContent = "Brouillon refusé : fiche modifiée ou expiration de 24 h dépassée."; restore.hidden = true;
        draftOperation("delete", record.key).catch(() => {}); return;
      }
      message.textContent = `Brouillon sur cet appareil, non enregistré (il y a ${Math.max(0, Math.round((Date.now() - record.at) / 60000))} min)`;
    }).catch(unavailable);
  }

  addEventListener("beforeunload", event => {
    if (!pending()) return;
    event.preventDefault();
    event.returnValue = LEAVING;
  });

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
        annulerPeremption(form);
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
      // L'aperçu local est branché ici, donc sur **tout** champ photo du carnet, et pas
      // page par page : les trois formulaires photo (observation de fiche, entrée du
      // journal, photo d'une entrée) le reçoivent sans l'écrire. Le branchement est
      // idempotent, `register` étant rejoué par `showErrors` et après un clonage.
      if (isPhotoField(control) && !previewBound.has(control)) {
        previewBound.add(control);
        attachPreview(form, control);
      }
    }
    guard(form);
    registerDraft(form);
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

  // --- Aperçu local d'une photo -------------------------------------------

  // Voir la photo choisie **avant** tout envoi est le seul moyen de vérifier qu'on envoie
  // la bonne : sur un téléphone, le sélecteur de fichiers ne rend qu'un nom. Cet aperçu
  // n'émet aucune requête et ne met rien en attente ; il ne fait que lire le fichier local
  // déjà choisi par l'opérateur. L'URL d'objet est révoquée à chaque changement, à la
  // remise à zéro du formulaire et au départ de la page : une image de 5 Mio retenue par
  // une URL oubliée resterait en mémoire tant que le document vit.
  // Tout est indexé par **contrôle**, jamais par formulaire : deux champs photo dans un
  // même formulaire partageraient sinon une URL et une zone, et le second effacerait
  // l'aperçu du premier.
  const previews = new Map();        // champ photo → URL d'objet en cours (itérable pour `pagehide`)
  const previewZones = new WeakMap(); // champ photo → conteneur d'aperçu qui lui appartient
  const previewBound = new WeakSet();
  const photoChoiceBound = new WeakSet();
  const photoCameraButtons = new WeakMap(); // champ photo → son bouton de prise de vue
  const resetBound = new WeakSet();  // formulaires dont la remise à zéro est déjà branchée
  const PREVIEW_ALT = "Aperçu local de la photo choisie, avant tout envoi.";

  const isPhotoField = control => control.type === "file" && /image/i.test(control.accept || "");

  // `capture` n'a pas un comportement uniforme : certains navigateurs ouvrent directement la
  // caméra et rendent le choix d'une image existante difficile. Deux actions explicites pilotent
  // le même champ et donc la même mutation/idempotence. Reprendre remplace simplement le File.
  function attachPhotoChoices(control) {
    if (photoChoiceBound.has(control)) return;
    photoChoiceBound.add(control);
    const actions = document.createElement("span");
    actions.className = "culture-photo-choices";
    const camera = document.createElement("button");
    camera.type = "button"; camera.className = "button button-secondary";
    camera.textContent = "Prendre une photo";
    camera.dataset.culturePhotoCamera = "";
    photoCameraButtons.set(control, camera);
    const library = document.createElement("button");
    library.type = "button"; library.className = "button button-secondary";
    library.textContent = "Choisir une image existante";
    library.dataset.culturePhotoLibrary = "";
    camera.addEventListener("click", () => {
      control.setAttribute("capture", "environment");
      control.click();
    });
    library.addEventListener("click", () => {
      control.removeAttribute("capture");
      control.click();
    });
    control.addEventListener("change", () => {
      camera.textContent = control.files?.length ? "Reprendre la photo" : "Prendre une photo";
    });
    actions.append(camera, library);
    (labelOf(control) || control).after(actions);
  }

  // Le conteneur est frère du `<label>` enveloppant, comme le message d'erreur, pour ne
  // pas entrer dans le nom accessible du champ. Un conteneur déjà posé par le gabarit
  // n'est adopté que s'il est le frère **suivant de ce champ-là** : une recherche dans
  // tout le formulaire rendrait la même zone à deux champs photo.
  function previewZone(control) {
    const known = previewZones.get(control);
    if (known?.isConnected) return known;
    const anchor = labelOf(control) || control;
    let zone = anchor.nextElementSibling;
    // `attachPhotoChoices` a déjà inséré ses deux boutons juste après l'ancre : une zone
    // fournie par le gabarit se trouve donc **derrière** eux. Sans ce saut, la branche
    // d'adoption était inatteignable — le socle créait une seconde zone et celle du
    // gabarit restait vide, à côté.
    if (zone?.classList.contains("culture-photo-choices")) zone = zone.nextElementSibling;
    if (!zone || !zone.hasAttribute("data-culture-photo-preview")) {
      zone = document.createElement("figure");
      zone.className = "culture-photo-preview";
      zone.setAttribute("data-culture-photo-preview", "");
      zone.hidden = true;
      anchor.after(zone);
    }
    previewZones.set(control, zone);
    return zone;
  }

  function clearControlPreview(control) {
    const url = previews.get(control);
    if (url) { URL.revokeObjectURL(url); previews.delete(control); }
    const zone = previewZones.get(control);
    if (!zone) return;
    zone.replaceChildren();
    zone.hidden = true;
  }

  // Signature conservée — les pages appellent `clearPreview(form)` après un enregistrement
  // réussi — mais l'effacement se fait champ par champ, chacun portant sa propre URL.
  function clearPreview(form) {
    if (!form) return;
    for (const control of controlsOf(form)) {
      if (isPhotoField(control)) clearControlPreview(control);
    }
  }

  function attachPreview(form, control) {
    attachPhotoChoices(control);
    control.addEventListener("change", () => {
      clearControlPreview(control);
      const chosen = control.files && control.files[0];
      if (!chosen) return;
      // Un fichier qui n'est pas une image n'a pas d'aperçu : `createObjectURL` rendrait
      // une URL parfaitement valide et l'`<img>` resterait cassé, donc visible et vide.
      // Le refus de fond, lui, reste au serveur.
      if (!/^image\//i.test(chosen.type)) return;
      const url = URL.createObjectURL(chosen);
      previews.set(control, url);
      const image = document.createElement("img");
      // Une image que le navigateur ne décode pas (fichier tronqué, format refusé) ne
      // laisse pas un cadre vide : la zone se referme et l'URL est révoquée.
      image.addEventListener("error", () => clearControlPreview(control));
      image.src = url;
      image.alt = PREVIEW_ALT;
      const zone = previewZone(control);
      zone.replaceChildren(image);
      zone.hidden = false;
    });
    // La remise à zéro est un événement du **formulaire** : une seule écoute par
    // formulaire, qui efface les aperçus de tous ses champs photo.
    if (!resetBound.has(form)) {
      resetBound.add(form);
      form.addEventListener("reset", () => {
        clearPreview(form);
        // Une remise à zéro vide toujours les champs fichier, et n'émet aucun `change` :
        // sans cette remise du libellé, le bouton proposerait « Reprendre la photo »
        // alors qu'aucun fichier n'est plus choisi. Le libellé est posé sans consulter
        // `control.files`, qui n'est vidé qu'**après** cet événement.
        for (const control of controlsOf(form)) {
          const camera = isPhotoField(control) ? photoCameraButtons.get(control) : null;
          if (camera) camera.textContent = "Prendre une photo";
        }
      });
    }
  }

  addEventListener("pagehide", event => {
    // Page mise en cache arrière/avant : elle peut revenir telle quelle, aperçus compris.
    // Révoquer ici laisserait des images cassées que rien ne recrée.
    if (event.persisted) return;
    for (const url of previews.values()) URL.revokeObjectURL(url);
    previews.clear();
  });

  function mark(control, message) {
    const label = labelOf(control);
    const errorId = `${control.id}-error`;
    let note = document.getElementById(errorId);
    if (!note) {
      // Le message est un frère du <label> enveloppant, jamais son enfant : tout texte
      // placé dans le label entre dans le nom accessible du champ (« Photo Photo
      // invalide… »), et le message serait annoncé deux fois, une fois comme nom et une
      // fois comme description. Il reste sous le champ grâce à `grid-column: 1 / -1`
      // dans les grilles du carnet. `unmark`/`clearField` le retrouvent par son identifiant.
      note = document.createElement("p");
      note.className = "field-error";
      note.id = errorId;
      (label || control).after(note);
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

  // Une ligne répétée (origine, ingrédient) se duplique par `cloneNode(true)` : le clone
  // recopierait sinon le message d'erreur de la ligne d'origine, avec son identifiant. Deux
  // éléments porteraient le même `id`, la nouvelle ligne s'afficherait refusée sans l'être,
  // et sa première saisie effacerait le message de l'ancienne. Ce nettoyage porte sur la
  // racine **et** ses descendants ; il est purement visuel et ne touche aucune valeur.
  function resetField(root) {
    if (!root) return root;
    const nodes = root.querySelectorAll ? [root, ...root.querySelectorAll("*")] : [root];
    for (const node of nodes) {
      if (node.classList?.contains("field-error")) { node.remove(); continue; }
      node.classList?.remove("field-invalid");
      if (!node.removeAttribute) continue;
      node.removeAttribute("aria-invalid");
      if (node.dataset && node.dataset.describedbyBase !== undefined) {
        const base = node.dataset.describedbyBase;
        if (base) node.setAttribute("aria-describedby", base);
        else node.removeAttribute("aria-describedby");
        delete node.dataset.describedbyBase;
      }
    }
    return root;
  }

  function clearErrors(form) {
    if (!form) return;
    form.querySelector(".culture-form-errors")?.remove();
    for (const control of controlsOf(form)) {
      if (control.hasAttribute("aria-invalid")) unmark(control);
    }
  }

  // Un champ refusé peut se trouver dans un repli : on l'ouvre avant de le viser, sans quoi
  // le focus se poserait sur un élément invisible. Seuls les replis sont ouverts : un
  // `hidden` posé par une règle de page (type d'origine semis/bouture, mode « Je démarre »,
  // ingrédients issus d'une recette) exprime une règle métier, pas un pliage. Le lever
  // afficherait un champ que la page a délibérément retiré de la saisie, sans jamais le
  // refermer. Un conteneur réellement repliable le déclare par `data-cf-collapsible`.
  function reveal(element) {
    for (let node = element; node && node !== document.body; node = node.parentElement) {
      if (node.tagName === "DETAILS") { node.open = true; node.hidden = false; continue; }
      if (node.hasAttribute("hidden") && node.hasAttribute("data-cf-collapsible")) node.hidden = false;
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

  // Un formulaire du carnet peut porter plusieurs boutons d'envoi — « Fait » et
  // « Reporter » d'un rappel, « Annuler ce rappel » sous son repli. N'en désactiver qu'un
  // pendant l'envoi laissait les autres cliquables : la garde `busy` refusait bien le
  // second envoi, mais l'opérateur voyait un bouton actif répondre « un envoi est déjà en
  // cours » au lieu d'un bouton visiblement indisponible.
  const submitButtons = form => Array.from(form.querySelectorAll('[type="submit"]'));

  // La clé d'idempotence est conservée tant que la saisie ne change pas : un même envoi
  // rejoué après une réponse perdue vérifie l'enregistrement au lieu d'en créer un
  // second. `crypto.randomUUID` n'existe pas hors contexte sécurisé (LAN en HTTP).
  //
  // La mémoire est indexée par **destination**, pas seulement par formulaire : un même
  // formulaire porte deux actes successifs et distincts (l'observation, puis sa photo).
  // Avec une mémoire unique, le second effaçait la clé du premier — reprendre la photo
  // puis réessayer l'observation repartait avec une clé neuve alors que le texte n'avait
  // pas bougé, ce qui aurait créé une seconde note si la première réponse s'était perdue.
  // C'est exactement le doublon que « Reprendre la photo » doit être incapable de faire.
  function requestKey(form, channel, signature) {
    let memo = keys.get(form);
    if (!memo) { memo = new Map(); keys.set(form, memo); }
    const known = memo.get(channel);
    if (!known || known.signature !== signature) {
      const fresh = {signature, value: identifier()};
      memo.set(channel, fresh);
      return fresh.value;
    }
    return known.value;
  }

  // Les gardes d'un envoi — hors ligne, envoi déjà en vol, boutons indisponibles pendant
  // la requête — ne dépendent pas du transport. Elles sont donc écrites une fois et
  // partagées par le chemin `fetch` (JSON, prévalidation) et le chemin `XMLHttpRequest`
  // (photo, avec progression). Deux copies auraient fini par diverger sur le seul point
  // qui compte : la réactivation des boutons dans le `finally`.
  async function withGuards(form, run) {
    if (isOffline()) {
      status(form, OFFLINE);
      return {ok: false, status: 0, data: {error: OFFLINE}, aborted: false, offline: true};
    }
    if (busy.has(form)) {
      return {ok: false, status: 0, data: {error: BUSY}, aborted: false, busy: true};
    }
    busy.add(form);
    // Seuls les boutons que cet envoi a désactivés sont réactivés : un bouton déjà
    // indisponible pour une autre raison le reste. La désactivation passe par la
    // propriété `disabled` et jamais par `aria-disabled`, qui n'empêcherait pas le clic.
    const disabled = submitButtons(form).filter(node => !node.disabled);
    for (const node of disabled) node.disabled = true;
    try {
      return await run();
    } finally {
      busy.delete(form);
      for (const node of disabled) node.disabled = false;
    }
  }

  function send(form, url, {headers, body, timeoutMs}) {
    return withGuards(form, async () => {
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
      }
    });
  }

  // `fetch` ne rend pas la progression d'un corps envoyé : une photo de 5 Mio sur un Wi-Fi
  // de serre laissait l'opérateur devant un texte figé, sans savoir si l'envoi avançait.
  // `XMLHttpRequest` la donne (`xhr.upload`), au prix d'un second transport — d'où le
  // contrat strict : **exactement** les quatre formes de retour du contrat — hors ligne,
  // occupé, réponse HTTP, réseau/délai — que `send` produit aussi, celui-ci y ajoutant
  // seulement le message d'une exception inattendue. Les appelants restent inchangés.
  // Aucun rejeu, aucune file, aucune reprise : un envoi interrompu se réessaie à la main,
  // avec la même clé d'idempotence.
  function sendUpload(form, url, {headers, body, timeoutMs, onProgress, onStart}) {
    return withGuards(form, async () => {
      // La barre n'existe **qu'ici**, à l'intérieur des gardes : créée avant, un envoi
      // refusé parce qu'un autre est déjà en vol en aurait ajouté une seconde, que le
      // `finally` de l'envoi en cours ne retire pas.
      const bar = onStart?.() ?? null;
      const report = event => { bar?.advance(event); onProgress?.(event); };
      try {
        return await new Promise(resolve => {
          // Un `open` ou un `send` qui lève (URL refusée, corps impossible à envoyer)
          // rejetterait la promesse et remonterait une exception aux appelants, qui
          // n'attendent que les quatre formes du contrat.
          try {
            const xhr = new XMLHttpRequest();
            // `open` avant tout `setRequestHeader` : l'ordre inverse lève une exception.
            xhr.open("POST", url);
            xhr.timeout = timeoutMs ?? UPLOAD_TIMEOUT_MS;
            for (const [key, value] of Object.entries({"X-CSRF-Token": csrf(), ...headers})) {
              if (value !== undefined && value !== null) xhr.setRequestHeader(key, String(value));
            }
            // Branchés avant `send` : un envoi très court émettrait sinon ses événements
            // avant que quiconque n'écoute, et la barre resterait indéterminée jusqu'à la
            // réponse.
            xhr.upload.addEventListener("progress", event => report({
              loaded: event.loaded, total: event.total, lengthComputable: event.lengthComputable,
            }));
            xhr.upload.addEventListener("load", () => report({done: true}));
            xhr.addEventListener("load", () => {
              let data;
              try { data = JSON.parse(xhr.responseText); } catch { data = null; }
              // 413, 415 et 408 sont refusés par aiohttp **avant** le carnet, en texte
              // brut : sans traduction ici, une photo trop grande n'aurait eu que le
              // refus générique du socle, qui ne nomme aucune limite. Les refus de fond
              // du carnet, eux, arrivent en JSON et gardent leur propre message.
              if (!data || typeof data !== "object") data = {error: UPLOAD_REFUSALS[xhr.status] || REFUSED};
              resolve({ok: xhr.status >= 200 && xhr.status < 300, status: xhr.status, data, aborted: false});
            });
            xhr.addEventListener("error", () =>
              resolve({ok: false, status: 0, data: {error: NO_ANSWER}, aborted: false}));
            xhr.addEventListener("timeout", () =>
              resolve({ok: false, status: 0, data: {error: NO_ANSWER}, aborted: true}));
            xhr.addEventListener("abort", () =>
              resolve({ok: false, status: 0, data: {error: NO_ANSWER}, aborted: true}));
            // Le `File` part tel quel : un `FormData` changerait le type du corps, que le
            // serveur exige binaire.
            xhr.send(body);
          } catch {
            resolve({ok: false, status: 0, data: {error: NO_ANSWER}, aborted: false});
          }
        });
      } finally {
        // La barre est retirée quelle que soit l'issue, et avant que l'appelant ne pose
        // son message : succès, refus, réseau ou délai laissent le même `<output>` propre.
        bar?.remove();
      }
    });
  }

  // La barre vit dans l'`<output role="status">` du formulaire, à côté du texte d'état
  // déjà posé par l'appelant, qui n'est pas réécrit. Cette région est **atomique** par
  // défaut : toute mutation de son sous-arbre la fait réannoncer en entier. La
  // `<progress>` y est donc ajoutée **une fois** — une seule annonce — et son avancement
  // ne passe ensuite que par ses attributs `value` et `aria-valuetext`, dont la mutation
  // ne réveille pas la région. Le texte visible du pourcentage, lui, est posé **hors** de
  // l'`<output>`, en frère immédiat, et retiré avec la barre : à l'intérieur, chaque pour
  // cent aurait été annoncé.
  function progressBar(form) {
    const output = outputOf(form);
    if (!output) return null;
    const bar = document.createElement("progress");
    bar.max = 100;
    bar.setAttribute("aria-label", "Progression de l’envoi de la photo");
    // Sans `value`, la barre est indéterminée : c'est l'état honnête tant qu'aucun
    // événement de progression n'est arrivé.
    const readout = document.createElement("span");
    readout.className = "culture-upload-readout";
    readout.setAttribute("aria-hidden", "true");
    output.append(bar);
    output.after(readout);
    return {
      advance(event) {
        if (event.done) {
          bar.value = 100;
          bar.setAttribute("aria-valuetext", "Envoi terminé");
          readout.textContent = "Envoi terminé, enregistrement en cours…";
          return;
        }
        if (!event.lengthComputable || !event.total) return;
        const percent = Math.max(0, Math.min(100, Math.round((event.loaded / event.total) * 100)));
        bar.value = percent;
        bar.setAttribute("aria-valuetext", `Envoi ${percent} %`);
        readout.textContent = `Envoi ${percent} %`;
      },
      remove() { bar.remove(); readout.remove(); },
    };
  }

  async function submitJson(form, url, body, options = {}) {
    register(form);
    const command = {...body};
    let changed = false;
    const change = () => { changed = true; };
    const signature = JSON.stringify(command);
    command.request_id = requestKey(form, url, signature);
    const domain = url === "/api/v1/cultures" ? "culture" : url === "/api/v1/cultures/solutions" ? "solution" : null;
    // La prévalidation coûte au serveur une transaction complète sur le thread unique du
    // carnet : elle n'est pas faite à chaque enregistrement. Trois cas la justifient — le
    // bouton « Vérifier avant d'enregistrer », qui ne demande rien d'autre ; le premier
    // envoi d'un relevé de solution, seul chemin qui cherche des ressemblances ; et une
    // transition guidée, qui change l'état de la fiche. Une saisie déjà vérifiée (même
    // empreinte, vérification non expirée) repart directement vers la mutation, qui
    // revalide de toute façon.
    const verifying = Boolean(reviewOnly.get(form));
    const seeksMatches = domain === "solution" && body.operation === "entry" && body.kind === "reading";
    // Transition guidée (`options.guided`) : une opération qui déplace le stade, l'espace
    // ou la clôture montre son avant/après avant d'écrire. Le panneau **est** la
    // confirmation — le clic suivant sur l'enregistrement, comme le bouton du panneau,
    // envoie la mutation — et toute modification de la saisie le retire, ce qui redemande
    // la vérification. La liste des opérations concernées vient du serveur, pas d'ici.
    const guided = domain === "culture" && Boolean(options.guided);
    const known = reviews.get(form);
    const reviewed = Boolean(known && known.signature === signature);
    if (reviewed && !verifying) {
      // Une ressemblance affichée et non confirmée reste un arrêt : rien n'est envoyé.
      if (known.matches !== "[]" && !known.confirmed) {
        status(form, CONFIRM_MATCH);
        return {ok: false, preview: true};
      }
    }
    if (domain && (verifying || ((guided || seeksMatches) && !reviewed))) {
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
      // Un refus de fond (400) ou un conflit (409) est le même refus que celui de la
      // mutation : il s'affiche au champ et rien n'est envoyé. Une vérification qui
      // n'aboutit pas — carnet occupé, réseau, délai dépassé — n'est pas un refus : elle ne
      // doit pas empêcher un enregistrement que le serveur revalidera.
      if (!checked.ok) {
        if (checked.offline || checked.busy || checked.status === 400 || checked.status === 409) return checked;
        if (verifying) return checked;
        status(form, PREVIEW_DOWN);
      } else if (isOffline()) {
        status(form, OFFLINE);
        return {ok: false, offline: true};
      }
      // Une réponse tardive ne peut qualifier une saisie modifiée pendant la requête.
      // Les événements de saisie invalident également toute confirmation précédente.
      const previous = reviews.get(form);
      const matches = JSON.stringify(checked.data.similar || []);
      const acknowledged = previous?.signature === signature && previous?.matches === matches && previous?.confirmed;
      // Une vérification qui n'a pas abouti n'a rien à montrer : le panneau ne se construit
      // que sur une réponse. Un rejeu (`replay`) désigne un enregistrement déjà accepté :
      // il n'y a plus de transition à confirmer, la mutation rendra le même résultat.
      const showPanel = checked.ok && (reviewOnly.get(form) || (guided && !checked.data.replay)
                                       || (checked.data.similar?.length && !acknowledged));
      if (showPanel) {
        form.querySelector(".culture-review")?.remove();
        const panel = document.createElement("section");
        panel.className = "notice culture-review";
        panel.tabIndex = -1;
        // Le panneau apparaît et disparaît sans action de l'opérateur : il s'annonce.
        panel.setAttribute("aria-live", "polite");
        const title = document.createElement("h3");
        title.textContent = "Vérification avant enregistrement";
        panel.append(title);
        for (const line of checked.data.summary || []) {
          const p = document.createElement("p"); p.textContent = line; panel.append(p);
        }
        // Actions nommées par le serveur : des liens de lecture vers une page du carnet.
        // Aucun n'écrit quoi que ce soit et aucun ne vaut confirmation. Un `href` qui n'est
        // pas un chemin local est ignoré plutôt que rendu : « /… » seul ne suffit pas, car
        // « //hôte/chemin » est une URL absolue de protocole relatif, donc un autre site.
        for (const item of checked.data.links || []) {
          if (!item || typeof item.href !== "string"
              || !item.href.startsWith("/") || item.href.startsWith("//")) continue;
          const link = document.createElement("a");
          link.href = item.href;
          link.textContent = String(item.label || item.href);
          const p = document.createElement("p"); p.append(link); panel.append(p);
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
        note.textContent = guided
          ? "Rien n’est encore enregistré. Confirmez pour écrire cette transition ; le serveur revérifiera le carnet."
          : "Rien n’est enregistré. Utilisez le bouton d’enregistrement pour confirmer ; le serveur vérifiera à nouveau le carnet.";
        panel.append(note);
        if (guided) {
          // Le panneau ne consomme pas la vérification : ce bouton renvoie simplement le
          // formulaire, qui repart avec la même empreinte et va cette fois jusqu'à la
          // mutation. Rien n'est mémorisé ici que la vérification déjà enregistrée.
          const confirm = document.createElement("button");
          confirm.type = "button";
          confirm.className = "button";
          confirm.textContent = "Confirmer et enregistrer";
          confirm.addEventListener("click", () => form.requestSubmit());
          panel.append(confirm);
        }
        form.prepend(panel); status(form, ""); focusOn(panel);
        reviewTimers.set(form, setTimeout(() => {
          reviewTimers.delete(form);
          if (reviews.get(form) !== memo) return;
          reviews.delete(form); panel.remove();
          status(form, "Vérification expirée : vérifiez à nouveau les données du carnet avant d’enregistrer.");
        }, PREVIEW_VALIDITY_MS));
        reviewOnly.delete(form);
        return {ok: false, preview: true};
      }
    }
    // La péremption de la vérification n'a plus d'objet une fois la mutation partie.
    // Laissée courir, elle écrasait trente secondes plus tard le refus que le serveur
    // venait d'afficher — l'opérateur voyait « Vérification expirée » à la place du motif
    // du refus, et sa saisie restait pourtant refusée.
    annulerPeremption(form);
    const answer = await send(form, url, {
      headers: {"Content-Type": "application/json"},
      body: JSON.stringify(command),
      timeoutMs: options.timeoutMs ?? 15000,
    });
    if (answer.ok) await disarm(form);
    return answer;
  }

  async function submitBinary(form, url, blob, metadata, options = {}) {
    register(form);
    const command = {...metadata};
    // L'identité du fichier fait partie de la saisie : une autre photo est un autre envoi.
    const signature =
      JSON.stringify(command) + `|${blob?.name || ""}:${blob?.size || 0}:${blob?.lastModified || 0}`;
    command.request_id = requestKey(form, url, signature);
    // La barre est posée par `sendUpload`, une fois les gardes franchies, et retirée par
    // lui quelle que soit l'issue : un envoi refusé hors ligne ou parce qu'un autre est
    // déjà en vol n'en laisse aucune trace.
    // Aucun `form.reset()` ici — en échec, la légende saisie et le fichier choisi restent
    // en place, donc la clé d'idempotence aussi, et le renvoi vérifie le même
    // enregistrement au lieu d'en créer un second.
    const answer = await sendUpload(form, url, {
      headers: {
        // VITAL : sans en-tête explicite, `XMLHttpRequest` déduirait le type du `File`
        // (`image/png`) et le serveur répondrait 415.
        "Content-Type": "application/octet-stream",
        "X-Culture-Metadata": encodeURIComponent(JSON.stringify(command)),
      },
      body: blob,
      timeoutMs: options.timeoutMs ?? UPLOAD_TIMEOUT_MS,
      onStart: () => progressBar(form),
      onProgress: options.onProgress,
    });
    if (answer.ok) await disarm(form);
    return answer;
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

  // Les aides de la fiche apparaissent, se remplacent et se retirent seules : la zone qui
  // les porte s'annonce. Le marquage est posé ici, pas dans le gabarit : la zone n'est une
  // région vivante que parce qu'un script l'alimente.
  for (const zone of document.querySelectorAll("[data-culture-assistance]")) {
    if (!zone.hasAttribute("aria-live")) zone.setAttribute("aria-live", "polite");
  }

  window.PhytoCultureForms = {
    register,
    submitJson,
    submitBinary,
    showError,
    showErrors,
    clearErrors,
    clearField,
    // L'aperçu est posé par le socle : c'est aussi lui qui sait le retirer, et les pages
    // n'ont plus à connaître l'URL d'objet ni le conteneur.
    clearPreview,
    resetField,
    // Exposé pour que les pages qui visent une ancre appliquent la **même** règle de
    // dévoilement que les refus : ouvrir un repli, jamais un bloc masqué par une règle
    // métier. Deux règles concurrentes finiraient par diverger.
    reveal,
    status,
  };
})();
