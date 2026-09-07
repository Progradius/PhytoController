"""Magasin séparé des noms et annotations d'équipements."""

from __future__ import annotations

import json
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field

from utils.atomic_io import write_text_atomic
from utils.pretty_console import warning

LOGGER_NAME = "equipment"
EQUIPMENT_IDS = ("daily_1", "daily_2", "cyclic_1", "cyclic_2", "motor", "heater")
ICON_NAMES = ("light", "pump", "fan", "heater", "relay", "equipment")

DEFAULTS = {
    "daily_1": ("Éclairage 1", "éclairage", "Serre", "light"),
    "daily_2": ("Éclairage 2", "éclairage", "Serre", "light"),
    "cyclic_1": ("Sortie cyclique 1", "cycle", "Serre", "pump"),
    "cyclic_2": ("Sortie cyclique 2", "cycle", "Serre", "relay"),
    "motor": ("Ventilation", "ventilation", "Serre", "fan"),
    "heater": ("Chauffage", "chauffage", "Serre", "heater"),
}


class EquipmentMetadata(BaseModel):
    model_config = ConfigDict(extra="forbid")
    display_name: str = Field(min_length=1, max_length=64)
    usage_type: str = Field(min_length=1, max_length=32)
    zone: str = Field(default="", max_length=64)
    icon: str = Field(default="equipment", pattern="^(light|pump|fan|heater|relay|equipment)$")
    wiring_note: str = Field(default="", max_length=240)
    dashboard_visible: bool = True
    out_of_service: bool = False


def default_catalog() -> dict[str, EquipmentMetadata]:
    return {
        key: EquipmentMetadata(
            display_name=value[0], usage_type=value[1], zone=value[2], icon=value[3]
        )
        for key, value in DEFAULTS.items()
    }


class EquipmentMetadataStore:
    def __init__(self, path: Path | None = None) -> None:
        self.path = path or Path(__file__).with_name("equipment_metadata.json")
        self.current = self._load()

    def _load(self) -> dict[str, EquipmentMetadata]:
        catalog = default_catalog()
        try:
            raw = json.loads(self.path.read_text(encoding="utf-8"))
            if set(raw) - set(EQUIPMENT_IDS):
                raise ValueError("identifiant d'équipement inconnu")
            for key, value in raw.items():
                catalog[key] = EquipmentMetadata.model_validate(value)
        except FileNotFoundError:
            pass
        except Exception as exc:
            warning(f"Métadonnées illisibles ({exc.__class__.__name__}) → catalogue par défaut", name=LOGGER_NAME)
        return catalog

    def save(self, candidate: dict[str, EquipmentMetadata]) -> None:
        if set(candidate) != set(EQUIPMENT_IDS):
            raise ValueError("catalogue d'équipements incomplet")
        payload = {key: candidate[key].model_dump() for key in EQUIPMENT_IDS}
        write_text_atomic(self.path, json.dumps(payload, indent=2, ensure_ascii=False) + "\n")
        self.current = dict(candidate)

    def payload(self) -> dict[str, dict]:
        return {key: value.model_dump() for key, value in self.current.items()}
