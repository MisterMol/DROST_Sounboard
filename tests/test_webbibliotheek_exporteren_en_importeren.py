"""HTTP-regressies voor het exporteren en importeren van echte ZIP-bestanden."""
from io import BytesIO
import json
import os
from pathlib import Path
from tempfile import TemporaryDirectory
import threading
import unittest
from urllib.error import HTTPError
from urllib.request import Request, urlopen
import wave
from zipfile import ZipFile

from app.diagnostiek.logboek import maak_logboeken_klaar, sluit_logboeken_netjes_af
from app.webinterface.bediening_van_de_audiomotor import WebbedieningVanDrostSoundboard
from app.webinterface.lokale_webserver import LokaleWebserverVanDrostSoundboard


class TestWebBibliotheekArchief(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tijdelijk = TemporaryDirectory()
        cls.map = Path(cls.tijdelijk.name)
        cls.oude_appdata = os.environ.get('LOCALAPPDATA')
        os.environ['LOCALAPPDATA'] = str(cls.map)
        cls.logs = maak_logboeken_klaar(cls.map / 'logs')
        cls.bediening = WebbedieningVanDrostSoundboard(object(), cls.logs, cls.map / 'geluiden.sqlite3')
        cls.server = LokaleWebserverVanDrostSoundboard(('127.0.0.1', 0), cls.bediening)
        cls.url = f'http://127.0.0.1:{cls.server.server_port}'
        cls.draad = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.draad.start()
        cls.wav = cls.server.media_map / 'geluiden' / 'bron.wav'
        with wave.open(str(cls.wav), 'wb') as uit:
            uit.setnchannels(1)
            uit.setsampwidth(2)
            uit.setframerate(16000)
            uit.writeframes(b'\0\0' * 8000)
        cls.item = cls.bediening.geluidenbibliotheek.voeg_geluidsbestanden_toe([cls.wav])[0]

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.draad.join(timeout=5)
        cls.bediening.sluit_alle_audio_af()
        sluit_logboeken_netjes_af(cls.logs)
        if cls.oude_appdata is None:
            os.environ.pop('LOCALAPPDATA', None)
        else:
            os.environ['LOCALAPPDATA'] = cls.oude_appdata
        cls.tijdelijk.cleanup()

    def verzoek(self, pad, gegevens=None, methode='GET', bestand=False):
        koppen = {}
        if methode == 'POST':
            koppen['X-Drost-Token'] = self.server.schrijf_token
            if bestand:
                koppen['Content-Type'] = 'application/octet-stream'
                data = gegevens
            else:
                koppen['Content-Type'] = 'application/json'
                data = json.dumps(gegevens).encode('utf-8')
        else:
            data = None
        with urlopen(Request(self.url + pad, data=data, headers=koppen, method=methode), timeout=10) as antwoord:
            return antwoord.status, antwoord.read(), antwoord.headers

    def test_metadata_wordt_via_http_opgeslagen_en_getoond(self):
        nummer = self.item.geluid_id
        status, data, _ = self.verzoek(f'/api/geluiden/{nummer}/instellingen', {
            'naam': 'Nieuwe naam', 'beginpositie': .123, 'maximale_duur': .345,
            'volume': .3, 'beschrijving': 'Jezus, wat een tijd',
            'gesproken_tekst': 'Dit wordt hardop gezegd', 'zoekwoorden': 'retro, werk',
        }, 'POST')
        self.assertEqual(status, 200)
        _, gegevens, _ = self.verzoek('/api/bibliotheek')
        regel = next(i for i in json.loads(gegevens)['geluiden'] if i['id'] == nummer)
        self.assertEqual(regel['gesproken_tekst'], 'Dit wordt hardop gezegd')
        self.assertEqual(regel['maximale_duur'], .345)

    def test_portabele_zip_kan_worden_gedownload_en_via_http_weer_geimporteerd(self):
        status, data, headers = self.verzoek(f'/api/bibliotheek/exporteer?id={self.item.geluid_id}')
        self.assertEqual(status, 200)
        self.assertEqual(headers.get_content_type(), 'application/zip')
        with ZipFile(BytesIO(data)) as zipbestand:
            self.assertIn('manifest.json', zipbestand.namelist())
            manifest = json.loads(zipbestand.read('manifest.json'))
            self.assertEqual(len(manifest['geluiden']), 1)
        status, resultaat, _ = self.verzoek('/api/bibliotheek/importeer?dubbelen=toestaan', data, 'POST', bestand=True)
        self.assertEqual(status, 201)
        self.assertEqual(json.loads(resultaat)['aantal'], 1)
        self.assertEqual(len(self.bediening.geef_geluidsbibliotheek()['geluiden']), 2)

    def test_meerdere_geluiden_in_een_keer_aan_groep_toewijzen_via_http(self):
        groep = self.bediening.groepen.maak_groep('Aanpassen')
        nummer = self.item.geluid_id
        status, antwoord, _ = self.verzoek('/api/bibliotheek/groep-toewijzen', {
            'groep_id': groep, 'geluid_ids': [nummer]
        }, 'POST')
        self.assertEqual(status, 200)
        self.assertEqual(json.loads(antwoord)['aantal'], 1)
        self.assertIn(groep, self.bediening.groepen.geef_groepsnummers_per_geluid()[nummer])

    def test_bulk_verwijderen_vereist_explicitie_bevestiging(self):
        nummer = self.item.geluid_id
        with self.assertRaises(HTTPError) as fout:
            self.verzoek('/api/bibliotheek/verwijder-selectie', {
                'geluid_ids': [nummer], 'bevestiging': 'nee'
            }, 'POST')
        self.assertEqual(fout.exception.code, 400)
        self.assertTrue(any(i.geluid_id == nummer for i in self.bediening.geluidenbibliotheek.geef_alle_geluiden()))

    def test_ongeldige_archiefupload_levert_400_op(self):
        with self.assertRaises(HTTPError) as fout:
            self.verzoek('/api/bibliotheek/importeer', b'geen zip', 'POST', bestand=True)
        self.assertEqual(fout.exception.code, 400)

    def test_ongeldige_metadata_wordt_afgewezen_zonder_eerdere_naamswijziging(self):
        nummer = self.item.geluid_id
        oude_naam = next(i['naam'] for i in self.bediening.geef_geluidsbibliotheek()['geluiden'] if i['id'] == nummer)
        with self.assertRaises(HTTPError) as fout:
            self.verzoek(f'/api/geluiden/{nummer}/instellingen', {
                'naam': 'Verkeerd', 'beginpositie': 0, 'maximale_duur': 1,
                'volume': .3, 'beschrijving': None, 'gesproken_tekst': '', 'zoekwoorden': '',
            }, 'POST')
        self.assertEqual(fout.exception.code, 400)
        nieuw = next(i['naam'] for i in self.bediening.geef_geluidsbibliotheek()['geluiden'] if i['id'] == nummer)
        self.assertEqual(nieuw, oude_naam)


if __name__ == '__main__':
    unittest.main()
