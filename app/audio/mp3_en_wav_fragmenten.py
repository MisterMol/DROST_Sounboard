"""Lees een gekozen MP3 of WAV en maak een begrensd fragment voor de live-mixer.

Een soundboard moet ook muziekbestanden van minutenlang kunnen *selecteren*,
zonder bij iedere klik alle muziek in het werkgeheugen te laden. Daarom lezen
we uitsluitend de ingestelde maximaal 120 seconden die de gebruiker wil gebruiken. De audiocallback
krijgt daarna kant-en-klare samples en hoeft niets van schijf te lezen.
"""

from __future__ import annotations

import hashlib
import math
from pathlib import Path

import numpy as np

from app.audio.geluidsnormalisatie import normaliseer_fragment_in_geheugen, controleer_normalisatiestand
from app.audio.geluidsbestanden import (
    AANTAL_UITVOERKANALEN,
    GeluidsbestandOngeldigFout,
    MAXIMALE_GELUIDSDUUR_IN_SECONDEN,
    SAMPLEFREQUENTIE_VAN_DE_UITVOER,
    STANDAARD_GELUIDSVOLUME,
    VoorbereidGeluidsfragment,
    versterk_samples_zonder_digitaal_te_oversturen,
)

TOEGESTANE_GELUIDSEXTENSIES = frozenset({".mp3", ".wav", ".mp4"})
MAXIMALE_BRONBESTANDSGROOTTE_IN_BYTES = 250 * 1024 * 1024


def controleer_of_geluidsbestand_gebruikt_mag_worden(bestandspad: str | Path) -> Path:
    """Controleer het bestand vóór we de decoder of de bibliotheek aanspreken."""
    if not isinstance(bestandspad, (str, Path)):
        raise GeluidsbestandOngeldigFout(
            f"GELUID-020: verwacht een bestandspad, ontvangen {type(bestandspad).__name__}."
        )
    if not str(bestandspad).strip():
        raise GeluidsbestandOngeldigFout("GELUID-021: kies eerst een bestand.")
    pad = Path(bestandspad).expanduser()
    if pad.suffix.casefold() not in TOEGESTANE_GELUIDSEXTENSIES:
        raise GeluidsbestandOngeldigFout(
            "GELUID-022: kies een MP3, WAV of MP4."
        )
    if not pad.is_file():
        raise GeluidsbestandOngeldigFout(
            f"GELUID-023: het bestand bestaat niet (meer): {pad.name}."
        )
    grootte = pad.stat().st_size
    if grootte == 0:
        raise GeluidsbestandOngeldigFout("GELUID-024: het bestand is leeg.")
    if grootte > MAXIMALE_BRONBESTANDSGROOTTE_IN_BYTES:
        raise GeluidsbestandOngeldigFout(
            "GELUID-025: bestand is groter dan 250 MiB. Dit voorkomt onbedoeld zware import."
        )
    return pad.resolve()


def _controleer_beginpositie_en_volume(beginpositie_seconden: float, volume: float) -> tuple[float, float]:
    """Weiger NaN, null en bool om stille of verkeerde audio te voorkomen."""
    for waarde, naam in ((beginpositie_seconden, "beginpositie"), (volume, "volume")):
        if isinstance(waarde, bool) or not isinstance(waarde, (float, int)):
            raise GeluidsbestandOngeldigFout(
                f"GELUID-026: {naam} moet een getal zijn; ontvangen {type(waarde).__name__}."
            )
        if not math.isfinite(waarde):
            raise GeluidsbestandOngeldigFout(f"GELUID-027: {naam} mag niet oneindig of NaN zijn.")
    if beginpositie_seconden < 0:
        raise GeluidsbestandOngeldigFout("GELUID-028: het startpunt mag niet negatief zijn.")
    if not 0 <= volume <= 2:
        raise GeluidsbestandOngeldigFout("GELUID-029: volume moet tussen nul en twee liggen (0 tot 200%).")
    return float(beginpositie_seconden), float(volume)


def lees_en_bereid_mp3_of_wav_voor(
    bestandspad: str | Path,
    beginpositie_seconden: float = 0.0,
    ingesteld_volume: float = STANDAARD_GELUIDSVOLUME,
    maximale_duur_seconden: float = MAXIMALE_GELUIDSDUUR_IN_SECONDEN,
    normalisatiestand: str = 'uit',
) -> VoorbereidGeluidsfragment:
    """Decodeer hooguit de ingestelde 120 seconden naar 48 kHz stereo met kwalitatief goede resampling.

    Alleen deze voorbereidende functie gebruikt soundfile en soxr. De callback
    blijft daardoor realtime en onafhankelijk van bestandsformaten.
    """
    controleer_normalisatiestand(normalisatiestand)
    gekozen_pad = controleer_of_geluidsbestand_gebruikt_mag_worden(bestandspad)
    startpunt, volume = _controleer_beginpositie_en_volume(beginpositie_seconden, ingesteld_volume)
    # Het maximale fragment is instelbaar per geluid, maar nooit meer dan twee minuten.
    # Daardoor worden enorme muzieknummers niet volledig in RAM gedecodeerd.
    if (isinstance(maximale_duur_seconden, bool)
            or not isinstance(maximale_duur_seconden, (int, float))
            or not math.isfinite(maximale_duur_seconden)
            or not 0.001 <= maximale_duur_seconden <= MAXIMALE_GELUIDSDUUR_IN_SECONDEN):
        raise GeluidsbestandOngeldigFout(
            "GELUID-037: maximale_duur_seconden moet een getal van 0,001 tot 120 zijn."
        )
    try:
        import soundfile as geluidsdecoder
        import soxr as audioconversie
    except ImportError as oorspronkelijke_fout:
        raise GeluidsbestandOngeldigFout(
            "GELUID-030: MP3/WAV-decoder ontbreekt. Voer Installeer_ontwikkelomgeving.bat uit."
        ) from oorspronkelijke_fout

    # MP4-audio wordt door FFmpeg gelezen. De MP4-video zelf blijft intact
    # en wordt later zonder geluid door de webbrowser weergegeven.
    if gekozen_pad.suffix.casefold() == '.mp4':
        from app.audio.mp4_verwerken import lees_een_mp4_fragment_als_stereo_float32
        samples, bronduur = lees_een_mp4_fragment_als_stereo_float32(
            gekozen_pad, startpunt, maximale_duur_seconden
        )
        samplefrequentie = SAMPLEFREQUENTIE_VAN_DE_UITVOER
        kanalen = 2
        beginframe = round(startpunt * samplefrequentie)
        totale_frames = round(bronduur * samplefrequentie)
        aantal_te_lezen_frames = len(samples)
    else:
        samples, bronduur, samplefrequentie, kanalen, beginframe, totale_frames, aantal_te_lezen_frames = (
            _lees_mp3_wav_uit_bestand(gekozen_pad, startpunt, maximale_duur_seconden, geluidsdecoder)
        )

    if len(samples) == 0 or not np.all(np.isfinite(samples)):
        raise GeluidsbestandOngeldigFout(
            "GELUID-035: decoder leverde lege of ongeldige audiosamples."
        )
    if kanalen == 1:
        samples = np.repeat(samples, AANTAL_UITVOERKANALEN, axis=1)

    # SoXR voorkomt kwaliteitsvermindering bij bijvoorbeeld 44,1 kHz op 48 kHz.
    try:
        if samplefrequentie != SAMPLEFREQUENTIE_VAN_DE_UITVOER:
            samples = audioconversie.resample(samples, samplefrequentie, SAMPLEFREQUENTIE_VAN_DE_UITVOER, quality="HQ")
    except (ValueError, RuntimeError) as oorspronkelijke_fout:
        raise GeluidsbestandOngeldigFout(
            "GELUID-036: de samplefrequentie kon niet veilig worden omgerekend."
        ) from oorspronkelijke_fout

    # Korte fades voorkomen een tik bij begin en einde van fragmenten.
    samples = np.ascontiguousarray(samples, dtype=np.float32)
    fadeframes = min(240, len(samples) // 2)
    if fadeframes:
        stijgen = np.linspace(0.0, 1.0, fadeframes, dtype=np.float32)
        samples[:fadeframes] *= stijgen[:, None]
        samples[-fadeframes:] *= stijgen[::-1, None]

    # Eerst het eigen volume toepassen en eventuele samplepieken beschermen.
    # Daarna pas normaliseren: anders kan bijvoorbeeld een fragment op 200%
    # de berekende correctie direct weer ongedaan maken.
    # Bij stand Uit is de uitgaande audio byte-voor-byte gelijk aan Beta 4.
    versterk_samples_zonder_digitaal_te_oversturen(samples, volume)
    normalisatiefactor = normaliseer_fragment_in_geheugen(samples, normalisatiestand) if volume > 0 else 1.0
    uitvoer = samples.astype("<f4", copy=False).tobytes()
    return VoorbereidGeluidsfragment(
        naam_van_het_geluid=gekozen_pad.stem,
        bestandspad=gekozen_pad,
        vingerafdruk_van_audio=hashlib.sha256(uitvoer).hexdigest(),
        ruwe_float32_stereo_audio=uitvoer,
        aantal_frames=len(samples),
        oorspronkelijke_samplefrequentie=samplefrequentie,
        oorspronkelijke_aantal_kanalen=kanalen,
        ingesteld_volume=volume,
        fragment_begint_bij_seconden=startpunt,
        bronduur_in_seconden=bronduur,
        fragment_ingekort=beginframe + aantal_te_lezen_frames < totale_frames,
        normalisatiestand=normalisatiestand,
        normalisatiefactor=normalisatiefactor,
    )


def _lees_mp3_wav_uit_bestand(gekozen_pad, startpunt, maximale_duur_seconden, geluidsdecoder):
    """Houd het uitlezen van MP3/WAV los van MP4, zodat beide routes testbaar blijven."""
    try:
        with geluidsdecoder.SoundFile(str(gekozen_pad), mode="r") as bron:
            samplefrequentie = bron.samplerate
            kanalen = bron.channels
            totale_frames = bron.frames
            if kanalen not in (1, 2):
                raise GeluidsbestandOngeldigFout(
                    f"GELUID-031: alleen mono en stereo worden ondersteund, ontvangen {kanalen}."
                )
            if not 8_000 <= samplefrequentie <= 192_000 or totale_frames <= 0:
                raise GeluidsbestandOngeldigFout(
                    "GELUID-032: geen geldige samplefrequentie of geen audiosamples."
                )
            bronduur = totale_frames / samplefrequentie
            beginframe = round(startpunt * samplefrequentie)
            if beginframe >= totale_frames:
                raise GeluidsbestandOngeldigFout(
                    f"GELUID-033: startpunt {startpunt:.1f} s ligt na het einde van het nummer "
                    f"({bronduur:.1f} s)."
                )
            # Nooit het hele nummer in RAM openen. Dat zou bij lange tracks
            # tot honderden megabytes geheugengebruik tijdens het gamen leiden.
            maximaal_aantal_frames = math.ceil(maximale_duur_seconden * samplefrequentie)
            aantal_te_lezen_frames = min(totale_frames - beginframe, maximaal_aantal_frames)
            bron.seek(beginframe)
            samples = bron.read(aantal_te_lezen_frames, dtype="float32", always_2d=True)
    except (OSError, RuntimeError, ValueError) as oorspronkelijke_fout:
        if isinstance(oorspronkelijke_fout, GeluidsbestandOngeldigFout):
            raise
        raise GeluidsbestandOngeldigFout(
            f"GELUID-034: het geluid '{gekozen_pad.name}' kon niet worden gedecodeerd. "
            "Controleer of het MP3- of WAV-bestand geldig is."
        ) from oorspronkelijke_fout

    return samples, bronduur, samplefrequentie, kanalen, beginframe, totale_frames, aantal_te_lezen_frames
