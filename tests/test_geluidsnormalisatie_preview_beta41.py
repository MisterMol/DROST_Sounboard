"""Beta 4.1: dezelfde effectieve gain in de browser en naar de mixer."""
from __future__ import annotations

import math
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

import numpy as np
import soundfile as sf

from app.audio.mp3_en_wav_fragmenten import lees_en_bereid_mp3_of_wav_voor
from app.audio.preview_normalisatie import bereken_browser_preview_versterkingen


class TestPreviewNormalisatieBeta41(unittest.TestCase):
    def maak_testbestand(self, pad: Path, amplitude: float = .55):
        t = np.arange(48000, dtype=np.float32) / 48000
        samples = (np.sin(2 * np.pi * 360 * t) * amplitude).astype('float32')
        sf.write(pad, samples, 48000)
        return samples

    def test_normalisatie_na_volume_200_procent_verlaagt_harde_clips(self):
        with TemporaryDirectory() as tmp:
            pad = Path(tmp) / 'test.wav'
            self.maak_testbestand(pad, .7)
            uit = lees_en_bereid_mp3_of_wav_voor(pad, ingesteld_volume=2.0, normalisatiestand='uit')
            subtiel = lees_en_bereid_mp3_of_wav_voor(pad, ingesteld_volume=2.0, normalisatiestand='subtiel')
            sterk = lees_en_bereid_mp3_of_wav_voor(pad, ingesteld_volume=2.0, normalisatiestand='sterk')
            self.assertLess(sterk.normalisatiefactor, subtiel.normalisatiefactor)
            self.assertLess(subtiel.normalisatiefactor, 1)
            waarden = lambda clip: float(np.sqrt(np.mean(np.frombuffer(clip.ruwe_float32_stereo_audio, dtype='<f4') ** 2)))
            self.assertGreater(waarden(uit), waarden(subtiel))
            self.assertGreater(waarden(subtiel), waarden(sterk))
            self.assertLessEqual(max(np.abs(np.frombuffer(sterk.ruwe_float32_stereo_audio, dtype='<f4'))), 1.0)

    def test_browser_versterking_volgt_live_sample_niveau_voor_alle_standen(self):
        with TemporaryDirectory() as tmp:
            pad = Path(tmp) / 'voorbeeld.wav'
            self.maak_testbestand(pad, .3)
            for volume in (0.0, .4, 1.0, 2.0):
                with self.subTest(volume=volume):
                    preview = bereken_browser_preview_versterkingen(pad, begin=0, duur=1, volume=volume)
                    bron = lees_en_bereid_mp3_of_wav_voor(pad, ingesteld_volume=1.0, normalisatiestand='uit')
                    basis = np.frombuffer(bron.ruwe_float32_stereo_audio, dtype='<f4')
                    for stand in ('uit', 'subtiel', 'normaal', 'sterk'):
                        live = lees_en_bereid_mp3_of_wav_voor(pad, ingesteld_volume=volume, normalisatiestand=stand)
                        uitgaand = np.frombuffer(live.ruwe_float32_stereo_audio, dtype='<f4')
                        verwachte_gain = preview['versterkingen'][stand]
                        np.testing.assert_allclose(basis * verwachte_gain, uitgaand, atol=0.00002)
                        self.assertTrue(math.isfinite(preview['correcties_db'][stand]))

    def test_piekbeveiliging_bij_stil_fragment_met_hoge_piek(self):
        with TemporaryDirectory() as tmp:
            pad = Path(tmp) / 'spike.wav'
            geluid = np.full((48000,), .01, dtype=np.float32)
            geluid[20000] = .99
            sf.write(pad, geluid, 48000)
            preview = bereken_browser_preview_versterkingen(pad, begin=0, duur=1, volume=2)
            bron = lees_en_bereid_mp3_of_wav_voor(pad, ingesteld_volume=1, normalisatiestand='uit')
            piek = max(np.abs(np.frombuffer(bron.ruwe_float32_stereo_audio, dtype='<f4')))
            for stand, gain in preview['versterkingen'].items():
                self.assertLessEqual(gain * piek, 1.00001, stand)

    def test_originalen_worden_niet_aangepast(self):
        with TemporaryDirectory() as tmp:
            pad = Path(tmp) / 'bron.wav'
            self.maak_testbestand(pad)
            oorspronkelijk = pad.read_bytes()
            bereken_browser_preview_versterkingen(pad, begin=0.1, duur=.3, volume=1)
            self.assertEqual(pad.read_bytes(), oorspronkelijk)


if __name__ == '__main__':
    unittest.main()
