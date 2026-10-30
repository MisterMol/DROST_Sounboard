"""Echte HTTP-routes en keuzecode met vervangende mixer en voorbeeldbron."""
import json
import unittest
from types import SimpleNamespace
from unittest.mock import Mock
import test_beta6417_http as httpbasis
import test_beta6417_stemkeuze as keuzebasis
from test_beta6418_voorbeeldaudio import wav, toon

class TestBronBediening418(unittest.TestCase):
    setUp=keuzebasis.TestVoorbeeldKeuze417.setUp
    def test_bron_is_onbewerkt_en_kiest_geen_andere_stem(self):
        data=wav(toon());self.bron.return_value=data
        self.assertEqual(self.c.maak_stemkeuze_bron('bob','verzoek_418'),data)
        self.bron.assert_called_once_with('bob','normaal',100,self.params)
        self.c.natuurlijke_stem.stel_in.assert_not_called()
        self.c.natuurlijke_stem.kies_variant.assert_not_called()
        self.c.stemkeuze_voorbeelden.render.assert_not_called()
    def test_bron_werkt_ook_tijdens_model_laden(self):
        self.c.natuurlijke_stem.status.return_value={'test_bezig':False,'toestand':'laden'}
        self.bron.return_value=wav(toon());self.c.maak_stemkeuze_bron('elise','verzoek_418')
        self.assertEqual(self.bron.call_args.args[0],'elise')
    def test_geen_bron_tijdens_eigen_microfoontest(self):
        self.c.stemvoorbeeld.actief=True
        with self.assertRaises(ValueError):self.c.maak_stemkeuze_bron('bob','verzoek_418')
        self.bron.assert_not_called()
    def test_geen_bron_tijdens_afsluiten(self):
        self.c._wordt_afgesloten=True
        with self.assertRaises(ValueError):self.c.maak_stemkeuze_bron('bob','verzoek_418')
    def test_ongeldige_spreker_of_verzoek_geweigerd(self):
        for speaker,req in [('extern','verzoek_418'),('bob','../bad'),([], 'verzoek_418')]:
            with self.subTest(speaker=speaker),self.assertRaises(ValueError):self.c.maak_stemkeuze_bron(speaker,req)
        self.bron.assert_not_called()
    def test_geen_ongeldige_audio_naar_browser(self):
        self.bron.return_value=b'not-wav'
        with self.assertRaises(ValueError):self.c.maak_stemkeuze_bron('bob','verzoek_418')
        self.assertTrue(self.c._stemvoorbeeld_render_slot.acquire(blocking=False))
    def test_late_bron_na_ander_profiel_geweigerd(self):
        def source(*args):
            self.c._stemkeuze_generatie+=1;return wav(toon())
        self.bron.side_effect=source
        with self.assertRaises(ValueError):self.c.maak_stemkeuze_bron('bob','verzoek_418')
    def test_fout_in_render_maakt_slot_vrij(self):
        self.bron.side_effect=RuntimeError('test')
        with self.assertRaises(RuntimeError):self.c.maak_stemkeuze_bron('bob','verzoek_418')
        self.assertTrue(self.c._stemvoorbeeld_render_slot.acquire(blocking=False))

class TestLaadHTTP418(unittest.TestCase):
    setUp=httpbasis.TestStemKeuzeHTTP417.setUp
    tearDown=httpbasis.TestStemKeuzeHTTP417.tearDown
    request=httpbasis.TestStemKeuzeHTTP417.request
    source='/api/stemkeuze/bron?spreker=bob&verzoek=verzoek_418'
    def test_bron_met_token(self):
        self.server.bediening.maak_stemkeuze_bron.return_value=b'RIFFtest'
        code,data,mime=self.request(self.source,method='GET')
        self.assertEqual((code,data,mime),(200,b'RIFFtest','audio/wav'))
        self.server.bediening.maak_stemkeuze_bron.assert_called_once_with('bob','verzoek_418')
    def test_bron_zonder_token_geweigerd(self):self.assertEqual(self.request(self.source,headers={'X-Drost-Token':''},method='GET')[0],400)
    def test_bron_andere_origin_geweigerd(self):self.assertEqual(self.request(self.source,headers={'Origin':'https://fout.example'},method='GET')[0],400)
    def test_bron_andere_host_geweigerd(self):self.assertEqual(self.request(self.source,headers={'Host':'fout.example'},method='GET')[0],400)
    def test_bron_extra_query_geweigerd(self):self.assertEqual(self.request(self.source+'&pad=extern.wav',method='GET')[0],400)
    def test_bron_dubbele_query_geweigerd(self):self.assertEqual(self.request(self.source+'&spreker=elise',method='GET')[0],400)
    def test_bron_onbekende_spreker_geweigerd(self):self.assertEqual(self.request(self.source.replace('bob','extern'),method='GET')[0],400)
    def test_bron_na_afsluiten_geweigerd(self):
        self.server.wordt_afgesloten.set();self.assertEqual(self.request(self.source,method='GET')[0],400)
    def test_effecten_bevestiging_na_verwerking(self):
        self.server.bediening.mixer.geef_huidige_status.return_value=SimpleNamespace(toestand='verbonden',geluidseffecten_aan=True)
        code,data,_=self.request('/api/effecten',{'aan':True})
        self.assertEqual(code,200);self.assertEqual(json.loads(data),dict(toestand='verbonden',effecten_aan=True,in_behandeling=False))
        self.server.bediening.zet_soundboard_aan_of_uit.assert_called_once_with(True)
    def test_effecten_wacht_op_wachtrij_niet_alleen_acceptatie(self):
        values=[SimpleNamespace(toestand='verbonden',geluidseffecten_aan=False),SimpleNamespace(toestand='verbonden',geluidseffecten_aan=True)]
        self.server.bediening.mixer.geef_huidige_status.side_effect=values
        code,data,_=self.request('/api/effecten',{'aan':True});self.assertEqual(code,200)
        self.assertTrue(json.loads(data)['effecten_aan']);self.assertEqual(self.server.bediening.mixer.geef_huidige_status.call_count,2)
    def test_nog_niet_verwerkt_geeft_202_geen_nep_succes(self):
        self.server.bediening.mixer.geef_huidige_status.return_value=SimpleNamespace(toestand='verbonden',geluidseffecten_aan=False)
        code,data,_=self.request('/api/effecten',{'aan':True});self.assertEqual(code,202)
        self.assertTrue(json.loads(data)['in_behandeling']);self.assertFalse(json.loads(data)['effecten_aan'])
    def test_verbinding_weg_blijft_onbevestigd(self):
        self.server.bediening.mixer.geef_huidige_status.return_value=SimpleNamespace(toestand='verbroken',geluidseffecten_aan=False)
        code,data,_=self.request('/api/effecten',{'aan':True});self.assertEqual(code,202);self.assertEqual(json.loads(data)['toestand'],'verbroken')
    def test_effecten_foute_types_of_extra_velden_geweigerd(self):
        for body in ({'aan':1},{'aan':'true'},{'aan':True,'extra':1},{}):
            with self.subTest(body=body):self.assertEqual(self.request('/api/effecten',body)[0],400)
        self.server.bediening.zet_soundboard_aan_of_uit.assert_not_called()
    def test_effecten_zonder_token_geweigerd(self):self.assertEqual(self.request('/api/effecten',{'aan':True},headers={'X-Drost-Token':''})[0],400)
    def test_effecten_fout_geen_verzonnen_stand(self):
        self.server.bediening.zet_soundboard_aan_of_uit.side_effect=ValueError('Geen verbinding.')
        code,data,_=self.request('/api/effecten',{'aan':True});self.assertEqual(code,400)
        self.assertNotIn('effecten_aan',json.loads(data))

if __name__=='__main__':unittest.main()
