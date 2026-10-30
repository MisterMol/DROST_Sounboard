"""Veilig een lege bibliotheek beginnen met een automatische herstelkopie.

Verwijdert uitsluitend bibliotheekregistraties. De oorspronkelijke media,
profielinstellingen, sneltoetsen en scherminstellingen blijven behouden.
"""
from __future__ import annotations

from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path
import sqlite3
from uuid import uuid4


class BibliotheekLeegmakenFout(ValueError):
    """Melding voor een weigering van een destructieve bibliotheekactie."""


# Alleen tabellen die specifiek bij een geluidsbibliotheek horen.
# Nooit gebruikersprofielen, normalisatie, stemvervorming, thema's of sneltoetsen.
BIBLIOTHEEK_TABELLEN = (
    'geluiden_in_groep', 'geluidsgroep_ouders', 'geluidsgroepen',
    'favoriete_geluiden', 'geluidsinstellingen', 'extra_geluidsinformatie',
    'recent_afgespeeld', 'recente_groepen', 'afspeelstatistieken', 'geluiden',
)


def begin_met_lege_bibliotheek(databasepad: Path, bevestiging: str) -> dict:
    """Back-up SQLite-consistent, wis gerichte tabellen in één transactie."""
    if bevestiging != 'BEVESTIG':
        raise BibliotheekLeegmakenFout('BIB-080: typ BEVESTIG om je bibliotheek leeg te maken.')
    databasepad = Path(databasepad)
    if not databasepad.is_file():
        raise BibliotheekLeegmakenFout('BIB-081: de bibliotheekdatabase bestaat niet.')
    reservemap = databasepad.parent / 'bibliotheek-reservekopien'
    reservemap.mkdir(parents=True, exist_ok=True)
    naam = f'bibliotheek_{datetime.now(timezone.utc):%Y%m%d_%H%M%S}_{uuid4().hex[:8]}.sqlite3'
    backuppad = reservemap / naam
    try:
        with closing(sqlite3.connect(databasepad, timeout=15)) as database:
            database.execute('PRAGMA foreign_keys=ON')
            with closing(sqlite3.connect(backuppad, timeout=15)) as backup:
                database.backup(backup)
            # Een onafgemaakte of mislukte back-up mag nooit tot wissen leiden.
            with closing(sqlite3.connect(backuppad, timeout=15)) as controle:
                if controle.execute('PRAGMA quick_check').fetchone()[0] != 'ok':
                    raise BibliotheekLeegmakenFout('BIB-082: de back-up is ongeldig. Er is niets gewist.')
            database.execute('BEGIN IMMEDIATE')
            try:
                aanwezig = {r[0] for r in database.execute("SELECT name FROM sqlite_master WHERE type='table'")}
                aantal_geluiden = database.execute('SELECT COUNT(*) FROM geluiden').fetchone()[0]
                aantal_mappen = database.execute('SELECT COUNT(*) FROM geluidsgroepen').fetchone()[0] if 'geluidsgroepen' in aanwezig else 0
                for tabel in BIBLIOTHEEK_TABELLEN:
                    if tabel in aanwezig:
                        database.execute(f'DELETE FROM {tabel}')
                database.commit()
            except Exception:
                database.rollback()
                raise
    except (OSError, sqlite3.Error) as fout:
        raise BibliotheekLeegmakenFout('BIB-083: back-up of bibliotheekreset mislukt. De gegevens zijn niet bewust gewist.') from fout
    return {
        'geluiden_verwijderd': aantal_geluiden,
        'mappen_verwijderd': aantal_mappen,
        'reservekopie': str(backuppad),
        'bronbestanden_bewaard': True,
    }
