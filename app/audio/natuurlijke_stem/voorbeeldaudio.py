"""Valideer en bereid alleen ingebouwde voorbeeldfragmenten voor.

Geen microfoon, model of netwerk. Een constante niveaucorrectie van hooguit
factor vier voorkomt dat een zeer zacht fragment onnodig zacht het model ingaat.
Dit herstelt geen slechte opname en verbetert niet het getrainde stemmodel.
"""
from __future__ import annotations

import io
import numpy as np
import soundfile as sf
import soxr

SAMPLEFREQUENTIE = 48000


def lees_voorbeeld(bron: bytes) -> tuple[np.ndarray, int]:
    """Lees een begrensd audiobestand; geef kanalen en samplefrequentie terug."""
    if not isinstance(bron, bytes) or not 44 <= len(bron) <= 12 * 1024 * 1024:
        raise ValueError('Het ingebouwde voorbeeld is niet leesbaar.')
    try:
        with sf.SoundFile(io.BytesIO(bron)) as bestand:
            rate, frames, channels = bestand.samplerate, len(bestand), bestand.channels
            if channels not in (1, 2) or not 8000 <= rate <= 96000 or not 0 < frames / rate <= 30:
                raise ValueError('Het ingebouwde voorbeeld heeft een ongeldige lengte of audio-indeling.')
            audio = bestand.read(dtype='float32', always_2d=True)
    except (RuntimeError, OSError) as fout:
        raise ValueError('Het ingebouwde voorbeeld is geen leesbaar audiobestand.') from fout
    if not np.isfinite(audio).all():
        raise ValueError('Het ingebouwde voorbeeld bevat ongeldige samples.')
    return audio, rate


def maak_mono(audio: np.ndarray) -> np.ndarray:
    """Meng stereo, behalve als de twee kanalen elkaar grotendeels uitdoven."""
    if audio.ndim != 2 or audio.shape[1] not in (1, 2) or not len(audio) or not np.isfinite(audio).all():
        raise ValueError('Ongeldige kanalen in het stemvoorbeeld.')
    mono = audio.mean(axis=1, dtype=np.float32)
    if audio.shape[1] == 2:
        energie = np.mean(audio.astype(np.float64) ** 2, axis=0)
        sterkste = int(np.argmax(energie))
        gemengd = float(np.mean(mono.astype(np.float64) ** 2))
        # Niet elk niveauverschil is tegenfase. Grijp alleen in bij sterke uitdoving.
        if energie[sterkste] > 1e-10 and gemengd < energie[sterkste] * 0.1:
            mono = audio[:, sterkste].copy()
    return mono


def pas_bronniveau_aan(mono: np.ndarray) -> np.ndarray:
    """Eén vaste gain voor het hele fragment, zonder compressor of toonbewerking."""
    if mono.ndim != 1 or not len(mono) or not np.isfinite(mono).all():
        raise ValueError('Het stemvoorbeeld bevat ongeldige samples.')
    piek = float(np.max(np.abs(mono)))
    if piek < 1e-4:
        return mono.copy()  # Stilte en vrijwel stille ruis niet opblazen.
    # Korte stukken meten voorkomt dat stilte voor/na spraak de gain bepaalt.
    venster = 960
    metingen = [float(np.sqrt(np.mean(mono[i:i+venster].astype(np.float64) ** 2)))
                for i in range(0, len(mono), venster)]
    actief = [x for x in metingen if x > max(1e-4, max(metingen) * 0.1)]
    niveau = float(np.percentile(actief, 70)) if actief else 0.0
    factor = 1.0
    if niveau and not 0.04 <= niveau <= 0.16:
        factor = max(0.25, min(4.0, 0.08 / niveau))
    factor = min(factor, 0.85 / piek)
    return (mono * factor).astype(np.float32)


def bereid_voorbeeld_voor(bron: bytes) -> np.ndarray:
    """Lever veilige 48 kHz mono-invoer voor dezelfde worker als live spraak."""
    audio, rate = lees_voorbeeld(bron)
    mono = maak_mono(audio)
    if rate != SAMPLEFREQUENTIE:
        mono = soxr.resample(mono, rate, SAMPLEFREQUENTIE, quality='HQ').astype(np.float32)
    return pas_bronniveau_aan(mono)
