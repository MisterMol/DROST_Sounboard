"""6.1 bèta: verwerkte live-stem, veilige lokale preview en voorkeuren."""
from __future__ import annotations

import logging
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import MagicMock

import numpy as np

from app.audio.apparatenbeheer import GevondenAudioapparaat
from app.audio.stemvervorming import Stemvervormer, controleer_stemprofiel
from app.audio.stemvoorbeeld import LokaalStemvoorbeeld, StemvoorbeeldFout
from app.audio.live_audiomixer import LiveAudiomixer
from app.webinterface.favorieten_en_instellingen import VasteFavorietenEnInstellingen


class TestLiveStemvervormer(unittest.TestCase):
    def setUp(self):
        self.fs = 48000
        tijd = np.arange(self.fs, dtype=np.float64) / self.fs
        self.stem = (.35 * np.sin(2 * np.pi * 220 * tijd)).astype(np.float32)[:, None]

    def verwerk_een_seconde(self, profiel):
        processor = Stemvervormer(profiel)
        blokken = [processor.verwerk(self.stem[i:i + 480])
                    for i in range(0, len(self.stem), 480)]
        return np.concatenate(blokken)[:, 0]

    def test_normaal_is_exact_onveranderd(self):
        processor = Stemvervormer()
        stukje = self.stem[:480]
        self.assertIs(processor.verwerk(stukje), stukje)
        np.testing.assert_array_equal(self.verwerk_een_seconde('normaal'), self.stem[:, 0])

    @unittest.skipUnless((Path(__file__).resolve().parents[1] / 'app/audio/native/win-x64/drost_stem.dll').is_file(),
                         'Echte DSP-motor ontbreekt in CI-checkout; lokaal voor release verplicht')
    def test_vervorming_is_hoorbaar_en_laat_bron_ongewijzigd(self):
        origineel = self.stem.copy()
        for profiel in ('radio', 'robot', 'diep'):
            resultaat = self.verwerk_een_seconde(profiel)
            self.assertTrue(np.isfinite(resultaat).all(), profiel)
            self.assertGreater(np.sqrt(np.mean((resultaat - origineel[:, 0])**2)), .04, profiel)
        np.testing.assert_array_equal(self.stem, origineel)

    def test_robot_heeft_modulatie_zijbanden(self):
        x = self.verwerk_een_seconde('robot')
        spectrum = np.abs(np.fft.rfft(x))
        self.assertGreater(spectrum[172], 10)
        self.assertGreater(spectrum[268], 10)

    @unittest.skipUnless((Path(__file__).resolve().parents[1] / 'app/audio/native/win-x64/drost_stem.dll').is_file(),
                         'Echte DSP-motor ontbreekt in CI-checkout; lokaal voor release verplicht')
    def test_diep_verlaagt_220_hertz_in_de_praktijk(self):
        x = self.verwerk_een_seconde('diep')[24000:]
        spec = np.abs(np.fft.rfft(x * np.hanning(len(x))))
        freq = np.fft.rfftfreq(len(x), 1/48000)
        grondtoon = float(freq[np.argmax(spec)])
        self.assertTrue(164 < grondtoon < 181, grondtoon)

    def test_radio_verzwakt_hoogfrequente_energie(self):
        tijd = np.arange(48000)/48000
        hoog = (0.2 * np.sin(2*np.pi*9000*tijd)).astype(np.float32)[:,None]
        proc = Stemvervormer('radio')
        resultaat = np.concatenate([proc.verwerk(hoog[i:i+480]) for i in range(0,len(hoog),480)])
        self.assertLess(np.sqrt(np.mean(resultaat[5000:]**2)), .08)

    def test_blokgrenzen_geven_consistente_verwerking(self):
        processor1, processor2 = Stemvervormer('robot'), Stemvervormer('robot')
        uit1 = np.concatenate([processor1.verwerk(self.stem[i:i+480]) for i in range(0,len(self.stem),480)])
        uit2 = np.concatenate([processor2.verwerk(self.stem[i:i+240]) for i in range(0,len(self.stem),240)])
        np.testing.assert_allclose(uit1, uit2, atol=1e-6)

    def test_ongeldige_stand_en_samples_worden_geweigerd(self):
        for waarde in ('', 'logitech', None, 0, True):
            with self.assertRaises(ValueError):
                controleer_stemprofiel(waarde)
        with self.assertRaisesRegex(ValueError, 'STEM-004'):
            Stemvervormer('robot').verwerk(np.asarray([[np.nan]], dtype=np.float32))

    def test_mixer_dempt_bij_dsp_fout_zonder_microfoon_te_verbreken(self):
        mixer = LiveAudiomixer(MagicMock(), MagicMock(spec=logging.Logger), MagicMock(spec=logging.Logger))
        mixer.stel_stemprofiel_in('robot')
        mixer.stel_stemvervormer_aan_in(True)
        mixer._stemvervormer.verwerk = MagicMock(side_effect=RuntimeError('gesimuleerde dsp-fout'))
        microfoon = np.ones((480, 1), dtype=np.float32)*.1
        uitvoer = np.zeros((480, 2), dtype=np.float32)
        mixer.verwerk_een_blok_live_audio(microfoon, uitvoer, 480, None, False)
        np.testing.assert_array_equal(uitvoer, np.zeros_like(uitvoer))
        self.assertTrue(mixer._stemvervorming_geblokkeerd)
        self.assertEqual(mixer._stemvervorming_terugvallen, 1)
        self.assertFalse(mixer._stop_de_verbinding.is_set())


class TestProfielBewaren(unittest.TestCase):
    def test_nieuwe_en_bestaande_sqlite_database(self):
        with tempfile.TemporaryDirectory() as temp:
            db = Path(temp)/'instellingen.sqlite3'
            items = VasteFavorietenEnInstellingen(db)
            self.assertEqual(items.geef_stemprofiel(), 'normaal')
            self.assertEqual(items.bewaar_stemprofiel('diep'), 'diep')
            self.assertEqual(VasteFavorietenEnInstellingen(db).geef_stemprofiel(), 'diep')
            with self.assertRaises(ValueError):
                items.bewaar_stemprofiel('ongeldig')
            self.assertEqual(items.geef_stemprofiel(), 'diep')


class FakeDuplexAudio:
    def __init__(self):
        self.kwargs = None
        self.uitvoer = None
        self.geopend = False

    def check_input_settings(self, **kwargs):
        return None

    def check_output_settings(self, **kwargs):
        return None

    def Stream(self, **kwargs):
        self.kwargs = kwargs
        eigenaar = self
        class Stroom:
            def __enter__(self):
                eigenaar.geopend = True
                microfoon = np.ones((480,1),dtype=np.float32)*.13
                output = np.zeros((480,2),dtype=np.float32)
                kwargs['callback'](microfoon,output,480,None,False)
                eigenaar.uitvoer=output.copy()
                return self
            def __exit__(self,*args):
                eigenaar.geopend = False
        return Stroom()


class TestVeiligeStemPreview(unittest.TestCase):
    def setUp(self):
        self.driver = FakeDuplexAudio()
        self.service = LokaalStemvoorbeeld(self.driver, MagicMock(spec=logging.Logger))
        self.mic = GevondenAudioapparaat(5, 'Microfoon (USB headset)', 'Windows WASAPI', 1, 0)
        self.headset = GevondenAudioapparaat(9, 'Koptelefoon', 'Windows WASAPI', 0, 2)
        self.kabel = GevondenAudioapparaat(11, 'CABLE Input (VB-Audio Virtual Cable)', 'Windows WASAPI', 0, 2)

    def tearDown(self):
        self.service.stop()

    def test_preview_gebruikt_fysieke_uitvoer_niet_de_kabel(self):
        self.service.start(self.mic,self.headset,'robot')
        self.assertTrue(self.service.actief)
        self.assertEqual(self.driver.kwargs['device'], (5,9))
        self.assertEqual(self.driver.kwargs['channels'], (1,2))
        self.assertGreater(np.max(np.abs(self.driver.uitvoer)),.001)
        self.service.stop()
        self.assertFalse(self.service.actief)

    def test_preview_weigert_cable_als_uitvoer(self):
        with self.assertRaisesRegex(StemvoorbeeldFout, 'STEM-010'):
            self.service.start(self.mic,self.kabel,'radio')
        self.assertIsNone(self.driver.kwargs)

    def test_preview_weigert_een_tweede_stream(self):
        self.service.start(self.mic,self.headset,'normaal')
        with self.assertRaisesRegex(StemvoorbeeldFout, 'STEM-011'):
            self.service.start(self.mic,self.headset,'robot')

    def test_preview_kan_tijdens_luisteren_profiel_wijzigen(self):
        self.service.start(self.mic,self.headset,'radio')
        self.service.stel_stemprofiel_in('robot')
        self.service._audio_callback(np.ones((480,1),dtype=np.float32)*.2,
                                    np.zeros((480,2),dtype=np.float32),480,None,False)
        self.assertEqual(self.service._processor.profiel,'robot')

if __name__ == '__main__':
    unittest.main()
