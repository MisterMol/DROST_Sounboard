"""Aparte instellingen voor dashboardindeling en aanvullende opmaak in SQLite.

Bestaande thema's, favorieten en geluiden worden niet gewijzigd.
"""
from __future__ import annotations
from contextlib import closing
from pathlib import Path
import sqlite3

INDELINGEN = frozenset({'klassiek', 'bibliotheek', 'favorieten'})
TEKSTGROOTTES = frozenset({'normaal', 'groot'})
KAARTHOEKEN = frozenset({'afgerond', 'strak'})
STANDAARD = {'indeling': 'klassiek', 'tekstgrootte': 'normaal', 'hoeken': 'afgerond'}

class Dashboardvoorkeuren:
    def __init__(self, databasepad: str | Path):
        self.databasepad = Path(databasepad)

    @staticmethod
    def _maak_tabel(database):
        database.execute("""CREATE TABLE IF NOT EXISTS dashboard_voorkeuren (
            sleutel INTEGER PRIMARY KEY CHECK(sleutel = 1),
            indeling TEXT NOT NULL CHECK(indeling IN ('klassiek','bibliotheek','favorieten')),
            tekstgrootte TEXT NOT NULL CHECK(tekstgrootte IN ('normaal','groot')),
            hoeken TEXT NOT NULL CHECK(hoeken IN ('afgerond','strak'))
        )""")

    @staticmethod
    def _lees(database):
        regel = database.execute(
            'SELECT indeling, tekstgrootte, hoeken FROM dashboard_voorkeuren WHERE sleutel=1'
        ).fetchone()
        return dict(zip(STANDAARD, regel)) if regel else dict(STANDAARD)

    def geef(self) -> dict[str, str]:
        with closing(sqlite3.connect(self.databasepad, timeout=5)) as database:
            self._maak_tabel(database)
            return self._lees(database)

    def bewaar(self, gegevens: dict) -> dict[str, str]:
        if type(gegevens) is not dict or not gegevens or not set(gegevens) <= set(STANDAARD):
            raise ValueError('Ongeldige dashboardinstellingen.')
        for sleutel, toegestaan, melding in (
            ('indeling', INDELINGEN, 'Kies een bestaande dashboardindeling.'),
            ('tekstgrootte', TEKSTGROOTTES, 'Kies een bestaande tekstgrootte.'),
            ('hoeken', KAARTHOEKEN, 'Kies een bestaande kaartvorm.'),
        ):
            if sleutel in gegevens and (type(gegevens[sleutel]) is not str or gegevens[sleutel] not in toegestaan):
                raise ValueError(melding)
        with closing(sqlite3.connect(self.databasepad, timeout=5)) as database:
            with database:
                self._maak_tabel(database)
                voorkeur = self._lees(database)
                voorkeur.update(gegevens)
                database.execute("""INSERT INTO dashboard_voorkeuren
                    (sleutel, indeling, tekstgrootte, hoeken) VALUES (1, ?, ?, ?)
                    ON CONFLICT(sleutel) DO UPDATE SET
                        indeling=excluded.indeling,
                        tekstgrootte=excluded.tekstgrootte,
                        hoeken=excluded.hoeken""",
                    (voorkeur['indeling'], voorkeur['tekstgrootte'], voorkeur['hoeken']))
                return voorkeur
