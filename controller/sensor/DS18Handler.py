# Author: Progradius (adapted)
# License: AGPL 3.0

from w1thermsensor import W1ThermSensor, Sensor, Unit, NoSensorFoundError


class DS18Handler:
    """
    Handler pour les capteurs DS18B20 via le bus OneWire (w1).
    Compatible avec la lib `w1thermsensor` sur Raspberry Pi.
    """

    def __init__(self):
        try:
            self.ds18_sensors = W1ThermSensor.get_available_sensors(Sensor.DS18B20)
        except NoSensorFoundError:
            print("Aucun capteur DS18B20 détecté.")
            self.ds18_sensors = []

    def get_address_list(self):
        try:
            return [sensor.id for sensor in self.ds18_sensors]
        except Exception as e:
            print("Erreur lors de la lecture des adresses DS18B20 :", e)
            return []

    def get_ds18_temp(self, sensor_number):
        try:
            index = sensor_number - 1
            if index < 0 or index >= len(self.ds18_sensors):
                print(f"Numéro de capteur invalide : {sensor_number}")
                return None

            sensor = self.ds18_sensors[index]
            temp = sensor.get_temperature(Unit.CELSIUS)
            return temp
        except Exception as e:
            print(f"Erreur lecture DS18B20 #{sensor_number} :", e)
            return None
