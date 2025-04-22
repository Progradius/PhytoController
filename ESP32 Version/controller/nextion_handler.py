# Author: Progradius
# License: AGPL 3.0

import machine
import time

uart = machine.UART(1, tx=27, rx=26, baudrate=9600)

eof = b'\xFF\xFF\xFF'


def send(cmd):
    uart.write(cmd)
    uart.write(eof)
    time.sleep_ms(100)
    print("Response:", uart.read())

