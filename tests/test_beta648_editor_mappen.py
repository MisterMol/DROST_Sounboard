"""Beta 4.8: groepskoppelingen, tijdelijke fragmentweergave en neutrale editor."""
from __future__ import annotations

import json
import logging
from pathlib import Path
import shutil
import subprocess
from tempfile import TemporaryDirectory
import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch
from urllib.error import HTTPError
from urllib.request import Request, urlopen
import threading
import wave

from app.diagnostiek.logboek import maak_logboeken_klaar, sluit_logboeken_netjes_af
from app.webinterface.bediening_van_de_audiomotor import WebbedieningVanDrostSoundboard, OngeldigeWebactie
from app.webinterface.geluidsgroepen import GroepsinstellingOngeldig
from app.webinterface.lokale_webserver import LokaleWebserverVanDrostSoundboard


class TestBeta648EditorMappen(unittest.TestCase):
    def setUp(self):
        self.tijdelijk = TemporaryDirectory()
        self.pad = Path(self.tijdelijk.name)
        self.logs = maak_logboeken_klaar(self.pad / 'logs')
        self.bediening = WebbedieningVanDrostSoundboard(Mock(), self.logs, self.pad / 'bibliotheek.sqlite3')
        self.wav = self.pad / 'demo.wav'
        with wave.open(str(self.wav), 'wb') as bestand:
            bestand.setnchannels(1)
            bestand.setsampwidth(2)
            bestand.setframerate(16000)
            bestand.writeframes(b'\x01\x00' * 32000)
        self.items = self.bediening.geluidenbibliotheek.voeg_geluidsbestanden_toe([self.wav])
        self.geluid_id = self.items[0].geluid_id

    def tearDown(self):
        self.bediening.sluit_alle_audio_af()
        sluit_logboeken_netjes_af(self.logs)
        self.tijdelijk.cleanup()

    def test_meerdere_geluiden_uit_een_map_halen_bewaart_andere_koppelingen(self):
        groep = self.bediening.groepen.maak_groep('Verkeerde map')
        ander = self.bediening.groepen.maak_groep('Juiste map')
        ander_bestand = self.pad / 'ander.wav'
        with wave.open(str(ander_bestand), 'wb') as bestand:
            bestand.setnchannels(1)
            bestand.setsampwidth(2)
            bestand.setframerate(16000)
            bestand.writeframes(b'\x02\x00' * 16000)
        extra = self.bediening.geluidenbibliotheek.voeg_geluidsbestanden_toe([ander_bestand])[0]
        self.bediening.groepen.verander_lidmaatschap(groep, self.geluid_id, True)
        self.bediening.groepen.verander_lidmaatschap(groep, extra.geluid_id, True)
        self.bediening.groepen.verander_lidmaatschap(ander, self.geluid_id, True)
        aantal = self.bediening.groepen.verwijder_meerdere_geluiden_uit_groep(groep,
            [self.geluid_id, extra.geluid_id, self.geluid_id])
        self.assertEqual(aantal, 2)
        koppelingen = self.bediening.groepen.geef_groepsnummers_per_geluid()
        self.assertEqual(koppelingen[self.geluid_id], [ander])
        self.assertNotIn(extra.geluid_id, koppelingen)
        self.assertEqual(len(self.bediening.geluidenbibliotheek.geef_alle_geluiden()), 2)
        self.assertTrue(self.wav.is_file())

    def test_ongeldige_selectie_verandert_geen_koppelingen(self):
        groep = self.bediening.groepen.maak_groep('Eerste map')
        self.bediening.groepen.verander_lidmaatschap(groep, self.geluid_id, True)
        voor = self.bediening.groepen.geef_groepsnummers_per_geluid()
        for IDs in ([], [self.geluid_id, 'onjuist'], [self.geluid_id, 'aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa'],
                    [self.geluid_id] * 251):
            with self.subTest(IDs=IDs), self.assertRaises(GroepsinstellingOngeldig):
                self.bediening.groepen.verwijder_meerdere_geluiden_uit_groep(groep, IDs)
            self.assertEqual(self.bediening.groepen.geef_groepsnummers_per_geluid(), voor)

    def test_editorselectie_is_tijdelijk_en_beïnvloedt_opgeslagen_volume_niet(self):
        originele = self.bediening.favorieten.geef_instellingen_van_geluid(self.geluid_id)
        nep_status = SimpleNamespace(toestand='verbonden', geluidseffecten_aan=True)
        mock_executor = Mock()
        with patch.object(self.bediening.mixer, 'geef_huidige_status', return_value=nep_status), \
             patch.object(self.bediening, '_werkdraad_voor_decoderen', mock_executor):
            self.bediening.speel_geluid_uit_de_bibliotheek(self.geluid_id, {
                'beginpositie': .25, 'maximale_duur': .5, 'volume': 1.5})
        _, args, _ = mock_executor.submit.mock_calls[0]
        tijdelijk = args[3]
        self.assertAlmostEqual(tijdelijk.begint_bij_seconden, .25)
        self.assertAlmostEqual(tijdelijk.maximale_duur_seconden, .5)
        self.assertAlmostEqual(tijdelijk.volume, 1.5)
        self.assertEqual(self.bediening.favorieten.geef_instellingen_van_geluid(self.geluid_id), originele)

    def test_tijdelijke_parameters_worden_voor_afspelen_gevalideerd(self):
        for invoer in ({'beginpositie': 0},
                       {'beginpositie': 0, 'maximale_duur': 2, 'volume': 3},
                       {'beginpositie': False, 'maximale_duur': 1, 'volume': 1},
                       {'beginpositie': 0, 'maximale_duur': 1, 'volume': 1, 'extra': 1}):
            with self.subTest(invoer=invoer), self.assertRaises(ValueError):
                self.bediening.speel_geluid_uit_de_bibliotheek(self.geluid_id, invoer)

    def test_preview_luistert_naar_individueel_volume_zonder_opslaan(self):
        # De app vergelijkt in de editor een niet-opgeslagen volume met dezelfde clip.
        with patch('app.webinterface.bediening_van_de_audiomotor.bereken_browser_preview_versterkingen',
                   side_effect=lambda *args, **kw: {'volume_test': kw['volume']}) as berekening:
            laag = self.bediening.geef_preview_normalisatie(self.geluid_id, .1, .8, .6)
            hoog = self.bediening.geef_preview_normalisatie(self.geluid_id, .1, .8, 1.5)
        self.assertEqual(laag['volume_test'], .6)
        self.assertEqual(hoog['volume_test'], 1.5)
        self.assertEqual(berekening.call_count, 2)
        self.assertEqual(self.bediening.favorieten.geef_instellingen_van_geluid(self.geluid_id).volume, 1)

    @unittest.skipUnless(shutil.which('node'), 'Node.js niet beschikbaar')
    def test_javascript_doorzoekbare_groepen_editor_en_uitzendknop(self):
        helper = Path(__file__).parent / 'hulpmiddelen' / 'test_editor_groepen_beta648.js'
        resultaat = subprocess.run(['node', str(helper)], text=True, capture_output=True, timeout=20)
        self.assertEqual(resultaat.returncode, 0, resultaat.stdout + resultaat.stderr)
        self.assertIn('OK: editor', resultaat.stdout)


class TestBeta648WebApi(unittest.TestCase):
    """Echte HTTP-aanvragen met schrijftoken; geen fysieke audioapparaten nodig."""
    def setUp(self):
        import os
        self.tijdelijk = TemporaryDirectory()
        self.pad = Path(self.tijdelijk.name)
        self.oude_appdata = os.environ.get('LOCALAPPDATA')
        os.environ['LOCALAPPDATA'] = str(self.pad)
        self.logs = maak_logboeken_klaar(self.pad / 'logs')
        self.bediening = WebbedieningVanDrostSoundboard(Mock(), self.logs, self.pad / 'app.sqlite3')
        self.server = LokaleWebserverVanDrostSoundboard(('127.0.0.1', 0), self.bediening)
        self.draad = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.draad.start()
        self.root = f'http://127.0.0.1:{self.server.server_port}'
        self.wav = self.server.media_map / 'geluiden' / 'test.wav'
        with wave.open(str(self.wav), 'wb') as bestand:
            bestand.setnchannels(1); bestand.setsampwidth(2); bestand.setframerate(16000)
            bestand.writeframes(b'\x01\x00'*32000)
        self.geluid = self.bediening.geluidenbibliotheek.voeg_geluidsbestanden_toe([self.wav])[0]

    def tearDown(self):
        import os
        self.server.shutdown(); self.server.server_close(); self.draad.join(timeout=3)
        self.bediening.sluit_alle_audio_af(); sluit_logboeken_netjes_af(self.logs)
        if self.oude_appdata is None: os.environ.pop('LOCALAPPDATA', None)
        else: os.environ['LOCALAPPDATA'] = self.oude_appdata
        self.tijdelijk.cleanup()

    def post(self, route, data, token=True):
        koppen = {'Content-Type':'application/json'}
        if token: koppen['X-Drost-Token'] = self.server.schrijf_token
        verzoek = Request(self.root + route, headers=koppen,
            data=json.dumps(data).encode('utf-8'), method='POST')
        try:
            with urlopen(verzoek, timeout=8) as antwoord:
                return antwoord.status, json.load(antwoord)
        except HTTPError as fout:
            return fout.code, json.load(fout)

    def test_groepsontkoppeling_veilig_via_http(self):
        groep = self.bediening.groepen.maak_groep('Map A')
        self.bediening.groepen.verander_lidmaatschap(groep, self.geluid.geluid_id, True)
        route = '/api/bibliotheek/groep-losmaken'
        payload = {'groep_id':groep,'geluid_ids':[self.geluid.geluid_id]}
        zonder_token, _ = self.post(route,payload,token=False)
        self.assertNotEqual(zonder_token,200)
        fout, _ = self.post(route, {'groep_id':groep,'geluid_ids':[self.geluid.geluid_id, 'onjuiste-id']})
        self.assertEqual(fout,400)
        self.assertIn(groep,self.bediening.groepen.geef_groepsnummers_per_geluid()[self.geluid.geluid_id])
        status, resultaat = self.post(route,payload)
        self.assertEqual(status,200)
        self.assertEqual(resultaat['aantal'],1)
        self.assertEqual(len(self.bediening.geluidenbibliotheek.geef_alle_geluiden()),1)

    def test_editor_uizenden_accepteert_tijdelijke_selectie_met_token(self):
        route = f'/api/geluiden/{self.geluid.geluid_id}/afspelen'
        payload = {'beginpositie':.25, 'maximale_duur':.75, 'volume':1.6}
        fout, _ = self.post(route,payload,token=False)
        self.assertNotEqual(fout,202)
        status = SimpleNamespace(toestand='verbonden',geluidseffecten_aan=True)
        with patch.object(self.bediening.mixer,'geef_huidige_status',return_value=status), \
             patch.object(self.bediening,'_werkdraad_voor_decoderen',Mock()) as uitvoerder:
            resultaat, _ = self.post(route,payload)
            self.assertEqual(resultaat,202)
            _, args, _ = uitvoerder.submit.mock_calls[0]
            self.assertEqual(args[3].volume,1.6)
            fout, _ = self.post(route, {'beginpositie':1,'maximale_duur':1,'volume':20})
            self.assertEqual(fout,400)

    def test_preview_api_kan_volume_van_editor_zonder_opslaan_berekenen(self):
        # Betrouwbaar toetsen op query-parsing en dezelfde DSP-methode.
        route = f'/api/geluiden/{self.geluid.geluid_id}/preview-normalisatie?begin=0.2&duur=0.4&volume=1.5'
        with patch.object(self.bediening, 'geef_preview_normalisatie',return_value={'correcties_db': {'uit': 0}, 'versterkingen':{'uit':1}}) as controle:
            with urlopen(Request(self.root+route,headers={'X-Drost-Token':self.server.schrijf_token}),timeout=8) as antwoord:
                self.assertEqual(antwoord.status,200)
            controle.assert_called_once_with(self.geluid.geluid_id,.2,.4,1.5)
