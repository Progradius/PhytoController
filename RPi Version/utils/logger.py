import logging
from logging.handlers import RotatingFileHandler
import os
from datetime import datetime

# Répertoire et fichier de log
LOG_DIR = os.path.join(os.path.dirname(__file__), "..", "logs")
os.makedirs(LOG_DIR, exist_ok=True)
LOG_FILE = os.path.join(LOG_DIR, "phyto.log")

# Configuration du logger
logger = logging.getLogger("phyto")
logger.setLevel(logging.DEBUG)  # log tout, même DEBUG

# Handler fichier avec rotation (max 1 Mo, 5 fichiers)
file_handler = RotatingFileHandler(LOG_FILE, maxBytes=1_000_000, backupCount=5)
file_handler.setLevel(logging.DEBUG)
formatter = logging.Formatter(
    "%(asctime)s [%(levelname)s] %(message)s", "%Y-%m-%d %H:%M:%S"
)
file_handler.setFormatter(formatter)
logger.addHandler(file_handler)

# Handler console custom pour conserver les couleurs actuelles
class PrettyConsoleHandler(logging.StreamHandler):
    COLORS = {
        "DEBUG": "\033[90m",  # gris
        "INFO": "\033[92m",   # vert
        "WARNING": "\033[93m",# jaune
        "ERROR": "\033[91m",  # rouge
        "CRITICAL": "\033[95m",# magenta
        "RESET": "\033[0m",
    }

    def emit(self, record):
        color = self.COLORS.get(record.levelname, "")
        reset = self.COLORS["RESET"]
        msg = self.format(record)
        self.stream.write(f"{color}{msg}{reset}\n")
        self.flush()

console_handler = PrettyConsoleHandler()
console_handler.setLevel(logging.INFO)
console_handler.setFormatter(formatter)
logger.addHandler(console_handler)
