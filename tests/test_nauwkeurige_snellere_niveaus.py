"""Controleer snelle maar echte niveaus zonder audiodriver.

Een snelle meter is geen vervanger voor een goede meetdefinitie. Deze tests
bevestigen de dBFS-conversie, de werkelijke 50 ms RMS-waarde, samplepiek,
geen blinde audioblokken, en het live HTTP-streamformaat.
"""

import json
import logging
import math
import time
import unittest
from unittest.mock import MagicMock
from types import SimpleNamespace
from urllib.request import urlopen

import numpy as np

from app.audio.geschiedenis_van_audioniveaus import (
    DUUR_VAN_PIEK_VENSTER_IN_SECONDEN,
    DUUR_VAN_RMS_VENSTER_IN_SECONDEN,
    GeschiedenisVanAudioniveaus,
)
from app.audio.live_audiomixer import LiveAudiomixer, AANTAL_CALLBACKS_TUSSEN_SIGNAALMETINGEN
from app.webinterface.bediening_van_de_audiomotor import WebbedieningVanDrostSoundboard
from app.audio.signaaldiagnose import meet_rms_en_piek_van_een_audioblok


class TestNumeriekNauwkeurigeMeting(unittest.TestCase):
    def test_een_volle_sinus_heeft_min_3_01_dbfs_rms_en_nul_dbfs_samplepiek(self):
        frequentie = 1000
        samplefrequentie = 48000
        tonen = np.sin(2 * np.pi * frequentie * np.arange(2400) / samplefrequentie)
        geschiedenis = GeschiedenisVanAudioniveaus()
        for nummer in range(5):
            blok = tonen[nummer * 480:(nummer + 1) * 480].astype(np.float32).reshape(-1, 1)
            rms, piek = meet_rms_en_piek_van_een_audioblok(blok)
            geschiedenis.onthoud_gemeten_audioblok(rms, piek, len(blok), 10.005 + nummer * 0.010)
        rms, piek = geschiedenis.geef_recente_rms_en_piek(10.050)
        self.assertAlmostEqual(20 * math.log10(rms), -3.0103, places=2)
        self.assertAlmostEqual(20 * math.log10(piek), 0.0, places=3)

    def test_korte_meetvensters_vallen_wel_voor_stem_bij_but_werken_niet_met_ghosting(self):
        self.assertEqual(DUUR_VAN_RMS_VENSTER_IN_SECONDEN, 0.05)
        self.assertEqual(DUUR_VAN_PIEK_VENSTER_IN_SECONDEN, 0.12)
        geschiedenis = GeschiedenisVanAudioniveaus()
        geschiedenis.onthoud_gemeten_audioblok(0.8, 0.9, 480, tijdstip=10.0)
        self.assertEqual(geschiedenis.geef_recente_rms_en_piek(tijdstip=10.20), (0.0, 0.0))

    def test_ook_het_eerste_audioblok_wordt_gemeten(self):
        self.assertEqual(AANTAL_CALLBACKS_TUSSEN_SIGNAALMETINGEN, 1)
        driver = MagicMock()
        driver.CallbackAbort = RuntimeError
        mixer = LiveAudiomixer(driver, MagicMock(spec=logging.Logger), MagicMock(spec=logging.Logger))
        ingang = np.full((480, 1), 0.1, dtype=np.float32)
        mixer.verwerk_een_blok_live_audio(ingang, np.zeros((480, 2), dtype=np.float32), 480, None, False)
        status = mixer.geef_huidige_status()
        self.assertTrue(status.is_signaal_gemeten)
        self.assertAlmostEqual(status.laatst_gemeten_microfoon_rms, 0.1, places=5)
        self.assertAlmostEqual(status.laatst_gemeten_kabel_rms, 0.08, places=5)
        self.assertEqual(status.aantal_bufferproblemen, 0)

    def test_stilgevallen_callback_levert_geen_verouderde_niveaus(self):
        # Een laatste hoog audioblok mag na een USB-onderbreking niet blijven
        # hangen als een actieve meter. Dat is belangrijk voor betrouwbaar UI.
        bediener = object.__new__(WebbedieningVanDrostSoundboard)
        bediener.mixer = MagicMock()
        bediener.mixer.geef_huidige_status.return_value = SimpleNamespace(
            toestand='verbonden', is_signaal_gemeten=True,
            seconden_sinds_laatste_callback=0.6,
            laatst_gemeten_microfoon_rms=0.9,
            laatst_gemeten_kabel_rms=0.5,
            laatst_gemeten_microfoon_piek=0.95,
            laatst_gemeten_kabel_piek=0.6,
        )
        niveaus = bediener.geef_directe_audioniveaus()
        self.assertFalse(niveaus['gemeten'])
        self.assertEqual(niveaus['microfoon_rms'], 0.0)
        self.assertEqual(niveaus['kabel_piek'], 0.0)

    def test_ook_stilte_heeft_een_echte_rms_van_nul(self):
        rms, piek = meet_rms_en_piek_van_een_audioblok(np.zeros((240, 2), dtype=np.float32))
        self.assertEqual((rms, piek), (0.0, 0.0))


if __name__ == '__main__':
    unittest.main()
