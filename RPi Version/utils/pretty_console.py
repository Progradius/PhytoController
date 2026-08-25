# utils/pretty_console.py
# Author : Progradius
# License : AGPL‑3.0
"""
Façade unique de journalisation (console + fichier).

‣ Un seul point d'entrée : les fonctions `debug/info/success/action/clock/warning/error/critical`
‣ Un seul filtre de niveau : il s'applique à la console **et** au fichier
‣ Niveau, par ordre de priorité : env `PHYTO_LOG_LEVEL` > `param.json` (Log_Settings) > INFO
‣ Fichier : une ligne par message, rotation quotidienne + archives gzip
  (`%(asctime)s [%(levelname)s] [%(name)s] %(message)s`)
‣ Console : couleurs ANSI (ou Rich si disponible), pictogrammes, horodatage court
  Les pictogrammes restent l'affaire de la console : le fichier n'en contient jamais.
"""

import json
import logging
import os
import shutil
import sys
from datetime import datetime
from logging.handlers import TimedRotatingFileHandler

# ───────────────────────────────────────────────────────────────
#  Paramètres globaux
# ───────────────────────────────────────────────────────────────
LOG_DIR = os.path.join(os.path.dirname(__file__), "..", "logs")
os.makedirs(LOG_DIR, exist_ok=True)
LOG_FILE = os.path.join(LOG_DIR, "phyto.log")

PARAM_FILE = os.path.join(os.path.dirname(__file__), "..", "param", "param.json")

ROOT_LOGGER_NAME = "phyto"
DEFAULT_LEVEL = logging.INFO
DEFAULT_RETENTION_DAYS = 14

_LEVEL_NAMES = {
    "DEBUG": logging.DEBUG,
    "INFO": logging.INFO,
    "WARNING": logging.WARNING,
    "ERROR": logging.ERROR,
    "CRITICAL": logging.CRITICAL,
}

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
#  Lecture du niveau souhaité (env > param.json > défaut)
# ───────────────────────────────────────────────────────────────
def _parse_level(value, fallback: int) -> int:
    """Convertit « DEBUG »/« 10 » en niveau logging, `fallback` si invalide."""
    if value is None:
        return fallback
    if isinstance(value, int):
        return value
    txt = str(value).strip().upper()
    if txt in _LEVEL_NAMES:
        return _LEVEL_NAMES[txt]
    if txt.isdigit():
        return int(txt)
    return fallback


def _env_level() -> int | None:
    """Niveau imposé par `PHYTO_LOG_LEVEL` (prioritaire), sinon None."""
    raw = os.getenv("PHYTO_LOG_LEVEL")
    if not raw:
        return None
    return _parse_level(raw, DEFAULT_LEVEL)


def _settings_from_param_file() -> tuple[int, int]:
    """
    Lit `Log_Settings` dans param.json sans passer par Pydantic
    (évite un import circulaire avec `param.config`).
    """
    try:
        with open(PARAM_FILE, encoding="utf-8") as f:
            block = json.load(f).get("Log_Settings", {}) or {}
    except Exception:
        block = {}

    level = _parse_level(block.get("level"), DEFAULT_LEVEL)
    try:
        retention = int(block.get("retention_days", DEFAULT_RETENTION_DAYS))
    except (TypeError, ValueError):
        retention = DEFAULT_RETENTION_DAYS
    return level, max(1, retention)


# ───────────────────────────────────────────────────────────────
#  Logger principal + handler fichier (rotation quotidienne, gzip)
# ───────────────────────────────────────────────────────────────
def _gzip_rotator(source: str, dest: str) -> None:
    """Compresse l'archive de rotation puis supprime l'original."""
    import gzip
    try:
        with open(source, "rb") as fin, gzip.open(f"{dest}.gz", "wb") as fout:
            shutil.copyfileobj(fin, fout)
        os.remove(source)
    except Exception:
        # En dernier recours on garde l'archive non compressée
        try:
            os.replace(source, dest)
        except OSError:
            pass


_file_level, _retention_days = _settings_from_param_file()
_LOG_LEVEL = _env_level() or _file_level

logger = logging.getLogger(ROOT_LOGGER_NAME)
logger.setLevel(_LOG_LEVEL)
logger.propagate = False

file_handler = TimedRotatingFileHandler(
    LOG_FILE, when="midnight", backupCount=_retention_days, encoding="utf-8"
)
file_handler.setFormatter(logging.Formatter(
    "%(asctime)s [%(levelname)s] [%(name)s] %(message)s", "%Y-%m-%d %H:%M:%S"
))
file_handler.rotator = _gzip_rotator
logger.addHandler(file_handler)


def apply_log_settings(level=None, retention_days: int | None = None) -> None:
    """
    Applique un niveau / une rétention (boot, ou POST /conf à chaud).
    `PHYTO_LOG_LEVEL` reste prioritaire sur la config.
    """
    global _LOG_LEVEL, _retention_days

    forced = _env_level()
    wanted = forced if forced is not None else _parse_level(level, _LOG_LEVEL)
    if wanted != _LOG_LEVEL:
        _LOG_LEVEL = wanted
        logger.setLevel(_LOG_LEVEL)
        logger.info("Niveau de log : %s", logging.getLevelName(_LOG_LEVEL))

    if retention_days:
        retention = max(1, int(retention_days))
        if retention != _retention_days:
            _retention_days = retention
            file_handler.backupCount = retention


def set_log_level(level) -> None:
    """Change dynamiquement le niveau (console + fichier)."""
    apply_log_settings(level=level)


# Compat historique
set_console_log_level = set_log_level


def get_log_level() -> int:
    return _LOG_LEVEL


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
#  Icônes Unicode (console uniquement)
# ───────────────────────────────────────────────────────────────
ICONS = {
    "debug"   : "·",
    "info"    : "ℹ️ ",
    "success" : "✅",
    "warning" : "⚠️ ",
    "error"   : "❌",
    "critical": "🔥",
    "action"  : "🔧",
    "clock"   : "⏰",
}


# ───────────────────────────────────────────────────────────────
#  Émission
# ───────────────────────────────────────────────────────────────
def _stamp() -> str:
    """Horodatage court HH:MM:SS."""
    return _c(datetime.now().strftime("%H:%M:%S"), "grey", dim=True)


def _logger_for(name: str | None) -> logging.Logger:
    """`name=\"motor\"` → logger « phyto.motor » ; None → « phyto »."""
    if not name:
        return logger
    if name == ROOT_LOGGER_NAME or name.startswith(ROOT_LOGGER_NAME + "."):
        return logging.getLogger(name)
    return logging.getLogger(f"{ROOT_LOGGER_NAME}.{name}")


def _print(icon_key: str, msg, color: str, *, level=logging.INFO,
           name: str | None = None, exc_info=False, **kwargs):
    log = _logger_for(name)
    if not log.isEnabledFor(level):
        return

    msg = str(msg)
    icon = ICONS.get(icon_key, "")
    if USE_RICH:
        rich_console.print(
            f"[dim]{datetime.now():%H:%M:%S}[/] [bold {color}]{icon} {msg}[/]",
            highlight=False,
        )
    else:
        print(f"{_stamp()} {_c(icon, color)} {_c(msg, color, **kwargs)}")

    log.log(level, msg, exc_info=exc_info)


# ─── Interfaces externes ───────────────────────────────────────
def debug(msg, *, name=None):
    _print("debug", msg, "grey", level=logging.DEBUG, name=name, dim=True)


def info(msg, *, name=None):
    _print("info", msg, "blue", level=logging.INFO, name=name)


def success(msg, *, name=None):
    _print("success", msg, "green", level=logging.INFO, name=name)


def warning(msg, *, name=None):
    _print("warning", msg, "yellow", level=logging.WARNING, name=name, bold=True)


def error(msg, *, name=None, exc_info=False):
    _print("error", msg, "red", level=logging.ERROR, name=name, exc_info=exc_info, bold=True)


def critical(msg, *, name=None, exc_info=False):
    _print("critical", msg, "magenta", level=logging.CRITICAL, name=name,
           exc_info=exc_info, bold=True)


def exception(msg, *, name=None):
    """Erreur + traceback complète dans le fichier."""
    error(msg, name=name, exc_info=True)


def action(msg, *, name=None):
    """Bruit de fonctionnement : DEBUG."""
    _print("action", msg, "cyan", level=logging.DEBUG, name=name)


def clock(msg, *, name=None):
    """Bruit de cadencement : DEBUG."""
    _print("clock", msg, "magenta", level=logging.DEBUG, name=name)


# ───────────────────────────────────────────────────────────────
#  Titres & cadres — console décorée, fichier sur une seule ligne
# ───────────────────────────────────────────────────────────────
def title(text, *, char="═", name=None, level=logging.INFO):
    log = _logger_for(name)
    if not log.isEnabledFor(level):
        return

    width = shutil.get_terminal_size((80, 20)).columns
    bar   = char * width
    deco  = f" {text} "
    if USE_RICH:
        rich_console.rule(deco, style="bold magenta")
    else:
        print(_c(bar, "magenta", bold=True))
        print(_c(deco.center(width, char), "magenta", bold=True))
        print(_c(bar, "magenta", bold=True))

    log.log(level, str(text).strip())


def box(text: str, *, color="white", name=None, level=logging.INFO):
    log = _logger_for(name)
    if not log.isEnabledFor(level):
        return

    lines = str(text).splitlines() or [""]
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

    # Fichier : une seule ligne (le multi-ligne casse le parsing)
    log.log(level, " | ".join(l.strip() for l in lines if l.strip()))
