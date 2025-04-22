# lib/sensors/VEML6075.py
# Version: adapté pour Python 3 sur Raspberry Pi
# Author: Progradius (adapté)
# License: AGPL 3.0

import struct
import time

# Adresse I2C du capteur
_VEML6075_ADDR = 0x10

# Registres du VEML6075
_REG_CONF    = 0x00
_REG_UVA     = 0x07
_REG_DARK    = 0x08  # non utilisé ici
_REG_UVB     = 0x09
_REG_UVCOMP1 = 0x0A
_REG_UVCOMP2 = 0x0B
_REV_ID      = 0x0C

# Constantes valides pour le temps d'intégration (ms → code bits)
_VEML6075_UV_IT = {
    50:  0x00,
    100: 0x01,
    200: 0x02,
    400: 0x03,
    800: 0x04
}


class VEML6075:
    """
    Driver VEML6075 pour Raspberry Pi (smbus2).
    usage:
        import smbus2
        bus = smbus2.SMBus(1)
        sensor = VEML6075(bus, integration_time=100, high_dynamic=True)
        uva = sensor.uva
        uvb = sensor.uvb
        uv_index = sensor.uv_index
    """

    def __init__(self,
                 i2c,
                 integration_time=50,
                 high_dynamic=True,
                 uva_a_coef=2.22,
                 uva_b_coef=1.33,
                 uvb_c_coef=2.95,
                 uvb_d_coef=1.74,
                 uva_response=0.001461,
                 uvb_response=0.002591):
        """
        i2c: instance smbus2.SMBus(1)
        integration_time: 50,100,200,400 ou 800 (ms)
        high_dynamic: True pour extended dynamic range
        coefficients: calibration UVA/UVB selon datasheet
        """
        self._i2c = i2c
        self._addr = _VEML6075_ADDR
        self._a = uva_a_coef
        self._b = uva_b_coef
        self._c = uvb_c_coef
        self._d = uvb_d_coef
        self._uvaresp = uva_response
        self._uvbresp = uvb_response
        self._uvacalc = None
        self._uvbcalc = None

        # Vérification de l'ID du capteur
        veml_id = self._read_register(_REV_ID)
        if veml_id != 0x26:
            raise RuntimeError(f"Incorrect VEML6075 ID 0x{veml_id:02X}")

        # Shutdown (bit0 = 1)
        self._write_register(_REG_CONF, 0x01)

        # Réglage du temps d'intégration
        self.integration_time = integration_time

        # Activation et dynamic range
        conf = self._read_register(_REG_CONF)
        if high_dynamic:
            conf |= 0x08
        conf &= ~0x01  # clear shutdown bit = power on
        self._write_register(_REG_CONF, conf)

    def _read_register(self, register):
        """
        Lit 2 octets (LSB, MSB) et renvoie un entier 16 bits.
        """
        data = self._i2c.read_i2c_block_data(self._addr, register, 2)
        # data[0]=LSB, data[1]=MSB
        return data[0] | (data[1] << 8)

    def _write_register(self, register, value):
        """
        Écrit 2 octets (LSB, MSB) dans un registre.
        """
        lsb = value & 0xFF
        msb = (value >> 8) & 0xFF
        self._i2c.write_i2c_block_data(self._addr, register, [lsb, msb])

    def _take_reading(self):
        """
        Lit les registres UVA, UVB et compensation, puis calcule les valeurs calibrées.
        """
        time.sleep(0.1)
        uva = self._read_register(_REG_UVA)
        uvb = self._read_register(_REG_UVB)
        uvcomp1 = self._read_register(_REG_UVCOMP1)
        uvcomp2 = self._read_register(_REG_UVCOMP2)

        self._uvacalc = uva - (self._a * uvcomp1) - (self._b * uvcomp2)
        self._uvbcalc = uvb - (self._c * uvcomp1) - (self._d * uvcomp2)

    @property
    def uva(self):
        """
        Lecture calibrée UVA (counts).
        """
        self._take_reading()
        return self._uvacalc

    @property
    def uvb(self):
        """
        Lecture calibrée UVB (counts).
        """
        self._take_reading()
        return self._uvbcalc

    @property
    def uv_index(self):
        """
        Calcul de l'indice UV à partir des lectures calibrées.
        """
        self._take_reading()
        return ((self._uvacalc * self._uvaresp) +
                (self._uvbcalc * self._uvbresp)) / 2

    @property
    def integration_time(self):
        """
        Temps d'intégration en millisecondes (50,100,200,400,800).
        """
        conf = self._read_register(_REG_CONF)
        key = (conf >> 4) & 0x07  # bits 4:6
        times = list(_VEML6075_UV_IT.keys())
        if 0 <= key < len(times):
            return times[key]
        raise RuntimeError("Invalid integration time")

    @integration_time.setter
    def integration_time(self, val):
        """
        Définit le temps d'intégration (doit être dans _VEML6075_UV_IT).
        """
        if val not in _VEML6075_UV_IT:
            raise RuntimeError("Invalid integration time")
        conf = self._read_register(_REG_CONF)
        conf &= ~0b01110000        # masque bits 4:6
        conf |= (_VEML6075_UV_IT[val] << 4)
        self._write_register(_REG_CONF, conf)
