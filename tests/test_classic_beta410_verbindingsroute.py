"""Classic: bewaar exact de oude Beta 4.10 WASAPI-microfoonstart.

De SHA256 is rechtstreeks uit de door de gebruiker verstrekte
DrostSoundboard_Beta4_10_Functieherstel(1).zip bepaald,
payload/app/audio/live_audiomixer.py. Dit is GEEN nieuwe audioimplementatie.
"""
import ast
import hashlib
from pathlib import Path
import unittest

PROJECT = Path(__file__).resolve().parents[1]
GEVERIFIEERD_OUD_PREFIX_SHA256 = (
    "2bd5f0db166ff9fa78744e7042dfcc8cf0f1c0254146cebcded7ca14d6b585c7"
)


class TestHersteldeBeta410Verbinding(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.bron = (PROJECT / "app/audio/live_audiomixer.py").read_text(encoding="utf-8")
        cls.regels = cls.bron.splitlines(keepends=True)

    def test_prefix_van_audiowerkdraad_is_bytegelijk_aan_beta410(self):
        boom = ast.parse(self.bron)
        mixer = next(n for n in boom.body
                     if isinstance(n, ast.ClassDef) and n.name == "LiveAudiomixer")
        functie = next(n for n in mixer.body if isinstance(n, ast.FunctionDef)
                       and n.name == "_voer_live_verbinding_met_gereed_com_uit")
        begin = functie.lineno - 1
        grens = next(i for i in range(begin, functie.end_lineno)
                     if "if audiostroom is None:" in self.regels[i])
        prefix = "".join(self.regels[begin:grens])
        self.assertEqual(
            hashlib.sha256(prefix.encode("utf-8")).hexdigest(),
            GEVERIFIEERD_OUD_PREFIX_SHA256,
            "De oude, werkende verbindingsstart mag niet ongemerkt veranderen.",
        )

    def test_geen_wasapi_directsound_fallback_na_geweigerde_duplex(self):
        blok = self.bron.split("    def _voer_live_verbinding_met_gereed_com_uit(")[1]
        blok = blok.split("    def ", 1)[0]
        self.assertIn("audiobibliotheek=self.audiobibliotheek,", blok)
        self.assertNotIn("maak_streamadapter(", blok)
        self.assertNotIn("Windows DirectSound", blok)
        self.assertNotIn("gescheiden_formaat =", blok)


if __name__ == "__main__":
    unittest.main()
