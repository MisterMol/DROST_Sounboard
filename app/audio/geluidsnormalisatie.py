"""Lichte luidheidsafstemming voor soundboardfragmenten, buiten de audiocallback.

De bronbestanden worden nooit gewijzigd. We gebruiken de RMS van actieve
100 ms-vensters, zodat stiltes de versterking niet kunstmatig omhoog duwen.
Dit is geen EBU R128/LUFS-normalisatie en ook geen dynamische limiter.
"""

from __future__ import annotations

import math

import numpy as np

NORMALISATIESTANDEN = ('uit', 'subtiel', 'normaal', 'sterk')
# Sterkte van de correctie plus grenzen voorkomen extreme versterking.
_STERKTES = {'uit': 0.0, 'subtiel': 0.35, 'normaal': 0.70, 'sterk': 1.0}
_MINIMUMFACTOR = {'uit': 1.0, 'subtiel': 0.8, 'normaal': 0.6, 'sterk': 0.4}
_MAXIMUMFACTOR = {'uit': 1.0, 'subtiel': 1.4, 'normaal': 2.0, 'sterk': 3.0}
DOEL_RMS = 0.12  # circa -18,4 dBFS in de actieve delen
MAXIMALE_AUDIOPIEK = 0.98  # bronpieken beschermen; mix krijgt later eigen limiter


def controleer_normalisatiestand(stand: str) -> str:
    """Accepteer precies de vier opgeslagen standen, geen ongeldige waarden."""
    if type(stand) is not str or stand not in NORMALISATIESTANDEN:
        raise ValueError('NORM-001: kies Uit, Subtiel, Normaal of Sterk.')
    return stand


def bereken_normalisatiefactor(samples: np.ndarray, stand: str) -> float:
    """Bepaal één rustige versterkingsfactor voor het *geselecteerde* fragment.

    Gebruik een vaste factor per fragment, niet per audioblok. Daarmee blijven
    dynamiek en ritme intact. Beperk pieken vóór het mengen met de microfoon.
    """
    controleer_normalisatiestand(stand)
    if stand == 'uit':
        return 1.0
    if not isinstance(samples, np.ndarray) or samples.ndim != 2 or samples.shape[1] != 2:
        raise ValueError('NORM-002: verwacht twee kanalen met audiosamples.')
    if not samples.size or not np.all(np.isfinite(samples)):
        raise ValueError('NORM-003: fragment heeft geen geldige audiosamples.')

    piek = float(np.max(np.abs(samples)))
    if piek < 0.003:
        # Volledige stilte en vrijwel onhoorbare ruis niet oppompen.
        return 1.0

    # Kleine vensters beperken tussentijds geheugenverbruik tot zo'n 40 KiB.
    # Voor 120 s audio betekent dit ongeveer 1200 kleine berekeningen.
    vensterframes = 4800  # 100 ms op 48 kHz
    niveaus = []
    for begin in range(0, len(samples), vensterframes):
        venster = samples[begin:begin + vensterframes]
        energie = float(np.einsum('ij,ij->', venster, venster, dtype=np.float64, optimize=False))
        niveaus.append(math.sqrt(energie / venster.size))
    niveaus = np.asarray(niveaus, dtype=np.float64)
    drempel = max(0.004, float(np.max(niveaus)) * 0.12)
    actief = niveaus[niveaus >= drempel]
    if actief.size == 0:
        return 1.0
    referentie = float(np.percentile(actief, 70))
    if referentie < 0.004:
        return 1.0

    doel_factor = DOEL_RMS / referentie
    factor = doel_factor ** _STERKTES[stand]
    factor = min(_MAXIMUMFACTOR[stand], max(_MINIMUMFACTOR[stand], factor))
    # Alleen extra versterking begrenzen op werkelijke pieken. Een reeds harde
    # bron niet stilletjes extra verlagen wanneer normalisatie méér volume wil.
    if factor > 1:
        factor = max(1.0, min(factor, MAXIMALE_AUDIOPIEK / piek))
    return float(factor)


def normaliseer_fragment_in_geheugen(samples: np.ndarray, stand: str) -> float:
    """Pas normalisatie in-place toe op de reeds gedecodeerde kopie, nooit op het bronbestand."""
    factor = bereken_normalisatiefactor(samples, stand)
    if factor != 1.0:
        samples *= np.float32(factor)
    return factor
