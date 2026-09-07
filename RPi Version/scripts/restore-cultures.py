"""Restaure le carnet dans un NOUVEAU fichier pour contrôle avant toute bascule."""

from pathlib import Path
import argparse
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from utils.culture_backup import restore_copy
from utils.pretty_console import error, success


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path, help="Sauvegarde SQLite téléchargée")
    parser.add_argument("destination", type=Path, help="Nouvelle copie isolée, non existante")
    args = parser.parse_args()
    try:
        restore_copy(args.source, args.destination)
    except Exception as exc:
        error(f"Restauration du carnet refusée ({type(exc).__name__}). Vérifier les chemins, l'intégrité et la version.", name="cultures")
        return 1
    success("Copie du carnet restaurée et vérifiée. Aucun remplacement du carnet actif.", name="cultures")
    return 0


if __name__ == "__main__":
    sys.exit(main())
