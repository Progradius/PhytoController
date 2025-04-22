# Author: Progradius
# License: AGPL 3.0

from machine import RTC
import uasyncio as asyncio


async def timer_daily(dailytimer, sampling_time):
    """Routine responsible to check if a component must be on or off depending on current time
   Used to make a daily timer"""
    while True:
        # Hold current time
        current_time = RTC().datetime()
        print("Checking component state on DailyTimer: " + str(dailytimer.timer_id))

        # Use the dailytimer object passed in parameter to check his state and act accordingly
        dailytimer.toggle_state_daily()
        # Print checked time
        print("Checked at " + str(current_time[4]) +
              ':' + str(current_time[5]) +
              ':' + str(current_time[6]))
        print("===========")

        await asyncio.sleep(sampling_time)
