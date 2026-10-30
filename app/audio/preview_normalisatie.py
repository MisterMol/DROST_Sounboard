"""Bepaal voor lokaal afspelen exact dezelfde gain als voor de audiomixer.

De browser behoudt het originele mediabestand (inclusief video) en gebruikt
Web Audio GainNode voor audio. Analyse is begrensd tot het geselecteerde
fragment en vindt uitsluitend plaats tijdens een expliciete preview.
"""
from __future__ import annotations

import math
from pathlib import Path

import numpy as np

from app.audio.geluidsnormalisatie import (
    NORMALISATIESTANDEN, bereken_normalisatiefactor,
)
from app.audio.mp3_en_wav_fragmenten import lees_en_bereid_mp3_of_wav_voor


def bereken_browser_preview_versterkingen(
    bestandspad: str | Path, *, begin: float, duur: float, volume: float,
) -> dict:
    """Lever vier versterkingen in een decode, zonder de bron aan te passen.

    `basisgain` omvat de per-geluid-instelling en dezelfde digitale
    piekbescherming als de mixer. De normalisatiefactor wordt berekend *na*
    deze volumeregeling, identiek aan het nieuwe live-afspeelpad.
    """
    clip = lees_en_bereid_mp3_of_wav_voor(
        bestandspad, beginpositie_seconden=begin, maximale_duur_seconden=duur,
        ingesteld_volume=1.0, normalisatiestand='uit',
    )
    ruwe_samples = np.frombuffer(clip.ruwe_float32_stereo_audio, dtype='<f4').reshape(-1, 2)
    piek = float(np.max(np.abs(ruwe_samples)))
    basisgain = float(volume)
    if piek > 0 and basisgain * piek > 1.0:
        basisgain = 1.0 / piek
    # Slechts een enkele tijdelijke kopie. Maximaal 120 s bij 48 kHz stereo.
    aangepaste_samples = np.array(ruwe_samples, copy=True)
    aangepaste_samples *= np.float32(basisgain)
    versterkingen = {}
    correcties_db = {}
    for stand in NORMALISATIESTANDEN:
        factor = 1.0 if volume == 0 else bereken_normalisatiefactor(aangepaste_samples, stand)
        versterkingen[stand] = round(basisgain * factor, 7)
        correcties_db[stand] = round(20.0 * math.log10(factor), 1) if factor > 0 else 0.0
    return {'versterkingen': versterkingen, 'correcties_db': correcties_db,
            'begin': float(begin), 'duur': float(clip.duur_in_seconden)}
