"""Meet de werkelijke lengte en golfvorm van een audiofragment.

We lezen maximaal twee minuten in kleine blokken. De pieken en het
RMS-gemiddelde worden PER tijdkolom bepaald; alleen deze samenvatting gaat
naar de browser. De originele bestanden en live audiostream blijven intact.
"""
from __future__ import annotations

import math
from pathlib import Path
import subprocess

from app.diagnostiek.vensterloze_windowsprocessen import geef_opstartopties_zonder_console

import numpy as np


class BronbestandNietLeesbaar(ValueError):
    """Geeft een herkenbare foutcode voor ongeldige of onleesbare bronnen."""


def bepaal_werkelijke_bronduur(bestandspad: Path) -> float:
    """Lees de echte bronduur; de limiet van 120 s is geen bronlengte."""
    bestandspad = Path(bestandspad)
    if not bestandspad.is_file():
        raise BronbestandNietLeesbaar('DUUR-001: het bronbestand bestaat niet.')
    try:
        if bestandspad.suffix.casefold() == '.mp4':
            from app.audio.mp4_verwerken import controleer_of_mp4_audio_en_video_bevat
            duur = controleer_of_mp4_audio_en_video_bevat(bestandspad)
        else:
            import soundfile as geluidsbestanden
            duur = float(geluidsbestanden.info(str(bestandspad)).duration)
    except (RuntimeError, ValueError, OSError) as fout:
        raise BronbestandNietLeesbaar('DUUR-002: de lengte van de bron kon niet worden gelezen.') from fout
    if not math.isfinite(duur) or duur <= 0:
        raise BronbestandNietLeesbaar('DUUR-003: het geluidsbestand heeft geen geldige lengte.')
    return round(duur, 4)


def bepaal_werkelijke_fragmentduur(bronduur: float | None, begin: float, maximum: float) -> float | None:
    """Toon bijvoorbeeld 0:29 als de bron 29 seconden lang is."""
    if bronduur is None:
        return None
    if any(not isinstance(x, (float, int)) or not math.isfinite(x) for x in (bronduur, begin, maximum)):
        return None
    if begin >= bronduur:
        return 0.0
    return round(max(0.0, min(bronduur - begin, maximum, 120.0)), 4)


def maak_golfvorm_voor_tijdsvenster(
    bestandspad: Path, begin: float, zichtbare_duur: float, aantal_kolommen: int = 160,
) -> list[float]:
    """Bestaande aanroep blijft een lijst pieken retourneren (achterwaarts compatibel)."""
    return maak_gedetailleerde_golfvorm_voor_tijdsvenster(
        bestandspad, begin, zichtbare_duur, aantal_kolommen,
    )['pieken']


def maak_gedetailleerde_golfvorm_voor_tijdsvenster(
    bestandspad: Path, begin: float, zichtbare_duur: float, aantal_kolommen: int = 640,
) -> dict[str, list[float]]:
    """Geef pieken én gemiddeld niveau per tijdkolom terug.

    Waarom twee reeksen? Een enkele piek per kolom laat ieder klikje er
    even groot uitzien. Met een tweede RMS-omtrek zie je ook de volle stukken
    van een stem of nummer, zonder nepdetails tussen samples te verzinnen.
    """
    if (type(aantal_kolommen) is not int or not 16 <= aantal_kolommen <= 1200
            or isinstance(begin, bool) or not isinstance(begin, (int, float))
            or not math.isfinite(begin) or begin < 0
            or isinstance(zichtbare_duur, bool) or not isinstance(zichtbare_duur, (int, float))
            or not math.isfinite(zichtbare_duur) or not 0.005 <= zichtbare_duur <= 120):
        raise BronbestandNietLeesbaar('GOLF-001: ongeldige beginpositie, vensterduur of resolutie.')
    bestandspad = Path(bestandspad)
    if not bestandspad.is_file():
        raise BronbestandNietLeesbaar('GOLF-002: het bronbestand is niet beschikbaar.')

    hoogste_pieken = np.zeros(aantal_kolommen, dtype=np.float32)
    som_van_kwadraten = np.zeros(aantal_kolommen, dtype=np.float64)
    aantal_samples_per_kolom = np.zeros(aantal_kolommen, dtype=np.int64)

    def verwerk_blok(waarden: np.ndarray, eerste_sample: int, totaal_frames: int) -> None:
        """Werk alleen statistieken bij; bewaar geen gedecodeerde audioblokken."""
        if len(waarden) == 0:
            return
        if waarden.ndim == 1:
            waarden = waarden.reshape(-1, 1)
        # Voor een stereo-bestand bepaalt de luidste sample de piek.
        # RMS nemen we over beide kanalen zodat de energie niet verdubbelt.
        pieken = np.max(np.abs(waarden), axis=1)
        energie = np.mean(waarden.astype(np.float64) ** 2, axis=1)
        posities = np.minimum(
            aantal_kolommen - 1,
            ((eerste_sample + np.arange(len(waarden), dtype=np.int64)) * aantal_kolommen)
            // max(1, totaal_frames),
        )
        np.maximum.at(hoogste_pieken, posities, pieken)
        som_van_kwadraten[:] += np.bincount(
            posities, weights=energie, minlength=aantal_kolommen,
        )
        aantal_samples_per_kolom[:] += np.bincount(
            posities, minlength=aantal_kolommen,
        )

    if bestandspad.suffix.casefold() == '.mp4':
        from app.audio.mp4_verwerken import geef_meegeleverde_ffmpeg
        # Bij sterk inzoomen heeft 800 Hz te weinig meetpunten. Gebruik
        # daarom meer echte samples per kolom, maar houd het aantal bytes
        # klein bij lange nummers. Dit geldt uitsluitend voor de golfvorm.
        meetfrequentie = min(48_000, max(800, math.ceil(3 * aantal_kolommen / zichtbare_duur)))
        commando = [
            geef_meegeleverde_ffmpeg(), '-nostdin', '-hide_banner', '-loglevel', 'error',
            '-ss', str(begin), '-i', str(bestandspad), '-t', str(zichtbare_duur),
            '-map', '0:a:0', '-vn', '-ac', '1', '-ar', str(meetfrequentie), '-f', 'f32le', 'pipe:1',
        ]
        try:
            resultaat = subprocess.run(commando, capture_output=True, timeout=35, check=False,
                                     **geef_opstartopties_zonder_console())
        except (subprocess.TimeoutExpired, OSError) as fout:
            raise BronbestandNietLeesbaar('GOLF-003: videogeluid kon niet worden gemeten.') from fout
        if resultaat.returncode != 0 or len(resultaat.stdout) % 4 != 0:
            raise BronbestandNietLeesbaar('GOLF-004: FFmpeg gaf geen bruikbare golfvorm terug.')
        samples = np.frombuffer(resultaat.stdout, dtype='<f4')
        # Ook bij ingezoomd videogeluid analyseren we werkelijke samples.
        # De meetfrequentie wordt begrensd op 48 kHz om RAM te beheersen.
        verwerk_blok(samples, 0, len(samples))
    else:
        try:
            import soundfile as sf
            with sf.SoundFile(str(bestandspad)) as bron:
                frequentie = bron.samplerate
                bron.seek(min(bron.frames, round(begin * frequentie)))
                frames = min(bron.frames - bron.tell(), round(zichtbare_duur * frequentie))
                gelezen = 0
                while gelezen < frames:
                    blok = bron.read(min(8192, frames - gelezen), dtype='float32', always_2d=True)
                    if len(blok) == 0:
                        break
                    verwerk_blok(blok, gelezen, frames)
                    gelezen += len(blok)
        except (RuntimeError, ValueError, OSError) as fout:
            raise BronbestandNietLeesbaar('GOLF-005: audiobestand kon niet worden gemeten.') from fout

    normalisatiefactor = float(np.max(hoogste_pieken))
    if not math.isfinite(normalisatiefactor) or normalisatiefactor <= 0:
        return {'pieken': [0.0] * aantal_kolommen, 'rms': [0.0] * aantal_kolommen}
    rms_per_kolom = np.sqrt(
        som_van_kwadraten / np.maximum(1, aantal_samples_per_kolom),
    )
    # Beide reeksen delen dezelfde normalisatie, anders lijkt ieder zacht
    # stukje even luid. Deze reeks bepaalt uitsluitend de visuele golfvorm.
    return {
        'pieken': [round(float(min(1.0, max(0.0, v / normalisatiefactor))), 4)
                   for v in hoogste_pieken],
        'rms': [round(float(min(1.0, max(0.0, v / normalisatiefactor))), 4)
                for v in rms_per_kolom],
    }
