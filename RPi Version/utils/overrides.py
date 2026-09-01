# utils/overrides.py
# Author : Progradius
# License: AGPL-3.0
# -------------------------------------------------------------
#  Forçages « arrêt » temporaires (jalon 4)
# -------------------------------------------------------------
"""
Un forçage est une **entrée de politique**, jamais un accès GPIO.

Ce magasin ne touche aucune broche : il conserve une intention opérateur bornée
dans le temps, que les boucles métier lisent en tête d'itération et que la
politique thermique pure reçoit sous forme d'échéances. Rien ici ne peut
allumer quoi que ce soit — un forçage ne sait que **couper**.

Deux horloges, échéance au premier des deux :

* `expires_epoch` (`time.time()`) est la seule échéance affichable et la seule
  qui survive à un redémarrage ;
* `deadline_mono` (`time.monotonic()`) est calculée à la création et n'est
  jamais persistée : elle rend un saut NTP incapable de **prolonger** un
  forçage, tandis qu'un saut avant le raccourcit par `expires_epoch`.

Les plafonds sont volontairement asymétriques : le chauffage et le moteur sont
plafonnés à 4 h. Ce sont des outils d'intervention physique, pas des réglages
saisonniers — et depuis l'arbitrage du 28/08/2026 le forçage moteur est
*absolu* (il prime sur `SECURITE_HAUTE`), donc la seule protection restante
contre une surchauffe est la brièveté de la coupure.

La raison saisie par l'opérateur n'est **jamais interpolée dans un journal** :
elle partirait dans le flux SSE de `/console` et dans son téléchargement.
"""

from __future__ import annotations

from dataclasses import dataclass
from time import monotonic, time

from param.equipment_metadata import EQUIPMENT_IDS
from utils.pretty_console import info, warning
from utils.state_store import StateStore, shared_store
from utils.time_reliability import time_reliability

LOGGER_NAME = "override"
SECTION = "overrides"

DEFAULT_MAX_SECONDS = 24 * 3600
MAX_SECONDS = {"heater": 4 * 3600, "motor": 4 * 3600}
DEFAULT_SECONDS = 3600
MAX_REASON_LENGTH = 200


class OverrideError(ValueError):
    """Refus de création ou d'annulation, présentable à l'opérateur."""


class UnknownTarget(OverrideError):
    pass


class InvalidDuration(OverrideError):
    pass


class TimeUnreliable(OverrideError):
    pass


def max_seconds(target: str) -> int:
    """Plafond de durée propre à la cible."""
    return MAX_SECONDS.get(target, DEFAULT_MAX_SECONDS)


def sanitize_reason(raw) -> str:
    """Raison bornée et sans caractère de contrôle (elle finit dans du HTML)."""
    text = "".join(ch for ch in str(raw or "") if ch.isprintable())
    return text.strip()[:MAX_REASON_LENGTH]


@dataclass(frozen=True)
class ForcedOff:
    """Un forçage « arrêt » sur une cible, borné par deux horloges."""

    target: str
    reason: str
    created_epoch: float
    expires_epoch: float
    deadline_mono: float
    confirmed: bool = True      # False : repris au démarrage avant heure fiable

    def active_at(self, now_epoch: float, now_mono: float) -> bool:
        """Échu au **premier** des deux horloges."""
        return now_epoch < self.expires_epoch and now_mono < self.deadline_mono

    def remaining_seconds(self, now_epoch: float, now_mono: float) -> float:
        return max(0.0, min(self.expires_epoch - now_epoch,
                            self.deadline_mono - now_mono))

    def to_payload(self) -> dict:
        """Forme persistée : `deadline_mono` n'a aucun sens après un reboot."""
        return {
            "reason": self.reason,
            "created_epoch": self.created_epoch,
            "expires_epoch": self.expires_epoch,
            "confirmed": self.confirmed,
        }


class OverrideStore:
    """
    État en mémoire, persisté dans la section `overrides` de
    `param/runtime_state.json`. **Aucune lecture disque dans une boucle de
    contrôle** : les boucles interrogent le dictionnaire en mémoire.
    """

    def __init__(self, store: StateStore | None = None) -> None:
        self._store = store if store is not None else shared_store()
        self._records: dict[str, ForcedOff] = {}

    # ── démarrage ─────────────────────────────────────────────
    def restore(self, *, now_epoch: float | None = None,
                now_mono: float | None = None) -> int:
        """
        Reprend les forçages non échus. Avant heure fiable, l'échéance ne peut
        être ni crue ni prolongée : elle est rebornée sur le plafond de la cible
        et marquée « à confirmer ». Un forçage chauffage repris indéfiniment,
        c'est une serre qui n'est plus chauffée.
        """
        now_epoch = time() if now_epoch is None else now_epoch
        now_mono = monotonic() if now_mono is None else now_mono
        confirmed = time_reliability().state != "unknown"

        raw = self._store.load(SECTION)
        records: dict[str, ForcedOff] = {}
        for target, item in raw.items():
            if target not in EQUIPMENT_IDS or not isinstance(item, dict):
                continue
            try:
                expires = float(item["expires_epoch"])
                created = float(item.get("created_epoch", expires))
            except (KeyError, TypeError, ValueError):
                warning(f"Forçage persisté illisible pour {target} → ignoré",
                        name=LOGGER_NAME)
                continue

            cap = max_seconds(target)
            if confirmed:
                if expires - now_epoch <= 0:
                    continue
                # Un enregistrement plus vieux que le plafond actuel ne peut pas
                # revenir plus long qu'un forçage créé aujourd'hui.
                expires = min(expires, now_epoch + cap)
                deadline = now_mono + (expires - now_epoch)
            else:
                expires = now_epoch + cap
                deadline = now_mono + cap

            records[target] = ForcedOff(
                target=target,
                reason=sanitize_reason(item.get("reason", "")),
                created_epoch=created,
                expires_epoch=expires,
                deadline_mono=deadline,
                confirmed=confirmed,
            )

        self._records = records
        if records:
            suffixe = "" if confirmed else " (à confirmer : heure non fiable)"
            info(f"Forçages « arrêt » repris : {', '.join(sorted(records))}{suffixe}",
                 name=LOGGER_NAME)
        if records or raw:
            self._persist(strict=False)
        return len(records)

    # ── mutations ─────────────────────────────────────────────
    def create(self, target: str, seconds, reason: str = "", *,
               now_epoch: float | None = None,
               now_mono: float | None = None) -> ForcedOff:
        """
        Crée ou remplace un forçage. Persiste **avant** de rendre la main :
        un forçage accepté mais non écrit disparaîtrait au premier redémarrage
        sans que personne ne l'ait levé, la route HTTP répond donc 500.
        """
        if target not in EQUIPMENT_IDS:
            raise UnknownTarget(f"cible inconnue : {target!r}")
        try:
            seconds = float(seconds)
        except (TypeError, ValueError):
            raise InvalidDuration("durée illisible")
        cap = max_seconds(target)
        if not 0 < seconds <= cap:
            raise InvalidDuration(
                f"durée hors bornes : 1 s à {cap // 60} min pour {target}"
            )
        if time_reliability().state == "unknown":
            raise TimeUnreliable(
                "heure non fiable : impossible de borner un forçage"
            )

        now_epoch = time() if now_epoch is None else now_epoch
        now_mono = monotonic() if now_mono is None else now_mono
        record = ForcedOff(
            target=target,
            reason=sanitize_reason(reason),
            created_epoch=now_epoch,
            expires_epoch=now_epoch + seconds,
            deadline_mono=now_mono + seconds,
        )

        previous = self._records.get(target)
        self._records[target] = record
        try:
            self._persist(strict=True)
        except OSError:
            if previous is None:
                self._records.pop(target, None)
            else:
                self._records[target] = previous
            raise
        # La raison n'est jamais journalisée : elle partirait dans /console.
        info(f"Forçage « arrêt » créé sur {target} pour {seconds / 60:.0f} min",
             name=LOGGER_NAME)
        return record

    def cancel(self, target: str) -> bool:
        """
        Lève un forçage. La levée est appliquée **immédiatement en mémoire** ;
        si la trace ne peut pas être écrite on la retentera au prochain passage,
        on ne rétablit pas une coupure que l'opérateur vient de lever. C'est la
        seule dissymétrie voulue avec `create()`.
        """
        if target not in EQUIPMENT_IDS:
            raise UnknownTarget(f"cible inconnue : {target!r}")
        if self._records.pop(target, None) is None:
            return False
        self._persist(strict=False)
        info(f"Forçage « arrêt » levé sur {target}", name=LOGGER_NAME)
        return True

    # ── lectures ──────────────────────────────────────────────
    def is_forced_off(self, target: str, now_epoch: float | None = None,
                      now_mono: float | None = None) -> bool:
        record = self._records.get(target)
        if record is None:
            return False
        now_epoch = time() if now_epoch is None else now_epoch
        now_mono = monotonic() if now_mono is None else now_mono
        if record.active_at(now_epoch, now_mono):
            return True
        self._expire(target)
        return False

    def deadlines(self, target: str, *, now_epoch: float | None = None,
                  now_mono: float | None = None) -> tuple[float | None, float | None]:
        """
        Échéances brutes destinées à `ClimateInputs`. La politique thermique
        réévalue l'expiration elle-même à partir de ses propres horloges : c'est
        ce qui la garde pure et rejouable au harnais.
        """
        if not self.is_forced_off(target, now_epoch, now_mono):
            return None, None
        record = self._records[target]
        return record.expires_epoch, record.deadline_mono

    def active(self, now_epoch: float | None = None,
               now_mono: float | None = None) -> dict[str, ForcedOff]:
        now_epoch = time() if now_epoch is None else now_epoch
        now_mono = monotonic() if now_mono is None else now_mono
        for target in list(self._records):
            self.is_forced_off(target, now_epoch, now_mono)
        return dict(self._records)

    def payload(self, now_epoch: float | None = None,
                now_mono: float | None = None) -> dict:
        """Vue destinée à `/api/v1/state` — aucun secret, raison telle que saisie."""
        now_epoch = time() if now_epoch is None else now_epoch
        now_mono = monotonic() if now_mono is None else now_mono
        items = []
        for target, record in sorted(self.active(now_epoch, now_mono).items()):
            items.append({
                "target": target,
                "reason": record.reason,
                "confirmed": record.confirmed,
                "expires_epoch": round(record.expires_epoch, 3),
                "remaining_seconds": round(
                    record.remaining_seconds(now_epoch, now_mono), 1
                ),
            })
        return {
            "active_count": len(items),
            "unconfirmed_count": sum(1 for item in items if not item["confirmed"]),
            "items": items,
            # Les plafonds voyagent avec l'état : ni le gabarit ni le JavaScript
            # n'ont à redéclarer une règle de sûreté.
            "limits_minutes": {target: max_seconds(target) // 60
                               for target in EQUIPMENT_IDS},
            "default_minutes": DEFAULT_SECONDS // 60,
        }

    # ── interne ───────────────────────────────────────────────
    def _expire(self, target: str) -> None:
        if self._records.pop(target, None) is None:
            return
        info(f"Forçage « arrêt » expiré sur {target}", name=LOGGER_NAME)
        self._persist(strict=False)

    def _persist(self, *, strict: bool) -> None:
        payload = {target: record.to_payload()
                   for target, record in self._records.items()}
        self._store.save(SECTION, payload, force=True, strict=strict)


# Magasin partagé du processus : une seule vérité pour les boucles et pour HTTP.
_shared: OverrideStore | None = None


def shared_overrides() -> OverrideStore:
    global _shared
    if _shared is None:
        _shared = OverrideStore()
    return _shared
