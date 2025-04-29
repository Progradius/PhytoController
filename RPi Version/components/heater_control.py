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
    Pilote le chauffage avec hystérésis :
      • Si config.heater_settings.enabled == False → chauffage forcé OFF
      • Sinon : détermine la consigne (temp_min) selon jour/nuit,
        et applique une logique d'hystérésis stricte :
          - Allume si T ≤ temp_min
          - Éteint si T > temp_min + hysteresis
          - Sinon conserve l'état précédent
    """
    current_state = 0  # état précédent : 0=OFF, 1=ON

    while True:
        if not config.heater_settings.enabled:
            if current_state != 0:
                heater_component.set_state(0)
                current_state = 0
                info("Chauffage désactivé manuellement → OFF")
            await asyncio.sleep(sampling_time)
            continue

        # Détermine si période jour ou nuit
        now_m = datetime.now().hour * 60 + datetime.now().minute
        start = config.daily_timer1.start_hour * 60 + config.daily_timer1.start_minute
        stop  = config.daily_timer1.stop_hour  * 60 + config.daily_timer1.stop_minute
        is_day = start <= now_m <= stop if start <= stop else now_m >= start or now_m <= stop

        # Récupère température cible minimale selon période
        temp_min = config.temperature.target_temp_min_day if is_day else config.temperature.target_temp_min_night
        hysteresis = config.temperature.hysteresis_offset

        # Lecture de température ambiante
        temp = sensor_handler.get_sensor_value("BME280T")
        if temp is None:
            warning("Chauffage - lecture de la T ambiante échouée")
        else:
            info(f"Chauffage - T={temp:.1f}°C, min={temp_min:.1f}, seuil OFF={temp_min + hysteresis:.1f}")

            if temp <= temp_min:
                if current_state != 1:
                    heater_component.set_state(1)
                    current_state = 1
                    info("Chauffage → ON")
            elif temp > (temp_min + hysteresis):
                if current_state != 0:
                    heater_component.set_state(0)
                    current_state = 0
                    info("Chauffage → OFF")
            else:
                info(f"Chauffage → État conservé : {'ON' if current_state else 'OFF'}")

        await asyncio.sleep(sampling_time)
