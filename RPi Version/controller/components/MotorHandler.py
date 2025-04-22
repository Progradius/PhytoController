# Author: Progradius
# License: AGPL 3.0

import asyncio
from time import sleep
from model.Motor import Motor
from controller.SensorHandler import SensorHandler


class MotorHandler:
    """
    Classe utilisée pour gérer le moteur et appliquer la logique liée à la température.
    """

    def __init__(self, parameters):
        self.parameters = parameters
        self.motor = Motor(
            pin1=self.parameters.get_motor_pin1(),
            pin2=self.parameters.get_motor_pin2(),
            pin3=self.parameters.get_motor_pin3(),
            pin4=self.parameters.get_motor_pin4()
        )
        self.all_pin_down()

    def all_pin_down(self):
        """Coupe toutes les sorties GPIO pour sécuriser le moteur."""
        self.motor.set_pin1_value(1)
        self.motor.set_pin2_value(1)
        self.motor.set_pin3_value(1)
        self.motor.set_pin4_value(1)

    def set_motor_speed(self, speed):
        """
        Définit la vitesse du moteur.
        Attention à l'ordre d'activation des pins pour éviter les courts-circuits.
        """
        speed = max(0, min(speed, 4))  # Clamp entre 0 et 4

        self.all_pin_down()
        sleep(1)

        if speed == 0:
            print("Speed set to 0")
        elif speed == 1:
            self.motor.set_pin1_value(0)
            print("Speed set to 1")
        elif speed == 2:
            self.motor.set_pin2_value(0)
            print("Speed set to 2")
        elif speed == 3:
            self.motor.set_pin3_value(0)
            print("Speed set to 3")
        elif speed == 4:
            self.motor.set_pin4_value(0)
            print("Speed set to 4")

        sleep(1)


async def temp_control(motor_handler, parameters, sampling_time):
    """
    Contrôle automatique du moteur en fonction de la température mesurée.
    Utilise un mécanisme d’hystérésis pour éviter les changements brutaux de vitesse.
    """
    while True:
        mode = parameters.get_motor_mode()
        if mode == "manual":
            speed = parameters.get_motor_user_speed()
            print(f"[MANUAL MODE] Choosen speed: {speed}")
            motor_handler.set_motor_speed(speed)
            await asyncio.sleep(60)

        elif mode == "auto":
            sensor_handler = SensorHandler(parameters=parameters)
            temp = sensor_handler.get_sensor_value("BME280T")

            try:
                temp_value = int(round(float(temp)))
            except (TypeError, ValueError):
                print("Invalid temperature value:", temp)
                await asyncio.sleep(sampling_time)
                continue

            target = int(parameters.get_target_temp())
            hysteresis = int(parameters.get_hysteresis())
            min_speed = max(0, min(4, int(parameters.get_motor_min_speed())))
            max_speed = max(0, min(4, int(parameters.get_motor_max_speed())))

            if temp_value < target:
                speed = min_speed
            elif target < temp_value < (target + hysteresis):
                speed = min_speed + 1
            elif (target + hysteresis) <= temp_value < (target + hysteresis * 2):
                speed = min_speed + 2
            elif (target + hysteresis * 2) <= temp_value < (target + hysteresis * 3):
                speed = max_speed
            else:
                speed = max_speed

            speed = min(speed, max_speed)
            print(f"[AUTO MODE] Temp: {temp_value}°C -> Speed: {speed}")
            motor_handler.set_motor_speed(speed)

            await asyncio.sleep(sampling_time)

        else:
            print(f"Unknown motor mode: {mode}")
            await asyncio.sleep(sampling_time)
