"""Nieuwe routes op echte HTTP-sockets; numerieke callbacks met testprocessor.

Geen Windows-audio of getrainde LLVC-gewichten in deze tests.
"""
import time
from types import SimpleNamespace
from unittest.mock import Mock
import unittest
import numpy as np
import test_beta6413_afsluiten as afsluiten
function, SERVICE = afsluiten.function, afsluiten.SERVICE
from test_beta6413_stemveiligheid import mixer, isolated, ROOT

class TestNatuurlijkeHTTP(unittest.TestCase):
    setUp=afsluiten.TestHTTPAfsluiten.setUp
    tearDown=afsluiten.TestHTTPAfsluiten.tearDown
    def request(self,method='POST',data=None,headers=None):
        self.server.bediening.stel_natuurlijke_stem_in.return_value={'aan':True,'toestand':'laden'}
        self.server.bediening.geef_natuurlijke_stem_status.return_value={'aan':False,'toestand':'uit'}
        return afsluiten.TestHTTPAfsluiten.request(self,method=method,path='/api/natuurlijke-stem',data={} if data is None else data,headers=headers)
    def test_post_aan_met_token(self):
        code,data=self.request(data={'aan':True});self.assertEqual(code,202)
        self.server.bediening.stel_natuurlijke_stem_in.assert_called_once_with(True)
    def test_post_uit_met_token(self):
        self.assertEqual(self.request(data={'aan':False})[0],202)
        self.server.bediening.stel_natuurlijke_stem_in.assert_called_once_with(False)
    def test_get_wijzigt_niets(self):
        self.assertEqual(self.request(method='GET')[0],200)
        self.server.bediening.stel_natuurlijke_stem_in.assert_not_called()
    def test_token_verplicht(self):
        self.assertEqual(self.request(data={'aan':True},headers={'X-Drost-Token':''})[0],400)
        self.server.bediening.stel_natuurlijke_stem_in.assert_not_called()
    def test_origin_verplicht(self):
        self.assertEqual(self.request(data={'aan':True},headers={'Origin':'https://vreemd.example'})[0],400)
        self.server.bediening.stel_natuurlijke_stem_in.assert_not_called()
    def test_host_verplicht(self):
        self.assertEqual(self.request(data={'aan':True},headers={'Host':'vreemd.example'})[0],400)
        self.server.bediening.stel_natuurlijke_stem_in.assert_not_called()
    def test_parameter_whitelist(self):
        self.assertEqual(self.request(data={'aan':True,'command':'fake.exe'})[0],400)
        self.server.bediening.stel_natuurlijke_stem_in.assert_not_called()
    def test_alleen_echte_boolean(self):
        for value in (1,'true',None,[]):
            with self.subTest(value=value):self.assertEqual(self.request(data={'aan':value})[0],400)
        self.server.bediening.stel_natuurlijke_stem_in.assert_not_called()
    def test_afsluiting_blokkeert_inschakelen(self):
        self.server.wordt_afgesloten.set();self.assertEqual(self.request(data={'aan':True})[0],400)
        self.server.bediening.stel_natuurlijke_stem_in.assert_not_called()

class TestNeuraleMixer(unittest.TestCase):
    def setUp(self):
        self.m=mixer.LiveAudiomixer(Mock(),Mock(),Mock());self.m.stel_limiter_in(False)
        self.m.natuurlijke_stem=SimpleNamespace(aan=True,verwerk=Mock(side_effect=lambda x,route:x*.5))
        self.m._stemvervormer.verwerk=Mock(side_effect=AssertionError('DSP mag niet tegelijk verwerken'))
        self.x=np.full((480,1),.1,np.float32)
    def block(self):
        out=np.zeros((480,2),np.float32)
        self.m.verwerk_een_blok_live_audio(self.x,out,480,None,False)
        return out
    def test_neuraal_werkt_ook_bij_normaal_dsp(self):
        np.testing.assert_allclose(self.block(),.04,atol=1e-6)
        self.m.natuurlijke_stem.verwerk.assert_called_once()
        self.m._stemvervormer.verwerk.assert_not_called()
    def test_soundboard_wordt_niet_vervormd(self):
        self.m._verwerk_het_lopende_geluid_in_het_audioblok=lambda out:out.__iadd__(.2)
        np.testing.assert_allclose(self.block(),.24,atol=1e-6)
    def test_model_fout_nooit_onbewerkt(self):
        self.m.natuurlijke_stem.verwerk.side_effect=RuntimeError('test')
        np.testing.assert_array_equal(self.block(),0)
    def test_slechte_vorm_nooit_onbewerkt(self):
        self.m.natuurlijke_stem.verwerk.side_effect=None;self.m.natuurlijke_stem.verwerk.return_value=np.zeros((1,1),np.float32)
        np.testing.assert_array_equal(self.block(),0)
    def test_neuraal_uit_behouwt_normale_microfoon(self):
        self.m.natuurlijke_stem.aan=False;np.testing.assert_allclose(self.block(),.08,atol=1e-6)
    def test_filter_keuze_geweigerd_als_neuraal_aan(self):
        method=function(SERVICE,'_controleer_gewone_stemkeuze')
        with self.assertRaises(ValueError):method(SimpleNamespace(natuurlijke_stem=SimpleNamespace(aan=True)))

class TestNeuralePreview(unittest.TestCase):
    def setUp(self):
        preview=isolated(ROOT/'app/audio/stemvoorbeeld.py','test415_preview',Stemvervormer=Mock,
                         STANDAARD_INTENSITEITEN={'normaal':100},standaard_parameters=lambda:{})
        self.p=preview.LokaalStemvoorbeeld(Mock(),Mock())
        self.p.natuurlijke_stem=SimpleNamespace(aan=True,verwerk=Mock(side_effect=lambda x,route:x*.5))
        self.x=np.full((480,1),.1,np.float32);self.out=np.zeros((480,2),np.float32)
    def test_preview_gebruikt_neurale_audio(self):
        self.p._audio_callback(self.x,self.out,480,None,False)
        np.testing.assert_allclose(self.out,.0325,atol=1e-6)
        self.assertEqual(self.p.natuurlijke_stem.verwerk.call_args.args[1],'preview')
    def test_preview_fout_dempt_ook_bij_normaal_profiel(self):
        self.p.natuurlijke_stem.verwerk.side_effect=RuntimeError('test')
        self.p._audio_callback(self.x,self.out,480,None,False)
        np.testing.assert_array_equal(self.out,0)

if __name__=='__main__':unittest.main()
