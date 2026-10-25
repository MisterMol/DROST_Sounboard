"""Extra tests voor diagnose bij een 'verbonden' maar stille audiomixer."""

from __future__ import annotations

import logging
import time
import unittest
from unittest.mock import MagicMock, patch

import numpy as np

from app.audio.apparatenbeheer import GevondenAudioapparaat
from app.audio.live_audiomixer import LiveAudiomixer
from app.audio.signaaldiagnose import (
    SignaalmetingFout,
    meet_rms_en_piek_van_een_audioblok,
    maak_een_leesbaar_geluidsniveau,
    bereken_meterstand_op_schaal_van_honderd,
)
from diagnoseer_microfoon import (
    vind_de_microfoon_voor_een_rechtstreekse_test,
    meet_fysieke_microfoon_zonder_opslag,
)


class TestLosseSignaalmetingen(unittest.TestCase):
    def test_stille_microfoon_wordt_niet_aangezien_voor_signaal(self):
        rms, piek = meet_rms_en_piek_van_een_audioblok(np.zeros((100, 1), dtype=np.float32))
        self.assertEqual(rms, 0.0)
        self.assertEqual(piek, 0.0)
        self.assertIn("geen meetbaar", maak_een_leesbaar_geluidsniveau(rms, True))
        self.assertEqual(bereken_meterstand_op_schaal_van_honderd(rms, True), 0)

    def test_bekend_signaal_heeft_rekenkundig_correct_niveau(self):
        rms, piek = meet_rms_en_piek_van_een_audioblok(
            np.array([[0.5], [-0.5]], dtype=np.float32)
        )
        self.assertAlmostEqual(rms, 0.5)
        self.assertAlmostEqual(piek, 0.5)
        self.assertIn("dBFS", maak_een_leesbaar_geluidsniveau(rms, True))
        self.assertGreater(bereken_meterstand_op_schaal_van_honderd(rms, True), 50)

    def test_nan_of_oneindig_wordt_niet_als_geldig_geluid_gezien(self):
        for waarde in (np.nan, np.inf, -np.inf):
            with self.subTest(waarde=waarde):
                with self.assertRaisesRegex(SignaalmetingFout, "SIGNAAL-003"):
                    meet_rms_en_piek_van_een_audioblok(
                        np.array([[waarde]], dtype=np.float32)
                    )

    def test_lege_of_verkeerde_frames_krijgen_duidelijke_foutcodes(self):
        with self.assertRaisesRegex(SignaalmetingFout, "SIGNAAL-002"):
            meet_rms_en_piek_van_een_audioblok(np.zeros((0, 2), dtype=np.float32))
        with self.assertRaisesRegex(SignaalmetingFout, "SIGNAAL-001"):
            meet_rms_en_piek_van_een_audioblok(None)

    def test_nog_niet_gemeten_is_iets_anders_dan_stil(self):
        self.assertEqual(maak_een_leesbaar_geluidsniveau(0.0, False), "nog niet gemeten")


class TestMixerMeetGeluidZonderOpslag(unittest.TestCase):
    def setUp(self):
        self.nepdriver = MagicMock()
        self.nepdriver.CallbackAbort = RuntimeError
        self.mixer = LiveAudiomixer(self.nepdriver, MagicMock(spec=logging.Logger),
                                    MagicMock(spec=logging.Logger))

    def test_mixer_telt_callbacks_en_meet_het_echte_niveau(self):
        for nummer in range(8):
            binnen = np.full((120, 1), 0.2, dtype=np.float32)
            naar_kabel = np.zeros((120, 2), dtype=np.float32)
            self.mixer.verwerk_een_blok_live_audio(binnen, naar_kabel, 120, None, False)
        status = self.mixer.geef_huidige_status()
        self.assertEqual(status.aantal_audio_callbacks, 8)
        self.assertEqual(status.aantal_aangeleverde_frames, 960)
        self.assertTrue(status.is_signaal_gemeten)
        self.assertAlmostEqual(status.laatst_gemeten_microfoon_rms, 0.2)
        self.assertAlmostEqual(status.laatst_gemeten_kabel_rms, 0.16)
        self.assertAlmostEqual(status.laatst_gemeten_microfoon_piek, 0.2)
        self.assertIsNotNone(status.seconden_sinds_laatste_callback)

    def test_actieve_callback_met_stilte_heeft_wel_callbacks_maar_geen_signaal(self):
        for _ in range(4):
            binnen = np.zeros((120, 1), dtype=np.float32)
            naar_kabel = np.full((120, 2), 3.0, dtype=np.float32)
            self.mixer.verwerk_een_blok_live_audio(binnen, naar_kabel, 120, None, False)
        status = self.mixer.geef_huidige_status()
        self.assertEqual(status.laatst_gemeten_microfoon_rms, 0)
        # maak_stereoblok_met_microfoon moet uitvoerbuffer eerst overschrijven.
        self.assertEqual(status.laatst_gemeten_kabel_rms, 0)

    def test_onjuiste_samples_worden_niet_stilzwijgend_naar_kabel_gestuurd(self):
        with self.assertRaises(RuntimeError):
            for _ in range(4):
                self.mixer.verwerk_een_blok_live_audio(
                    np.array([[np.nan]], dtype=np.float32),
                    np.zeros((1, 2), dtype=np.float32), 1, None, False,
                )


class NepDriverMetStilstaandeCallbacks:
    CallbackAbort = RuntimeError

    def __init__(self):
        self.stroom = self.NepStroom()

    def check_input_settings(self, **kwargs):
        return None

    def check_output_settings(self, **kwargs):
        return None

    def Stream(self, **kwargs):
        return self.stroom

    class NepStroom:
        active = False

        def start(self):
            self.active = True

        def stop(self, ignore_errors=False):
            self.active = False

        def close(self, ignore_errors=False):
            self.active = False


class TestDriverDieWelStartMaarGeenAudioGeeft(unittest.TestCase):
    def test_verbonden_zonder_callbacks_wordt_na_korte_bewaking_fout(self):
        uitgevallen_driver = NepDriverMetStilstaandeCallbacks()
        softwarelogboek = MagicMock(spec=logging.Logger)
        auditlogboek = MagicMock(spec=logging.Logger)
        mixer = LiveAudiomixer(uitgevallen_driver, softwarelogboek, auditlogboek)
        mic = GevondenAudioapparaat(24, "Microfoon (Razer USB Sound Card)", "Windows WASAPI", 2, 0)
        kabel = GevondenAudioapparaat(21, "CABLE Input (VB-Audio Virtual Cable)", "Windows WASAPI", 0, 2)
        with patch("app.audio.live_audiomixer.MAXIMALE_TIJD_ZONDER_AUDIO_CALLBACK_IN_SECONDEN", 0.22):
            mixer.verbind_de_microfoon_met_vb_cable(mic, kabel)
            deadline = time.monotonic() + 2
            while mixer.geef_huidige_status().toestand != "fout":
                self.assertLess(time.monotonic(), deadline)
                time.sleep(0.03)
            self.assertTrue(mixer.wacht_tot_verbinding_echt_weg_is())
        self.assertIn("LIVE-018", mixer.geef_huidige_status().laatst_bekende_fout)
        self.assertTrue(softwarelogboek.exception.called)


class NepMicrofoonStream:
    def __init__(self, callback, heeft_signaal=True):
        self.callback = callback
        self.heeft_signaal = heeft_signaal

    def __enter__(self):
        if self.heeft_signaal:
            self.callback(np.full((240, 1), 0.1, dtype=np.float32), 240, None, False)
        return self

    def __exit__(self, *args):
        return False


class NepMicrofoonBibliotheek:
    CallbackAbort = RuntimeError

    def __init__(self, heeft_signaal=True):
        self.heeft_signaal = heeft_signaal

    def check_input_settings(self, **kwargs):
        return None

    def InputStream(self, **kwargs):
        return NepMicrofoonStream(kwargs["callback"], self.heeft_signaal)


class TestLosseMicrofoonControle(unittest.TestCase):
    def setUp(self):
        self.microfoon = GevondenAudioapparaat(
            24, "Microfoon (Razer USB Sound Card)", "Windows WASAPI", 2, 0
        )
        self.software = MagicMock(spec=logging.Logger)
        self.audit = MagicMock(spec=logging.Logger)

    def test_herkent_de_enige_microfoon_zonder_vast_nummer(self):
        gevonden = vind_de_microfoon_voor_een_rechtstreekse_test([self.microfoon])
        self.assertIs(gevonden, self.microfoon)

    def test_kiest_windows_standaard_microfoon_bij_meerdere_merken(self):
        tweede = GevondenAudioapparaat(26, 'Microfoon (Logitech)', 'Windows WASAPI', 1, 0)
        gevonden = vind_de_microfoon_voor_een_rechtstreekse_test(
            [self.microfoon, tweede], standaardnummer=26)
        self.assertIs(gevonden, tweede)

    def test_zonder_standaard_kiest_diagnose_niet_willekeurig(self):
        tweede = GevondenAudioapparaat(26, 'Microfoon (Logitech)', 'Windows WASAPI', 1, 0)
        with self.assertRaisesRegex(RuntimeError, 'MIC-005'):
            vind_de_microfoon_voor_een_rechtstreekse_test([self.microfoon, tweede])

    def test_directe_test_bewaart_alleen_geluidsniveaus(self):
        with patch("diagnoseer_microfoon.time.sleep", return_value=None):
            gegevens = meet_fysieke_microfoon_zonder_opslag(
                NepMicrofoonBibliotheek(), self.microfoon, self.software, self.audit
            )
        self.assertAlmostEqual(gegevens["hoogste_rms"], 0.1)
        self.assertEqual(gegevens["spraakbestand_opgeslagen"], False)
        self.assertGreater(gegevens["aantal_callbacks"], 0)

    def test_inputstream_zonder_callbacks_wordt_niet_gezien_als_werkend(self):
        with patch("diagnoseer_microfoon.time.sleep", return_value=None):
            with self.assertRaisesRegex(RuntimeError, "MIC-003"):
                meet_fysieke_microfoon_zonder_opslag(
                    NepMicrofoonBibliotheek(heeft_signaal=False), self.microfoon,
                    self.software, self.audit
                )


if __name__ == "__main__":
    unittest.main()
