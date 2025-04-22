# controller/sensor/DS18Handler.py
# Author: Progradius (adapted)
# License: AGPL 3.0

import glob

try:
    from w1thermsensor import W1ThermSensor, Unit, NoSensorFoundError
    _USE_W1TS = True
except ModuleNotFoundError:
    _USE_W1TS = False

class DS18Handler:
    """
    Handler pour DS18B20 :
    - Si la lib w1thermsensor est installée, on l'utilise.
    - Sinon, on lit dans /sys/bus/w1/devices/.
    """

    SYSFS_BASE = "/sys/bus/w1/devices/28-*"

    def __init__(self):
        if _USE_W1TS:
            try:
                self.sensors = W1ThermSensor.get_available_sensors()
            except NoSensorFoundError:
                print("⚠️ Aucun DS18B20 détecté via w1thermsensor.")
                self.sensors = []
        else:
            # Recherche des dossiers 28-xxxx sur le bus 1-Wire
            self.device_folders = glob.glob(self.SYSFS_BASE)
            if not self.device_folders:
                print("⚠️ Aucun DS18B20 détecté dans sysfs.")

    def get_address_list(self):
        if _USE_W1TS:
            return [sensor.id for sensor in self.sensors]
        else:
            return [f.split("/")[-1] for f in self.device_folders]

    def get_ds18_temp(self, sensor_number):
        idx = sensor_number - 1
        if _USE_W1TS:
            if idx<0 or idx>=len(self.sensors):
                print(f"⚠️ Capteur DS18#{sensor_number} invalide.")
                return None
            try:
                return round(self.sensors[idx].get_temperature(Unit.CELSIUS), 2)
            except Exception as e:
                print(f"Erreur lecture DS18#{sensor_number} via w1thermsensor :", e)
                return None
        else:
            if idx<0 or idx>=len(self.device_folders):
                print(f"⚠️ Capteur DS18#{sensor_number} invalide.")
                return None
            # Lecture sysfs
            path = self.device_folders[idx] + "/w1_slave"
            try:
                lines = open(path).read().splitlines()
                if lines[0].endswith("YES"):
                    temp_str = lines[1].split("t=")[1]
                    return round(int(temp_str)/1000.0, 2)
                else:
                    print(f"⚠️ CRC invalide pour DS18#{sensor_number}.")
                    return None
            except Exception as e:
                print(f"Erreur lecture DS18#{sensor_number} via sysfs :", e)
                return None
