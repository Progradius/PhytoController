# controller/components/cyclic_timer_handler.py
# Author : Progradius
# Licence : AGPL‑3.0
"""
Gestion asynchrone d'un timer cyclique :
  - Attend la « période » (en minutes)
  - Active le composant pendant « action_duration » (en secondes)
  - Boucle indéfiniment
"""

import asyncio
from datetime import datetime

from function import convert_minute_to_seconds
from ui import pretty_console as ui


async def timer_cylic(cyclic_timer):
    """
    Timer cyclique (coroutine) - `cyclic_timer` est une instance de `CyclicTimer`
    contenant :
        • .timer_id          - identifiant lisible
        • .component         - instance de Component
        • .get_period()      - période   (minutes)
        • .get_action_duration() - durée (secondes)
    """
    tid = cyclic_timer.timer_id
    comp = cyclic_timer.component

    # Boucle infinie
    while True:
        # ── Attente de la prochaine période ───────────────────
        await asyncio.sleep(convert_minute_to_seconds(cyclic_timer.get_period()))

        now = datetime.now().strftime("%H:%M:%S")
        ui.box(f"CyclicTimer #{tid}   ↦  ACTIVATION   {now}", color="cyan")
        comp.set_state(0)            # ON (ou LOW selon ton câblage)

        # ── Maintien à l'état ON pendant la durée demandée ────
        await asyncio.sleep(cyclic_timer.get_action_duration())

        now = datetime.now().strftime("%H:%M:%S")
        ui.box(f"CyclicTimer #{tid}   ↦  DESACTIVATION   {now}", color="yellow")
        comp.set_state(1)            # OFF (ou HIGH)
