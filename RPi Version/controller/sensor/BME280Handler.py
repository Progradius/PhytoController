# controller/sensor/BME280Handler.py
# Author : Progradius (adapted)
# License: AGPL-3.0

"""
Wrapper simple autour de notre driver `lib.sensors.BME280` (dérivé Pimoroni)
pour :

• masquer les différences d'API (get_temperature vs read_temperature, …)
• centraliser la gestion des erreurs
• offrir une variable ``available`` afin que le code appelant sache immédiatement
  si le capteur est prêt
"""

from controller.ui.pretty_console import error, warning, info
from typing import Optional, Callable


class BME280Handler:
    """Handler haut-niveau pour le capteur BME280 (bus I²C /dev/i2c-1)."""

    # --------------------------------------------------------------------- #
    def __init__(self, i2c):
        """
        Parameters
        ----------
        i2c : smbus2.SMBus
            Instance déjà ouverte sur le bus 1 (gérée par SensorHandler).
        """
        try:
            from lib.sensors.BME280 import BME280
        except ModuleNotFoundError as e:
            error("Driver lib.sensors.BME280 introuvable : " + str(e))
            self.available = False
            self._sensor: Optional["BME280"] = None
            return

        # Tentative d'initialisation – le constructeur diffère selon les forks.
        try:
            self._sensor = BME280(i2c_dev=i2c)        # Pimoroni
        except TypeError:
            try:
                self._sensor = BME280(i2c_bus=i2c)    # Variante adafruit
            except Exception as ex:                   # Autre problème
                error(f"❌ Init BME280 impossible : {ex}")
                self.available = False
                self._sensor = None
                return

        info("✅ BME280 détecté et initialisé")
        self.available = True

        # Petites lambdas pour unifier l'API (lecture paresseuse)
        self._read: dict[str, Callable[[], float]] = {
            "temp":     self._probe_method(("get_temperature", "read_temperature")),
            "press":    self._probe_method(("get_pressure",    "read_pressure")),
            "hum":      self._probe_method(("get_humidity",    "read_humidity")),
        }

    # ------------------------------------------------------------------ #
    #  API publique
    # ------------------------------------------------------------------ #
    def get_bme_temp(self):
        return self._safe("temp", "température")

    def get_bme_pressure(self):
        return self._safe("press", "pression")

    def get_bme_hygro(self):
        return self._safe("hum", "humidité")

    # ------------------------------------------------------------------ #
    #  Helpers internes
    # ------------------------------------------------------------------ #
    def _safe(self, key: str, label_fr: str):
        """Enrobe l'accès avec gestion d'erreur uniforme."""
        if not self.available:
            return None
        try:
            val = self._read[key]()
            return round(val, 2) if isinstance(val, (int, float)) else val
        except Exception as e:
            warning(f"BME280 : erreur lecture {label_fr} → {e}")
            return None

    def _probe_method(self, names: tuple[str, str]) -> Callable[[], float]:
        """
        Retourne la 1ʳᵉ méthode existante parmi celles listées.
        Lève AttributeError si aucune n'existe → sera géré plus haut.
        """
        for name in names:
            if hasattr(self._sensor, name):
                return getattr(self._sensor, name)
        raise AttributeError(f"méthodes {names} absentes dans le driver")
