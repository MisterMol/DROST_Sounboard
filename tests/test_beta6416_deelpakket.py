"""Bestandstests met een expliciet nep-EXE-bestand. Geen echte installerbouw."""
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from app.desktop.deelpakket import maak_deelmap, bestandsha
from app.audio.natuurlijke_stem import runtimecontrole as rt

class TestDeelpakket416(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name)
        self.exe=self.root/'Drost-beta-Setup.exe';self.exe.write_bytes(b'MZTESTGEENINSTALLER')
        self.e=self.root/'exe.json';self.e.write_text('{"geslaagd":true,"versie":"6.1.0-beta.4.16","persoonlijk_pad":"GEHEIM"}')
        self.m=self.root/'model.json';self.m.write_text(json.dumps(dict(passed=True,finite=True,reset_ok=True,model_sha256=rt.MODEL_SHA)))
    def tearDown(self):self.tmp.cleanup()
    def maak(self):return maak_deelmap(self.exe,self.root/'release','6.1.0-beta.4.16',self.e,self.m)
    def test_volledige_map(self):
        folder=self.maak();self.assertEqual(len(list(folder.iterdir())),4)
        self.assertEqual((folder/self.exe.name).read_bytes(),self.exe.read_bytes())
    def test_geen_privacygevoelig_bouwlog(self):
        folder=self.maak();s=(folder/'BOUWCONTROLE.json').read_text();self.assertNotIn('GEHEIM',s)
    def test_geen_praktijkgoedkeuring(self):
        j=json.loads((self.maak()/'BOUWCONTROLE.json').read_text());self.assertFalse(j['echte_audio_getest']);self.assertFalse(j['schone_windowsinstallatie_getest'])
    def test_hash_verifieerbaar(self):
        folder=self.maak()
        for line in (folder/'SHA256SUMS.txt').read_text().splitlines():
            h,n=line.split('  ',1);self.assertEqual(bestandsha(folder/n),h)
    def test_tweede_build_overschrijft_niet(self):self.assertNotEqual(self.maak(),self.maak())
    def test_foute_exetest_weigert(self):
        self.e.write_text('{"geslaagd":false}')
        with self.assertRaises(ValueError):self.maak()
        self.assertFalse((self.root/'release').exists())
    def test_oude_exeversie_weigert(self):
        self.e.write_text('{"geslaagd":true,"versie":"6.1.0-beta.4.15"}')
        with self.assertRaises(ValueError):self.maak()
    def test_foute_modeltest_weigert(self):
        self.m.write_text('{"passed":false}')
        with self.assertRaises(ValueError):self.maak()
    def test_geen_windowsbestand_weigert(self):
        self.exe.write_bytes(b'gewoon tekst')
        with self.assertRaises(ValueError):self.maak()
    def test_schrijffout_geen_half_deelpakket(self):
        with patch('app.desktop.deelpakket.shutil.copy2',side_effect=OSError('test')),self.assertRaises(OSError):self.maak()
        self.assertEqual(list((self.root/'release').iterdir()),[])

class TestRuntime416(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name)
        (self.root/'DrostStemWorker.exe').write_bytes(b'NEPWORKER');(self.root/'G_500000.pth').write_bytes(b'NEPMODEL')
        self.sha=rt.file_sha(self.root/'G_500000.pth')
        self.patch=patch.object(rt,'MODEL_SHA',self.sha);self.patch.start()
        self.files={p.name:rt.file_sha(p) for p in self.root.iterdir()}
        self.save()
    def tearDown(self):self.patch.stop();self.tmp.cleanup()
    def save(self):
        (self.root/'runtime.json').write_text(json.dumps(dict(schema=1,model_sha256=self.sha,files=self.files)))
    def test_goede_hashes(self):self.assertEqual(rt.valideer_runtime(self.root)['files'],self.files)
    def test_veranderd_model(self):
        (self.root/'G_500000.pth').write_bytes(b'ANDERS')
        with self.assertRaises(ValueError):rt.valideer_runtime(self.root)
    def test_extra_bestand(self):
        (self.root/'losse.dll').write_bytes(b'test')
        with self.assertRaises(ValueError):rt.valideer_runtime(self.root)
    def test_pad_buiten_map(self):
        self.files['../escape']=self.sha;self.save()
        with self.assertRaises(ValueError):rt.valideer_runtime(self.root)
    def test_absolute_windowsnaam(self):
        self.files['C:/escape']=self.sha;self.save()
        with self.assertRaises(ValueError):rt.valideer_runtime(self.root)
    def test_dubbele_hoofdletter(self):
        self.files['g_500000.pth']=self.sha;self.save()
        with self.assertRaises((ValueError,FileNotFoundError)):rt.valideer_runtime(self.root)
    def test_verkeerde_hashvorm(self):
        self.files['DrostStemWorker.exe']='x';self.save()
        with self.assertRaises(ValueError):rt.valideer_runtime(self.root)
    def test_dubbele_jsonsleutel(self):
        (self.root/'runtime.json').write_text('{"schema":1,"schema":1}')
        with self.assertRaises(ValueError):rt.valideer_runtime(self.root)
    def test_link_weigeren(self):
        file=self.root/'DrostStemWorker.exe';file.unlink()
        try:file.symlink_to('G_500000.pth')
        except OSError:self.skipTest('Symlink maken op dit systeem niet toegestaan.')
        with self.assertRaises(ValueError):rt.valideer_runtime(self.root)

if __name__=='__main__':unittest.main()
