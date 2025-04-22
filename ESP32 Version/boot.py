# Author: Progradius
# License: AGPL 3.0

# This file is executed on every boot (including wake-boot from deepsleep)
import esp
import gc
from function import  motor_all_pin_down_at_boot
# Set motor's pin down at boot, avoding short circuits
motor_all_pin_down_at_boot()
esp.osdebug(None)
gc.collect()

