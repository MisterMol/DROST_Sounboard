"""Maak uitsluitend ontbrekende, reproduceerbare Windows-releasebestanden.

De bestanden komen uit het bestaande, vastgelegde DrostSoundboard-logo.
Overschrijf een lokaal al aanwezig installericoon of splashscherm niet.
"""
from __future__ import annotations

from pathlib import Path
import shutil

from PIL import Image

from hulpmiddelen.maak_logo_bestanden import (
    RELEASE_MAP, WEB_MAP, teken_logo, maak_installatieafbeelding,
)


def bereid_releaseassets_voor() -> tuple[Path, Path]:
    favicon = WEB_MAP / "favicon.ico"
    if not favicon.is_file():
        raise FileNotFoundError("Het originele favicon.ico ontbreekt.")
    RELEASE_MAP.mkdir(parents=True, exist_ok=True)

    ico = RELEASE_MAP / "DrostSoundboard.ico"
    if not ico.exists():
        shutil.copyfile(favicon, ico)
    if ico.read_bytes() != favicon.read_bytes():
        raise ValueError("Het Windows-icoon verschilt van het bronfavicon.")
    with Image.open(ico) as afbeelding:
        if not {(16, 16), (32, 32), (48, 48), (64, 64), (256, 256)} <= set(afbeelding.info["sizes"]):
            raise ValueError("Het icoon mist benodigde Windows-resoluties.")

    splash = RELEASE_MAP / "DrostSoundboard_Installatie.png"
    if not splash.exists():
        maak_installatieafbeelding(teken_logo(80)).save(
            splash, format="PNG", optimize=True,
        )
    with Image.open(splash) as afbeelding:
        afbeelding.verify()
    return ico, splash


if __name__ == "__main__":
    for pad in bereid_releaseassets_voor():
        print("Windows-releasebestand gecontroleerd:", pad)
