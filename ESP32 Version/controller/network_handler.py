# Author: Progradius
# License: AGPL 3.0

import network
from controller.parameter_handler import read_parameters_from_json
from lib.uPing import uping

parameters = read_parameters_from_json()


def do_connect():
    """ Wifi Connection function """
    sta_if = network.WLAN(network.STA_IF)
    # If not already connected:
    if not sta_if.isconnected():
        print('connecting to network...')
        sta_if.active(True)
        sta_if.connect(parameters["Network_Settings"]["wifi_ssid"], parameters["Network_Settings"]["wifi_password"])
        # Maybe make this part of the parameters, later
        sta_if.ifconfig(('192.168.1.20', '255.255.255.0', '192.168.1.1', '192.168.1.10'))
        # While not connected, try to connect
        while not sta_if.isconnected():
            pass

    print('network config:', sta_if.ifconfig())


def is_host_connected():
    result = uping.ping(host=parameters["Network_Settings"]["host_machine_address"], count=4, timeout=5000, interval=10, quiet=True, size=64)
    print(result)
    if result[1] > 0:
        print("Host Activated")
        return "online"
    else:
        print("Host Deactivated")
        return "offline"
