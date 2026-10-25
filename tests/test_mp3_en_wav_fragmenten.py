"""Controleer echte MP3-decodering en foutgevallen zonder microfoon of VB-CABLE."""

from pathlib import Path
from tempfile import TemporaryDirectory
import math
import unittest
import wave

import numpy as np
import soundfile as sf

from app.audio.geluidsbestanden import GeluidsbestandOngeldigFout
from app.audio.mp3_en_wav_fragmenten import (
    controleer_of_geluidsbestand_gebruikt_mag_worden,
    lees_en_bereid_mp3_of_wav_voor,
)


class TestEchteMp3EnWavFragmenten(unittest.TestCase):
    def setUp(self):
        self.tijdelijke_map = TemporaryDirectory()
        self.map = Path(self.tijdelijke_map.name)

    def tearDown(self):
        self.tijdelijke_map.cleanup()

    def maak_kort_mp3_met_testtoon(self, samplefrequentie=44100):
        pad = self.map / "muziek met spaties (1).mp3"
        tijd = np.arange(samplefrequentie // 2, dtype=np.float64) / samplefrequentie
        testtoon = (np.sin(2 * np.pi * 660 * tijd) * .25).astype("float32")
        sf.write(pad, testtoon, samplefrequentie, format="MP3")
        return pad

    def test_echte_mp3_wordt_stereo_float32_op_48000_hz(self):
        bestand = self.maak_kort_mp3_met_testtoon()
        resultaat = lees_en_bereid_mp3_of_wav_voor(bestand)
        frames = np.frombuffer(resultaat.ruwe_float32_stereo_audio, dtype="<f4").reshape((-1, 2))
        self.assertEqual(frames.shape[1], 2)
        self.assertEqual(resultaat.oorspronkelijke_samplefrequentie, 44100)
        self.assertEqual(resultaat.oorspronkelijke_aantal_kanalen, 1)
        self.assertAlmostEqual(resultaat.duur_in_seconden, .5, places=2)
        self.assertGreater(float(np.sqrt(np.mean(frames[:, 0] ** 2))), 0.01)
        self.assertTrue(np.allclose(frames[:, 0], frames[:, 1]))
        self.assertEqual(len(resultaat.vingerafdruk_van_audio), 64)
        self.assertEqual(resultaat.fragment_begint_bij_seconden, 0.0)

    def test_wav_startpunt_bij_einde_leest_alleen_benodigde_frames(self):
        bestand = self.map / "lang met beginpositie.wav"
        sf.write(bestand, np.zeros(48000 * 3, dtype="float32"), 48000)
        geluid = lees_en_bereid_mp3_of_wav_voor(bestand, beginpositie_seconden=2.25)
        self.assertAlmostEqual(geluid.duur_in_seconden, .75, places=2)
        self.assertAlmostEqual(geluid.bronduur_in_seconden, 3)
        self.assertFalse(geluid.fragment_ingekort)

    def test_lange_wav_wordt_zichtbaar_teruggebracht_tot_aangevraagde_duur(self):
        bestand = self.map / "lang.wav"
        # Dit is maar ~700 KB op schijf omdat het 8 kHz 16-bit mono is.
        sf.write(bestand, np.zeros(50 * 8000, dtype="float32"), 8000)
        geluid = lees_en_bereid_mp3_of_wav_voor(bestand, maximale_duur_seconden=25)
        self.assertEqual(geluid.aantal_frames, 25 * 48000)
        self.assertTrue(geluid.fragment_ingekort)
        self.assertEqual(geluid.bronduur_in_seconden, 50.0)

    def test_een_lang_fragment_heeft_een_harde_grens_van_twee_minuten(self):
        bestand = self.map / "121 seconden.wav"
        sf.write(bestand, np.zeros(121 * 8000, dtype="float32"), 8000)
        geluid = lees_en_bereid_mp3_of_wav_voor(bestand, maximale_duur_seconden=120)
        self.assertEqual(geluid.aantal_frames, 120 * 48000)
        self.assertEqual(geluid.duur_in_seconden, 120)
        self.assertTrue(geluid.fragment_ingekort)
        with self.assertRaisesRegex(GeluidsbestandOngeldigFout, "GELUID-037"):
            lees_en_bereid_mp3_of_wav_voor(bestand, maximale_duur_seconden=121)

    def test_mp3_met_instelbaar_startpunt(self):
        bestand = self.maak_kort_mp3_met_testtoon()
        geluid = lees_en_bereid_mp3_of_wav_voor(bestand, beginpositie_seconden=.25)
        self.assertAlmostEqual(geluid.duur_in_seconden, .25, places=2)
        self.assertEqual(geluid.fragment_begint_bij_seconden, .25)

    def test_mp3_is_kapot_en_originale_decoderfout_blijft_in_de_keten(self):
        bestand = self.map / "niet_echt.mp3"
        bestand.write_bytes(b"dit is geen mp3")
        with self.assertRaisesRegex(GeluidsbestandOngeldigFout, "GELUID-034") as fout:
            lees_en_bereid_mp3_of_wav_voor(bestand)
        self.assertIsNotNone(fout.exception.__cause__)

    def test_verkeerde_paden_en_null_geeft_de_juiste_foutcode(self):
        for waarde, verwachte_code in [
            (None, "GELUID-020"), ("", "GELUID-021"),
            ("test.ogg", "GELUID-022"), ("bestaat-niet.mp3", "GELUID-023"),
        ]:
            with self.subTest(waarde=waarde), self.assertRaisesRegex(
                GeluidsbestandOngeldigFout, verwachte_code
            ):
                controleer_of_geluidsbestand_gebruikt_mag_worden(waarde)

    def test_beginpositie_mag_niet_null_nan_of_negatief_zijn(self):
        pad = self.maak_kort_mp3_met_testtoon()
        for waarde in (None, True, float("nan"), float("inf"), -2):
            with self.subTest(waarde=waarde), self.assertRaises(GeluidsbestandOngeldigFout):
                lees_en_bereid_mp3_of_wav_voor(pad, beginpositie_seconden=waarde)
        with self.assertRaisesRegex(GeluidsbestandOngeldigFout, "GELUID-033"):
            lees_en_bereid_mp3_of_wav_voor(pad, beginpositie_seconden=999)

    def test_volume_mag_niet_te_hoog_of_onjuist_zijn(self):
        pad = self.maak_kort_mp3_met_testtoon()
        for waarde in (None, True, float("nan"), float("inf"), -1, 2.5):
            with self.subTest(waarde=waarde), self.assertRaises(GeluidsbestandOngeldigFout):
                lees_en_bereid_mp3_of_wav_voor(pad, ingesteld_volume=waarde)

    def test_lege_mp3_wordt_voor_decode_geweigerd(self):
        pad = self.map / "leeg.mp3"
        pad.touch()
        with self.assertRaisesRegex(GeluidsbestandOngeldigFout, "GELUID-024"):
            lees_en_bereid_mp3_of_wav_voor(pad)


if __name__ == "__main__":
    unittest.main()
