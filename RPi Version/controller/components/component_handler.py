# Author: Progradius
# License: AGPL 3.0

def toggle_state(component):
    """
    Inverse l'état d'un composant :
    - Si le GPIO est à 0 (OFF), le met à 1 (ON)
    - Si le GPIO est à 1 (ON), le met à 0 (OFF)
    """
    if component.get_state() == 0:
        component.set_state(1)
        print("Toggling state: ON")
    else:
        component.set_state(0)
        print("Toggling state: OFF")
