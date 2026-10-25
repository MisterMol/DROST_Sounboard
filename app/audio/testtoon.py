"""Maak het testsignaal voor de virtuele kabel zonder audiobestanden te lezen.

Een zelfgemaakt testsignaal is voor deze eerste controle voorspelbaar en
werkt ook op een nieuwe Windows-installatie zonder geluidsbibliotheek.
"""

from __future__ import annotations

from array import array
from dataclasses import dataclass
from math import pi, sin


@dataclass(frozen=True)
class InstellingenVoorTesttoon:
    """Bewaar de eigenschappen van de toon die we aan beide kanten verwachten."""

    samplefrequentie: int = 48_000
    aantal_kanalen: int = 2
    toonhoogte_in_hertz: int = 440
    duur_in_seconden: float = 1.8
    volume: float = 0.12
    duur_van_fade_in_en_out: float = 0.025


def controleer_testtooninstellingen(instellingen: InstellingenVoorTesttoon) -> None:
    """Weiger ongeldige instellingen voordat we ook maar één stream openen."""
    if type(instellingen.samplefrequentie) is not int or instellingen.samplefrequentie <= 0:
        raise ValueError("TOON-001: samplefrequentie moet een positief geheel getal zijn.")
    if instellingen.aantal_kanalen != 2:
        raise ValueError("TOON-002: deze kabeltest vereist precies twee uitvoerkanalen.")
    if not 0 < instellingen.toonhoogte_in_hertz < instellingen.samplefrequentie / 2:
        raise ValueError("TOON-003: toonhoogte past niet bij de samplefrequentie.")
    if not 0 < instellingen.duur_in_seconden <= 5:
        raise ValueError("TOON-004: de testtoon moet tussen 0 en 5 seconden duren.")
    if not 0 < instellingen.volume <= 0.20:
        raise ValueError("TOON-005: het testvolume mag maximaal 20 procent zijn.")
    if not 0 <= instellingen.duur_van_fade_in_en_out < instellingen.duur_in_seconden / 2:
        raise ValueError("TOON-006: de fade is ongeldig of te lang.")


def maak_testtoon_voor_de_virtuele_kabel(instellingen: InstellingenVoorTesttoon) -> bytes:
    """Maak stereo float32-samples, zodat RawOutputStream ze rechtstreeks kan afspelen.

    We laten de toon aan het begin en einde rustig op- en aflopen om
    tikken bij het openen/sluiten van een audiostream te voorkomen.
    """
    controleer_testtooninstellingen(instellingen)
    aantal_frames = round(instellingen.samplefrequentie * instellingen.duur_in_seconden)
    aantal_fade_frames = round(
        instellingen.samplefrequentie * instellingen.duur_van_fade_in_en_out
    )
    stereo_samples = array("f")

    for framenummer in range(aantal_frames):
        sample = instellingen.volume * sin(
            2 * pi * instellingen.toonhoogte_in_hertz * framenummer
            / instellingen.samplefrequentie
        )

        if aantal_fade_frames:
            if framenummer < aantal_fade_frames:
                sample *= framenummer / aantal_fade_frames
            elif framenummer >= aantal_frames - aantal_fade_frames:
                sample *= (aantal_frames - 1 - framenummer) / aantal_fade_frames

        stereo_samples.extend((sample, sample))

    # Windows x64 gebruikt kleine endian-getallen. array('f') is hier een
    # normale buffer met IEEE float32-samples; NumPy is dus niet nodig.
    if stereo_samples.itemsize != 4:
        raise RuntimeError("TOON-007: dit systeem gebruikt geen float32 van vier bytes.")
    return stereo_samples.tobytes()


def verdeel_testtoon_in_kleine_audio_blokken(
    testtoon_als_bytes: bytes,
    aantal_kanalen: int = 2,
    aantal_frames_per_blok: int = 1024,
):
    """Lever telkens een hanteerbare hoeveelheid audio aan de Windows-driver."""
    if aantal_kanalen <= 0 or aantal_frames_per_blok <= 0:
        raise ValueError("TOON-008: kanalen en blokgrootte moeten groter dan nul zijn.")

    aantal_bytes_per_frame = aantal_kanalen * 4
    if len(testtoon_als_bytes) % aantal_bytes_per_frame:
        raise ValueError("TOON-009: onvolledige framegegevens ontvangen.")

    blokgrootte_in_bytes = aantal_frames_per_blok * aantal_bytes_per_frame
    for positie in range(0, len(testtoon_als_bytes), blokgrootte_in_bytes):
        yield testtoon_als_bytes[positie : positie + blokgrootte_in_bytes]
