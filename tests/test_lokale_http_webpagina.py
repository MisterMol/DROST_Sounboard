"""Loopback-server en upload testen zonder Razer-hardware."""

from contextlib import closing
from io import BytesIO
import json
import os
from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import patch
from urllib.error import HTTPError
from urllib.request import Request, urlopen
import wave

from app.diagnostiek.logboek import maak_logboeken_klaar, sluit_logboeken_netjes_af
from app.webinterface.bediening_van_de_audiomotor import WebbedieningVanDrostSoundboard
from app.webinterface.lokale_webserver import LokaleWebserverVanDrostSoundboard


class TestLokaleWebserver(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tijdelijke_map = tempfile.TemporaryDirectory()
        cls.map = Path(cls.tijdelijke_map.name)
        cls.oude_appdata = os.environ.get('LOCALAPPDATA')
        os.environ['LOCALAPPDATA'] = str(cls.map)
        cls.logs = maak_logboeken_klaar(cls.map / 'logboeken')
        cls.bediening = WebbedieningVanDrostSoundboard(object(), cls.logs, cls.map / 'database.sqlite3')
        cls.server = LokaleWebserverVanDrostSoundboard(('127.0.0.1', 0), cls.bediening)
        cls.url = f'http://127.0.0.1:{cls.server.server_port}'
        cls.draad = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.draad.start()

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.draad.join(timeout=4)
        cls.bediening.sluit_alle_audio_af()
        sluit_logboeken_netjes_af(cls.logs)
        if cls.oude_appdata is None:
            os.environ.pop('LOCALAPPDATA', None)
        else:
            os.environ['LOCALAPPDATA'] = cls.oude_appdata
        cls.tijdelijke_map.cleanup()

    def verzoek(self, pad, methode='GET', gegevens=None, token=True, bestandsnaam=None):
        headers = {}
        if methode != 'GET' and token:
            headers['X-Drost-Token'] = self.server.schrijf_token
        if bestandsnaam is not None:
            headers['X-Bestandsnaam'] = bestandsnaam
            headers['Content-Type'] = 'application/octet-stream'
            data = gegevens
        elif methode == 'POST':
            headers['Content-Type'] = 'application/json'
            data = json.dumps(gegevens or {}).encode('utf-8')
        else:
            data = None
        verzoek = Request(self.url + pad, data=data, headers=headers, method=methode)
        with urlopen(verzoek, timeout=5) as antwoord:
            ruwe_data=antwoord.read()
            return antwoord.status, (json.loads(ruwe_data) if antwoord.headers.get_content_type() == 'application/json' else ruwe_data)

    def test_html_kan_lokaal_geopend_worden(self):
        status, inhoud = self.verzoek('/')
        self.assertEqual(status, 200)
        self.assertIn(b'Mijn 15 favorieten', inhoud)
        self.assertIn(self.server.schrijf_token.encode(), inhoud)

    def test_dashboard_biedt_javascript_en_css(self):
        self.assertEqual(self.verzoek('/video_synchronisatie.js')[0], 200)
        self.assertEqual(self.verzoek('/dashboard.js')[0], 200)
        self.assertEqual(self.verzoek('/stijl.css')[0], 200)

    def test_api_apparaten_geeft_windows_standaard_mee_aan_dashboard(self):
        microfoons = [{'nummer': 2, 'naam': 'Microfoon (Logitech)'},
                      {'nummer': 7, 'naam': 'Microfoon (Realtek)'}]
        with patch.object(self.bediening, 'geef_apparaten_voor_de_webpagina', return_value=microfoons), \
             patch.object(self.bediening, 'geef_standaard_microfoonnummer_voor_de_webpagina', return_value=7) as standaard, \
             patch.object(self.bediening, 'geef_uitvoerapparaten_voor_de_webpagina', return_value=[]):
            code, inhoud = self.verzoek('/api/apparaten')
        self.assertEqual(code, 200)
        self.assertEqual(inhoud['standaard_microfoonnummer'], 7)
        self.assertEqual(inhoud['microfoons'], microfoons)
        standaard.assert_called_once_with(microfoons)

    def test_actief_achtergrondproces_geeft_zijn_eigen_versie_terug(self):
        # Een dubbelklik kan anders een nog draaiende vorige installatie openen.
        # Dit endpoint laat zien welke code werkelijk in RAM is geladen.
        from app.diagnostiek.logboek import VERSIE_VAN_DE_APP
        httpcode, inhoud = self.verzoek('/api/versie')
        self.assertEqual(httpcode, 200)
        self.assertEqual(inhoud['versie'], VERSIE_VAN_DE_APP)
        self.assertEqual(inhoud['proces_id'], os.getpid())
        self.assertEqual(sorted(inhoud), ['proces_id', 'versie'])

    def test_api_fout_keert_met_een_logreferentie_terug(self):
        # Zo kan een gebruiker een onverwachte fout melden zonder een screenshot
        # van zijn privépaden of een hele Python-traceback te delen.
        from unittest.mock import patch
        with patch.object(self.bediening, 'geef_geluidsbibliotheek',
                          side_effect=RuntimeError('TEST geheim Windows-pad')):
            with self.assertRaises(HTTPError) as antwoord:
                self.verzoek('/api/bibliotheek')
        self.assertEqual(antwoord.exception.code, 500)
        gegevens = json.loads(antwoord.exception.read())
        self.assertEqual(gegevens['foutcode'], 'WEB-999')
        self.assertEqual(gegevens['actie'], 'GET /api/bibliotheek')
        self.assertNotIn('geheim Windows-pad', gegevens['fout'])
        referentie = gegevens['referentie']
        self.assertEqual(len(referentie), 12)
        for handler in self.logs.softwarelogboek.handlers:
            handler.flush()
        inhoud = (self.map / 'logboeken/software.jsonl').read_text(encoding='utf-8')
        self.assertIn(referentie, inhoud)
        self.assertIn('Traceback', inhoud)

    def test_oude_webstarter_meldt_dat_hotkeys_alleen_met_desktop_werken(self):
        status, inhoud = self.verzoek('/api/sneltoetsen')
        self.assertEqual(status, 200)
        self.assertFalse(inhoud['ondersteund'])

    def test_sneltoetsinstellingen_mogen_niet_zonder_csrf_token_wijzigen(self):
        from unittest.mock import MagicMock
        oude = getattr(self.server, 'sneltoetsbediening', None)
        self.server.sneltoetsbediening = MagicMock()
        try:
            with self.assertRaises(HTTPError) as fout:
                self.verzoek('/api/sneltoetsen', 'POST',
                    {'ingeschakeld': False, 'combinaties': {}}, token=False)
            self.assertEqual(fout.exception.code, 400)
            self.server.sneltoetsbediening.pas_instellingen_aan.assert_not_called()
        finally:
            if oude is None:
                del self.server.sneltoetsbediening
            else:
                self.server.sneltoetsbediening = oude

    def test_hotkey_api_gebruikt_de_aanwezige_windows_bediening(self):
        from unittest.mock import MagicMock
        oude = getattr(self.server, 'sneltoetsbediening', None)
        nep = MagicMock()
        nep.geef_huidige_instellingen.return_value = {'ondersteund': True,
            'ingeschakeld': False, 'combinaties': {}, 'mislukte_registraties': {}}
        nep.pas_instellingen_aan.return_value = nep.geef_huidige_instellingen.return_value
        self.server.sneltoetsbediening = nep
        try:
            self.assertTrue(self.verzoek('/api/sneltoetsen')[1]['ondersteund'])
            self.assertEqual(self.verzoek('/api/sneltoetsen', 'POST',
                {'ingeschakeld': False, 'combinaties': {}})[0], 200)
            nep.pas_instellingen_aan.assert_called_once()
        finally:
            if oude is None:
                del self.server.sneltoetsbediening
            else:
                self.server.sneltoetsbediening = oude

    def test_vb_cable_status_is_uitleesbaar_zonder_schrijven(self):
        """Status moet leesbaar zijn zonder audiostream of CSRF-schrijfactie."""
        from unittest.mock import patch
        meting = {'status': 'ontbreekt', 'bruikbaar': False,
                  'melding': 'VB-CABLE niet zichtbaar', 'officiele_website': 'https://vb-audio.com/Cable/'}
        with patch.object(self.bediening, 'geef_vb_cable_status', return_value=meting) as controle:
            status, inhoud = self.verzoek('/api/vereisten/vb-cable')
        self.assertEqual(status, 200)
        self.assertEqual(inhoud, meting)
        controle.assert_called_once_with()

    def test_status_begint_als_niet_verbonden(self):
        status, inhoud = self.verzoek('/api/status')
        self.assertEqual(status, 200)
        self.assertEqual(inhoud['toestand'], 'verbroken')

    def test_snellere_niveaus_gebruiken_een_eigen_gebeurtenissenstroom(self):
        # Lees één meetbericht. Anders blijft een werkende SSE-verbinding
        # bewust open en zou de test ten onrechte blijven wachten.
        with urlopen(self.url + '/api/niveaus/live', timeout=3) as antwoord:
            self.assertEqual(antwoord.status, 200)
            self.assertEqual(antwoord.headers.get_content_type(), 'text/event-stream')
            self.assertIn(b'retry: 1000', antwoord.readline())
            self.assertEqual(antwoord.readline().strip(), b'')
            self.assertEqual(antwoord.readline().strip(), b'event: niveau')
            regel = antwoord.readline().decode().strip()
            self.assertTrue(regel.startswith('data: '))
            gegevens = json.loads(regel.removeprefix('data: '))
            self.assertFalse(gegevens['gemeten'])
            self.assertEqual(gegevens['microfoon_rms'], 0.0)
            self.assertEqual(gegevens['kabel_rms'], 0.0)
            self.assertIsInstance(gegevens['verzonden_op_ms'], int)

    def test_csrf_token_is_verplicht_bij_wijzigingen(self):
        with self.assertRaises(HTTPError) as fout:
            self.verzoek('/api/stop', 'POST', {}, token=False)
        self.assertEqual(fout.exception.code, 400)

    def test_wav_import_favoriet_instellen_hernoemen_en_verwijderen(self):
        inhoud = BytesIO()
        with wave.open(inhoud, 'wb') as geluid:
            geluid.setnchannels(1)
            geluid.setsampwidth(2)
            geluid.setframerate(48000)
            geluid.writeframes(b'\x00\x00' * 400)
        status, nieuw = self.verzoek('/api/geluiden/importeer', 'POST', inhoud.getvalue(),
                                     bestandsnaam='Mijn%20testgeluid.wav')
        self.assertEqual(status, 201)
        geluid_id = nieuw['geluid_id']
        self.verzoek('/api/favorieten/7', 'POST', {'geluid_id': geluid_id})
        _, bibliotheek = self.verzoek('/api/bibliotheek')
        self.assertEqual(bibliotheek['favorieten'][6], geluid_id)
        self.assertTrue(any(i['naam'] == 'Mijn testgeluid' for i in bibliotheek['geluiden']))
        status,_=self.verzoek(f'/api/geluiden/{geluid_id}/instellingen','POST', {
            'naam':'Eigen naam', 'beginpositie':0.0,'volume':0.35,'maximale_duur':120,
        })
        self.assertEqual(status,200)
        _, bibliotheek=self.verzoek('/api/bibliotheek')
        self.assertEqual(next(i for i in bibliotheek['geluiden'] if i['id'] == geluid_id)['naam'],'Eigen naam')
        self.verzoek(f'/api/geluiden/{geluid_id}','DELETE')
        _, bibliotheek=self.verzoek('/api/bibliotheek')
        self.assertIsNone(bibliotheek['favorieten'][6])

    def test_afbeelding_met_html_inhoud_wordt_afgewezen(self):
        _, item=self.verzoek('/api/geluiden/importeer','POST',self.maak_geldig_wav(),
                             bestandsnaam='plaatje-test.wav')
        with self.assertRaises(HTTPError) as fout:
            self.verzoek(f"/api/geluiden/{item['geluid_id']}/afbeelding", 'POST',
                         b'<html>geen afbeelding</html>', bestandsnaam='verdacht.png')
        self.assertEqual(fout.exception.code,400)

    def test_echte_gif_wordt_lokaal_opgeslagen_en_served(self):
        _, item=self.verzoek('/api/geluiden/importeer','POST',self.maak_geldig_wav(),
                             bestandsnaam='gif-demo.wav')
        # Een minimale GIF volstaat om de beeldhandtekening te testen.
        gif = (b'GIF89a\x01\x00\x01\x00\x80\x00\x00\x00\x00\x00\xff\xff\xff'
               b'!\xf9\x04\x01\x00\x00\x00\x00,\x00\x00\x00\x00'
               b'\x01\x00\x01\x00\x00\x02\x02D\x01\x00;')
        code,_=self.verzoek(f"/api/geluiden/{item['geluid_id']}/afbeelding", 'POST', gif, bestandsnaam='animatie.gif')
        self.assertEqual(code,201)
        _,bibliotheek=self.verzoek('/api/bibliotheek')
        afbeelding=next(x for x in bibliotheek['geluiden'] if x['id']==item['geluid_id'])['afbeelding']
        self.assertTrue(afbeelding.endswith('.gif'))
        code,ruwe_bytes=self.verzoek(afbeelding)
        self.assertEqual(code,200)
        self.assertEqual(ruwe_bytes,gif)

    def test_corrupte_mp3_wordt_met_nederlandse_foutcode_geweigerd(self):
        with self.assertRaises(HTTPError) as fout:
            self.verzoek('/api/geluiden/importeer','POST',b'geen echte MP3',bestandsnaam='fout.mp3')
        self.assertEqual(fout.exception.code,400)
        melding=json.loads(fout.exception.read())['fout']
        self.assertIn('WEB-038',melding)

    def test_instelscherm_weigert_een_fragment_van_meer_dan_120_seconden(self):
        _,item=self.verzoek('/api/geluiden/importeer','POST',self.maak_geldig_wav(),bestandsnaam='duur-test.wav')
        with self.assertRaises(HTTPError) as fout:
            self.verzoek(f"/api/geluiden/{item['geluid_id']}/instellingen",'POST', {
                'naam':'Mag niet','beginpositie':0,'volume':.35,'maximale_duur':121,
            })
        self.assertEqual(fout.exception.code,400)
        _,bibliotheek=self.verzoek('/api/bibliotheek')
        objectje=next(x for x in bibliotheek['geluiden'] if x['id']==item['geluid_id'])
        self.assertEqual(objectje['maximale_duur'],120)
        self.assertNotEqual(objectje['naam'],'Mag niet')

    def maak_geldig_wav(self):
        inhoud=BytesIO()
        with wave.open(inhoud,'wb') as geluid:
            geluid.setnchannels(1);geluid.setsampwidth(2);geluid.setframerate(48000)
            geluid.writeframes(b'\x00\x00' * 200)
        return inhoud.getvalue()


    def test_media_preview_kan_audio_met_range_lezen_zonder_cable(self):
        _, item = self.verzoek('/api/geluiden/importeer', 'POST', self.maak_geldig_wav(),
                               bestandsnaam='test_preview.wav')
        mediaadres = f"/media/{item['geluid_id']}"
        headers = {'Range': 'bytes=0-31'}
        with urlopen(Request(self.url + mediaadres, headers=headers), timeout=5) as antwoord:
            self.assertEqual(antwoord.status, 206)
            self.assertEqual(antwoord.headers['Content-Type'], 'audio/wav')
            self.assertEqual(len(antwoord.read()), 32)
        with urlopen(Request(self.url + mediaadres), timeout=5) as antwoord:
            self.assertEqual(antwoord.status, 200)
            self.assertTrue(antwoord.read().startswith(b'RIFF'))

    def test_weergave_ophalen_opslaan_en_herstartbestendig(self):
        _, begin = self.verzoek('/api/instellingen/weergave')
        self.assertIn(begin['thema'], ('obsidian', 'midnight', 'amethyst', 'ember', 'monochrome'))
        nieuw = {'thema': 'ember', 'accentkleur': '#FFE0BB', 'gradient': 'duidelijk',
                 'gradientrichting': 'onder', 'compact': True}
        code, voorkeur = self.verzoek('/api/instellingen/weergave', 'POST', nieuw)
        self.assertEqual(code, 200)
        self.assertEqual(voorkeur['thema'], 'ember')
        self.assertEqual(voorkeur['palet']['accent'], '#FFE0BB')
        self.assertEqual(self.verzoek('/api/instellingen/weergave')[1]['compact'], True)

    def test_verkeerde_kleur_en_ontbrekende_token_worden_geweigerd(self):
        nieuw = {'thema': 'obsidian', 'accentkleur': 'url(http://onveilig)',
                 'gradient': 'subtiel', 'gradientrichting': 'rechtsboven', 'compact': False}
        with self.assertRaises(HTTPError) as fout:
            self.verzoek('/api/instellingen/weergave', 'POST', nieuw)
        self.assertEqual(fout.exception.code, 400)
        with self.assertRaises(HTTPError) as fout:
            self.verzoek('/api/recente-gebruik/wissen', 'POST', {}, token=False)
        self.assertEqual(fout.exception.code, 400)

    def test_eigen_themaprofielen_kunnen_veilig_worden_bewaard_en_gewist(self):
        instellingen = {'thema': 'monochrome', 'accentkleur': '#D2EAF0',
                        'gradient': 'uit', 'gradientrichting': 'rechtsboven', 'compact': False}
        code, profiel = self.verzoek('/api/instellingen/thema-profielen', 'POST', {
            'naam': 'Mijn minimalistische thema', 'instellingen': instellingen,
        })
        self.assertEqual(code, 200)
        self.assertEqual(profiel['naam'], 'Mijn minimalistische thema')
        self.assertTrue(any(x['id'] == profiel['id'] for x in
                            self.verzoek('/api/instellingen/thema-profielen')[1]['profielen']))
        with self.assertRaises(HTTPError) as fout:
            self.verzoek('/api/instellingen/thema-profielen', 'POST', {
                'naam': '<script>', 'instellingen': {**instellingen, 'accentkleur': 'url(https://voorbeeld.invalid)'}
            })
        self.assertEqual(fout.exception.code, 400)
        code, _ = self.verzoek('/api/instellingen/thema-profielen/' + profiel['id'], 'DELETE')
        self.assertEqual(code, 200)
        self.assertFalse(any(x['id'] == profiel['id'] for x in
                             self.verzoek('/api/instellingen/thema-profielen')[1]['profielen']))

    def test_recente_groep_en_gescheiden_previewregistratie(self):
        _, item = self.verzoek('/api/geluiden/importeer', 'POST', self.maak_geldig_wav(),
                               bestandsnaam='Recentgeluid.wav')
        _, groep = self.verzoek('/api/groepen', 'POST', {'naam': 'Recente South Park'})
        groepsnummer = groep['groep_id']
        self.verzoek(f'/api/groepen/{groepsnummer}/geluiden', 'POST', {'geluid_id': item['geluid_id']})
        self.verzoek('/api/preview', 'POST', {'geluid_id': item['geluid_id'], 'actie': 'gestart',
                     'afspeelbeurt': 'recente-testpreview', 'verstreken_seconden': 0})
        self.verzoek('/api/preview', 'POST', {'geluid_id': item['geluid_id'], 'actie': 'gestopt',
                     'afspeelbeurt': 'recente-testpreview', 'reden': 'handmatig',
                     'verstreken_seconden': 0.4})
        _, recente = self.verzoek('/api/recente-gebruik')
        self.assertEqual(recente['groepen'][0]['id'], groepsnummer)
        self.assertEqual(recente['geluiden'][0]['wijze'], 'preview')
        self.assertEqual(recente['geluiden'][0]['status'], 'handmatig')
        self.verzoek('/api/groepen/recent', 'POST', {'groep_id': groepsnummer})
        self.assertEqual(self.verzoek('/api/recente-gebruik')[1]['groepen'][0]['id'], groepsnummer)

    def test_geschiedenis_wissen_raakt_bibliotheek_niet(self):
        code, _ = self.verzoek('/api/recente-gebruik/wissen', 'POST', {})
        self.assertEqual(code, 200)
        self.assertEqual(self.verzoek('/api/recente-gebruik')[1], {'groepen': [], 'geluiden': []})
        self.assertGreater(len(self.verzoek('/api/bibliotheek')[1]['geluiden']), 0)

    def test_preview_wordt_gelogd_zonder_de_live_mixer_te_gebruiken(self):
        _, item = self.verzoek('/api/geluiden/importeer', 'POST', self.maak_geldig_wav(),
                               bestandsnaam='alleen_mijn_headset.wav')
        with patch.object(self.bediening.mixer, 'speel_een_voorbereid_geluid') as echte_mixer:
            self.verzoek('/api/preview', 'POST', {'geluid_id': item['geluid_id'],
                          'actie': 'gestart', 'verstreken_seconden': 0})
            self.verzoek('/api/preview', 'POST', {'geluid_id': item['geluid_id'],
                          'actie': 'gestopt', 'verstreken_seconden': 1.2})
            echte_mixer.assert_not_called()

    def test_preview_weigert_langer_dan_twee_minuten(self):
        _, item = self.verzoek('/api/geluiden/importeer', 'POST', self.maak_geldig_wav(),
                               bestandsnaam='te_lange_preview.wav')
        with self.assertRaises(HTTPError) as fout:
            self.verzoek('/api/preview', 'POST', {'geluid_id': item['geluid_id'],
                         'actie': 'gestopt', 'verstreken_seconden': 999})
        self.assertEqual(fout.exception.code, 400)

    def test_media_range_na_het_einde_krijgt_416(self):
        _, item = self.verzoek('/api/geluiden/importeer', 'POST', self.maak_geldig_wav(),
                               bestandsnaam='foutbereik.wav')
        with self.assertRaises(HTTPError) as fout:
            urlopen(Request(self.url + f"/media/{item['geluid_id']}",
                            headers={'Range': 'bytes=99999999-'}), timeout=5)
        self.assertEqual(fout.exception.code, 416)

    def test_mp4_import_behoudt_video_en_stuurt_fragmenten_als_audio(self):
        import subprocess
        import imageio_ffmpeg
        videopad = self.map / 'controle_video.mp4'
        resultaat = subprocess.run([
            imageio_ffmpeg.get_ffmpeg_exe(), '-y', '-nostdin', '-loglevel', 'error',
            '-f', 'lavfi', '-i', 'color=c=blue:s=80x80:r=12:d=1',
            '-f', 'lavfi', '-i', 'sine=frequency=660:duration=1',
            '-c:v', 'libx264', '-pix_fmt', 'yuv420p', '-c:a', 'aac',
            '-shortest', str(videopad),
        ], capture_output=True, timeout=20)
        self.assertEqual(resultaat.returncode, 0, resultaat.stderr)
        _, nieuw = self.verzoek('/api/geluiden/importeer', 'POST', videopad.read_bytes(),
                                bestandsnaam='eigen%20animatie.mp4')
        _, bibliotheek = self.verzoek('/api/bibliotheek')
        geluid = next(x for x in bibliotheek['geluiden'] if x['id'] == nieuw['geluid_id'])
        self.assertTrue(geluid['is_video'])
        self.assertEqual(geluid['formaat'], 'mp4')
        with urlopen(Request(self.url + geluid['mediabron'],
                             headers={'Range': 'bytes=0-99'}), timeout=5) as antwoord:
            self.assertEqual(antwoord.status, 206)
            self.assertEqual(antwoord.headers['Content-Type'], 'video/mp4')
            self.assertEqual(antwoord.read(), videopad.read_bytes()[:100])

if __name__ == '__main__':
    unittest.main()
