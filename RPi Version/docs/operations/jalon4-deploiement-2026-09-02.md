# Jalon 4 — déploiement et qualification sur le Pi de production (2 septembre 2026)

Trois commits poussés et déployés **un par un** sur `feature/qol-operator-experience`, chacun
qualifié avant le suivant. Pi `phytocontroller`, service `phyto`, déploiement par
`scripts/deploy.sh` (sauvegarde de la config vivante, `compileall` avant coupure, sonde de santé
stable 15 s, rollback automatique sinon).

## Référence d'avant-déploiement

Commit servi `2ecefb1`, santé complète, 0 alarme, heure `synchronized`.
Climat en `MANUEL`, chauffage OFF, moteur vitesse 2, T = 22,86 °C, seuil de ventilation 25,0 °C.

| Broche | Rôle | Polarité | Niveau |
|---|---|---|---|
| 5 | daily_1 | actif-BAS | LOW (ON) |
| 18 | daily_2 | actif-BAS | HIGH (OFF) |
| 27 | cyclic_1 | actif-BAS | LOW (ON) |
| 22 | cyclic_2 | actif-BAS | bascule |
| 23 | heater | actif-BAS | HIGH (OFF) |
| 25 / 8 / 7 / 1 | moteur 1-4 | actif-HAUT | 8 HIGH (vitesse 2) |

## Commit 1 — `a058be3` overrides force-OFF

Déploiement stable du premier coup (2 commits appliqués, `fca1339` de documentation inclus).

| Contrôle | Résultat |
|---|---|
| Version servie | `a058be3` sur `/health/live` |
| `/api/v1/state` | clé `overrides` additive, plafonds publiés (240 min chauffage et moteur, 1440 ailleurs) |
| Tableau de bord | section « Interventions », 6 cartes, 7 dialogues (6 cibles + « tout couper ») |
| Coupure d'une sortie | `daily_2` coupé, GPIO 18 maintenu HIGH, actionneur en mode « forçage opérateur », `tracking: ok` |
| Persistance | section `overrides` écrite **sans** `deadline_mono` |
| Secret | la raison saisie absente de `phyto.log` **et** de `journalctl` (0 occurrence) ; le journal ne porte que cible et durée |
| Relance ciblée | `Tâche « daily_timer_2 » rechargée volontairement` |
| **Verrou moteur absolu** | mode `manual` vitesse 2 (GPIO 8 HIGH) → **quatre broches moteur LOW**, état `FORCAGE_OFF`, `motor_forced_off: true`, aucune alarme parasite |
| Alarme de verrou | non levée à 22,9 °C < seuil 25,0 °C — conforme, elle ne se déclenche qu'au-dessus du seuil |
| Levée | `target=all` → moteur revenu à la vitesse 2 (GPIO 8 HIGH), persistance vidée |
| Expiration automatique | forçage de 30 s : actif à 5 s, purgé à 65 s, `Forçage « arrêt » expiré sur daily_2` |
| Reprise au redémarrage | forçage de 10 min conservé au `systemctl restart`, `confirmed: true`, 577,8 s restantes |

## Commit 2 — `865b789` console

| Contrôle | Résultat |
|---|---|
| Flux SSE | charges JSON valides, exactement `{ts, level, logger, message}` |
| Barre d'outils | niveau, composant, recherche, pause, suivi, copie, téléchargement, effacement, compteurs |
| Bornes | `HISTORY_SIZE = 2000` côté serveur, `MAX_RECORDS = 2000` côté navigateur |
| XSS | aucun `innerHTML` dans le code servi |
| Liens d'alarme | `/console?component=phyto.influx&level=WARNING`, idem `time` et `network`, `disque` en recherche |
| Empreinte | RSS 57,9 Mo, charge 0,68 |

Aucun enregistrement multi-ligne observé en marche normale : `pretty_console.box()` replie déjà ses
encadrés sur une ligne avant le handler. La découpe reste un filet de sécurité, couverte par test.

## Commit 3 — `fa63006` reboot / extinction

Contrôles sans coupure : `system.js` servi (200), `FAILURE_AFTER_MS = 30000`, `REQUIRED_ALIVE = 2`,
`replaceState(null, "", "/")` présents, aucun `innerHTML`, asset **non** préchargé par la PWA,
`GET /actions/system/reboot` → 405, `POST` sans jeton → 403.

**Redémarrage réel**, sur accord explicite de l'opérateur :

- `POST /actions/system/reboot` → **HTTP 202 à 10:32:51**, page de suivi rendue
  (`data-system-action="reboot"`) **avant** que la commande ne parte. C'est le défaut central
  corrigé : l'ancien `await process.wait()` ne revenait jamais ;
- disparition confirmée à 10:32:59, retour à 10:33:07 ;
- redémarrage authentifié par le changement de `boot_id`
  (`23cd2c44…` → `94c0e7b7…`) et `uptime` remis à zéro — environ 15 s ;
- **deux réponses `/health/live` consécutives** en 200 portant `fa63006`, exactement ce que la page
  exige avant d'annoncer le retour ;
- minuteries cycliques reprises depuis `runtime_state.json` (127 s et 8354 s restantes) ;
- **GPIO identiques à la référence**, aux deux polarités.

Deux alarmes transitoires au retour, toutes deux attendues et auto-résolues : heure `plausible`
avant resynchronisation NTP (pas de RTC sur ce Pi), et `influx_unavailable` le temps qu'InfluxDB
redémarre. `control_healthy` est resté **vrai** pendant les deux — le partage contrôle/auxiliaire du
jalon 2 fait exactement son travail. Retour à 0 alarme à 10:34:20.

## État final

`fa63006`, santé complète, 0 alarme, 0 forçage, heure `synchronized`, climat `MANUEL` à 22,94 °C,
onze routes et assets en 200, cycle création/annulation de forçage rejoué après redémarrage,
`runtime_state.json` propre, GPIO conformes.

## Coupure en pleine impulsion — qualifiée sur la serre en marche (10:40)

Cible choisie : `cyclic_2` « Ventilation croissance », un ventilateur, et non `cyclic_1` « Pompes ».
La tâche était à l'intérieur de `with comp.energized(): await hb_sleep(...)`, phase ON séquentielle.

- GPIO 22 à LOW (ON), actionneur `mode: séquentiel`, `reason: phase ON (jour)` ;
- création du forçage → `Tâche « cyclic_timer_2 » rechargée volontairement`, et **dans la même
  seconde** `GPIO 22 ← OFF (HIGH - inactif)` : c'est le `finally` d'`energized()` qui a coupé sur
  annulation de la tâche, pas la boucle au tour suivant ;
- à l'expiration : `Cyclic #2 : reprise de la phase ON (7890 s restantes)` puis
  `GPIO 22 ← ON (LOW - actif)`. La phase reprend depuis `runtime_state.json`, elle n'est pas relancée
  du début.

Santé complète, 0 alarme, `tracking: ok` de bout en bout.

## Reste ouvert

- Observation longue de la console à 2 000 lignes (elle demande des heures, pas une vérification
  ponctuelle).
- **Coupure sur faute** : provoquer une exception ou un blocage dans une boucle de contrôle n'a
  aucun interrupteur — il faudrait faire tourner du code volontairement cassé sur la serre, et si le
  garde-fou testé est justement celui qui manque, le mode de panne est un relais resté fermé sur une
  charge réelle. Le comportement logiciel est déjà prouvé par la suite
  (`test_energized_coupe_sur_sortie_normale_et_exception`,
  `test_energized_coupe_sur_annulation`, `test_crash_applique_etat_sur_avant_relance`,
  `test_tache_bloquee_est_annulee_mise_en_securite_et_relancee`) ; ce qui manque est la moitié
  **électrique**, qui relève de `docs/development/hardware-validation.md`.

## Note d'exploitation

Les scripts sont suivis en mode `100644` (l'arbre de travail vit sur un montage Windows qui ne
conserve pas le bit d'exécution) : sur le Pi, `deploy.sh` doit être lancé par
`bash "RPi Version/scripts/deploy.sh" <cible>`, sans quoi le shell répond `Permission denied`.
