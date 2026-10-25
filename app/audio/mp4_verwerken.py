"""Haal gecontroleerd de audio uit MP4, maar bewaar de video voor de browser.

FFmpeg draait uitsluitend tijdens importcontrole en voorbereiding van een gekozen
fragment. De realtime audiocallback wacht nooit op een video- of geluidsdecoder.
"""
from __future__ import annotations

import math
from pathlib import Path
import re
import subprocess
import sys

from app.diagnostiek.vensterloze_windowsprocessen import geef_opstartopties_zonder_console

import numpy as np


class MP4VerwerkingFout(ValueError):
    """Beschrijf wat misging zonder de oorspronkelijke FFmpeg-fout kwijt te raken."""


def geef_meegeleverde_ffmpeg():
    """Gebruik de decoder die via requirements.txt wordt geïnstalleerd.

    Hierdoor hoeft de gebruiker geen uitvoerbaar bestand te downloaden of een
    Windows PATH-variabele handmatig te wijzigen.
    """
    try:
        import imageio_ffmpeg
        if sys.platform == 'win32':
            # imageio_ffmpeg.get_ffmpeg_exe() voert op Windows voor validatie
            # ffmpeg -version uit. Juist die verborgen interne subprocess
            # was nog niet voorzien van onze CREATE_NO_WINDOW-vlag en kon
            # daarom kort een leeg consolevenster op de voorgrond tekenen.
            # De Windows-wheel levert de binary zelf al mee; we kiezen die
            # rechtstreeks, zonder een extra testproces op te starten.
            map_met_decoders = Path(imageio_ffmpeg.__file__).resolve().parent / 'binaries'
            architectuur = 'ffmpeg-win-x86_64-*.exe' if sys.maxsize > 2**32 else 'ffmpeg-win32-*.exe'
            kandidaten = sorted(map_met_decoders.glob(architectuur))
            if len(kandidaten) != 1 or not kandidaten[0].is_file():
                raise MP4VerwerkingFout(
                    'VIDEO-012: er is geen unieke meegeleverde Windows-decoder gevonden. '
                    'Installeer de Python-afhankelijkheden opnieuw.'
                )
            return str(kandidaten[0])
        return imageio_ffmpeg.get_ffmpeg_exe()
    except (ImportError, RuntimeError, OSError) as fout:
        raise MP4VerwerkingFout(
            'VIDEO-001: de MP4-decoder ontbreekt. Voer Installeer_ontwikkelomgeving.bat uit.'
        ) from fout


def controleer_of_mp4_audio_en_video_bevat(bestandspad: Path) -> float:
    """Controleer beide sporen vooraf, zodat een stille video niet in de bibliotheek belandt."""
    if not isinstance(bestandspad, Path) or not bestandspad.is_file():
        raise MP4VerwerkingFout('VIDEO-002: het MP4-bestand bestaat niet.')
    try:
        resultaat = subprocess.run(
            [geef_meegeleverde_ffmpeg(), '-nostdin', '-hide_banner', '-i', str(bestandspad)],
            capture_output=True, text=True, timeout=20, check=False,
            **geef_opstartopties_zonder_console(),
        )
    except (OSError, subprocess.TimeoutExpired) as fout:
        raise MP4VerwerkingFout('VIDEO-003: MP4 kon niet worden onderzocht binnen de tijdslimiet.') from fout
    bericht = (resultaat.stderr or '')[-12000:]
    if 'Video:' not in bericht or 'Audio:' not in bericht:
        raise MP4VerwerkingFout('VIDEO-004: de MP4 moet zowel een video- als een audiospoor bevatten.')
    match = re.search(r'Duration:\s*(\d+):(\d+):(\d+(?:\.\d+)?)', bericht)
    if match is None:
        raise MP4VerwerkingFout('VIDEO-005: de duur van de MP4 kon niet worden bepaald.')
    duur = int(match[1])*3600 + int(match[2])*60 + float(match[3])
    if not math.isfinite(duur) or duur <= 0:
        raise MP4VerwerkingFout('VIDEO-006: de MP4 heeft een ongeldige duur.')
    return duur


def lees_een_mp4_fragment_als_stereo_float32(
    bestandspad: Path, begint_bij_seconden: float, maximale_duur_seconden: float,
) -> tuple[np.ndarray, float]:
    """Decodeer maximaal 120 seconden naar het vaste formaat van VB-CABLE.

    Argumenten gaan afzonderlijk naar subprocess, nooit naar een shell.
    We begrenzen zowel tijd als uitvoeromvang om onnodig geheugengebruik te voorkomen.
    """
    bronduur = controleer_of_mp4_audio_en_video_bevat(bestandspad)
    if begint_bij_seconden >= bronduur:
        raise MP4VerwerkingFout(
            f'VIDEO-007: beginpositie {begint_bij_seconden:.1f} ligt na het einde ({bronduur:.1f}s).'
        )
    werkelijk_maximaal = min(float(maximale_duur_seconden), bronduur - begint_bij_seconden)
    commando = [
        geef_meegeleverde_ffmpeg(), '-nostdin', '-hide_banner', '-loglevel', 'error',
        '-ss', str(begint_bij_seconden), '-i', str(bestandspad),
        '-t', str(werkelijk_maximaal), '-map', '0:a:0', '-vn',
        '-ac', '2', '-ar', '48000', '-f', 'f32le', 'pipe:1',
    ]
    try:
        resultaat = subprocess.run(commando, capture_output=True, timeout=90, check=False,
                                 **geef_opstartopties_zonder_console())
    except (OSError, subprocess.TimeoutExpired) as fout:
        raise MP4VerwerkingFout('VIDEO-008: het decoderen van MP4 is mislukt of duurt te lang.') from fout
    if resultaat.returncode != 0:
        uitleg = resultaat.stderr.decode('utf-8', errors='replace')[-700:]
        raise MP4VerwerkingFout(f'VIDEO-009: FFmpeg kon de audio niet lezen: {uitleg}')
    maximaal_bytes = math.ceil(werkelijk_maximaal * 48_000) * 2 * 4 + 48_000
    if not resultaat.stdout or len(resultaat.stdout) > maximaal_bytes or len(resultaat.stdout) % 8 != 0:
        raise MP4VerwerkingFout('VIDEO-010: decoder leverde lege, te grote of onvolledige stereoframes.')
    samples = np.frombuffer(resultaat.stdout, dtype='<f4').reshape(-1, 2).copy()
    if not np.isfinite(samples).all():
        raise MP4VerwerkingFout('VIDEO-011: de gedecodeerde audio bevat NaN of oneindige waarden.')
    return samples, bronduur


def maak_miniatuur_van_videobeeld(bestandspad: Path, doelpad: Path) -> bool:
    """Maak een stil eerste videoframe voor snelle kaarten in de bibliotheek.

    We laden niet in iedere kaart een compleet MP4-bestand. Een afbeelding
    bespaart decodeerwerk, GPU en geheugen wanneer er niets wordt afgespeeld.
    Als de miniatuur mislukt, blijft import en de originele MP4 bruikbaar.
    """
    try:
        resultaat = subprocess.run([
            geef_meegeleverde_ffmpeg(), '-nostdin', '-hide_banner', '-loglevel', 'error',
            '-ss', '0.1', '-i', str(bestandspad), '-map', '0:v:0', '-frames:v', '1',
            '-vf', 'scale=480:270:force_original_aspect_ratio=decrease',
            '-y', str(doelpad),
        ], capture_output=True, timeout=20, check=False,
        **geef_opstartopties_zonder_console())
        if resultaat.returncode != 0 or not doelpad.is_file() or doelpad.stat().st_size < 20:
            doelpad.unlink(missing_ok=True)
            return False
        # Alleen bestanden met de echte PNG-handtekening worden aan browsers gegeven.
        if not doelpad.read_bytes().startswith(b'\x89PNG\r\n\x1a\n'):
            doelpad.unlink(missing_ok=True)
            return False
        return True
    except (OSError, subprocess.TimeoutExpired):
        doelpad.unlink(missing_ok=True)
        return False
