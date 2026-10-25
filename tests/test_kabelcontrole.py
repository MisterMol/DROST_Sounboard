"""Controleer apparaatkeuze en signaalmeting zonder echte drivers te openen."""

import struct
import unittest

from app.audio.apparatenbeheer import GevondenAudioapparaat
from app.audio.kabelcontrole import (
    KabelcontroleFout,
    bereken_signaalsterkte_van_ruwe_audio,
    selecteer_de_twee_uiteinden_van_vb_cable,
)


def voorbeeldapparaat(nummer, naam, api, invoer, uitvoer):
    return GevondenAudioapparaat(nummer, naam, api, invoer, uitvoer)


class TestKabelcontrole(unittest.TestCase):
    def setUp(self):
        self.apparaten = [
            voorbeeldapparaat(7, "CABLE Input (VB-Audio Virtual C", "MME", 0, 16),
            voorbeeldapparaat(20, "CABLE In 16ch (VB-Audio Virtual Cable)", "Windows WASAPI", 0, 2),
            voorbeeldapparaat(21, "CABLE Input (VB-Audio Virtual Cable)", "Windows WASAPI", 0, 2),
            voorbeeldapparaat(23, "CABLE Output (VB-Audio Virtual Cable)", "Windows WASAPI", 2, 0),
            voorbeeldapparaat(24, "Microfoon (Razer USB Sound Card)", "Windows WASAPI", 2, 0),
        ]

    def test_selectie_gebruikt_wasapi_en_geen_vaste_nummers(self):
        selectie = selecteer_de_twee_uiteinden_van_vb_cable(self.apparaten)
        self.assertEqual(selectie.afspeelkant.huidig_apparaatnummer, 21)
        self.assertEqual(selectie.opnamekant.huidig_apparaatnummer, 23)

    def test_selectie_weigert_ontbrekende_kabel(self):
        with self.assertRaisesRegex(KabelcontroleFout, "KABEL-002"):
            selecteer_de_twee_uiteinden_van_vb_cable(self.apparaten[:2])

    def test_selectie_weigert_dubbele_kabel_om_verkeerd_routen_te_voorkomen(self):
        met_dubbele_kabel = self.apparaten + [self.apparaten[2]]
        with self.assertRaisesRegex(KabelcontroleFout, "KABEL-002"):
            selecteer_de_twee_uiteinden_van_vb_cable(met_dubbele_kabel)

    def test_selectie_vereist_een_lijst(self):
        with self.assertRaisesRegex(TypeError, "KABEL-001"):
            selecteer_de_twee_uiteinden_van_vb_cable(None)

    def test_signaalsterkte_is_controleerbaar(self):
        gegevens = struct.pack("<ffff", -0.25, 0.25, 0.0, 0.5)
        aantal, piek, som_kwadraten = bereken_signaalsterkte_van_ruwe_audio(gegevens)
        self.assertEqual(aantal, 4)
        self.assertAlmostEqual(piek, 0.5)
        self.assertAlmostEqual(som_kwadraten, 0.375)

    def test_signaalmeting_weigert_onvolledige_sample(self):
        with self.assertRaisesRegex(ValueError, "KABEL-003"):
            bereken_signaalsterkte_van_ruwe_audio(b"a")

    def test_signaalmeting_weigert_nan(self):
        with self.assertRaisesRegex(ValueError, "KABEL-004"):
            bereken_signaalsterkte_van_ruwe_audio(struct.pack("<f", float("nan")))


if __name__ == "__main__":
    unittest.main()
