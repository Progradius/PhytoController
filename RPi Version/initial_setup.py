# Author: Progradius
# License: AGPL 3.0

import os.path
import json
import re
import sys
import time
import socket

"""
Welcome to this configuration tool, it will help you setting things up,
and will help you in the future to edit your param.json before pushing it to the esp
"""
# TODO: Document new functions
# TODO: Add option to disable countdown/sleep time

# Hold the config file's name
config_file_name = "param.json"


def read_json_data():
    """
    Read JSON file and extract the data in a dictionary
    :return: A dictionary containing JSON file's values
    """
    if os.path.exists(config_file_name):
        try:
            with open(config_file_name) as json_file:
                return json.load(json_file)
        except IOError:
            print("File not accessible")


def write_data_to_json(data):
    """
    Write data from a dictionary into the JSON config file
    :param data: A dictionary with key/value pair that will form the JSON file
    :return:
    """
    if os.path.exists(config_file_name):
        try:
            with open(config_file_name, 'w') as json_file:
                json.dump(data, json_file, indent=4)
                print("===========================")
                print("|Data successfully written|")
                print("===========================")
                print("")
        except IOError:
            print("File not accessible")
            print("")


# Hold JSON info such as gpio or timer's settings
json_data = read_json_data()


def pretty_print_json_file():
    """
    Reprint the known parameters from dict
    to take advantage fo the pretty print function of json.dump
    :return:
    """
    write_data_to_json(json_data)


def select_menu_number():
    """
    Force user input into a number to make a menu's choice
    :return:
    """
    stmt = True
    while stmt:
        user_input = input("Please enter menu's number: ")
        print("")
        try:
            val = int(user_input)
            stmt = False
            return val
        except ValueError:
            print("Wrong input, Please enter a valid number")
            print("")


def clear_terminal():
    """
    Used to clear terminal between each screens
    :return:
    """
    os.system('cls' if os.name == 'nt' else 'clear')


def sleep_before_redirect(secs):
    """
    Used before redirecting the user, display a countdown then clear the terminal for the next screen
    :param secs:
    :return:
    """
    print("Redirecting in ... ", end="", flush=True)
    for i in range(secs + 1):
        val = secs - i
        time.sleep(1)
        print(str(val) + " ", end="", flush=True)
    clear_terminal()


def exit_function():
    """
    Used when a user exit the program
    :return:
    """
    clear_terminal()
    print("GoodBye !!")
    sleep_before_redirect(2)
    clear_terminal()
    sys.exit()


def valid_ip(address):
    try:
        socket.inet_aton(address)
        return True
    except:
        return False


def ascii_art():
    """
    Function holding main menu ASCII art, for easier change
    :return:
    """
    print("""
       |
     .'|'.
    /.'|\ \    PhytoController Configuration Tool
    | /|'.|                             
     \ |\/                      by Progradius
      \|/
       `
       
    """)


def gpio_writer(json_key, menu_name):
    """
    Takes user input and feed the dictionary for GPIOs parameters
    Write parameters into the JSON file
    :param json_key: Corresponding JSON GPIO's key
    :param menu_name: User displayed menu
    :return:
    """
    print("Choose GPIO Port for " + menu_name)

    for value in json_key:
        if len(json_key) > 1:
            print("Enter GPIO number for " + value)
        else:
            print("Enter GPIO Number")

        print(("Current setting: " + str(json_data["GPIO_Settings"][value])))
        print("")
        stmt = True
        while stmt:
            gpio = input("Please enter a number: ")
            try:
                val = int(gpio)
                print("Chosen GPIO is: " + str(val))
                print("")
                json_data["GPIO_Settings"][value] = val
                write_data_to_json(json_data)
                stmt = False
            except ValueError:
                print("Wrong input. Please enter a valid number")
                print("")


def dailytimer_writer(timer_id, menu_name):
    """
    Takes user input and feed the dictionary for dailytimer parameters
    Write parameters into the JSON file
    :param timer_id: Timer's number (1 or 2)
    :param menu_name: User displayed menu
    :return:
    """
    print("Schedule for " + menu_name)
    dailytimer_name = "DailyTimer" + timer_id + "_Settings"
    time_re = re.compile("^\\d{1,2}:\\d{1,2}")

    def start_and_stop_formatter(value):
        stmt = True
        while stmt:
            placeholder_hour = value + "_hour"
            placeholder_minute = value + "_minute"

            print("Choose " + str(value).title() + " Hour")
            print("Current setting: " +
                  str(json_data[dailytimer_name][placeholder_hour]) + ":" +
                  str(json_data[dailytimer_name][placeholder_minute]))
            print("")
            user_input = input("Please enter an hour in 24h format \"hh:mm\"  : ")
            schedule = time_re.match(user_input)
            if schedule is not None:
                user_hour_splited = user_input.split(":")
                hour = int(user_hour_splited[0])
                if hour > 24 or hour < 0:
                    print("Wrong hour entered, hour set to default: 12")
                    hour = 12
                minute = int(user_hour_splited[1])
                if minute > 60 or minute < 0:
                    print("Wrong minutes entered, hour set to default: 0")
                    minute = 0
                json_data[dailytimer_name][placeholder_hour] = hour
                json_data[dailytimer_name][placeholder_minute] = minute
                print("Chosen Start Hour: " + str(hour) + ":" + str(minute))
                print("")
                write_data_to_json(json_data)
                stmt = False
            else:
                print("Wrong Input, please enter a correct time")
                print("")

    start_and_stop_formatter("start")
    start_and_stop_formatter("stop")


def cyclictimer_writer(timer_id, menu_name):
    """
    Takes user input and feed the dictionary for cyclictimer parameters
    Write parameters into the JSON file
    :param timer_id: Timer's number (1 or 2)
    :param menu_name: User displayed menu
    :return:
    """
    print("Schedule for " + menu_name)
    cyclictimer_name = "Cyclic" + timer_id + "_Settings"

    print("Choose the Action Period (in minutes)")
    print("")
    print("Current setting: " + str(json_data[cyclictimer_name]["period_minutes"]) + "min")
    stmt = True
    while stmt:
        period = input("Please enter a number: ")
        try:
            val = int(period)
            if val > 9999 or val < 0:
                print("Wrong value, negative value and value above 9999 are forbidden")
                print("Setting period to default value: 30min")
                val = 30
            print("Chosen Action Period is: " + str(val))
            print("")
            json_data[cyclictimer_name]["period_minutes"] = val
            stmt = False
        except ValueError:
            print("Wrong input. Please enter a valid number")
            print("")

    print("Choose the Action duration (in seconds) by entering a number")
    print("")
    print("Current setting: " + str(json_data[cyclictimer_name]["action_duration_seconds"]) + "s")
    stmt = True
    while stmt:
        action_duration = input("Please enter a number: ")
        try:
            val = int(action_duration)
            if val > 9999 or val < 0:
                print("Wrong value, negative value and value above 9999 are forbidden")
                print("Setting period to default value: 30secs")
                val = 30
            print("Chosen Action Duration is: " + str(val))
            print("")
            json_data[cyclictimer_name]["action_duration_seconds"] = val
            stmt = False
        except ValueError:
            print("Wrong input. Please enter a valid number")
            print("")

    write_data_to_json(json_data)


def motor_writer(motor_id, menu_name):
    """
    Takes user input and feed the dictionary for motor parameters
    Write parameters into the JSON file
    :param motor_id: Motor id used to map multiple motors
    :param menu_name: User displayed menu
    :return:
    """

    def mode_auto_formatter(parameter, speed=False):
        print("Auto Mode: Insert " + str(parameter).replace("_", " ").title())
        print("")
        print("Current setting: " + str(json_data["Motor_Settings"][parameter]))
        auto_stmt = True
        while auto_stmt:
            data = input("Please enter a number: ")

            try:
                if speed is True:
                    val = int(round(float(data)))
                    if val > 4:
                        val = 4
                    if val < 0:
                        val = 0
                else:
                    val = int(round(float(data)))

                json_data["Motor_Settings"][parameter] = val
                write_data_to_json(json_data)
                print("Chosen " + str(parameter).replace("_", " ").title() + " " + str(val))
                print("")
                auto_stmt = False
            except ValueError:
                print("Wrong input. Please enter a valid number")
                print("")

    # Beginning choice
    print("Choose Settings for " + menu_name)
    print("Select Motor Mode")
    print("")
    print(("Current setting: " + str(json_data["Motor_Settings"]["motor_mode"])))
    stmt = True
    while stmt:
        manual_re = re.compile("^manual")
        auto_re = re.compile("^auto")

        mode = input("Please choose between \"auto\" and \"manual\": ")
        print("")
        if manual_re.match(mode):
            json_data["Motor_Settings"]["motor_mode"] = mode
            print("Manual Mode: Choose Fixed Speed")
            print("")
            print("Current setting: " + str(json_data["Motor_Settings"]["motor_user_speed"]))
            speed_stmt = True
            while speed_stmt:
                user_speed = input("Please enter a number between 0 and 4: ")
                try:
                    manual_val = int(round(float(user_speed)))
                    if manual_val > 4:
                        manual_val = 4
                    if manual_val < 0:
                        manual_val = 0
                    print("Chosen speed: " + str(manual_val))
                    print("")
                    json_data["Motor_Settings"]["motor_user_speed"] = manual_val
                    write_data_to_json(json_data)
                    speed_stmt = False
                except ValueError:
                    print("Wrong input. Please enter a valid number")
                    print("")
            break

        elif auto_re.match(mode):
            mode_auto_formatter(parameter="target_temp")
            mode_auto_formatter(parameter="hysteresis")
            mode_auto_formatter(parameter="min_speed", speed=True)
            mode_auto_formatter(parameter="max_speed", speed=True)
            stmt = False

        else:
            print("Wrong input. Please select between auto or manual mode")


def sensor_writer(sensor_name):
    """
    Use the sensor_name parameter, to configure the corresponding sensor
    Enabling/Disabling Sensor's and later assign GPIOs
    :param sensor_name: The corresponding and implemented sensor (not necessary used in production)
    :return:
    """
    sensor_state = sensor_name + "_state"
    print(sensor_name.upper() + " Configuration")
    print("")
    print("1 - Enable")
    print("2 - Disable")
    print("3 - Return to Sensor's Setup")
    print("")
    print("Current setting: " + json_data["Sensor_State"][sensor_state])
    choice = select_menu_number()

    if choice == 1:
        print("")
        print("Sensor " + sensor_name.upper() + " Enabled")
        json_data["Sensor_State"][sensor_state] = "enabled"
        write_data_to_json(json_data)

    if choice == 2:
        print("")
        print("Sensor " + sensor_name.upper() + " Disabled")
        json_data["Sensor_State"][sensor_state] = "disabled"
        write_data_to_json(json_data)

    if choice == 3:
        sensor_setup()


def network_writer(section_name, parameter):
    stmt = True
    while stmt:
        print(section_name + " Configuration")
        if parameter == "host":
            print("Enter Host IP address")
            print("Current setting: " + json_data["Network_Settings"]["host_machine_address"])
            print("")
            host_ip = input("Please enter a valid IP address: ")
            if valid_ip(host_ip):
                json_data["Network_Settings"]["host_machine_address"] = host_ip
                write_data_to_json(json_data)
                stmt = False
            else:
                print("Wrong input. Please enter a valid IP address e.g 192.168.1.10")
                print("")

        if parameter == "wifi":
            print("Enter Wifi Credentials")
            print("")
            print("Current setting: " + json_data["Network_Settings"]["wifi_ssid"])
            ssid = input("Please enter your WIFI's SSID: ")
            print("")
            print("Current setting: " + json_data["Network_Settings"]["wifi_password"])
            passwd = input("Please enter your Wifi's password: ")
            json_data["Network_Settings"]["wifi_ssid"] = ssid
            json_data["Network_Settings"]["wifi_password"] = passwd
            write_data_to_json(json_data)
            stmt = False

        if parameter == "influxdb":
            print("Enter InfluxDB Credentials")
            print("")
            print("Influx Database Name")
            print("")
            print("Current setting: " + json_data["Network_Settings"]["influx_db_name"])
            db_name = input("Please enter database name: ")
            print("")
            print("Influx Database Username")
            print("")
            print("Current setting: " + json_data["Network_Settings"]["influx_db_user"])
            db_user = input("Please enter database username: ")
            print("")
            print("Influx Database Password")
            print("")
            print("Current setting: " + json_data["Network_Settings"]["influx_db_password"])
            db_passwd = input("Please enter database password: ")

            json_data["Network_Settings"]["influx_db_name"] = db_name
            json_data["Network_Settings"]["influx_db_user"] = db_user
            json_data["Network_Settings"]["influx_db_password"] = db_passwd

            write_data_to_json(json_data)
            stmt = False



def gpio_setup():
    """
    The GPIO Setup Page
    :return:
    """
    while True:
        # Menu
        ascii_art()
        print("_.~\"(_.~\"(_.~\"(_.~\"(_.~\"(")
        print("        GPIO Setup  ")
        print("_.~\"(_.~\"(_.~\"(_.~\"(_.~\"(")
        print("")
        print("1 - Daily Timers Settings")
        print("2 - Cyclic Timers Settings")
        print("3 - Motor Settings")
        print("4 - I2C Bus Settings")
        print("5 - DS18B20 Settings")
        print("6 - HCSR04 Settings")
        print("7 - Main Menu")
        print("8 - Exit")
        print("")
        print("DS18B20 and HCSR04 sensors must be activated before accessing their GPIO menus")
        print("")
        # User Input
        choice = select_menu_number()

        if choice == 1:
            clear_terminal()
            gpio_writer(json_key=["light1_pin", "light2_pin"], menu_name="Daily Timers")
            # Return to GPIO setup after the write
            sleep_before_redirect(5)
            gpio_setup()

        if choice == 2:
            clear_terminal()
            gpio_writer(json_key=["cyclic1_pin", "cyclic2_pin"], menu_name="Cyclic Timers")
            # Return to GPIO setup after the write
            sleep_before_redirect(5)
            gpio_setup()

        if choice == 3:
            clear_terminal()
            gpio_writer(json_key=["motor_pin1", "motor_pin2", "motor_pin3", "motor_pin4"], menu_name="Motor Pins")
            # Return to GPIO setup after the write
            sleep_before_redirect(5)
            gpio_setup()

        if choice == 4:
            clear_terminal()
            gpio_writer(json_key=["i2c_sda", "i2c_scl"], menu_name="I2C Bus")
            # Return to GPIO setup after the write
            sleep_before_redirect(5)
            gpio_setup()

        if choice == 5:
            clear_terminal()
            if json_data["Sensor_State"]["ds18b20_state"] == "enabled":
                gpio_writer(json_key=["ds18_pin"], menu_name="DS18B20")
            else:
                print("Sensor disabled, enable it first")
            # Return to GPIO setup after the write
            sleep_before_redirect(2)
            gpio_setup()

        if choice == 6:
            clear_terminal()
            if json_data["Sensor_State"]["hcsr04_state"] == "enabled":
                gpio_writer(json_key=["hcsr_trigger_pin", "hcsr_echo_pin"], menu_name="HCSR04")
            else:
                print("Sensor disabled, enable it first")
            # Return to GPIO setup after the write
            sleep_before_redirect(5)
            gpio_setup()

        if choice == 7:
            clear_terminal()
            sleep_before_redirect(2)
            main_menu()

        if choice == 8:
            exit_function()

        if choice > 8 or choice < 0:
            clear_terminal()
            print("There is no menu n°" + str(choice) + ", you donkey ^_^ !")


def dailytimer_setup():
    """
    The DailyTimer Setup Page
    :return:
    """
    while True:
        # Menu
        ascii_art()
        print("_.~\"(_.~\"(_.~\"(_.~\"(_.~\"(_.~\"(_.~\"(")
        print("        DailyTimer Setup  ")
        print("_.~\"(_.~\"(_.~\"(_.~\"(_.~\"(_.~\"(_.~\"(")
        print("")
        print("1 - DailyTimer n°1")
        print("2 - DailyTimer n°2")
        print("3 - Main Menu")
        print("4 - Exit")
        # User Input
        choice = select_menu_number()

        if choice == 1:
            clear_terminal()
            dailytimer_writer(timer_id="1", menu_name="DailyTimer n°1")
            # Return to DailyTimer setup after the write
            sleep_before_redirect(5)
            dailytimer_setup()

        if choice == 2:
            clear_terminal()
            dailytimer_writer(timer_id="2", menu_name="DailyTimer n°2")
            # Return to DailyTimer setup after the write
            sleep_before_redirect(5)
            dailytimer_setup()
        if choice == 3:
            clear_terminal()
            sleep_before_redirect(2)
            main_menu()

        if choice == 4:
            exit_function()

        if choice > 4 or choice < 0:
            print("There is no menu n°" + str(choice) + ", you donkey ^_^ !")


def cyclictimer_setup():
    """
    The CyclicTimer Setup Page
    :return:
    """
    while True:
        # Menu
        ascii_art()
        print("_.~\"(_.~\"(_.~\"(_.~\"(_.~\"(_.~\"(_.~\"(")
        print("        CyclicTimer Setup  ")
        print("_.~\"(_.~\"(_.~\"(_.~\"(_.~\"(_.~\"(_.~\"(")
        print("")
        print("1 - CyclicTimer n°1")
        print("2 - CyclicTimer n°2")
        print("3 - Main Menu")
        print("4 - Exit")
        # User Input
        choice = select_menu_number()

        if choice == 1:
            clear_terminal()
            cyclictimer_writer(timer_id="1", menu_name="Cyclic Timer n°1")
            sleep_before_redirect(5)
            cyclictimer_setup()

        if choice == 2:
            clear_terminal()
            cyclictimer_writer(timer_id="2", menu_name="Cyclic Timer n°2")
            sleep_before_redirect(5)
            cyclictimer_setup()

        if choice == 3:
            clear_terminal()
            sleep_before_redirect(2)
            main_menu()

        if choice == 4:
            exit_function()

        if choice > 4 or choice < 0:
            clear_terminal()
            print("There is no menu n°" + str(choice) + ", you donkey ^_^ !")


def sensor_setup():
    """
    The Sensor Setup Page
    :return:
    """
    while True:
        # Menu
        ascii_art()
        print("_.~\"(_.~\"(_.~\"(_.~\"(_.~\"(")
        print("        Sensor Setup  ")
        print("_.~\"(_.~\"(_.~\"(_.~\"(_.~\"(")
        print("")
        print("1 - BME280")
        print("2 - DS18B20")
        print("3 - HCSR04")
        print("4 - MLX90614")
        print("5 - TSL2591")
        print("6 - VEML6075")
        print("7 - VL53L0X")
        print("8 - Main Menu")
        print("9 - Exit")
        print("")
        choice = select_menu_number()

        if choice == 1:
            clear_terminal()
            sensor_writer(sensor_name="bme280")
            sleep_before_redirect(5)
            sensor_setup()

        if choice == 2:
            clear_terminal()
            sensor_writer(sensor_name="ds18b20")
            sleep_before_redirect(5)
            sensor_setup()

        if choice == 3:
            clear_terminal()
            sensor_writer(sensor_name="hcsr04")
            sleep_before_redirect(5)
            sensor_setup()

        if choice == 4:
            clear_terminal()
            sensor_writer(sensor_name="mlx90614")
            sleep_before_redirect(5)
            sensor_setup()

        if choice == 5:
            clear_terminal()
            sensor_writer(sensor_name="tsl2591")
            sleep_before_redirect(5)
            sensor_setup()

        if choice == 6:
            clear_terminal()
            sensor_writer(sensor_name="veml6075")
            sleep_before_redirect(5)
            sensor_setup()

        if choice == 7:
            clear_terminal()
            sensor_writer(sensor_name="vl53l0x")
            sleep_before_redirect(5)
            sensor_setup()

        if choice == 8:
            clear_terminal()
            sleep_before_redirect(2)
            main_menu()

        if choice == 9:
            exit_function()

        if choice > 9 or choice < 0:
            clear_terminal()
            print("There is no menu n°" + str(choice) + ", you donkey ^_^ !")


def motor_setup():
    """
    The Motor Setup Page
    :return:
    """
    while True:
        # Menu
        ascii_art()
        print("_.~\"(_.~\"(_.~\"(_.~\"(_.~\"(")
        print("        Motor Setup  ")
        print("_.~\"(_.~\"(_.~\"(_.~\"(_.~\"(")
        print("")
        print("1 - Motor n°1")
        print("2 - Main Menu")
        print("3 - Exit")
        # User Input
        choice = select_menu_number()

        if choice == 1:
            clear_terminal()
            motor_writer(motor_id="1", menu_name="Motor n°1")
            sleep_before_redirect(5)
            motor_setup()

        if choice == 2:
            clear_terminal()
            sleep_before_redirect(2)
            main_menu()

        if choice == 3:
            exit_function()

        if choice > 3 or choice < 0:
            clear_terminal()
            print("There is no menu n°" + str(choice) + ", you donkey ^_^ !")


def network_setup():
    while True:
        # Menu
        ascii_art()
        print("_.~\"(_.~\"(_.~\"(_.~\"(_.~\"(_.~\"(_.~\"(")
        print("        Network Setup  ")
        print("_.~\"(_.~\"(_.~\"(_.~\"(_.~\"(_.~\"(_.~\"(")
        print("")
        print("1 - Host Machine")
        print("2 - Wifi")
        print("3 - InfluxDB ")
        print("4 - Main Menu")
        print("5 - Exit")
        # User Input
        choice = select_menu_number()

        if choice == 1:
            clear_terminal()
            network_writer(section_name="Host Machine", parameter="host")
            # Return to Network setup after the write
            sleep_before_redirect(5)
            network_setup()

        if choice == 2:
            clear_terminal()
            network_writer(section_name="Wifi", parameter="wifi")
            # Return to Network setup after the write
            sleep_before_redirect(5)
            network_setup()

        if choice == 3:
            clear_terminal()
            network_writer(section_name="InfluxDB", parameter="influxdb")
            sleep_before_redirect(5)
            network_setup()

        if choice == 4:
            clear_terminal()
            sleep_before_redirect(2)
            main_menu()

        if choice == 5:
            exit_function()

        if choice > 5 or choice < 0:
            print("There is no menu n°" + str(choice) + ", you donkey ^_^ !")


def full_setup():
    """
    The full setup page/process, for when the user has never done the first conf,
    or when the user wants to redo everything
    :return:
    """
    ascii_art()
    print("_.~\"(_.~\"(_.~\"(_.~\"(_.~\"(")
    print("        Full Setup  ")
    print("_.~\"(_.~\"(_.~\"(_.~\"(_.~\"(")
    print("")
    print("Welcome to PhytoController's Setup!")
    print("It will help you configure the various options")
    print("")
    input("Press ENTER to continue")
    print("")
    clear_terminal()

    print("Network Configuration")
    print("")
    network_writer(section_name="Host Machine", parameter="host")
    network_writer(section_name="Wifi", parameter="wifi")
    network_writer(section_name="InfluxDB", parameter="influxdb")
    print("Network configured.")

    print("DailyTimers GPIO Configuration")
    print("")
    gpio_writer(json_key=["dailytimer1_pin", "dailytimer2_pin"], menu_name="Daily Timers")
    print("DailyTimers configured.")
    sleep_before_redirect(5)

    print("CyclicTimers GPIO Configuration")
    print("")
    gpio_writer(json_key=["cyclic1_pin", "cyclic2_pin"], menu_name="Cyclic Timers")
    print("CyclicTimers configured.")
    sleep_before_redirect(5)

    print("Motor GPIO Configuration")
    print("")
    gpio_writer(json_key=["motor_pin1", "motor_pin2", "motor_pin3", "motor_pin4"], menu_name="Motor Pins")
    print("Motor configured.")
    sleep_before_redirect(5)

    print("I2C Bus GPIO Configuration")
    print("")
    gpio_writer(json_key=["i2c_sda", "i2c_scl"], menu_name="I2C Bus")
    print("I2C Bus Configured")
    sleep_before_redirect(5)

    print("DailyTimer n°1 Schedule Configuration")
    print("")
    dailytimer_writer(timer_id="1", menu_name="DailyTimer n°1")
    print("DailyTimer n°1 Configured")
    sleep_before_redirect(5)

    print("DailyTimer n°2 Schedule Configuration")
    print("")
    dailytimer_writer(timer_id="2", menu_name="DailyTimer n°2")
    print("DailyTimer n°2 Configured")
    sleep_before_redirect(5)

    print("CyclicTimer n°1 Schedule Configuration")
    print("")
    cyclictimer_writer(timer_id="1", menu_name="CyclicTimer n°1")
    print("CyclicTimer n°1 Configured")
    sleep_before_redirect(5)

    print("CyclicTimer n°2 Schedule Configuration")
    print("")
    cyclictimer_writer(timer_id="2", menu_name="CyclicTimer n°2")
    print("CyclicTimer n°2 Configured")
    sleep_before_redirect(5)

    print("Motor Temperature Control Configuration")
    print("")
    motor_writer(motor_id="1", menu_name="Motor Temperature Control")
    print("Temperature Control Configured.")
    sleep_before_redirect(5)

    clear_terminal()
    print("==============================================================")
    print("Well Done !!")
    print("Full Setup is now finished!")
    print("You can now access to the Main Menu.")
    print("More sensors can now be activated")
    print("==============================================================")
    json_data["Setup"]["first_setup_achieved"] = "True"
    sleep_before_redirect(5)
    write_data_to_json(json_data)

    main_menu()


def main_menu():
    """
    Main Menu Page
    :return:
    """
    if json_data["Setup"]["first_setup_achieved"] == "False":
        clear_terminal()
        full_setup()

    else:
        while True:
            clear_terminal()
            ascii_art()
            print("_.~\"(_.~\"(_.~\"(_.~\"(_.~\"(")
            print("        Main Menu  ")
            print("_.~\"(_.~\"(_.~\"(_.~\"(_.~\"(")
            print("")
            # Menu
            print("1 - GPIO Settings")
            print("2 - Daily Timers Settings")
            print("3 - Cyclic Timers Settings")
            print("4 - Motor Settings")
            print("5 - Network Settings")
            print("6 - Add or Remove Sensor")
            print("7 - Full Setup")
            print("8 - Pretty Print JSON File")
            print("9 - Exit")
            print("")

            choice = select_menu_number()

            if choice == 1:
                clear_terminal()
                gpio_setup()

            elif choice == 2:
                clear_terminal()
                dailytimer_setup()

            elif choice == 3:
                clear_terminal()
                cyclictimer_setup()

            elif choice == 4:
                clear_terminal()
                motor_setup()

            elif choice == 5:
                clear_terminal()
                network_setup()

            elif choice == 6:
                clear_terminal()
                sensor_setup()

            elif choice == 7:
                clear_terminal()
                full_setup()

            elif choice == 8:
                print("Pretty printing current config file...")
                pretty_print_json_file()
                sleep_before_redirect(5)

            elif choice == 9:
                exit_function()

            elif choice > 9 or choice < 0:
                clear_terminal()
                print("There is no menu n°" + str(choice) + ", you donkey! ^_^")

            else:
                clear_terminal()
                "Wrong choice, terminating the program."
                sys.exit()


# Starting the program loop
main_menu()
