# controller/ui/pretty_console.py
# Author : Progradius
# License : AGPL‑3.0
"""
Gestion unifiée de l'affichage console + log persistants.

‣ Couleurs ANSI (fallback sans couleur si le flux n'est pas un TTY)
‣ Pictogrammes (Unicode) pour chaque niveau de message
‣ Log file persistants via logging (avec rotation)
‣ Optionnel : support de Rich pour un rendu amélioré
‣ Filtrage dynamique du niveau de log console (LOG_LEVEL_CONSOLE)
"""

import sys
import shutil
from datetime import datetime
import logging
from logging.handlers import RotatingFileHandler
import os

# ───────────────────────────────────────────────────────────────
#  Paramètres globaux
# ───────────────────────────────────────────────────────────────
LOG_DIR = os.path.join(os.path.dirname(__file__), "..", "logs")
os.makedirs(LOG_DIR, exist_ok=True)
LOG_FILE = os.path.join(LOG_DIR, "phyto.log")

# Niveau de log visible en console (modifiable dynamiquement)
LOG_LEVEL_CONSOLE = logging.INFO  # DEBUG=10, INFO=20, WARNING=30, ERROR=40

# Activation Rich si présent
USE_RICH = False
try:
    from rich.console import Console as RichConsole
    from rich.traceback import install as rich_traceback
    rich_console = RichConsole()
    rich_traceback()
    USE_RICH = True
except ImportError:
    pass

# ───────────────────────────────────────────────────────────────
#  Logger principal
# ───────────────────────────────────────────────────────────────
logger = logging.getLogger("phyto")
logger.setLevel(logging.DEBUG)

file_handler = RotatingFileHandler(LOG_FILE, maxBytes=1_000_000, backupCount=5)
file_handler.setFormatter(logging.Formatter(
    "%(asctime)s [%(levelname)s] %(message)s", "%Y-%m-%d %H:%M:%S"
))
logger.addHandler(file_handler)

# ───────────────────────────────────────────────────────────────
#  Palette ANSI (console standard)
# ───────────────────────────────────────────────────────────────
class _Ansi:
    RESET = '\033[0m'
    BOLD  = '\033[1m'
    DIM   = '\033[2m'
    FG = {
        "grey"    : '\033[90m',
        "red"     : '\033[91m',
        "green"   : '\033[92m',
        "yellow"  : '\033[93m',
        "blue"    : '\033[94m',
        "magenta" : '\033[95m',
        "cyan"    : '\033[96m',
        "white"   : '\033[97m',
    }

USE_COLOR = sys.stdout.isatty() and not USE_RICH

def _c(text, color=None, *, bold=False, dim=False):
    """Applique couleur et attributs ANSI si autorisé (hors rich)."""
    if not USE_COLOR or color not in _Ansi.FG:
        return text
    style = ""
    if bold: style += _Ansi.BOLD
    if dim : style += _Ansi.DIM
    style += _Ansi.FG[color]
    return f"{style}{text}{_Ansi.RESET}"

# ───────────────────────────────────────────────────────────────
#  Icônes Unicode
# ───────────────────────────────────────────────────────────────
ICONS = {
    "info"    : "ℹ️ ",
    "success" : "✅",
    "warning" : "⚠️ ",
    "error"   : "❌",
    "action"  : "🔧",
    "clock"   : "⏰",
}

# ───────────────────────────────────────────────────────────────
#  Afficheurs console + fichier
# ───────────────────────────────────────────────────────────────
def _stamp() -> str:
    """Horodatage court HH:MM:SS."""
    return _c(datetime.now().strftime("%H:%M:%S"), "grey", dim=True)

def _should_display(level: int) -> bool:
    """Détermine si le message doit être affiché en console."""
    return level >= LOG_LEVEL_CONSOLE

def _log_to_file(level, msg: str):
    if level == logging.INFO:
        logger.info(msg)
    elif level == logging.WARNING:
        logger.warning(msg)
    elif level == logging.ERROR:
        logger.error(msg)
    elif level == logging.DEBUG:
        logger.debug(msg)

def _print(level_name: str, msg: str, color: str, *, level=logging.INFO, **kwargs):
    icon = ICONS.get(level_name, "")
    if _should_display(level):
        if USE_RICH:
            rich_console.print(f"[bold {color}]{icon} {msg}[/]", highlight=False)
        else:
            print(f"{_stamp()} {_c(icon, color)} {_c(msg, color, **kwargs)}")
    _log_to_file(level, msg)

# ─── Interfaces externes ───────────────────────────────────────
def set_console_log_level(level: int):
    """Change dynamiquement le niveau de log affiché en console."""
    global LOG_LEVEL_CONSOLE
    LOG_LEVEL_CONSOLE = level
    logger.info(f"[Logger] Niveau console changé : {logging.getLevelName(level)}")

def info(msg):     _print("info",    msg, "blue",    level=logging.INFO)
def success(msg):  _print("success", msg, "green",   level=logging.INFO)
def warning(msg):  _print("warning", msg, "yellow",  level=logging.WARNING, bold=True)
def error(msg):    _print("error",   msg, "red",     level=logging.ERROR,   bold=True)
def action(msg):   _print("action",  msg, "cyan",    level=logging.INFO)
def clock(msg):    _print("clock",   msg, "magenta", level=logging.INFO)

# ───────────────────────────────────────────────────────────────
#  Titres & cadres
# ───────────────────────────────────────────────────────────────
def title(text, *, char="═"):
    width = shutil.get_terminal_size((80, 20)).columns
    bar   = char * width
    text  = f" {text} "
    mid   = text.center(width, char)
    if USE_RICH:
        rich_console.rule(text, style="bold magenta")
    else:
        print(_c(bar, "magenta", bold=True))
        print(_c(mid, "magenta", bold=True))
        print(_c(bar, "magenta", bold=True))
    logger.info(f"[TITLE] {text.strip()}")

def box(text: str, *, color="white"):
    lines = text.splitlines() or [""]
    maxi  = max(len(l) for l in lines)
    top   = f"╔{'═'*(maxi+2)}╗"
    bot   = f"╚{'═'*(maxi+2)}╝"
    if USE_RICH:
        rich_console.print(top, style=color)
        for line in lines:
            rich_console.print(f"║ {line.ljust(maxi)} ║", style=color)
        rich_console.print(bot, style=color)
    else:
        print(_c(top, color))
        for line in lines:
            print(_c(f"║ {line.ljust(maxi)} ║", color))
        print(_c(bot, color))
    logger.info(f"[BOX]\n{text}")