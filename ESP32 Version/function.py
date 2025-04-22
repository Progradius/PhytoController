# Author: Progradius
# License: AGPL 3.0

import os
import gc
from machine import RTC, Pin
import utime
from ntptime import settime
from controller.parameter_handler import read_parameters_from_json

parameters = read_parameters_from_json()


# Various functions
def convert_time_to_minutes(hour, minute):
    return (int(hour) * 60) + int(minute)


def convert_time_to_seconds(hour, minute, second):
    return (int(hour) * 3600) + (int(minute) * 60) + int(second)


def convert_minute_to_seconds(minutes):
    return int(minutes) * 60


# Get flash size info
def check_flash_usage():
    s = os.statvfs('//')
    return '{0} MB'.format((s[0] * s[3]) / 1048576)


# Get ram info
def check_ram_usage():
    gc.collect()
    F = gc.mem_free()
    A = gc.mem_alloc()
    T = F + A
    P = '{0:.2f}%'.format(F / T * 100)
    print('Total:{0} Free:{1} ({2})'.format(T, F, P))


def set_ntp_time():
    # Set time to UTC 0 with settime() then change it to correct timezone
    try:
        # Set time from NTP (UTC 0)
        settime()
        # Set RTC time
        rtc = RTC()
        # Change UTC to correct one
        utc_shift = 2
        # mktime return the seconds since epoch, translated to a localtime format
        tm = utime.localtime(utime.mktime(utime.localtime()) + utc_shift * 3600)
        tm = tm[0:3] + (0,) + tm[3:6] + (0,)
        rtc.datetime(tm)
    except OSError as e:
        print("Time cannot be set: ", e)


def motor_all_pin_down_at_boot():
    pin1 = Pin(parameters["GPIO_Settings"]["motor_pin1"], Pin.OUT)
    pin2 = Pin(parameters["GPIO_Settings"]["motor_pin2"], Pin.OUT)
    pin3 = Pin(parameters["GPIO_Settings"]["motor_pin3"], Pin.OUT)
    pin4 = Pin(parameters["GPIO_Settings"]["motor_pin4"], Pin.OUT)
    pin1.value(1)
    pin2.value(1)
    pin3.value(1)
    pin4.value(1)
