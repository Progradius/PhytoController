# Author: Progradius
# License: AGPL 3.0

import ure
import gc
import ujson
from controller import parameter_handler
from controller.SensorHandler import SensorHandler


class API:
    def __init__(self, writer, response, controller_status, parameters):
        self.controller_status = controller_status
        self.response = response
        self.parameters = parameters
        self.sensor_handler = SensorHandler(self.parameters)
        self.writer = writer

    def api_manager(self):
        print(self.response.find('/temperature'))
        """ Handle query string and apply corresponding logic """

        # Dailytimer1 query string: parse DailyTimer Start and Stop time
        gc.collect()
        if str(self.response).find('dt1start') != -1 and str(self.response).find('dt1stop') != -1:
            self.dailytimer_configuration()
        # Cyclic1 query string: parse period and duration
        if str(self.response).find('period') != -1 and str(self.response).find('duration') != -1:
            self.cyclic_configuration()
        # Temperature route, return a JSON
        if str(self.response).find('/temperature') and str(self.response).find('/temperature') == 6:
            print("into temp")
            yield from self.writer.awrite("HTTP/1.0 200 OK\r\n\r\n" + self.temperature_json() + "\r\n")
        # Hygrometry route, return a JSON
        if str(self.response).find('/hygrometry') and str(self.response).find('/hygrometry') == 6:
            return self.hygrometry_json()
        # System state route, return a JSON
        if str(self.response).find('/status') and str(self.response).find('/status') == 6:
            return self.system_state_json()

    def dailytimer_configuration(self):
        """ Parse response and apply found parameters """
        try:
            # Start time
            dailytimer_start_time_raw = ure.search('dt1start=\\d+(%3A)\\d+', self.response) \
                .group(0).decode('utf-8').replace('%3A', ':')
            dailytimer_start_time_clean = ure.search('\\d+(:)\\d+', dailytimer_start_time_raw) \
                .group(0).split(':')

            # Stop time
            dailytimer_stop_time_raw = ure.search('dt1stop=\\d+(%3A)\\d+', self.response) \
                .group(0).decode('utf-8').replace('%3A', ':')
            dailytimer_stop_time_clean = ure.search('\\d+(:)\\d+', dailytimer_stop_time_raw) \
                .group(0).split(':')

            # Cleaned and Parsed start time:
            dailytimer_start_hour = int(dailytimer_start_time_clean[0])
            dailytimer_start_minute = int(dailytimer_start_time_clean[1])
            # Cleaned and Parsed stop time
            dailytimer_stop_hour = int(dailytimer_stop_time_clean[0])
            dailytimer_stop_minute = int(dailytimer_stop_time_clean[1])

            # Converting stop and start time into minutes
            dailytimer_start_time = dailytimer_start_hour * 60 + dailytimer_start_minute
            dailytimer_stop_time = dailytimer_stop_hour * 60 + dailytimer_stop_minute

            # Check correctness of time (one day is 1440 min, and it cannot be exceeded)
            if dailytimer_start_time > 1440 or dailytimer_start_time < 0:
                # If entered time is incorrect, setting time by default to midnight
                print("Incorrect start time selected, setting time to midnight")
                dailytimer_start_hour = 0
                dailytimer_start_minute = 0

            if dailytimer_stop_time > 1440 or dailytimer_stop_time < 0:
                # If entered time is incorrect, setting time by default to 1am
                print("Incorrect stop time selected, setting time to 1am")
                dailytimer_stop_hour = 1
                dailytimer_stop_minute = 0

            print("Choosen start time: " + str(dailytimer_start_hour) + ':' + str(dailytimer_start_minute))
            print("Choosen stop time: " + str(dailytimer_stop_hour) + ':' + str(dailytimer_stop_minute))

            # Set parameters
            try:
                self.parameters.set_dailytimer1_start_hour(dailytimer_start_hour)
                self.parameters.set_dailytimer1_start_minute(dailytimer_start_minute)
                self.parameters.set_dailytimer1_stop_hour(dailytimer_stop_hour)
                self.parameters.set_dailytimer1_stop_minute(dailytimer_start_minute)
                parameter_handler.write_current_parameters_to_json(self.parameters)
                gc.collect()

            except OSError as e:
                print("Error while writing parameters: ", e)

        except OSError as e:
            print("Error during DT parsing: ", e)

    def cyclic_configuration(self):
        """ Parse response and apply cyclic found parameters """
        period_raw = ure.search('period=\\d+', self.response).group(0).decode('utf-8')
        period_clean = ure.search('\\d+', period_raw).group(0)
        duration_raw = ure.search('duration=\\d+', self.response).group(0).decode('utf-8')
        duration_clean = ure.search('\\d+', duration_raw).group(0)

        try:
            self.parameters.set_cyclic1_period_minutes(period_clean)
            self.parameters.set_cyclic1_action_duration_seconds(duration_clean)
            parameter_handler.write_current_parameters_to_json(self.parameters)
            print("Choosen period: " + str(period_clean))
            print("Choosen duration: " + str(duration_clean))
            gc.collect()
        except OSError as e:
            print("Error while writing parameters: ", e)
            gc.collect()

    def temperature_json(self):
        temperature = {}
        if self.sensor_handler.bme is not None:
            temperature["BME280"] = self.sensor_handler.bme.get_bme_temp()
        if self.sensor_handler.ds18 is not None:
            temperature["DS18#1"] = self.sensor_handler.ds18.get_ds18_temp(1)
            temperature["DS18#2"] = self.sensor_handler.ds18.get_ds18_temp(2)
            temperature["DS18#3"] = self.sensor_handler.ds18.get_ds18_temp(3)
        json = ujson.dumps(temperature)
        return json

    def hygrometry_json(self):
        if self.sensor_handler.bme is not None:
            hygrometry = {"BME280HR": self.sensor_handler.bme.get_bme_hygro()}
            json = ujson.dumps(hygrometry)
            return json

    def pressure_json(self):
        if self.sensor_handler.bme is not None:
            pressure = {"BME280PR": self.sensor_handler.bme.get_bme_pressure()}
            json = ujson.dumps(pressure)
            return json

    def system_state_json(self):
        system_state = {"component_state": self.controller_status.get_component_state(),
                        "motor_speed": self.controller_status.get_motor_speed(),
                        "dailytimer1_start_time": self.controller_status.get_dailytimer_current_start_time(),
                        "dailytimer_stop_time": self.controller_status.get_dailytimer_current_stop_time(),
                        "cyclic_duration": self.controller_status.get_cyclic_duration(),
                        "cyclic_period": self.controller_status.get_cyclic_period()}
        json = ujson.dumps(system_state)
        return json
