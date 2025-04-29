# controller/sensor/MLX90614Handler.py
# Author : Progradius
# License: AGPL-3.0
"""
Handler pour le capteur infrarouge MLX90614.
Expose :
    • get_ambient_temp()  -> température ambiante (°C | None)
    • get_object_temp()   -> température objet    (°C | None)
"""

from ui import pretty_console as pc


class MLX90614Handler:
    """
    Encapsulation haut-niveau du driver ``lib.sensors.MLX90614``.
    """

    ADDR = 0x5A  # adresse I²C par défaut

    # ------------------------------------------------------------------
    # Initialisation
    # ------------------------------------------------------------------
    def __init__(self, i2c):
        """
        Parameters
        ----------
        i2c : smbus2.SMBus
            Instance ouverte sur /dev/i2c-1.
        """
        from lib.sensors.MLX90614 import MLX90614

        self.available = False
        try:
            self.mlx = MLX90614(i2c, address=self.ADDR)
            self.available = True
            pc.success("MLX90614 initialisé")
        except Exception as exc:
            pc.error(f"Impossible d'initialiser le MLX90614 : {exc}")
            self.mlx = None

    # ------------------------------------------------------------------
    # Mesures
    # ------------------------------------------------------------------
    def get_ambient_temp(self):
        """Température ambiante en °C, ou None si lecture impossible."""
        if not self.available:
            pc.warning("MLX90614 non disponible (ambiante)")
            return None
        try:
            value = self.mlx.read_ambient_temp()
            pc.info(f"MLX90614 ambiant : {value:.2f} °C")
            return value
        except Exception as exc:
            pc.error(f"Lecture ambiante MLX90614 échouée : {exc}")
            return None

    # ------------------------------------------------------------------
    def get_object_temp(self):
        """Température objet en °C, ou None si lecture impossible."""
        if not self.available:
            pc.warning("MLX90614 non disponible (objet)")
            return None
        try:
            value = self.mlx.read_object_temp()
            pc.info(f"MLX90614 objet : {value:.2f} °C")
            return value
        except Exception as exc:
            pc.error(f"Lecture objet MLX90614 échouée : {exc}")
            return None
