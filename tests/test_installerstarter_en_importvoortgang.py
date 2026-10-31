"""Contracttests voor de Windows-starter en voortgang van grote audiopacks."""
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]


class TestInstallerStarterEnImportVoortgang(unittest.TestCase):
    def test_installer_toont_downloadlocatie_en_toegankelijke_knoppen(self):
        bron = (ROOT / "hulpmiddelen/installerstarter/DrostInstallerStarter.cs").read_text(encoding="utf-8")
        self.assertIn('ForeColor = Color.FromArgb(241, 248, 249)', bron)
        self.assertIn('Soundpack opgeslagen in Downloads:', bron)
        self.assertIn('map.Enabled = true;', bron)
        self.assertIn('SHA256.Create()', bron)

    def test_een_exe_kan_soundpack_automatisch_toevoegen(self):
        starter = (ROOT / "hulpmiddelen/installerstarter/DrostInstallerStarter.cs").read_text(encoding="utf-8")
        helper = (ROOT / "hulpmiddelen/installerstarter/StartersoundpackAutomatisch.cs").read_text(encoding="utf-8")
        build = (ROOT / "Bouw_Installerstarter.ps1").read_text(encoding="utf-8")
        self.assertIn("pack.Checked = false;", starter)
        self.assertIn("StartersoundpackAutomatisch.VoegToe(", starter)
        self.assertIn("X-Drost-Token", helper)
        self.assertIn("127.0.0.1:", helper)
        self.assertIn("/api/versie", helper)
        self.assertIn("/api/bibliotheek/importeer?dubbelen=overslaan", helper)
        self.assertIn("IProgress<int>", helper)
        self.assertIn("TryComputeLength(out long length)", helper)
        self.assertIn("StartersoundpackAutomatisch.cs", build)
        self.assertIn("GebundeldeSetup.cs", build)
        self.assertIn("ingesloten.PakUit(", starter)
        self.assertIn("Stap 2 van 3: DrostSoundboard installeren", starter)
        self.assertIn("Geluidsarchief tonen", starter)
        self.assertIn("DrostSoundboard openen", starter)
        self.assertIn("Bibliotheek", starter)
        self.assertIn("GeinstalleerdeApp()", starter)

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
