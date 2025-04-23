# controller/components/heater_control.py
# Author: Progradius (adapted)
# License: AGPL 3.0

import asyncio
from datetime import datetime

from ui.pretty_console import info, warning

async def heat_control(
    *,
    heater_component,
    sensor_handler,
    parameters,
    sampling_time: int = 60
):
    """
    Pilote le chauffage via hystérésis :
      ◦ Choisit plage jour/nuit selon horaire DailyTimer
      ◦ Si T < T_min - offset  → ON
      ◦ Si T > T_max + offset  → OFF
      ◦ Sinon conserve l’état précédent et l’affiche
    """
    while True:
        # 1) Mode manuel On/Off
        if parameters.get_heater_enabled() != "enabled":
            info("Chauffage désactivé – contrôle suspendu")
            await asyncio.sleep(sampling_time)
            continue

        # 2) Détermination de la plage jour/nuit d’après DailyTimer #1
        now = datetime.now()
        current = now.hour * 60 + now.minute
        start = parameters.get_dailytimer1_start_hour() * 60 + parameters.get_dailytimer1_start_minute()
        stop  = parameters.get_dailytimer1_stop_hour()  * 60 + parameters.get_dailytimer1_stop_minute()

        if start <= stop:
            is_day = start <= current <= stop
        else:
            is_day = current >= start or current <= stop

        offset = parameters.get_hysteresis_offset()
        if is_day:
            t_min = parameters.get_target_temp_min_day()   - offset
            t_max = parameters.get_target_temp_max_day()   + offset
        else:
            t_min = parameters.get_target_temp_min_night() - offset
            t_max = parameters.get_target_temp_max_night() + offset

        # 3) Lecture de la température ambiante
        temp = sensor_handler.get_sensor_value("BME280T")
        if temp is None:
            warning("Chauffage – lecture T ambiante échouée")
        else:
            info(f"Chauffage – T={temp:.1f}°C, plage [{t_min:.1f};{t_max:.1f}]")
            if temp < t_min:
                heater_component.set_state(1)
                info("Chauffage → ON")
            elif temp > t_max:
                heater_component.set_state(0)
                info("Chauffage → OFF")
            else:
                # 4) Température OK : on conserve l'état précédent
                etat = "ON" if heater_component.get_state() == 1 else "OFF"
                info(f"Chauffage reste → {etat}")

        await asyncio.sleep(sampling_time)
