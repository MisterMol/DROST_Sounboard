"""Bewaar precies vijftien favoriete posities en afspeelinstellingen in SQLite.

Een favoriet heeft een eigen positie. De interface kan dus op verschillende
schermgroottes andere kolommen tonen zonder dat de volgorde verandert.
Alle databaseacties hebben een eigen verbinding en draaien buiten PortAudio.
"""

from __future__ import annotations

from contextlib import closing
from dataclasses import dataclass
import math
from pathlib import Path
import sqlite3

from app.audio.geluidenbibliotheek import bepaal_standaardlocatie_van_de_bibliotheek

AANTAL_FAVORIETE_PLEKKEN = 15


class OngeldigeFavorietOfInstelling(ValueError):
    """Geef een herleidbare foutcode voor ongeldige of ontbrekende invoer."""


@dataclass(frozen=True)
class Afspeelinstellingen:
    begint_bij_seconden: float = 0.0
    volume: float = 1.0
    maximale_duur_seconden: float = 120.0
    afbeelding_bestandsnaam: str | None = None
    beeldvoorkeur: str = 'automatisch'


def controleer_favorietplek(plek: int) -> int:
    if type(plek) is not int or not 1 <= plek <= AANTAL_FAVORIETE_PLEKKEN:
        raise OngeldigeFavorietOfInstelling('FAV-001: positie moet een heel getal van 1 tot 15 zijn.')
    return plek


def controleer_afspeelinstellingen(
    begint_bij_seconden: float, volume: float, maximale_duur_seconden: float,
) -> Afspeelinstellingen:
    """Voorkom stille audio en geheugenspikes door null, NaN en extreme waarden."""
    for naam, waarde in (
        ('begint_bij_seconden', begint_bij_seconden),
        ('volume', volume),
        ('maximale_duur_seconden', maximale_duur_seconden),
    ):
        if isinstance(waarde, bool) or not isinstance(waarde, (int, float)) or not math.isfinite(waarde):
            raise OngeldigeFavorietOfInstelling(
                f'FAV-002: {naam} moet een eindig getal zijn, ontvangen {type(waarde).__name__}.'
            )
    if begint_bij_seconden < 0 or begint_bij_seconden > 36000:
        raise OngeldigeFavorietOfInstelling('FAV-003: startpunt moet tussen 0 en 36000 seconden liggen.')
    if not 0 <= volume <= 2:
        raise OngeldigeFavorietOfInstelling('FAV-004: volume moet tussen 0 en 2 liggen (0 tot 200%).')
    if not 0.001 <= maximale_duur_seconden <= 120:
        raise OngeldigeFavorietOfInstelling('FAV-005: een fragment mag maximaal 120 seconden duren.')
    return Afspeelinstellingen(
        float(begint_bij_seconden), float(volume), float(maximale_duur_seconden)
    )


class VasteFavorietenEnInstellingen:
    """Gebruik dezelfde SQLite-database als de bestaande geluidenbibliotheek."""

    def __init__(self, databasepad: Path | None = None):
        self.databasepad = Path(databasepad) if databasepad is not None else bepaal_standaardlocatie_van_de_bibliotheek()
        self.databasepad.parent.mkdir(parents=True, exist_ok=True)
        with self._open_database() as database:
            with database:
                database.execute('''CREATE TABLE IF NOT EXISTS favoriete_geluiden (
                    plek INTEGER PRIMARY KEY CHECK (plek BETWEEN 1 AND 15),
                    geluid_id TEXT NOT NULL UNIQUE REFERENCES geluiden(geluid_id) ON DELETE CASCADE
                )''')
                database.execute('''CREATE TABLE IF NOT EXISTS geluidsinstellingen (
                    geluid_id TEXT PRIMARY KEY REFERENCES geluiden(geluid_id) ON DELETE CASCADE,
                    beginpositie REAL NOT NULL DEFAULT 0,
                    volume REAL NOT NULL DEFAULT 1.0,
                    maximale_duur REAL NOT NULL DEFAULT 120,
                    afbeelding TEXT,
                    beeldvoorkeur TEXT NOT NULL DEFAULT 'automatisch'
                )''')
                # Bestaande bibliotheken verliezen geen instellingen. Alleen
                # wanneer de kolom ontbreekt voegen we die eenmalig toe.
                kolommen = {regel[1] for regel in database.execute('PRAGMA table_info(geluidsinstellingen)')}
                if 'beeldvoorkeur' not in kolommen:
                    database.execute("ALTER TABLE geluidsinstellingen ADD COLUMN beeldvoorkeur TEXT NOT NULL DEFAULT 'automatisch'")

    def _open_database(self):
        """SQLite verwijdert gekoppelde favorieten alleen wanneer FK expliciet aan staat."""
        verbinding = sqlite3.connect(self.databasepad, timeout=10)
        verbinding.execute('PRAGMA foreign_keys = ON')
        return closing(verbinding)

    def geef_alle_favorietplekken(self) -> list[str | None]:
        """Geef exact 15 posities terug, ook wanneer de bibliotheek nog leeg is."""
        with self._open_database() as database:
            regels = database.execute('''SELECT f.plek, f.geluid_id
                FROM favoriete_geluiden f INNER JOIN geluiden g ON g.geluid_id = f.geluid_id
                ORDER BY f.plek''').fetchall()
        plekken: list[str | None] = [None] * AANTAL_FAVORIETE_PLEKKEN
        for nummer, geluid_id in regels:
            plekken[nummer - 1] = geluid_id
        return plekken

    def _controleer_of_geluid_bestaat(self, database: sqlite3.Connection, geluid_id: str) -> None:
        if not isinstance(geluid_id, str) or not geluid_id.strip():
            raise OngeldigeFavorietOfInstelling('FAV-006: er is geen geldig geluidsnummer opgegeven.')
        if database.execute('SELECT 1 FROM geluiden WHERE geluid_id = ?', (geluid_id,)).fetchone() is None:
            raise OngeldigeFavorietOfInstelling('FAV-007: dit geluid bestaat niet meer.')

    def zet_een_geluid_op_een_vaste_plek(self, plek: int, geluid_id: str) -> None:
        """Verplaats bestaande favoriet zonder het geluid dubbel in het raster te zetten.

        Wordt een bezette plek overschreven, dan komt het oude geluid terug in
        de vorige plek van het verplaatste item. Nieuwe items vervangen de plek.
        """
        controleer_favorietplek(plek)
        with self._open_database() as database:
            with database:
                self._controleer_of_geluid_bestaat(database, geluid_id)
                oude_plek_regel = database.execute(
                    'SELECT plek FROM favoriete_geluiden WHERE geluid_id = ?', (geluid_id,)
                ).fetchone()
                huidig_op_doel = database.execute(
                    'SELECT geluid_id FROM favoriete_geluiden WHERE plek = ?', (plek,)
                ).fetchone()
                oude_plek = oude_plek_regel[0] if oude_plek_regel else None
                oud_geluid = huidig_op_doel[0] if huidig_op_doel else None
                if oude_plek == plek:
                    return
                database.execute('DELETE FROM favoriete_geluiden WHERE plek = ? OR geluid_id = ?', (plek, geluid_id))
                database.execute(
                    'INSERT INTO favoriete_geluiden (plek, geluid_id) VALUES (?, ?)', (plek, geluid_id)
                )
                if oude_plek is not None and oud_geluid is not None:
                    database.execute(
                        'INSERT INTO favoriete_geluiden (plek, geluid_id) VALUES (?, ?)', (oude_plek, oud_geluid)
                    )

    def wissel_twee_favorietplekken(self, eerste_plek: int, tweede_plek: int) -> None:
        """Behoud de unieke geluidsnummers door binnen één transactie te wisselen."""
        controleer_favorietplek(eerste_plek)
        controleer_favorietplek(tweede_plek)
        if eerste_plek == tweede_plek:
            return
        with self._open_database() as database:
            with database:
                gevonden = dict(database.execute(
                    'SELECT plek, geluid_id FROM favoriete_geluiden WHERE plek IN (?, ?)',
                    (eerste_plek, tweede_plek),
                ).fetchall())
                database.execute('DELETE FROM favoriete_geluiden WHERE plek IN (?, ?)', (eerste_plek, tweede_plek))
                for bestemming, bron in ((eerste_plek, tweede_plek), (tweede_plek, eerste_plek)):
                    if bron in gevonden:
                        database.execute(
                            'INSERT INTO favoriete_geluiden (plek, geluid_id) VALUES (?, ?)',
                            (bestemming, gevonden[bron]),
                        )

    def maak_een_favorietplek_leeg(self, plek: int) -> None:
        controleer_favorietplek(plek)
        with self._open_database() as database:
            with database:
                database.execute('DELETE FROM favoriete_geluiden WHERE plek = ?', (plek,))

    def geef_instellingen_van_geluid(self, geluid_id: str) -> Afspeelinstellingen:
        if not isinstance(geluid_id, str) or not geluid_id:
            raise OngeldigeFavorietOfInstelling('FAV-008: geluidsnummer ontbreekt.')
        with self._open_database() as database:
            gevonden = database.execute(
                'SELECT beginpositie, volume, maximale_duur, afbeelding, beeldvoorkeur FROM geluidsinstellingen WHERE geluid_id = ?',
                (geluid_id,),
            ).fetchone()
        if gevonden is None:
            return Afspeelinstellingen()
        return Afspeelinstellingen(*gevonden)

    def bewaar_afspeelinstellingen(
        self, geluid_id: str, begin: float, volume: float, duur: float, beeldvoorkeur: str = 'automatisch',
    ) -> None:
        instellingen = controleer_afspeelinstellingen(begin, volume, duur)
        if beeldvoorkeur not in ('automatisch', 'video', 'afbeelding'):
            raise OngeldigeFavorietOfInstelling('FAV-010: kies automatisch, video of afbeelding.')
        with self._open_database() as database:
            with database:
                self._controleer_of_geluid_bestaat(database, geluid_id)
                database.execute('''INSERT INTO geluidsinstellingen
                    (geluid_id, beginpositie, volume, maximale_duur, beeldvoorkeur)
                    VALUES (?, ?, ?, ?, ?)
                    ON CONFLICT(geluid_id) DO UPDATE SET
                    beginpositie = excluded.beginpositie,
                    volume = excluded.volume,
                    maximale_duur = excluded.maximale_duur,
                    beeldvoorkeur = excluded.beeldvoorkeur''',
                    (geluid_id, instellingen.begint_bij_seconden,
                     instellingen.volume, instellingen.maximale_duur_seconden, beeldvoorkeur),
                )

    def zet_volumes_van_geluiden_in_een_keer(self, geluidsnummers: list[str], volume: float) -> int:
        """Zet meerdere clips op één volume, zonder hun knipgrenzen te veranderen.

        Alles gaat in één SQLite-transactie. Een ongeldig geluid mag dus
        niet veroorzaken dat een halve selectie wel is aangepast.
        """
        controleer_afspeelinstellingen(0.0, volume, 1.0)
        if (not isinstance(geluidsnummers, list) or not 1 <= len(geluidsnummers) <= 250
                or any(not isinstance(nummer, str) or not nummer for nummer in geluidsnummers)):
            raise OngeldigeFavorietOfInstelling('FAV-011: kies 1 tot 250 geldige geluiden.')
        unieke_nummers = list(dict.fromkeys(geluidsnummers))
        with self._open_database() as database:
            with database:
                for nummer in unieke_nummers:
                    self._controleer_of_geluid_bestaat(database, nummer)
                for nummer in unieke_nummers:
                    database.execute("""INSERT INTO geluidsinstellingen (geluid_id, volume)
                        VALUES (?, ?) ON CONFLICT(geluid_id) DO UPDATE SET volume = excluded.volume""",
                        (nummer, volume))
        return len(unieke_nummers)

    def bewaar_afbeelding_voor_geluid(self, geluid_id: str, bestandsnaam: str) -> None:
        if not isinstance(bestandsnaam, str) or not bestandsnaam:
            raise OngeldigeFavorietOfInstelling('FAV-009: afbeeldingsnaam ontbreekt.')
        with self._open_database() as database:
            with database:
                self._controleer_of_geluid_bestaat(database, geluid_id)
                database.execute('''INSERT INTO geluidsinstellingen (geluid_id, afbeelding)
                    VALUES (?, ?) ON CONFLICT(geluid_id)
                    DO UPDATE SET afbeelding = excluded.afbeelding''', (geluid_id, bestandsnaam))

    def verwijder_referenties_naar_geluid(self, geluid_id: str) -> None:
        """Ook oude bibliotheekclients gebruiken niet altijd PRAGMA foreign_keys=ON."""
        with self._open_database() as database:
            with database:
                database.execute('DELETE FROM favoriete_geluiden WHERE geluid_id = ?', (geluid_id,))
                database.execute('DELETE FROM geluidsinstellingen WHERE geluid_id = ?', (geluid_id,))
