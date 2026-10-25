"""Bescherm de juiste interpretatie van de twee live geluidsmeters.

De audiomotor draait hier niet. We testen de rekenkundige betekenis van
RMS, de afzonderlijke piekwaarde en de CSS-schaal van het dashboard.
"""
from pathlib import Path
import subprocess
import unittest

WEBMAP = Path(__file__).resolve().parents[1] / "app" / "webinterface" / "statisch"


class TestJuisteDecibelSchaal(unittest.TestCase):
    def test_labels_staan_op_de_rekenkundig_juiste_plaats(self):
        css = (WEBMAP / "stijl.css").read_text(encoding="utf-8")
        self.assertIn("span:nth-child(2) { left: 50%; }", css)
        self.assertIn("span:nth-child(3) { left: 80%; }", css)

    def test_witte_markering_volgt_rms_en_herstart_geen_tweede_piek_timer(self):
        js = (WEBMAP / "dashboard.js").read_text(encoding="utf-8")
        self.assertIn("markering.style.left = `${percentage}%`", js)
        self.assertNotIn("piekVasthoudenTot", js)
        self.assertNotIn("Math.max(meter.rmsSchaal, meter.piekSchaal)", js)
        self.assertIn("DECIBEL_WAARBIJ_METER_AANGAAT", js)
        self.assertIn("DECIBEL_WAARBIJ_METER_UITGAAT", js)

    def test_gradient_is_geknipt_en_niet_naar_voren_samengedrukt(self):
        css = (WEBMAP / "stijl.css").read_text(encoding="utf-8")
        js = (WEBMAP / "dashboard.js").read_text(encoding="utf-8")
        self.assertIn("clip-path: inset(0 100% 0 0)", css)
        self.assertIn("style.clipPath = `inset(0 ${100 - percentage}% 0 0)`", js)
        self.assertNotIn("style.transform = `scaleX(", js)

    def test_piek_staat_als_eigen_waarde_zichtbaar_bij_iedere_meter(self):
        html = (WEBMAP / "dashboard.html").read_text(encoding="utf-8")
        for naam in ("microfoon", "uitvoer"):
            self.assertIn(f'id="tekst-{naam}-piek"', html)
        self.assertIn("Piek: —", html)

    def test_javascript_schaal_met_echte_waarden(self):
        js = (WEBMAP / "dashboard.js").read_text(encoding="utf-8")
        snippet = js[js.index("function geefDecibelVanGemetenNiveau"):
                     js.index("function toonRms(rms, gemeten)")]
        for inhoud, verwacht in (("Math.pow(10, -60 / 20)", 0),
                                ("Math.pow(10, -30 / 20)", 50),
                                ("Math.pow(10, -12 / 20)", 80),
                                ("1", 100)):
            code = (f"const DECIBEL_ONDERKANT_VAN_METER=-60;"
                    f"const DECIBEL_BOVENKANT_VAN_METER=0;"
                    f"{snippet}; console.log(meterPercentage({inhoud}))")
            try:
                process = subprocess.run(["node", "-e", code], check=True,
                    capture_output=True, text=True)
            except FileNotFoundError:
                self.skipTest("Node niet geinstalleerd: alle andere metertests werken zonder Node")
            self.assertAlmostEqual(float(process.stdout.strip()), verwacht, places=4)


if __name__ == "__main__":
    unittest.main()
