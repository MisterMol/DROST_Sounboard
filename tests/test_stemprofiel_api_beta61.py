"""Stemprofiel-API gebruikt localhost + CSRF-token en schrijft nooit microfoonaudio."""
from __future__ import annotations

from pathlib import Path
import json
import logging
import tempfile
import threading
import unittest
from unittest.mock import MagicMock, patch
from urllib.request import Request, urlopen
from urllib.error import HTTPError

from app.audio.apparatenbeheer import GevondenAudioapparaat, ResultaatVanApparaatcontrole
from app.diagnostiek.logboek import BeschikbareLogboeken
from app.webinterface.bediening_van_de_audiomotor import WebbedieningVanDrostSoundboard, OngeldigeWebactie
from app.webinterface.lokale_webserver import LokaleWebserverVanDrostSoundboard


class TestStemprofielWebAPI(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory()
        logger = MagicMock(spec=logging.Logger)
        cls.logs = BeschikbareLogboeken(logger, logger, Path(cls.temp.name), 'test')
        cls.bediening = WebbedieningVanDrostSoundboard(object(), cls.logs, Path(cls.temp.name)/'geluid.sqlite3')
        cls.server = LokaleWebserverVanDrostSoundboard(('127.0.0.1',0),cls.bediening)
        cls.url = f'http://127.0.0.1:{cls.server.server_port}'
        cls.draad = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.draad.start()

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown();cls.server.server_close();cls.draad.join(timeout=4)
        cls.bediening.sluit_alle_audio_af();cls.temp.cleanup()

    def verzoek(self,pad,gegevens=None,token=True):
        method = 'POST' if gegevens is not None else 'GET'
        headers={'Content-Type':'application/json'}
        if token and method=='POST':
            headers['X-Drost-Token']=self.server.schrijf_token
        request=Request(self.url+pad,method=method,headers=headers,
                        data=json.dumps(gegevens).encode() if gegevens is not None else None)
        with urlopen(request,timeout=5) as response:
            return response.status,json.loads(response.read())

    def test_profiel_read_write_met_directe_mixerinstelling(self):
        code, data = self.verzoek('/api/instellingen/stemprofiel')
        self.assertEqual(code,200)
        self.assertIn(data['profiel'],('normaal','robot','radio','diep'))
        code,result = self.verzoek('/api/instellingen/stemprofiel',{'profiel':'robot'})
        self.assertEqual(code,200)
        self.assertEqual(result['profiel'],'robot')
        self.assertEqual(self.bediening.mixer.geef_huidige_status().stemprofiel,'robot')
        code,result = self.verzoek('/api/instellingen/stemprofiel')
        self.assertEqual(result['profiel'],'robot')
        self.verzoek('/api/instellingen/stemprofiel',{'profiel':'normaal'})

    def test_post_vereist_correct_token(self):
        with self.assertRaises(HTTPError) as fout:
            self.verzoek('/api/instellingen/stemprofiel',{'profiel':'diep'}, token=False)
        self.assertEqual(fout.exception.code,400)

    def test_unknown_profil_blijft_ongewijzigd(self):
        with self.assertRaises(HTTPError) as fout:
            self.verzoek('/api/instellingen/stemprofiel',{'profiel':'fout'})
        self.assertEqual(fout.exception.code,400)

    def test_lokale_preview_weigert_live_audio(self):
        self.bediening.mixer._toestand='verbonden'
        try:
            with self.assertRaises(HTTPError) as fout:
                self.verzoek('/api/stemvoorbeeld/start',{'microfoonnummer':3})
            self.assertEqual(fout.exception.code,400)
            self.assertFalse(self.bediening.stemvoorbeeld.actief)
        finally:
            self.bediening.mixer._toestand='verbroken'

    def test_virtuele_uitvoer_wordt_geweigerd_zonder_aanzetten_stream(self):
        mic=GevondenAudioapparaat(3,'USB microfoon','Windows WASAPI',1,0)
        kabel=GevondenAudioapparaat(7,'CABLE Input (VB-Audio Virtual Cable)','Windows WASAPI',0,2)
        overzicht=ResultaatVanApparaatcontrole([mic,kabel],True,True,True)
        with patch('app.webinterface.bediening_van_de_audiomotor.controleer_werkelijk_aangesloten_audioapparaten',return_value=overzicht):
            with self.assertRaisesRegex(OngeldigeWebactie,'STEM-025'):
                self.bediening.begin_stemvoorbeeld(3,7)
        self.assertFalse(self.bediening.stemvoorbeeld.actief)

    def test_stop_preview_route_is_veilig_ook_wanneer_niets_speelt(self):
        code, data=self.verzoek('/api/stemvoorbeeld/stop',{})
        self.assertEqual(code,200)
        self.assertFalse(data['actief'])

if __name__ == '__main__':
    unittest.main()
