"""Beta 5: numerieke piekbeveiliging zonder echte microfoon of kabel."""

from __future__ import annotations

import logging
import math
from pathlib import Path
import tempfile
import unittest
from unittest.mock import MagicMock, patch

import numpy as np

from app.audio.pieklimiter import PiekLimiter, PIEKPLAFOND
from app.audio.live_audiomixer import LiveAudiomixer
from app.webinterface.favorieten_en_instellingen import (
    VasteFavorietenEnInstellingen, OngeldigeFavorietOfInstelling,
)


class TestPiekLimiterOpAudioframes(unittest.TestCase):
    def test_rustig_signaal_blijft_exact_gelijk_en_heeft_geen_vertraging(self):
        bron = np.tile(np.sin(np.linspace(0.2, 20.2, 480)).astype(np.float32)[:, None], (1, 2)) * 0.2
        verwerkt = bron.copy()
        reductie = PiekLimiter().verwerk_in_place(verwerkt)
        np.testing.assert_array_equal(verwerkt, bron)
        self.assertEqual(reductie, 0.0)
        self.assertNotEqual(float(verwerkt[0, 0]), 0.0)

    def test_harde_stereo_mix_komt_nooit_boven_plafond(self):
        limiter = PiekLimiter()
        sinus = np.sin(np.linspace(0, 60 * np.pi, 480, dtype=np.float32))
        origineel = np.column_stack((1.6 * sinus, 1.0 * sinus)).astype(np.float32)
        verwerkt = origineel.copy()
        reductie = limiter.verwerk_in_place(verwerkt)
        self.assertGreater(reductie, 2.0)
        self.assertLessEqual(np.max(np.abs(verwerkt)), PIEKPLAFOND + 1e-5)
        # Behoud van stereo-ratio: één gedeelde gain op beide kanalen.
        np.testing.assert_allclose(verwerkt[:, 0], 1.6 * verwerkt[:, 1], rtol=1e-5, atol=1e-6)
        # Niet de huidige hard-clip-output: geen platte sample-toppen.
        clip = np.clip(origineel, -PIEKPLAFOND, PIEKPLAFOND)
        self.assertGreater(np.max(np.abs(verwerkt - clip)), 0.01)

    def test_limiter_begint_voordat_nabije_piek_komt(self):
        limiter = PiekLimiter()
        bron = np.full((480, 2), 0.3, dtype=np.float32)
        bron[100, :] = 1.5
        limiter.verwerk_in_place(bron)
        self.assertLess(float(bron[60, 0]), 0.3)  # vóór de piek al terugregelen
        self.assertLessEqual(np.max(np.abs(bron)), PIEKPLAFOND + 1e-5)

    def test_herstelt_geleidelijk_en_niet_bloksgewijs(self):
        limiter = PiekLimiter()
        hard = np.full((480, 2), 1.4, dtype=np.float32)
        limiter.verwerk_in_place(hard)
        zacht = np.full((480, 2), 0.2, dtype=np.float32)
        limiter.verwerk_in_place(zacht)
        self.assertLess(float(zacht[0, 0]), float(zacht[-1, 0]))
        self.assertLess(float(zacht[-1, 0]), 0.2)
        for _ in range(25):
            limiter.verwerk_in_place(np.full((480, 2), 0.2, dtype=np.float32))
        laatste = np.full((480, 2), 0.2, dtype=np.float32)
        self.assertEqual(limiter.verwerk_in_place(laatste), 0)
        np.testing.assert_array_equal(laatste, np.full((480, 2), 0.2, dtype=np.float32))

    def test_onverwachte_invoer_wordt_afgewezen(self):
        limiter = PiekLimiter()
        for sample in (np.nan, np.inf, -np.inf):
            with self.subTest(sample=sample):
                with self.assertRaisesRegex(ValueError, 'LIMITER-003'):
                    limiter.verwerk_in_place(np.full((10, 2), sample, dtype=np.float32))
        with self.assertRaisesRegex(ValueError, 'LIMITER-002'):
            limiter.verwerk_in_place(np.zeros((10, 1), dtype=np.float32))

    def test_geen_extra_afhankelijkheden_of_python_lus_per_audioframe(self):
        import inspect
        code = inspect.getsource(PiekLimiter.verwerk_in_place)
        self.assertIn('np.minimum.accumulate', code)
        self.assertNotIn('for frame in', code)


class TestMixerIntegratie(unittest.TestCase):
    def setUp(self):
        self.driver = MagicMock()
        self.driver.CallbackAbort = RuntimeError
        self.software = MagicMock(spec=logging.Logger)
        self.audit = MagicMock(spec=logging.Logger)
        self.mixer = LiveAudiomixer(self.driver, self.software, self.audit)

    def verwerk(self, microfoonwaarde):
        ingang = np.full((480, 1), microfoonwaarde, dtype=np.float32)
        resultaat = np.zeros((480, 2), dtype=np.float32)
        self.mixer.verwerk_een_blok_live_audio(ingang, resultaat, 480, None, False)
        return resultaat

    def test_bij_normale_stem_geen_onbedoelde_verandering(self):
        resultaat = self.verwerk(0.2)
        np.testing.assert_allclose(resultaat, 0.16, atol=1e-7)
        self.assertEqual(self.mixer.geef_huidige_status().limiter_reductie_db, 0)

    def test_stem_kan_hard_zijn_en_toch_blijft_stream_draaien(self):
        resultaat = self.verwerk(2.0)
        self.assertLessEqual(np.max(np.abs(resultaat)), PIEKPLAFOND + 1e-6)
        self.assertGreater(self.mixer.geef_huidige_status().limiter_reductie_db, 0)
        self.assertFalse(self.mixer._stop_de_verbinding.is_set())
        # Stoppen van een niet-actief effect verbreekt nooit de microfoon.
        self.mixer.stop_het_huidige_geluid()
        resultaat = self.verwerk(0.25)
        self.assertGreater(np.max(np.abs(resultaat)), 0)
        self.assertFalse(self.mixer._stop_de_verbinding.is_set())

    def test_bypass_gebruikt_oude_veiligheidsclip(self):
        self.mixer.stel_limiter_in(False)
        uitvoer = self.verwerk(2.0)
        np.testing.assert_allclose(uitvoer, PIEKPLAFOND)
        self.assertFalse(self.mixer.geef_huidige_status().limiter_aan)
        self.mixer.stel_limiter_in(True)
        uitvoer = self.verwerk(2.0)
        self.assertTrue(self.mixer.geef_huidige_status().limiter_aan)
        self.assertGreater(self.mixer.geef_huidige_status().limiter_reductie_db, 0)
        self.assertLessEqual(np.max(np.abs(uitvoer)), PIEKPLAFOND + 1e-6)

    def test_als_limiter_faalt_geen_driver_abort_en_traceback_buiten_callback(self):
        with patch.object(self.mixer._limiter, 'verwerk_in_place', side_effect=RuntimeError('limiter testfout')):
            uitvoer = self.verwerk(2.0)
        self.assertLessEqual(np.max(np.abs(uitvoer)), PIEKPLAFOND + 1e-6)
        self.assertEqual(self.mixer.geef_huidige_status().limiter_terugvallen, 1)
        self.assertFalse(self.mixer._stop_de_verbinding.is_set())
        self.software.error.assert_not_called()  # nooit loggen binnen callback
        self.mixer._schrijf_alle_uitgestelde_auditregels()
        self.software.error.assert_called_once()
        self.assertIn('limiter testfout', str(self.software.error.call_args.kwargs['exc_info'][1]))


class TestDashboardLimiterMetNode(unittest.TestCase):
    def test_javascript_limiterweergave_als_node_aanwezig_is(self):
        import shutil
        import subprocess
        if not shutil.which('node'):
            self.skipTest('Node.js ontbreekt; Python-limiter en HTML/API worden wel getest')
        script = Path(__file__).parent / 'hulpmiddelen' / 'test_pieklimiter_beta5.js'
        uitslag = subprocess.run(['node', str(script)], capture_output=True, text=True, timeout=10)
        self.assertEqual(uitslag.returncode, 0, msg=uitslag.stdout + uitslag.stderr)


class TestBewarenVanLimiterinstellingen(unittest.TestCase):
    def test_bestaande_sqlite_krijgt_veilig_default_en_bewaart_stand(self):
        with tempfile.TemporaryDirectory() as mapnaam:
            db = Path(mapnaam) / 'geluiden.sqlite3'
            favorieten = VasteFavorietenEnInstellingen(db)
            self.assertTrue(favorieten.geef_limiterstand())
            self.assertFalse(favorieten.bewaar_limiterstand(False))
            self.assertFalse(VasteFavorietenEnInstellingen(db).geef_limiterstand())
            self.assertTrue(favorieten.bewaar_limiterstand(True))
            self.assertTrue(VasteFavorietenEnInstellingen(db).geef_limiterstand())

    def test_weiger_strings_en_getallen(self):
        with tempfile.TemporaryDirectory() as mapnaam:
            favorieten = VasteFavorietenEnInstellingen(Path(mapnaam) / 'd.db')
            for onjuist in ('false', 1, 0, None, {}, []):
                with self.subTest(waarde=onjuist):
                    with self.assertRaisesRegex(OngeldigeFavorietOfInstelling, 'FAV-020'):
                        favorieten.bewaar_limiterstand(onjuist)
