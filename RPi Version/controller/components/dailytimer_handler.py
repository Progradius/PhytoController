# Author: Progradius
# License: AGPL 3.0

import asyncio
from datetime import datetime


async def timer_daily(dailytimer, sampling_time):
    """
    Routine asynchrone qui vérifie périodiquement si un composant
    doit être activé ou désactivé selon l’heure courante.
    """
    while True:
        now = datetime.now()
        print(f"Checking component state on DailyTimer #{dailytimer.timer_id}")

        dailytimer.toggle_state_daily()

        print(f"Checked at {now.hour}:{now.minute}:{now.second}")
        print("===========")

        await asyncio.sleep(sampling_time)
