from __future__ import annotations

from dataclasses import replace
import math

import pytest

from components.climate_policy import (
    ALARM_CONTINUOUS_LIMIT,
    ALARM_MOTOR_LOCKOUT,
    ALARM_SENSOR_FALLBACK,
    FORCED_OFF_COOLDOWN_MINUTES,
    MAX_CONSECUTIVE_SENSOR_FAILURES,
    MAX_CONTINUOUS_ON_MINUTES,
    MAX_TICK_CREDIT_SECONDS,
    ClimateInputs,
    ClimateMemory,
    STATE_DEHUMIDIFY,
    STATE_FLOOR,
    STATE_FORCED_OFF,
    STATE_OVERHEAT,
    STATE_RENEW,
    STATE_SENSOR_FALLBACK,
    STATE_VENT,
    clamp_speed,
    decide,
)


def run_tick(settings, memory=None, *, mono=0.0, epoch=1_000.0,
             temperature=21.0, humidity=50.0):
    return decide(
        settings,
        ClimateInputs(
            now_mono=mono,
            now_epoch=epoch,
            temperature=temperature,
            humidity=humidity,
            is_day=True,
        ),
        memory or ClimateMemory(),
    )


@pytest.mark.parametrize(
    ("temperature", "heater_on", "motor_speed"),
    [
        (19.9, True, 0),
        (20.0, True, 0),
        (21.1, False, 0),
        (23.9, False, 0),
        (24.0, False, 1),
        (25.0, False, 2),
        (26.0, False, 3),
        (27.0, False, 4),
    ],
)
def test_decisions_automatiques_aux_seuils(
    climate_settings, temperature, heater_on, motor_speed
):
    decision, _ = run_tick(climate_settings(), temperature=temperature)
    assert decision.heater_on is heater_on
    assert decision.motor_speed == motor_speed


@pytest.mark.parametrize(
    ("temp_max", "expected", "raised"),
    [(20.0, 22.0, True), (22.0, 22.0, False), (24.0, 24.0, False)],
)
def test_seuil_ventilation_garantit_la_zone_morte(
    climate_settings, temp_max, expected, raised
):
    settings = climate_settings(temp_max=temp_max)
    assert settings.vent_threshold == expected
    assert settings.vent_threshold_raised is raised


def test_chauffage_desactive_ne_releve_pas_le_seuil(climate_settings):
    settings = climate_settings(heater_enabled=False, temp_max=20.0)
    assert settings.vent_threshold == 20.0
    assert settings.vent_threshold_raised is False


@pytest.mark.parametrize("temp_max", [19.0, 21.0, 22.0, 24.0, 30.0])
def test_jamais_chauffage_et_ventilation_thermique_simultanes(
    climate_settings, temp_max
):
    settings = climate_settings(temp_max=temp_max)
    memory = ClimateMemory()
    mono = 0.0
    temperatures = [value / 4 for value in range(-76, 240)]
    temperatures += list(reversed(temperatures))
    for temperature in temperatures:
        mono += 1.0
        decision, memory = run_tick(
            settings, memory, mono=mono, temperature=temperature
        )
        assert not (
            decision.heater_on
            and decision.state in {STATE_VENT, STATE_OVERHEAT}
        ), (temperature, decision)


def test_plancher_absolu_prime_sur_humidite_quota_et_dwell(climate_settings):
    settings = climate_settings(motor_mode="winter", min_dwell_seconds=600)
    memory = ClimateMemory(
        motor_speed=3,
        motor_speed_since=100.0,
        quota_window_start=1_000.0,
    )
    decision, memory = run_tick(
        settings, memory, mono=101.0, epoch=1_010.0,
        temperature=4.9, humidity=100.0,
    )
    assert decision.state == STATE_FLOOR
    assert decision.motor_speed == 0
    assert memory.credit_kind is None


def test_budgets_hiver_sont_distincts_et_bornes(climate_settings):
    settings = climate_settings(motor_mode="winter")
    memory = ClimateMemory()

    first, memory = run_tick(
        settings, memory, mono=0.0, epoch=1_000.0,
        temperature=18.0, humidity=90.0,
    )
    assert first.state == STATE_RENEW

    memory = replace(memory, renew_minutes_used=5.0)
    humid, memory = run_tick(
        settings, memory, mono=60.0, epoch=1_060.0,
        temperature=18.0, humidity=90.0,
    )
    assert humid.state == STATE_DEHUMIDIFY
    assert memory.renew_minutes_used == pytest.approx(6.0)
    assert memory.humidity_minutes_used == 0.0

    memory = replace(memory, renew_minutes_used=5.0, humidity_minutes_used=10.0)
    exhausted, memory = run_tick(
        settings, memory, mono=120.0, epoch=1_120.0,
        temperature=17.9, humidity=90.0,
    )
    assert exhausted.motor_speed == 0
    assert memory.credit_kind is None


def test_credit_hiver_utilise_le_temps_reel_avec_plafond(climate_settings):
    settings = climate_settings(motor_mode="winter")
    memory = ClimateMemory(
        quota_window_start=1_000.0,
        credit_kind="renew",
        last_tick_mono=0.0,
    )
    _, memory = run_tick(
        settings, memory, mono=1_000.0, epoch=1_100.0,
        temperature=18.0,
    )
    assert memory.renew_minutes_used == pytest.approx(MAX_TICK_CREDIT_SECONDS / 60)


@pytest.mark.parametrize("epoch", [999.0, 4_600.0])
def test_fenetre_hiver_se_rearme_sur_saut_ntp_ou_echeance(
    climate_settings, epoch
):
    settings = climate_settings(motor_mode="winter")
    memory = ClimateMemory(
        quota_window_start=1_000.0,
        renew_minutes_used=4.0,
        humidity_minutes_used=7.0,
    )
    _, memory = run_tick(settings, memory, mono=10.0, epoch=epoch)
    assert memory.quota_window_start == epoch
    assert memory.renew_minutes_used == 0.0
    assert memory.humidity_minutes_used == 0.0


@pytest.mark.parametrize("invalid", [None, "illisible", -20.0, 60.0, math.nan, math.inf])
def test_cinquieme_lecture_invalide_declenche_le_repli(
    climate_settings, invalid
):
    settings = climate_settings()
    memory = ClimateMemory(heater_on=True, heater_on_since=0.0, motor_speed=1)
    for failure in range(1, MAX_CONSECUTIVE_SENSOR_FAILURES + 1):
        decision, memory = run_tick(
            settings, memory, mono=float(failure), temperature=invalid
        )
        assert memory.sensor_failures == failure
        if failure < MAX_CONSECUTIVE_SENSOR_FAILURES:
            assert decision.heater_on is True
            assert decision.motor_speed == 1

    assert decision.state == STATE_SENSOR_FALLBACK
    assert decision.heater_on is False
    assert decision.motor_speed == settings.sensor_fallback_speed
    assert decision.alarm_code == ALARM_SENSOR_FALLBACK
    assert decision.alarm


def test_retour_capteur_quitte_le_repli(climate_settings):
    settings = climate_settings()
    memory = ClimateMemory(sensor_failures=MAX_CONSECUTIVE_SENSOR_FAILURES)
    decision, memory = run_tick(settings, memory, temperature=19.0)
    assert memory.sensor_failures == 0
    assert decision.state != STATE_SENSOR_FALLBACK
    assert decision.alarm_code is None
    assert decision.heater_on is True


def test_incoherence_confirmee_declenche_le_repli_sans_attendre(climate_settings):
    settings = climate_settings()
    memory = ClimateMemory(heater_on=True, heater_on_since=0.0, motor_speed=1)
    decision, memory = decide(
        settings,
        ClimateInputs(
            now_mono=1.0,
            now_epoch=1_001.0,
            temperature=None,
            humidity=50.0,
            is_day=True,
            temperature_inconsistent=True,
            temperature_quality_reason="frozen",
        ),
        memory,
    )

    assert memory.sensor_failures == MAX_CONSECUTIVE_SENSOR_FAILURES
    assert decision.state == STATE_SENSOR_FALLBACK
    assert decision.heater_on is False
    assert decision.motor_speed == settings.sensor_fallback_speed
    assert decision.alarm_code == ALARM_SENSOR_FALLBACK
    assert "frozen" in decision.alarm


def test_duree_maximale_et_cooldown_chauffage(climate_settings):
    settings = climate_settings()
    decision, memory = run_tick(settings, mono=0.0, temperature=19.0)
    assert decision.heater_on is True

    almost = MAX_CONTINUOUS_ON_MINUTES * 60 - 0.1
    decision, memory = run_tick(settings, memory, mono=almost, temperature=19.0)
    assert decision.heater_on is True

    limit = MAX_CONTINUOUS_ON_MINUTES * 60
    decision, memory = run_tick(settings, memory, mono=limit, temperature=19.0)
    assert decision.heater_on is False
    assert decision.alarm_code == ALARM_CONTINUOUS_LIMIT
    assert memory.heater_cooldown_until == limit + FORCED_OFF_COOLDOWN_MINUTES * 60

    decision, memory = run_tick(
        settings, memory, mono=memory.heater_cooldown_until - 0.1,
        epoch=-1_000_000.0, temperature=19.0,
    )
    assert decision.heater_on is False
    assert decision.alarm_code == ALARM_CONTINUOUS_LIMIT

    decision, memory = run_tick(
        settings, memory, mono=memory.heater_cooldown_until,
        epoch=9_000_000.0, temperature=19.0,
    )
    assert decision.heater_on is True
    assert decision.alarm_code is None


def test_hysterese_de_palier_et_temps_de_maintien(climate_settings):
    settings = climate_settings(min_dwell_seconds=30.0)
    memory = ClimateMemory(motor_speed=2, motor_speed_since=100.0)

    decision, memory = run_tick(settings, memory, mono=110.0, temperature=24.4)
    assert decision.motor_speed == 2
    assert decision.motor_speed_requested == 1
    assert decision.dwell_remaining_seconds == 20.0

    decision, memory = run_tick(settings, memory, mono=131.0, temperature=24.6)
    assert decision.motor_speed == 2  # au-dessus du seuil de relâchement du palier 2

    decision, memory = run_tick(settings, memory, mono=132.0, temperature=24.4)
    assert decision.motor_speed == 1


def test_un_ordre_arret_reste_un_arret(climate_settings):
    assert clamp_speed(climate_settings(min_speed=3), 0) == 0


# ─────────────────────────────────────────────────────────────
#  Forçages « arrêt » opérateur (jalon 4) — matrice pure
# ─────────────────────────────────────────────────────────────
def run_forced(settings, memory=None, *, mono=0.0, epoch=1_000.0,
               temperature=21.0, humidity=50.0, heater=None, motor=None):
    """`heater`/`motor` : couple (echeance_epoch, echeance_mono) ou None."""
    return decide(
        settings,
        ClimateInputs(
            now_mono=mono, now_epoch=epoch,
            temperature=temperature, humidity=humidity, is_day=True,
            heater_forced_off_until_epoch=heater[0] if heater else None,
            heater_forced_off_deadline_mono=heater[1] if heater else None,
            motor_forced_off_until_epoch=motor[0] if motor else None,
            motor_forced_off_deadline_mono=motor[1] if motor else None,
        ),
        memory or ClimateMemory(),
    )


def test_forcage_chauffage_coupe_sous_la_consigne(climate_settings):
    settings = climate_settings()
    normal, _ = run_forced(settings, temperature=15.0)
    assert normal.heater_on is True

    forcé, _ = run_forced(settings, temperature=15.0, heater=(2_000.0, 100.0))
    assert forcé.heater_on is False
    assert forcé.heater_forced_off is True
    assert forcé.state == STATE_FORCED_OFF


def test_forcage_chauffage_ne_deplace_pas_le_seuil_de_ventilation(climate_settings):
    # Détourner `heater_enabled` abaisserait le seuil de hystérésis + zone morte.
    settings = climate_settings(temp_max=20.0)
    normal, _ = run_forced(settings, temperature=15.0)
    forcé, _ = run_forced(settings, temperature=15.0, heater=(2_000.0, 100.0))
    assert forcé.vent_threshold == normal.vent_threshold
    assert forcé.vent_threshold == pytest.approx(22.0)


def test_forcage_chauffage_couvre_la_lecture_manquee(climate_settings):
    # La branche « lecture manquée » *tient* l'état ON : sans post-filtre, un
    # forçage laisserait chauffer.
    settings = climate_settings()
    memory = ClimateMemory(heater_on=True, heater_on_since=0.0)
    tenu, _ = run_forced(settings, memory, temperature=None)
    assert tenu.heater_on is True

    forcé, _ = run_forced(settings, memory, temperature=None,
                          heater=(2_000.0, 100.0))
    assert forcé.heater_on is False


def test_forcage_chauffage_preserve_l_alarme_de_repli(climate_settings):
    settings = climate_settings()
    memory = ClimateMemory(sensor_failures=MAX_CONSECUTIVE_SENSOR_FAILURES - 1)
    decision, _ = run_forced(settings, memory, temperature=None,
                             heater=(2_000.0, 100.0))
    assert decision.alarm_code == ALARM_SENSOR_FALLBACK
    assert decision.heater_on is False


def test_forcage_moteur_prime_sur_la_securite_haute(climate_settings):
    # Arbitrage opérateur du 28/08/2026 : verrouillage absolu.
    settings = climate_settings()
    normal, _ = run_forced(settings, temperature=40.0)
    assert normal.state == STATE_OVERHEAT and normal.motor_speed == 4

    forcé, _ = run_forced(settings, temperature=40.0, motor=(2_000.0, 100.0))
    assert forcé.motor_speed == 0
    assert forcé.state == STATE_FORCED_OFF


def test_forcage_moteur_prime_sur_le_repli_capteur(climate_settings):
    settings = climate_settings(sensor_fallback_speed=3)
    memory = ClimateMemory(sensor_failures=MAX_CONSECUTIVE_SENSOR_FAILURES - 1)
    replié, _ = run_forced(settings, memory, temperature=None)
    assert replié.motor_speed == 3

    forcé, _ = run_forced(settings, memory, temperature=None,
                          motor=(2_000.0, 100.0))
    assert forcé.motor_speed == 0


def test_forcage_moteur_prime_sur_le_mode_manuel(climate_settings):
    settings = climate_settings(motor_mode="manual", motor_user_speed=3)
    forcé, _ = run_forced(settings, motor=(2_000.0, 100.0))
    assert forcé.motor_speed == 0


def test_forcage_moteur_ignore_le_temps_de_maintien(climate_settings):
    settings = climate_settings(min_dwell_seconds=600.0)
    memory = ClimateMemory(motor_speed=3, motor_speed_since=0.0)
    forcé, _ = run_forced(settings, memory, mono=1.0, motor=(2_000.0, 100.0))
    assert forcé.motor_speed == 0


def test_verrou_moteur_leve_une_alarme_quand_la_serre_monte(climate_settings):
    settings = climate_settings()
    froid, _ = run_forced(settings, temperature=21.0, motor=(2_000.0, 100.0))
    assert froid.alarm_code is None

    chaud, _ = run_forced(settings, temperature=40.0, motor=(2_000.0, 100.0))
    assert chaud.alarm_code == ALARM_MOTOR_LOCKOUT
    assert chaud.motor_speed == 0


def test_alarme_de_verrou_ne_masque_pas_le_repli_capteur(climate_settings):
    settings = climate_settings()
    memory = ClimateMemory(sensor_failures=MAX_CONSECUTIVE_SENSOR_FAILURES - 1)
    decision, _ = run_forced(settings, memory, temperature=None,
                             motor=(2_000.0, 100.0))
    assert decision.alarm_code == ALARM_SENSOR_FALLBACK


def test_forcage_echu_sur_l_horloge_murale(climate_settings):
    settings = climate_settings()
    decision, _ = run_forced(settings, temperature=15.0, epoch=3_000.0,
                             heater=(2_000.0, 100.0))
    assert decision.heater_on is True
    assert decision.heater_forced_off is False


def test_forcage_echu_sur_le_monotonic(climate_settings):
    # Saut NTP arrière : l'horloge murale rendrait le forçage éternel.
    settings = climate_settings()
    decision, _ = run_forced(settings, temperature=15.0, epoch=0.0, mono=500.0,
                             heater=(2_000.0, 100.0))
    assert decision.heater_on is True


def test_forcage_moteur_ne_consomme_aucun_budget_hiver(climate_settings):
    settings = climate_settings(motor_mode="winter")
    verrou = (2_000.0, 100_000.0)
    _, memory = run_forced(settings, temperature=21.0, motor=verrou)
    decision, memory = run_forced(settings, memory, mono=600.0, temperature=21.0,
                                  motor=verrou)
    assert decision.motor_speed == 0
    assert memory.renew_minutes_used == 0.0
