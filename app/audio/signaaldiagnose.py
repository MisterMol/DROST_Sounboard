"""Maak gemeten audiovolumes leesbaar zonder spraak op te slaan.

De audiomixer gebruikt alleen getallen over het niveau van een audioblok.
Er worden geen opnames, gespreksinhoud of losse audiosamples bewaard.
Deze berekeningen zitten los van het venster en zijn daarom eenvoudig te testen.
"""

from __future__ import annotations

import math

import numpy as np


class SignaalmetingFout(ValueError):
    """Een ontvangen audioblok is niet geschikt om betrouwbaar te meten."""


def meet_rms_en_piek_van_een_audioblok(audioblok: np.ndarray) -> tuple[float, float]:
    """Meet gemiddelde sterkte en piek van audiogeluid tussen nul en één.

    RMS is bruikbaar voor spraak: een enkele tik kan wel een hoge piek geven,
    maar is geen bewijs dat er continu microfoongeluid binnenkomt.
    """
    if not isinstance(audioblok, np.ndarray):
        raise SignaalmetingFout(
            f"SIGNAAL-001: verwacht een NumPy-audioblok, kreeg {type(audioblok).__name__}."
        )
    if audioblok.size == 0 or audioblok.ndim != 2:
        raise SignaalmetingFout("SIGNAAL-002: audioblok moet frames en kanalen bevatten.")
    if not np.isfinite(audioblok).all():
        raise SignaalmetingFout("SIGNAAL-003: audioblok bevat NaN of oneindige samples.")

    # Gebruik float64 voor het kwadraat. Float32 kan kleine audioniveaus
    # onnauwkeurig weergeven, waardoor een zachte microfoon als stil lijkt.
    kwadraten = np.square(audioblok, dtype=np.float64)
    gemiddeld_kwadraat = float(np.mean(kwadraten))
    hoogste_piek = float(np.max(np.abs(audioblok)))
    return math.sqrt(gemiddeld_kwadraat), hoogste_piek


def maak_een_leesbaar_geluidsniveau(rms: float, gemeten: bool) -> str:
    """Toon stilte en decibels zonder te suggereren dat VB-CABLE audio ontvangt."""
    if not gemeten:
        return "nog niet gemeten"
    if not isinstance(rms, (float, int)) or not math.isfinite(rms) or rms < 0:
        return "ongeldige meetwaarde"
    if rms < 0.0001:
        return "geen meetbaar signaal (lager dan -80 dBFS)"
    decibel = 20.0 * math.log10(rms)
    return f"{decibel:.1f} dBFS (RMS)"


def bereken_meterstand_op_schaal_van_honderd(rms: float, gemeten: bool) -> int:
    """Maak de meter ook voor zachte stemmen leesbaar zonder volume te wijzigen."""
    if not gemeten or not math.isfinite(rms) or rms <= 0:
        return 0
    decibel = 20.0 * math.log10(rms)
    return max(0, min(100, round((decibel + 70) / 70 * 100)))
