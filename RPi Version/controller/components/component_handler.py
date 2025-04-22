# controller/components/toggle_state.py
# Author : Progradius
# Licence : AGPL‑3.0
"""
Petite fonction utilitaire qui inverse l'état GPIO d'un composant et
l'affiche joliment dans la console.
"""

from ui import pretty_console as ui


def toggle_state(component) -> None:
    """
    Inverse l'état d'un composant :

    • Si le GPIO est à 0 (OFF)  → le bascule à 1 (ON)  
    • Si le GPIO est à 1 (ON)   → le bascule à 0 (OFF)
    """
    new_state = 1 if component.get_state() == 0 else 0
    component.set_state(new_state)

    txt = "ON" if new_state else "OFF"
    ui.action(f"Toggling component → {txt}")
