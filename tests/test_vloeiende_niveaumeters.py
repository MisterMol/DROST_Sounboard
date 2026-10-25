"""Controleer of het dashboard alleen werkelijke RMS en samplepieken toont.

Deze tests openen geen microfoon en sturen geen geluid naar VB-CABLE.
"""

import logging
import math
import unittest
from unittest.mock import MagicMock

import numpy as np

from app.audio.geschiedenis_van_audioniveaus import (
    GeschiedenisVanAudioniveaus,
    MAXIMALE_AANTAL_RECENTE_METINGEN,
)
from app.audio.live_audiomixer import LiveAudiomixer
from pathlib import Path


class TestNiveaumetingMetEchteAudioWaardes(unittest.TestCase):
    def test_rms_weegt_aantal_frames_correct(self):
        metingen = GeschiedenisVanAudioniveaus()
        metingen.onthoud_gemeten_audioblok(0.1, 0.2, 100, tijdstip=10.0)
        metingen.onthoud_gemeten_audioblok(0.4, 0.5, 300, tijdstip=10.04)
        # Tijdens het venster van 50 ms tellen beide blokken nog mee.
        rms, piek = metingen.geef_recente_rms_en_piek(tijdstip=10.045)
        self.assertAlmostEqual(rms, math.sqrt((0.1**2 * 100 + 0.4**2 * 300) / 400))
        self.assertAlmostEqual(piek, 0.5)
        # 80 ms later wordt het oudere blok terecht niet meer meegerekend.
        rms, piek = metingen.geef_recente_rms_en_piek(tijdstip=10.08)
        self.assertAlmostEqual(rms, 0.4)
        self.assertEqual(piek, 0.5)

    def test_korte_piek_blijft_zichtbaar_ook_na_zachter_audioblok(self):
        metingen = GeschiedenisVanAudioniveaus()
        metingen.onthoud_gemeten_audioblok(0.3, 0.95, 480, tijdstip=10.0)
        metingen.onthoud_gemeten_audioblok(0.03, 0.06, 480, tijdstip=10.1)
        rms, piek = metingen.geef_recente_rms_en_piek(tijdstip=10.12)
        self.assertAlmostEqual(rms, 0.03)
        self.assertEqual(piek, 0.95)

    def test_rms_kan_al_stil_zijn_terwijl_korte_piek_nog_wordt_getoond(self):
        metingen = GeschiedenisVanAudioniveaus()
        metingen.onthoud_gemeten_audioblok(0.3, 0.95, 480, tijdstip=10.0)
        rms, piek = metingen.geef_recente_rms_en_piek(tijdstip=10.10)
        self.assertEqual(rms, 0.0)
        self.assertEqual(piek, 0.95)
        self.assertEqual(metingen.geef_recente_rms_en_piek(tijdstip=10.2), (0.0, 0.0))

    def test_ongeldige_getallen_en_frames_worden_afgewezen(self):
        metingen = GeschiedenisVanAudioniveaus()
        for rms, piek, frames in ((float('nan'), 0.4, 480), (0.4, float('inf'), 480),
                                  (-0.2, 0.4, 480), (0.2, -1, 480), (0.2, 0.4, 0)):
            with self.subTest(rms=rms, piek=piek, frames=frames):
                with self.assertRaisesRegex(ValueError, 'NIVEAU-001'):
                    metingen.onthoud_gemeten_audioblok(rms, piek, frames)

    def test_er_worden_geen_samples_of_oneindig_veel_metingen_bewaard(self):
        metingen = GeschiedenisVanAudioniveaus()
        for nummer in range(250):
            metingen.onthoud_gemeten_audioblok(0.1, 0.2, 480, tijdstip=10 + nummer / 100)
        self.assertEqual(len(metingen._metingen), MAXIMALE_AANTAL_RECENTE_METINGEN)
        self.assertEqual(len(metingen._metingen[0]), 4)


class TestMixerHeeftNiveaumetersZonderEenEchteGeluidsdriver(unittest.TestCase):
    def setUp(self):
        driver = MagicMock()
        driver.CallbackAbort = RuntimeError
        self.mixer = LiveAudiomixer(driver, MagicMock(spec=logging.Logger), MagicMock(spec=logging.Logger))

    def test_live_mixer_legt_echte_microfoon_en_kabelpiek_vast(self):
        for ingang in (0.1, 0.8, 0.1, 0.1):
            microfoon = np.full((480, 1), ingang, dtype=np.float32)
            uitvoer = np.zeros((480, 2), dtype=np.float32)
            self.mixer.verwerk_een_blok_live_audio(microfoon, uitvoer, 480, None, False)
        status = self.mixer.geef_huidige_status()
        self.assertTrue(status.is_signaal_gemeten)
        self.assertAlmostEqual(status.laatst_gemeten_microfoon_piek, 0.8)
        self.assertAlmostEqual(status.laatst_gemeten_kabel_piek, 0.64)
        self.assertGreater(status.laatst_gemeten_microfoon_rms, 0.1)
        self.assertEqual(status.aantal_bufferproblemen, 0)

    def test_vensters_worden_bij_opnieuw_verbinden_weer_leeg(self):
        metingen = self.mixer._recente_microfoonmetingen
        metingen.onthoud_gemeten_audioblok(0.5, 0.5, 480)
        self.assertGreater(self.mixer.geef_huidige_status().laatst_gemeten_microfoon_piek, 0)
        # De waarde komt niet van een globale instantie en kan los gereset worden.
        self.mixer._recente_microfoonmetingen = GeschiedenisVanAudioniveaus()
        self.assertEqual(self.mixer.geef_huidige_status().laatst_gemeten_microfoon_piek, 0.0)


class TestWebpaginaHeeftTweeGelijkeVloeiendeMeters(unittest.TestCase):
    def test_microfoon_en_kabel_hebben_beide_een_piekmarkering(self):
        webmap = Path(__file__).resolve().parents[1] / 'app' / 'webinterface' / 'statisch'
        html = (webmap / 'dashboard.html').read_text(encoding='utf-8')
        javascript = (webmap / 'dashboard.js').read_text(encoding='utf-8')
        for naam in ('microfoon', 'uitvoer'):
            self.assertIn(f'id="meter-{naam}"', html)
            self.assertIn(f'id="meter-{naam}-piek"', html)
            self.assertIn(f'meter-{naam}-piek', javascript)
        self.assertIn('requestAnimationFrame(beweegLiveNiveaumeters)', javascript)

    def test_javascript_en_css_nemen_dezelfde_dbfs_schaal(self):
        webmap = Path(__file__).resolve().parents[1] / 'app' / 'webinterface' / 'statisch'
        html = (webmap / 'dashboard.html').read_text(encoding='utf-8')
        javascript = (webmap / 'dashboard.js').read_text(encoding='utf-8')
        css = (webmap / 'stijl.css').read_text(encoding='utf-8')
        self.assertIn('−60', html)
        self.assertIn('(decibel - DECIBEL_ONDERKANT_VAN_METER) * 100 /', javascript)
        self.assertIn('prefers-reduced-motion', javascript)
        self.assertIn('.meter-piek', css)



if __name__ == '__main__':
    unittest.main()
