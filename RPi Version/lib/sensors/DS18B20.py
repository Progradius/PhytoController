import machine
import time
import onewire
import ds18x20


class DS18:

    def __init__(self, ds_pin):
        self.ds_sensor = ds18x20.DS18X20(onewire.OneWire(ds_pin))
        self.roms = self.ds_sensor.scan()
        # print('Found DS devices: ', self.roms)

    # Retrieve List of DS addresses
    def get_address_list(self):
        self.ds_sensor.convert_temp()
        # Let pass some time to do the calculation
        time.sleep_ms(750)
        return self.roms

    # Read one sensor using his address
    def read_ds_sensor_individually(self, rom):
        self.ds_sensor.convert_temp()
        # Let pass some time to do the calculation
        time.sleep_ms(750)
        current_temp = self.ds_sensor.read_temp(rom)
        if isinstance(current_temp, float):
            msg = round(current_temp, 2)
            return msg
        return '0'
