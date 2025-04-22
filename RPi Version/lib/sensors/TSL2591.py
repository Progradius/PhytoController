# lib/sensors/TSL2591.py
# Adapté pour Python 3 sur Raspberry Pi
# Author: Progradius (adapté)
# License: AGPL 3.0

import time
import struct

# Constantes de registre et commandes
ADDR           = 0x29
COMMAND_BIT    = 0xA0
CLEAR_BIT      = 0x40
WORD_BIT       = 0x20

REGISTER_ENABLE        = 0x00
REGISTER_CONTROL       = 0x01
REGISTER_CHAN0_LOW     = 0x14
REGISTER_CHAN1_LOW     = 0x16

ENABLE_POWERON  = 0x01
ENABLE_POWEROFF = 0x00
ENABLE_AEN      = 0x02  # ALS enable
ENABLE_AIEN     = 0x10  # ALS interrupt enable

INTEGRATIONTIME_100MS = 0x00
INTEGRATIONTIME_200MS = 0x01
INTEGRATIONTIME_300MS = 0x02
INTEGRATIONTIME_400MS = 0x03
INTEGRATIONTIME_500MS = 0x04
INTEGRATIONTIME_600MS = 0x05

GAIN_LOW   = 0x00
GAIN_MED   = 0x10
GAIN_HIGH  = 0x20
GAIN_MAX   = 0x30

LUX_DF   = 408.0
LUX_COEFB = 1.64
LUX_COEFC = 0.59
LUX_COEFD = 0.86


def _bytes_to_int(lsb, msb):
    """Combine LSB + MSB en entier 16-bit."""
    return lsb | (msb << 8)


class Tsl2591:
    """
    Driver TSL2591 pour Raspberry Pi (smbus2).
    """

    def __init__(self, i2c_bus, integration=INTEGRATIONTIME_100MS, gain=GAIN_LOW):
        """
        i2c_bus   : instance smbus2.SMBus(1)
        integration: temps d'intégration (100..600 ms)
        gain      : GAIN_LOW/MED/HIGH/MAX
        """
        self._i2c = i2c_bus
        self._addr = ADDR
        self.integration_time = integration
        self.gain = gain
        # Initialise le capteur
        self.disable()
        self.set_timing(self.integration_time)
        self.set_gain(self.gain)

    def _write_register(self, reg, value):
        """
        Écrit 1 octet 'value' dans le registre 'reg' (avec COMMAND_BIT).
        """
        cmd = COMMAND_BIT | reg
        self._i2c.write_i2c_block_data(self._addr, cmd, [value & 0xFF])

    def _read_register_word(self, reg):
        """
        Lit 2 octets depuis 'reg' (LSB, MSB) et renvoie un entier 16 bits.
        """
        cmd = COMMAND_BIT | WORD_BIT | reg
        data = self._i2c.read_i2c_block_data(self._addr, cmd, 2)
        return _bytes_to_int(data[0], data[1])

    def enable(self):
        """Allume le capteur + ALS + interruption."""
        self._write_register(REGISTER_ENABLE, ENABLE_POWERON | ENABLE_AEN | ENABLE_AIEN)

    def disable(self):
        """Éteint le capteur."""
        self._write_register(REGISTER_ENABLE, ENABLE_POWEROFF)

    def set_timing(self, integration):
        """Définit le temps d'intégration (100..600 ms)."""
        self.enable()
        control = (integration & 0x07) | (self.gain & 0x30)
        self._write_register(REGISTER_CONTROL, control)
        self.disable()
        self.integration_time = integration

    def set_gain(self, gain):
        """Définit le gain (LOW, MED, HIGH, MAX)."""
        self.enable()
        control = (self.integration_time & 0x07) | (gain & 0x30)
        self._write_register(REGISTER_CONTROL, control)
        self.disable()
        self.gain = gain

    def get_full_luminosity(self):
        """
        Retourne (full, ir) en lecture brute 16 bits.
        """
        self.enable()
        # délai = integration_time * 100 ms + 1 ms margin
        time.sleep((self.integration_time + 1) * 0.1)
        full = self._read_register_word(REGISTER_CHAN0_LOW)
        ir   = self._read_register_word(REGISTER_CHAN1_LOW)
        self.disable()
        return full, ir

    def get_luminosity(self, channel="FULLSPECTRUM"):
        """
        Retourne la lecture brute selon channel :
         - "FULLSPECTRUM": full
         - "INFRARED":      ir
         - "VISIBLE":       full - ir
        """
        full, ir = self.get_full_luminosity()
        if channel == "INFRARED":
            return ir
        if channel == "VISIBLE":
            return full - ir
        return full  # default full spectrum

    def calculate_lux(self, full, ir):
        """
        Calcule la luminosité en lux à partir des lectures brute.
        """
        # cap 0xFFFF → 0
        if full >= 0xFFFF or ir >= 0xFFFF:
            return 0.0

        # mapping integration_time → ms
        ms_map = {
            INTEGRATIONTIME_100MS: 100.0,
            INTEGRATIONTIME_200MS: 200.0,
            INTEGRATIONTIME_300MS: 300.0,
            INTEGRATIONTIME_400MS: 400.0,
            INTEGRATIONTIME_500MS: 500.0,
            INTEGRATIONTIME_600MS: 600.0,
        }
        atime = ms_map.get(self.integration_time, 100.0)

        gain_map = {
            GAIN_LOW: 1.0,
            GAIN_MED: 25.0,
            GAIN_HIGH: 428.0,
            GAIN_MAX: 9876.0,
        }
        again = gain_map.get(self.gain, 1.0)

        cpl    = (atime * again) / LUX_DF
        lux1   = (full - (LUX_COEFB * ir)) / cpl
        lux2   = ((LUX_COEFC * full) - (LUX_COEFD * ir)) / cpl
        return max(lux1, lux2)
