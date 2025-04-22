# lib/sensors/VL53L0X.py
# Adapté pour Python 3 / Raspberry Pi avec smbus2
# Author: Progradius (adapté)
# License: AGPL 3.0

import struct
import time

# Constantes (anciens const())
_IO_TIMEOUT            = 1000
_SYSRANGE_START        = 0x00
_EXTSUP_HV             = 0x89
_MSRC_CONFIG           = 0x60
_FINAL_RATE_RTN_LIMIT  = 0x44
_SYSTEM_SEQUENCE       = 0x01
_SPAD_REF_START        = 0x4f
_SPAD_ENABLES          = 0xb0
_REF_EN_START_SELECT   = 0xb6
_SPAD_NUM_REQUESTED    = 0x4e
_INTERRUPT_GPIO        = 0x0a
_INTERRUPT_CLEAR       = 0x0b
_GPIO_MUX_ACTIVE_HIGH  = 0x84
_RESULT_INTERRUPT_STATUS = 0x13
_RESULT_RANGE_STATUS   = 0x14
_OSC_CALIBRATE         = 0xf8
_MEASURE_PERIOD        = 0x04


class TimeoutError(RuntimeError):
    """Timeout lors d'une opération I2C / capteur."""
    pass


class VL53L0X:
    """
    Driver VL53L0X pour Raspberry Pi (smbus2).
    __init__(i2c_bus, address=0x29)
    Méthode read() retourne la distance en mm.
    """

    def __init__(self, i2c_bus, address=0x29):
        self._i2c = i2c_bus
        self._addr = address
        self._started = False
        self._init_sensor()

    def _read_regs(self, register, count, fmt):
        """
        Lit 'count' octets depuis 'register', et unpack selon 'fmt' struct.
        """
        raw = self._i2c.read_i2c_block_data(self._addr, register, count)
        b = bytes(raw)
        return struct.unpack(fmt, b)

    def _write_regs(self, register, fmt, *values):
        """
        Pack 'values' selon 'fmt' et écrit sur 'register'.
        """
        data = struct.pack(fmt, *values)
        self._i2c.write_i2c_block_data(self._addr, register, list(data))

    def _read_reg(self, register, fmt='B'):
        return self._read_regs(register, struct.calcsize(fmt), fmt)[0]

    def _write_reg(self, register, fmt, value):
        self._write_regs(register, fmt, value)

    def _flag(self, register, bit, value=None):
        """
        Lit un bit, ou le modifie si value booléen donné.
        """
        v = self._read_reg(register)
        mask = 1 << bit
        if value is None:
            return bool(v & mask)
        v = (v | mask) if value else (v & ~mask)
        self._write_reg(register, 'B', v)

    def _config(self, *tuples):
        """
        Initialise une série de (reg, value) à 8‑bits.
        """
        for reg, val in tuples:
            self._write_reg(reg, 'B', val)

    def _init_sensor(self):
        """Reprend la logique de init() MicroPython, traduit en smbus2."""
        # Support 2v8
        self._flag(_EXTSUP_HV, 0, True)

        # Séquence de configuration initiale
        self._config(
            (0x88, 0x00),
            (0x80, 0x01),
            (0xff, 0x01),
            (0x00, 0x00),
        )
        self._stop_variable = self._read_reg(0x91)
        self._config(
            (0x00, 0x01),
            (0xff, 0x00),
            (0x80, 0x00),
        )

        # Désactive les checks
        self._flag(_MSRC_CONFIG, 1, True)
        self._flag(_MSRC_CONFIG, 4, True)

        # rate_limit = 0.25 * 2^7
        self._write_reg(_FINAL_RATE_RTN_LIMIT, '>H', int(0.25 * (1 << 7)))

        # Séquence système
        self._write_reg(_SYSTEM_SEQUENCE, 'B', 0xff)

        # SPAD setup
        spad_count, is_ap = self._spad_info()
        spad_map = bytearray(self._read_regs(_SPAD_ENABLES, 6, '6B'))

        # Configure les SPADs
        self._config(
            (0xff, 0x01),
            (_SPAD_REF_START, 0x00),
            (_SPAD_NUM_REQUESTED, 0x2c),
            (0xff, 0x00),
            (_REF_EN_START_SELECT, 0xb4),
        )

        enabled = 0
        for i in range(48):
            byte_index = i // 8
            bit_index  = i % 8
            if (i < 12 and is_ap) or (enabled >= spad_count):
                spad_map[byte_index] &= ~(1 << bit_index)
            elif spad_map[byte_index] & (1 << bit_index):
                enabled += 1

        # Écriture du nouveau mask SPAD
        self._i2c.write_i2c_block_data(self._addr, _SPAD_ENABLES, list(spad_map))

        # Suite de config longue...
        self._config(
            (0xff, 0x01), (0x00, 0x00),
            (0xff, 0x00), (0x09, 0x00), (0x10, 0x00), (0x11, 0x00),
            (0x24, 0x01), (0x25, 0xFF), (0x75, 0x00),
            (0xFF, 0x01), (0x4E, 0x2C), (0x48, 0x00), (0x30, 0x20),
            (0xFF, 0x00), (0x30, 0x09), (0x54, 0x00), (0x31, 0x04),
            (0x32, 0x03), (0x40, 0x83), (0x46, 0x25), (0x60, 0x00),
            (0x27, 0x00), (0x50, 0x06), (0x51, 0x00), (0x52, 0x96),
            (0x56, 0x08), (0x57, 0x30), (0x61, 0x00), (0x62, 0x00),
            (0x64, 0x00), (0x65, 0x00), (0x66, 0xA0), (0xFF, 0x01),
            (0x22, 0x32), (0x47, 0x14), (0x49, 0xFF), (0x4A, 0x00),
            (0xFF, 0x00), (0x7A, 0x0A), (0x7B, 0x00), (0x78, 0x21),
            (0xFF, 0x01), (0x23, 0x34), (0x42, 0x00), (0x44, 0xFF),
            (0x45, 0x26), (0x46, 0x05), (0x40, 0x40), (0x0E, 0x06),
            (0x20, 0x1A), (0x43, 0x40), (0xFF, 0x00), (0x34, 0x03),
            (0x35, 0x44), (0xFF, 0x01), (0x31, 0x04), (0x4B, 0x09),
            (0x4C, 0x05), (0x4D, 0x04), (0xFF, 0x00), (0x44, 0x00),
            (0x45, 0x20), (0x47, 0x08), (0x48, 0x28), (0x67, 0x00),
            (0x70, 0x04), (0x71, 0x01), (0x72, 0xFE), (0x76, 0x00),
            (0x77, 0x00), (0xFF, 0x01), (0x0D, 0x01), (0xFF, 0x00),
            (0x80, 0x01), (0x01, 0xF8), (0xFF, 0x01), (0x8E, 0x01),
            (0x00, 0x01), (0xFF, 0x00), (0x80, 0x00),
        )

        # Interruption et clear
        self._write_reg(_INTERRUPT_GPIO, 'B', 0x04)
        self._flag(_GPIO_MUX_ACTIVE_HIGH, 4, False)
        self._write_reg(_INTERRUPT_CLEAR, 'B', 0x01)

        # Calibrations VHV
        self._write_reg(_SYSTEM_SEQUENCE, 'B', 0x01)
        self._calibrate(0x40)
        self._write_reg(_SYSTEM_SEQUENCE, 'B', 0x02)
        self._calibrate(0x00)

        self._write_reg(_SYSTEM_SEQUENCE, 'B', 0xE8)

    def _spad_info(self):
        """Lit et renvoie (count, is_aperture)."""
        self._config(
            (0x80, 0x01), (0xff, 0x01), (0x00, 0x00), (0xff, 0x06),
        )
        self._flag(0x83, 3, True)
        self._config((0xff, 0x07), (0x81, 0x01), (0x80, 0x01),
                     (0x94, 0x6b), (0x83, 0x00))
        for _ in range(_IO_TIMEOUT):
            if self._read_reg(0x83):
                break
            time.sleep(0.003)
        else:
            raise TimeoutError()
        # Stop sequence SPAD
        self._config((0x83, 0x01),)
        value = self._read_reg(0x92)
        # Reset sequence
        self._config((0x81, 0x00), (0xff, 0x06))
        self._flag(0x83, 3, False)
        self._config((0xff, 0x01), (0x00, 0x01), (0xff, 0x00), (0x80, 0x00))
        count = value & 0x7F
        is_ap = bool(value & 0x80)
        return count, is_ap

    def _calibrate(self, vhv_init_byte):
        """Déclenche et attend la calibration VHV."""
        self._write_reg(_SYSRANGE_START, 'B', 0x01 | vhv_init_byte)
        for _ in range(_IO_TIMEOUT):
            if self._read_reg(_RESULT_INTERRUPT_STATUS) & 0x07:
                break
            time.sleep(0.001)
        else:
            raise TimeoutError()
        self._write_reg(_INTERRUPT_CLEAR, 'B', 0x01)
        self._write_reg(_SYSRANGE_START, 'B', 0x00)

    def start(self, period_ms=0):
        """
        Démarre le ranging. Si period_ms>0, passe en continuous à ce period.
        """
        self._config(
            (0x80, 0x01), (0xFF, 0x01), (0x00, 0x00),
            (0x91, self._stop_variable), (0x00, 0x01),
            (0xFF, 0x00), (0x80, 0x00),
        )
        if period_ms:
            osc = self._read_reg(_OSC_CALIBRATE, '>H')
            period = int(period_ms * osc)
            self._write_reg(_MEASURE_PERIOD, '>H', period)
            self._write_reg(_SYSRANGE_START, 'B', 0x04)
        else:
            self._write_reg(_SYSRANGE_START, 'B', 0x02)
        self._started = True

    def stop(self):
        """Arrête le ranging."""
        self._write_reg(_SYSRANGE_START, 'B', 0x01)
        self._config(
            (0xFF, 0x01), (0x00, 0x00),
            (0x91, self._stop_variable),
            (0x00, 0x01), (0xFF, 0x00),
        )
        self._started = False

    def read(self):
        """
        Lit une mesure. Si non démarré, lance un measurement unique.
        Retourne la distance en mm.
        """
        if not self._started:
            # single shot
            self._config(
                (0x80, 0x01), (0xFF, 0x01), (0x00, 0x00),
                (0x91, self._stop_variable), (0x00, 0x01), (0xFF, 0x00),
                (_SYSRANGE_START, 0x01),
            )
            for _ in range(_IO_TIMEOUT):
                if (self._read_reg(_SYSRANGE_START) & 0x01) == 0:
                    break
                time.sleep(0.001)
            else:
                raise TimeoutError()

        # attend la fin de la mesure
        for _ in range(_IO_TIMEOUT):
            if self._read_reg(_RESULT_INTERRUPT_STATUS) & 0x07:
                break
            time.sleep(0.001)
        else:
            raise TimeoutError()

        # lecture du résultat (MSB:LSB)
        msb, lsb = self._read_regs(_RESULT_RANGE_STATUS + 10, 2, '>HH')
        # clear interrupt
        self._write_reg(_INTERRUPT_CLEAR, 'B', 0x01)
        return (msb << 8) | (lsb & 0xFF)
