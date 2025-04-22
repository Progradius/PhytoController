# controller/ui/pretty_console.py
# Author : Progradius
# License : AGPL‑3.0
"""
Gestion unifiée de l'affichage console.

‣ Couleurs ANSI (fallback sans couleur si le flux n'est pas un TTY)
‣ Pictogrammes (Unicode) pour chaque niveau de message
‣ Cadres ASCII/UTF‑8 pour titrer ou isoler des blocs
"""

import sys
import shutil
from datetime import datetime

# ───────────────────────────────────────────────────────────────
#  Palette ANSI  (codes courts)
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

# Couleurs désactivées si stdout n'est pas un terminal
USE_COLOR = sys.stdout.isatty()

def _c(text, color=None, *, bold=False, dim=False):
    """Applique couleur et attributs si autorisé."""
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
#  Afficheurs de base
# ───────────────────────────────────────────────────────────────
def _stamp() -> str:
    """Horodatage court HH:MM:SS."""
    return _c(datetime.now().strftime("%H:%M:%S"), "grey", dim=True)

def info(msg):     _print("info",    msg, "blue")
def success(msg):  _print("success", msg, "green")
def warning(msg):  _print("warning", msg, "yellow", bold=True)
def error(msg):    _print("error",   msg, "red",    bold=True)

def action(msg):   _print("action",  msg, "cyan")
def clock(msg):    _print("clock",   msg, "magenta")

def _print(level, msg, color, **kwargs):
    icon = ICONS.get(level, "")
    print(f"{_stamp()} {_c(icon, color)} {_c(msg, color, **kwargs)}")

# ───────────────────────────────────────────────────────────────
#  Titres & blocs encadrés
# ───────────────────────────────────────────────────────────────
def title(text, *, char="═"):
    """Titre encadré (sur toute la largeur du terminal)."""
    width = shutil.get_terminal_size((80, 20)).columns
    bar   = char * width
    text  = f" {text} "
    mid   = text.center(width, char)
    print(_c(bar, "magenta", bold=True))
    print(_c(mid, "magenta", bold=True))
    print(_c(bar, "magenta", bold=True))

def box(text: str, *, color="white"):
    """Encadre un (ou plusieurs) paragraphes avec un double cadre."""
    lines = text.splitlines() or [""]
    maxi  = max(len(l) for l in lines)
    top   = f"╔{'═'*(maxi+2)}╗"
    bot   = f"╚{'═'*(maxi+2)}╝"
    print(_c(top, color))
    for line in lines:
        print(_c(f"║ {line.ljust(maxi)} ║", color))
    print(_c(bot, color))

# ───────────────────────────────────────────────────────────────
#  Exemple d'utilisation (à retirer en production)
# ───────────────────────────────────────────────────────────────
if __name__ == "__main__":
    title("Pretty Console Demo")
    info("System started")
    success("Parameters successfully written to file")
    warning("Component already OFF")
    error("Sensor read failed")
    box("Next on‑period in 140 minutes\nChecked at 15:40:45", color="cyan")
