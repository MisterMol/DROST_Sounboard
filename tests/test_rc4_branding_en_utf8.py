"""Hetzelfde logo in browser, Windows, installer en systeemvak."""
from __future__ import annotations

from pathlib import Path
from xml.etree import ElementTree
from unittest import TestCase
from PIL import Image, ImageChops

ROOT = Path(__file__).resolve().parents[1]
WEB = ROOT / 'app/webinterface/statisch'


class TestEenduidigeBranding(TestCase):
    def test_logo_is_een_vectorbron_met_vijf_balken(self):
        hoofd = (ROOT/'assets/branding/DrostSoundboard.svg').read_bytes()
        self.assertEqual((WEB/'drost-logo.svg').read_bytes(), hoofd)
        vector = ElementTree.fromstring(hoofd)
        vormen = list(vector.iter('{http://www.w3.org/2000/svg}rect'))
        self.assertEqual(len(vormen), 6)
        self.assertEqual([int(float(v.attrib['height'])) for v in vormen[1:]], [12, 24, 38, 24, 12])

    def test_favicon_en_exeicoon_zijn_exact_gelijk(self):
        exe = (ROOT/'assets/release/DrostSoundboard.ico').read_bytes()
        self.assertEqual((WEB/'favicon.ico').read_bytes(), exe)
        with Image.open(ROOT/'assets/release/DrostSoundboard.ico') as ico:
            self.assertTrue({(16,16), (32,32), (48,48), (64,64), (256,256)} <= ico.info['sizes'])

    def test_tray_gebruikt_web_logo_png(self):
        from app.desktop.systeemvak import maak_eenvoudig_soundboard_pictogram
        with Image.open(WEB/'drost-logo.png') as logo:
            verwacht = logo.convert('RGBA').resize((64,64),Image.Resampling.LANCZOS)
        voor = maak_eenvoudig_soundboard_pictogram(False)
        na = maak_eenvoudig_soundboard_pictogram(True)
        self.assertEqual(voor.size, (64,64))
        self.assertIsNone(ImageChops.difference(voor, verwacht).getbbox())
        self.assertIsNone(ImageChops.difference(voor, na).getbbox())

    def test_navbar_opstartscherm_en_favicon_hebben_dezelfde_bron(self):
        html = (WEB/'dashboard.html').read_text(encoding='utf-8')
        self.assertEqual(html.count('src="/drost-logo.svg"'),2)
        self.assertIn('href="/favicon.ico"',html)
        self.assertIn('href="/drost-logo.svg"',html)
        self.assertNotIn('class="merk-balken"',html)
        self.assertEqual(html.count('id="knop-app-afsluiten"'),1)

    def test_server_biedt_vaste_logo_urls_aan(self):
        server = (ROOT/'app/webinterface/lokale_webserver.py').read_text(encoding='utf-8')
        self.assertIn("elif pad in ('/drost-logo.svg', '/drost-logo.png', '/favicon.ico')",server)
        for type_ in ('image/svg+xml','image/png','image/x-icon'):
            self.assertIn(type_,server)
        self.assertIn("(STATISCHE_MAP / pad.lstrip('/')).read_bytes()",server)

    def test_windows_exe_setup_en_zelftest(self):
        bouw = (ROOT/'Bouw_Windows_Release.ps1').read_text(encoding='utf-8')
        self.assertGreaterEqual(bouw.count("--icon (Join-Path $project 'assets\\release\\DrostSoundboard.ico')"),2)
        self.assertIn('--splashImage',bouw)
        test = (ROOT/'app/desktop/release_zelftest.py').read_text(encoding='utf-8')
        self.assertIn("'drost-logo.svg', 'drost-logo.png', 'favicon.ico'",test)

    def test_utf8_lezen_staat_explicit_in_oude_tests(self):
        for naam in ('test_rc1_releasevoorbereiding.py','test_beta6410_bediening.py','test_beta6419_stemnamen.py'):
            content = (ROOT/'tests'/naam).read_text(encoding='utf-8')
            for line in content.splitlines():
                if "statisch/dashboard.html').read_text(" in line:
                    self.assertIn("encoding='utf-8'",line,naam)

    def test_logo_generatie_reproduceert_de_ico_bron(self):
        from hulpmiddelen.maak_logo_bestanden import teken_logo
        gemaakte = teken_logo(256)
        with Image.open(WEB/'drost-logo.png') as op_schijf:
            self.assertIsNone(ImageChops.difference(gemaakte,op_schijf.convert('RGBA')).getbbox())


if __name__ == '__main__':
    import unittest
    unittest.main()
