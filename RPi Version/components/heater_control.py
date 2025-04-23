# controller/components/heater_control.py
import asyncio
from ui.pretty_console import info, warning

async def heat_control(
    *,
    heater_component,
    sensor_handler,
    parameters,
    sampling_time: int = 60
):
    """
    Pilote le chauffage via hystérésis + override manuel :
      • Si heater_enabled != "enabled" → chauffage forcé OFF, on attend
      • Sinon : on calcule plage jour/nuit, on compare T ambiante et t_min/max ± offset, on ON/OFF
    """
    from datetime import datetime

    while True:
        # override manuel
        if parameters.get_heater_enabled() != "enabled":
            heater_component.set_state(0)
            info("Chauffage désactivé manuellement → OFF")
            await asyncio.sleep(sampling_time)
            continue

        # on récupère l'heure actuelle en minutes
        now_minutes = datetime.now().hour * 60 + datetime.now().minute

        # période jour selon DailyTimer#1
        start = parameters.get_dailytimer1_start_hour() * 60 + parameters.get_dailytimer1_start_minute()
        stop  = parameters.get_dailytimer1_stop_hour()  * 60 + parameters.get_dailytimer1_stop_minute()
        if start <= stop:
            is_day = (start <= now_minutes <= stop)
        else:
            # chevauche minuit
            is_day = (now_minutes >= start or now_minutes <= stop)

        # consignes + offset d’hystérésis
        offset = parameters.get_hysteresis_offset()
        if is_day:
            t_min = parameters.get_target_temp_min_day()   - offset
            t_max = parameters.get_target_temp_max_day()   + offset
        else:
            t_min = parameters.get_target_temp_min_night() - offset
            t_max = parameters.get_target_temp_max_night() + offset

        temp = sensor_handler.get_sensor_value("BME280T")
        if temp is None:
            warning("Chauffage - lecture T ambiante échouée")
        else:
            info(f"Chauffage - T={temp:.1f}°C, plage [{t_min:.1f};{t_max:.1f}]")
            if temp < t_min:
                heater_component.set_state(1)
                info("Chauffage → ON")
            elif temp > t_max:
                heater_component.set_state(0)
                info("Chauffage → OFF")
            # sinon on conserve l’état courant

        await asyncio.sleep(sampling_time)
