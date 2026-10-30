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
import re

from app.audio.geluidenbibliotheek import bepaal_standaardlocatie_van_de_bibliotheek
from app.audio.geluidsnormalisatie import controleer_normalisatiestand
from app.audio.stemvervorming import (controleer_stemprofiel, controleer_stemintensiteit,
                                     STANDAARD_INTENSITEITEN)
from app.audio.stemparameters import standaard_parameters, controleer_parameters
import json

AANTAL_FAVORIETE_PLEKKEN = 15
STANDAARD_SOUNDBOARDVOLUME = 75  # Rustiger beginvolume voor nieuwe installaties.


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
                # Ook schemawijzigingen zijn atomair: geen halve migratie bij een fout.
                database.execute("BEGIN IMMEDIATE")
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
                # Een algemene, optionele stand. We wijzigen geen bestaande
                # clipinstellingen of opgeslagen volumewaarden bij een upgrade.
                database.execute('''CREATE TABLE IF NOT EXISTS geluidsnormalisatie (
                    sleutel INTEGER PRIMARY KEY CHECK (sleutel = 1),
                    stand TEXT NOT NULL CHECK (stand IN ('uit', 'subtiel', 'normaal', 'sterk'))
                )''')
                self._maak_volume_tot_200_beschikbaar(database)
                database.execute('''CREATE TABLE IF NOT EXISTS pieklimiter_instellingen (
                    sleutel INTEGER PRIMARY KEY CHECK (sleutel = 1),
                    ingeschakeld INTEGER NOT NULL CHECK (ingeschakeld IN (0, 1))
                )''')
                database.execute('''CREATE TABLE IF NOT EXISTS stemprofiel_instellingen (
                    sleutel INTEGER PRIMARY KEY CHECK (sleutel = 1),
                    profiel TEXT NOT NULL CHECK (profiel IN ('normaal', 'radio', 'robot', 'diep'))
                )''')
                # De bestaande tabel heeft een vaste CHECK op de oude 4 profielen.
                # Die blijft intact; nieuwe keuzes en sterktes krijgen eigen tabellen.
                # Zo verliezen bestaande gebruikers hun oorspronkelijke voorkeur niet.
                database.execute('''CREATE TABLE IF NOT EXISTS stemprofiel_keuze_v2 (
                    sleutel INTEGER PRIMARY KEY CHECK (sleutel = 1),
                    profiel TEXT NOT NULL
                )''')
                database.execute('''CREATE TABLE IF NOT EXISTS stemprofiel_intensiteit (
                    profiel TEXT PRIMARY KEY,
                    intensiteit INTEGER NOT NULL CHECK (intensiteit BETWEEN 0 AND 100)
                )''')
                database.execute('''CREATE TABLE IF NOT EXISTS stemprofiel_parameters (
                    profiel TEXT PRIMARY KEY, instellingen_json TEXT NOT NULL
                )''')
                database.execute('''CREATE TABLE IF NOT EXISTS stemvoorbeeld_spreker (
                    sleutel INTEGER PRIMARY KEY CHECK(sleutel = 1),
                    spreker TEXT NOT NULL CHECK(spreker IN ('bob','elise'))
                )''')
                database.execute('''CREATE TABLE IF NOT EXISTS stemvervormer_aan (
                    sleutel INTEGER PRIMARY KEY CHECK (sleutel=1),
                    aan INTEGER NOT NULL CHECK (aan IN (0,1))
                )''')
                database.execute('''CREATE TABLE IF NOT EXISTS eigen_stem_monitor (
                    sleutel INTEGER PRIMARY KEY CHECK(sleutel = 1),
                    aan INTEGER NOT NULL CHECK(aan IN (0, 1)),
                    volume INTEGER NOT NULL CHECK(volume BETWEEN 1 AND 100)
                )''')
                # Bestaande bibliotheken verliezen geen instellingen. Alleen
                # wanneer de kolom ontbreekt voegen we die eenmalig toe.
                kolommen = {regel[1] for regel in database.execute('PRAGMA table_info(geluidsinstellingen)')}
                if 'beeldvoorkeur' not in kolommen:
                    database.execute("ALTER TABLE geluidsinstellingen ADD COLUMN beeldvoorkeur TEXT NOT NULL DEFAULT 'automatisch'")

    @staticmethod
    def _maak_volume_tot_200_beschikbaar(database) -> None:
        """Verruim alleen de volumetabel, met behoud van de oude rij als reservekopie.

        De aanroeper houdt één SQLite-transactie vast. De bibliotheek, media en
        individuele geluidsinstellingen worden niet opnieuw opgebouwd.
        """
        regel = database.execute(
            "SELECT sql FROM sqlite_master WHERE type='table' AND name='algemeen_effectvolume'"
        ).fetchone()
        if regel and re.search(r'BETWEEN\s+0\s+AND\s+100\b', regel[0], re.IGNORECASE):
            database.execute('ALTER TABLE algemeen_effectvolume RENAME TO algemeen_effectvolume_voor_beta411')
            database.execute('''CREATE TABLE algemeen_effectvolume (
                sleutel INTEGER PRIMARY KEY CHECK(sleutel = 1),
                percentage INTEGER NOT NULL CHECK(percentage BETWEEN 0 AND 200)
            )''')
            database.execute('''INSERT INTO algemeen_effectvolume(sleutel, percentage)
                SELECT sleutel, percentage FROM algemeen_effectvolume_voor_beta411''')
        else:
            database.execute('''CREATE TABLE IF NOT EXISTS algemeen_effectvolume (
                sleutel INTEGER PRIMARY KEY CHECK(sleutel = 1),
                percentage INTEGER NOT NULL CHECK(percentage BETWEEN 0 AND 200)
            )''')

    def _open_database(self):
        """SQLite verwijdert gekoppelde favorieten alleen wanneer FK expliciet aan staat."""
        verbinding = sqlite3.connect(self.databasepad, timeout=10)
        verbinding.execute('PRAGMA foreign_keys = ON')
        return closing(verbinding)

    def geef_stemvervormer_aan(self) -> bool:
        # De live aan/uitstand is onafhankelijk van het geselecteerde profiel.
        with self._open_database() as database:
            regel = database.execute('SELECT aan FROM stemvervormer_aan WHERE sleutel=1').fetchone()
        return bool(regel[0]) if regel else False

    def bewaar_stemvervormer_aan(self, aan: bool) -> bool:
        if type(aan) is not bool:
            raise OngeldigeFavorietOfInstelling('STEM-081: aan moet true of false zijn.')
        with self._open_database() as database:
            with database:
                database.execute('''INSERT INTO stemvervormer_aan(sleutel, aan) VALUES(1, ?)
                    ON CONFLICT(sleutel) DO UPDATE SET aan=excluded.aan''', (int(aan),))
        return aan

    def geef_eigen_stem_monitor(self) -> dict:
        with self._open_database() as database:
            regel = database.execute(
                'SELECT aan, volume FROM eigen_stem_monitor WHERE sleutel = 1'
            ).fetchone()
        return {'aan': bool(regel[0]), 'volume': regel[1]} if regel else {'aan': False, 'volume': 25}

    def bewaar_eigen_stem_monitor(self, aan: bool, volume: int) -> dict:
        if type(aan) is not bool or type(volume) is not int or not 1 <= volume <= 100:
            raise OngeldigeFavorietOfInstelling('MON-010: kies aan of uit en volume 1 tot 100%.')
        with self._open_database() as database:
            with database:
                database.execute('''INSERT INTO eigen_stem_monitor(sleutel, aan, volume)
                    VALUES (1, ?, ?) ON CONFLICT(sleutel) DO UPDATE SET
                    aan=excluded.aan, volume=excluded.volume''', (int(aan), volume))
        return {'aan': aan, 'volume': volume}

    def geef_normalisatiestand(self) -> str:
        """Lees de ingestelde sterkte; bestaande gebruikers beginnen veilig met Uit."""
        with self._open_database() as database:
            gevonden = database.execute(
                'SELECT stand FROM geluidsnormalisatie WHERE sleutel = 1'
            ).fetchone()
        return controleer_normalisatiestand(gevonden[0]) if gevonden else 'uit'

    def bewaar_normalisatiestand(self, stand: str) -> str:
        """Bewaar één algemene stand, zonder media of andere instellingen te wijzigen."""
        stand = controleer_normalisatiestand(stand)
        with self._open_database() as database:
            with database:
                database.execute('''INSERT INTO geluidsnormalisatie (sleutel, stand)
                    VALUES (1, ?) ON CONFLICT(sleutel) DO UPDATE SET stand=excluded.stand''', (stand,))
        return stand

    def geef_algemeen_effectvolume(self) -> int:
        """Bewaar expliciete keuzes; zonder keuze starten effecten op 75%."""
        with self._open_database() as database:
            regel = database.execute(
                'SELECT percentage FROM algemeen_effectvolume WHERE sleutel = 1'
            ).fetchone()
        return int(regel[0]) if regel else STANDAARD_SOUNDBOARDVOLUME

    def bewaar_algemeen_effectvolume(self, percentage: int) -> int:
        """Bewaar een absoluut percentage, zonder individuele clipvolumes aan te passen."""
        if type(percentage) is not int or not 0 <= percentage <= 200:
            raise OngeldigeFavorietOfInstelling(
                'VOLUME-001: soundboardvolume moet een heel percentage tussen 0 en 200 zijn.'
            )
        with self._open_database() as database:
            with database:
                database.execute("""INSERT INTO algemeen_effectvolume(sleutel, percentage)
                    VALUES(1, ?) ON CONFLICT(sleutel) DO UPDATE SET
                    percentage=excluded.percentage""", (percentage,))
        return percentage

    def geef_limiterstand(self) -> bool:
        """Bestaande bibliotheken krijgen standaard veilige piekbeveiliging."""
        with self._open_database() as database:
            gevonden = database.execute(
                'SELECT ingeschakeld FROM pieklimiter_instellingen WHERE sleutel = 1'
            ).fetchone()
        return bool(gevonden[0]) if gevonden else True

    def bewaar_limiterstand(self, ingeschakeld: bool) -> bool:
        """Bewaar alleen een echte bool, niet een JSON-string of een getal."""
        if type(ingeschakeld) is not bool:
            raise OngeldigeFavorietOfInstelling('FAV-020: limiter moet true of false zijn.')
        with self._open_database() as database:
            with database:
                database.execute('''INSERT INTO pieklimiter_instellingen (sleutel, ingeschakeld)
                    VALUES (1, ?) ON CONFLICT(sleutel) DO UPDATE SET ingeschakeld=excluded.ingeschakeld''',
                    (int(ingeschakeld),))
        return ingeschakeld

    def geef_stemprofiel(self) -> str:
        '''Geef nieuwe keuze terug; gebruik bij een upgrade eerst de oude waarde.'''
        with self._open_database() as database:
            regel = database.execute(
                'SELECT profiel FROM stemprofiel_keuze_v2 WHERE sleutel = 1'
            ).fetchone()
            if not regel:
                regel = database.execute(
                    'SELECT profiel FROM stemprofiel_instellingen WHERE sleutel = 1'
                ).fetchone()
        return controleer_stemprofiel(regel[0]) if regel else 'normaal'

    def bewaar_stemprofiel(self, profiel: str) -> str:
        profiel = controleer_stemprofiel(profiel)
        with self._open_database() as database:
            with database:
                database.execute('''INSERT INTO stemprofiel_keuze_v2 (sleutel, profiel)
                    VALUES (1, ?) ON CONFLICT(sleutel) DO UPDATE SET profiel=excluded.profiel''',
                    (profiel,))
        return profiel

    def geef_stemintensiteiten(self) -> dict[str, int]:
        '''Retourneer ook defaults voor profielen die nog nooit zijn gewijzigd.'''
        alle = dict(STANDAARD_INTENSITEITEN)
        with self._open_database() as database:
            regels = database.execute(
                'SELECT profiel, intensiteit FROM stemprofiel_intensiteit'
            ).fetchall()
        for profiel, intensiteit in regels:
            if profiel in alle:
                alle[profiel] = controleer_stemintensiteit(intensiteit)
        return alle

    def geef_stemparameters(self) -> dict[str,dict]:
        waarden = standaard_parameters()
        with self._open_database() as database:
            regels = database.execute('SELECT profiel, instellingen_json FROM stemprofiel_parameters').fetchall()
        for profiel, ruwe_json in regels:
            if profiel in waarden:
                try:
                    opgeslagen = json.loads(ruwe_json)
                    waarden[profiel] = controleer_parameters(profiel, opgeslagen)
                except (ValueError, TypeError):
                    # Ongeldige waarden worden nooit aan de audiocallback doorgegeven.
                    pass
        return waarden

    def bewaar_stemparameters(self, profiel: str, waarden: dict) -> dict:
        gecontroleerd = controleer_parameters(profiel, waarden)
        with self._open_database() as database:
            with database:
                database.execute('''INSERT INTO stemprofiel_parameters(profiel, instellingen_json)
                    VALUES (?, ?) ON CONFLICT(profiel) DO UPDATE SET instellingen_json=excluded.instellingen_json''',
                    (profiel, json.dumps(gecontroleerd, separators=(',', ':'))))
        return gecontroleerd

    def herstel_stemparameters(self, profiel: str | None = None) -> dict[str,dict]:
        if profiel is not None and profiel not in standaard_parameters():
            raise ValueError('STEM-054: dit profiel heeft geen geavanceerde instellingen.')
        with self._open_database() as database:
            with database:
                if profiel is None:
                    database.execute('DELETE FROM stemprofiel_parameters')
                else:
                    database.execute('DELETE FROM stemprofiel_parameters WHERE profiel=?', (profiel,))
        return self.geef_stemparameters()

    def geef_voorbeeldspreker(self) -> str:
        with self._open_database() as database:
            rij = database.execute('SELECT spreker FROM stemvoorbeeld_spreker WHERE sleutel=1').fetchone()
        return rij[0] if rij else 'bob'

    def bewaar_voorbeeldspreker(self, spreker: str) -> str:
        if type(spreker) is not str or spreker not in ('bob','elise'):
            raise ValueError('STEM-055: kies Bob of Elise.')
        with self._open_database() as database:
            with database:
                database.execute('''INSERT INTO stemvoorbeeld_spreker(sleutel, spreker)
                    VALUES(1, ?) ON CONFLICT(sleutel) DO UPDATE SET spreker=excluded.spreker''', (spreker,))
        return spreker

    def bewaar_stemintensiteit(self, profiel: str, intensiteit: int) -> int:
        profiel = controleer_stemprofiel(profiel)
        intensiteit = controleer_stemintensiteit(intensiteit)
        with self._open_database() as database:
            with database:
                database.execute('''INSERT INTO stemprofiel_intensiteit (profiel, intensiteit)
                    VALUES (?, ?) ON CONFLICT(profiel) DO UPDATE SET intensiteit=excluded.intensiteit''',
                    (profiel, intensiteit))
        return intensiteit

    def herstel_stemintensiteit(self, profiel: str | None = None) -> dict[str, int]:
        '''Herstel één profiel, of expliciet alle profielen bij None.'''
        if profiel is not None:
            controleer_stemprofiel(profiel)
        with self._open_database() as database:
            with database:
                if profiel is None:
                    database.execute('DELETE FROM stemprofiel_intensiteit')
                else:
                    database.execute('DELETE FROM stemprofiel_intensiteit WHERE profiel = ?', (profiel,))
        return self.geef_stemintensiteiten()

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
