# lib/sensors/BME280.py
# Adapté pour Python 3 sur Raspberry Pi (smbus2)
# Author: Progradius (adapté)
# License: AGPL 3.0

import struct
import time

# Adresses I2C possibles
BME280_I2C_ADDR1 = 0x76
BME280_I2C_ADDR2 = 0x77

# Registres
_REG_CALIB00 = 0x88  # données de calibration (T1..H1)
_REG_CALIB26 = 0xE1  # suite calibration (H2..H6)
_REG_CTRL_HUM = 0xF2
_REG_STATUS   = 0xF3
_REG_CTRL_MEAS= 0xF4
_REG_CONFIG   = 0xF5
_REG_DATA     = 0xF7  # début des 8 octets temp/pression/hum

class BME280:
    """
    Driver BME280 basique (T/H/P) pour Raspberry Pi (smbus2).
    """

    def __init__(self, i2c_bus, address=BME280_I2C_ADDR1):
        self._i2c  = i2c_bus
        self._addr = address
        # Lecture des coefficients de calibration
        calib = self._i2c.read_i2c_block_data(self._addr, _REG_CALIB00, 26)
        self.dig_T1, self.dig_T2, self.dig_T3, \
        self.dig_P1, self.dig_P2, self.dig_P3, self.dig_P4, self.dig_P5, \
        self.dig_P6, self.dig_P7, self.dig_P8, self.dig_P9, \
        self.dig_H1 = struct.unpack_from('<HhhHhhhhhhhhB', bytes(calib), 0)

        calib2 = self._i2c.read_i2c_block_data(self._addr, _REG_CALIB26, 7)
        self.dig_H2 = struct.unpack_from('<h', bytes(calib2), 0)[0]
        self.dig_H3 = calib2[2]
        e4,e5,e6 = calib2[3], calib2[4], calib2[5]
        self.dig_H4 = (e4 << 4) | (e5 & 0x0F)
        self.dig_H5 = (e6 << 4) | (e5 >> 4)
        self.dig_H6 = struct.unpack('<b', bytes([calib2[6]]))[0]

        # Config de base : oversampling x1, normal mode
        self._i2c.write_i2c_block_data(self._addr, _REG_CTRL_HUM,  [0x01])  # osrs_h = x1
        self._i2c.write_i2c_block_data(self._addr, _REG_CTRL_MEAS, [0x27])  # osrs_t=1, osrs_p=1, mode=normal
        self._i2c.write_i2c_block_data(self._addr, _REG_CONFIG,    [0xA0])  # t_sb=1000ms, filter off

        self._t_fine = 0

    def _read_raw(self):
        # Lit 8 octets : press[0..2], temp[3..5], hum[6..7]
        data = self._i2c.read_i2c_block_data(self._addr, _REG_DATA, 8)
        raw_p = (data[0] << 12) | (data[1] << 4) | (data[2] >> 4)
        raw_t = (data[3] << 12) | (data[4] << 4) | (data[5] >> 4)
        raw_h = (data[6] << 8)  |  data[7]
        return raw_t, raw_p, raw_h

    def _compensate_temp(self, adc_T):
        var1 = (adc_T / 16384.0 - self.dig_T1 / 1024.0) * self.dig_T2
        var2 = (adc_T / 131072.0 - self.dig_T1 / 8192.0)
        var2 = var2 * var2 * self.dig_T3
        self._t_fine = var1 + var2
        return self._t_fine / 5120.0

    def _compensate_press(self, adc_P):
        var1 = self._t_fine / 2.0 - 64000.0
        var2 = var1 * var1 * self.dig_P6 / 32768.0
        var2 = var2 + var1 * self.dig_P5 * 2.0
        var2 = var2 / 4.0 + self.dig_P4 * 65536.0
        var1 = (self.dig_P3 * var1 * var1 / 524288.0 + self.dig_P2 * var1) / 524288.0
        var1 = (1.0 + var1 / 32768.0) * self.dig_P1
        if var1 == 0:
            return 0
        p = 1048576.0 - adc_P
        p = (p - var2 / 4096.0) * 6250.0 / var1
        var1 = self.dig_P9 * p * p / 2147483648.0
        var2 = p * self.dig_P8 / 32768.0
        return p + (var1 + var2 + self.dig_P7) / 16.0

    def _compensate_hum(self, adc_H):
        h = self._t_fine - 76800.0
        h = (adc_H - (self.dig_H4 * 64.0 + self.dig_H5 / 16384.0 * h)) \
            * (self.dig_H2 / 65536.0 * (1.0 + self.dig_H6 / 67108864.0 * h * (1.0 + self.dig_H3 / 67108864.0 * h)))
        h = h * (1.0 - self.dig_H1 * h / 524288.0)
        return max(0.0, min(h, 100.0))

    def read_temperature(self):
        raw_t, _, _ = self._read_raw()
        return round(self._compensate_temp(raw_t), 2)

    def read_pressure(self):
        _, raw_p, _ = self._read_raw()
        return round(self._compensate_press(raw_p) / 100.0, 2)  # hPa

    def read_humidity(self):
        _, _, raw_h = self._read_raw()
        return round(self._compensate_hum(raw_h), 2)
