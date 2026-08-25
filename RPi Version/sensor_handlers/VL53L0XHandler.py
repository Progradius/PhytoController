# controller/sensor/VL53L0XHandler.py
# Author : Progradius
# License: AGPL-3.0
"""
Wrapper pour le télémètre laser VL53L0X.

‣ Initialisation « safe » : si le capteur n'est pas présent sur le bus
  I²C, le handler passe en mode *indisponible* mais n'arrête pas l'appli.
‣ Lecture unique (`get_vl53_reading`) qui retourne toujours un `int`
  (millimètres) ou `None` en cas d'échec/timeout.
"""

import smbus2
from lib.sensors.VL53L0X import VL53L0X, TimeoutError
from utils.pretty_console import debug, info, warning, error

LOGGER_NAME = "sensors.vl53l0x"


class VL53L0XHandler:
    """
    Handler haut-niveau pour le capteur VL53L0X.
    """

    # ------------------------------------------------------------------
    def __init__(self, parameters):
        """
        Parameters
        ----------
        parameters : Parameter
            Objet config  (uniquement pour l'adresse I²C optionnelle).
        """
        addr = getattr(parameters, "get_vl53_address", lambda: 0x29)()
        self.available = False
        try:
            # Ouverture bus I²C 1 (/dev/i2c-1)
            self._bus = smbus2.SMBus(1)
            self._vl53 = VL53L0X(i2c_bus=self._bus, i2c_address=addr)
            self.available = True
            info(f"VL53L0X prêt @0x{addr:02X}", name=LOGGER_NAME)
        except Exception as exc:
            warning(f"Initialisation VL53L0X échouée → capteur désactivé ({exc})", name=LOGGER_NAME)
            self._vl53 = None
            self._bus  = None

    # ------------------------------------------------------------------
    def get_vl53_reading(self):
        """
        Effectue une mesure « single-shot ».

        Returns
        -------
        int | None
            Distance en millimètres ou `None` si erreur/timeout.
        """
        if not self.available:
            debug("VL53L0X indisponible", name=LOGGER_NAME)
            return None

        try:
            return self._vl53.read()
        except TimeoutError:
            warning("VL53L0X : délai d'attente dépassé", name=LOGGER_NAME)
            return None
        except Exception as exc:
            error(f"Lecture VL53L0X échouée : {exc}", name=LOGGER_NAME)
            return None

    # ------------------------------------------------------------------
    def close(self):
        """Libère proprement le bus I²C (optionnel)."""
        if self._bus:
            try:
                self._bus.close()
            except Exception as exc:
                debug(f"Fermeture du bus I²C VL53L0X : {exc}", name=LOGGER_NAME)
