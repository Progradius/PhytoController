# controller/components/heater_control.py
import asyncio
from datetime import datetime
from ui.pretty_console import info, warning

async def heat_control(
    *,
    heater_component,
    sensor_handler,
    config,             # AppConfig
    sampling_time: int = 60
):
    """
    Pilote le chauffage via hystérésis + override manuel :
      • Si config.heater_settings.enabled == False → chauffage forcé OFF
      • Sinon : détermination plage jour/nuit depuis config.daily_timer1,
        calcul des consignes jour/nuit ± offset, et ON/OFF suivant T ambiante.
    """
    while True:
        # override manuel
        if not config.heater_settings.enabled:
            heater_component.set_state(0)
            info("Chauffage désactivé manuellement → OFF")
            await asyncio.sleep(sampling_time)
            continue

        # Calcul horaire : convertit le début/fin du jour en minutes depuis minuit
        start = config.daily_timer1.start_hour   * 60 + config.daily_timer1.start_minute
        stop  = config.daily_timer1.stop_hour    * 60 + config.daily_timer1.stop_minute
        now_m = datetime.now().hour * 60 + datetime.now().minute

        # Détermine si on est en période jour (gère le chevauchement minuit)
        if start <= stop:
            is_day = (start <= now_m <= stop)
        else:
            is_day = (now_m >= start or now_m <= stop)

        # Récupère l’offset d’hystérésis
        offset = config.temperature.hysteresis_offset

        # Détermine plages min/max selon jour/nuit
        if is_day:
            t_min = config.temperature.target_temp_min_day   - offset
            t_max = config.temperature.target_temp_max_day   + offset
        else:
            t_min = config.temperature.target_temp_min_night - offset
            t_max = config.temperature.target_temp_max_night + offset

        # Lecture de la température ambiante
        temp = sensor_handler.get_sensor_value("BME280T")
        if temp is None:
            warning("Chauffage - lecture de la T ambiante échouée")
        else:
            info(f"Chauffage – T={temp:.1f}°C, consignes [{t_min:.1f}; {t_max:.1f}]")
            if temp < t_min:
                heater_component.set_state(1)
                info("Chauffage → ON")
            elif temp > t_max:
                heater_component.set_state(0)
                info("Chauffage → OFF")
            # sinon on conserve l’état

        await asyncio.sleep(sampling_time)
