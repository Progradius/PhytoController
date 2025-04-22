"""

Copyright (C) 2015 Max Hofbauer

Micropython changes Copyright (C) 2016 by Data-Ken Research

Permission is hereby granted, free of charge, to any person obtaining a copy of this software and associated documentation files (the "Software"), to deal in the Software without restriction, including without limitation the rights to use, copy, modify, merge, publish, distribute, sublicense, and/or sell copies of the Software, and to permit persons to whom the Software is furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM, OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE SOFTWARE.
"""


# tsl2591 lux sensor interface
import time
from machine import I2C, Pin

VISIBLE = 2
INFRARED = 1
FULLSPECTRUM = 0

ADDR = 0x29
READBIT = 0x01
COMMAND_BIT = 0xA0
CLEAR_BIT = 0x40
WORD_BIT = 0x20
BLOCK_BIT = 0x10
ENABLE_POWERON = 0x01
ENABLE_POWEROFF = 0x00
ENABLE_AEN = 0x02
ENABLE_AIEN = 0x10
CONTROL_RESET = 0x80
LUX_DF = 408.0
LUX_COEFB = 1.64
LUX_COEFC = 0.59
LUX_COEFD = 0.86

REGISTER_ENABLE = 0x00
REGISTER_CONTROL = 0x01
REGISTER_THRESHHOLDL_LOW = 0x02
REGISTER_THRESHHOLDL_HIGH = 0x03
REGISTER_THRESHHOLDH_LOW = 0x04
REGISTER_THRESHHOLDH_HIGH = 0x05
REGISTER_INTERRUPT = 0x06
REGISTER_CRC = 0x08
REGISTER_ID = 0x0A
REGISTER_CHAN0_LOW = 0x14
REGISTER_CHAN0_HIGH = 0x15
REGISTER_CHAN1_LOW = 0x16
REGISTER_CHAN1_HIGH = 0x17
INTEGRATIONTIME_100MS = 0x00
INTEGRATIONTIME_200MS = 0x01
INTEGRATIONTIME_300MS = 0x02
INTEGRATIONTIME_400MS = 0x03
INTEGRATIONTIME_500MS = 0x04
INTEGRATIONTIME_600MS = 0x05

GAIN_LOW = 0x00
GAIN_MED = 0x10
GAIN_HIGH = 0x20
GAIN_MAX = 0x30


def _bytes_to_int(data):
    return data[0] + (data[1] << 8)


SENSOR_ADDRESS = 0x29


class Tsl2591:
    def __init__(self, i2c, sensor_id,
                 integration=INTEGRATIONTIME_100MS,
                 gain=GAIN_LOW):
        self.i2c = i2c
        self.sensor_id = sensor_id
        self.integration_time = integration
        self.gain = gain
        self.set_timing(self.integration_time)
        self.set_gain(self.gain)
        self.disable()

    def write_byte_data(self, addr, cmd, val):
        buf = bytes([cmd, val])
        self.i2c.writeto(addr, buf)

    def read_word_data(self, addr, cmd):
        assert cmd < 256
        buf = bytes([cmd])
        self.i2c.writeto(addr, buf)
        data = self.i2c.readfrom(addr, 4)
        return _bytes_to_int(data)

    def set_timing(self, integration):
        self.enable()
        self.integration_time = integration
        self.write_byte_data(
            SENSOR_ADDRESS,
            COMMAND_BIT | REGISTER_CONTROL,
            self.integration_time | self.gain
        )
        self.disable()

    def set_gain(self, gain):
        self.enable()
        self.gain = gain
        self.write_byte_data(
            SENSOR_ADDRESS,
            COMMAND_BIT | REGISTER_CONTROL,
            self.integration_time | self.gain
        )
        self.disable()

    def calculate_lux(self, full, ir):
        if (full == 0xFFFF) | (ir == 0xFFFF):
            return 0

        case_integ = {
            INTEGRATIONTIME_100MS: 100.,
            INTEGRATIONTIME_200MS: 200.,
            INTEGRATIONTIME_300MS: 300.,
            INTEGRATIONTIME_400MS: 400.,
            INTEGRATIONTIME_500MS: 500.,
            INTEGRATIONTIME_600MS: 600.,
        }
        if self.integration_time in case_integ.keys():
            atime = case_integ[self.integration_time]
        else:
            atime = 100.

        case_gain = {
            GAIN_LOW: 1.,
            GAIN_MED: 25.,
            GAIN_HIGH: 428.,
            GAIN_MAX: 9876.,
        }

        if self.gain in case_gain.keys():
            again = case_gain[self.gain]
        else:
            again = 1.

        cpl = (atime * again) / LUX_DF
        lux1 = (full - (LUX_COEFB * ir)) / cpl

        lux2 = ((LUX_COEFC * full) - (LUX_COEFD * ir)) / cpl

        return max([lux1, lux2])

    def enable(self):
        self.write_byte_data(
            SENSOR_ADDRESS,
            COMMAND_BIT | REGISTER_ENABLE,
            ENABLE_POWERON | ENABLE_AEN | ENABLE_AIEN
        )

    def disable(self):
        self.write_byte_data(
            SENSOR_ADDRESS,
            COMMAND_BIT | REGISTER_ENABLE,
            ENABLE_POWEROFF
        )

    def get_full_luminosity(self):
        self.enable()
        time.sleep(0.120 * self.integration_time + 1)
        full = self.read_word_data(
            SENSOR_ADDRESS, COMMAND_BIT | REGISTER_CHAN0_LOW
        )
        ir = self.read_word_data(
            SENSOR_ADDRESS, COMMAND_BIT | REGISTER_CHAN1_LOW
        )
        self.disable()
        return full, ir

    def get_luminosity(self, channel):
        full, ir = self.get_full_luminosity()
        if channel == "FULLSPECTRUM":
            return full
        elif channel == "INFRARED":
            return ir
        elif channel == "VISIBLE":
            return full - ir
        else:
            return 0

    def sample(self):
        full, ir = self.get_full_luminosity()
        return self.calculate_lux(full, ir)
