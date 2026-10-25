"""Bewaar optionele beschrijving, gesproken tekst en zoekwoorden per geluid.

De tabel wordt toegevoegd aan de bestaande bibliotheek. Eerdere geluiden
behouden hun naam, bestandspad, favorieten en afspeelinstellingen.
"""
from __future__ import annotations

from contextlib import closing
from dataclasses import dataclass
from pathlib import Path
import sqlite3


class OngeldigeGeluidsinformatie(ValueError):
    """Geldige, herkenbare meldingen voor foutieve velden."""


@dataclass(frozen=True)
class ExtraGeluidsinformatie:
    beschrijving: str = ''
    gesproken_tekst: str = ''
    zoekwoorden: str = ''


def controleer_aanvullende_informatie(beschrijving: str, gesproken_tekst: str, zoekwoorden: str) -> ExtraGeluidsinformatie:
    """Valideer tekst om te voorkomen dat exports en de webpagina onbeheersbaar groot worden."""
    grenzen = ((beschrijving, 'beschrijving', 2000),
               (gesproken_tekst, 'gesproken_tekst', 8000),
               (zoekwoorden, 'zoekwoorden', 500))
    for waarde, naam, limiet in grenzen:
        if not isinstance(waarde, str) or len(waarde) > limiet or '\x00' in waarde:
            raise OngeldigeGeluidsinformatie(
                f'INFO-001: {naam} moet tekst van maximaal {limiet} tekens zijn zonder null-tekens.'
            )
    return ExtraGeluidsinformatie(beschrijving.strip(), gesproken_tekst.strip(), zoekwoorden.strip())


class BeheerVanExtraGeluidsinformatie:
    def __init__(self, databasepad: Path):
        self.databasepad = Path(databasepad)
        with self._open_database() as database:
            with database:
                database.execute('''CREATE TABLE IF NOT EXISTS extra_geluidsinformatie (
                    geluid_id TEXT PRIMARY KEY REFERENCES geluiden(geluid_id) ON DELETE CASCADE,
                    beschrijving TEXT NOT NULL DEFAULT '',
                    gesproken_tekst TEXT NOT NULL DEFAULT '',
                    zoekwoorden TEXT NOT NULL DEFAULT ''
                )''')

    def _open_database(self):
        database = sqlite3.connect(self.databasepad, timeout=10)
        database.execute('PRAGMA foreign_keys=ON')
        return closing(database)

    def geef_alle_informatie(self) -> dict[str, ExtraGeluidsinformatie]:
        with self._open_database() as database:
            gegevens = database.execute('''SELECT geluid_id, beschrijving, gesproken_tekst, zoekwoorden
                FROM extra_geluidsinformatie''').fetchall()
        return {geluid_id: ExtraGeluidsinformatie(beschrijving, gesproken_tekst, zoekwoorden)
                for geluid_id, beschrijving, gesproken_tekst, zoekwoorden in gegevens}

    def bewaar_informatie(self, geluid_id: str, beschrijving: str, gesproken_tekst: str, zoekwoorden: str) -> None:
        inhoud = controleer_aanvullende_informatie(beschrijving, gesproken_tekst, zoekwoorden)
        with self._open_database() as database:
            with database:
                if database.execute('SELECT 1 FROM geluiden WHERE geluid_id=?', (geluid_id,)).fetchone() is None:
                    raise OngeldigeGeluidsinformatie('INFO-002: geluid bestaat niet meer in de bibliotheek.')
                database.execute('''INSERT INTO extra_geluidsinformatie
                    (geluid_id, beschrijving, gesproken_tekst, zoekwoorden) VALUES (?, ?, ?, ?)
                    ON CONFLICT(geluid_id) DO UPDATE SET
                    beschrijving=excluded.beschrijving,
                    gesproken_tekst=excluded.gesproken_tekst,
                    zoekwoorden=excluded.zoekwoorden''',
                    (geluid_id, inhoud.beschrijving, inhoud.gesproken_tekst, inhoud.zoekwoorden))
