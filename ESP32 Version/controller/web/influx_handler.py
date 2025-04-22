# Author: Progradius
# License: AGPL 3.0

import gc
import urequests
import uasyncio as asyncio
from model.Parameter import Parameter
from controller.SensorHandler import SensorHandler

parameters = Parameter()
sensor_handler = SensorHandler(parameters=parameters)
influx_db_host = "http://" + parameters.get_host_machine_address() + ":" + parameters.get_influx_db_port()
influx_db_name = parameters.get_influx_db_name()
influx_db_user = parameters.get_influx_db_user()
influx_db_password = parameters.get_influx_db_password()

# Will be used as response for the API, embedding password in clear in the get command
# Will be fixed with inflxudb 2.0

db_query = influx_db_host + "/write?db=" + influx_db_name + "&u=" + influx_db_user + "&p=" + influx_db_password


def write_influx_data(measurement, field_name, sensor_data):
    """ Write into Influxdb using HTTP api
        Use it like that:write_sensor_data(measurement='temperature',
                         field_name='BME280',
                         sensor_data=sensorHandler.get_bme_temp())
                         """

    # InfluxDB measurements headers
    resp_data = measurement + ' ' + field_name + '=' + str(sensor_data)
    resp_data_formated = "Measurement: " + measurement + " Field Name: " + field_name + ' Value = ' + str(sensor_data)

    # POST data to influxdb
    try:
        print(resp_data_formated)
        resp = urequests.post(db_query, data=resp_data)
        print('response: {}'.format(resp.status_code))
        if resp.status_code == 204:
            print('OK')
        else:
            print('ERROR')
        gc.collect()

    except Exception as e:
        print('Error: {}'.format(e))


async def write_sensor_values(sampling_delay=60):
    """
    Write sensor data  asynchronously into InfluxDB,
    using sensor name as a parameter as well as InfluxDB parameters
    """

    while True:
        # Represent a dictionary holding measurement's and sensor's names
        # in form of {"measurement": ["sensor_name",...]}
        sensor_dict = sensor_handler.sensor_dict
        for key, value in sensor_dict.items():
            for item in value:
                # Write data into InfluxDB using custom method
                write_influx_data(measurement=key, field_name=item,
                                  sensor_data=sensor_handler.get_sensor_value(item))
        # Pause the execution of the method, enabling others to be executed, also used as a sampling period
        gc.collect()
        await asyncio.sleep(sampling_delay)
