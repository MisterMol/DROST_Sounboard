"""Bescherm het doorlopende controlebestand tegen onbedoelde stilte of volumeproblemen."""

from __future__ import annotations

from pathlib import Path
import unittest
import wave
import numpy as np

from app.audio.geluidsbestanden import lees_en_bereid_wav_geluid_voor
from app.audio.kabel_ontvangstmeting import meet_signaal_en_herken_controletoon


BESTAND = Path(__file__).resolve().parents[1] / "voorbeelden" / "controletoon_12seconden.wav"


class TestHetDuidelijkeControlebestand(unittest.TestCase):
    def test_controletoon_duurt_twaalf_seconden_en_is_een_normale_wav(self):
        with wave.open(str(BESTAND), "rb") as bestand:
            self.assertEqual(bestand.getframerate(), 48_000)
            self.assertEqual(bestand.getnchannels(), 1)
            self.assertEqual(bestand.getnframes(), 48_000 * 12)

    def test_na_de_standaard_volumeinstelling_is_660_hertz_goed_herkenbaar(self):
        voorbereid = lees_en_bereid_wav_geluid_voor(BESTAND)
        frames = np.frombuffer(voorbereid.ruwe_float32_stereo_audio, dtype=np.float32)
        stereo = frames.reshape(-1, 2)
        midden = stereo[2 * 48_000 : 2 * 48_000 + 4800]
        meting = meet_signaal_en_herken_controletoon(midden)
        self.assertGreater(meting.effectieve_sterkte, .06)
        self.assertTrue(meting.controletoon_herkend)


if __name__ == "__main__":
    unittest.main()
