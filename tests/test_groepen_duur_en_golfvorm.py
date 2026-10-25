"""De huidige lengte, groepen en de editor mogen oude favorieten niet beschadigen."""
from __future__ import annotations

from io import BytesIO
from pathlib import Path
from tempfile import TemporaryDirectory
import json
import math
import os
import threading
import unittest
from unittest.mock import patch
from urllib.error import HTTPError
from urllib.request import Request, urlopen
import wave

import numpy as np

from app.audio.bronduur_en_golfvorm import (bepaal_werkelijke_bronduur,
    bepaal_werkelijke_fragmentduur, maak_golfvorm_voor_tijdsvenster,
    BronbestandNietLeesbaar)
from app.audio.geluidenbibliotheek import PersoonlijkeGeluidenbibliotheek
from app.diagnostiek.logboek import maak_logboeken_klaar, sluit_logboeken_netjes_af
from app.webinterface.geluidsgroepen import PersoonlijkeGeluidsgroepen, GroepsinstellingOngeldig
from app.webinterface.favorieten_en_instellingen import VasteFavorietenEnInstellingen
from app.webinterface.bediening_van_de_audiomotor import WebbedieningVanDrostSoundboard
from app.webinterface.lokale_webserver import LokaleWebserverVanDrostSoundboard


def maak_wav(bestandspad: Path, seconden: float):
    """Genereer een kleine, echte testbron met exact de gevraagde lengte."""
    samplefrequentie = 8000
    waarden = (np.sin(2 * np.pi * 320 * np.arange(round(seconden * samplefrequentie)) / samplefrequentie) * 12000).astype('<i2')
    with wave.open(str(bestandspad), 'wb') as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(samplefrequentie)
        wav.writeframes(waarden.tobytes())


class TestGeluidsduurEnGroepen(unittest.TestCase):
    def setUp(self):
        self.tijdelijk = TemporaryDirectory()
        self.map = Path(self.tijdelijk.name)
        self.databasepad = self.map / 'bibliotheek.sqlite3'
        self.bibliotheek = PersoonlijkeGeluidenbibliotheek(self.databasepad)
        self.groepen = PersoonlijkeGeluidsgroepen(self.databasepad)
        self.favorieten = VasteFavorietenEnInstellingen(self.databasepad)
        self.geluidspad = self.map / 'south_park.wav'
        maak_wav(self.geluidspad, 29)
        self.geluid = self.bibliotheek.voeg_geluidsbestanden_toe([self.geluidspad])[0]

    def tearDown(self):
        self.tijdelijk.cleanup()

    def test_29_seconden_is_werkelijk_29_en_nooit_120(self):
        self.assertEqual(bepaal_werkelijke_bronduur(self.geluidspad), 29)
        self.assertEqual(bepaal_werkelijke_fragmentduur(29, 0, 120), 29)
        self.assertEqual(bepaal_werkelijke_fragmentduur(29, 10, 120), 19)
        self.assertEqual(bepaal_werkelijke_fragmentduur(29, 25, 2.5), 2.5)
        self.assertEqual(bepaal_werkelijke_fragmentduur(None, 0, 120), None)

    def test_golfvorm_komt_uit_het_echte_bestand(self):
        pieken = maak_golfvorm_voor_tijdsvenster(self.geluidspad, 0, 1, aantal_kolommen=64)
        self.assertEqual(len(pieken), 64)
        self.assertAlmostEqual(max(pieken), 1.0, places=2)
        self.assertGreater(min(pieken), 0.9)

    def test_willekeurige_en_te_lange_golfvorm_wordt_geweigerd(self):
        for begin, duur in [(-1, 2), (0, 121), (float('nan'), 1), (0, 0)]:
            with self.subTest(begin=begin, duur=duur), self.assertRaises(BronbestandNietLeesbaar):
                maak_golfvorm_voor_tijdsvenster(self.geluidspad, begin, duur)

    def test_south_park_groep_wordt_bewaard_na_herstart(self):
        nummer = self.groepen.maak_groep('South Park')
        self.groepen.verander_lidmaatschap(nummer, self.geluid.geluid_id, True)
        heropen = PersoonlijkeGeluidsgroepen(self.databasepad)
        self.assertEqual(heropen.geef_alle_groepen()[0]['naam'], 'South Park')
        self.assertEqual(heropen.geef_groepsnummers_per_geluid()[self.geluid.geluid_id], [nummer])

    def test_geluid_kan_in_meerdere_groepen_zitten(self):
        a = self.groepen.maak_groep('South Park')
        b = self.groepen.maak_groep('Memes')
        for nummer in (a, b):
            self.groepen.verander_lidmaatschap(nummer, self.geluid.geluid_id, True)
        self.assertEqual(set(self.groepen.geef_groepsnummers_per_geluid()[self.geluid.geluid_id]), {a, b})

    def test_groep_verwijderen_laat_geluid_en_favoriet_staan(self):
        groep = self.groepen.maak_groep('South Park')
        self.groepen.verander_lidmaatschap(groep, self.geluid.geluid_id, True)
        self.favorieten.zet_een_geluid_op_een_vaste_plek(8, self.geluid.geluid_id)
        self.groepen.verwijder_groep(groep)
        self.assertEqual(len(self.bibliotheek.geef_alle_geluiden()), 1)
        self.assertEqual(self.favorieten.geef_alle_favorietplekken()[7], self.geluid.geluid_id)
        self.assertTrue(self.geluidspad.is_file())

    def test_dubbele_groepsnaam_met_andere_hoofdletters_wordt_geweigerd(self):
        self.groepen.maak_groep('South Park')
        with self.assertRaises(GroepsinstellingOngeldig):
            self.groepen.maak_groep('south park')


class TestNieuweHttpFuncties(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tijdelijk = TemporaryDirectory()
        cls.map = Path(cls.tijdelijk.name)
        cls.env = patch.dict(os.environ, {'LOCALAPPDATA': str(cls.map)})
        cls.env.start()
        cls.logboeken = maak_logboeken_klaar(cls.map / 'logs')
        cls.bediening = WebbedieningVanDrostSoundboard(object(), cls.logboeken, cls.map/'bibliotheek.sqlite3')
        cls.server = LokaleWebserverVanDrostSoundboard(('127.0.0.1', 0), cls.bediening)
        cls.url = f'http://127.0.0.1:{cls.server.server_port}'
        cls.draad = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.draad.start()
        cls.geluidspad = cls.map / 'hello.wav'
        maak_wav(cls.geluidspad, 29)
        cls.geluid = cls.bediening.geluidenbibliotheek.voeg_geluidsbestanden_toe([cls.geluidspad])[0]

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.draad.join(timeout=3)
        cls.bediening.sluit_alle_audio_af()
        sluit_logboeken_netjes_af(cls.logboeken)
        cls.env.stop()
        cls.tijdelijk.cleanup()

    def aanvraag(self, pad, methode='GET', data=None, token=True):
        koppen = {}
        ruwe = None
        if methode != 'GET':
            if token:
                koppen['X-Drost-Token'] = self.server.schrijf_token
            if methode == 'POST':
                koppen['Content-Type'] = 'application/json'
                ruwe = json.dumps(data or {}).encode()
        with urlopen(Request(self.url+pad, data=ruwe, headers=koppen, method=methode), timeout=12) as response:
            return response.status, json.loads(response.read())

    def test_bibliotheek_toont_echte_29_seconden(self):
        _, antwoord = self.aanvraag('/api/bibliotheek')
        geluid = next(x for x in antwoord['geluiden'] if x['id'] == self.geluid.geluid_id)
        self.assertEqual(geluid['bronduur'], 29)
        self.assertEqual(geluid['fragmentduur'], 29)
        self.assertEqual(geluid['maximale_duur'], 120)

    def test_groep_http_maken_koppelen_en_verwijderen(self):
        _, antwoord = self.aanvraag('/api/groepen', 'POST', {'naam': 'South Park'})
        groep = antwoord['groep_id']
        self.aanvraag(f'/api/groepen/{groep}/geluiden', 'POST', {'geluid_id': self.geluid.geluid_id})
        _, bibliotheek = self.aanvraag('/api/bibliotheek')
        geluid = next(x for x in bibliotheek['geluiden'] if x['id'] == self.geluid.geluid_id)
        self.assertIn(groep, geluid['groep_ids'])
        self.aanvraag(f'/api/groepen/{groep}/geluiden/{self.geluid.geluid_id}', 'DELETE')
        self.aanvraag(f'/api/groepen/{groep}', 'DELETE')
        _, bibliotheek = self.aanvraag('/api/bibliotheek')
        self.assertNotIn(groep, {g['id'] for g in bibliotheek['groepen']})

    def test_waveform_endpoint_geeft_echte_monsterpunten(self):
        _, antwoord = self.aanvraag(f'/api/geluiden/{self.geluid.geluid_id}/golfvorm?begin=0&duur=10')
        self.assertEqual(len(antwoord['pieken']), 160)
        self.assertAlmostEqual(antwoord['bronduur'], 29)
        self.assertTrue(max(antwoord['pieken']) > 0)

    def test_golfvorm_met_640_kolommen_geeft_ook_rms_terug(self):
        _, antwoord = self.aanvraag(
            f'/api/geluiden/{self.geluid.geluid_id}/golfvorm?begin=0&duur=10&resolutie=640'
        )
        self.assertEqual(len(antwoord['pieken']), 640)
        self.assertEqual(len(antwoord['rms']), 640)
        self.assertEqual(antwoord['resolutie'], 640)
        self.assertTrue(max(antwoord['pieken']) > 0)

    def test_server_weigert_onbegrensde_golfvormresolutie(self):
        for resolutie in (-1, 1201, 'foo'):
            with self.subTest(resolutie=resolutie), self.assertRaises(HTTPError) as fout:
                self.aanvraag(
                    f'/api/geluiden/{self.geluid.geluid_id}/golfvorm?begin=0&duur=10&resolutie={resolutie}'
                )
            self.assertEqual(fout.exception.code, 400)

    def test_editor_cursor_verplaatsen_wordt_als_preview_gelogd(self):
        antwoord, body = self.aanvraag('/api/preview', 'POST', {
            'geluid_id': self.geluid.geluid_id,
            'actie': 'verplaatst',
            'verstreken_seconden': 4.5,
            'reden': 'editor_cursor_verplaatst',
        })
        self.assertEqual(antwoord, 200)
        self.assertIn('opgeslagen', body['melding'].lower())

    def test_golfvorm_weigert_meer_dan_120_seconden(self):
        with self.assertRaises(HTTPError) as fout:
            self.aanvraag(f'/api/geluiden/{self.geluid.geluid_id}/golfvorm?begin=0&duur=180')
        self.assertEqual(fout.exception.code, 400)

    def test_groep_schrijven_zonder_token_kan_niet(self):
        with self.assertRaises(HTTPError) as fout:
            self.aanvraag('/api/groepen', 'POST', {'naam': 'Mag niet'}, token=False)
        self.assertEqual(fout.exception.code, 400)

    def test_browserfout_wordt_als_softwarefout_aangenomen(self):
        status, antwoord = self.aanvraag('/api/frontendfout', 'POST', {
            'melding': 'De knop werkte niet',
            'stapel': 'TypeError: ...\n    at beginDashboard (dashboard.js:10)',
        })
        self.assertEqual(status, 200)
        self.assertIn('geregistreerd', antwoord['melding'].lower())

    def test_echt_fragment_is_korter_als_begin_verschuift(self):
        geluid_id = self.geluid.geluid_id
        self.aanvraag(f'/api/geluiden/{geluid_id}/instellingen', 'POST', {
            'naam': 'hello', 'beginpositie': 10, 'volume': 0.35, 'maximale_duur': 120,
        })
        try:
            _, data = self.aanvraag('/api/bibliotheek')
            item = next(g for g in data['geluiden'] if g['id'] == geluid_id)
            self.assertEqual(item['bronduur'], 29)
            self.assertEqual(item['fragmentduur'], 19)
        finally:
            self.aanvraag(f'/api/geluiden/{geluid_id}/instellingen', 'POST', {
                'naam': 'hello', 'beginpositie': 0, 'volume': 0.35, 'maximale_duur': 120,
            })

class TestGroepOpslaanAlsEenTransactie(unittest.TestCase):
    def test_ongeldige_nieuwe_groep_verwijdert_bestaande_niet(self):
        with TemporaryDirectory() as naam:
            map = Path(naam)
            bibliotheek = PersoonlijkeGeluidenbibliotheek(map/'db.sqlite')
            groepen = PersoonlijkeGeluidsgroepen(map/'db.sqlite')
            pad = map/'toon.wav'
            maak_wav(pad, 1)
            geluid_id = bibliotheek.voeg_geluidsbestanden_toe([pad])[0].geluid_id
            bestaande_groep = groepen.maak_groep('South Park')
            groepen.bewaar_groepen_voor_geluid(geluid_id, [bestaande_groep])
            with self.assertRaises(GroepsinstellingOngeldig):
                groepen.bewaar_groepen_voor_geluid(geluid_id, ['aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa'])
            self.assertEqual(groepen.geef_groepsnummers_per_geluid()[geluid_id], [bestaande_groep])

    def test_atomair_opslaan_kan_meerdere_groepen_toevoegen(self):
        with TemporaryDirectory() as naam:
            map = Path(naam)
            bibliotheek = PersoonlijkeGeluidenbibliotheek(map/'db.sqlite')
            groepen = PersoonlijkeGeluidsgroepen(map/'db.sqlite')
            pad = map/'toon.wav'
            maak_wav(pad, 1)
            geluid_id = bibliotheek.voeg_geluidsbestanden_toe([pad])[0].geluid_id
            a, b = groepen.maak_groep('South Park'), groepen.maak_groep('Memes')
            groepen.bewaar_groepen_voor_geluid(geluid_id, [a, b])
            self.assertEqual(set(groepen.geef_groepsnummers_per_geluid()[geluid_id]), {a, b})
            groepen.bewaar_groepen_voor_geluid(geluid_id, [b])
            self.assertEqual(groepen.geef_groepsnummers_per_geluid()[geluid_id], [b])


class TestVideoMiniatuur(unittest.TestCase):
    def test_zelfgemaakte_mp4_krijgt_lichte_png(self):
        from app.audio.mp4_verwerken import geef_meegeleverde_ffmpeg, maak_miniatuur_van_videobeeld
        import subprocess
        with TemporaryDirectory() as naam:
            map = Path(naam)
            video = map/'test.mp4'
            poster = map/'test.png'
            commando = [geef_meegeleverde_ffmpeg(), '-y', '-nostdin', '-loglevel', 'error',
                        '-f', 'lavfi', '-i', 'color=c=blue:s=160x90:r=15:d=1.25',
                        '-f', 'lavfi', '-i', 'sine=frequency=660:duration=1.25',
                        '-c:v', 'libx264', '-pix_fmt', 'yuv420p',
                        '-c:a', 'aac', '-b:a', '96k', '-shortest', str(video)]
            resultaat = subprocess.run(commando, capture_output=True, timeout=25)
            self.assertEqual(resultaat.returncode, 0, resultaat.stderr.decode(errors='replace'))
            self.assertTrue(maak_miniatuur_van_videobeeld(video, poster))
            self.assertTrue(poster.read_bytes().startswith(b'\x89PNG\r\n\x1a\n'))
