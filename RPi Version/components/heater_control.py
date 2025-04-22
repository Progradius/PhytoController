# controller/components/heater_control.py
# Author: Progradius (added)
# License: AGPL 3.0

import asyncio
from datetime import datetime

async def heat_control(
    heater_component,
    parameters,
    sensor_handler,
    sampling_time: int = 60
):
    """
    Pilote le chauffage via hystérésis :
      • Choisit plage jour/nuit selon DailyTimers
      • Si T < T_min - offset → ON
      • Si T > T_max + offset → OFF
    """
    from function import convert_time_to_minutes

    # on récupère les horaires jour/nuit depuis les DailyTimers
    dt1_start = convert_time_to_minutes(
        parameters.get_dailytimer1_start_hour(),
        parameters.get_dailytimer1_start_minute()
    )
    dt1_stop = convert_time_to_minutes(
        parameters.get_dailytimer1_stop_hour(),
        parameters.get_dailytimer1_stop_minute()
    )
    dt2_start = convert_time_to_minutes(
        parameters.get_dailytimer2_start_hour(),
        parameters.get_dailytimer2_start_minute()
    )
    dt2_stop = convert_time_to_minutes(
        parameters.get_dailytimer2_stop_hour(),
        parameters.get_dailytimer2_stop_minute()
    )

    offset = parameters.get_hysteresis_offset()

    while True:
        now_m = convert_time_to_minutes(
            datetime.now().hour,
            datetime.now().minute
        )

        # déterminer si on est en période "jour" ou "nuit"
        if dt1_start <= now_m <= dt1_stop:
            t_min = parameters.get_target_temp_min_day() - offset
            t_max = parameters.get_target_temp_max_day() + offset
            period = "day"
        elif dt2_start <= now_m <= dt2_stop:
            t_min = parameters.get_target_temp_min_night() - offset
            t_max = parameters.get_target_temp_max_night() + offset
            period = "night"
        else:
            # si hors de ces plages, on reste dans la dernière période
            # ou on pourrait définir un comportement par défaut
            t_min = parameters.get_target_temp_min_day() - offset
            t_max = parameters.get_target_temp_max_day() + offset
            period = "day"

        temp = sensor_handler.get_sensor_value("BME280T")
        if temp is None:
            heater_component.set_state(0)
        else:
            # hystérésis : allume si T < t_min, éteint si T > t_max
            if temp < t_min:
                heater_component.set_state(1)
            elif temp > t_max:
                heater_component.set_state(0)
            # sinon on conserve l'état

        await asyncio.sleep(sampling_time)
