"""Pure verwerkingstijd- en buffercontroles. Geen getraind model of audioapparaat."""
import math
from pathlib import Path
import tempfile
import time
import unittest
from unittest.mock import Mock, patch
import numpy as np
from app.audio.natuurlijke_stem.prestatie import BUFFERPROFIELEN, Meetvenster, beoordeel, controleer_profiel, percentiel, samenvatting
from app.audio.natuurlijke_stem.dienst import NatuurlijkeStemDienst, FRAMES

class TestMetingen416(unittest.TestCase):
    def test_percentiel_interpoleert(self):self.assertAlmostEqual(percentiel([10,20,30,40]),38.5)
    def test_lege_meting_is_onbekend_geen_nul(self):self.assertIsNone(samenvatting([])['gemiddeld_ms'])
    def test_te_laat_teller(self):self.assertEqual(samenvatting([10,52,53])['te_laat'],1)
    def test_budget_is_geen_cpu_percentage(self):self.assertEqual(samenvatting([26]*32)['budget_procent'],50)
    def test_snelle_test(self):self.assertTrue(beoordeel([15]*32,[14]*32,niet_stil=True,model_sha='test')['geslaagd'])
    def test_stille_test_geen_succes(self):self.assertEqual(beoordeel([15]*32,[14]*32,niet_stil=False,model_sha='test')['oordeel'],'geen_audio')
    def test_gemiddelde_te_langzaam(self):self.assertFalse(beoordeel([40]*32,[14]*32,niet_stil=True,model_sha='test')['geslaagd'])
    def test_p95_blokkeert_ook_bij_snel_gemiddelde(self):self.assertFalse(beoordeel([1]*29+[70]*3,[1]*32,niet_stil=True,model_sha='test')['geslaagd'])
    def test_afronding_wijzigt_geen_grens(self):self.assertTrue(beoordeel([36.3999]*32,[36]*32,niet_stil=True,model_sha='test')['geslaagd'])
    def test_ongeldige_tijden(self):
        for x in (math.nan,math.inf,-1):
            with self.subTest(x=x),self.assertRaises(ValueError):samenvatting([x])
    def test_te_korte_test(self):
        with self.assertRaises(ValueError):beoordeel([1]*3,[1]*3,niet_stil=True,model_sha='test')
    def test_ongelijke_meetlengte(self):
        with self.assertRaises(ValueError):beoordeel([1]*32,[1]*31,niet_stil=True,model_sha='test')
    def test_venster_blijft_begrensd(self):
        m=Meetvenster(12)
        for i in range(200):m.voeg_toe(i)
        self.assertEqual(m.status()['blokken'],12);self.assertEqual(m.status()['maximum_ms'],199)
    def test_venster_wissen(self):
        m=Meetvenster();m.voeg_toe(1);m.wis();self.assertEqual(m.status()['blokken'],0)
    def test_profiel_whitelist(self):
        for x in ('extra','../direct',1,None,[]):
            with self.subTest(x=x),self.assertRaises(ValueError):controleer_profiel(x)
    def test_geen_klank_of_totale_latency_claim(self):
        r=beoordeel([1]*32,[1]*32,niet_stil=True,model_sha='test')
        self.assertIsNone(r['totale_audiovertraging_ms']);self.assertFalse(r['geluidskwaliteit_getest'])

class TestBuffer416(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name)
        self.d=NatuurlijkeStemDienst(self.root/'stem2_keuze.json',Mock(),root=self.root/'runtime',autostart=False)
    def tearDown(self):self.d.sluiten();self.tmp.cleanup()
    def actief(self,profiel):
        self.d.bufferprofiel=profiel;self.d.aan=True;self.d._state='gereed'
        self.d._route='live';self.d._last_callback=time.monotonic()
    def test_default_blijft_twee_blokken(self):self.assertEqual(self.d.status()['opstartreserve_ms'],104)
    def test_alle_drie_profielen_werken(self):
        for profiel,info in BUFFERPROFIELEN.items():
            with self.subTest(profiel=profiel):
                self.d.wis_audio();self.actief(profiel);g=self.d._generation
                for _ in range(info['blokken']-1):self.d._outputs.put((g,np.full(FRAMES,.3,np.float32)))
                x=np.full((480,1),.1,np.float32)
                np.testing.assert_array_equal(self.d.verwerk(x,'live'),0)
                self.d._outputs.put((g,np.full(FRAMES,.3,np.float32)))
                np.testing.assert_allclose(self.d.verwerk(x,'live'),.3)
    def test_geen_profielwissel_tijdens_actief(self):
        self.actief('direct')
        with self.assertRaises(ValueError):self.d.stel_bufferprofiel_in('stabiel')
    def test_geen_profielwissel_tijdens_computertest(self):
        self.d._test_only=True
        with self.assertRaises(ValueError):self.d.stel_bufferprofiel_in('direct')
        self.d._test_only=False
    def test_profiel_en_uit_worden_bewaard(self):
        import json
        self.d.stel_bufferprofiel_in('direct');j=json.loads(self.d.instellingpad.read_text())
        self.assertFalse(j['aan']);self.assertEqual(j['bufferprofiel'],'direct')
    def test_herstart_leest_profiel(self):
        self.d.stel_bufferprofiel_in('stabiel')
        other=NatuurlijkeStemDienst(self.d.instellingpad,Mock(),root=self.root/'runtime')
        self.assertEqual(other.bufferprofiel,'stabiel');self.assertFalse(other.aan);other.sluiten()
    def test_oude_keuze_zonder_profiel_blijft_geldig(self):
        self.d.instellingpad.write_text('{"aan":false}')
        other=NatuurlijkeStemDienst(self.d.instellingpad,Mock(),root=self.root/'runtime')
        self.assertEqual(other.bufferprofiel,'gebalanceerd');self.assertFalse(other.aan);other.sluiten()
    def test_schrijffout_herstelt_profiel(self):
        with patch.object(self.d,'_save',side_effect=OSError('test')),self.assertRaises(OSError):self.d.stel_bufferprofiel_in('direct')
        self.assertEqual(self.d.bufferprofiel,'gebalanceerd')
    def test_oude_spraak_wordt_geweigerd(self):
        self.actief('direct');g=self.d._generation
        self.d._outputs.put((g,np.full(FRAMES,.3,np.float32),time.monotonic()-1))
        np.testing.assert_array_equal(self.d.verwerk(np.full((480,1),.1,np.float32),'live'),0)
        self.assertGreater(self.d._generation,g)
    def test_rapport_bevat_geen_paden_audio_of_gebruikersnaam(self):
        import json
        s=json.dumps(self.d.geef_rapport())
        self.assertNotIn(str(self.root),s);self.assertNotIn('samples',s);self.assertIsNone(self.d.geef_rapport()['totale_audiovertraging_ms'])
    def test_start_weigert_dubbele_test(self):
        self.d._test_only=True
        with self.assertRaises(ValueError):self.d.stel_in(True)
        self.d._test_only=False
    def test_test_na_afsluiten_geweigerd(self):
        self.d.sluiten()
        with self.assertRaises(RuntimeError):self.d.test_computer()
    def test_test_tijdens_actieve_proefstem_geweigerd(self):
        self.actief('direct')
        with self.assertRaises(ValueError):self.d.test_computer()
    def test_annuleren_zonder_test_verandert_aan_niet(self):
        self.actief('direct');self.d.annuleer_test();self.assertTrue(self.d.aan)
    def test_eerdere_goedkeuring_wordt_niet_hergebruikt_bij_startfout(self):
        self.d._pc_test={'geslaagd':True}
        self.d.stel_in(True)
        deadline=time.monotonic()+2
        while self.d._state=='laden' and time.monotonic()<deadline:time.sleep(.005)
        self.assertEqual(self.d._state,'fout');self.assertIsNone(self.d.status()['computertest'])
    def test_status_copy_is_geisoleerd(self):
        a=self.d.status();a['bufferprofielen']['direct']['blokken']=99
        self.assertEqual(BUFFERPROFIELEN['direct']['blokken'],1)

if __name__=='__main__':unittest.main()
