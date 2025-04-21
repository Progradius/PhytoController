# Author: Progradius (adapted)
# License: AGPL 3.0

from lib.sensors.VEML6075 import VEML6075


class VEMLHandler:
    """
    Handler pour le capteur UV VEML6075.
    Permet de lire l'index UV, les UVA et UVB individuellement.
    """

    def __init__(self, i2c):
        self.veml = VEML6075(i2c=i2c)

    def get_veml_uv_index(self):
        try:
            return self.veml.uv_index
        except Exception as e:
            print("Erreur lecture VEML6075 (UV Index) :", e)
            return None

    def get_veml_uva(self):
        try:
            return self.veml.uva
        except Exception as e:
            print("Erreur lecture VEML6075 (UVA) :", e)
            return None

    def get_veml_uvb(self):
        try:
            return self.veml.uvb
        except Exception as e:
            print("Erreur lecture VEML6075 (UVB) :", e)
            return None
