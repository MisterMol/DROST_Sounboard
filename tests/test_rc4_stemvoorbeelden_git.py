"""RC4: ingebouwde korte stemsamples altijd beschikbaar in Git én Setup."""
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
from hulpmiddelen.controleer_git_publicatie import (
    beoordeel_pad, is_stemvoorbeeld, controleer_project, VEREISTE_STEMVOORBEELDEN,
)

ROOT = Path(__file__).resolve().parents[1]


class TestStemvoorbeeldenGit(unittest.TestCase):
    def test_gitignore_laat_stemvoorbeelden_expliciet_toe(self):
        regels = (ROOT / '.gitignore').read_text(encoding='utf-8').splitlines()
        self.assertIn('*.mp3', regels)
        self.assertIn('!app/audio/stemvoorbeelden/*.mp3', regels)

    def test_git_checker_laat_alleen_stemvoorbeeld_mp3_toe(self):
        for pad in VEREISTE_STEMVOORBEELDEN:
            self.assertTrue(is_stemvoorbeeld(pad))
            self.assertIsNone(beoordeel_pad(pad))
        for pad in ('mijn_geluiden/voice.mp3', 'app/audio/voice.mp3',
                    'app/audio/stemvoorbeelden/extra.wav',
                    'app/audio/stemvoorbeelden/submap/prive.mp3',
                    'app/audio/stemvoorbeelden/../../prive.mp3',
                    'app/audio/stemvoorbeelden/model.onnx'):
            with self.subTest(pad=pad):
                self.assertIsNotNone(beoordeel_pad(pad))

    def test_releasebundel_bevat_stemvoorbeelden(self):
        ps1 = (ROOT / 'Bouw_Windows_Release.ps1').read_text(encoding='utf-8-sig')
        self.assertIn("--add-data 'app/audio/stemvoorbeelden:app/audio/stemvoorbeelden'", ps1)
        smoke = (ROOT / 'app/desktop/release_zelftest.py').read_text(encoding='utf-8')
        self.assertIn("'stemvoorbeelden'", smoke)

    @unittest.skipUnless(shutil.which('git'), 'Git niet beschikbaar voor de integratietest')
    def test_git_index_verplicht_bob_en_elise(self):
        with tempfile.TemporaryDirectory() as tijdelijk:
            root = Path(tijdelijk)
            (root / '.gitignore').write_bytes((ROOT / '.gitignore').read_bytes())
            (root / 'README.md').write_text('Git-integratietest\n', encoding='utf-8')
            stemdir = root / 'app/audio/stemvoorbeelden'
            stemdir.mkdir(parents=True)
            for pad in VEREISTE_STEMVOORBEELDEN:
                (root / pad).write_bytes(b'ID3\x03\x00\x00')  # Dummy bytes, geen audio
            (root / 'privemuziek.mp3').write_bytes(b'ID3')
            def git(*args):
                return subprocess.run(['git', '-c', 'core.excludesfile=', *args],
                                      cwd=root, capture_output=True, text=True)
            self.assertEqual(git('init', '-q').returncode, 0)
            self.assertEqual(git('add', '.gitignore', 'README.md').returncode, 0)
            _, fouten = controleer_project(root)
            self.assertEqual(sum('ontbreekt in Git' in fout for fout in fouten), 2)
            self.assertEqual(git('add', *VEREISTE_STEMVOORBEELDEN).returncode, 0)
            opgenomen = git('ls-files', '--', 'app/audio/stemvoorbeelden/')
            for pad in VEREISTE_STEMVOORBEELDEN:
                self.assertIn(pad, opgenomen.stdout)
            self.assertNotIn('privemuziek.mp3', git('ls-files').stdout)
            _, fouten = controleer_project(root)
            self.assertFalse(fouten, fouten)


if __name__ == '__main__':
    unittest.main()
