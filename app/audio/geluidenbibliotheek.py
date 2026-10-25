"""Bewaar zelfgekozen geluidsnamen en bestandspaden in een kleine SQLite-database.

We kopiëren de audiobestanden in deze fase niet. Dat voorkomt het ongevraagd
verdubbelen van grote muzieknummers. Bestanden mogen dus niet verplaatst worden
zonder ze opnieuw te koppelen. In een latere fase komt bibliotheekexport.
"""

from __future__ import annotations

from contextlib import closing
from dataclasses import dataclass
from datetime import datetime, timezone
import os
from pathlib import Path
import sqlite3
from uuid import uuid4
from collections.abc import Iterable

from app.audio.mp3_en_wav_fragmenten import controleer_of_geluidsbestand_gebruikt_mag_worden


class BibliotheekFout(ValueError):
    """Een expliciete foutcode voor ongeldige invoer of missende bibliotheekitems."""


@dataclass(frozen=True)
class GeluidInBibliotheek:
    geluid_id: str
    eigen_naam: str
    bestandspad: Path


def bepaal_standaardlocatie_van_de_bibliotheek() -> Path:
    """Op iedere Windows-pc gebruikt de bibliotheek de eigen gebruikersmap."""
    basis = os.environ.get("LOCALAPPDATA")
    if basis:
        return Path(basis) / "DrostSoundboard" / "bibliotheek.sqlite3"
    return Path.home() / ".drostsoundboard" / "bibliotheek.sqlite3"


def _controleer_eigen_geluidsnaam(nieuwe_naam: str) -> str:
    if not isinstance(nieuwe_naam, str):
        raise BibliotheekFout(
            f"BIB-001: geluidsnaam moet tekst zijn, niet {type(nieuwe_naam).__name__}."
        )
    naam = nieuwe_naam.strip()
    if not 1 <= len(naam) <= 100 or any(teken in naam for teken in "\n\r\0"):
        raise BibliotheekFout("BIB-002: kies een naam van 1 tot 100 tekens zonder regeleinden.")
    return naam


class PersoonlijkeGeluidenbibliotheek:
    """Houd alle databaseacties buiten de realtime audiocallback."""

    def __init__(self, databasepad: str | Path | None = None) -> None:
        self.databasepad = Path(databasepad) if databasepad is not None else bepaal_standaardlocatie_van_de_bibliotheek()
        self.databasepad.parent.mkdir(parents=True, exist_ok=True)
        try:
            with closing(sqlite3.connect(self.databasepad, timeout=5)) as database:
                with database:
                    database.execute("""CREATE TABLE IF NOT EXISTS geluiden (
                        geluid_id TEXT PRIMARY KEY,
                        eigen_naam TEXT NOT NULL,
                        bestandspad TEXT NOT NULL,
                        zoeksleutel_pad TEXT NOT NULL UNIQUE,
                        toegevoegd_op_utc TEXT NOT NULL
                    )""")
        except sqlite3.Error as oorspronkelijke_fout:
            raise BibliotheekFout("BIB-003: de geluidenbibliotheek kon niet worden geopend.") from oorspronkelijke_fout

    def geef_alle_geluiden(self) -> list[GeluidInBibliotheek]:
        try:
            with closing(sqlite3.connect(self.databasepad, timeout=5)) as database:
                regels = database.execute(
                    "SELECT geluid_id, eigen_naam, bestandspad FROM geluiden ORDER BY eigen_naam COLLATE NOCASE, toegevoegd_op_utc"
                ).fetchall()
        except sqlite3.Error as oorspronkelijke_fout:
            raise BibliotheekFout("BIB-004: de geluidenbibliotheek kon niet worden gelezen.") from oorspronkelijke_fout
        return [GeluidInBibliotheek(regel[0], regel[1], Path(regel[2])) for regel in regels]

    def voeg_geluidsbestanden_toe(self, bestandspaden: Iterable[str | Path]) -> list[GeluidInBibliotheek]:
        """Importeer meerdere bestanden atomair, zonder de oorspronkelijke muziek te wijzigen."""
        if isinstance(bestandspaden, (str, bytes, Path)) or bestandspaden is None:
            raise BibliotheekFout("BIB-005: geef een verzameling bestandspaden op, niet één tekstwaarde.")
        try:
            paden = [controleer_of_geluidsbestand_gebruikt_mag_worden(p) for p in bestandspaden]
        except TypeError as oorspronkelijke_fout:
            raise BibliotheekFout("BIB-006: de ontvangen bestandspaden zijn niet doorloopbaar.") from oorspronkelijke_fout
        if not paden:
            return []
        toegevoegde_geluiden: list[GeluidInBibliotheek] = []
        try:
            with closing(sqlite3.connect(self.databasepad, timeout=5)) as database:
                with database:
                    for pad in paden:
                        sleutel = str(pad).casefold()
                        bestaand = database.execute(
                            "SELECT geluid_id, eigen_naam, bestandspad FROM geluiden WHERE zoeksleutel_pad = ?",
                            (sleutel,),
                        ).fetchone()
                        if bestaand is not None:
                            toegevoegde_geluiden.append(
                                GeluidInBibliotheek(bestaand[0], bestaand[1], Path(bestaand[2]))
                            )
                            continue
                        item = GeluidInBibliotheek(str(uuid4()), _controleer_eigen_geluidsnaam(pad.stem), pad)
                        database.execute(
                            "INSERT INTO geluiden (geluid_id, eigen_naam, bestandspad, zoeksleutel_pad, toegevoegd_op_utc) VALUES (?, ?, ?, ?, ?)",
                            (item.geluid_id, item.eigen_naam, str(pad), sleutel, datetime.now(timezone.utc).isoformat()),
                        )
                        toegevoegde_geluiden.append(item)
        except sqlite3.Error as oorspronkelijke_fout:
            raise BibliotheekFout("BIB-007: het toevoegen aan de bibliotheek is mislukt.") from oorspronkelijke_fout
        return toegevoegde_geluiden

    def verander_de_naam_van_een_geluid(self, geluid_id: str, nieuwe_naam: str) -> None:
        naam = _controleer_eigen_geluidsnaam(nieuwe_naam)
        if not isinstance(geluid_id, str) or not geluid_id:
            raise BibliotheekFout("BIB-008: het geluidsnummer ontbreekt.")
        try:
            with closing(sqlite3.connect(self.databasepad, timeout=5)) as database:
                with database:
                    teller = database.execute(
                        "UPDATE geluiden SET eigen_naam = ? WHERE geluid_id = ?", (naam, geluid_id)
                    )
                    if teller.rowcount != 1:
                        raise BibliotheekFout("BIB-009: dit geluid staat niet meer in de bibliotheek.")
        except sqlite3.Error as oorspronkelijke_fout:
            raise BibliotheekFout("BIB-010: geluidsnaam kon niet worden bewaard.") from oorspronkelijke_fout

    def haal_geluid_uit_de_bibliotheek(self, geluid_id: str) -> None:
        """Verwijder alleen de verwijzing, nooit iemands eigen MP3-bestand."""
        if not isinstance(geluid_id, str) or not geluid_id:
            raise BibliotheekFout("BIB-011: het geluidsnummer ontbreekt.")
        try:
            with closing(sqlite3.connect(self.databasepad, timeout=5)) as database:
                with database:
                    aantal = database.execute(
                        "DELETE FROM geluiden WHERE geluid_id = ?", (geluid_id,)
                    ).rowcount
                    if aantal != 1:
                        raise BibliotheekFout("BIB-012: geluid staat niet in de bibliotheek.")
        except sqlite3.Error as oorspronkelijke_fout:
            raise BibliotheekFout("BIB-013: het geluid kon niet uit de bibliotheek worden gehaald.") from oorspronkelijke_fout

    def haal_meerdere_geluiden_uit_de_bibliotheek(self, geluidsnummers: list[str]) -> int:
        """Verwijder een selectie in één transactie zonder geluidsbestanden te wissen."""
        if (not isinstance(geluidsnummers, list) or not 1 <= len(geluidsnummers) <= 250
                or any(not isinstance(nummer, str) for nummer in geluidsnummers)):
            raise BibliotheekFout('BIB-014: selecteer tussen 1 en 250 geldige geluiden.')
        uniek = list(dict.fromkeys(geluidsnummers))
        with closing(sqlite3.connect(self.databasepad, timeout=10)) as database:
            database.execute('PRAGMA foreign_keys=ON')
            with database:
                placeholders = ','.join('?' for _ in uniek)
                gevonden = database.execute(f'SELECT COUNT(*) FROM geluiden WHERE geluid_id IN ({placeholders})', uniek).fetchone()[0]
                if gevonden != len(uniek):
                    raise BibliotheekFout('BIB-015: één of meer geselecteerde geluiden bestaan niet meer.')
                database.execute(f'DELETE FROM geluiden WHERE geluid_id IN ({placeholders})', uniek)
        return len(uniek)
