"""Lokale gebruiksgeschiedenis en persoonlijke schermkleuren.

Audio loopt nooit door deze module. Alleen expliciete gebruikersacties en
schermvoorkeuren gaan naar SQLite, buiten de realtime audiocallback.
De geschiedenis bevat geen opnames of microfoonsamples.
"""
from __future__ import annotations

from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path
import re
import sqlite3
from uuid import UUID, uuid4

from app.audio.geluidenbibliotheek import bepaal_standaardlocatie_van_de_bibliotheek


class OngeldigeWeergaveOfGeschiedenis(ValueError):
    """Gecontroleerde invoerfout met herkenbare foutcode."""


# Basis-thema's zijn vaste, leesbare combinaties. De gebruiker kan daarnaast
# één accentkleur kiezen zonder foutmeldingen of de Stop-knop te recoloreren.
BASISTHEMAS = {
    'obsidian': {'naam': 'Obsidian', 'achtergrond': '#0A0D12', 'paneel': '#121820', 'paneel_hoog': '#1A242E', 'rand': '#293440', 'accent': '#78D6C5'},
    'midnight': {'naam': 'Midnight', 'achtergrond': '#0B1221', 'paneel': '#151E31', 'paneel_hoog': '#1B2A42', 'rand': '#33435B', 'accent': '#8AAEFF'},
    'amethyst': {'naam': 'Amethyst', 'achtergrond': '#130F1C', 'paneel': '#20182C', 'paneel_hoog': '#2C213B', 'rand': '#413650', 'accent': '#C5A0F0'},
    'ember': {'naam': 'Ember', 'achtergrond': '#18110F', 'paneel': '#251B19', 'paneel_hoog': '#352522', 'rand': '#503935', 'accent': '#F0AA79'},
    'monochrome': {'naam': 'Monochrome', 'achtergrond': '#101214', 'paneel': '#1C2024', 'paneel_hoog': '#282D32', 'rand': '#414850', 'accent': '#E4EBEE'},
}
GRADIENTSTERKTES = ('uit', 'subtiel', 'duidelijk')
GRADIENTRICHTINGEN = ('rechtsboven', 'linksboven', 'onder')
GELDIGE_AFSPEELWIJZEN = ('preview', 'gesprek')
MAX_GESCHIEDENIS = 500


def controleer_weergave_instellingen(gegevens: dict) -> dict:
    """Valideer alle waarden voordat er iets wordt opgeslagen of gerenderd.

    Met strikte keys voorkom je dat een typefout ongemerkt een niet-werkende
    voorkeur toevoegt. Een zelfgekozen accent is altijd een hexkleur, nooit CSS.
    """
    if not isinstance(gegevens, dict) or set(gegevens) != {
        'thema', 'accentkleur', 'gradient', 'gradientrichting', 'compact'
    }:
        raise OngeldigeWeergaveOfGeschiedenis('THEMA-001: vul thema, accentkleur, gradient, gradientrichting en compact in.')
    thema = gegevens['thema']
    if not isinstance(thema, str) or thema not in BASISTHEMAS:
        raise OngeldigeWeergaveOfGeschiedenis('THEMA-002: dit basisthema bestaat niet.')
    accent = gegevens['accentkleur']
    if accent is not None and (not isinstance(accent, str) or not re.fullmatch(r'#[0-9a-fA-F]{6}', accent)):
        raise OngeldigeWeergaveOfGeschiedenis('THEMA-003: accentkleur moet leeg of een hexkleur zoals #78D6C5 zijn.')
    if gegevens['gradient'] not in GRADIENTSTERKTES:
        raise OngeldigeWeergaveOfGeschiedenis('THEMA-004: ongeldige gradientsterkte.')
    if gegevens['gradientrichting'] not in GRADIENTRICHTINGEN:
        raise OngeldigeWeergaveOfGeschiedenis('THEMA-005: ongeldige gradientrichting.')
    if type(gegevens['compact']) is not bool:
        raise OngeldigeWeergaveOfGeschiedenis('THEMA-006: compact moet true of false zijn.')
    accent = accent.upper() if accent else None
    if accent:
        # Een heel donkere accentkleur tegen een donker paneel maakt knoppen
        # onvindbaar. Voor grafische bediening eisen we minimaal 3:1 contrast.
        def kanaal(lineair):
            waarde = lineair / 255
            return waarde / 12.92 if waarde <= .04045 else ((waarde + .055) / 1.055) ** 2.4
        def helderheid(kleur):
            return sum(factor * kanaal(int(kleur[i:i + 2], 16)) for factor, i in ((.2126, 1), (.7152, 3), (.0722, 5)))
        licht = helderheid(accent)
        donker = helderheid(BASISTHEMAS[thema]['paneel'])
        verhouding = (max(licht, donker) + .05) / (min(licht, donker) + .05)
        if verhouding < 3:
            raise OngeldigeWeergaveOfGeschiedenis('THEMA-007: de accentkleur is te donker voor dit thema. Kies een lichtere kleur.')
    return {
        'thema': thema, 'accentkleur': accent,
        'gradient': gegevens['gradient'], 'gradientrichting': gegevens['gradientrichting'],
        'compact': gegevens['compact'],
    }


class RecenteGeluidenEnWeergave:
    """Bewaar schermvoorkeuren en de laatste audioacties naast de bibliotheek."""

    def __init__(self, databasepad: Path | None = None):
        self.databasepad = Path(databasepad) if databasepad else bepaal_standaardlocatie_van_de_bibliotheek()
        self.databasepad.parent.mkdir(parents=True, exist_ok=True)
        with self._open_database() as database:
            with database:
                database.execute('''CREATE TABLE IF NOT EXISTS schermvoorkeuren (
                    nummer INTEGER PRIMARY KEY CHECK (nummer=1),
                    thema TEXT NOT NULL, accentkleur TEXT, gradient TEXT NOT NULL,
                    gradientrichting TEXT NOT NULL, compact INTEGER NOT NULL
                )''')
                database.execute('''CREATE TABLE IF NOT EXISTS recent_afgespeeld (
                    nummer INTEGER PRIMARY KEY AUTOINCREMENT,
                    geluid_id TEXT NOT NULL, naam TEXT NOT NULL,
                    wijze TEXT NOT NULL, tijdstip_utc TEXT NOT NULL,
                    afspeelbeurt TEXT UNIQUE, status TEXT NOT NULL DEFAULT 'gestart',
                    duur_seconden REAL NOT NULL DEFAULT 0
                )''')
                database.execute('''CREATE INDEX IF NOT EXISTS index_recente_afspeelbeurten
                    ON recent_afgespeeld(tijdstip_utc DESC, nummer DESC)''')
                database.execute('''CREATE TABLE IF NOT EXISTS afspeelstatistieken (
                    geluid_id TEXT PRIMARY KEY, aantal_keer INTEGER NOT NULL DEFAULT 0,
                    laatst_afgespeeld_utc TEXT NOT NULL
                )''')
                # Historisch gebruik zo goed mogelijk eenmalig meenemen, zonder nieuwe tellingen te verliezen.
                # De oude geschiedenis is begrensd: aantallen van vóór die grens zijn onbekend.
                database.execute('''INSERT OR IGNORE INTO afspeelstatistieken (geluid_id, aantal_keer, laatst_afgespeeld_utc)
                    SELECT geluid_id, COUNT(*), MAX(tijdstip_utc) FROM recent_afgespeeld
                    WHERE wijze='gesprek' GROUP BY geluid_id''')
                database.execute('''CREATE TABLE IF NOT EXISTS recente_groepen (
                    groep_id TEXT PRIMARY KEY, laatst_gebruikt_utc TEXT NOT NULL
                )''')
                database.execute('''CREATE TABLE IF NOT EXISTS eigen_themaprofielen (
                    profiel_id TEXT PRIMARY KEY, naam TEXT NOT NULL UNIQUE COLLATE NOCASE,
                    thema TEXT NOT NULL, accentkleur TEXT,
                    gradient TEXT NOT NULL, gradientrichting TEXT NOT NULL,
                    compact INTEGER NOT NULL, opgeslagen_op_utc TEXT NOT NULL
                )''')

    def _open_database(self):
        database = sqlite3.connect(self.databasepad, timeout=10)
        database.execute('PRAGMA foreign_keys=ON')
        return closing(database)

    def geef_weergave(self) -> dict:
        with self._open_database() as database:
            rij = database.execute('''SELECT thema, accentkleur, gradient, gradientrichting, compact
                FROM schermvoorkeuren WHERE nummer=1''').fetchone()
        if rij is None:
            rij = ('obsidian', None, 'subtiel', 'rechtsboven', 0)
        gegevens = controleer_weergave_instellingen({
            'thema': rij[0], 'accentkleur': rij[1], 'gradient': rij[2],
            'gradientrichting': rij[3], 'compact': bool(rij[4]),
        })
        return {**gegevens, 'palet': {**BASISTHEMAS[gegevens['thema']],
                                       'accent': gegevens['accentkleur'] or BASISTHEMAS[gegevens['thema']]['accent']}}

    def bewaar_weergave(self, gegevens: dict) -> dict:
        voorkeur = controleer_weergave_instellingen(gegevens)
        with self._open_database() as database:
            with database:
                database.execute('''INSERT INTO schermvoorkeuren VALUES (1,?,?,?,?,?)
                    ON CONFLICT(nummer) DO UPDATE SET
                    thema=excluded.thema, accentkleur=excluded.accentkleur,
                    gradient=excluded.gradient, gradientrichting=excluded.gradientrichting,
                    compact=excluded.compact''',
                    (voorkeur['thema'], voorkeur['accentkleur'], voorkeur['gradient'],
                     voorkeur['gradientrichting'], int(voorkeur['compact'])))
        return self.geef_weergave()

    def geef_eigen_themaprofielen(self) -> list[dict]:
        with self._open_database() as database:
            rijen = database.execute('''SELECT profiel_id, naam, thema, accentkleur, gradient,
                gradientrichting, compact FROM eigen_themaprofielen
                ORDER BY naam COLLATE NOCASE''').fetchall()
        return [{'id': rij[0], 'naam': rij[1], 'instellingen': {
            'thema': rij[2], 'accentkleur': rij[3], 'gradient': rij[4],
            'gradientrichting': rij[5], 'compact': bool(rij[6]),
        }} for rij in rijen]

    def bewaar_eigen_themaprofiel(self, naam: str, gegevens: dict) -> dict:
        """Bewaar maximaal 20 herbruikbare ontwerpen, zonder huidige keuze te wijzigen.

        Een bestaande naam mag overschreven worden. Zo kan iemand kleuren
        bijwerken zonder dat er twintig vrijwel gelijke presets ontstaan.
        """
        if not isinstance(naam, str) or not 1 <= len(naam.strip()) <= 40 or any(c in naam for c in '\r\n\0'):
            raise OngeldigeWeergaveOfGeschiedenis('THEMA-008: kies een profielnaam van 1 tot 40 tekens.')
        naam = naam.strip()
        voorkeur = controleer_weergave_instellingen(gegevens)
        with self._open_database() as database:
            with database:
                bestaand = database.execute('SELECT profiel_id FROM eigen_themaprofielen WHERE naam=?', (naam,)).fetchone()
                if bestaand is None and database.execute('SELECT COUNT(*) FROM eigen_themaprofielen').fetchone()[0] >= 20:
                    raise OngeldigeWeergaveOfGeschiedenis('THEMA-009: bewaar maximaal 20 eigen thema’s.')
                profiel_id = bestaand[0] if bestaand else str(uuid4())
                database.execute('''INSERT INTO eigen_themaprofielen VALUES (?,?,?,?,?,?,?,?)
                    ON CONFLICT(naam) DO UPDATE SET thema=excluded.thema,
                    accentkleur=excluded.accentkleur, gradient=excluded.gradient,
                    gradientrichting=excluded.gradientrichting, compact=excluded.compact,
                    opgeslagen_op_utc=excluded.opgeslagen_op_utc''',
                    (profiel_id, naam, voorkeur['thema'], voorkeur['accentkleur'],
                     voorkeur['gradient'], voorkeur['gradientrichting'], int(voorkeur['compact']), self._tijdstip()))
        return {'id': profiel_id, 'naam': naam, 'instellingen': voorkeur}

    def verwijder_eigen_themaprofiel(self, profiel_id: str) -> None:
        try:
            profiel_id = str(UUID(profiel_id))
        except (ValueError, TypeError, AttributeError) as fout:
            raise OngeldigeWeergaveOfGeschiedenis('THEMA-010: ongeldig profielnummer.') from fout
        with self._open_database() as database:
            with database:
                verwijderd = database.execute('DELETE FROM eigen_themaprofielen WHERE profiel_id=?', (profiel_id,))
                if verwijderd.rowcount != 1:
                    raise OngeldigeWeergaveOfGeschiedenis('THEMA-011: eigen thema bestaat niet meer.')

    @staticmethod
    def _tijdstip() -> str:
        return datetime.now(timezone.utc).isoformat(timespec='microseconds')

    def registreer_groep_geopend(self, groep_id: str) -> None:
        try:
            groep_id = str(UUID(groep_id))
        except (TypeError, ValueError, AttributeError) as fout:
            raise OngeldigeWeergaveOfGeschiedenis('RECENT-001: ongeldig groepsnummer.') from fout
        with self._open_database() as database:
            with database:
                if not database.execute('SELECT 1 FROM geluidsgroepen WHERE groep_id=?', (groep_id,)).fetchone():
                    raise OngeldigeWeergaveOfGeschiedenis('RECENT-002: groep is niet gevonden.')
                self._zet_groep_als_recent(database, groep_id, self._tijdstip())

    @staticmethod
    def _zet_groep_als_recent(database, groep_id: str, tijdstip: str) -> None:
        database.execute('''INSERT INTO recente_groepen VALUES (?, ?)
            ON CONFLICT(groep_id) DO UPDATE SET laatst_gebruikt_utc=excluded.laatst_gebruikt_utc''',
            (groep_id, tijdstip))

    def registreer_afspelen(self, geluid_id: str, naam: str, wijze: str,
                            afspeelbeurt: str | None = None) -> None:
        if not isinstance(geluid_id, str) or not geluid_id or not isinstance(naam, str) or not naam:
            raise OngeldigeWeergaveOfGeschiedenis('RECENT-003: geluidsnummer of naam ontbreekt.')
        if wijze not in GELDIGE_AFSPEELWIJZEN:
            raise OngeldigeWeergaveOfGeschiedenis('RECENT-004: kies preview of gesprek.')
        if afspeelbeurt is not None and (not isinstance(afspeelbeurt, str) or not 1 <= len(afspeelbeurt) <= 120):
            raise OngeldigeWeergaveOfGeschiedenis('RECENT-005: ongeldig afspeelbeurtnummer.')
        nu = self._tijdstip()
        with self._open_database() as database:
            with database:
                # Speelbeurten mogen niet dubbel tellen bij een verzoek dat
                # opnieuw wordt verstuurd na een trage browserreactie.
                ingevoegd = database.execute('''INSERT OR IGNORE INTO recent_afgespeeld
                    (geluid_id, naam, wijze, tijdstip_utc, afspeelbeurt)
                    VALUES (?, ?, ?, ?, ?)''', (geluid_id, naam[:100], wijze, nu, afspeelbeurt))
                if ingevoegd.rowcount and wijze == 'gesprek':
                    database.execute('''INSERT INTO afspeelstatistieken VALUES (?, 1, ?)
                        ON CONFLICT(geluid_id) DO UPDATE SET aantal_keer=aantal_keer+1,
                        laatst_afgespeeld_utc=excluded.laatst_afgespeeld_utc''', (geluid_id, nu))
                groep_ids = database.execute('''SELECT koppeling.groep_id FROM geluiden_in_groep AS koppeling
                    JOIN geluidsgroepen AS groep ON groep.groep_id=koppeling.groep_id
                    WHERE koppeling.geluid_id=?''', (geluid_id,)).fetchall()
                for (groep_id,) in groep_ids:
                    self._zet_groep_als_recent(database, groep_id, nu)
                database.execute('''DELETE FROM recent_afgespeeld WHERE nummer IN (
                    SELECT nummer FROM recent_afgespeeld ORDER BY tijdstip_utc DESC, nummer DESC
                    LIMIT -1 OFFSET ?)''', (MAX_GESCHIEDENIS,))

    def registreer_afspeel_einde(self, geluid_id: str, wijze: str, reden: str,
                                 duur_seconden: float = 0, afspeelbeurt: str | None = None) -> None:
        if wijze not in GELDIGE_AFSPEELWIJZEN:
            raise OngeldigeWeergaveOfGeschiedenis('RECENT-004: kies preview of gesprek.')
        if not isinstance(reden, str) or len(reden) > 80:
            raise OngeldigeWeergaveOfGeschiedenis('RECENT-006: ongeldige stopreden.')
        if isinstance(duur_seconden, bool) or not isinstance(duur_seconden, (int, float)) or not 0 <= duur_seconden <= 120:
            raise OngeldigeWeergaveOfGeschiedenis('RECENT-007: afspeelduur moet tussen 0 en 120 liggen.')
        # Bij een historische preview zonder afspeelbeurt gebruiken we de
        # laatst gestarte sessie voor hetzelfde geluid. Dat behoudt compatibiliteit.
        filter_beurt = 'AND afspeelbeurt=?' if afspeelbeurt else ''
        parameters = (geluid_id, wijze, afspeelbeurt) if afspeelbeurt else (geluid_id, wijze)
        with self._open_database() as database:
            with database:
                database.execute(f'''UPDATE recent_afgespeeld
                    SET status=?, duur_seconden=? WHERE nummer=(
                        SELECT nummer FROM recent_afgespeeld
                        WHERE geluid_id=? AND wijze=? AND status='gestart' {filter_beurt}
                        ORDER BY nummer DESC LIMIT 1)''',
                    (reden[:80], float(duur_seconden), *parameters))

    def geef_recente_gebruik(self, maximaal_geluiden: int = 12) -> dict:
        if type(maximaal_geluiden) is not int or not 1 <= maximaal_geluiden <= 100:
            raise OngeldigeWeergaveOfGeschiedenis('RECENT-008: vraag maximaal 100 recente geluiden op.')
        with self._open_database() as database:
            groepregels = database.execute('''SELECT groepen.groep_id, groepen.naam,
                (SELECT COUNT(*) FROM geluiden_in_groep k WHERE k.groep_id=groepen.groep_id),
                recent.laatst_gebruikt_utc
                FROM recente_groepen recent JOIN geluidsgroepen groepen ON groepen.groep_id=recent.groep_id
                ORDER BY recent.laatst_gebruikt_utc DESC LIMIT 5''').fetchall()
            geluidregels = database.execute('''SELECT geschiedenis.geluid_id, geschiedenis.naam,
                geschiedenis.wijze, geschiedenis.tijdstip_utc, geschiedenis.status,
                geschiedenis.duur_seconden,
                EXISTS (SELECT 1 FROM geluiden g WHERE g.geluid_id=geschiedenis.geluid_id)
                FROM recent_afgespeeld geschiedenis
                ORDER BY geschiedenis.tijdstip_utc DESC, geschiedenis.nummer DESC LIMIT ?''', (maximaal_geluiden,)).fetchall()
        return {
            'groepen': [{'id': x[0], 'naam': x[1], 'aantal_geluiden': x[2], 'laatst_gebruikt_utc': x[3]}
                       for x in groepregels],
            'geluiden': [{'id': x[0], 'naam': x[1], 'wijze': x[2], 'tijdstip_utc': x[3],
                          'status': x[4], 'afgespeelde_seconden': x[5], 'bestaat_nog': bool(x[6])}
                         for x in geluidregels],
        }

    def geef_afspeelaantallen(self) -> dict[str, int]:
        """Blijvende teller van werkelijke soundboard-uitzendingen, dus geen previews."""
        with self._open_database() as database:
            return {nummer: int(aantal) for nummer, aantal in database.execute(
                'SELECT geluid_id, aantal_keer FROM afspeelstatistieken')}

    def wis_afspeelgeschiedenis(self) -> None:
        """Wis gebruikshistorie, niet bibliotheek, groepen of favorieten."""
        with self._open_database() as database:
            with database:
                database.execute('DELETE FROM recent_afgespeeld')
                database.execute('DELETE FROM recente_groepen')
