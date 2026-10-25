"""Controleer dat de kabeltest de eigen toon van andere geluiden kan scheiden."""

import struct
import unittest

from app.audio.signaalherkenning import HerkennerVoorEenVasteToon
from app.audio.testtoon import (
    InstellingenVoorTesttoon,
    maak_testtoon_voor_de_virtuele_kabel,
)


class TestHerkennenVanEenSpecifiekeToon(unittest.TestCase):
    def test_herkent_de_ingebouwde_440_hertz_toon(self):
        herkenner = HerkennerVoorEenVasteToon(48_000, 440)
        geluid = maak_testtoon_voor_de_virtuele_kabel(
            InstellingenVoorTesttoon(duur_in_seconden=0.1)
        )
        herkenner.verwerk_nieuw_audioblok(geluid)
        self.assertGreater(herkenner.bereken_sterkte_van_de_herkende_toon(), 0.05)

    def test_herkent_stilte_niet_als_de_testtoon(self):
        herkenner = HerkennerVoorEenVasteToon(48_000, 440)
        herkenner.verwerk_nieuw_audioblok(bytes(48_000 // 10 * 8))
        self.assertEqual(herkenner.bereken_sterkte_van_de_herkende_toon(), 0.0)

    def test_andere_frequentie_telt_niet_als_de_eigen_toon(self):
        herkenner = HerkennerVoorEenVasteToon(48_000, 1000)
        geluid = maak_testtoon_voor_de_virtuele_kabel(
            InstellingenVoorTesttoon(duur_in_seconden=0.1)
        )
        herkenner.verwerk_nieuw_audioblok(geluid)
        self.assertLess(herkenner.bereken_sterkte_van_de_herkende_toon(), 0.001)

    def test_onvolledige_stereo_frames_krijgen_een_foutcode(self):
        herkenner = HerkennerVoorEenVasteToon(48_000, 440)
        with self.assertRaisesRegex(ValueError, "TOON-010"):
            herkenner.verwerk_nieuw_audioblok(struct.pack("<f", 0.0))


if __name__ == "__main__":
    unittest.main()
