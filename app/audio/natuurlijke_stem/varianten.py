"""Benoemde klankvarianten van één LLVC-model, geen nieuwe getrainde stemmen.

Dezelfde nabewerking wordt gebruikt voor live audio en de ingebouwde voorbeelden.
Een Signalsmith-instantie hoort bij één stream en blijft tussen blokken bestaan.
"""
from __future__ import annotations
from dataclasses import dataclass
import numpy as np


@dataclass(frozen=True)
class Stemvariant:
    id: str
    naam: str
    beschrijving: str
    icoon: str
    toonhoogte: float = 0.0
    klankkleur: float = 0.0
    effect: int = 0
    sterkte: float = 1.0
    instelling1: float = 0.5
    instelling2: float = 0.5
    nabewerking: bool = True


VARIANTEN = (
    Stemvariant('llvc_basis', 'Nova', 'De basisstem, zonder extra klankbewerking.', 'nova-basis', nabewerking=False),
    Stemvariant('llvc_warm', 'Ruben', 'Een lagere, donkerdere variant van Nova.', 'nova-warm', -2.5, -1.2),
    Stemvariant('llvc_helder', 'Linde', 'Een hogere, lichtere variant van Nova.', 'nova-helder', 2.5, 1.3),
    Stemvariant('llvc_radio', 'Omroeper', 'Nova met een smalle, licht metalen radioklank.', 'nova-radio', effect=2, sterkte=.78, instelling1=.22, instelling2=.27),
)
OP_ID = {v.id: v for v in VARIANTEN}


def controleer_variant(keuze: str) -> Stemvariant:
    if not isinstance(keuze, str) or keuze not in OP_ID:
        raise ValueError('Kies een beschikbare karaktervariant.')
    return OP_ID[keuze]


def catalogus() -> list[dict]:
    return [dict(id=v.id, naam=v.naam, beschrijving=v.beschrijving, icoon=v.icoon,
                 motor='llvc', soort='klankvariant', model_id='koeai-llvc-proef-1',
                 label={'llvc_basis': 'Basisstem', 'llvc_warm': 'Lagere klank',
                        'llvc_helder': 'Hogere klank', 'llvc_radio': 'Radioklank'}[v.id]) for v in VARIANTEN]


class Klankbewerking:
    def __init__(self, keuze: str, *, motor_factory=None):
        self.variant = controleer_variant(keuze)
        self.motor = None
        if self.variant.nabewerking:
            if motor_factory is None:
                from app.audio.signalsmith_motor import SignalsmithMotor
                motor_factory = SignalsmithMotor
            self.motor = motor_factory(48000)
        self.vertraging_ms = (self.motor.vertraging_samples / 48
                             if self.motor is not None and self.variant.effect == 0 else 0.0)

    def verwerk(self, mono: np.ndarray) -> np.ndarray:
        if (not isinstance(mono, np.ndarray) or mono.dtype != np.float32
                or mono.ndim != 1 or not np.isfinite(mono).all()):
            raise ValueError('Ongeldige audio voor de karaktervariant.')
        if self.motor is None:
            return mono.copy()
        v = self.variant
        uit = self.motor.verwerk_blok(mono[:, None], toonhoogte=v.toonhoogte,
                    klankkleur=v.klankkleur, effect=v.effect, sterkte=v.sterkte,
                    instelling1=v.instelling1, instelling2=v.instelling2)
        return np.clip(uit[:, 0], -.95, .95).astype(np.float32)

    def sluiten(self):
        if self.motor is not None:
            self.motor.sluiten()
            self.motor = None

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.sluiten()
