"""Maak eigen verzamelingen geluiden met namen zoals 'South Park'.

Een geluid kan in meerdere groepen staan. Het geluid blijft ook in de algemene
bibliotheek beschikbaar. Het verwijderen van een groep raakt nooit de media
of de vaste favorieten. Alle wijzigingen gebeuren binnen SQLite-transacties.
"""
from __future__ import annotations

from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path
import sqlite3
from uuid import UUID, uuid4

from app.audio.geluidenbibliotheek import bepaal_standaardlocatie_van_de_bibliotheek


class GroepsinstellingOngeldig(ValueError):
    """Een invoerfout met Nederlandse uitleg en foutcode."""


def controleer_groepsnaam(naam: str) -> str:
    if not isinstance(naam, str) or not 1 <= len(naam.strip()) <= 60 or any(c in naam for c in '\n\r\0'):
        raise GroepsinstellingOngeldig('GROEP-001: geef een naam van 1 tot 60 tekens zonder regeleinden.')
    return naam.strip()


def controleer_groepsnummer(groep_id: str) -> str:
    try:
        return str(UUID(groep_id))
    except (TypeError, AttributeError, ValueError) as fout:
        raise GroepsinstellingOngeldig('GROEP-002: ongeldig groepsnummer.') from fout


class PersoonlijkeGeluidsgroepen:
    """Beheer groepsnamen en de koppeling met bestaande geluidsnummers."""

    def __init__(self, databasepad: Path | None = None):
        self.databasepad = Path(databasepad or bepaal_standaardlocatie_van_de_bibliotheek())
        self.databasepad.parent.mkdir(parents=True, exist_ok=True)
        with self._open_database() as database:
            with database:
                database.execute('''CREATE TABLE IF NOT EXISTS geluidsgroepen (
                    groep_id TEXT PRIMARY KEY,
                    naam TEXT NOT NULL UNIQUE COLLATE NOCASE,
                    toegevoegd_op_utc TEXT NOT NULL
                )''')
                database.execute('''CREATE TABLE IF NOT EXISTS geluiden_in_groep (
                    groep_id TEXT NOT NULL REFERENCES geluidsgroepen(groep_id) ON DELETE CASCADE,
                    geluid_id TEXT NOT NULL REFERENCES geluiden(geluid_id) ON DELETE CASCADE,
                    PRIMARY KEY (groep_id, geluid_id)
                )''')
                database.execute('CREATE INDEX IF NOT EXISTS index_geluidsgroep_voor_geluid ON geluiden_in_groep(geluid_id)')

    def _open_database(self):
        verbinding = sqlite3.connect(self.databasepad, timeout=10)
        verbinding.execute('PRAGMA foreign_keys = ON')
        return closing(verbinding)

    def geef_alle_groepen(self) -> list[dict]:
        with self._open_database() as database:
            regels = database.execute('''SELECT g.groep_id, g.naam, COUNT(k.geluid_id)
                FROM geluidsgroepen AS g LEFT JOIN geluiden_in_groep AS k ON g.groep_id=k.groep_id
                GROUP BY g.groep_id ORDER BY g.naam COLLATE NOCASE''').fetchall()
        return [{'id': groep_id, 'naam': naam, 'aantal_geluiden': aantal} for groep_id, naam, aantal in regels]

    def geef_groepsnummers_per_geluid(self) -> dict[str, list[str]]:
        met_groepen: dict[str, list[str]] = {}
        with self._open_database() as database:
            regels = database.execute('SELECT geluid_id, groep_id FROM geluiden_in_groep ORDER BY groep_id').fetchall()
        for geluid_id, groep_id in regels:
            met_groepen.setdefault(geluid_id, []).append(groep_id)
        return met_groepen

    def maak_groep(self, naam: str) -> str:
        naam = controleer_groepsnaam(naam)
        nieuw_id = str(uuid4())
        try:
            with self._open_database() as database:
                with database:
                    database.execute('INSERT INTO geluidsgroepen VALUES (?, ?, ?)',
                                     (nieuw_id, naam, datetime.now(timezone.utc).isoformat()))
        except sqlite3.IntegrityError as fout:
            raise GroepsinstellingOngeldig('GROEP-003: er bestaat al een groep met deze naam.') from fout
        return nieuw_id

    def hernoem_groep(self, groep_id: str, naam: str) -> None:
        groep_id, naam = controleer_groepsnummer(groep_id), controleer_groepsnaam(naam)
        try:
            with self._open_database() as database:
                with database:
                    gevonden = database.execute('UPDATE geluidsgroepen SET naam=? WHERE groep_id=?',
                                                (naam, groep_id))
                    if gevonden.rowcount == 0:
                        raise GroepsinstellingOngeldig('GROEP-004: deze groep bestaat niet meer.')
        except sqlite3.IntegrityError as fout:
            raise GroepsinstellingOngeldig('GROEP-003: er bestaat al een groep met deze naam.') from fout

    def verwijder_groep(self, groep_id: str) -> None:
        groep_id = controleer_groepsnummer(groep_id)
        with self._open_database() as database:
            with database:
                verwijderde = database.execute('DELETE FROM geluidsgroepen WHERE groep_id=?', (groep_id,))
                if verwijderde.rowcount == 0:
                    raise GroepsinstellingOngeldig('GROEP-004: deze groep bestaat niet meer.')

    def verander_lidmaatschap(self, groep_id: str, geluid_id: str, toevoegen: bool) -> None:
        groep_id = controleer_groepsnummer(groep_id)
        if not isinstance(geluid_id, str) or not geluid_id:
            raise GroepsinstellingOngeldig('GROEP-005: een geluidsnummer ontbreekt.')
        if type(toevoegen) is not bool:
            raise GroepsinstellingOngeldig('GROEP-006: toevoegen moet true of false zijn.')
        with self._open_database() as database:
            with database:
                if database.execute('SELECT 1 FROM geluidsgroepen WHERE groep_id=?', (groep_id,)).fetchone() is None:
                    raise GroepsinstellingOngeldig('GROEP-004: deze groep bestaat niet meer.')
                if database.execute('SELECT 1 FROM geluiden WHERE geluid_id=?', (geluid_id,)).fetchone() is None:
                    raise GroepsinstellingOngeldig('GROEP-007: dit geluid bestaat niet (meer).')
                if toevoegen:
                    database.execute('INSERT OR IGNORE INTO geluiden_in_groep VALUES (?, ?)', (groep_id, geluid_id))
                else:
                    database.execute('DELETE FROM geluiden_in_groep WHERE groep_id=? AND geluid_id=?',
                                     (groep_id, geluid_id))

    def verwijder_koppelingen_naar_geluid(self, geluid_id: str) -> None:
        """Verwijder expliciet koppelingen voor oude code met foreign_keys uit."""
        with self._open_database() as database:
            with database:
                database.execute('DELETE FROM geluiden_in_groep WHERE geluid_id=?', (geluid_id,))

    def bewaar_groepen_voor_geluid(self, geluid_id: str, groepsnummers: list[str]) -> None:
        """Vervang alle vinkjes in één transactie, zodat half opslaan onmogelijk is."""
        if not isinstance(geluid_id, str) or not geluid_id:
            raise GroepsinstellingOngeldig('GROEP-005: een geluidsnummer ontbreekt.')
        if (not isinstance(groepsnummers, list) or len(groepsnummers) > 100
                or any(not isinstance(nummer, str) for nummer in groepsnummers)):
            raise GroepsinstellingOngeldig('GROEP-008: geef maximaal 100 groepsnummers als lijst.')
        gecontroleerd = {controleer_groepsnummer(nummer) for nummer in groepsnummers}
        with self._open_database() as database:
            with database:
                if database.execute('SELECT 1 FROM geluiden WHERE geluid_id=?', (geluid_id,)).fetchone() is None:
                    raise GroepsinstellingOngeldig('GROEP-007: dit geluid bestaat niet (meer).')
                for nummer in gecontroleerd:
                    if database.execute('SELECT 1 FROM geluidsgroepen WHERE groep_id=?', (nummer,)).fetchone() is None:
                        raise GroepsinstellingOngeldig('GROEP-004: een geselecteerde groep bestaat niet meer.')
                database.execute('DELETE FROM geluiden_in_groep WHERE geluid_id=?', (geluid_id,))
                for nummer in gecontroleerd:
                    database.execute('INSERT INTO geluiden_in_groep VALUES (?, ?)', (nummer, geluid_id))

    def voeg_meerdere_geluiden_toe_aan_groep(self, groep_id: str, geluidsnummers: list[str]) -> int:
        """Voeg een selectie atomair toe. Ongeldig geluidsnummer betekent géén wijzigingen."""
        groep_id = controleer_groepsnummer(groep_id)
        if (not isinstance(geluidsnummers, list) or not 1 <= len(geluidsnummers) <= 250
                or any(not isinstance(nummer, str) for nummer in geluidsnummers)):
            raise GroepsinstellingOngeldig('GROEP-009: selecteer tussen 1 en 250 geldige geluiden.')
        uniek = list(dict.fromkeys(geluidsnummers))
        with self._open_database() as database:
            with database:
                if database.execute('SELECT 1 FROM geluidsgroepen WHERE groep_id=?', (groep_id,)).fetchone() is None:
                    raise GroepsinstellingOngeldig('GROEP-004: deze groep bestaat niet meer.')
                placeholders = ','.join('?' for _ in uniek)
                gevonden = database.execute(f'SELECT COUNT(*) FROM geluiden WHERE geluid_id IN ({placeholders})', uniek).fetchone()[0]
                if gevonden != len(uniek):
                    raise GroepsinstellingOngeldig('GROEP-007: één of meer geselecteerde geluiden ontbreken.')
                database.executemany('INSERT OR IGNORE INTO geluiden_in_groep VALUES (?, ?)',
                                     [(groep_id, nummer) for nummer in uniek])
        return len(uniek)
