# components/climate_policy.py
# Author  : Progradius
# License : AGPL-3.0
# -------------------------------------------------------------
#  Arbitre thermique — décision pure (audit C8, C9, C10, E8, E9, E10, M11, M13, M14)
# -------------------------------------------------------------
"""
Chauffage et ventilation régulent la **même** température. Tant qu'ils étaient
pilotés par deux boucles indépendantes, ils se contredisaient en permanence :
sur toute la bande de consigne, le chauffage chauffait pendant que l'extracteur
évacuait (audit C9), et en mode hiver l'humidité court-circuitait le quota de
renouvellement (C8).

Ce module ne contient **que la décision**, sous forme d'une fonction pure :

    decide(settings, inputs, memory) -> (ClimateDecision, ClimateMemory)

Aucun GPIO, aucun accès disque, aucune horloge implicite : le temps entre par
`ClimateInputs`, l'état par `ClimateMemory` (gelé, sérialisable). La même
séquence d'entrées produit toujours la même séquence de décisions, ce qui rend
la régulation rejouable à la main — la seule façon d'auditer une logique qui
commute du 230 V.

Invariants tenus ici :

* **zone morte garantie par construction** — le seuil de ventilation ne peut
  jamais descendre sous le seuil d'extinction du chauffage augmenté de
  `vent_deadband` ; il n'existe donc aucune température à laquelle les deux
  organes soient actifs (C9) ;
* **quota unique** — tout renouvellement d'air en mode hiver consomme un budget
  borné, compté en minutes **réellement écoulées** (C8, M14), et la
  déshumidification a son propre budget borné, explicite ;
* **plancher thermique absolu** — sous `absolute_floor_temp`, aucune
  ventilation, quel que soit le budget restant ;
* **hystérésis à état + temps de maintien** — un palier ne se relâche que sous
  un seuil distinct et jamais avant `min_dwell_seconds` (E9) ;
* **repli nommé sur capteur mort** — `REPLI_CAPTEUR` : chauffage coupé, moteur à
  la vitesse de repli, alarme persistante (C10) ;
* **un ordre d'arrêt reste un arrêt** — le clamp ne remonte jamais un 0 vers
  `min_speed` (M13).
"""

from __future__ import annotations

from dataclasses import dataclass, replace

# ─────────────────────────────────────────────────────────────
#  Garde-fous de sécurité (hérités de la Phase 0, audit C10)
# ─────────────────────────────────────────────────────────────
# Hors de ces bornes, la valeur vient d'un bus perturbé, pas d'une mesure : on
# la traite comme une lecture manquée plutôt que de réguler dessus.
TEMP_VALID_MIN = -20.0
TEMP_VALID_MAX = 60.0
# L'humidité relative n'a de sens que dans [0 ; 100].
RH_VALID_MIN = 0.0
RH_VALID_MAX = 100.0

# Lectures invalides consécutives tolérées avant de couper. À 30 s de période,
# cela laisse 2 min 30 au capteur pour se rétablir.
MAX_CONSECUTIVE_SENSOR_FAILURES = 5
ALARM_CONTINUOUS_LIMIT = "heater_continuous_limit"
ALARM_SENSOR_FALLBACK = "sensor_fallback"
# Le forçage « arrêt » moteur est **absolu** (arbitrage opérateur du 28/08/2026) :
# il prime sur `SECURITE_HAUTE`. La protection contre la surchauffe est donc
# remplacée par cette alarme — un défaut *subi*, à la différence du forçage
# lui-même qui est un acte volontaire et n'entre pas au centre d'alarmes.
ALARM_MOTOR_LOCKOUT = "motor_lockout_overheat"

# Durée maximale d'allumage continu, **indépendante du capteur** : même avec une
# température parfaitement valide mais bloquée sur une valeur basse (défaut
# classique du BME280 sur bus perturbé), le chauffage ne peut pas rester ON
# indéfiniment.
MAX_CONTINUOUS_ON_MINUTES = 120
# Repos imposé après une coupure sur durée max, sinon la condition
# `temp <= temp_min` rallumerait au tick suivant.
FORCED_OFF_COOLDOWN_MINUTES = 15

# Fenêtre glissante des budgets hiver.
QUOTA_WINDOW_SECONDS = 3600.0
# Un tick « perdu » (tâche relancée, machine suspendue) ne doit pas créditer des
# heures de ventilation d'un coup : l'écart pris en compte est plafonné.
MAX_TICK_CREDIT_SECONDS = 300.0

# ─────────────────────────────────────────────────────────────
#  États de l'arbitre — vocabulaire unique, exposé tel quel par l'API
# ─────────────────────────────────────────────────────────────
STATE_DISABLED = "DESACTIVE"          # régulation thermique coupée (chauffage off, moteur libre)
STATE_HEAT = "CHAUFFER"
STATE_NEUTRAL = "NEUTRE"
STATE_VENT = "VENTILER"
STATE_RENEW = "RENOUVELER"            # renouvellement d'air hiver (quota)
STATE_DEHUMIDIFY = "DESHUMIDIFIER"    # ventilation pilotée par l'humidité (budget dédié)
STATE_OVERHEAT = "SECURITE_HAUTE"
STATE_FLOOR = "PLANCHER_THERMIQUE"    # sous le plancher absolu : plus aucune ventilation
STATE_SENSOR_FALLBACK = "REPLI_CAPTEUR"
STATE_MANUAL = "MANUEL"
STATE_FORCED_OFF = "FORCAGE_OFF"      # forçage opérateur borné (jalon 4)

# Motifs de crédit des budgets hiver (mémorisés d'un tick à l'autre).
CREDIT_RENEW = "renew"
CREDIT_HUMIDITY = "humidity"


# ─────────────────────────────────────────────────────────────
#  Entrées / sorties
# ─────────────────────────────────────────────────────────────
@dataclass(frozen=True)
class ClimateSettings:
    """Consignes extraites de `AppConfig` pour la phase jour ou nuit en cours."""

    heater_enabled: bool
    temp_min: float
    temp_max: float
    heater_hysteresis: float
    vent_deadband: float
    vent_step: float
    vent_release: float
    absolute_floor_temp: float
    min_dwell_seconds: float

    motor_mode: str
    motor_user_speed: int
    min_speed: int
    max_speed: int
    sensor_fallback_speed: int

    winter_default_speed: int
    winter_temp_margin: float
    winter_refresh_speed: int
    winter_refresh_minutes_per_hour: float
    winter_humidity_threshold: float
    winter_humidity_minutes_per_hour: float

    # --- seuils dérivés ---------------------------------------
    @property
    def heater_off_threshold(self) -> float:
        """Température au-dessus de laquelle le chauffage s'éteint."""
        return self.temp_min + self.heater_hysteresis

    @property
    def vent_threshold(self) -> float:
        """
        Température de démarrage de la ventilation.

        `max(...)` et non la seule consigne haute : c'est ici que la zone morte
        est **garantie par construction**. Une config où `target_temp_max` est
        sous `temp_min + hysteresis + vent_deadband` (cas du param.json déployé :
        23 / 25 / 2) ferait sinon ventiler pendant que le chauffage chauffe.
        Relever le seuil est préférable à un validateur qui refuserait la
        configuration : une config refusée, c'est un boot mort.

        Chauffage désactivé, en revanche, il n'y a **pas deux organes à
        séparer** : relever le seuil ne ferait que laisser monter la serre d'un
        degré sans rien protéger. La consigne haute s'applique alors telle
        quelle.
        """
        if not self.heater_enabled:
            return self.temp_max
        return max(self.temp_max, self.heater_off_threshold + self.vent_deadband)

    @property
    def vent_threshold_raised(self) -> bool:
        """Vrai si la consigne haute a dû être relevée pour tenir la zone morte."""
        return self.vent_threshold > self.temp_max


@dataclass(frozen=True)
class ClimateInputs:
    """Tout ce qui vient du monde extérieur, horloges comprises."""

    now_mono: float          # `time.monotonic()` : durées, insensible à NTP
    now_epoch: float         # `time.time()` : fenêtres de budget, survit au reboot
    temperature: float | None
    humidity: float | None
    is_day: bool
    temperature_inconsistent: bool = False
    temperature_quality_reason: str | None = None

    # Forçages « arrêt » opérateur : des **échéances**, pas des booléens. C'est
    # `decide()` qui tranche l'expiration, à partir des horloges ci-dessus et de
    # rien d'autre — la fonction reste pure et un forçage se rejoue au harnais.
    # Un forçage n'est pas de la configuration : il n'a rien à faire dans
    # `ClimateSettings`, dont dépendent les seuils dérivés.
    heater_forced_off_until_epoch: float | None = None
    heater_forced_off_deadline_mono: float | None = None
    motor_forced_off_until_epoch: float | None = None
    motor_forced_off_deadline_mono: float | None = None

    @property
    def heater_forced_off(self) -> bool:
        return _forced_off(self.heater_forced_off_until_epoch,
                           self.heater_forced_off_deadline_mono, self)

    @property
    def motor_forced_off(self) -> bool:
        return _forced_off(self.motor_forced_off_until_epoch,
                           self.motor_forced_off_deadline_mono, self)


def _forced_off(until_epoch: float | None, deadline_mono: float | None,
                inputs: "ClimateInputs") -> bool:
    """
    Échu au **premier** des deux horloges : un saut NTP avant coupe plus tôt,
    un saut arrière ne prolonge rien. Règle volontairement dupliquée avec
    `utils.overrides.ForcedOff.active_at` — la politique ne doit importer ni le
    magasin, ni le disque, ni le journal.
    """
    if until_epoch is None:
        return False
    if inputs.now_epoch >= until_epoch:
        return False
    if deadline_mono is not None and inputs.now_mono >= deadline_mono:
        return False
    return True


@dataclass(frozen=True)
class ClimateMemory:
    """
    État reporté d'un tick au suivant. Gelé : `decide()` en renvoie une nouvelle
    version au lieu de muter la précédente, donc rien ne change dans le dos de
    l'appelant. Les champs de budget sont les seuls persistés sur disque (E10).
    """

    heater_on: bool = False
    heater_on_since: float | None = None
    heater_cooldown_until: float | None = None
    sensor_failures: int = 0

    motor_speed: int = 0
    motor_speed_since: float = 0.0

    quota_window_start: float | None = None      # epoch, début de la fenêtre d'une heure
    renew_minutes_used: float = 0.0
    humidity_minutes_used: float = 0.0
    credit_kind: str | None = None               # budget crédité par le tick précédent
    last_tick_mono: float | None = None


@dataclass(frozen=True)
class ClimateDecision:
    """Décision d'un tick — appliquée telle quelle par la coroutine."""

    heater_on: bool
    motor_speed: int
    motor_speed_requested: int
    state: str
    reason: str
    alarm: str | None = None
    alarm_code: str | None = None
    temperature: float | None = None
    humidity: float | None = None
    temp_min: float = 0.0
    temp_max: float = 0.0
    vent_threshold: float = 0.0
    heater_off_threshold: float = 0.0
    renew_minutes_used: float = 0.0
    renew_minutes_quota: float = 0.0
    humidity_minutes_used: float = 0.0
    humidity_minutes_quota: float = 0.0
    dwell_remaining_seconds: float = 0.0
    heater_forced_off: bool = False
    motor_forced_off: bool = False


# ─────────────────────────────────────────────────────────────
#  Utilitaires purs
# ─────────────────────────────────────────────────────────────
def _valid_temperature(value) -> float | None:
    try:
        temp = float(value)
    except (TypeError, ValueError):
        return None
    return temp if TEMP_VALID_MIN < temp < TEMP_VALID_MAX else None


def _valid_humidity(value) -> float | None:
    try:
        rh = float(value)
    except (TypeError, ValueError):
        return None
    return rh if RH_VALID_MIN <= rh <= RH_VALID_MAX else None


def clamp_speed(settings: ClimateSettings, level: int) -> int:
    """
    Ramène une vitesse dans [min_speed ; max_speed] **sans jamais transformer un
    ordre d'arrêt en marche** (audit M13) : 0 reste 0, quel que soit `min_speed`.
    """
    if level <= 0:
        return 0
    high = max(0, min(4, settings.max_speed))
    if high == 0:
        return 0
    low = min(max(1, settings.min_speed), high)
    return max(low, min(level, high))


def _vent_level(settings: ClimateSettings, temp: float, previous: int) -> int:
    """
    Échelle de ventilation à hystérésis d'état (audit E9).

    Le palier `k` s'engage à `seuil + (k-1)·vent_step` et ne se relâche que sous
    `seuil + (k-1)·vent_step − vent_release`. Sans ce seuil de relâchement
    distinct, une température qui oscille d'un dixième autour du seuil fait
    battre le relais des centaines de fois par heure.
    """
    threshold = settings.vent_threshold
    level = 0
    for step in range(1, 5):
        if temp >= threshold + (step - 1) * settings.vent_step:
            level = step

    if level >= previous:
        return level
    # Descente : uniquement si la température est repassée sous le seuil de
    # relâchement du palier courant.
    release = threshold + (previous - 1) * settings.vent_step - settings.vent_release
    return level if temp < release else previous


def _roll_budgets(settings: ClimateSettings, inputs: ClimateInputs,
                  memory: ClimateMemory) -> ClimateMemory:
    """
    Crédite les budgets du temps **réellement écoulé** depuis le tick précédent
    (audit M14 : l'ancien comptage utilisait la période nominale), puis fait
    tourner la fenêtre d'une heure.

    La fenêtre est ancrée sur l'epoch et non sur `monotonic()` : elle doit
    survivre à un redémarrage (E10). Un saut d'horloge en arrière (resync NTP
    sans RTC) réarme la fenêtre au lieu de la geler.
    """
    renew = memory.renew_minutes_used
    humid = memory.humidity_minutes_used

    if memory.last_tick_mono is not None and memory.credit_kind is not None:
        elapsed = inputs.now_mono - memory.last_tick_mono
        elapsed = max(0.0, min(elapsed, MAX_TICK_CREDIT_SECONDS)) / 60.0
        if memory.credit_kind == CREDIT_RENEW:
            renew += elapsed
        elif memory.credit_kind == CREDIT_HUMIDITY:
            humid += elapsed

    window_start = memory.quota_window_start
    if (window_start is None
            or inputs.now_epoch < window_start
            or inputs.now_epoch - window_start >= QUOTA_WINDOW_SECONDS):
        window_start = inputs.now_epoch
        renew = 0.0
        humid = 0.0

    return replace(
        memory,
        quota_window_start=window_start,
        renew_minutes_used=renew,
        humidity_minutes_used=humid,
        last_tick_mono=inputs.now_mono,
    )


# ─────────────────────────────────────────────────────────────
#  Chauffage
# ─────────────────────────────────────────────────────────────
def _decide_heater(settings: ClimateSettings, inputs: ClimateInputs,
                   memory: ClimateMemory, temp: float | None,
                   sensor_lost: bool) -> tuple[bool, str | None, str | None, str, ClimateMemory]:
    """Retourne `(chauffage_on, code_alarme, alarme, motif, mémoire)`."""
    now = inputs.now_mono

    if not settings.heater_enabled:
        return False, None, None, "chauffage désactivé", replace(
            memory, heater_cooldown_until=None
        )

    # Garde-fou 1 : durée maximale d'allumage continu.
    if (memory.heater_on and memory.heater_on_since is not None
            and now - memory.heater_on_since >= MAX_CONTINUOUS_ON_MINUTES * 60):
        memory = replace(
            memory,
            heater_cooldown_until=now + FORCED_OFF_COOLDOWN_MINUTES * 60,
        )
        alarm = (
            f"allumage continu de {MAX_CONTINUOUS_ON_MINUTES} min atteint → "
            f"repos forcé de {FORCED_OFF_COOLDOWN_MINUTES} min "
            "(capteur bloqué ? puissance de chauffe insuffisante ?)"
        )
        return False, ALARM_CONTINUOUS_LIMIT, alarm, f"durée max de {MAX_CONTINUOUS_ON_MINUTES} min atteinte", memory

    in_cooldown = (memory.heater_cooldown_until is not None
                   and now < memory.heater_cooldown_until)
    if memory.heater_cooldown_until is not None and not in_cooldown:
        memory = replace(memory, heater_cooldown_until=None)

    # Garde-fou 2 : repli sur perte durable du capteur.
    if sensor_lost:
        diagnostic = (
            f" ({inputs.temperature_quality_reason})"
            if inputs.temperature_quality_reason else ""
        )
        alarm = (f"température ambiante illisible{diagnostic} → chauffage coupé, "
                 "régulation impossible")
        return False, ALARM_SENSOR_FALLBACK, alarm, (
            f"repli capteur ({memory.sensor_failures} lectures manquées)"
        ), memory

    if temp is None:
        # Panne transitoire : on conserve l'état, le compteur fait le reste.
        return memory.heater_on, None, None, (
            f"lecture manquée {memory.sensor_failures}/"
            f"{MAX_CONSECUTIVE_SENSOR_FAILURES} → état conservé"
        ), memory

    if in_cooldown:
        alarm = (
            f"repos forcé après {MAX_CONTINUOUS_ON_MINUTES} min de chauffe "
            f"continue ({FORCED_OFF_COOLDOWN_MINUTES} min de cooldown)"
        )
        return False, ALARM_CONTINUOUS_LIMIT, alarm, "repos forcé en cours → allumage inhibé", memory

    if temp <= settings.temp_min:
        return True, None, None, f"{temp:.1f}°C ≤ {settings.temp_min:.1f}°C", memory
    if temp > settings.heater_off_threshold:
        return False, None, None, (
            f"{temp:.1f}°C > {settings.heater_off_threshold:.1f}°C"
        ), memory
    return memory.heater_on, None, None, (
        f"{temp:.1f}°C dans la bande morte "
        f"]{settings.temp_min:.1f} ; {settings.heater_off_threshold:.1f}]"
    ), memory


# ─────────────────────────────────────────────────────────────
#  Ventilation
# ─────────────────────────────────────────────────────────────
def _decide_motor(settings: ClimateSettings, inputs: ClimateInputs,
                  memory: ClimateMemory, temp: float | None, rh: float | None,
                  sensor_lost: bool) -> tuple[int, str, str, str | None, bool]:
    """
    Retourne `(vitesse, état, motif, motif_de_crédit, immédiat)`.

    `immédiat` court-circuite le temps de maintien : une coupure de sécurité ne
    se négocie pas.
    """
    mode = (settings.motor_mode or "").lower()

    # Forçage opérateur : **absolu**, avant le mode manuel et avant le repli
    # capteur (arbitrage du 28/08/2026 — verrouillage pour intervention
    # physique sur le ventilateur). C'est un renoncement assumé à
    # `SECURITE_HAUTE` : il est compensé par un plafond de 4 h et par
    # `ALARM_MOTOR_LOCKOUT`, levée plus bas dès que la serre chauffe malgré le
    # verrou. `immediate=True` : un ordre d'arrêt ne se négocie pas avec
    # `min_dwell_seconds`.
    if inputs.motor_forced_off:
        return (0, STATE_FORCED_OFF, "forçage opérateur : arrêt", None, True)

    if mode == "manual":
        return (clamp_speed(settings, settings.motor_user_speed), STATE_MANUAL,
                "consigne manuelle", None, True)

    if sensor_lost:
        return (clamp_speed(settings, settings.sensor_fallback_speed),
                STATE_SENSOR_FALLBACK,
                f"repli capteur ({memory.sensor_failures} lectures manquées)",
                None, True)

    if temp is None:
        return (memory.motor_speed, STATE_NEUTRAL,
                "température indisponible → vitesse maintenue", memory.credit_kind, False)

    # Plancher thermique absolu : au-dessous, plus rien ne ventile, quel que
    # soit le budget restant ou l'humidité (audit C8).
    if temp < settings.absolute_floor_temp:
        return (0, STATE_FLOOR,
                f"{temp:.1f}°C < plancher {settings.absolute_floor_temp:.1f}°C",
                None, True)

    level = _vent_level(settings, temp, memory.motor_speed)

    if mode == "auto":
        if level == 0:
            return (0, STATE_NEUTRAL,
                    f"{temp:.1f}°C < seuil de ventilation "
                    f"{settings.vent_threshold:.1f}°C", None, False)
        state = STATE_OVERHEAT if level >= 4 else STATE_VENT
        return (clamp_speed(settings, level), state,
                f"{temp:.1f}°C ≥ {settings.vent_threshold:.1f}°C → palier {level}",
                None, level >= 4)

    if mode == "winter":
        if level > 0:
            # Sécurité haute : elle prime sur toute logique de conservation de
            # chaleur, et ne consomme aucun budget.
            state = STATE_OVERHEAT if level >= 3 else STATE_VENT
            return (clamp_speed(settings, level), state,
                    f"sécurité haute : {temp:.1f}°C ≥ "
                    f"{settings.vent_threshold:.1f}°C → palier {level}",
                    None, level >= 3)

        too_cold = temp < settings.temp_min - settings.winter_temp_margin
        humidity_high = (rh is not None and rh >= settings.winter_humidity_threshold)

        renew_left = settings.winter_refresh_minutes_per_hour - memory.renew_minutes_used
        humid_left = settings.winter_humidity_minutes_per_hour - memory.humidity_minutes_used

        # Budget de renouvellement : la ressource unique qui gouverne l'air neuf.
        if renew_left > 0:
            return (clamp_speed(settings, settings.winter_refresh_speed), STATE_RENEW,
                    f"renouvellement {memory.renew_minutes_used:.1f}/"
                    f"{settings.winter_refresh_minutes_per_hour:.0f} min/h",
                    CREDIT_RENEW, False)

        # Budget de déshumidification : distinct et **borné**. C'est lui qui
        # remplace l'ancien court-circuit du quota par l'humidité (audit C8).
        if humidity_high and humid_left > 0:
            return (clamp_speed(settings, settings.winter_refresh_speed), STATE_DEHUMIDIFY,
                    f"RH {rh:.1f}% ≥ {settings.winter_humidity_threshold:.1f}% "
                    f"({memory.humidity_minutes_used:.1f}/"
                    f"{settings.winter_humidity_minutes_per_hour:.0f} min/h)",
                    CREDIT_HUMIDITY, False)

        if too_cold:
            # On ferme : la consigne de brassage ne s'applique pas au grand froid.
            return (0, STATE_NEUTRAL,
                    f"froid ({temp:.1f}°C) et budgets épuisés → fermeture",
                    None, False)

        return (clamp_speed(settings, settings.winter_default_speed), STATE_NEUTRAL,
                "budgets épuisés → vitesse par défaut", None, False)

    # Mode inconnu : l'arrêt est le seul état sûr.
    return (0, STATE_NEUTRAL, f"mode moteur inconnu ({mode!r}) → arrêt", None, True)


def _apply_dwell(settings: ClimateSettings, inputs: ClimateInputs,
                 memory: ClimateMemory, wanted: int,
                 immediate: bool) -> tuple[int, bool]:
    """
    Temps de maintien minimal entre deux changements de vitesse (audit E9).
    Retourne `(vitesse_retenue, changement)`.
    """
    if wanted == memory.motor_speed:
        return wanted, False
    if immediate or settings.min_dwell_seconds <= 0:
        return wanted, True
    if inputs.now_mono - memory.motor_speed_since >= settings.min_dwell_seconds:
        return wanted, True
    return memory.motor_speed, False


# ─────────────────────────────────────────────────────────────
#  Décision complète
# ─────────────────────────────────────────────────────────────
def decide(settings: ClimateSettings, inputs: ClimateInputs,
           memory: ClimateMemory) -> tuple[ClimateDecision, ClimateMemory]:
    """
    Arbitre un tick : une lecture, une décision cohérente pour les deux organes.

    Le chauffage est décidé d'abord (c'est lui qui porte les garde-fous de
    sécurité physique), la ventilation ensuite ; la zone morte garantit qu'ils
    ne peuvent pas être actifs en même temps, donc aucun arbitrage supplémentaire
    n'est nécessaire — l'incohérence est rendue **impossible** plutôt que
    corrigée après coup.
    """
    memory = _roll_budgets(settings, inputs, memory)

    temp = _valid_temperature(inputs.temperature)
    rh = _valid_humidity(inputs.humidity)

    failures = (
        MAX_CONSECUTIVE_SENSOR_FAILURES
        if inputs.temperature_inconsistent
        else 0 if temp is not None else memory.sensor_failures + 1
    )
    memory = replace(memory, sensor_failures=failures)
    sensor_lost = failures >= MAX_CONSECUTIVE_SENSOR_FAILURES

    heater_on, alarm_code, alarm, heater_reason, memory = _decide_heater(
        settings, inputs, memory, temp, sensor_lost
    )

    # Forçage « arrêt » chauffage : post-filtre, et non branche interne. Ainsi
    # `ALARM_SENSOR_FALLBACK`, `ALARM_CONTINUOUS_LIMIT`, le compteur de lectures
    # manquées et le cooldown continuent d'être calculés et publiés pendant le
    # forçage. Il couvre aussi la branche « lecture manquée » qui *tient* l'état
    # ON, seule façon qu'un forçage laisse chauffer.
    # `settings.vent_threshold` n'est volontairement **pas** touché : détourner
    # `heater_enabled` pour couper le chauffage abaisserait le seuil de
    # ventilation de l'hystérésis plus la zone morte, silencieusement, pendant
    # toute la durée du forçage.
    if inputs.heater_forced_off:
        heater_on = False
        heater_reason = f"forçage opérateur : arrêt ({heater_reason})"

    if heater_on != memory.heater_on:
        memory = replace(
            memory,
            heater_on=heater_on,
            heater_on_since=inputs.now_mono if heater_on else None,
        )
    elif heater_on and memory.heater_on_since is None:
        memory = replace(memory, heater_on_since=inputs.now_mono)

    wanted, state, motor_reason, credit, immediate = _decide_motor(
        settings, inputs, memory, temp, rh, sensor_lost
    )
    speed, changed = _apply_dwell(settings, inputs, memory, wanted, immediate)
    if speed != wanted:
        motor_reason += " (temps de maintien)"
        # La vitesse retenue n'est pas celle voulue : on ne crédite que ce qui
        # tourne réellement.
        credit = memory.credit_kind
    memory = replace(
        memory,
        motor_speed=speed,
        motor_speed_since=inputs.now_mono if changed else memory.motor_speed_since,
        credit_kind=credit if speed > 0 else None,
    )

    # L'état publié décrit ce qui *agit*. Le renouvellement et la
    # déshumidification d'hiver restent nommés même quand le chauffage tourne :
    # ce sont des épisodes **bornés** et voulus, à ne pas confondre avec le
    # conflit chauffage/ventilation que la zone morte interdit.
    if state not in (STATE_FLOOR, STATE_SENSOR_FALLBACK, STATE_MANUAL,
                     STATE_FORCED_OFF) and speed == 0:
        if heater_on:
            state = STATE_HEAT
        elif inputs.heater_forced_off:
            state = STATE_FORCED_OFF
        elif not settings.heater_enabled and state == STATE_NEUTRAL:
            state = STATE_DISABLED

    # Verrou moteur pendant que la serre monte : la ventilation aurait démarré
    # sans le forçage. C'est le seul cas où l'arbitre ne peut plus rien faire —
    # il le dit fort. L'alarme prime sur celle de durée de chauffe, jamais sur
    # le repli capteur (température inconnue : rien à comparer).
    if (inputs.motor_forced_off and temp is not None
            and temp >= settings.vent_threshold
            and alarm_code != ALARM_SENSOR_FALLBACK):
        alarm_code = ALARM_MOTOR_LOCKOUT
        alarm = (f"{temp:.1f}°C ≥ seuil de ventilation "
                 f"{settings.vent_threshold:.1f}°C alors qu'un forçage « arrêt » "
                 "verrouille le moteur → aucune ventilation possible")

    decision = ClimateDecision(
        heater_on=heater_on,
        motor_speed=speed,
        motor_speed_requested=wanted,
        state=state,
        reason=f"chauffage : {heater_reason} · ventilation : {motor_reason}",
        alarm=alarm,
        alarm_code=alarm_code,
        temperature=temp,
        humidity=rh,
        vent_threshold=settings.vent_threshold,
        heater_off_threshold=settings.heater_off_threshold,
        renew_minutes_used=round(memory.renew_minutes_used, 2),
        renew_minutes_quota=settings.winter_refresh_minutes_per_hour,
        humidity_minutes_used=round(memory.humidity_minutes_used, 2),
        humidity_minutes_quota=settings.winter_humidity_minutes_per_hour,
        dwell_remaining_seconds=round(
            max(
                0.0,
                settings.min_dwell_seconds
                - (inputs.now_mono - memory.motor_speed_since),
            ) if speed != wanted else 0.0,
            1,
        ),
        temp_min=settings.temp_min,
        temp_max=settings.temp_max,
        heater_forced_off=inputs.heater_forced_off,
        motor_forced_off=inputs.motor_forced_off,
    )
    return decision, memory


# ─────────────────────────────────────────────────────────────
#  Passerelle depuis AppConfig
# ─────────────────────────────────────────────────────────────
def settings_from_config(config, is_day: bool) -> ClimateSettings:
    """
    Projette `AppConfig` sur les consignes du moment. C'est le seul point du
    module qui connaisse la forme de la configuration : `decide()` reste
    utilisable avec des valeurs écrites à la main.
    """
    temperature = config.temperature
    motor = config.motor
    return ClimateSettings(
        heater_enabled=config.heater_settings.enabled,
        temp_min=(temperature.target_temp_min_day if is_day
                  else temperature.target_temp_min_night),
        temp_max=(temperature.target_temp_max_day if is_day
                  else temperature.target_temp_max_night),
        heater_hysteresis=temperature.hysteresis_offset,
        vent_deadband=temperature.vent_deadband,
        vent_step=temperature.vent_step,
        vent_release=temperature.vent_release,
        absolute_floor_temp=temperature.absolute_floor_temp,
        min_dwell_seconds=temperature.min_dwell_seconds,
        motor_mode=motor.motor_mode,
        motor_user_speed=motor.motor_user_speed,
        min_speed=motor.min_speed,
        max_speed=motor.max_speed,
        sensor_fallback_speed=motor.sensor_fallback_speed,
        winter_default_speed=motor.winter_default_speed,
        winter_temp_margin=motor.winter_temp_margin,
        winter_refresh_speed=motor.winter_refresh_speed,
        winter_refresh_minutes_per_hour=float(motor.winter_refresh_minutes_per_hour),
        winter_humidity_threshold=motor.winter_humidity_threshold,
        winter_humidity_minutes_per_hour=float(motor.winter_humidity_minutes_per_hour),
    )


def preview_thresholds(config) -> dict:
    """
    Seuils **effectifs** de l'arbitre pour une configuration donnée.

    Projection de lecture, destinée à la prévisualisation de l'IHM. Elle
    n'invente aucune formule : elle rejoue `settings_from_config`,
    `vent_threshold` et `clamp_speed`, exactement ce que `decide()` utilisera.
    Rejouer ces règles en JavaScript serait une seconde vérité, et c'est le
    seuil de ventilation qui en souffrirait le premier : `vent_threshold` peut
    dépasser la consigne haute saisie de l'hystérésis plus la zone morte, un
    écart de deux degrés qu'un formulaire tairait en silence.
    """
    phases = {}
    for name, is_day in (("day", True), ("night", False)):
        settings = settings_from_config(config, is_day)
        phases[name] = {
            "temp_min": settings.temp_min,
            "temp_max": settings.temp_max,
            "heater_on_at_or_below": settings.temp_min,
            "heater_off_above": round(settings.heater_off_threshold, 2),
            # Les deux hystérésis du système sont republiées telles quelles :
            # celle du chauffage (largeur de la bande morte) et celle des
            # paliers de ventilation (écart entre engagement et relâchement).
            "heater_hysteresis": settings.heater_hysteresis,
            "vent_release": settings.vent_release,
            "vent_threshold": round(settings.vent_threshold, 2),
            "vent_threshold_raised": settings.vent_threshold_raised,
            "vent_ladder": [
                {
                    "step": step,
                    "starts_at": round(
                        settings.vent_threshold + (step - 1) * settings.vent_step, 2
                    ),
                    "releases_below": round(
                        settings.vent_threshold
                        + (step - 1) * settings.vent_step
                        - settings.vent_release,
                        2,
                    ),
                    "effective_speed": clamp_speed(settings, step),
                }
                for step in range(1, 5)
            ],
            "absolute_floor_temp": settings.absolute_floor_temp,
            "min_dwell_seconds": settings.min_dwell_seconds,
        }
    return {
        "heater_enabled": config.heater_settings.enabled,
        "motor_mode": config.motor.motor_mode,
        "min_speed": config.motor.min_speed,
        "max_speed": config.motor.max_speed,
        "phases": phases,
    }
