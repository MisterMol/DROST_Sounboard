"""Controleer of een specifiek testsignaal is ontvangen, niet zomaar ruis.

Een gewone niveaumeting kan ook slagen wanneer een ander programma toevallig
iets naar CABLE Input stuurt. Daarom zoeken we daarnaast gericht naar de
frequentie van onze eigen testtoon van 440 Hz.
"""

from __future__ import annotations

import math
import struct
from dataclasses import dataclass


@dataclass
class HerkennerVoorEenVasteToon:
    """Meet met een eenvoudige Goertzel-berekening hoe sterk één toon aanwezig is.

    We bewaren alleen enkele getallen. Daarmee hoeven we opgenomen audio
    niet vast te houden of naar een logbestand te schrijven.
    """

    samplefrequentie: int
    toonhoogte_in_hertz: int
    aantal_verwerkte_frames: int = 0
    vorige_berekening: float = 0.0
    berekening_daarvoor: float = 0.0

    def verwerk_nieuw_audioblok(self, stereo_float32_bytes: bytes) -> None:
        """Voeg opeenvolgende audioframes toe aan de toonherkenning."""
        if len(stereo_float32_bytes) % 8:
            raise ValueError(
                "TOON-010: toonherkenning verwacht hele stereo float32-frames."
            )
        if self.samplefrequentie <= 0 or not (
            0 < self.toonhoogte_in_hertz < self.samplefrequentie / 2
        ):
            raise ValueError("TOON-011: ongeldige frequenties voor toonherkenning.")

        factor_voor_gezochte_toon = 2 * math.cos(
            2 * math.pi * self.toonhoogte_in_hertz / self.samplefrequentie
        )

        for linker_sample, rechter_sample in struct.iter_unpack(
            "<ff", stereo_float32_bytes
        ):
            gemiddelde_sample = (linker_sample + rechter_sample) / 2
            nieuwe_berekening = (
                gemiddelde_sample
                + factor_voor_gezochte_toon * self.vorige_berekening
                - self.berekening_daarvoor
            )
            self.berekening_daarvoor = self.vorige_berekening
            self.vorige_berekening = nieuwe_berekening
            self.aantal_verwerkte_frames += 1

    def bereken_sterkte_van_de_herkende_toon(self) -> float:
        """Geef een amplitude terug, of nul als er geen complete meting is."""
        if not self.aantal_verwerkte_frames:
            return 0.0

        factor_voor_gezochte_toon = 2 * math.cos(
            2 * math.pi * self.toonhoogte_in_hertz / self.samplefrequentie
        )
        vermogen = (
            self.vorige_berekening**2
            + self.berekening_daarvoor**2
            - factor_voor_gezochte_toon
            * self.vorige_berekening
            * self.berekening_daarvoor
        )
        return 2 * math.sqrt(max(0.0, vermogen)) / self.aantal_verwerkte_frames
