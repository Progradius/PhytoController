# controller/sensor/MLX90614Handler.py
# Author: Progradius
# License: AGPL 3.0

class MLX90614Handler:
    """
    Handler pour le capteur IR MLX90614.
    Fournit get_ambient_temp() et get_object_temp().
    """

    def __init__(self, i2c):
        """
        i2c : instance smbus2.SMBus(1)
        """
        from lib.sensors.MLX90614 import MLX90614
        self.available = False
        try:
            self.mlx = MLX90614(i2c, address=0x5A)
            self.available = True
        except Exception as e:
            print("⚠️ Erreur init MLX90614 :", e)
            self.mlx = None

    def get_ambient_temp(self):
        """
        Retourne la température ambiante (°C) ou None si erreur.
        """
        if not self.available:
            print("⚠️ MLX90614 indisponible (ambiante)")
            return None
        try:
            return self.mlx.read_ambient_temp()
        except Exception as e:
            print("Erreur lecture MLX90614 (ambiante) :", e)
            return None

    def get_object_temp(self):
        """
        Retourne la température de l'objet (°C) ou None si erreur.
        """
        if not self.available:
            print("⚠️ MLX90614 indisponible (objet)")
            return None
        try:
            return self.mlx.read_object_temp()
        except Exception as e:
            print("Erreur lecture MLX90614 (objet) :", e)
            return None
