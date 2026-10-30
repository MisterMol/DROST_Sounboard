"""Genereer alle DrostSoundboard-iconen vanuit een vaste SVG-bron.

Het vectorlogo staat in assets/branding/DrostSoundboard.svg. Het script gebruikt
alleen Pillow en de standaardbibliotheek, dus er is geen externe ontwerpsoftware
nodig op Windows. Alle pictogrammen hebben dezelfde vorm en vijf balken.

Gebruik: python -m hulpmiddelen.maak_logo_bestanden
"""
from __future__ import annotations

from pathlib import Path
from xml.etree import ElementTree
import argparse
import shutil

from PIL import Image, ImageDraw, ImageFont

PROJECT = Path(__file__).resolve().parents[1]
SVG_BRON = PROJECT / 'assets' / 'branding' / 'DrostSoundboard.svg'
WEB_MAP = PROJECT / 'app' / 'webinterface' / 'statisch'
RELEASE_MAP = PROJECT / 'assets' / 'release'
SVG_NS = '{http://www.w3.org/2000/svg}'


def _parse_kleur(waarde: str):
    return tuple(bytes.fromhex(waarde.lstrip('#')))


def teken_logo(grootte: int) -> Image.Image:
    """Teken het SVG-logo met extra resolutie voor scherpe kleine Windowsiconen."""
    if not 16 <= grootte <= 512:
        raise ValueError('Gebruik een gangbare iconresolutie.')
    factor = max(1, 1024 // grootte)
    schaal = grootte * factor / 64
    wortel = ElementTree.parse(SVG_BRON).getroot()
    if wortel.attrib.get('viewBox') != '0 0 64 64':
        raise ValueError('Ongeldige SVG-grootte.')
    afbeelding = Image.new('RGBA', (grootte * factor, grootte * factor), (0, 0, 0, 0))
    pen = ImageDraw.Draw(afbeelding)
    vlakken = list(wortel.iter(SVG_NS + 'rect'))
    if len(vlakken) != 6:
        raise ValueError('Logo moet een achtergrond en vijf geluidsbalken bevatten.')
    for vlak in vlakken:
        x = float(vlak.attrib['x']) * schaal
        y = float(vlak.attrib['y']) * schaal
        breed = float(vlak.attrib['width']) * schaal
        hoog = float(vlak.attrib['height']) * schaal
        radius = float(vlak.attrib.get('rx', 0)) * schaal
        kleur = _parse_kleur(vlak.attrib['fill'])
        rand = vlak.attrib.get('stroke')
        pen.rounded_rectangle((round(x), round(y), round(x + breed), round(y + hoog)),
                              radius=round(radius), fill=(*kleur, 255),
                              outline=(*_parse_kleur(rand), 255) if rand else None,
                              width=max(1, round(float(vlak.attrib.get('stroke-width', 0)) * schaal)) if rand else 1)
    return afbeelding.resize((grootte, grootte), Image.Resampling.LANCZOS)


def _lettertype(punten: int, vet: bool = False):
    # Het font wordt niet verpakt. De gegenereerde afbeelding wel.
    namen = (['C:/Windows/Fonts/seguisb.ttf', 'DejaVuSans-Bold.ttf'] if vet
             else ['C:/Windows/Fonts/segoeui.ttf', 'DejaVuSans.ttf'])
    for naam in namen:
        try:
            return ImageFont.truetype(naam, punten)
        except OSError:
            pass
    return ImageFont.load_default()


def maak_installatieafbeelding(logo: Image.Image) -> Image.Image:
    """Maak een stilstaande installerafbeelding met exact hetzelfde pictogram."""
    img = Image.new('RGB', (600, 300), '#0b1015')
    pen = ImageDraw.Draw(img)
    pen.rounded_rectangle((16, 16, 583, 284), radius=18, outline='#30444c', width=1)
    pen.line((42, 239, 558, 239), fill='#31434a', width=1)
    img.paste(logo, (42, 81), logo)
    pen.text((138, 92), 'Drost', font=_lettertype(31, True), fill='#f0f5f5')
    # Tekstbreedte opvragen zorgt dat 'Soundboard' nooit over Drost heen valt.
    start = 138 + pen.textlength('Drost', font=_lettertype(31, True))
    pen.text((round(start), 92), 'Soundboard', font=_lettertype(31, True), fill='#78d6c5')
    pen.text((139, 150), 'Installeren', font=_lettertype(16), fill='#c8d9de')
    pen.text((42, 256), 'Windows 11  |  Audio en soundboard', font=_lettertype(12), fill='#97adb7')
    return img


def genereer() -> list[Path]:
    """Schrijf webicoon, favicon, tray-PNG, EXE/Setup-ICO en splash naar vaste paden."""
    WEB_MAP.mkdir(parents=True, exist_ok=True)
    RELEASE_MAP.mkdir(parents=True, exist_ok=True)
    logo = teken_logo(256)
    svg = WEB_MAP / 'drost-logo.svg'
    if SVG_BRON.resolve() != svg.resolve():
        shutil.copyfile(SVG_BRON, svg)
    png = WEB_MAP / 'drost-logo.png'
    logo.save(png, format='PNG', optimize=True)
    ico = RELEASE_MAP / 'DrostSoundboard.ico'
    # Pillow maakt de verschillende resoluties uit eenzelfde bronafbeelding.
    logo.save(ico, format='ICO', sizes=[(16, 16), (24, 24), (32, 32), (48, 48),
                                         (64, 64), (128, 128), (256, 256)])
    fav = WEB_MAP / 'favicon.ico'
    shutil.copyfile(ico, fav)
    splash = RELEASE_MAP / 'DrostSoundboard_Installatie.png'
    maak_installatieafbeelding(teken_logo(80)).save(splash, format='PNG', optimize=True)
    return [svg, png, ico, fav, splash]


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.parse_args()
    for bestand in genereer():
        print('Gemaakt:', bestand.relative_to(PROJECT))
