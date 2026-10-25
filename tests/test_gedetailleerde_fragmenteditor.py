"""Fase 5.4: editorprecisie, lokaal luisteren en veilige golfvormresolutie.

We gebruiken synthetische WAV-bestanden. Geen echte microfoon, headset,
VB-CABLE of geluidsopname wordt geopend door deze tests.
"""
from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
import wave

import numpy as np

from app.audio.bronduur_en_golfvorm import (
    BronbestandNietLeesbaar,
    maak_gedetailleerde_golfvorm_voor_tijdsvenster,
    maak_golfvorm_voor_tijdsvenster,
)


class TestGedetailleerdeGolfvorm(unittest.TestCase):
    def setUp(self) -> None:
        self.tijdelijke_map = TemporaryDirectory()
        self.bestand = Path(self.tijdelijke_map.name) / 'spraakachtig.wav'
        frequentie = 8000
        posities = np.arange(4 * frequentie) / frequentie
        # Een korte piek, een zachter gedeelte en stilte moeten zichtbaar zijn.
        amplitude = np.where(posities < 1, .8,
                     np.where(posities < 2.5, .12, 0))
        samples = (np.sin(posities * 2 * np.pi * 330) * amplitude * 32767).astype('<i2')
        with wave.open(str(self.bestand), 'wb') as bestand:
            bestand.setnchannels(1)
            bestand.setsampwidth(2)
            bestand.setframerate(frequentie)
            bestand.writeframes(samples.tobytes())

    def tearDown(self) -> None:
        self.tijdelijke_map.cleanup()

    def test_beide_golfvormreeksen_zijn_640_echte_tijdkolommen(self) -> None:
        resultaat = maak_gedetailleerde_golfvorm_voor_tijdsvenster(self.bestand, 0, 4, 640)
        self.assertEqual(len(resultaat['pieken']), 640)
        self.assertEqual(len(resultaat['rms']), 640)
        self.assertAlmostEqual(max(resultaat['pieken']), 1.0, places=3)
        self.assertTrue(all(0 <= gemiddelde <= piek + .00015
                            for gemiddelde, piek in zip(resultaat['rms'], resultaat['pieken'])))
        self.assertGreater(max(resultaat['pieken'][:160]), 0.9)
        self.assertLess(max(resultaat['pieken'][480:]), 0.002)

    def test_hoge_resolutie_blijft_begrensd_op_1200(self) -> None:
        self.assertEqual(len(maak_gedetailleerde_golfvorm_voor_tijdsvenster(
            self.bestand, 0, 1, 1200)['pieken']), 1200)
        for resolutie in (0, 1201, True, '720', -40):
            with self.subTest(resolutie=resolutie), self.assertRaisesRegex(BronbestandNietLeesbaar, 'GOLF-001'):
                maak_gedetailleerde_golfvorm_voor_tijdsvenster(self.bestand, 0, 1, resolutie)

    def test_oude_golfvormfunctie_blijft_werken(self) -> None:
        pieken = maak_golfvorm_voor_tijdsvenster(self.bestand, 0, 2)
        self.assertEqual(len(pieken), 160)
        self.assertTrue(all(isinstance(waarde, float) for waarde in pieken))

    def test_gedetailleerde_metingen_bewaren_geen_monsters_in_de_database(self) -> None:
        resultaat = maak_gedetailleerde_golfvorm_voor_tijdsvenster(self.bestand, 0, 1, 300)
        self.assertEqual(set(resultaat), {'pieken', 'rms'})
        self.assertEqual(len(resultaat['pieken']), 300)


class TestWebeditorHeeftEigenAfspeelkop(unittest.TestCase):
    def setUp(self) -> None:
        map_ = Path(__file__).resolve().parents[1] / 'app' / 'webinterface' / 'statisch'
        self.html = (map_ / 'dashboard.html').read_text(encoding='utf-8')
        self.javascript = (map_ / 'dashboard.js').read_text(encoding='utf-8')
        self.css = (map_ / 'stijl.css').read_text(encoding='utf-8')

    def test_cursor_heeft_focus_en_toegankelijke_tijdpositie(self) -> None:
        self.assertIn('id="editor-afspeelvlak"', self.html)
        self.assertIn('role="slider" tabindex="0"', self.html)
        self.assertIn('aria-valuetext', self.javascript)
        self.assertIn('pointermove', self.javascript)
        self.assertIn('setPointerCapture', self.javascript)

    def test_eigen_editorpreview_kan_pauzeren_en_op_dezelfde_plek_verder(self) -> None:
        self.assertIn('pauzeerEditorPreview', self.javascript)
        self.assertIn('netteTijdMetTienden', self.javascript)
        self.assertIn('gebeurtenis.code !== "Space"', self.javascript)
        self.assertIn('voorbeeld.speler.currentTime = plek', self.javascript)
        self.assertIn('id="editor-voortgang-vulling"', self.html)
        self.assertIn('id="knop-editor-stop"', self.html)

    def test_preview_blijft_lokaal_en_is_niet_de_verzendknop(self) -> None:
        preview = self.javascript.split('async function speelEditorSelectieLokaal()', 1)[1].split('function verplaatsEditorCursorMetAanwijzer', 1)[0]
        self.assertIn('registreerPreviewBijPython', preview)
        self.assertNotIn('/api/geluiden/', preview)
        self.assertNotIn('/api/verbinden', preview)

    def test_piekwordt_alleen_in_de_weergave_vastgehouden(self) -> None:
        self.assertIn('PIEK_VASTHOUDEN_MILLISECONDEN = 1200', self.javascript)
        self.assertIn('toonVastgehoudenPiek', self.javascript)
        self.assertIn('function tekenEenAudiometer', self.javascript)
        self.assertIn('.editor-afspeelkop', self.css)


if __name__ == '__main__':
    unittest.main()
