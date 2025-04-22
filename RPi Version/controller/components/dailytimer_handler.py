# controller/components/dailytimer_handler.py
# Author  : Progradius (adapted)
# Licence : AGPL‑3.0
"""
Routine asynchrone : contrôle périodique d'un DailyTimer
"""

import asyncio
from datetime import datetime, timedelta

from controller.ui import pretty_console as ui


async def timer_daily(dailytimer, sampling_time: int = 60):
    """
    Vérifie toutes les *sampling_time* secondes si le composant du
    DailyTimer doit être (dé)activé en fonction de l'heure courante.

    • dailytimer : instance de `DailyTimer`
      (doit exposer .timer_id, .toggle_state_daily(), .component.get_state())

    • sampling_time : période de vérification, en secondes
    """
    tid = dailytimer.timer_id

    while True:
        now = datetime.now()

        # ── affichage avant vérification ─────────────────────
        ui.clock(f"DailyTimer #{tid}  –  check @ {now:%H:%M:%S}")

        # La méthode utilisateur gère seule la décision / action
        changed = dailytimer.toggle_state_daily()  # bool éventuel ou None

        # ── Affichage résultat — si état modifié on le signale ─
        if changed:
            state_on = dailytimer.component.get_state() == 0  # adapté à ton log.
            txt  = "ON" if state_on else "OFF"
            col  = "green" if state_on else "grey"
            ui.box(f"Component switched {txt}", color=col)
        else:
            ui.info("Aucun changement demandé par le planning.")

        # ── Prochaine vérification ────────────────────────────
        next_check = (now + timedelta(seconds=sampling_time)).strftime("%H:%M:%S")
        ui.dim = True  # petite astuce : attribut dynamique (cf. pretty_console)
        ui.info(f"Prochaine vérif : {next_check}")
        ui.dim = False

        await asyncio.sleep(sampling_time)
