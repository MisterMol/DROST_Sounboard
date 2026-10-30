"""6.1 Beta 2: profielen, per-profielintensiteit, microfoonniveaus en API."""
from __future__ import annotations

import json
from contextlib import closing
import logging
from pathlib import Path
import shutil
import sqlite3
import subprocess
import tempfile
import threading
import unittest
from html.parser import HTMLParser
from unittest.mock import MagicMock
from urllib.error import HTTPError
from urllib.request import Request, urlopen

import numpy as np

from app.audio.stemvervorming import (PROFIELEN, STANDAARD_INTENSITEITEN,
    Stemvervormer, controleer_stemintensiteit, profiel_catalogus_voor_api)
from app.audio.stemvoorbeeld import LokaalStemvoorbeeld
from app.audio.live_audiomixer import LiveAudiomixer
from app.diagnostiek.logboek import BeschikbareLogboeken
from app.webinterface.favorieten_en_instellingen import VasteFavorietenEnInstellingen
from app.webinterface.bediening_van_de_audiomotor import WebbedieningVanDrostSoundboard
from app.webinterface.lokale_webserver import LokaleWebserverVanDrostSoundboard

ROOT = Path(__file__).resolve().parents[1]


class TestEffectenEnIntensiteit(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.microfoon = (np.sin(np.arange(48000, dtype=np.float64)*2*np.pi*220/48000)*.21).astype(np.float32)[:, None]

    def _verwerk(self, profiel, intensiteit=None):
        p = Stemvervormer(profiel, intensiteit=intensiteit)
        return np.concatenate([p.verwerk(self.microfoon[i:i+480]) for i in range(0,48000,480)])

    def test_profielen_en_icons_zijn_uniek(self):
        lijst = profiel_catalogus_voor_api()
        self.assertGreaterEqual(len(lijst), 10)
        self.assertEqual(set(PROFIELEN) - {'jongen', 'meisje', 'oudeman', 'oudevrouw'}, {p['id'] for p in lijst})
        self.assertEqual(set(PROFIELEN) - {p['id'] for p in lijst}, {'jongen', 'meisje', 'oudeman', 'oudevrouw'})
        self.assertTrue(all(p['naam'] and p['icoon'] and p['beschrijving'] for p in lijst))
        self.assertIn('heel_hoog', PROFIELEN)
        self.assertIn('heel_diep', PROFIELEN)

    def test_ieder_profiel_verwerkt_audio_zonder_nan_of_overflows(self):
        for naam in PROFIELEN:
            with self.subTest(naam=naam):
                resultaat = self._verwerk(naam)
                self.assertEqual(resultaat.shape, self.microfoon.shape)
                self.assertTrue(np.isfinite(resultaat).all())
                self.assertGreater(float(np.max(np.abs(resultaat))), .02)

    def test_nul_intensiteit_is_echt_onbewerkt(self):
        for naam in PROFIELEN:
            x = self.microfoon[:480].copy()
            p = Stemvervormer(naam, intensiteit=0)
            self.assertIs(p.verwerk(x), x)

    def test_intensiteit_verandert_het_resultaat(self):
        for naam in ('robot','radio','diep','heel_hoog','alien','echo','monster','megafoon'):
            with self.subTest(naam=naam):
                zacht = self._verwerk(naam, 20)
                sterk = self._verwerk(naam, 95)
                self.assertGreater(float(np.sqrt(np.mean((zacht - sterk)**2))), .012)

    def test_hoog_lager_dan_heel_hoog_en_diep_lager_dan_heel_diep(self):
        def grondtoon(naam):
            x = self._verwerk(naam, 100)[24000:,0]
            spectrum = np.abs(np.fft.rfft(x*np.hanning(len(x))))
            return float(np.fft.rfftfreq(len(x), 1/48000)[np.argmax(spectrum)])
        self.assertLess(grondtoon('heel_diep'), grondtoon('diep'))
        self.assertLess(grondtoon('diep'), 220)
        self.assertGreater(grondtoon('hoog'), 220)
        self.assertGreater(grondtoon('heel_hoog'), grondtoon('hoog'))

    def test_intensiteit_verwerpt_onveilige_waarden(self):
        for verkeerd in (-1,101,True,20.0,'50',None,float('nan')):
            with self.subTest(waarde=verkeerd), self.assertRaises(ValueError):
                controleer_stemintensiteit(verkeerd)


class TestIntensiteitDatabase(unittest.TestCase):
    def test_bestaande_database_wordt_veilig_uitgebreid(self):
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp)/'bibliotheek.sqlite3'
            with closing(sqlite3.connect(p)) as db, db:
                db.execute("""CREATE TABLE stemprofiel_instellingen (
                    sleutel INTEGER PRIMARY KEY CHECK (sleutel = 1),
                    profiel TEXT NOT NULL CHECK (profiel IN ('normaal', 'radio', 'robot', 'diep')))""")
                db.execute("INSERT INTO stemprofiel_instellingen VALUES(1,'robot')")
            inst=VasteFavorietenEnInstellingen(p)
            self.assertEqual(inst.geef_stemprofiel(),'robot')
            inst.bewaar_stemprofiel('heel_hoog')
            inst.bewaar_stemintensiteit('heel_hoog', 34)
            inst.bewaar_stemintensiteit('radio', 15)
            nieuwe=VasteFavorietenEnInstellingen(p)
            self.assertEqual(nieuwe.geef_stemprofiel(),'heel_hoog')
            self.assertEqual(nieuwe.geef_stemintensiteiten()['heel_hoog'],34)
            self.assertEqual(nieuwe.geef_stemintensiteiten()['radio'],15)
            self.assertEqual(inst.herstel_stemintensiteit('heel_hoog')['heel_hoog'],STANDAARD_INTENSITEITEN['heel_hoog'])
            self.assertEqual(inst.geef_stemintensiteiten()['radio'],15)
            inst.herstel_stemintensiteit()
            self.assertEqual(inst.geef_stemintensiteiten(),STANDAARD_INTENSITEITEN)
            self.assertEqual(inst.geef_stemprofiel(),'heel_hoog')
            with closing(sqlite3.connect(p)) as db, db:
                self.assertEqual(db.execute('SELECT profiel FROM stemprofiel_instellingen').fetchone()[0],'robot')

    def test_beschadigde_intensiteit_wordt_niet_opgeslagen(self):
        with tempfile.TemporaryDirectory() as tmp:
            inst=VasteFavorietenEnInstellingen(Path(tmp)/'test.sqlite3')
            with self.assertRaises(ValueError):
                inst.bewaar_stemintensiteit('robot', True)
            self.assertEqual(inst.geef_stemintensiteiten()['robot'],STANDAARD_INTENSITEITEN['robot'])


class TestStemMeters(unittest.TestCase):
    def test_preview_meet_apart_binnenkomst_en_effect(self):
        preview = LokaalStemvoorbeeld(MagicMock(),MagicMock(spec=logging.Logger))
        preview.stel_stemprofiel_in('robot')
        preview._gewenste_intensiteiten['robot']=100
        frames = np.ones((480,1), dtype=np.float32)*.23
        uit = np.zeros((480,2), dtype=np.float32)
        preview._audio_callback(frames,uit,480,None,False)
        preview._draait = True
        preview._draad = MagicMock()
        preview._draad.is_alive.return_value=True
        info=preview.status()
        self.assertGreater(info['microfoon_rms'],.22)
        self.assertGreater(info['stem_rms'],0)
        self.assertNotEqual(info['stem_rms'],info['microfoon_rms'])
        preview._draait=False
        self.assertEqual(preview.status()['microfoon_rms'],0)

    def test_mixer_stopt_microfoon_niet_bij_stemverandering(self):
        mixer=LiveAudiomixer(MagicMock(),MagicMock(spec=logging.Logger),MagicMock(spec=logging.Logger))
        mixer.stel_stemprofiel_in('heel_hoog')
        intensiteiten=dict(STANDAARD_INTENSITEITEN)
        intensiteiten['heel_hoog']=45
        mixer.stel_stemintensiteiten_in(intensiteiten)
        x=(np.ones((480,1))*0.08).astype(np.float32)
        y=np.zeros((480,2),dtype=np.float32)
        piek = 0.0
        for _ in range(9):
            mixer.verwerk_een_blok_live_audio(x,y,480,None,False)
            piek = max(piek, float(np.max(np.abs(y))))
        self.assertFalse(mixer._stop_de_verbinding.is_set())
        self.assertEqual(mixer._stemvervormer.intensiteit,45)
        self.assertGreater(piek,.01)


class TestWebStemInstellingen(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp=tempfile.TemporaryDirectory()
        logger=MagicMock(spec=logging.Logger)
        logs=BeschikbareLogboeken(logger,logger,Path(cls.tmp.name),'test')
        cls.bediening=WebbedieningVanDrostSoundboard(object(), logs, Path(cls.tmp.name)/'test.db')
        cls.server=LokaleWebserverVanDrostSoundboard(('127.0.0.1',0),cls.bediening)
        cls.base=f'http://127.0.0.1:{cls.server.server_port}'
        cls.thread=threading.Thread(target=cls.server.serve_forever,daemon=True)
        cls.thread.start()

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown();cls.server.server_close();cls.thread.join(timeout=3)
        cls.bediening.sluit_alle_audio_af();cls.tmp.cleanup()

    def call(self,route,body=None,token=True):
        headers={'Content-Type':'application/json'}
        if body is not None and token:
            headers['X-Drost-Token']=self.server.schrijf_token
        request=Request(self.base+route,method='POST' if body is not None else 'GET',headers=headers,
                        data=json.dumps(body).encode('utf-8') if body is not None else None)
        with urlopen(request,timeout=6) as resp:
            return json.loads(resp.read())

    def test_catalogus_en_insteltabel(self):
        info=self.call('/api/instellingen/stemprofiel')
        self.assertIn('heel_hoog',info['intensiteiten'])
        self.assertGreaterEqual(len(info['profielen']),10)
        self.assertEqual(len({p['icoon'] for p in info['profielen']}),len(info['profielen']))

    def test_opslaan_reset_en_live_propagatie(self):
        r=self.call('/api/instellingen/stemintensiteit',{'profiel':'heel_diep','intensiteit':41})
        self.assertEqual(r['intensiteit'],41)
        self.assertEqual(self.bediening.mixer._stemintensiteiten['heel_diep'],41)
        self.assertEqual(self.bediening.stemvoorbeeld._gewenste_intensiteiten['heel_diep'],41)
        self.assertEqual(self.call('/api/instellingen/stemprofiel')['intensiteiten']['heel_diep'],41)
        self.call('/api/instellingen/stemintensiteit/herstel',{'profiel':'heel_diep'})
        self.assertEqual(self.call('/api/instellingen/stemprofiel')['intensiteiten']['heel_diep'],STANDAARD_INTENSITEITEN['heel_diep'])
        self.call('/api/instellingen/stemintensiteit',{'profiel':'radio','intensiteit':19})
        self.call('/api/instellingen/stemintensiteit/herstel-alles',{})
        self.assertEqual(self.call('/api/instellingen/stemprofiel')['intensiteiten'],STANDAARD_INTENSITEITEN)

    def test_beveiliging_en_onjuiste_input(self):
        for route,body in [
            ('/api/instellingen/stemintensiteit',{'profiel':'robot','intensiteit':100}),
            ('/api/instellingen/stemintensiteit/herstel',{'profiel':'robot'}),
            ('/api/instellingen/stemintensiteit/herstel-alles',{})
        ]:
            with self.subTest(route=route),self.assertRaises(HTTPError) as fout:
                self.call(route,body,token=False)
            self.assertEqual(fout.exception.code,400)
        for route,body in [
            ('/api/instellingen/stemintensiteit',{'profiel':'robot','intensiteit':101}),
            ('/api/instellingen/stemintensiteit',{'profiel':'robot','intensiteit':True}),
            ('/api/instellingen/stemintensiteit',{'profiel':'onbekend','intensiteit':40}),
            ('/api/instellingen/stemintensiteit/herstel-alles',{'per_ongeluk':True})
        ]:
            with self.subTest(route=route,body=body),self.assertRaises(HTTPError) as fout:
                self.call(route,body)
            self.assertEqual(fout.exception.code,400)


class TestStemInstellingenHTML(unittest.TestCase):
    def test_schuif_meter_knoppen_en_raster_alleen_op_instellingenpagina(self):
        html=(ROOT/'app/webinterface/statisch/dashboard.html').read_text(encoding='utf-8')
        instellingen=html[html.index('<section id="instellingen-pagina"'):]
        dashboard=html[html.index('<main id="dashboard"'):html.index('<section id="instellingen-pagina"')]
        for id in ('stemprofielen-raster','stemintensiteit-schuif','knop-stem-reset',
                   'knop-stem-reset-alles','stemmeters-in','stemmeters-uit'):
            self.assertIn(f'id="{id}"',instellingen)
            self.assertNotIn(f'id="{id}"',dashboard)

    @unittest.skipUnless(shutil.which('node'),'Node.js optioneel')
    def test_javascript_syntaxis(self):
        result=subprocess.run(['node','--check',str(ROOT/'app/webinterface/statisch/dashboard.js')],
                              capture_output=True,text=True)
        self.assertEqual(result.returncode,0,result.stderr)


if __name__ == '__main__':
    unittest.main()
