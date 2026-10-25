"""Bewaar instelbare, expliciet ingeschakelde globale Windows-sneltoetsen.

Geen keylogger: alleen vooraf geregistreerde combinaties kunnen een actie
oproepen. Gebruikers kunnen de sneltoetsen volledig uitschakelen.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
import re

from app.desktop.een_actieve_instantie import geef_map_voor_desktopinstellingen

MAXIMAAL_SNELTOETSEN = 16
TOEGESTANE_COMBINATIE = re.compile(r'^(?:CTRL\+ALT|CTRL\+SHIFT|CTRL\+ALT\+SHIFT)\+(?:[0-9]|F(?:[1-9]|1[0-9]|2[0-4]))$')
TOEGESTANE_ACTIES = {f'favoriet_{nummer}' for nummer in range(1, 16)} | {'stop'}


class OngeldigeSneltoetsinstelling(ValueError):
    """De wijziging is geweigerd zonder de bestaande instellingen te wissen."""


def geef_standaard_sneltoetsen() -> dict:
    # Standaard UIT: de app pakt geen toetsen van Discord, Steam of games af
    # zolang de gebruiker dit niet zelf inschakelt.
    sneltoetsen = {f'favoriet_{nummer}': f'CTRL+ALT+{nummer}' for nummer in range(1, 10)}
    sneltoetsen['stop'] = 'CTRL+ALT+0'
    return {'ingeschakeld': False, 'combinaties': sneltoetsen}


def controleer_sneltoetsinstellingen(gegevens: object) -> dict:
    if not isinstance(gegevens, dict):
        raise OngeldigeSneltoetsinstelling('HOTKEY-001: instellingen moeten een object zijn.')
    if type(gegevens.get('ingeschakeld')) is not bool:
        raise OngeldigeSneltoetsinstelling('HOTKEY-002: ingeschakeld moet true of false zijn.')
    combinaties = gegevens.get('combinaties')
    if not isinstance(combinaties, dict) or len(combinaties) > MAXIMAAL_SNELTOETSEN:
        raise OngeldigeSneltoetsinstelling('HOTKEY-003: geef hoogstens 16 acties op.')
    if any(naam not in TOEGESTANE_ACTIES or not isinstance(naam, str) for naam in combinaties):
        raise OngeldigeSneltoetsinstelling('HOTKEY-004: een onbekende actie is opgegeven.')
    gebruikt = set()
    gezuiverde_combinaties = {}
    for actie, sneltoets in combinaties.items():
        if not isinstance(sneltoets, str) or len(sneltoets) > 40:
            raise OngeldigeSneltoetsinstelling('HOTKEY-005: sneltoets heeft verkeerd type of lengte.')
        sneltoets = sneltoets.upper().replace(' ', '')
        if not TOEGESTANE_COMBINATIE.fullmatch(sneltoets):
            raise OngeldigeSneltoetsinstelling(f'HOTKEY-006: {actie} heeft een niet toegestane combinatie.')
        if sneltoets in gebruikt:
            raise OngeldigeSneltoetsinstelling('HOTKEY-007: twee acties gebruiken dezelfde sneltoets.')
        gebruikt.add(sneltoets)
        gezuiverde_combinaties[actie] = sneltoets
    return {'ingeschakeld': gegevens['ingeschakeld'], 'combinaties': gezuiverde_combinaties}


class OpslagVanSneltoetsinstellingen:
    def __init__(self, opslagpad: Path | None = None):
        map_met_instellingen = geef_map_voor_desktopinstellingen()
        self.opslagpad = Path(opslagpad) if opslagpad is not None else map_met_instellingen / 'sneltoetsen.json'

    def lees_instellingen(self) -> dict:
        if not self.opslagpad.exists():
            return geef_standaard_sneltoetsen()
        try:
            return controleer_sneltoetsinstellingen(json.loads(self.opslagpad.read_text(encoding='utf-8')))
        except (OSError, ValueError, TypeError) as fout:
            raise OngeldigeSneltoetsinstelling('HOTKEY-008: bewaarde sneltoetsen zijn ongeldig; bestand wordt niet overschreven.') from fout

    def bewaar_instellingen(self, gegevens: object) -> dict:
        gecontroleerd = controleer_sneltoetsinstellingen(gegevens)
        self.opslagpad.parent.mkdir(parents=True, exist_ok=True)
        tijdelijk = self.opslagpad.with_suffix('.tmp')
        tijdelijk.write_text(json.dumps(gecontroleerd, ensure_ascii=False, indent=2), encoding='utf-8')
        os.replace(tijdelijk, self.opslagpad)
        return gecontroleerd
