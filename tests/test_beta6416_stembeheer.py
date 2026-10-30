"""Echte HTTP-sockets en controllerfuncties; audioapparaten vervangen door testobjecten."""
from types import SimpleNamespace
import threading
import unittest
from unittest.mock import Mock
import test_beta6413_afsluiten as basis

class TestStemHTTP416(unittest.TestCase):
    setUp=basis.TestHTTPAfsluiten.setUp
    tearDown=basis.TestHTTPAfsluiten.tearDown
    def vraag(self,data=None,headers=None,method='POST',path='/api/natuurlijke-stem/beheer'):
        self.server.bediening.beheer_natuurlijke_stem.return_value={'test_bezig':True}
        self.server.bediening.geef_natuurlijke_stem_rapport.return_value={'geen_microfoonopname':True}
        return basis.TestHTTPAfsluiten.request(self,method=method,path=path,data={} if data is None else data,headers=headers)
    def test_start_met_token(self):
        self.assertEqual(self.vraag({'actie':'test'})[0],202)
        self.server.bediening.beheer_natuurlijke_stem.assert_called_once_with('test',None)
    def test_stop_met_token(self):self.assertEqual(self.vraag({'actie':'stop_test'})[0],202)
    def test_buffer_met_token(self):
        self.assertEqual(self.vraag({'actie':'buffer','bufferprofiel':'direct'})[0],202)
        self.server.bediening.beheer_natuurlijke_stem.assert_called_once_with('buffer','direct')
    def test_geen_executable_parameters(self):self.assertEqual(self.vraag({'actie':'test','command':'other.exe'})[0],400)
    def test_buffer_alleen_whitelist(self):
        for x in ('gpu',None,[],42):
            with self.subTest(x=x):self.assertEqual(self.vraag({'actie':'buffer','bufferprofiel':x})[0],400)
    def test_actie_alleen_whitelist(self):
        for x in ('exec',None,[],42):
            with self.subTest(x=x):self.assertEqual(self.vraag({'actie':x})[0],400)
    def test_buffer_parameter_verplicht(self):self.assertEqual(self.vraag({'actie':'buffer'})[0],400)
    def test_geen_token_geweigerd(self):self.assertEqual(self.vraag({'actie':'test'},{'X-Drost-Token':''})[0],400)
    def test_vreemde_origin_geweigerd(self):self.assertEqual(self.vraag({'actie':'test'},{'Origin':'https://extern.example'})[0],400)
    def test_vreemde_host_geweigerd(self):self.assertEqual(self.vraag({'actie':'test'},{'Host':'extern.example'})[0],400)
    def test_afsluiten_blokkeert(self):
        self.server.wordt_afgesloten.set();self.assertEqual(self.vraag({'actie':'test'})[0],400)
    def test_get_beheer_doet_niets(self):
        self.assertEqual(self.vraag(method='GET')[0],404);self.server.bediening.beheer_natuurlijke_stem.assert_not_called()
    def test_rapport_get_neemt_niets_op(self):
        code,data=self.vraag(method='GET',path='/api/natuurlijke-stem/rapport');self.assertEqual(code,200)
        self.assertTrue(data['geen_microfoonopname']);self.server.bediening.beheer_natuurlijke_stem.assert_not_called()

class TestController416(unittest.TestCase):
    def setUp(self):
        self.f=basis.function(basis.SERVICE,'beheer_natuurlijke_stem')
        self.obj=SimpleNamespace(_bescherm_toestand=threading.RLock(),_wordt_afgesloten=False,
            mixer=Mock(),stemvoorbeeld=SimpleNamespace(actief=False),natuurlijke_stem=Mock())
        self.obj.mixer.geef_huidige_status.return_value=SimpleNamespace(toestand='verbroken')
    def test_test_zonder_verbinding(self):self.f(self.obj,'test');self.obj.natuurlijke_stem.test_computer.assert_called_once()
    def test_geen_test_in_gesprek(self):
        self.obj.mixer.geef_huidige_status.return_value.toestand='verbonden'
        with self.assertRaises(ValueError):self.f(self.obj,'test')
        self.obj.natuurlijke_stem.test_computer.assert_not_called()
    def test_geen_test_tijdens_verbinden(self):
        self.obj.mixer.geef_huidige_status.return_value.toestand='wordt_verbonden'
        with self.assertRaises(ValueError):self.f(self.obj,'test')
    def test_geen_test_met_preview(self):
        self.obj.stemvoorbeeld.actief=True
        with self.assertRaises(ValueError):self.f(self.obj,'test')
    def test_annuleren_mag_ook_tijdens_verbinding(self):
        self.obj.mixer.geef_huidige_status.return_value.toestand='verbonden';self.f(self.obj,'stop_test')
        self.obj.natuurlijke_stem.annuleer_test.assert_called_once()
    def test_buffer_overgedragen(self):self.f(self.obj,'buffer','direct');self.obj.natuurlijke_stem.stel_bufferprofiel_in.assert_called_once_with('direct')
    def test_afsluiten_geweigerd(self):
        self.obj._wordt_afgesloten=True
        with self.assertRaises(ValueError):self.f(self.obj,'test')
    def test_verbinden_tijdens_computertest_geweigerd(self):
        f=basis.function(basis.SERVICE,'_controleer_computertest')
        self.obj.natuurlijke_stem.status.return_value={'test_bezig':True}
        with self.assertRaises(ValueError):f(self.obj)
    def test_verbinden_zonder_computertest_toegestaan(self):
        f=basis.function(basis.SERVICE,'_controleer_computertest')
        self.obj.natuurlijke_stem.status.return_value={'test_bezig':False};f(self.obj)

if __name__=='__main__':unittest.main()
