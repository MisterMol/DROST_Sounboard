"""Bied een klein, lokaal HTTP-dashboard aan zonder derde webframework.

Het dashboard is uitsluitend bereikbaar op 127.0.0.1. Schrijfopdrachten
vereisen een per-start willekeurig token, zodat een andere website niet
zomaar geluiden of instellingen in onze lokale applicatie kan veranderen.
Bestandsuploads worden in blokken weggeschreven om het geheugen te sparen.
"""

from __future__ import annotations

import base64
from datetime import datetime, timezone
import html
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import logging
import os
from pathlib import Path
import re
import secrets
import shutil
import socket
import threading
import time
from tempfile import NamedTemporaryFile
from typing import Any
from urllib.parse import unquote, urlsplit, parse_qs
from uuid import UUID, uuid4

from app.audio.mp3_en_wav_fragmenten import controleer_of_geluidsbestand_gebruikt_mag_worden
from app.webinterface.api_foutantwoorden import maak_webfoutantwoord, maak_webantwoord_voor_onbekende_route
from app.audio.mp4_verwerken import controleer_of_mp4_audio_en_video_bevat
from app.diagnostiek.logboek import schrijf_auditgebeurtenis
from app.webinterface.bediening_van_de_audiomotor import WebbedieningVanDrostSoundboard
from app.webinterface.favorieten_en_instellingen import controleer_favorietplek

STATISCHE_MAP = Path(__file__).resolve().parent / 'statisch'
TOEGESTANE_AFBEELDINGEN = frozenset({'.png', '.jpg', '.jpeg', '.gif', '.webp'})
GROOTSTE_AUDIO_UPLOAD_IN_BYTES = 250 * 1024 * 1024
GROOTSTE_BIBLIOTHEEK_ARCHIEF_BYTES = 512 * 1024 * 1024
GROOTSTE_AFBEELDING_IN_BYTES = 8 * 1024 * 1024
GROOTSTE_JSON_IN_BYTES = 65536
MEDIA_UITVOERBLOK_BYTES = 256 * 1024
BESTANDSBUFFER_IN_BYTES = 256 * 1024


class OngeldigWebverzoek(ValueError):
    """Een herkenbare clientfout met een controleerbare melding."""


def geef_map_voor_beheerde_bestanden() -> Path:
    """Gebruik AppData, omdat het project later in Program Files kan staan."""
    return Path(os.environ.get('LOCALAPPDATA') or (Path.home() / '.drostsoundboard')) / 'DrostSoundboard' / 'media'


def controleer_of_afbeelding_echt_een_afbeelding_is(pad: Path, extensie: str) -> None:
    """Een HTML-bestand met een .jpg-naam mag nooit als actieve webinhoud komen."""
    with pad.open('rb') as bestand:
        begin = bestand.read(16)
    handtekeningen = {
        '.jpg': begin.startswith(b'\xff\xd8\xff'),
        '.jpeg': begin.startswith(b'\xff\xd8\xff'),
        '.png': begin.startswith(b'\x89PNG\r\n\x1a\n'),
        '.gif': begin.startswith((b'GIF87a', b'GIF89a')),
        '.webp': begin.startswith(b'RIFF') and begin[8:12] == b'WEBP',
    }
    if not handtekeningen.get(extensie, False):
        raise OngeldigWebverzoek('WEB-020: bestand is geen geldige afbeelding van dit type.')


class LokaleWebserverVanDrostSoundboard(ThreadingHTTPServer):
    """Bewaar instellingen op de server, nooit in globale requestvariabelen."""
    daemon_threads = True
    allow_reuse_address = True

    def __init__(self, adres: tuple[str, int], bediening: WebbedieningVanDrostSoundboard):
        super().__init__(adres, DrostVerzoekAfhandeling)
        self.bediening = bediening
        self.schrijf_token = secrets.token_urlsafe(32)
        # Elke browser heeft hooguit één SSE-verbinding. Begrenzing voorkomt
        # dat onbedoeld veel tabbladen de kleine lokale server overbelasten.
        self.maximale_live_verbindingen = threading.BoundedSemaphore(4)
        # Slechts één actieve FFmpeg-export tegelijk: voorkomt dat game-audio
        # gaat haperen doordat meerdere zware conversies CPU opeisen.
        self.maximale_losse_exports = threading.BoundedSemaphore(1)
        self.media_map = geef_map_voor_beheerde_bestanden()
        (self.media_map / 'geluiden').mkdir(parents=True, exist_ok=True)
        (self.media_map / 'afbeeldingen').mkdir(parents=True, exist_ok=True)


class DrostVerzoekAfhandeling(BaseHTTPRequestHandler):
    """Kleine verzameling van expliciet toegestane lokale HTTP-routes."""
    server: LokaleWebserverVanDrostSoundboard
    protocol_version = 'HTTP/1.1'

    def log_message(self, formaat: str, *args: Any) -> None:
        # Elke 400 ms is er een statusverzoek. Die apart loggen zou
        # software.jsonl razendsnel laten groeien. Echte fouten loggen we wel.
        pass

    def _stuur_bytes(self, httpcode: int, inhoud: bytes, inhoudstype: str, extra_koppen: dict[str, str] | None = None) -> None:
        self.send_response(httpcode)
        self.send_header('Content-Type', inhoudstype)
        self.send_header('Content-Length', str(len(inhoud)))
        self.send_header('Cache-Control', 'no-store')
        self.send_header('X-Content-Type-Options', 'nosniff')
        self.send_header('X-Frame-Options', 'DENY')
        self.send_header('Referrer-Policy', 'no-referrer')
        self.send_header('Content-Security-Policy', "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; media-src 'self'; connect-src 'self'; object-src 'none'; frame-ancestors 'none'; base-uri 'none'")
        for naam, waarde in (extra_koppen or {}).items():
            self.send_header(naam, waarde)
        self.end_headers()
        self.wfile.write(inhoud)

    def _stuur_multimedia_met_range_ondersteuning(self, geluid_id: str) -> None:
        """Stuur alleen geïmporteerde bestanden, in blokken en met seek-ondersteuning.

        Een browser zoekt in video's met HTTP Range. Zonder Range werkt MP4
        vaak niet en zou Python anders het complete bestand in RAM laden.
        """
        item = self.server.bediening.zoek_geluid_met_id(geluid_id)
        veiligemap = (self.server.media_map / 'geluiden').resolve()
        bron = item.bestandspad.resolve()
        if not bron.is_relative_to(veiligemap) or not bron.is_file():
            raise OngeldigWebverzoek('WEB-050: preview kan alleen met media die via het dashboard is geïmporteerd.')
        inhoudstypen = {'.mp3': 'audio/mpeg', '.wav': 'audio/wav', '.mp4': 'video/mp4'}
        inhoudstype = inhoudstypen.get(bron.suffix.lower())
        if inhoudstype is None:
            raise OngeldigWebverzoek('WEB-051: mediaformaat wordt niet ondersteund.')
        totaal = bron.stat().st_size
        if totaal <= 0:
            raise OngeldigWebverzoek('WEB-052: het mediabestand is leeg.')
        begin, einde, httpcode = 0, totaal - 1, 200
        bereik = self.headers.get('Range')
        if bereik:
            gevonden = re.fullmatch(r'bytes=(\d*)-(\d*)', bereik.strip())
            if gevonden is None or (not gevonden[1] and not gevonden[2]):
                self.send_response(416)
                self.send_header('Content-Range', f'bytes */{totaal}')
                self.send_header('Content-Length', '0')
                self.end_headers()
                return
            if not gevonden[1]:
                laatste_bytes = int(gevonden[2])
                begin = max(0, totaal - laatste_bytes)
            else:
                begin = int(gevonden[1])
                einde = int(gevonden[2]) if gevonden[2] else totaal - 1
            einde = min(einde, totaal - 1)
            if begin > einde or begin >= totaal:
                self.send_response(416)
                self.send_header('Content-Range', f'bytes */{totaal}')
                self.send_header('Content-Length', '0')
                self.end_headers()
                return
            httpcode = 206
        self.send_response(httpcode)
        self.send_header('Content-Type', inhoudstype)
        self.send_header('Content-Length', str(einde - begin + 1))
        self.send_header('Accept-Ranges', 'bytes')
        self.send_header('Cache-Control', 'no-store')
        self.send_header('X-Content-Type-Options', 'nosniff')
        self.send_header('Content-Security-Policy', "default-src 'self'; media-src 'self'; script-src 'self'; object-src 'none'")
        if httpcode == 206:
            self.send_header('Content-Range', f'bytes {begin}-{einde}/{totaal}')
        self.end_headers()
        nog = einde - begin + 1
        with bron.open('rb') as bestand:
            bestand.seek(begin)
            while nog:
                blok = bestand.read(min(MEDIA_UITVOERBLOK_BYTES, nog))
                if not blok:
                    raise OSError('WEB-053: bronbestand veranderde tijdens het afspelen.')
                self.wfile.write(blok)
                nog -= len(blok)

    def _stuur_tijdelijk_downloadbestand(self, pad: Path, bestandsnaam: str) -> None:
        """Stream het ZIP-bestand naar de browser, nooit als één grote bytestring.

        Het tijdelijke bestand wordt ook na een afgebroken download verwijderd.
        """
        try:
            self.send_response(200)
            self.send_header('Content-Type', 'application/zip')
            self.send_header('Content-Disposition', f'attachment; filename="{bestandsnaam}"')
            self.send_header('Content-Length', str(pad.stat().st_size))
            self.send_header('Cache-Control', 'no-store')
            self.send_header('X-Content-Type-Options', 'nosniff')
            self.end_headers()
            with pad.open('rb') as bestand:
                while blok := bestand.read(BESTANDSBUFFER_IN_BYTES):
                    self.wfile.write(blok)
        finally:
            pad.unlink(missing_ok=True)

    def _stuur_los_mediabestand(self, pad: Path, bestandsnaam: str, inhoudstype: str) -> None:
        """Lever MP3, MP4 of GIF als download en verwijder het tijdelijke bestand.

        De exportmodule levert uitsluitend geschoonde ASCII-bestandsnamen.
        De browser krijgt nooit een pad naar de schijf van de gebruiker.
        """
        try:
            self.send_response(200)
            self.send_header('Content-Type', inhoudstype)
            self.send_header('Content-Disposition', f'attachment; filename="{bestandsnaam}"')
            self.send_header('Content-Length', str(pad.stat().st_size))
            self.send_header('Cache-Control', 'no-store')
            self.send_header('X-Content-Type-Options', 'nosniff')
            self.send_header('X-Frame-Options', 'DENY')
            self.end_headers()
            with pad.open('rb') as bron:
                while blok := bron.read(BESTANDSBUFFER_IN_BYTES):
                    self.wfile.write(blok)
        finally:
            # Ook bij wegklikken of een afgebroken download ruimen we op.
            pad.unlink(missing_ok=True)

    def _stuur_json(self, httpcode: int, gegevens: Any) -> None:
        ruwe_data = json.dumps(gegevens, ensure_ascii=False, default=str).encode('utf-8')
        self._stuur_bytes(httpcode, ruwe_data, 'application/json; charset=utf-8')

    def _controleer_herkomst(self, aanpassing: bool) -> None:
        # Zonder hostcontrole kan DNS-rebinding een lokaal proces benaderen.
        host = self.headers.get('Host', '').lower()
        geldige_hosts = {f'127.0.0.1:{self.server.server_port}', f'localhost:{self.server.server_port}'}
        if host not in geldige_hosts:
            raise OngeldigWebverzoek('WEB-021: dit dashboard is alleen op deze computer bereikbaar.')
        if aanpassing:
            if self.headers.get('X-Drost-Token') != self.server.schrijf_token:
                raise OngeldigWebverzoek('WEB-022: ongeldige beveiligingscode. Herlaad het dashboard.')
            origin = self.headers.get('Origin')
            if origin and origin.lower() not in {
                f'http://127.0.0.1:{self.server.server_port}',
                f'http://localhost:{self.server.server_port}',
            }:
                raise OngeldigWebverzoek('WEB-023: verzoek kwam niet uit het lokale dashboard.')

    def _lees_invoer_json(self) -> dict[str, Any]:
        if not self.headers.get('Content-Type', '').startswith('application/json'):
            raise OngeldigWebverzoek('WEB-024: JSON-inhoudstype ontbreekt.')
        lengte = self._controleer_grootte_van_verzoek(GROOTSTE_JSON_IN_BYTES)
        try:
            gegevens = json.loads(self.rfile.read(lengte).decode('utf-8'))
        except (UnicodeError, json.JSONDecodeError) as fout:
            raise OngeldigWebverzoek('WEB-025: verzoek bevat geen geldige JSON.') from fout
        if not isinstance(gegevens, dict):
            raise OngeldigWebverzoek('WEB-026: verwacht een JSON-object.')
        return gegevens

    def _controleer_grootte_van_verzoek(self, maximaal: int) -> int:
        lengte = self.headers.get('Content-Length', '')
        try:
            aantal_bytes = int(lengte)
        except (TypeError, ValueError) as fout:
            raise OngeldigWebverzoek('WEB-027: lengte van het bestand of verzoek ontbreekt.') from fout
        if aantal_bytes < 1 or aantal_bytes > maximaal:
            raise OngeldigWebverzoek(f'WEB-028: verzoek is leeg of groter dan {maximaal // (1024*1024)} MiB.')
        return aantal_bytes

    def _lees_een_bestand_in_blokken(self, map_voor_bestand: Path, extensie: str, maximaal: int) -> Path:
        lengte = self._controleer_grootte_van_verzoek(maximaal)
        map_voor_bestand.mkdir(parents=True, exist_ok=True)
        doelpad = map_voor_bestand / f'{uuid4()}{extensie}'
        tijdelijk_pad = map_voor_bestand / f'.{uuid4()}.deel'
        resterend = lengte
        try:
            with tijdelijk_pad.open('xb') as uitvoer:
                while resterend > 0:
                    blok = self.rfile.read(min(resterend, BESTANDSBUFFER_IN_BYTES))
                    if not blok:
                        raise OngeldigWebverzoek('WEB-029: de upload werd onverwacht onderbroken.')
                    uitvoer.write(blok)
                    resterend -= len(blok)
            tijdelijk_pad.replace(doelpad)
        except Exception:
            tijdelijk_pad.unlink(missing_ok=True)
            raise
        return doelpad

    def _controleer_geluids_id(self, tekst: str) -> str:
        try:
            return str(UUID(tekst))
        except (ValueError, AttributeError, TypeError) as fout:
            raise OngeldigWebverzoek('WEB-030: ongeldig geluidsnummer.') from fout

    def _verwerk_fout(self, fout: Exception, actie: str) -> None:
        # Een browser sluit bewust zijn oude MP4/MP3-download zodra je Stop,
        # Preview of een ander geluid kiest. Windows meldt dan soms 10053
        # of 10054. Dat is normaal browsergedrag, geen servercrash of HTTP 500.
        # We houden alleen de gebeurtenis bij en schrijven niets terug naar
        # de inmiddels gesloten socket. Echte lees- of decoderfouten blijven
        # onveranderd een volledige traceback krijgen.
        onderbroken_door_browser = (
            isinstance(fout, (BrokenPipeError, ConnectionAbortedError, ConnectionResetError))
            or getattr(fout, 'winerror', None) in (10053, 10054)
        )
        if actie.startswith('GET /media/') and onderbroken_door_browser:
            self.server.bediening.logboeken.softwarelogboek.info(
                'Browser heeft mediaverzoek voortijdig gestopt',
                extra={'gebeurtenis': 'media_verzoek_door_browser_geannuleerd',
                       'gegevens': {'pad': urlsplit(self.path).path,
                                   'type': type(fout).__name__,
                                   'winerror': getattr(fout, 'winerror', None)}},
            )
            self.close_connection = True
            return
        antwoord = maak_webfoutantwoord(fout, actie)
        # Eén logreferentie koppelt de fout in de browser aan zijn volledige
        # traceback in software.jsonl. De gebruiker ziet geen interne paden.
        self.server.bediening.logboeken.softwarelogboek.error(
            'Lokale webactie is mislukt',
            exc_info=(type(fout), fout, fout.__traceback__),
            extra={'gebeurtenis': 'webactie_mislukt', 'gegevens': {
                'foutcode': antwoord.inhoud['foutcode'],
                'oorzaakcode': antwoord.inhoud['oorzaakcode'],
                'referentie': antwoord.logreferentie,
                'actie': actie, 'fouttype': type(fout).__name__,
                'requestpad': urlsplit(self.path).path,
            }},
        )
        try:
            self._stuur_json(antwoord.http_status, antwoord.inhoud)
        except (OSError, ConnectionError):
            # Browser sloot tijdens terugsturen. De oorspronkelijke traceback
            # blijft met dezelfde referentie in de softwarelogging bewaard.
            pass
        self.close_connection = True

    def _stuur_directe_niveaus_naar_browser(self) -> None:
        """Verstuur lichte niveauupdates via één permanente HTTP-verbinding.

        EventSource is native in browsers en vraagt geen extra Python-pakket.
        De audiocallback doet GEEN netwerkwerk. Deze HTTP-werkdraad leest
        uitsluitend reeds berekende gegevens, maximaal 30 keer per seconde.
        """
        # Voorkom dat een andere website ongemerkt een langdurige verbinding
        # opent. De gewone Host-controle wordt al in do_GET uitgevoerd.
        herkomst = self.headers.get('Origin')
        if herkomst and herkomst.lower() not in {
            f'http://127.0.0.1:{self.server.server_port}',
            f'http://localhost:{self.server.server_port}',
        }:
            raise OngeldigWebverzoek('WEB-075: niveaustroom kwam niet van het lokale dashboard.')
        if not self.server.maximale_live_verbindingen.acquire(blocking=False):
            self._stuur_json(429, maak_webantwoord_voor_onbekende_route('WEB-076', 'er zijn al vier niveaustromen geopend.'))
            return
        try:
            self.send_response(200)
            self.send_header('Content-Type', 'text/event-stream; charset=utf-8')
            self.send_header('Cache-Control', 'no-cache, no-store')
            self.send_header('Connection', 'close')
            self.send_header('X-Accel-Buffering', 'no')
            self.send_header('X-Content-Type-Options', 'nosniff')
            self.send_header('Content-Security-Policy', "default-src 'none'")
            self.end_headers()
            self.wfile.write(b'retry: 1000\n\n')
            self.wfile.flush()
            eindtijd = time.monotonic() + 45
            while time.monotonic() < eindtijd:
                # Metingen, geen samples en geen auditregels of databasewerk.
                niveaus = self.server.bediening.geef_directe_audioniveaus()
                bericht = ('event: niveau\ndata: '
                            + json.dumps(niveaus, separators=(',', ':'), allow_nan=False)
                            + '\n\n')
                self.wfile.write(bericht.encode('utf-8'))
                self.wfile.flush()
                time.sleep(1 / 30)
        except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError, TimeoutError):
            # Wegnavigeren of een tabblad sluiten is geen softwarefout.
            pass
        finally:
            self.close_connection = True
            self.server.maximale_live_verbindingen.release()

    def do_GET(self) -> None:
        pad = urlsplit(self.path).path
        try:
            self._controleer_herkomst(False)
            if pad == '/':
                pagina = (STATISCHE_MAP / 'dashboard.html').read_text(encoding='utf-8')
                pagina = pagina.replace('__DROST_TOKEN__', html.escape(self.server.schrijf_token, quote=True))
                self._stuur_bytes(200, pagina.encode('utf-8'), 'text/html; charset=utf-8')
            elif pad == '/stijl.css':
                self._stuur_bytes(200, (STATISCHE_MAP / 'stijl.css').read_bytes(), 'text/css; charset=utf-8')
            elif pad == '/dashboard.js':
                self._stuur_bytes(200, (STATISCHE_MAP / 'dashboard.js').read_bytes(), 'text/javascript; charset=utf-8')
            elif pad == '/video_synchronisatie.js':
                # Losse, testbare videologica. Alleen lezen vanaf eigen projectmap.
                self._stuur_bytes(200, (STATISCHE_MAP / 'video_synchronisatie.js').read_bytes(), 'text/javascript; charset=utf-8')
            elif pad == '/api/niveaus/live':
                self._stuur_directe_niveaus_naar_browser()
            elif pad == '/api/versie':
                # De dashboardtab kan naar een OUDE achtergrondinstantie verwijzen.
                # Toon daarom de werkelijk geladen codeversie én het proces-ID.
                # Dit endpoint bevat geen gegevens van gebruikers of microfoons.
                from app.diagnostiek.logboek import VERSIE_VAN_DE_APP
                self._stuur_json(200, {'versie': VERSIE_VAN_DE_APP, 'proces_id': os.getpid()})
            elif pad == '/api/status':
                self._stuur_json(200, self.server.bediening.geef_huidige_webstatus())
            elif pad == '/api/apparaten':
                microfoons = self.server.bediening.geef_apparaten_voor_de_webpagina()
                self._stuur_json(200, {
                    'microfoons': microfoons,
                    'standaard_microfoonnummer': (
                        self.server.bediening.geef_standaard_microfoonnummer_voor_de_webpagina(microfoons)
                    ),
                    'uitvoerapparaten': self.server.bediening.geef_uitvoerapparaten_voor_de_webpagina(),
                })
            elif pad == '/api/vereisten/vb-cable':
                # Alleen uitlezen; geen microfoon openen, installeren of wijzigen.
                self._stuur_json(200, self.server.bediening.geef_vb_cable_status())
            elif pad == '/api/bibliotheek':
                self._stuur_json(200, self.server.bediening.geef_geluidsbibliotheek())
            elif pad == '/api/recente-gebruik':
                query = parse_qs(urlsplit(self.path).query)
                try:
                    aantal = int(query.get('maximaal', ['12'])[0])
                except (ValueError, TypeError, IndexError) as fout:
                    raise OngeldigWebverzoek('RECENT-009: ongeldig maximum voor geschiedenis.') from fout
                self._stuur_json(200, self.server.bediening.recent_en_weergave.geef_recente_gebruik(aantal))
            elif pad == '/api/sneltoetsen':
                sneltoetsbediening = getattr(self.server, 'sneltoetsbediening', None)
                if sneltoetsbediening is None:
                    self._stuur_json(200, {'ondersteund': False, 'ingeschakeld': False,
                                           'combinaties': {}, 'mislukte_registraties': {}})
                else:
                    self._stuur_json(200, sneltoetsbediening.geef_huidige_instellingen())
            elif pad == '/api/instellingen/weergave':
                self._stuur_json(200, self.server.bediening.recent_en_weergave.geef_weergave())
            elif pad == '/api/instellingen/thema-profielen':
                self._stuur_json(200, {'profielen': self.server.bediening.recent_en_weergave.geef_eigen_themaprofielen()})
            elif pad == '/api/bibliotheek/exporteer':
                from app.webinterface.bibliotheek_archieven import maak_draagbaar_bibliotheekarchief
                # Een download is een leesverzoek. Stuur de ZIP direct in blokken:
                # geen enorme Blob in het browsergeheugen en geen tweede verzoek.
                parameters = parse_qs(urlsplit(self.path).query)
                nummers = parameters.get('id')
                archief = maak_draagbaar_bibliotheekarchief(self.server.bediening, self.server.media_map, nummers)
                schrijf_auditgebeurtenis(self.server.bediening.logboeken.auditlogboek,
                    'bibliotheek_geexporteerd', {'aantal': len(nummers) if nummers else 'alle'})
                self._stuur_tijdelijk_downloadbestand(archief, 'DrostSoundboard_bibliotheek.zip')
            elif re.fullmatch(r'/api/geluiden/[0-9a-f-]{36}/golfvorm', pad):
                import math
                parameters = parse_qs(urlsplit(self.path).query)
                try:
                    begin = float(parameters.get('begin', ['0'])[0])
                    duur = float(parameters.get('duur', ['120'])[0])
                    resolutie = int(parameters.get('resolutie', ['160'])[0])
                except (TypeError, ValueError, IndexError) as fout:
                    raise OngeldigWebverzoek('WEB-061: ongeldige golfvormparameters.') from fout
                if not (math.isfinite(begin) and math.isfinite(duur)
                        and begin >= 0 and 0.005 <= duur <= 120
                        and 16 <= resolutie <= 1200):
                    raise OngeldigWebverzoek('WEB-062: golfvorm moet maximaal twee minuten zijn.')
                geluid_id = self._controleer_geluids_id(pad.split('/')[3])
                self._stuur_json(200, self.server.bediening.geef_golfvorm_van_geluid(geluid_id, begin, duur, resolutie))
            elif re.fullmatch(r'/media/[0-9a-f-]{36}', pad):
                self._stuur_multimedia_met_range_ondersteuning(
                    self._controleer_geluids_id(pad.split('/')[-1])
                )
            elif re.fullmatch(r'/afbeeldingen/[0-9a-f-]{36}\.(?:png|jpg|jpeg|gif|webp)', pad):
                bestandsnaam = pad.rsplit('/', 1)[1]
                self._controleer_geluids_id(bestandsnaam.rsplit('.', 1)[0])
                afbeelding = self.server.media_map / 'afbeeldingen' / bestandsnaam
                if not afbeelding.is_file():
                    raise OngeldigWebverzoek('WEB-031: afbeelding bestaat niet meer.')
                extensie = afbeelding.suffix.lower()
                inhoudstype = {
                    '.png': 'image/png', '.jpg': 'image/jpeg', '.jpeg': 'image/jpeg',
                    '.gif': 'image/gif', '.webp': 'image/webp',
                }[extensie]
                self._stuur_bytes(200, afbeelding.read_bytes(), inhoudstype)
            else:
                self._stuur_json(404, maak_webantwoord_voor_onbekende_route('WEB-032', 'onbekende pagina of actie.'))
        except Exception as fout:
            self._verwerk_fout(fout, f'GET {pad}')

    def do_POST(self) -> None:
        pad = urlsplit(self.path).path
        try:
            self._controleer_herkomst(True)
            bediening = self.server.bediening
            if pad == '/api/verbinden':
                gegevens = self._lees_invoer_json()
                bediening.verbind_met_microfoon(gegevens.get('microfoonnummer'))
                self._stuur_json(202, {'melding': 'Verbinding wordt opgebouwd.'})
            elif pad == '/api/verbreken':
                self._lees_invoer_json()
                bediening.verbreek_de_verbinding()
                self._stuur_json(202, {'melding': 'Verbinding wordt verbroken.'})
            elif pad == '/api/effecten':
                gegevens = self._lees_invoer_json()
                bediening.zet_soundboard_aan_of_uit(gegevens.get('aan'))
                self._stuur_json(202, {'melding': 'Soundboardstand wordt aangepast.'})
            elif pad == '/api/stop':
                self._lees_invoer_json()
                bediening.stop_het_huidige_geluid()
                self._stuur_json(202, {'melding': 'Geluid wordt gestopt. Microfoon blijft aan.'})
            elif pad == '/api/monitor':
                gegevens = self._lees_invoer_json()
                bediening.stel_meeluisteren_in(gegevens.get('aan'), gegevens.get('uitvoernummer'))
                self._stuur_json(200, {'melding': 'Meeluisterinstellingen aangepast.'})
            elif pad == '/api/preview':
                gegevens = self._lees_invoer_json()
                bediening.registreer_preview(
                    self._controleer_geluids_id(gegevens.get('geluid_id')),
                    gegevens.get('actie'), gegevens.get('verstreken_seconden', 0.0),
                    gegevens.get('reden', 'niet_opgegeven'),
                    gegevens.get('afspeelbeurt'),
                )
                self._stuur_json(200, {'melding': 'Previewregistratie opgeslagen.'})
            elif pad == '/api/geluiden/importeer':
                self._importeer_audiobestand()
            elif re.fullmatch(r'/api/geluiden/[0-9a-f-]{36}/exporteer', pad):
                # Alleen via POST met schrijftoken. Eén conversie tegelijkertijd
                # voorkomt onnodige CPU-belasting tijdens het gamen of bellen.
                from app.webinterface.losse_media_exporteren import exporteer_geluid_als_los_bestand
                geluid_id = self._controleer_geluids_id(pad.split('/')[3])
                instellingen = self._lees_invoer_json()
                if not self.server.maximale_losse_exports.acquire(blocking=False):
                    raise OngeldigWebverzoek('EXP-015: een export loopt nog. Probeer het opnieuw als die klaar is.')
                try:
                    formaat = instellingen.get('formaat')
                    tijdelijk_pad, bestandsnaam, inhoudstype, werkelijke_duur = exporteer_geluid_als_los_bestand(
                        bediening, self.server.media_map, geluid_id, formaat,
                        instellingen.get('begin'), instellingen.get('duur'),
                    )
                    schrijf_auditgebeurtenis(bediening.logboeken.auditlogboek, 'los_mediaformaat_geexporteerd', {
                        'geluid_id': geluid_id, 'formaat': formaat,
                        'bestandsnaam': bestandsnaam, 'duur_seconden': round(werkelijke_duur, 3),
                        'bestandsgrootte_bytes': tijdelijk_pad.stat().st_size,
                    })
                    self._stuur_los_mediabestand(tijdelijk_pad, bestandsnaam, inhoudstype)
                finally:
                    self.server.maximale_losse_exports.release()
            elif pad == '/api/bibliotheek/exporteer':
                from app.webinterface.bibliotheek_archieven import maak_draagbaar_bibliotheekarchief
                gegevens = self._lees_invoer_json()
                nummers = gegevens.get('geluid_ids')
                tijdelijk_zip = maak_draagbaar_bibliotheekarchief(bediening, self.server.media_map, nummers)
                schrijf_auditgebeurtenis(bediening.logboeken.auditlogboek, 'bibliotheek_geexporteerd', {
                    'aantal_geluiden': len(nummers) if nummers is not None else 'alle',
                })
                self._stuur_tijdelijk_downloadbestand(tijdelijk_zip, 'DrostSoundboard_bibliotheek.zip')
            elif pad == '/api/bibliotheek/importeer':
                self._importeer_bibliotheekarchief()
            elif pad == '/api/bibliotheek/groep-toewijzen':
                gegevens = self._lees_invoer_json()
                groepsnummer = gegevens.get('groep_id')
                aantal = bediening.groepen.voeg_meerdere_geluiden_toe_aan_groep(
                    groepsnummer, gegevens.get('geluid_ids'))
                schrijf_auditgebeurtenis(bediening.logboeken.auditlogboek,
                    'meerdere_geluiden_in_groep_geplaatst', {'groep_id': groepsnummer, 'aantal': aantal})
                self._stuur_json(200, {'melding': f'{aantal} geluiden aan groep gekoppeld.', 'aantal': aantal})
            elif pad == '/api/bibliotheek/volume':
                gegevens = self._lees_invoer_json()
                # Alleen een selectie wordt veranderd. Bestaande persoonlijke
                # volumes veranderen nooit ongemerkt tijdens een update.
                aantal = bediening.favorieten.zet_volumes_van_geluiden_in_een_keer(
                    gegevens.get('geluid_ids'), gegevens.get('volume')
                )
                schrijf_auditgebeurtenis(bediening.logboeken.auditlogboek,
                    'meerdere_geluidsvolumes_gewijzigd', {'aantal': aantal,
                    'volume': gegevens.get('volume')})
                self._stuur_json(200, {'melding': f'{aantal} geluiden aangepast naar 100%.', 'aantal': aantal})
            elif pad == '/api/bibliotheek/verwijder-selectie':
                gegevens = self._lees_invoer_json()
                if gegevens.get('bevestiging') != 'VERWIJDER':
                    raise OngeldigWebverzoek('WEB-065: bevestig verwijderen expliciet.')
                aantal = bediening.geluidenbibliotheek.haal_meerdere_geluiden_uit_de_bibliotheek(
                    gegevens.get('geluid_ids'))
                schrijf_auditgebeurtenis(bediening.logboeken.auditlogboek,
                    'meerdere_geluiden_uit_bibliotheek_gehaald', {'aantal': aantal,
                    'bronbestanden_verwijderd': False})
                self._stuur_json(200, {'melding': f'{aantal} geluiden uit de bibliotheek gehaald. Bronbestanden blijven staan.',
                    'aantal': aantal})
            elif pad == '/api/sneltoetsen':
                gegevens = self._lees_invoer_json()
                sneltoetsbediening = getattr(self.server, 'sneltoetsbediening', None)
                if sneltoetsbediening is None:
                    raise OngeldigWebverzoek('HOTKEY-030: start de desktopversie voor globale sneltoetsen.')
                self._stuur_json(200, sneltoetsbediening.pas_instellingen_aan(gegevens))
            elif pad == '/api/instellingen/weergave':
                gegevens = self._lees_invoer_json()
                opgeslagen = bediening.recent_en_weergave.bewaar_weergave(gegevens)
                schrijf_auditgebeurtenis(bediening.logboeken.auditlogboek, 'weergave_aangepast', {
                    'thema': opgeslagen['thema'], 'gradient': opgeslagen['gradient'],
                    'gradientrichting': opgeslagen['gradientrichting'], 'compact': opgeslagen['compact'],
                    'eigen_accent': opgeslagen['accentkleur'] is not None,
                })
                self._stuur_json(200, opgeslagen)
            elif pad == '/api/instellingen/thema-profielen':
                gegevens = self._lees_invoer_json()
                opgeslagen = bediening.recent_en_weergave.bewaar_eigen_themaprofiel(
                    gegevens.get('naam'), gegevens.get('instellingen'))
                schrijf_auditgebeurtenis(bediening.logboeken.auditlogboek, 'eigen_thema_bewaard', {
                    'profiel_id': opgeslagen['id'], 'naam': opgeslagen['naam'],
                })
                self._stuur_json(200, opgeslagen)
            elif pad == '/api/recente-gebruik/wissen':
                self._lees_invoer_json()
                bediening.recent_en_weergave.wis_afspeelgeschiedenis()
                schrijf_auditgebeurtenis(bediening.logboeken.auditlogboek, 'recente_gebruik_gewist', {})
                self._stuur_json(200, {'melding': 'De afspeelgeschiedenis en recente groepen zijn gewist.'})
            elif pad == '/api/groepen/recent':
                gegevens = self._lees_invoer_json()
                groep_id = gegevens.get('groep_id')
                bediening.recent_en_weergave.registreer_groep_geopend(groep_id)
                schrijf_auditgebeurtenis(bediening.logboeken.auditlogboek, 'geluidsgroep_geopend', {
                    'groep_id': groep_id,
                })
                self._stuur_json(200, {'melding': 'Recent gebruikte groep bijgewerkt.'})
            elif pad == '/api/groepen':
                gegevens = self._lees_invoer_json()
                groeps_id = bediening.groepen.maak_groep(gegevens.get('naam'))
                schrijf_auditgebeurtenis(bediening.logboeken.auditlogboek, 'geluidsgroep_aangemaakt', {
                    'groep_id': groeps_id, 'naam': gegevens.get('naam'),
                })
                self._stuur_json(201, {'groep_id': groeps_id, 'melding': 'Groep aangemaakt.'})
            elif re.fullmatch(r'/api/groepen/[0-9a-f-]{36}', pad):
                groep_id = pad.split('/')[3]
                gegevens = self._lees_invoer_json()
                bediening.groepen.hernoem_groep(groep_id, gegevens.get('naam'))
                schrijf_auditgebeurtenis(bediening.logboeken.auditlogboek, 'geluidsgroep_hernoemd', {
                    'groep_id': groep_id, 'naam': gegevens.get('naam'),
                })
                self._stuur_json(200, {'melding': 'Groepsnaam opgeslagen.'})
            elif re.fullmatch(r'/api/geluiden/[0-9a-f-]{36}/groepen', pad):
                geluid_id = self._controleer_geluids_id(pad.split('/')[3])
                gegevens = self._lees_invoer_json()
                groep_ids = gegevens.get('groep_ids')
                bediening.groepen.bewaar_groepen_voor_geluid(geluid_id, groep_ids)
                schrijf_auditgebeurtenis(bediening.logboeken.auditlogboek, 'groepen_van_geluid_gewijzigd', {
                    'geluid_id': geluid_id, 'groep_ids': groep_ids,
                })
                self._stuur_json(200, {'melding': 'Groepen opgeslagen.'})
            elif pad == '/api/frontendfout':
                gegevens = self._lees_invoer_json()
                melding, stapel = gegevens.get('melding'), gegevens.get('stapel')
                if (not isinstance(melding, str) or not 1 <= len(melding) <= 1000
                        or not isinstance(stapel, str) or len(stapel) > 8000):
                    raise OngeldigWebverzoek('WEB-063: ongeldige foutinformatie uit de browser.')
                # JavaScript kent geen Python-traceback. De originele
                # JavaScript-stack bewaren we daarom als apart softwareveld.
                bediening.logboeken.softwarelogboek.error(
                    'Browserfout in dashboard', extra={'gebeurtenis': 'frontendfout', 'gegevens': {
                        'melding': melding, 'javascript_stack': stapel,
                    }}
                )
                self._stuur_json(200, {'melding': 'Browserfout geregistreerd.'})
            elif re.fullmatch(r'/api/groepen/[0-9a-f-]{36}/geluiden', pad):
                groep_id = pad.split('/')[3]
                gegevens = self._lees_invoer_json()
                geluid_id = self._controleer_geluids_id(gegevens.get('geluid_id'))
                bediening.groepen.verander_lidmaatschap(groep_id, geluid_id, True)
                schrijf_auditgebeurtenis(bediening.logboeken.auditlogboek, 'geluid_aan_groep_toegevoegd', {
                    'groep_id': groep_id, 'geluid_id': geluid_id,
                })
                self._stuur_json(200, {'melding': 'Geluid aan groep toegevoegd.'})
            elif re.fullmatch(r'/api/geluiden/[0-9a-f-]{36}/afspelen', pad):
                self._lees_invoer_json()
                geluid_id = self._controleer_geluids_id(pad.split('/')[3])
                bediening.speel_geluid_uit_de_bibliotheek(geluid_id)
                self._stuur_json(202, {'melding': 'Geluid wordt voorbereid en afgespeeld.'})
            elif re.fullmatch(r'/api/geluiden/[0-9a-f-]{36}/instellingen', pad):
                geluid_id = self._controleer_geluids_id(pad.split('/')[3])
                gegevens = self._lees_invoer_json()
                bediening.zoek_geluid_met_id(geluid_id)
                naam = gegevens.get('naam')
                begin = gegevens.get('beginpositie')
                volume = gegevens.get('volume')
                duur = gegevens.get('maximale_duur')
                beeldvoorkeur = gegevens.get('beeldvoorkeur', 'automatisch')
                # Valideer alles voordat we ook maar één veld in SQLite wijzigen.
                from app.webinterface.favorieten_en_instellingen import controleer_afspeelinstellingen
                from app.webinterface.extra_geluidsinformatie import controleer_aanvullende_informatie
                controleer_afspeelinstellingen(begin, volume, duur)
                controleer_aanvullende_informatie(gegevens.get('beschrijving', ''),
                    gegevens.get('gesproken_tekst', ''), gegevens.get('zoekwoorden', ''))
                if not isinstance(naam, str) or not 1 <= len(naam.strip()) <= 100:
                    raise OngeldigWebverzoek('WEB-033: geef een naam van 1 tot 100 tekens op.')
                bediening.geluidenbibliotheek.verander_de_naam_van_een_geluid(geluid_id, naam)
                bediening.favorieten.bewaar_afspeelinstellingen(geluid_id, begin, volume, duur, beeldvoorkeur)
                bediening.extra_informatie.bewaar_informatie(
                    geluid_id, gegevens.get('beschrijving', ''), gegevens.get('gesproken_tekst', ''), gegevens.get('zoekwoorden', ''))
                schrijf_auditgebeurtenis(bediening.logboeken.auditlogboek, 'geluidsinstellingen_gewijzigd', {
                    'geluid_id': geluid_id, 'naam': naam.strip(), 'begin': begin,
                    'volume': volume, 'maximale_duur': duur, 'beeldvoorkeur': beeldvoorkeur,
                    'beschrijving_lengte': len(gegevens.get('beschrijving', '')),
                    'gesproken_tekst_lengte': len(gegevens.get('gesproken_tekst', '')),
                })
                self._stuur_json(200, {'melding': 'Geluidsinstellingen opgeslagen.'})
            elif re.fullmatch(r'/api/geluiden/[0-9a-f-]{36}/afbeelding', pad):
                self._voeg_afbeelding_toe(pad.split('/')[3])
            elif re.fullmatch(r'/api/favorieten/(?:[1-9]|1[0-5])', pad):
                plek = controleer_favorietplek(int(pad.split('/')[-1]))
                gegevens = self._lees_invoer_json()
                geluid_id = self._controleer_geluids_id(gegevens.get('geluid_id'))
                bediening.favorieten.zet_een_geluid_op_een_vaste_plek(plek, geluid_id)
                schrijf_auditgebeurtenis(bediening.logboeken.auditlogboek, 'favoriet_ingesteld', {
                    'plek': plek, 'geluid_id': geluid_id,
                })
                self._stuur_json(200, {'melding': f'Favoriet {plek} is opgeslagen.'})
            elif pad == '/api/favorieten/wissel':
                gegevens = self._lees_invoer_json()
                bediening.favorieten.wissel_twee_favorietplekken(gegevens.get('eerste'), gegevens.get('tweede'))
                schrijf_auditgebeurtenis(bediening.logboeken.auditlogboek, 'favorieten_verwisseld', gegevens)
                self._stuur_json(200, {'melding': 'De favoriete plekken zijn verwisseld.'})
            else:
                self._stuur_json(404, maak_webantwoord_voor_onbekende_route('WEB-034', 'onbekende actie.'))
        except Exception as fout:
            self._verwerk_fout(fout, f'POST {pad}')

    def do_DELETE(self) -> None:
        pad = urlsplit(self.path).path
        try:
            self._controleer_herkomst(True)
            bediening = self.server.bediening
            if re.fullmatch(r'/api/instellingen/thema-profielen/[0-9a-f-]{36}', pad):
                profiel_id = pad.rsplit('/', 1)[1]
                self.server.bediening.recent_en_weergave.verwijder_eigen_themaprofiel(profiel_id)
                schrijf_auditgebeurtenis(self.server.bediening.logboeken.auditlogboek, 'eigen_thema_verwijderd', {
                    'profiel_id': profiel_id,
                })
                self._stuur_json(200, {'melding': 'Eigen thema verwijderd.'})
            elif re.fullmatch(r'/api/favorieten/(?:[1-9]|1[0-5])', pad):
                plek = controleer_favorietplek(int(pad.split('/')[-1]))
                bediening.favorieten.maak_een_favorietplek_leeg(plek)
                schrijf_auditgebeurtenis(bediening.logboeken.auditlogboek, 'favoriet_leeggemaakt', {'plek': plek})
                self._stuur_json(200, {'melding': f'Plek {plek} is leeg.'})
            elif re.fullmatch(r'/api/groepen/[0-9a-f-]{36}', pad):
                groep_id = pad.split('/')[3]
                bediening.groepen.verwijder_groep(groep_id)
                schrijf_auditgebeurtenis(bediening.logboeken.auditlogboek, 'geluidsgroep_verwijderd', {
                    'groep_id': groep_id,
                })
                self._stuur_json(200, {'melding': 'Groep verwijderd. Geluiden blijven bestaan.'})
            elif re.fullmatch(r'/api/groepen/[0-9a-f-]{36}/geluiden/[0-9a-f-]{36}', pad):
                groep_id, geluid_id = pad.split('/')[3], self._controleer_geluids_id(pad.split('/')[5])
                bediening.groepen.verander_lidmaatschap(groep_id, geluid_id, False)
                schrijf_auditgebeurtenis(bediening.logboeken.auditlogboek, 'geluid_uit_groep_gehaald', {
                    'groep_id': groep_id, 'geluid_id': geluid_id,
                })
                self._stuur_json(200, {'melding': 'Geluid uit groep gehaald.'})
            elif re.fullmatch(r'/api/geluiden/[0-9a-f-]{36}', pad):
                geluid_id = self._controleer_geluids_id(pad.split('/')[-1])
                item = bediening.zoek_geluid_met_id(geluid_id)
                bediening.favorieten.verwijder_referenties_naar_geluid(geluid_id)
                bediening.groepen.verwijder_koppelingen_naar_geluid(geluid_id)
                bediening.geluidenbibliotheek.haal_geluid_uit_de_bibliotheek(geluid_id)
                # Bewust geen unlink. Een verwijderd bibliotheekitem mag nooit
                # zomaar bestanden uit Downloads of een andere map wissen.
                schrijf_auditgebeurtenis(bediening.logboeken.auditlogboek, 'geluid_uit_bibliotheek_gehaald', {
                    'geluid_id': geluid_id, 'naam': item.eigen_naam,
                })
                self._stuur_json(200, {'melding': 'Geluid verwijderd uit de lijst. Bestand bewaard.'})
            else:
                self._stuur_json(404, maak_webantwoord_voor_onbekende_route('WEB-035', 'onbekende verwijderactie.'))
        except Exception as fout:
            self._verwerk_fout(fout, f'DELETE {pad}')

    def _importeer_bibliotheekarchief(self) -> None:
        """ZIP-upload eerst als tijdelijk bestand opslaan en na controle verwijderen."""
        from app.webinterface.bibliotheek_archieven import importeer_draagbaar_bibliotheekarchief
        tijdelijk_pad = self._lees_een_bestand_in_blokken(
            self.server.media_map / 'tijdelijk', '.zip', GROOTSTE_BIBLIOTHEEK_ARCHIEF_BYTES,
        )
        try:
            resultaat = importeer_draagbaar_bibliotheekarchief(
                self.server.bediening, self.server.media_map, tijdelijk_pad,
            )
            schrijf_auditgebeurtenis(self.server.bediening.logboeken.auditlogboek,
                                   'bibliotheek_geimporteerd', {'aantal': resultaat['aantal']})
            self._stuur_json(201, resultaat)
        finally:
            tijdelijk_pad.unlink(missing_ok=True)

    def _importeer_audiobestand(self) -> None:
        originele_naam = unquote(self.headers.get('X-Bestandsnaam', '')).replace('\\', '/').split('/')[-1].strip()
        extensie = Path(originele_naam).suffix.casefold()
        if extensie not in {'.mp3', '.wav', '.mp4'}:
            raise OngeldigWebverzoek('WEB-036: kies een MP3, WAV of MP4-bestand.')
        pad = self._lees_een_bestand_in_blokken(
            self.server.media_map / 'geluiden', extensie, GROOTSTE_AUDIO_UPLOAD_IN_BYTES
        )
        try:
            # soundfile.info kan MP3- en WAV-headers controleren zonder het
            # complete (mogelijk lange) bestand te decoderen.
            if extensie == '.mp4':
                # Controleer beide sporen voordat een nieuwe bibliotheekregel
                # wordt opgeslagen. Een video zonder audio is geen soundboardfragment.
                controleer_of_mp4_audio_en_video_bevat(pad)
            else:
                import soundfile as geluidsdecoder
                try:
                    geluidsdecoder.info(str(pad))
                except (RuntimeError, ValueError, OSError) as decoderfout:
                    raise OngeldigWebverzoek(
                        f"WEB-038: '{originele_naam}' is geen leesbaar MP3- of WAV-bestand."
                    ) from decoderfout
            bestand = controleer_of_geluidsbestand_gebruikt_mag_worden(pad)
            item = self.server.bediening.geluidenbibliotheek.voeg_geluidsbestanden_toe([bestand])[0]
            nieuwe_naam = Path(originele_naam).stem.strip()[:100]
            if nieuwe_naam:
                self.server.bediening.geluidenbibliotheek.verander_de_naam_van_een_geluid(
                    item.geluid_id, nieuwe_naam
                )
            if extensie == '.mp4':
                # Een stil videoframe is veel lichter dan tien browser-video's
                # die alleen maar een poster moeten tonen in de bibliotheek.
                from app.audio.mp4_verwerken import maak_miniatuur_van_videobeeld
                miniatuur = self.server.media_map / 'afbeeldingen' / f'{item.geluid_id}.png'
                if maak_miniatuur_van_videobeeld(pad, miniatuur):
                    self.server.bediening.favorieten.bewaar_afbeelding_voor_geluid(item.geluid_id, miniatuur.name)
                else:
                    self.server.bediening.logboeken.softwarelogboek.warning(
                        'Videominiatuur kon niet worden gemaakt',
                        extra={'gebeurtenis': 'videominiatuur_mislukt', 'gegevens': {'geluid_id': item.geluid_id}},
                    )
            schrijf_auditgebeurtenis(
                self.server.bediening.logboeken.auditlogboek, 'geluid_toegevoegd_aan_bibliotheek', {
                    'geluid_id': item.geluid_id, 'naam': nieuwe_naam or item.eigen_naam,
                    'bronbestandsnaam': originele_naam, 'grootte_bytes': pad.stat().st_size,
                }
            )
            self._stuur_json(201, {'melding': 'Geluid toegevoegd aan bibliotheek.', 'geluid_id': item.geluid_id})
        except Exception:
            pad.unlink(missing_ok=True)
            raise

    def _voeg_afbeelding_toe(self, geluid_id_van_pad: str) -> None:
        geluid_id = self._controleer_geluids_id(geluid_id_van_pad)
        bediening = self.server.bediening
        bediening.zoek_geluid_met_id(geluid_id)
        originele_naam = unquote(self.headers.get('X-Bestandsnaam', '')).replace('\\', '/').split('/')[-1].strip()
        extensie = Path(originele_naam).suffix.casefold()
        if extensie not in TOEGESTANE_AFBEELDINGEN:
            raise OngeldigWebverzoek('WEB-037: afbeeldingen moeten PNG, JPG, WEBP of GIF zijn.')
        pad = self._lees_een_bestand_in_blokken(
            self.server.media_map / 'afbeeldingen', extensie, GROOTSTE_AFBEELDING_IN_BYTES
        )
        try:
            controleer_of_afbeelding_echt_een_afbeelding_is(pad, extensie)
            if extensie == '.gif':
                # Bewaar het eerste frame apart. Anders blijft iedere GIF al
                # bewegen in de bibliotheek, zelfs wanneer niets wordt gespeeld.
                from PIL import Image
                miniatuur = pad.with_suffix('.png')
                try:
                    with Image.open(pad) as afbeelding:
                        afbeelding.seek(0)
                        eerste_frame = afbeelding.convert('RGB')
                        eerste_frame.thumbnail((480, 480))
                        eerste_frame.save(miniatuur, 'PNG')
                except Exception as fout:
                    miniatuur.unlink(missing_ok=True)
                    raise OngeldigWebverzoek('WEB-054: de GIF kon niet veilig worden verwerkt.') from fout
            bediening.favorieten.bewaar_afbeelding_voor_geluid(geluid_id, pad.name)
            schrijf_auditgebeurtenis(bediening.logboeken.auditlogboek, 'geluidsafbeelding_gewijzigd', {
                'geluid_id': geluid_id, 'afbeeldingstype': extensie,
            })
            self._stuur_json(201, {'melding': 'Afbeelding toegevoegd.'})
        except Exception:
            pad.unlink(missing_ok=True)
            raise
