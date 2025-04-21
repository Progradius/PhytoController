# Author: Progradius
# License: AGPL 3.0

import re
import json
from controller import parameter_handler
from controller.SensorHandler import SensorHandler


class API:
    def __init__(self, writer, response, controller_status, parameters):
        self.controller_status = controller_status
        self.response = response
        self.parameters = parameters
        self.sensor_handler = SensorHandler(self.parameters)
        self.writer = writer

    async def api_manager(self):
        """
        Gère les routes API et déclenche les fonctions appropriées.
        """
        response = str(self.response)

        if 'dt1start' in response and 'dt1stop' in response:
            self.dailytimer_configuration()

        if 'period' in response and 'duration' in response:
            self.cyclic_configuration()

        if response.startswith('GET /temperature'):
            await self.writer.write("HTTP/1.0 200 OK\r\n\r\n" + self.temperature_json() + "\r\n")

        elif response.startswith('GET /hygrometry'):
            await self.writer.write("HTTP/1.0 200 OK\r\n\r\n" + self.hygrometry_json() + "\r\n")

        elif response.startswith('GET /status'):
            await self.writer.write("HTTP/1.0 200 OK\r\n\r\n" + self.system_state_json() + "\r\n")

    def dailytimer_configuration(self):
        try:
            # Start time
            start_match = re.search(r'dt1start=(\d+)%3A(\d+)', self.response)
            stop_match = re.search(r'dt1stop=(\d+)%3A(\d+)', self.response)

            if not start_match or not stop_match:
                print("Invalid time format in request")
                return

            dailytimer_start_hour = int(start_match.group(1))
            dailytimer_start_minute = int(start_match.group(2))
            dailytimer_stop_hour = int(stop_match.group(1))
            dailytimer_stop_minute = int(stop_match.group(2))

            start_time = dailytimer_start_hour * 60 + dailytimer_start_minute
            stop_time = dailytimer_stop_hour * 60 + dailytimer_stop_minute

            if not (0 <= start_time <= 1440):
                print("Incorrect start time, defaulting to 00:00")
                dailytimer_start_hour = 0
                dailytimer_start_minute = 0

            if not (0 <= stop_time <= 1440):
                print("Incorrect stop time, defaulting to 01:00")
                dailytimer_stop_hour = 1
                dailytimer_stop_minute = 0

            print(f"Choosen start time: {dailytimer_start_hour}:{dailytimer_start_minute}")
            print(f"Choosen stop time: {dailytimer_stop_hour}:{dailytimer_stop_minute}")

            self.parameters.set_dailytimer1_start_hour(dailytimer_start_hour)
            self.parameters.set_dailytimer1_start_minute(dailytimer_start_minute)
            self.parameters.set_dailytimer1_stop_hour(dailytimer_stop_hour)
            self.parameters.set_dailytimer1_stop_minute(dailytimer_stop_minute)

            parameter_handler.write_current_parameters_to_json(self.parameters)

        except Exception as e:
            print("Error during DT parsing:", e)

    def cyclic_configuration(self):
        try:
            period_match = re.search(r'period=(\d+)', self.response)
            duration_match = re.search(r'duration=(\d+)', self.response)

            if not period_match or not duration_match:
                print("Invalid cyclic params")
                return

            period = int(period_match.group(1))
            duration = int(duration_match.group(1))

            self.parameters.set_cyclic1_period_minutes(period)
            self.parameters.set_cyclic1_action_duration_seconds(duration)

            parameter_handler.write_current_parameters_to_json(self.parameters)

            print(f"Choosen period: {period}")
            print(f"Choosen duration: {duration}")

        except Exception as e:
            print("Error while writing cyclic parameters:", e)

    def temperature_json(self):
        temperature = {}
        if self.sensor_handler.bme:
            temperature["BME280"] = self.sensor_handler.bme.get_bme_temp()
        if self.sensor_handler.ds18:
            temperature["DS18#1"] = self.sensor_handler.ds18.get_ds18_temp(1)
            temperature["DS18#2"] = self.sensor_handler.ds18.get_ds18_temp(2)
            temperature["DS18#3"] = self.sensor_handler.ds18.get_ds18_temp(3)
        return json.dumps(temperature)

    def hygrometry_json(self):
        if self.sensor_handler.bme:
            hygrometry = {"BME280HR": self.sensor_handler.bme.get_bme_hygro()}
            return json.dumps(hygrometry)

    def pressure_json(self):
        if self.sensor_handler.bme:
            pressure = {"BME280PR": self.sensor_handler.bme.get_bme_pressure()}
            return json.dumps(pressure)

    def system_state_json(self):
        system_state = {
            "component_state": self.controller_status.get_component_state(),
            "motor_speed": self.controller_status.get_motor_speed(),
            "dailytimer1_start_time": self.controller_status.get_dailytimer_current_start_time(),
            "dailytimer_stop_time": self.controller_status.get_dailytimer_current_stop_time(),
            "cyclic_duration": self.controller_status.get_cyclic_duration(),
            "cyclic_period": self.controller_status.get_cyclic_period()
        }
        return json.dumps(system_state)
