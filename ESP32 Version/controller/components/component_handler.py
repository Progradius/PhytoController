# Author: Progradius
# License: AGPL 3.0

def toggle_state(component):
    """ Toggle component state """
    if component.get_state() == 0:
        component.set_state(1)
        print("Toggling state: " + str(component.get_state()))
    else:
        component.set_state(0)
        print("Toggling state: " + str(component.get_state()))
