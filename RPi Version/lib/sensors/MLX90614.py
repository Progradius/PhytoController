# lib/sensors/MLX90614.py
# Adapté pour Python 3 sur Raspberry Pi
# Author: Progradius (adapté)
# License: AGPL 3.0

import struct

# Registres
_REGISTER_TA    = 0x06  # température ambiante
_REGISTER_TOBJ1 = 0x07  # température objet
_REGISTER_TOBJ2 = 0x08  # deuxième thermopile optionnel

class MLX90614:
    """
    Driver MLX90614 pour Raspberry Pi (smbus2).
    Expose read_ambient_temp(), read_object_temp(), read_object2_temp().
    """

    def __init__(self, i2c_bus, address=0x5A):
        """
        i2c_bus : instance smbus2.SMBus(1)
        address : adresse I2C du capteur (0x5A par défaut)
        """
        self._i2c    = i2c_bus
        self._addr   = address

        # Lecture du registre CONFIG1 pour détecter dual-zone
        raw = self._i2c.read_i2c_block_data(self._addr, 0x25, 2)
        cfg1 = struct.unpack('<H', bytes(raw))[0]
        self.dual_zone = bool(cfg1 & (1 << 6))

    def _read16(self, register):
        """
        Lit 2 octets LSB/MSB au registre donné et renvoie un entier 16 bits.
        """
        data = self._i2c.read_i2c_block_data(self._addr, register, 2)
        return struct.unpack('<H', bytes(data))[0]

    def _read_temp(self, register):
        """
        Retourne la température (°C) lue au registre donné :
        (raw * 0.02) - 273.15
        """
        raw = self._read16(register)
        temp = raw * 0.02      # résolution 0.02 °C/LSB
        return round(temp - 273.15, 2)

    def read_ambient_temp(self):
        """
        Température ambiante (°C).
        """
        return self._read_temp(_REGISTER_TA)

    def read_object_temp(self):
        """
        Température de l'objet mesuré (°C).
        """
        return self._read_temp(_REGISTER_TOBJ1)

    def read_object2_temp(self):
        """
        Température du second thermopile, si dual-zone.
        """
        if not self.dual_zone:
            raise RuntimeError("MLX90614: pas de second thermopile disponible")
        return self._read_temp(_REGISTER_TOBJ2)

    @property
    def ambient_temp(self):
        return self.read_ambient_temp()

    @property
    def object_temp(self):
        return self.read_object_temp()

    @property
    def object2_temp(self):
        return self.read_object2_temp()
