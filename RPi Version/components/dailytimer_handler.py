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
from param.config import AppConfig  # pour typer le paramètre config

async def timer_daily(
    dailytimer,
    config: AppConfig | None = None,
    sampling_time: int = 60
):
    """
    Vérifie toutes les *sampling_time* secondes si le composant du
    DailyTimer doit être (dé)activé en fonction de l'heure courante.

    • dailytimer : instance de `DailyTimer`
      (doit exposer .timer_id, .toggle_state_daily(), .component.get_state())

    • config : AppConfig optionnel, pour recharger les horaires
      depuis la configuration avant chaque vérification.

    • sampling_time : période de vérification, en secondes
    """
    tid = str(dailytimer.timer_id)

    while True:
        now = datetime.now()
        now_str = now.strftime("%H:%M:%S")
        ui.box(f"[D] #{tid} CHECK @ {now_str}", color="green")

        # Si on a reçu la config, on met à jour dynamiquement les horaires
        if config is not None:
            if tid == "1":
                block = config.daily_timer1
            elif tid == "2":
                block = config.daily_timer2
            else:
                ui.warning(f"timer_daily: ID inattendu {tid}")
                block = None

            if block is not None:
                dailytimer.start_hour   = block.start_hour
                dailytimer.start_minute = block.start_minute
                dailytimer.stop_hour    = block.stop_hour
                dailytimer.stop_minute  = block.stop_minute

        # La méthode interne décide si on doit activer/désactiver
        changed = dailytimer.toggle_state_daily()

        # Affichage résultat
        if changed:
            gpio_state = dailytimer.component.get_state()
            state_on = gpio_state == 0  # ON = GPIO LOW
            action = "ON" if state_on else "OFF"
            color  = "green" if state_on else "yellow"
            now = datetime.now().strftime("%H:%M:%S")
            ui.box(f"[D] #{tid} {action} @ {now}", color=color)
        else:
            ui.dim = True
            ui.info("Aucun changement demandé par le planning.")
            ui.dim = False

        # Prochaine vérif (info allégée, pas dans le style [D])
        next_check = (now + timedelta(seconds=sampling_time)).strftime("%H:%M:%S")
        ui.dim = True
        ui.info(f"Prochaine vérif : {next_check}")
        ui.dim = False

        await asyncio.sleep(sampling_time)
