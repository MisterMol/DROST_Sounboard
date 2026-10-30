"""RC4: documentatie en onboarding, zonder audiomotor of netwerk."""
from pathlib import Path
import unittest
from hulpmiddelen.controleer_git_publicatie import beoordeel_pad
from app.diagnostiek.logboek import VERSIE_VAN_DE_APP

ROOT = Path(__file__).resolve().parents[1]


class TestRC4GitHubEnVB(unittest.TestCase):
    def test_unieke_nieuwe_releaseversie(self):
        self.assertEqual(VERSIE_VAN_DE_APP, '6.1.0-rc.4')

    def test_vb_warning_geeft_handmatige_stappen(self):
        html = (ROOT / 'app/webinterface/statisch/dashboard.html').read_text(encoding='utf-8')
        js = (ROOT / 'app/webinterface/statisch/dashboard.js').read_text(encoding='utf-8')
        css = (ROOT / 'app/webinterface/statisch/stijl.css').read_text(encoding='utf-8')
        self.assertIn('id="vb-cable-stappen"', html)
        self.assertIn('VBCABLE_Setup_x64.exe', html)
        self.assertIn('https://vb-audio.com/Cable/', html)
        self.assertIn("['ontbreekt', 'onvolledig']", js)
        self.assertIn('.vb-cable-stappen[hidden]', css)

    def test_documentatie_informeert_eerlijk_over_release(self):
        readme = (ROOT/'README.md').read_text(encoding='utf-8')
        handleiding = (ROOT/'INSTALLEREN.md').read_text(encoding='utf-8')
        self.assertIn('6.1.0 RC4', readme)
        self.assertIn('6.1.0 RC4', handleiding)
        self.assertIn('github.com/MisterMol/DROST_Sounboard', readme)
        self.assertIn('Setup.exe', readme)
        self.assertIn('git clone', readme)
        self.assertIn('geen volledige stemruntime', handleiding)

    def test_binaries_en_data_mogen_niet_mee_naar_git(self):
        for naam in ('stem-runtime/Worker.exe', 'app/audio/native/win-x64/drost_stem.dll',
                     'mijn_data/bibliotheek.db', 'release-velopack/Setup.exe',
                     'model/G_500000.pth', 'Downloads/pakket.zip', '.env.local'):
            with self.subTest(naam=naam):
                self.assertIsNotNone(beoordeel_pad(naam))
        for naam in ('README.md', 'app/webinterface/statisch/dashboard.js',
                     'tests/test_vb_cable_vereisten.py',
                     'app/audio/stemvoorbeelden/hello_my_name_is_bob.mp3',
                     'app/audio/stemvoorbeelden/hello_my_name_is_elise.mp3'):
            self.assertIsNone(beoordeel_pad(naam))

    def test_installer_branding_is_meegeleverd(self):
        script = (ROOT/'Bouw_Windows_Release.ps1').read_text(encoding='utf-8-sig')
        self.assertIn('--splashImage', script)
        self.assertIn('--icon', script)
        self.assertTrue((ROOT/'assets/release/DrostSoundboard.ico').is_file())
        self.assertTrue((ROOT/'assets/release/DrostSoundboard_Installatie.png').is_file())

    def test_release_documentatie_verwijst_naar_vb_audio(self):
        txt = (ROOT/'app/desktop/deelpakket.py').read_text(encoding='utf-8')
        self.assertIn('https://vb-audio.com/Cable/', txt)
        self.assertIn('VBCABLE_Setup_x64.exe', txt)


if __name__ == '__main__':
    unittest.main()
