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
from utils.pretty_console import info, warning, error


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
            info(f"VL53L0X ready @0x{addr:02X} ✔")
        except Exception as exc:
            warning(f"VL53L0X init failed → capteur désactivé ({exc})")
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
            warning("VL53L0X indisponible")
            return None

        try:
            return self._vl53.read()
        except TimeoutError:
            warning("VL53L0X : délai d'attente dépassé")
            return None
        except Exception as exc:
            error(f"VL53L0X read error : {exc}")
            return None

    # ------------------------------------------------------------------
    def close(self):
        """Libère proprement le bus I²C (optionnel)."""
        if self._bus:
            try:
                self._bus.close()
            except Exception:
                pass
