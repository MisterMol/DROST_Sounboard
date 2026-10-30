"""6.1 Beta 4.2: live stem aan/uit, vaste navigatie en veilige bibliotheekreset."""
from __future__ import annotations

from contextlib import closing
from pathlib import Path
import json
import logging
import sqlite3
import tempfile
import threading
import unittest
from unittest.mock import MagicMock
from urllib.error import HTTPError
from urllib.request import Request, urlopen
import wave

import numpy as np

from app.audio.geluidenbibliotheek import PersoonlijkeGeluidenbibliotheek
from app.audio.live_audiomixer import LiveAudiomixer
from app.diagnostiek.logboek import BeschikbareLogboeken
from app.webinterface.bediening_van_de_audiomotor import WebbedieningVanDrostSoundboard
from app.webinterface.bibliotheek_opnieuw_beginnen import begin_met_lege_bibliotheek, BibliotheekLeegmakenFout
from app.webinterface.favorieten_en_instellingen import VasteFavorietenEnInstellingen
from app.webinterface.geluidsgroepen import PersoonlijkeGeluidsgroepen
from app.webinterface.lokale_webserver import LokaleWebserverVanDrostSoundboard
from app.webinterface.recente_geluiden_en_weergave import RecenteGeluidenEnWeergave

ROOT = Path(__file__).resolve().parents[1]


class TestStemvervormerExpliciet(unittest.TestCase):
    def test_profiel_is_niet_hetzelfde_als_live_activeren(self):
        with tempfile.TemporaryDirectory() as temp:
            db = Path(temp) / 'db.sqlite3'
            PersoonlijkeGeluidenbibliotheek(db)
            instellingen = VasteFavorietenEnInstellingen(db)
            instellingen.bewaar_stemprofiel('robot')
            self.assertFalse(instellingen.geef_stemvervormer_aan())
            self.assertEqual(instellingen.geef_stemprofiel(), 'robot')
            instellingen.bewaar_stemvervormer_aan(True)
            self.assertTrue(VasteFavorietenEnInstellingen(db).geef_stemvervormer_aan())
            instellingen.bewaar_stemvervormer_aan(False)
            self.assertEqual(instellingen.geef_stemprofiel(), 'robot')
            self.assertFalse(VasteFavorietenEnInstellingen(db).geef_stemvervormer_aan())
            with self.assertRaises(ValueError):
                instellingen.bewaar_stemvervormer_aan('false')

    def test_uitgeschakeld_verwerkt_microfoon_niet_met_dsp(self):
        mixer = LiveAudiomixer(MagicMock(), MagicMock(spec=logging.Logger), MagicMock(spec=logging.Logger))
        mixer.stel_stemprofiel_in('robot')
        mixer._stemvervormer.verwerk = MagicMock(return_value=np.ones((480, 1), dtype=np.float32) * .8)
        mic = np.ones((480, 1), dtype=np.float32) * .12
        uitgang = np.zeros((480, 2), dtype=np.float32)
        mixer.verwerk_een_blok_live_audio(mic, uitgang, 480, None, False)
        mixer._stemvervormer.verwerk.assert_not_called()
        uitgeschakeld = uitgang.copy()
        self.assertGreater(float(uitgeschakeld.mean()), .01)
        mixer.stel_stemvervormer_aan_in(True)
        mixer.verwerk_een_blok_live_audio(mic, uitgang, 480, None, False)
        mixer._stemvervormer.verwerk.assert_called_once()
        self.assertGreater(float(uitgang.mean()), float(uitgeschakeld.mean()))
        mixer.stel_stemvervormer_aan_in(False)
        mixer.verwerk_een_blok_live_audio(mic, uitgang, 480, None, False)
        self.assertEqual(mixer._stemvervormer.verwerk.call_count, 1)
        with self.assertRaises(ValueError):
            mixer.stel_stemvervormer_aan_in(1)


class TestVolledigeBibliotheekReset(unittest.TestCase):
    def test_leegmaken_met_back_up_bewaart_gebruikersinstellingen_en_bestanden(self):
        with tempfile.TemporaryDirectory() as tijdelijk:
            map = Path(tijdelijk)
            database = map / 'bibliotheek.sqlite3'
            bibliotheek = PersoonlijkeGeluidenbibliotheek(database)
            instellingen = VasteFavorietenEnInstellingen(database)
            groepen = PersoonlijkeGeluidsgroepen(database)
            RecenteGeluidenEnWeergave(database)
            instellingen.bewaar_stemprofiel('robot')
            instellingen.bewaar_stemvervormer_aan(True)
            instellingen.bewaar_normalisatiestand('normaal')
            geluidspad = map / 'mijn_geluid.wav'
            with wave.open(str(geluidspad), 'wb') as w:
                w.setnchannels(1); w.setsampwidth(2); w.setframerate(48000)
                w.writeframes(b'\x00\x00' * 480)
            geluid = bibliotheek.voeg_geluidsbestanden_toe([geluidspad])[0]
            groep = groepen.maak_groep('Movies')
            groepen.verander_lidmaatschap(groep, geluid.geluid_id, True)
            instellingen.zet_een_geluid_op_een_vaste_plek(1, geluid.geluid_id)
            with closing(sqlite3.connect(database)) as con:
                con.execute('INSERT INTO afspeelstatistieken VALUES (?,?,?)', (geluid.geluid_id, 24, '2026-10-25'))
                con.commit()
            with self.assertRaises(BibliotheekLeegmakenFout):
                begin_met_lege_bibliotheek(database, 'VERWIJDER')
            self.assertEqual(len(bibliotheek.geef_alle_geluiden()), 1)
            gegevens = begin_met_lege_bibliotheek(database, 'BEVESTIG')
            self.assertEqual(gegevens['geluiden_verwijderd'], 1)
            self.assertEqual(gegevens['mappen_verwijderd'], 1)
            self.assertTrue(geluidspad.is_file())
            self.assertEqual(bibliotheek.geef_alle_geluiden(), [])
            self.assertEqual(groepen.geef_alle_groepen(), [])
            self.assertEqual(instellingen.geef_alle_favorietplekken(), [None] * 15)
            self.assertEqual(instellingen.geef_stemprofiel(), 'robot')
            self.assertTrue(instellingen.geef_stemvervormer_aan())
            self.assertEqual(instellingen.geef_normalisatiestand(), 'normaal')
            with closing(sqlite3.connect(database)) as con:
                self.assertEqual(con.execute('SELECT COUNT(*) FROM afspeelstatistieken').fetchone()[0], 0)
            reserve = Path(gegevens['reservekopie'])
            self.assertTrue(reserve.is_file())
            with closing(sqlite3.connect(reserve)) as con:
                self.assertEqual(con.execute('SELECT COUNT(*) FROM geluiden').fetchone()[0], 1)
                self.assertEqual(con.execute('SELECT COUNT(*) FROM geluidsgroepen').fetchone()[0], 1)
                self.assertEqual(con.execute('PRAGMA quick_check').fetchone()[0], 'ok')
            # Herimporteren blijft mogelijk met hetzelfde originele audiobestand.
            self.assertEqual(len(bibliotheek.voeg_geluidsbestanden_toe([geluidspad])), 1)

    def test_niets_wissen_wanneer_back_up_mislukt(self):
        with tempfile.TemporaryDirectory() as tijdelijk:
            p = Path(tijdelijk) / 'bibliotheek.sqlite3'
            b = PersoonlijkeGeluidenbibliotheek(p)
            with closing(sqlite3.connect(p)) as con:
                con.execute("INSERT INTO geluiden VALUES ('x', 'Test', '/test.wav', '/test.wav', 'nu')")
                con.commit()
            # De reservekopiemap kan niet gemaakt worden als daar al een bestand staat.
            (p.parent / 'bibliotheek-reservekopien').write_text('niet een map', encoding='utf-8')
            with self.assertRaises((OSError, BibliotheekLeegmakenFout)):
                begin_met_lege_bibliotheek(p, 'BEVESTIG')
            self.assertEqual(len(b.geef_alle_geluiden()), 1)


class TestLokaleStemEnResetAPI(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        logger = MagicMock(spec=logging.Logger)
        self.service = WebbedieningVanDrostSoundboard(object(),
            BeschikbareLogboeken(logger, logger, Path(self.temp.name), 'test'),
            Path(self.temp.name) / 'db.sqlite3')
        self.server = LokaleWebserverVanDrostSoundboard(('127.0.0.1', 0), self.service)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.base = f'http://127.0.0.1:{self.server.server_port}'

    def tearDown(self):
        self.server.shutdown(); self.server.server_close(); self.thread.join(timeout=4)
        self.service.sluit_alle_audio_af(); self.temp.cleanup()

    def call(self, route, data=None, token=True):
        headers = {'Content-Type':'application/json'}
        if data is not None and token:headers['X-Drost-Token'] = self.server.schrijf_token
        req = Request(self.base + route, data=json.dumps(data).encode() if data is not None else None,
                      headers=headers, method='POST' if data is not None else 'GET')
        with urlopen(req, timeout=5) as response:
            return response.status, json.loads(response.read())

    def test_profiel_kiezen_start_geen_live_vervorming(self):
        self.call('/api/instellingen/stemprofiel', {'profiel':'robot'})
        self.assertEqual(self.service.mixer._stemprofiel, 'robot')
        self.assertFalse(self.service.mixer._stemvervormer_aan)
        self.assertFalse(self.call('/api/instellingen/stemprofiel')[1]['actief'])
        self.assertFalse(self.call('/api/status')[1]['stemvervormer_aan'])
        self.call('/api/instellingen/stemactief', {'aan':True})
        self.assertTrue(self.call('/api/status')[1]['stemvervormer_aan'])
        self.call('/api/instellingen/stemactief', {'aan':False})
        self.assertFalse(self.service.mixer._stemvervormer_aan)
        self.assertEqual(self.service.favorieten.geef_stemprofiel(),'robot')

    def test_reset_vereist_token_en_exacte_typtekst(self):
        for route, payload in [('/api/bibliotheek/leegmaken', {'bevestiging':'JA'}),
                               ('/api/instellingen/stemactief', {'aan':'ja'})]:
            with self.assertRaises(HTTPError) as err: self.call(route, payload)
            self.assertEqual(err.exception.code, 400)
        with self.assertRaises(HTTPError) as err:
            self.call('/api/bibliotheek/leegmaken', {'bevestiging':'BEVESTIG'},token=False)
        self.assertEqual(err.exception.code, 400)
        status, gegevens = self.call('/api/bibliotheek/leegmaken', {'bevestiging':'BEVESTIG'})
        self.assertEqual(status, 200)
        self.assertTrue(Path(gegevens['reservekopie']).is_file())


class TestInterfaceBediening(unittest.TestCase):
    def test_vaste_navigatie_en_resetdialog(self):
        html = (ROOT / 'app/webinterface/statisch/dashboard.html').read_text(encoding='utf-8')
        js = (ROOT / 'app/webinterface/statisch/dashboard.js').read_text(encoding='utf-8')
        css = (ROOT / 'app/webinterface/statisch/stijl.css').read_text(encoding='utf-8')
        for id, pad in [('knop-dashboard-pagina','#dashboard'),('knop-bibliotheek-pagina','#bibliotheek'),('knop-instellingen','#instellingen')]:
            self.assertIn(f'id="{id}"', html)
            self.assertIn(f'href="{pad}"', html)
        self.assertIn("knop.setAttribute('aria-current', 'page')", js)
        self.assertIn('.navigatie-link[aria-current="page"]', css)
        self.assertIn('id="bibliotheek-reset-bevestiging"', html)
        self.assertIn("bevestiging.value !== 'BEVESTIG'", js)
        self.assertIn("'/api/bibliotheek/leegmaken'", js)
        self.assertIn('werkSnelleStemweergaveBij()', js)
        self.assertNotIn("keuze.dataset.speelNaKiezen", js)
        self.assertIn('waarde.title = uitleg', js)
        self.assertIn('Aantal keren uitgezonden via de virtuele microfoon', js)
        self.assertIn('Totale duur van het fragment', js)
        self.assertEqual(html.count('id="knop-bibliotheek-pagina"'),1)


if __name__ == '__main__':
    unittest.main()
