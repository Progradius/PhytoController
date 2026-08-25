# TODO — Audit 2026-08-25, Phase 1 (chantier « état sûr », structurel)

Plan source : `AUDIT-2026-08-25.md` § 8. Périmètre **volontairement réduit** :
le PinRegistry central et la migration des broches moteur sont relogés plus bas
(décision du 25/08/2026 : pas de changement de brochage maintenant).

## Fait

- [x] **1.1 Superviseur de tâches** *(C6)* — `utils/supervisor.py`.
      `TaskSupervisor.register(nom, fabrique, safe_state=…, max_silence=…)` puis
      `start()` / `wait()`. Chaque travail tourne dans un runner
      `while True: try/except` :
      • back-off exponentiel 5 s → 300 s, réarmé à 5 s si la tâche a tenu ≥ 10 min ;
      • **état sûr repositionné AVANT chaque relance** (sortie coupée, moteur à 0) ;
      • le travail s'exécute dans une tâche *fille* — le veilleur peut l'annuler
        sans tuer le runner, qui doit survivre à tout ;
      • une annulation venue de l'arrêt du processus est propagée telle quelle.
      `PuppetMaster` n'appelle plus `loop.create_task()` : il enregistre 8 travaux
      et attend le superviseur (plus d'`asyncio.Event().wait()` qui faisait passer
      pour sain un processus dont les 8 tâches étaient mortes).

- [x] **1.2 Battements de cœur** *(C6, E2)* — `beat()` en tête de chaque tour de
      boucle et `supervisor.sleep()` à la place d'`asyncio.sleep()` dans
      `timer_daily`, `timer_cyclic`, `temp_control`, `heat_control`,
      `write_sensor_values`. L'attente est découpée en tranches de 30 s battues :
      une sieste voulue de 10 jours (cyclic journalier) n'est pas un blocage.
      Le travail courant est porté par un `contextvars` posé par le runner —
      aucune signature métier ne transporte le superviseur.
      Un travail vivant mais muet > 300 s est annulé et relancé (`_watch_stalls`).
      `http_server` est enregistré avec `max_silence=None` : attendre une connexion
      **est** son fonctionnement normal.

- [x] **1.3 Contexte `energized()`** *(E5)* — `Component.energized()`, seul motif
      autorisé pour un couple ON / attente / OFF. Le `finally` coupe la sortie sur
      exception, sur annulation (relance par le superviseur, arrêt du processus) et
      en sortie normale, puis **vérifie** que la broche est bien retombée : sinon
      seconde tentative, puis alarme CRITICAL (« sortie potentiellement collée »).
      Branché sur les deux modes de `timer_cyclic` (journalier et séquentiel), qui
      laissaient l'électrovanne ouverte indéfiniment si l'attente était interrompue.

- [x] **1.4 Watchdog piloté par la santé** *(E2)* — `utils/watchdog.py`, thread
      supprimé de `main.py`. La caresse est **conditionnée** à
      `supervisor.is_healthy()` : dès qu'un travail est mort ou muet, on cesse de
      caresser et le redémarrage arrive. Deux voies, jamais les deux :
      systemd (`NOTIFY_SOCKET` + `WATCHDOG_USEC` → `WATCHDOG=1`, plus un `STATUS=`
      lisible dans `systemctl status`) ou `/dev/watchdog` en direct.
      Le descripteur est ouvert **une fois** et gardé au niveau module : le magic
      close (`V`) doit être écrit sur *ce* descripteur — l'ancien code rouvrait le
      périphérique et échouait en `EBUSY`, laissant le watchdog armé.
      Défaut inversé : activé, `PHYTO_HW_WATCHDOG=0` pour l'opt-out.
      La boucle tourne dans l'event loop, pas dans un thread : un event loop bloqué
      doit cesser de caresser, c'est précisément le défaut recherché.

- [x] **1.5 `/status` : compteurs et alarmes** *(C6, report Phase 0)* — `/status`
      publie `healthy`, `tasks` (par travail : `alive`, `healthy`, `silence_s`,
      `restarts`, `stalls`, `last_error`) et `heater_alarm`, l'alarme chauffage de
      la Phase 0 qui n'était encore exposée que par `get_heater_alarm()`.

## À faire sur le Pi (hors dépôt)

- [ ] **Unité systemd** — pour activer la voie sd_notify, ajouter à
      `/etc/systemd/system/phyto.service` :

      ```ini
      [Service]
      Type=notify
      NotifyAccess=main
      WatchdogSec=600
      Restart=always
      ```

      `WatchdogSec` doit être **plus grand** que le silence toléré par le
      superviseur (`MAX_SILENCE_SECONDS = 300 s`), sinon systemd redémarre le
      service avant que le superviseur ait eu le temps de relancer la tâche.
      600 s = 2× la marge : le superviseur agit d'abord, systemd n'intervient que
      s'il a lui-même échoué.
      Sans `Type=notify`, rien ne casse : `sd_notify` est un no-op et l'ouverture
      de `/dev/watchdog` échoue en `EBUSY` (systemd le tient déjà via
      `RuntimeWatchdogSec=15`) — c'est journalisé, le service continue.
- [ ] Vérifier au log de démarrage : `Tâches supervisées : daily_timer_1, …,
      http_server` puis, selon la configuration, `Watchdog systemd actif …` ou
      `Watchdog matériel armé` / `Watchdog matériel non disponible : … EBUSY`.
- [ ] Contrôler `curl http://<pi>:8123/status | jq .tasks` après quelques heures :
      `restarts` et `stalls` doivent rester à 0.

## Relogés — Phase 1 non traitée (décision du 25/08/2026)

- [ ] **1.A PinRegistry central** *(C1, C2b, C5-GPIO, C6-listes, M1, F1)* —
      allocation exclusive d'une broche à un propriétaire, état sûr déclaré par
      broche (HIGH/LOW/INPUT), validation d'unicité + liste noire
      `{0,1,2,3,7,8,14,15}`. Alimenterait l'init, la séquence d'arrêt **et** la
      génération de `config.txt`. Aujourd'hui les listes `GENERIC_SAFE_PINS` /
      `MOTOR_PINS` de `main.py` sont tenues à la main et rien n'interdit d'affecter
      deux fois la même broche depuis `/conf`.
      *Reporté : suppose de figer le brochage, ce qui n'est pas souhaité maintenant.*
- [ ] **1.B Migration des broches moteur vers GPIO ≥ 9** *(C1)* — sans fonction
      alternative. Recouvre le point déjà ouvert dans `tasks/todo.md` (vitesse 4 sur
      BCM 1 = `ID_SC`, cible proposée BCM 16).
      *Reporté : aucun changement de brochage pour l'instant.*
- [ ] **1.C Garde-fous matériels** *(C1, C2, C3, E1, E3)* — hors code, seuls
      remèdes à la fenêtre de boot et aux coupures brutales :
      pull-down 4,7 kΩ sur les entrées moteur + pull-up sur les entrées actives-BAS ;
      **thermostat / fusible thermique en série sur le chauffage** ; watchdog externe
      coupant l'alimentation de la carte relais ; interlock électromécanique entre
      les 4 vitesses moteur.

## Points de suivi laissés ouverts par la Phase 1

- `MAX_SILENCE_SECONDS` est une constante de `PuppetMaster` (300 s), pas un champ
  de `param.json` — même raison qu'en Phase 0 : un nouveau champ ferait diverger le
  `param.json` du dépôt de celui du Pi. À reprendre avec le `ConfigStore` (Phase 3).
- Le veilleur de silence relance une tâche bloquée, mais si c'est l'**event loop
  entier** qui est gelé (appels bloquants `requests` / busy-wait HC-SR04, audit E4)
  le veilleur est gelé lui aussi : seul le watchdog rattrape ce cas, et uniquement
  parce que la caresse a lieu dans l'event loop. Le vrai correctif est la frontière
  I/O de la Phase 4.
- `timer_cyclic` en mode journalier dort toujours des jours entiers dans une seule
  itération (E6/E7) : les battements masquent le symptôme (la tâche n'est plus vue
  comme morte) mais l'ordonnanceur à échéances absolues reste à faire en Phase 2.
