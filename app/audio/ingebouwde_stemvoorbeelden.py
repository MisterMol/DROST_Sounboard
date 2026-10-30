"""Maak een lokale WAV-demo met dezelfde DSP als de live-stemvervormer.

Meegeleverde korte Bob- en Elise-MP3's, zonder persoonlijke bestanden of
microfoonstream. CPU-limiet ligt buiten de audiocallback, bij de lokale API.
"""
from __future__ import annotations

from io import BytesIO
from pathlib import Path
import wave

import numpy as np

from app.audio.stemvervorming import SAMPLEFREQUENTIE, Stemvervormer, controleer_stemprofiel, controleer_stemintensiteit
from app.audio.stemparameters import standaard_parameters, controleer_parameters

VOORBEELD_MAP = Path(__file__).resolve().parent / 'stemvoorbeelden'
VOORBEELD_SPREKERS = ('bob', 'elise')

def geef_voorbeeldpad(spreker: str) -> Path:
    if type(spreker) is not str or spreker not in VOORBEELD_SPREKERS:
        raise ValueError('STEM-055: kies Bob of Elise.')
    return VOORBEELD_MAP / f'hello_my_name_is_{spreker}.mp3'

def render_voorbeeld(spreker: str, profiel: str, intensiteit: int,
                      parameters: dict[str,dict] | None = None) -> bytes:
    """Decode, filter en render op 48 kHz mono 16-bits PCM. Nooit naar VB-CABLE."""
    pad = geef_voorbeeldpad(spreker)
    profiel = controleer_stemprofiel(profiel)
    intensiteit = controleer_stemintensiteit(intensiteit)
    import soundfile as sf
    import soxr
    if not pad.is_file() or pad.stat().st_size > 2 * 1024 * 1024:
        raise ValueError('STEM-056: meegeleverd voorbeeld ontbreekt of is ongeldig.')
    samples, bronfrequentie = sf.read(pad, dtype='float32', always_2d=True)
    if not 8000 <= bronfrequentie <= 96000 or not 1 <= len(samples) <= bronfrequentie * 12:
        raise ValueError('STEM-057: voorbeeld heeft een ongeldige duur of samplefrequentie.')
    if samples.shape[1] != 1:
        samples = np.mean(samples, axis=1, keepdims=True)
    if bronfrequentie != SAMPLEFREQUENTIE:
        samples = soxr.resample(samples, bronfrequentie, SAMPLEFREQUENTIE)
    samples = np.ascontiguousarray(samples, dtype=np.float32)
    alle = standaard_parameters() if parameters is None else {
        naam: controleer_parameters(naam, data) for naam,data in parameters.items()}
    processor = Stemvervormer(profiel, intensiteit=intensiteit, parameters=alle)
    staart = 0
    if profiel == 'echo' and intensiteit > 0:
        p = alle['echo']
        # Langere echo's blijven hoorbaar na het einde van de korte teststem.
        feedback = p['feedback_pct'] / 100.0
        herhalingen = 2 if feedback < .20 else 4 if feedback < .50 else 6
        staart = min(6 * SAMPLEFREQUENTIE,
                    int(SAMPLEFREQUENTIE * p['vertraging_ms']/1000 * herhalingen))
    als_audio = np.concatenate([samples, np.zeros((staart,1),dtype=np.float32)],axis=0)
    uitvoer = np.empty_like(als_audio)
    for begin in range(0,len(als_audio),480):
        einde = min(begin+480,len(als_audio))
        uitvoer[begin:einde] = processor.verwerk(als_audio[begin:einde])
    # Rustige browserweergave, pieken tegen digitale oversturing beschermen.
    uitvoer = np.clip(np.nan_to_num(uitvoer), -.92, .92)
    pcm = np.asarray(uitvoer[:,0] * 32767, dtype='<i2').tobytes()
    resultaat = BytesIO()
    with wave.open(resultaat,'wb') as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(SAMPLEFREQUENTIE)
        wav.writeframes(pcm)
    return resultaat.getvalue()
