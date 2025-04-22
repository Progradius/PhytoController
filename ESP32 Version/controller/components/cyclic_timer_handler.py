# Author: Progradius
# License: AGPL 3.0

from machine import RTC
import uasyncio as asyncio
from function import convert_minute_to_seconds


async def timer_cylic(cyclic_timer):
    """  Used to make a cyclic timer, working asynchronously """
    while True:
        # Wait for a period of time - extracted from the json config file
        await asyncio.sleep(convert_minute_to_seconds(cyclic_timer.get_period()))
        # Hold current time
        current_time = RTC().datetime()
        print("Checking component state on CyclicTimer: " + str(cyclic_timer.timer_id))

        cyclic_timer.component.set_state(0)
        print(
            "Cyclic: enabling component at: " +
            str(current_time[4]) +
            ':' + str(current_time[5]) +
            ':' + str(current_time[6]))

        await asyncio.sleep(cyclic_timer.get_action_duration())
        cyclic_timer.component.set_state(1)
        current_time = RTC().datetime()
        print(
            "Cyclic: disabling component at: " + str(current_time[4]) +
            ':' + str(current_time[5]) +
            ':' + str(current_time[6]))
