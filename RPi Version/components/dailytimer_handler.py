# controller/components/dailytimer_handler.py
# Author  : Progradius
# Licence : AGPL-3.0
"""
Routine asynchrone : contrôle périodique d'un DailyTimer
avec rechargement dynamique des horaires depuis AppConfig.
"""

import asyncio
from datetime import datetime, timedelta

from ui import pretty_console as ui
from param.config import AppConfig

async def timer_daily(
    dailytimer,
    config: AppConfig | None = None,
    sampling_time: int = 60
):
    """
    Vérifie toutes les *sampling_time* secondes si le composant du
    DailyTimer doit être (dé)activé en fonction de l'heure courante.

    • dailytimer : instance de `DailyTimer`
      (doit exposer .timer_id, .toggle_state_daily(), .component.get_state(), .refresh_from_config())

    • config : AppConfig optionnel, pour recharger les horaires
      depuis la configuration avant chaque vérification.

    • sampling_time : période de vérification, en secondes
    """
    tid = str(dailytimer.timer_id)

    while True:
        # 1) Date/heure actuelle
        now_dt = datetime.now()
        ui.clock(f"DailyTimer #{tid}  –  check @ {now_dt:%H:%M:%S}")

        # 2) Rechargement à chaud de la conf si supporté
        if hasattr(dailytimer, "refresh_from_config"):
            try:
                dailytimer.refresh_from_config()
            except Exception as e:
                ui.warning(f"Échec refresh_from_config #{tid} → {e}")

        # 3) Décision ON/OFF
        changed = dailytimer.toggle_state_daily()
        if changed:
            state_on = bool(dailytimer.component.get_state())
            txt = "ON" if state_on else "OFF"
            col = "green" if state_on else "grey"
            ui.action(f"DailyTimer #{tid} switched {txt}")
        else:
            ui.info("Aucun changement demandé par le planning.")

        # 4) Prochaine vérif (affichage format HH:MM:SS)
        next_dt = now_dt + timedelta(seconds=sampling_time)
        next_check = next_dt.strftime("%H:%M:%S")
        ui.dim = True
        ui.info(f"Prochaine vérif : {next_check}")
        ui.dim = False

        await asyncio.sleep(sampling_time)
