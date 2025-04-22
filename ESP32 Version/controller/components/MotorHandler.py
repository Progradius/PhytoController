# Author: Progradius
# License: AGPL 3.0

import uasyncio as asyncio
from time import sleep
from model.Motor import Motor
from controller.SensorHandler import SensorHandler


class MotorHandler:
    """
    Class used to handle the motor and apply temperature driven logic
    """

    def __init__(self, parameters):
        self.parameters = parameters
        self.motor = Motor(pin1=self.parameters.get_motor_pin1(),
                           pin2=self.parameters.get_motor_pin2(),
                           pin3=self.parameters.get_motor_pin3(),
                           pin4=self.parameters.get_motor_pin4())
        # Set all pins down for security reason before doing anything else
        self.all_pin_down()

    def all_pin_down(self):
        """Set all pin down for security"""
        self.motor.set_pin1_value(1)
        self.motor.set_pin2_value(1)
        self.motor.set_pin3_value(1)
        self.motor.set_pin4_value(1)

    def set_motor_speed(self, speed):
        """
        Select the motor speed
        Be careful to always have ALL GPIO DOWN BEFORE TURNING ONE UP, to avoid a short circuit
        DANGER will be potentially handling high current and voltage
        """
        # Restrain speed range in case of bad user input
        if speed < 0:
            speed = 0
        if speed > 4:
            speed = 4

        if speed == 0:
            self.all_pin_down()
            print("Speed set to 0")
        if speed == 1:
            self.motor.set_pin2_value(1)
            self.motor.set_pin3_value(1)
            self.motor.set_pin4_value(1)
            sleep(1)
            self.motor.set_pin1_value(0)
            print("Speed set to 1")
        if speed == 2:
            self.motor.set_pin1_value(1)
            self.motor.set_pin3_value(1)
            self.motor.set_pin4_value(1)
            sleep(1)
            self.motor.set_pin2_value(0)
            print("Speed set to 2")
            sleep(1)
        if speed == 3:
            self.motor.set_pin1_value(1)
            self.motor.set_pin2_value(1)
            self.motor.set_pin4_value(1)
            sleep(1)
            self.motor.set_pin3_value(0)
            print("Speed set to 3")
            sleep(1)
        if speed == 4:
            self.motor.set_pin1_value(1)
            self.motor.set_pin2_value(1)
            self.motor.set_pin3_value(1)
            sleep(1)
            self.motor.set_pin4_value(0)
            print("Speed set to 4")
            sleep(1)


async def temp_control(motor_handler, parameters, sampling_time):
    """
    Control motor speed based on current temp
    Has an hysteresis parameter to avoid constant change of speed
    A minimum speed can be set
    """
    while True:
        # Manual Motor mode, let's the user choose his speed
        if parameters.get_motor_mode() == "manual":
            print("Choosen speed: " + str(parameters.get_motor_user_speed()))
            motor_handler.set_motor_speed(parameters.get_motor_user_speed())
            await asyncio.sleep(60)

        # Auto Motor Mode, temperature driven
        if parameters.get_motor_mode() == "auto":
            sensor_handler = SensorHandler(parameters=parameters)
            # Temp value extracted from sensor and rounded into an int
            temp_value = int(round(float(sensor_handler.get_sensor_value("BME280T"))))
            # Environment target temperature
            target = int(motor_handler.parameters.get_target_temp())
            # Hysteresis, the number added or subtracted to the target temp
            hysteresis = int(motor_handler.parameters.get_hysteresis())
            min_speed = int(motor_handler.parameters.get_motor_min_speed())
            max_speed = int(motor_handler.parameters.get_motor_max_speed())

            if min_speed < 0:
                min_speed = 0
            if min_speed > 4:
                min_speed = 4

            # Case if current temp is below targeted temp
            if temp_value < target:
                speed = min_speed
                if speed > max_speed:
                    speed = max_speed
                print("Mode Auto - " + "Temp: " + str(temp_value) + " speed: " + str(speed))
                motor_handler.set_motor_speed(speed)
            # Case if current temp is above targeted temp plus one hysteresis
            elif target < temp_value < (target + hysteresis):
                speed = min_speed + 1
                if speed > max_speed:
                    speed = max_speed
                print("Mode Auto - " + "Temp: " + str(temp_value) + " speed: " + str(speed))
                motor_handler.set_motor_speed(speed)
            # Case if current temp is above targeted temp plus hysteresis,
            # but below target temp + two hysteresis
            elif (target + hysteresis) < temp_value < (target + hysteresis * 2):
                speed = min_speed + 2
                if speed > max_speed:
                    speed = max_speed
                print("Mode Auto - " + "Temp: " + str(temp_value) + " speed: " + str(speed))
                motor_handler.set_motor_speed(speed)
            # Case if current temp is above targeted temp plus two hysteresis,
            # but below target temp + three hysteresis
            elif (target + hysteresis * 2) <= temp_value < (target + hysteresis * 3):
                speed = max_speed
                print("Mode Auto - " + "Temp: " + str(temp_value) + " speed: " + str(speed))
                motor_handler.set_motor_speed(speed)
            else:
                print("Temp above target: " + str(temp_value) + " speed set to max")
                motor_handler.set_motor_speed(max_speed)
            await asyncio.sleep(sampling_time)
