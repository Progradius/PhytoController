# controller/components/heater_control.py
# Author: Progradius (adapted)
# License: AGPL 3.0

import asyncio
from datetime import datetime

from ui.pretty_console import info, warning

# controller/components/heater_control.py

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
    """
    from datetime import datetime
    from ui.pretty_console import info, warning

    while True:
        now_h = datetime.now().hour

        # on récupère les consignes jour/nuit
        if (   parameters.get_dailytimer1_start_hour() * 60
            + parameters.get_dailytimer1_start_minute()
            <= datetime.now().hour * 60 + datetime.now().minute
            <= parameters.get_dailytimer1_stop_hour()  * 60
            + parameters.get_dailytimer1_stop_minute()):
            # période « jour » selon DailyTimer #1
            t_min = parameters.get_target_temp_min_day()  - parameters.get_hysteresis_offset()
            t_max = parameters.get_target_temp_max_day()  + parameters.get_hysteresis_offset()
        else:
            # période « nuit »
            t_min = parameters.get_target_temp_min_night() - parameters.get_hysteresis_offset()
            t_max = parameters.get_target_temp_max_night() + parameters.get_hysteresis_offset()

        temp = sensor_handler.get_sensor_value("BME280T")
        if temp is None:
            warning("Chauffage – lecture T ambiante échouée")
        else:
            info(f"Chauffage – T={temp:.1f}°C, plage [{t_min:.1f};{t_max:.1f}]")
            if temp < t_min:
                heater_component.set_state(1)
                info("Chauffage ON")
            elif temp > t_max:
                heater_component.set_state(0)
                info("Chauffage OFF")
            # sinon on conserve l’état courant

        await asyncio.sleep(sampling_time)
