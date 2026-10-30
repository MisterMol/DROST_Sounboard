"""CPU-beheer en veilige demping. Geen echt model, Windows-driver of geluidsapparaat."""
from pathlib import Path
import ast
import json
import logging
import tempfile
import threading
import time
import unittest
from unittest.mock import Mock, patch
import numpy as np
from app.audio.natuurlijke_stem.dienst import NatuurlijkeStemDienst, FRAMES, _read_exact, _write_exact
from app.audio.natuurlijke_stem.proces import EigenProcesgroep

ROOT=Path(__file__).resolve().parents[1]

class TestDienst(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.root=Path(self.tmp.name)
        self.d=NatuurlijkeStemDienst(self.root/'keuze.json',Mock(),root=self.root/'runtime',autostart=False)
        self.x=np.full((480,1),.1,np.float32)
    def tearDown(self):
        self.d.sluiten();self.tmp.cleanup()
    def active(self):
        self.d.aan=True;self.d._state='gereed'
        self.d._route='live';self.d._last_callback=time.monotonic()
    def test_default_uit_zonder_worker(self):
        self.assertFalse(self.d.aan);self.assertIsNone(self.d._thread)
    def test_laden_blijft_stil(self):
        self.d.aan=True;self.d._state='laden'
        np.testing.assert_array_equal(self.d.verwerk(self.x,'live'),0)
    def test_fout_blijft_stil(self):
        self.d.aan=True;self.d._fault('fout')
        np.testing.assert_array_equal(self.d.verwerk(self.x,'live'),0)
    def test_callback_verandert_bron_niet(self):
        self.active();before=self.x.copy();self.d.verwerk(self.x,'live')
        np.testing.assert_array_equal(before,self.x)
    def test_callback_roept_geen_procesbeheer_aan(self):
        self.active()
        with patch.object(self.d,'_run',side_effect=AssertionError('geen model in callback')):
            self.d.verwerk(self.x,'live')
    def test_callback_wacht_niet_op_lock(self):
        self.active();self.d._lock.acquire()
        try:
            begin=time.monotonic();y=self.d.verwerk(self.x,'live')
            self.assertLess(time.monotonic()-begin,.1);np.testing.assert_array_equal(y,0)
        finally:self.d._lock.release()
    def test_te_volle_invoer_dempt(self):
        self.active()
        for _ in range(19):self.d.verwerk(self.x,'live')
        self.assertEqual(self.d.status()['toestand'],'fout')
        np.testing.assert_array_equal(self.d.verwerk(self.x,'live'),0)
    def test_dubbele_uitvoerbuffer_kan_afspelen(self):
        self.active();g=self.d._generation
        for _ in range(2):self.d._outputs.put_nowait((g,np.full(FRAMES,.3,np.float32)))
        np.testing.assert_allclose(self.d.verwerk(self.x,'live'),.3)
    def test_verkeerde_generatie_speelt_niet(self):
        self.active()
        for _ in range(2):self.d._outputs.put_nowait((-1,np.full(FRAMES,.3,np.float32)))
        np.testing.assert_array_equal(self.d.verwerk(self.x,'live'),0)
    def test_preview_naar_live_wist_oude_spraak(self):
        self.active();self.d._route='preview'
        for _ in range(2):self.d._outputs.put_nowait((0,np.full(FRAMES,.3,np.float32)))
        np.testing.assert_array_equal(self.d.verwerk(self.x,'live'),0)
        self.assertEqual(self.d._generation,1)
    def test_pauze_wist_oude_spraak(self):
        self.active();self.d._last_callback=0
        for _ in range(2):self.d._outputs.put_nowait((0,np.full(FRAMES,.3,np.float32)))
        np.testing.assert_array_equal(self.d.verwerk(self.x,'live'),0)
    def test_ongeduldige_fout_dempen(self):
        self.active();self.d._fault('te langzaam')
        self.assertTrue(self.d.aan);self.assertTrue(self.d._stop.is_set())
    def test_sluiten_houdt_mute_tot_stream_stopt(self):
        self.active();self.d.sluiten()
        self.assertTrue(self.d.aan);np.testing.assert_array_equal(self.d.verwerk(self.x,'live'),0)
    def test_geen_nieuwe_start_na_sluiten(self):
        self.d.sluiten()
        with self.assertRaises(RuntimeError):self.d.stel_in(True)
    def test_alleen_echte_boolean(self):
        for value in (1,0,'true',None,[]):
            with self.subTest(value=value),self.assertRaises(ValueError):self.d.stel_in(value)
    def test_geen_bestand_bij_constructie(self):
        self.assertFalse(self.d.instellingpad.exists())
    def test_explicit_uit_herstelt_gewone_route(self):
        self.active();self.d.stel_in(False)
        self.assertFalse(self.d.aan);self.assertEqual(json.loads(self.d.instellingpad.read_text())['aan'],False)
    def test_oude_keuze_aan_wordt_autostart(self):
        self.d.instellingpad.write_text('{"aan":true}')
        with patch.object(NatuurlijkeStemDienst,'stel_in') as change:
            other=NatuurlijkeStemDienst(self.d.instellingpad,Mock(),root=self.root)
            change.assert_called_once_with(True,bewaren=False)
            other.sluiten()
    def test_beschadigde_keuze_dempt(self):
        self.d.instellingpad.write_text('kapot')
        other=NatuurlijkeStemDienst(self.d.instellingpad,Mock(),root=self.root)
        self.assertTrue(other.aan);self.assertEqual(other.status()['toestand'],'fout');other.sluiten()
    def test_niet_eindige_invoer_geweigerd(self):
        self.active();self.x[0,0]=np.nan
        np.testing.assert_array_equal(self.d.verwerk(self.x,'live'),0)
        self.assertEqual(self.d.status()['toestand'],'fout')
    def test_grote_invoer_geweigerd(self):
        self.active();self.d.verwerk(np.zeros((5000,1),np.float32),'live')
        self.assertEqual(self.d.status()['toestand'],'fout')
    def test_stereo_wordt_mono_ingevoerd(self):
        self.active();x=np.tile(np.array([[.1,.3]],np.float32),(480,1));self.d.verwerk(x,'live')
        _,mono,_=self.d._inputs.get_nowait();np.testing.assert_allclose(mono,.2)
    def test_lege_output_lekt_geen_dry_audio(self):
        self.active();np.testing.assert_array_equal(self.d.verwerk(self.x,'live'),0)
    def test_reset_is_begrensd(self):
        self.active();self.d.verwerk(self.x,'live');self.d.wis_audio()
        self.assertEqual(self.d._inputs.qsize(),0);self.assertEqual(len(self.d._out),0)
    def test_ontbrekende_runtime_geeft_fout_zonder_crash(self):
        self.d.stel_in(True)
        deadline=time.monotonic()+2
        while self.d._state=='laden' and time.monotonic()<deadline:time.sleep(.01)
        self.assertEqual(self.d._state,'fout');self.assertTrue(self.d.aan)

class TestProtocol(unittest.TestCase):
    def test_korte_leesstukken_worden_samengevoegd(self):
        class Small:
            def __init__(self):self.data=bytearray(b'abcdef')
            def read(self,n):x=self.data[:min(n,2)];del self.data[:len(x)];return bytes(x)
        self.assertEqual(_read_exact(Small(),6),b'abcdef')
    def test_eof_is_fout(self):
        import io
        with self.assertRaises(EOFError):_read_exact(io.BytesIO(b'a'),2)
    def test_korte_writes_worden_afgemaakt(self):
        class Small:
            def __init__(self):self.data=bytearray()
            def write(self,b):self.data.extend(b[:2]);return min(2,len(b))
        s=Small();_write_exact(s,b'abcdef');self.assertEqual(s.data,b'abcdef')
    def test_afgebroken_write(self):
        s=Mock();s.write.return_value=0
        with self.assertRaises(EOFError):_write_exact(s,b'abc')

class TestKoppeling(unittest.TestCase):
    def source(self,p):return (ROOT/p).read_text(encoding='utf-8-sig')
    def test_soundboard_komt_na_neurale_stem(self):
        s=self.source('app/audio/live_audiomixer.py')
        self.assertLess(s.index("dienst.verwerk(inkomende_microfoonframes, 'live')"),s.index('self._verwerk_het_lopende_geluid_in_het_audioblok(uitgaande_audio)'))
    def test_preview_gebruikt_dezelfde_dienst(self):
        self.assertIn("dienst.verwerk(invoer, 'preview')",self.source('app/audio/stemvoorbeeld.py'))
    def test_shutdown_heeft_aparte_stemstap(self):
        self.assertIn("('natuurlijke stemmotor', self._sluit_natuurlijke_stem)",self.source('app/webinterface/bediening_van_de_audiomotor.py'))
    def test_route_is_achter_bestaande_herkomstcontrole(self):
        s=self.source('app/webinterface/lokale_webserver.py').split('    def do_POST(',1)[1]
        self.assertLess(s.index('self._controleer_herkomst(True)'),s.index("pad == '/api/natuurlijke-stem'"))
        self.assertIn("type(gegevens['aan']) is not bool",s)
    def test_soundboardomgeving_importeert_geen_torch(self):
        for f in (ROOT/'app/audio/natuurlijke_stem').glob('*.py'):
            tree=ast.parse(f.read_text());imports=[n for n in ast.walk(tree) if isinstance(n,(ast.Import,ast.ImportFrom))]
            for n in imports:self.assertNotIn('torch',ast.unparse(n))
    def test_builder_neemt_worker_mee(self):
        s=self.source('Bouw_Windows_Release.ps1');self.assertIn("'stem-runtime:stem-runtime'",s)
        self.assertIn('-m unittest discover -s tests -q',s);self.assertIn('stemstatus.passed',s)

if __name__=='__main__':unittest.main()
