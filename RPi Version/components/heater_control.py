# controller/components/heater_control.py
import asyncio
from datetime import datetime
from utils.pretty_console import info, warning


async def heat_control(
    *,
    heater_component,
    sensor_handler,
    config,             # AppConfig
    sampling_time: int = 60
):
    """
    Pilote le chauffage avec hystérésis stricte :
      • Chauffage forcé OFF si désactivé manuellement
      • Sinon :
          - Allume si T ≤ temp_min
          - Éteint si T > temp_min + hysteresis
          - Sinon conserve l’état précédent
    """
    current_state = heater_component.get_state()  # récupération initiale

    while True:
        if not config.heater_settings.enabled:
            if current_state != 0:
                heater_component.set_state(0)
                current_state = 0
                info("Chauffage désactivé manuellement → OFF")
            await asyncio.sleep(sampling_time)
            continue

        # Détermination jour/nuit
        now_m = datetime.now().hour * 60 + datetime.now().minute
        start = config.daily_timer1.start_hour * 60 + config.daily_timer1.start_minute
        stop  = config.daily_timer1.stop_hour  * 60 + config.daily_timer1.stop_minute
        is_day = start <= now_m <= stop if start <= stop else now_m >= start or now_m <= stop

        # Plage de consigne
        temp_min = config.temperature.target_temp_min_day if is_day else config.temperature.target_temp_min_night
        hysteresis = config.temperature.hysteresis_offset

        # Lecture température
        temp = sensor_handler.get_sensor_value("BME280T")
        if temp is None:
            warning("Chauffage - lecture de la T ambiante échouée")
        else:
            seuil_off = temp_min + hysteresis
            info(f"Chauffage – T={temp:.1f}°C, min={temp_min:.1f}, seuil OFF={seuil_off:.1f}")

            if temp <= temp_min and current_state == 0:
                heater_component.set_state(1)
                current_state = 1
                info("Chauffage → ON")

            elif temp > seuil_off and current_state == 1:
                heater_component.set_state(0)
                current_state = 0
                info("Chauffage → OFF")

            else:
                info(f"Chauffage → État conservé : {'ON' if current_state else 'OFF'}")

        await asyncio.sleep(sampling_time)
