"""Regressietests voor de echte ingebouwde DLL op Windows. Geen microfoon nodig."""
from pathlib import Path
import importlib.util
import sys
import unittest
import numpy as np
from app.audio import signalsmith_motor
from app.audio.stemvervorming import Stemvervormer, profiel_catalogus_voor_api
from app.audio.stemparameters import standaard_parameters

class TestStemcatalogus414(unittest.TestCase):
    def test_nieuwe_profielen_zijn_beschikbaar(self):
        ids={x['id'] for x in profiel_catalogus_voor_api()}
        self.assertTrue({'monsterkoor','ruimtepak','spook','retrocomputer'} <= ids)
    def test_twee_regelaars_per_nieuw_profiel(self):
        d=standaard_parameters()
        for profiel in ('monsterkoor','ruimtepak','spook','retrocomputer'):
            with self.subTest(profiel=profiel):self.assertEqual(len(d[profiel]),2)
    def test_normaal_is_ongewijzigd(self):
        x=np.full((480,1),.1,np.float32)
        self.assertIs(Stemvervormer('normaal').verwerk(x),x)

@unittest.skipUnless(sys.platform=='win32','De meegebouwde native bibliotheek is uitsluitend Windows x64.')
class TestWerkelijkeNativeMotor414(unittest.TestCase):
    def test_native_acceptatie_zonder_audiodevice(self):
        path=Path(__file__).parent/'hulpmiddelen/stem_native_probe.py'
        spec=importlib.util.spec_from_file_location('drost414_probe',path)
        module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
        result=module.controleer(signalsmith_motor,signalsmith_motor.laad_library())
        self.assertTrue(result['geslaagd'])

if __name__=='__main__':unittest.main()
