# Author: Progradius
# License: AGPL 3.0

import asyncio
import requests
import gc
from urllib.parse import urlencode
from model.Parameter import Parameter
from controller.SensorHandler import SensorHandler

# Initialisation des paramètres
parameters = Parameter()
sensor_handler = SensorHandler(parameters=parameters)

influx_db_host = f"http://{parameters.get_host_machine_address()}:{parameters.get_influx_db_port()}"
influx_db_name = parameters.get_influx_db_name()
influx_db_user = parameters.get_influx_db_user()
influx_db_password = parameters.get_influx_db_password()

# Construction de l'URL complète avec credentials (InfluxDB v1.x)
db_query = f"{influx_db_host}/write?" + urlencode({
    "db": influx_db_name,
    "u": influx_db_user,
    "p": influx_db_password
})

def write_influx_data(measurement, field_name, sensor_data):
    """
    Écrit une donnée dans InfluxDB via l’API HTTP.
    """
    resp_data = f"{measurement} {field_name}={sensor_data}"
    formatted = f"Measurement: {measurement} Field Name: {field_name} Value = {sensor_data}"

    try:
        print(formatted)
        resp = requests.post(db_query, data=resp_data)
        print(f"response: {resp.status_code}")
        if resp.status_code == 204:
            print("OK")
        else:
            print("ERROR")
    except Exception as e:
        print(f"Error sending data to InfluxDB: {e}")
    finally:
        gc.collect()

async def write_sensor_values(sampling_delay=60):
    """
    Envoie périodiquement les données des capteurs à InfluxDB.
    """
    while True:
        sensor_dict = sensor_handler.sensor_dict
        for measurement, sensors in sensor_dict.items():
            for sensor_name in sensors:
                value = sensor_handler.get_sensor_value(sensor_name)
                write_influx_data(measurement, sensor_name, value)
        gc.collect()
        await asyncio.sleep(sampling_delay)
