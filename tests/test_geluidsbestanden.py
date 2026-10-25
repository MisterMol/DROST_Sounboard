"""Test conversie en foutafhandeling van echte WAV-bestanden zonder hardware."""

from pathlib import Path
import struct
from tempfile import TemporaryDirectory
import unittest
import wave

import numpy as np

from app.audio.geluidsbestanden import (
    GeluidsbestandOngeldigFout,
    _zet_pcm_samples_om_naar_float32,
    lees_en_bereid_wav_geluid_voor,
    MAXIMALE_BESTANDSGROOTTE_IN_BYTES,
)


class TestGeluidenInlezen(unittest.TestCase):
    def setUp(self):
        self.tijdelijke_map = TemporaryDirectory()
        self.map = Path(self.tijdelijke_map.name)

    def tearDown(self):
        self.tijdelijke_map.cleanup()

    def maak_een_testwav(
        self, naam="geluid.wav", aantal_kanalen=1, samplefrequentie=48000,
        aantal_bytes_per_sample=2, duur_frames=960,
    ) -> Path:
        pad = self.map / naam
        with wave.open(str(pad), "wb") as testbestand:
            testbestand.setnchannels(aantal_kanalen)
            testbestand.setsampwidth(aantal_bytes_per_sample)
            testbestand.setframerate(samplefrequentie)
            per_sample = (0).to_bytes(aantal_bytes_per_sample, "little", signed=False)
            testbestand.writeframes(per_sample * aantal_kanalen * duur_frames)
        return pad

    def test_kort_mono_wav_wordt_float32_stereo(self):
        bestand = self.maak_een_testwav()
        geluid = lees_en_bereid_wav_geluid_voor(bestand)
        self.assertEqual(geluid.aantal_frames, 960)
        self.assertEqual(len(geluid.ruwe_float32_stereo_audio), 960 * 2 * 4)
        self.assertEqual(geluid.naam_van_het_geluid, "geluid")
        self.assertAlmostEqual(geluid.duur_in_seconden, 0.02)
        self.assertEqual(len(geluid.vingerafdruk_van_audio), 64)

    def test_wav_van_44100_wordt_netjes_omgerekend_naar_48000(self):
        bestand = self.maak_een_testwav(samplefrequentie=44100, duur_frames=4410)
        geluid = lees_en_bereid_wav_geluid_voor(bestand)
        self.assertEqual(geluid.aantal_frames, 4800)
        self.assertEqual(geluid.oorspronkelijke_samplefrequentie, 44100)

    def test_24_bit_negatieve_waarde_wordt_negatief(self):
        samples = _zet_pcm_samples_om_naar_float32(
            bytes([0, 0, 0x80, 0xFF, 0xFF, 0x7F]), 3
        )
        self.assertAlmostEqual(float(samples[0]), -1.0)
        self.assertAlmostEqual(float(samples[1]), 1.0, places=5)

    def test_8_bit_is_unsigned(self):
        samples = _zet_pcm_samples_om_naar_float32(bytes([0, 128, 255]), 1)
        self.assertEqual(float(samples[0]), -1.0)
        self.assertEqual(float(samples[1]), 0.0)
        self.assertGreater(float(samples[2]), 0.99)

    def test_32_bit_wordt_bruikbaar_float(self):
        audio = struct.pack("<iii", -2147483648, 0, 2147483647)
        uitkomst = _zet_pcm_samples_om_naar_float32(audio, 4)
        self.assertAlmostEqual(float(uitkomst[0]), -1.0)
        self.assertEqual(float(uitkomst[1]), 0)
        self.assertAlmostEqual(float(uitkomst[2]), 1.0)

    def test_lege_of_verkeerde_bestandsparameters_geven_duidelijke_codes(self):
        for waarde, code in [(None, "GELUID-001"), ("", "GELUID-002"), (9, "GELUID-001")]:
            with self.subTest(waarde=waarde), self.assertRaisesRegex(GeluidsbestandOngeldigFout, code):
                lees_en_bereid_wav_geluid_voor(waarde)
        with self.assertRaisesRegex(GeluidsbestandOngeldigFout, "GELUID-003"):
            lees_en_bereid_wav_geluid_voor("geluid.mp3")
        with self.assertRaisesRegex(GeluidsbestandOngeldigFout, "GELUID-004"):
            lees_en_bereid_wav_geluid_voor(self.map / "bestaat_niet.wav")

    def test_volume_null_nan_oneindig_boolean_wordt_geweigerd(self):
        for waarde in (None, True, float("nan"), float("inf"), 2.1, -0.1):
            with self.subTest(waarde=waarde), self.assertRaises(GeluidsbestandOngeldigFout):
                lees_en_bereid_wav_geluid_voor(self.maak_een_testwav(), ingesteld_volume=waarde)

    def test_stil_geluidsbestand_met_foutieve_header_wordt_geweigerd(self):
        pad = self.map / "kapot.wav"
        pad.write_bytes(b"geen_wav")
        with self.assertRaisesRegex(GeluidsbestandOngeldigFout, "GELUID-019"):
            lees_en_bereid_wav_geluid_voor(pad)

    def test_bestand_langer_dan_maximum_geeft_fout(self):
        pad = self.maak_een_testwav(samplefrequentie=8000, duur_frames=121 * 8000)
        with self.assertRaisesRegex(GeluidsbestandOngeldigFout, "GELUID-017"):
            lees_en_bereid_wav_geluid_voor(pad)

    def test_driekanaals_bestand_wordt_geweigerd(self):
        pad = self.maak_een_testwav(aantal_kanalen=3)
        with self.assertRaisesRegex(GeluidsbestandOngeldigFout, "GELUID-013"):
            lees_en_bereid_wav_geluid_voor(pad)

    def test_te_groot_bestand_wordt_vooraf_geweigerd(self):
        pad = self.map / "groot.wav"
        with pad.open("wb") as bestand:
            bestand.truncate(MAXIMALE_BESTANDSGROOTTE_IN_BYTES + 1)
        with self.assertRaisesRegex(GeluidsbestandOngeldigFout, "GELUID-006"):
            lees_en_bereid_wav_geluid_voor(pad)

    def test_mono_en_stereo_kanalen_worden_correct_gekoppeld(self):
        pad = self.map / "stereo.wav"
        with wave.open(str(pad), "wb") as bestand:
            bestand.setnchannels(2)
            bestand.setsampwidth(2)
            bestand.setframerate(48000)
            bestand.writeframes(struct.pack("<hhhh", 10000, -10000, 20000, -20000))
        geluid = lees_en_bereid_wav_geluid_voor(pad, ingesteld_volume=1)
        arrays = np.frombuffer(geluid.ruwe_float32_stereo_audio, dtype="<f4").reshape(-1, 2)
        self.assertGreater(float(arrays[0, 0]), 0)
        self.assertLess(float(arrays[0, 1]), 0)


if __name__ == "__main__":
    unittest.main()
