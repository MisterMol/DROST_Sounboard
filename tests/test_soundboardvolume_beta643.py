"""6.1 Beta 4.3: test apart soundboardvolume, opslag en werkelijke audioblokken."""
from __future__ import annotations

from pathlib import Path
import logging
import tempfile
import unittest
from unittest.mock import MagicMock

import numpy as np

from app.audio.geluidsbestanden import VoorbereidGeluidsfragment
from app.audio.live_audiomixer import LiveAudiomixer, _LopendGeluidsfragment
from app.webinterface.favorieten_en_instellingen import (
    VasteFavorietenEnInstellingen, OngeldigeFavorietOfInstelling,
)


class TestSoundboardvolumeOpslag(unittest.TestCase):
    def test_standaard_75_en_persisteert_ook_na_opnieuw_openen(self):
        with tempfile.TemporaryDirectory() as t:
            pad = Path(t) / 'bibliotheek.sqlite3'
            instellingen = VasteFavorietenEnInstellingen(pad)
            self.assertEqual(instellingen.geef_algemeen_effectvolume(), 75)
            self.assertEqual(instellingen.bewaar_algemeen_effectvolume(70), 70)
            self.assertEqual(VasteFavorietenEnInstellingen(pad).geef_algemeen_effectvolume(), 70)
            instellingen.bewaar_algemeen_effectvolume(0)
            self.assertEqual(VasteFavorietenEnInstellingen(pad).geef_algemeen_effectvolume(), 0)
            instellingen.bewaar_algemeen_effectvolume(100)
            self.assertEqual(instellingen.geef_algemeen_effectvolume(), 100)

    def test_versterking_tot_200_wordt_bewaard_en_opnieuw_gelezen(self):
        with tempfile.TemporaryDirectory() as t:
            pad = Path(t) / 'bibliotheek.sqlite3'
            instellingen = VasteFavorietenEnInstellingen(pad)
            for percentage in (100, 101, 150, 199, 200):
                with self.subTest(percentage=percentage):
                    self.assertEqual(instellingen.bewaar_algemeen_effectvolume(percentage), percentage)
                    self.assertEqual(VasteFavorietenEnInstellingen(pad).geef_algemeen_effectvolume(), percentage)

    def test_invaliden_weigeren_zonder_waarde_te_wijzigen(self):
        with tempfile.TemporaryDirectory() as t:
            instellingen = VasteFavorietenEnInstellingen(Path(t) / 'db.sqlite3')
            instellingen.bewaar_algemeen_effectvolume(65)
            for onjuist in (True, False, 65.0, -1, 201, None, '75', float('nan')):
                with self.subTest(onjuist=onjuist), self.assertRaisesRegex(
                        OngeldigeFavorietOfInstelling, 'VOLUME-001'):
                    instellingen.bewaar_algemeen_effectvolume(onjuist)
            self.assertEqual(instellingen.geef_algemeen_effectvolume(), 65)


class TestSoundboardvolumeInDeCallback(unittest.TestCase):
    def setUp(self):
        self.mixer = LiveAudiomixer(MagicMock(), MagicMock(spec=logging.Logger),
                                     MagicMock(spec=logging.Logger))
        self.mixer._geluidseffecten_ingeschakeld = True
        self.microfoon = np.full((480, 1), 0.1, dtype=np.float32)

    def verwerk(self):
        uitvoer = np.zeros((480, 2), dtype=np.float32)
        self.mixer.verwerk_een_blok_live_audio(self.microfoon, uitvoer, 480, None, False)
        return uitvoer

    def activeer_geluid(self, samples):
        bron = np.asarray(samples, dtype=np.float32).copy()
        fragment = VoorbereidGeluidsfragment(
            naam_van_het_geluid='test', bestandspad=Path('test.wav'),
            vingerafdruk_van_audio='sampletest', ruwe_float32_stereo_audio=bron.tobytes(),
            aantal_frames=len(bron), oorspronkelijke_samplefrequentie=48000,
            oorspronkelijke_aantal_kanalen=2, ingesteld_volume=1.0,
        )
        self.mixer._huidige_geluid = _LopendGeluidsfragment(
            afspeelbeurt_id='test', geluid=fragment, voorbereide_samples=bron,
        )
        return bron

    def test_honderd_procent_is_het_oude_niveau(self):
        self.verwerk()  # Geen geluid, ramp is correct ingesteld.
        self.activeer_geluid(np.full((480, 2), .3))
        mix = self.verwerk()
        np.testing.assert_allclose(mix, .38, atol=1e-6)
        self.assertFalse(self.mixer._stop_de_verbinding.is_set())

    def test_zestig_procent_beinvloedt_alleen_effect_en_headsetmonitor(self):
        effect_to_headset = MagicMock()
        self.mixer.koppel_monitor_voor_effecten(effect_to_headset, lambda: None)
        self.mixer.stel_algemeen_effectvolume_in(60)
        self.verwerk()  # Nu geen geluid: sla de actuele stand op.
        bron = self.activeer_geluid(np.full((480, 2), .3))
        mix = self.verwerk()
        np.testing.assert_allclose(mix, 0.08 + .18, atol=1e-6)
        np.testing.assert_allclose(effect_to_headset.call_args.args[0], .18, atol=1e-6)
        np.testing.assert_allclose(bron, .3, atol=1e-6)
        self.assertFalse(self.mixer._stop_de_verbinding.is_set())

    def test_nul_procent_is_stil_effect_met_hoorbare_microfoon(self):
        self.mixer.stel_algemeen_effectvolume_in(0)
        self.verwerk()
        self.activeer_geluid(np.full((480, 2), .6))
        mix = self.verwerk()
        np.testing.assert_allclose(mix, .08, atol=1e-6)
        self.assertFalse(self.mixer._stop_de_verbinding.is_set())

    def test_aanpassen_tijdens_fragment_geeft_vloeiende_overgang(self):
        self.verwerk()
        bron = self.activeer_geluid(np.full((1440, 2), .3))
        eerste = self.verwerk()
        self.mixer.stel_algemeen_effectvolume_in(20)
        tweede = self.verwerk()
        derde = self.verwerk()
        self.assertAlmostEqual(float(eerste[0,0]), .38, places=5)
        self.assertGreater(float(tweede[0,0]), float(tweede[-1,0]))
        self.assertGreater(float(tweede[0,0]), float(derde[0,0]))
        np.testing.assert_allclose(derde, .08 + .06, atol=1e-6)
        np.testing.assert_allclose(bron, .3, atol=1e-6)
        self.assertFalse(self.mixer._stop_de_verbinding.is_set())

    def test_200_procent_versterkt_alleen_soundboard_en_headset(self):
        monitor = MagicMock()
        self.mixer.koppel_monitor_voor_effecten(monitor, lambda: None)
        self.mixer.stel_algemeen_effectvolume_in(200)
        self.verwerk()
        bron = self.activeer_geluid(np.full((480, 2), .1))
        mix = self.verwerk()
        np.testing.assert_allclose(mix, .08 + .2, atol=1e-6)
        np.testing.assert_allclose(monitor.call_args.args[0], .2, atol=1e-6)
        np.testing.assert_allclose(bron, .1, atol=1e-6)
        self.assertEqual(self.mixer.geef_algemeen_effectvolume(), 200)
        self.assertFalse(self.mixer._stop_de_verbinding.is_set())

    def test_foute_percentages_mogen_niet_in_callback(self):
        for onjuist in (True, -5, 201, '50', 0.5, None):
            with self.subTest(waarde=onjuist), self.assertRaisesRegex(ValueError, 'VOLUME-001'):
                self.mixer.stel_algemeen_effectvolume_in(onjuist)
        self.assertEqual(self.mixer.geef_algemeen_effectvolume(), 100)


class TestSoundboardvolumeInterface(unittest.TestCase):
    def test_instelscherm_houdt_het_dashboard_compact(self):
        root = Path(__file__).resolve().parents[1] / 'app/webinterface/statisch'
        html = (root / 'dashboard.html').read_text(encoding='utf-8')
        instellingen = html.split('id="instellingen-pagina"',1)[1]
        dashboard = html.split('id="instellingen-pagina"',1)[0]
        self.assertIn('id="algemeen-effectvolume"', instellingen)
        self.assertIn('id="effectvolume-reset"', instellingen)
        self.assertNotIn('id="algemeen-effectvolume"', dashboard)
        js = (root / 'dashboard.js').read_text(encoding='utf-8')
        self.assertIn('effectvolumeFactor', js)
        self.assertIn('gebruikPreviewNormalisatie(toestand.preview)', js)
        self.assertIn('koppelAlgemeenEffectvolume()', js)
