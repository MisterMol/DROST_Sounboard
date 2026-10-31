"""6.1 Beta 3: voorbeelden, effectinstellingen en lokale API, zonder audioapparaat."""
from __future__ import annotations

from contextlib import closing
from io import BytesIO
import json
from pathlib import Path
import sqlite3
import tempfile
import threading
import unittest
from unittest.mock import MagicMock
from urllib.error import HTTPError
from urllib.request import Request, urlopen
import wave

import numpy as np

from app.audio.ingebouwde_stemvoorbeelden import VOORBEELD_SPREKERS, geef_voorbeeldpad, render_voorbeeld
from app.audio.stemparameters import standaard_parameters, controleer_parameters
from app.audio.stemvervorming import PROFIELEN, STANDAARD_INTENSITEITEN, Stemvervormer
from app.diagnostiek.logboek import BeschikbareLogboeken
from app.webinterface.favorieten_en_instellingen import VasteFavorietenEnInstellingen
from app.webinterface.bediening_van_de_audiomotor import WebbedieningVanDrostSoundboard
from app.webinterface.lokale_webserver import LokaleWebserverVanDrostSoundboard

ROOT = Path(__file__).resolve().parents[1]


class TestStemmenAudio(unittest.TestCase):
    def test_achttien_profielen_en_voorbeelden(self):
        self.assertEqual(len(PROFIELEN), 22)
        self.assertIn('meisje', PROFIELEN)
        self.assertIn('autotune', PROFIELEN)
        for spreker in VOORBEELD_SPREKERS:
            pad = geef_voorbeeldpad(spreker)
            self.assertTrue(pad.is_file(), pad)
            self.assertLess(pad.stat().st_size, 30000)
            self.assertGreater(pad.stat().st_size, 15000)

    @unittest.skipUnless((Path(__file__).resolve().parents[1] / 'app/audio/native/win-x64/drost_stem.dll').is_file(),
                         'Echte DSP-motor ontbreekt in CI-checkout; lokaal voor release verplicht')
    def test_wav_door_filter_en_bestaande_intensiteit(self):
        neutraal = render_voorbeeld('bob', 'normaal', 100)
        lage_stem = render_voorbeeld('bob', 'heel_diep', 100)
        hoger = render_voorbeeld('elise', 'meisje', 100)
        for ruwe_data in (neutraal, lage_stem, hoger):
            with wave.open(BytesIO(ruwe_data)) as wav:
                self.assertEqual(wav.getframerate(), 48000)
                self.assertEqual(wav.getsampwidth(), 2)
                self.assertEqual(wav.getnchannels(), 1)
                self.assertGreater(wav.getnframes(), 48000)
        self.assertNotEqual(neutraal, lage_stem)
        self.assertNotEqual(neutraal, hoger)
        self.assertEqual(render_voorbeeld('bob', 'xbox2010', 0), neutraal)
        self.assertNotEqual(render_voorbeeld('bob', 'xbox2010', 100), neutraal)

    def test_echo_lange_staart_en_feedback_veranderen_output(self):
        kort = standaard_parameters()
        lang = standaard_parameters()
        kort['echo']['vertraging_ms'] = 180
        lang['echo']['vertraging_ms'] = 1200
        lang['echo']['feedback_pct'] = 70
        kort_data = render_voorbeeld('bob', 'echo', 100, kort)
        lang_data = render_voorbeeld('bob', 'echo', 100, lang)
        with wave.open(BytesIO(kort_data)) as wav:
            kort_frames = wav.getnframes()
        with wave.open(BytesIO(lang_data)) as wav:
            lang_frames = wav.getnframes()
        self.assertGreater(lang_frames, kort_frames)
        self.assertLessEqual(lang_frames, 10 * 48000)

    @unittest.skipUnless((Path(__file__).resolve().parents[1] / 'app/audio/native/win-x64/drost_stem.dll').is_file(),
                         'Echte DSP-motor ontbreekt in CI-checkout; lokaal voor release verplicht')
    def test_alle_nieuwe_profielen_zijn_eindig(self):
        bron = np.sin(np.arange(480*55)*2*np.pi*224/48000).astype(np.float32)[:,None]*.23
        for profiel in ('jongen','meisje','oudeman','oudevrouw','xbox2010','autotune'):
            with self.subTest(profiel=profiel):
                p = Stemvervormer(profiel)
                samples = np.concatenate([p.verwerk(bron[i:i+480]) for i in range(0,len(bron),480)])
                self.assertTrue(np.isfinite(samples).all())
                self.assertGreater(np.max(np.abs(samples)), .01)

    def test_parameters_worden_strikt_gevalideerd(self):
        met_fout = (
            ('echo', dict(vertraging_ms=10000,feedback_pct=28,mix_pct=50)),
            ('echo', dict(vertraging_ms=190,feedback_pct=True,mix_pct=50)),
            ('echo', dict(vertraging_ms=190,feedback_pct=28)),
            ('autotune', dict(ruis_pct=101,haperingen_pct=50,korrel_pct=70)),
            ('autotune', dict(ruis_pct=60,haperingen_pct='veel',korrel_pct=70)),
            ('autotune', dict(toonsoort='C',toonladder='majeur',snelheid_pct=80)),
            ('normaal', {}),
        )
        for profiel,waarden in met_fout:
            with self.subTest(profiel=profiel,waarden=waarden), self.assertRaises(ValueError):
                controleer_parameters(profiel,waarden)


class TestDatabaseInstellingen(unittest.TestCase):
    def test_behoud_migratie_en_reset(self):
        with tempfile.TemporaryDirectory() as temp:
            db = Path(temp)/'geluiden.sqlite3'
            opslag = VasteFavorietenEnInstellingen(db)
            self.assertEqual(opslag.geef_voorbeeldspreker(), 'bob')
            opslag.bewaar_voorbeeldspreker('elise')
            params = opslag.geef_stemparameters()['echo']
            params['vertraging_ms'] = 1200
            opslag.bewaar_stemparameters('echo',params)
            opslag.bewaar_stemprofiel('echo')
            opslag.bewaar_stemintensiteit('echo', 23)
            opnieuw = VasteFavorietenEnInstellingen(db)
            self.assertEqual(opnieuw.geef_stemparameters()['echo']['vertraging_ms'],1200)
            self.assertEqual(opnieuw.geef_voorbeeldspreker(),'elise')
            self.assertEqual(opnieuw.geef_stemprofiel(),'echo')
            self.assertEqual(opnieuw.geef_stemintensiteiten()['echo'],23)
            opnieuw.herstel_stemparameters('echo')
            self.assertEqual(opnieuw.geef_stemparameters()['echo']['vertraging_ms'],190)
            self.assertEqual(opnieuw.geef_stemprofiel(),'echo')
            self.assertEqual(opnieuw.geef_stemintensiteiten()['echo'],23)
            opnieuw.bewaar_stemparameters('echo',params)
            opnieuw.herstel_stemparameters()
            self.assertEqual(opnieuw.geef_stemparameters(),standaard_parameters())

    def test_onjuiste_opgeslagen_json_valt_veilig_terug(self):
        with tempfile.TemporaryDirectory() as temp:
            db=Path(temp)/'test.db'
            opslag=VasteFavorietenEnInstellingen(db)
            with closing(sqlite3.connect(db)) as conn, conn:
                conn.execute('INSERT INTO stemprofiel_parameters VALUES (?,?)',('echo','{"vertraging_ms":100000}'))
            self.assertEqual(opslag.geef_stemparameters()['echo'], standaard_parameters()['echo'])


class TestLokaleVoorbeeldAPI(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        logger = MagicMock()
        logs = BeschikbareLogboeken(logger,logger,Path(cls.tmp.name),'test')
        cls.bediening = WebbedieningVanDrostSoundboard(object(),logs,Path(cls.tmp.name)/'test.db')
        cls.server = LokaleWebserverVanDrostSoundboard(('127.0.0.1',0),cls.bediening)
        cls.url=f'http://127.0.0.1:{cls.server.server_port}'
        cls.thread=threading.Thread(target=cls.server.serve_forever,daemon=True)
        cls.thread.start()

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown();cls.server.server_close();cls.thread.join(timeout=3)
        cls.bediening.sluit_alle_audio_af();cls.tmp.cleanup()

    def request(self,pad,body=None,token=True):
        headers={}
        if token:headers['X-Drost-Token']=self.server.schrijf_token
        if body is not None:headers['Content-Type']='application/json'
        req=Request(self.url+pad,headers=headers,
                    data=None if body is None else json.dumps(body).encode('utf-8'),
                    method='GET' if body is None else 'POST')
        with urlopen(req,timeout=8) as antwoord:
            return antwoord.status,antwoord.headers,antwoord.read()

    def test_audio_alleen_met_token(self):
        with self.assertRaises(HTTPError) as fout:
            self.request('/api/stemmen/voorbeeld?spreker=bob',token=False)
        self.assertEqual(fout.exception.code,400)
        code,koppen,data=self.request('/api/stemmen/voorbeeld?spreker=bob')
        self.assertEqual(code,200)
        self.assertIn('audio/wav',koppen['Content-Type'])
        self.assertTrue(data.startswith(b'RIFF'))
        self.assertTrue(len(data)>200000)
        for pad in ('/api/stemmen/voorbeeld?spreker=../../etc/passwd',
                    '/api/stemmen/voorbeeld?spreker=bob&spreker=elise'):
            with self.subTest(pad=pad),self.assertRaises(HTTPError):
                self.request(pad)

    def test_instelniveaus_en_voorbeeld_koppelen(self):
        _,_,data=self.request('/api/instellingen/stemprofiel')
        settings=json.loads(data)
        self.assertEqual(settings['voorbeeldspreker'],'bob')
        self.assertIn('echo',settings['parameters_catalogus'])
        self.request('/api/instellingen/stemprofiel',{'profiel':'echo'})
        params=standaard_parameters()['echo'];params['vertraging_ms']=1000
        self.request('/api/instellingen/stemparameters',{'profiel':'echo','parameters':params})
        _,_,data=self.request('/api/instellingen/stemprofiel')
        self.assertEqual(json.loads(data)['effectparameters']['echo']['vertraging_ms'],1000)
        self.assertEqual(self.bediening.mixer._stemparameters['echo']['vertraging_ms'],1000)
        self.assertEqual(self.bediening.stemvoorbeeld._gewenste_parameters['echo']['vertraging_ms'],1000)
        self.request('/api/instellingen/stemvoorbeeldspreker',{'spreker':'elise'})
        _,_,audio=self.request('/api/stemmen/voorbeeld?spreker=elise')
        with wave.open(BytesIO(audio)) as wav:
            self.assertGreater(wav.getnframes(), 48000*4)
        self.request('/api/instellingen/stemparameters/herstel',{'profiel':'echo'})
        self.assertEqual(self.bediening.favorieten.geef_stemparameters()['echo']['vertraging_ms'],190)
        self.request('/api/instellingen/stemparameters/herstel-alles',{})
        with self.assertRaises(HTTPError) as fout:
            self.request('/api/instellingen/stemparameters',{'profiel':'echo','parameters':{'vertraging_ms':999999}})
        self.assertEqual(fout.exception.code,400)


class TestBundelingEnInterface(unittest.TestCase):
    def test_build_en_smoketest_neemt_stemmp3_mee(self):
        script=(ROOT/'Bouw_Windows_Release.ps1').read_text(encoding='utf-8')
        self.assertIn('--add-data \'app/audio/stemvoorbeelden:app/audio/stemvoorbeelden\'',script)
        # RC1-Bouwcontract: test de versieparser in plaats van een oud regexfragment.
        from app.desktop.releasevoorbereiding import lees_releaseversie
        self.assertIn('VERSIE_VAN_DE_APP', script)
        self.assertIn('app.desktop.releasevoorbereiding plan', script)
        self.assertEqual(lees_releaseversie('6.1.0-rc.1').soort, 'rc')
        self.assertEqual(lees_releaseversie('6.1.0').kanaal, 'stable')
        with self.assertRaises(ValueError):
            lees_releaseversie('6.1.0-rc.1.1')
        zelftest=(ROOT/'app/desktop/release_zelftest.py').read_text(encoding='utf-8')
        self.assertIn("'stemvoorbeelden'",zelftest)
        gitignore=(ROOT/'.gitignore').read_text(encoding='utf-8')
        self.assertIn('!app/audio/stemvoorbeelden/*.mp3',gitignore)

    def test_instelscherm_en_api_bestaan(self):
        html=(ROOT/'app/webinterface/statisch/dashboard.html').read_text(encoding='utf-8')
        js=(ROOT/'app/webinterface/statisch/dashboard.js').read_text(encoding='utf-8')
        for id in ('stem-demo-spreker','knop-stem-demo','stem-demo-audio','stem-extra-velden'):
            self.assertIn(f'id="{id}"',html)
            self.assertIn(f"element('{id}')",js)
        self.assertIn('klik',html.lower())
        self.assertIn('/api/stemkeuze/voorbeeld?spreker=', js)
        self.assertIn('/api/stemkeuze/bron?spreker=', js)
        self.assertIn('/api/stemkeuze/voorbeeld/stop', js)
        self.assertIn('X-Drost-Token',js)
