"""Contracttests voor de Windows-starter en voortgang van grote audiopacks."""
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]


class TestInstallerStarterEnImportVoortgang(unittest.TestCase):
    def test_installer_toont_downloadlocatie_en_toegankelijke_knoppen(self):
        bron = (ROOT / "hulpmiddelen/installerstarter/DrostInstallerStarter.cs").read_text(encoding="utf-8")
        self.assertIn('ForeColor=Color.FromArgb(241,248,249)', bron)
        self.assertIn('hint.Text="Soundpack opgeslagen in Downloads:', bron)
        self.assertIn('map.Enabled=true;', bron)
        self.assertIn('SHA256.Create()', bron)

    def test_bibliotheek_import_heeft_blijvende_visuele_voortgang(self):
        html = (ROOT / "app/webinterface/statisch/dashboard.html").read_text(encoding="utf-8")
        js = (ROOT / "app/webinterface/statisch/dashboard.js").read_text(encoding="utf-8")
        css = (ROOT / "app/webinterface/statisch/stijl.css").read_text(encoding="utf-8")
        for id_ in ("audiopack-voortgang", "audiopack-fase", "audiopack-balk"):
            self.assertIn('id="' + id_ + '"', html)
        self.assertIn("zetAudiopackVoortgangAan('Geluiden importeren')", js)
        self.assertIn("verzoek.upload.onprogress", js)
        self.assertIn("verzoek.upload.onload", js)
        self.assertIn("element('audiopack-balk').removeAttribute('value')", js)
        self.assertIn(".audiopack-voortgang[hidden]", css)
        self.assertIn("@media (prefers-reduced-motion:reduce)", css)


if __name__ == "__main__":
    unittest.main()
