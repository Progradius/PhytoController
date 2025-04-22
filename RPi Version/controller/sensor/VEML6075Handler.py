# Author: Progradius (adapted)
# License: AGPL 3.0

from lib.sensors.VEML6075 import VEML6075

class VEMLHandler:
    """
    Handler du capteur UV VEML6075 pour Raspberry Pi.
    Initialisation et lectures sécurisées (gestion d'erreurs I2C).
    """

    def __init__(self, i2c, integration_time=100, high_dynamic=True):
        """
        i2c             : instance smbus2.SMBus(1)
        integration_time: 50, 100, 200, 400, 800 (ms)
        high_dynamic    : True pour dynamic range étendu
        """
        self.available = False
        try:
            # Passe le bus et les paramètres au driver
            self.veml = VEML6075(
                i2c=i2c,
                integration_time=integration_time,
                high_dynamic=high_dynamic
            )
            self.available = True
        except Exception as e:
            print("⚠️ Erreur initialisation VEML6075 :", e)
            self.veml = None

    def get_veml_uva(self):
        """Retourne la valeur UVA calibrée, ou None."""
        if not self.available:
            print("⚠️ VEML6075 indisponible pour UVA")
            return None
        try:
            return self.veml.uva
        except Exception as e:
            print("⚠️ Erreur lecture UVA VEML6075 :", e)
            return None

    def get_veml_uvb(self):
        """Retourne la valeur UVB calibrée, ou None."""
        if not self.available:
            print("⚠️ VEML6075 indisponible pour UVB")
            return None
        try:
            return self.veml.uvb
        except Exception as e:
            print("⚠️ Erreur lecture UVB VEML6075 :", e)
            return None

    def get_veml_uv_index(self):
        """Retourne l'indice UV, ou None."""
        if not self.available:
            print("⚠️ VEML6075 indisponible pour UV index")
            return None
        try:
            return self.veml.uv_index
        except Exception as e:
            print("⚠️ Erreur lecture UV Index VEML6075 :", e)
            return None
