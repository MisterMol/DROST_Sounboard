"""Lichte stereo-pieklimiter voor de finale microfoonmix.

De limiter verwerkt alleen het al gemengde blok, dus zonder extra
buffervertraging. Binnen het beschikbare blok begint hij de versterking
al te verlagen vóór een nabije piek. De herstelhelling is begrensd,
zodat het volume niet voortdurend op en neer springt.

Het is een sample-pieklimiter, geen true-peak/oversampling- of
loudness-processor. De noodbegrenzing in de audiomixer blijft bestaan.
"""
from __future__ import annotations

import math
import numpy as np
from numpy.lib.stride_tricks import sliding_window_view

from app.audio.geluidsbestanden import SAMPLEFREQUENTIE_VAN_DE_UITVOER

PIEKPLAFOND = 0.95
VOORUITKIJKEN_IN_MILLISECONDEN = 2.0
HERSTEL_DUUR_IN_SECONDEN = 0.12


class PiekLimiter:
    """Eén toestand voor alle opeenvolgende audioframes van een stereomix."""

    def __init__(self, samplefrequentie: int = SAMPLEFREQUENTIE_VAN_DE_UITVOER):
        if type(samplefrequentie) is not int or samplefrequentie < 8000:
            raise ValueError('LIMITER-001: een geldige samplefrequentie is verplicht.')
        self.samplefrequentie = samplefrequentie
        self.plafond = PIEKPLAFOND
        self.vooruitkijk_frames = max(1, round(
            samplefrequentie * VOORUITKIJKEN_IN_MILLISECONDEN / 1000))
        # Lineaire, langzame vrijgave: ongeveer 120 ms van 0% naar 100% gain.
        self.herstel_per_frame = 1.0 / (samplefrequentie * HERSTEL_DUUR_IN_SECONDEN)
        self.huidige_versterking = 1.0
        self._gewichten = np.linspace(1.0, 0.0, self.vooruitkijk_frames + 1, dtype=np.float32)

    def herstel(self) -> None:
        """Begin na opnieuw verbinden/inschakelen met een neutrale gain."""
        self.huidige_versterking = 1.0

    def verwerk_in_place(self, stereomix: np.ndarray) -> float:
        """Begrens pieken in dezelfde buffer; geef de grootste reductie in dB terug.

        Beide kanalen krijgen dezelfde gain. Zo verschuift het stereo-beeld
        niet. De korte vooruitblik is beperkt tot het reeds ontvangen blok:
        er worden dus geen extra audiobuffers of samples vastgehouden.
        """
        if (not isinstance(stereomix, np.ndarray) or stereomix.ndim != 2
                or stereomix.shape[1] != 2 or stereomix.dtype != np.float32):
            raise ValueError('LIMITER-002: verwacht float32-stereo in een NumPy-buffer.')
        aantal_frames = len(stereomix)
        if aantal_frames == 0:
            return 0.0
        if not np.isfinite(stereomix).all():
            raise ValueError('LIMITER-003: bronmix bevat niet-eindige samples.')
        pieken = np.max(np.abs(stereomix), axis=1)
        # Alleen wanneer de piek groter is dan het plafond is verwerking
        # nodig. Bij een rustige mix blijft het geluid exact onveranderd
        # zodra de vorige reductie is vrijgegeven.
        gewenst = np.minimum(1.0, self.plafond / np.maximum(pieken, 1e-12))
        vooruit = min(self.vooruitkijk_frames, aantal_frames - 1)
        if vooruit > 0:
            # Aan het einde van een PortAudio-blok kennen we de toekomst
            # niet. Gebruik uitsluitend daadwerkelijk aangeleverde frames.
            # De aflopende weging laat piekreductie binnen dat venster
            # geleidelijk toenemen, zonder extra uitgangsvertraging.
            verlies = 1.0 - gewenst
            venster = sliding_window_view(np.pad(verlies, (0, vooruit)), vooruit + 1)
            gewenste_reductie = np.max(
                venster * self._gewichten[:vooruit + 1][None, :], axis=1)
            gewenste_versterking = 1.0 - gewenste_reductie
        else:
            gewenste_versterking = gewenst
        if self.huidige_versterking >= 1.0 and np.all(gewenste_versterking >= 1.0):
            return 0.0
        # g[i] = min(gewenst[i], g[i-1] + release). Deze exacte
        # recurrence is met cumulative-min volledig in NumPy berekend.
        # Daardoor loopt er geen Python-forlus per frame in de callback.
        herstel = np.arange(1, aantal_frames + 1, dtype=np.float32) * self.herstel_per_frame
        relatieve_grens = gewenste_versterking - herstel
        versterking = np.minimum(
            float(self.huidige_versterking), np.minimum.accumulate(relatieve_grens)) + herstel
        np.clip(versterking, 0.0, 1.0, out=versterking)
        # De gewenste gain is op elk sample minstens zo klein als nodig
        # voor het echte sample-plafond. Deze extra minimumstap is defensief.
        np.minimum(versterking, gewenste_versterking, out=versterking)
        stereomix *= versterking[:, None]
        self.huidige_versterking = float(versterking[-1])
        kleinste = float(np.min(versterking))
        return max(0.0, -20 * math.log10(max(kleinste, 1e-12)))
