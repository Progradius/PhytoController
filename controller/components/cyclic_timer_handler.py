# Author: Progradius
# License: AGPL 3.0

import asyncio
from datetime import datetime
from function import convert_minute_to_seconds


async def timer_cylic(cyclic_timer):
    """
    Timer cyclique asynchrone :
    - attend un délai = période
    - active le composant pour une durée = action_duration
    """
    while True:
        # Attendre la période définie
        await asyncio.sleep(convert_minute_to_seconds(cyclic_timer.get_period()))

        now = datetime.now()
        print(f"CyclicTimer #{cyclic_timer.timer_id} - Activation à {now.hour}:{now.minute}:{now.second}")
        cyclic_timer.component.set_state(0)

        # Durée d'activation
        await asyncio.sleep(cyclic_timer.get_action_duration())

        now = datetime.now()
        print(f"CyclicTimer #{cyclic_timer.timer_id} - Désactivation à {now.hour}:{now.minute}:{now.second}")
        cyclic_timer.component.set_state(1)
