"""Controleer de zelfgemaakte testtoon zonder aangesloten audiohardware."""

import struct
import unittest

from app.audio.testtoon import (
    InstellingenVoorTesttoon,
    maak_testtoon_voor_de_virtuele_kabel,
    verdeel_testtoon_in_kleine_audio_blokken,
)


class TestTesttoon(unittest.TestCase):
    def test_stereo_float32_heeft_het_gevraagde_aantal_bytes(self):
        instellingen = InstellingenVoorTesttoon(duur_in_seconden=0.1)
        toon = maak_testtoon_voor_de_virtuele_kabel(instellingen)
        self.assertEqual(len(toon), 48_000 // 10 * 2 * 4)

    def test_stereo_kanalen_zijn_gelijk(self):
        toon = maak_testtoon_voor_de_virtuele_kabel(
            InstellingenVoorTesttoon(duur_in_seconden=0.1)
        )
        for links, rechts in struct.iter_unpack("<ff", toon):
            self.assertAlmostEqual(links, rechts)

    def test_fade_stopt_op_nul(self):
        toon = maak_testtoon_voor_de_virtuele_kabel(
            InstellingenVoorTesttoon(duur_in_seconden=0.1)
        )
        laatste_sample = struct.unpack_from("<f", toon, len(toon) - 4)[0]
        self.assertAlmostEqual(laatste_sample, 0.0)

    def test_volume_mag_niet_te_hoog_zijn(self):
        with self.assertRaisesRegex(ValueError, "TOON-005"):
            maak_testtoon_voor_de_virtuele_kabel(
                InstellingenVoorTesttoon(volume=0.99)
            )

    def test_blokken_geven_exact_het_originele_signaal_terug(self):
        toon = maak_testtoon_voor_de_virtuele_kabel(
            InstellingenVoorTesttoon(duur_in_seconden=0.13)
        )
        blokken = list(verdeel_testtoon_in_kleine_audio_blokken(toon))
        self.assertEqual(b"".join(blokken), toon)
        self.assertTrue(all(len(blok) % 8 == 0 for blok in blokken))

    def test_onvolledige_frames_worden_geweigerd(self):
        with self.assertRaisesRegex(ValueError, "TOON-009"):
            list(verdeel_testtoon_in_kleine_audio_blokken(b"abc"))


if __name__ == "__main__":
    unittest.main()
