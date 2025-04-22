# controller/sensor/BME280Handler.py
# Author: Progradius (adapted)
# License: AGPL 3.0

class BME280Handler:
    """
    Handler du capteur BME280 pour RPi.
    """

    def __init__(self, i2c):
        """
        i2c : instance smbus2.SMBus(1)
        """
        from lib.sensors.BME280 import BME280
        try:
            self.sensor = BME280(i2c_bus=i2c)
            self.available = True
        except Exception as e:
            print("⚠️ Erreur init BME280 :", e)
            self.available = False
            self.sensor = None

    def get_bme_temp(self):
        if not self.available:
            return None
        try:
            return self.sensor.read_temperature()
        except Exception as e:
            print("Erreur lecture BME280 température :", e)
            return None

    def get_bme_pressure(self):
        if not self.available:
            return None
        try:
            return self.sensor.read_pressure()
        except Exception as e:
            print("Erreur lecture BME280 pression :", e)
            return None

    def get_bme_hygro(self):
        if not self.available:
            return None
        try:
            return self.sensor.read_humidity()
        except Exception as e:
            print("Erreur lecture BME280 humidité :", e)
            return None
