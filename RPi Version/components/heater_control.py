# controller/components/heater_control.py
# Author: Progradius
# License: AGPL 3.0

import asyncio
from datetime import datetime
from ui.pretty_console import info, warning

# utilitaire pour convertir HH:MM en minutes depuis minuit
def _to_minutes(h, m):
    return int(h) * 60 + int(m)

async def heat_control(
    sensor_handler,
    parameters,
    heater_component,
    sampling_time: int = 60
):
    """
    Pilote le chauffage via hystérésis et plages jour/nuit issues du DailyTimer #1 :
      - On récupère la plage « jour » définie par DailyTimer #1 (start1/stop1).
      - Si l'’'heure courante est dans cette plage → on prend t_min_day / t_max_day,
        sinon → t_min_night / t_max_night.
      - On applique une hystérésis : on allume si T < t_min - offset,
        on éteint si T > t_max + offset, sinon on laisse tel quel.
    """
    while True:
        now = datetime.now()
        current_min = _to_minutes(now.hour, now.minute)

        # jour définie par DailyTimer #1
        start = _to_minutes(
            parameters.get_dailytimer1_start_hour(),
            parameters.get_dailytimer1_start_minute()
        )
        stop = _to_minutes(
            parameters.get_dailytimer1_stop_hour(),
            parameters.get_dailytimer1_stop_minute()
        )

        # déterminer si c'est « jour »
        if start <= stop:
            is_day = start <= current_min < stop
        else:
            # cas chevauchement minuit
            is_day = current_min >= start or current_min < stop

        # choisir les bornes adaptées
        if is_day:
            t_min = parameters.get_target_temp_min_day()
            t_max = parameters.get_target_temp_max_day()
        else:
            t_min = parameters.get_target_temp_min_night()
            t_max = parameters.get_target_temp_max_night()

        # hystérésis configurable
        offset = parameters.get_hysteresis_offset()

        lower = t_min - offset
        upper = t_max + offset

        # lecture température
        temp = sensor_handler.get_sensor_value("BME280T")
        if temp is None:
            warning("Chauffage - lecture température ambiante échouée")
        else:
            info(f"Chauffage - T={temp:.1f}°C, plage [{'day' if is_day else 'night'}] [{t_min}…{t_max}] +/-{offset}")
            if temp < lower:
                heater_component.set_state(1)
                info("▶️  Chauffage : ON")
            elif temp > upper:
                heater_component.set_state(0)
                info("⏹️  Chauffage : OFF")
            else:
                # dans l'’'intervalle, on laisse l'’'état tel quel
                pass

        await asyncio.sleep(sampling_time)
