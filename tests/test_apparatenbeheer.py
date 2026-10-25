"""Test apparaatcontrole zonder echte Windows-audioapparaten te openen."""

import logging
import unittest

from app.audio.apparatenbeheer import maak_veilig_overzicht_van_audioapparaten


class TestGeluidsapparaten(unittest.TestCase):
    def setUp(self):
        self.logboek = logging.getLogger("test.audio")
        self.logboek.addHandler(logging.NullHandler())
        self.logboek.propagate = False
        self.hostapis = [{"name": "Windows WASAPI"}]

    def test_de_virtuale_kabel_wordt_aan_beide_kanten_herkend(self):
        apparaten = [
            {"name": "CABLE Input (VB-Audio Virtual Cable)", "hostapi": 0, "max_input_channels": 0, "max_output_channels": 2},
            {"name": "CABLE Output (VB-Audio Virtual Cable)", "hostapi": 0, "max_input_channels": 2, "max_output_channels": 0},
            {"name": "Microfoon (Razer USB Sound Card)", "hostapi": 0, "max_input_channels": 1, "max_output_channels": 0},
        ]
        resultaat = maak_veilig_overzicht_van_audioapparaten(apparaten, self.hostapis, self.logboek)
        self.assertTrue(resultaat.cable_input_aanwezig)
        self.assertTrue(resultaat.cable_output_aanwezig)
        self.assertTrue(resultaat.fysieke_microfoon_mogelijk_aanwezig)

    def test_onverwachte_null_en_verkeerd_type_worden_niet_gezien_als_apparaat(self):
        apparaten = [
            None,
            {"name": "Fout apparaat", "hostapi": 0, "max_input_channels": None, "max_output_channels": 2},
            {"name": "Luidspreker", "hostapi": 0, "max_input_channels": 0, "max_output_channels": 2},
        ]
        resultaat = maak_veilig_overzicht_van_audioapparaten(apparaten, self.hostapis, self.logboek)
        self.assertEqual(len(resultaat.apparaten), 1)
        self.assertEqual(resultaat.apparaten[0].naam, "Luidspreker")

    def test_extra_gegevens_die_de_driver_zelf_teruggeeft_zijn_geen_fout(self):
        # Driverobjecten mogen eigen velden hebben. Strikte onbekende-veld-
        # controle is wel nodig bij onze eigen JavaScript-API, niet hier.
        apparaten = [
            {"name": "Microfoon", "hostapi": 0, "max_input_channels": 1, "max_output_channels": 0, "default_samplerate": 48000.0},
        ]
        resultaat = maak_veilig_overzicht_van_audioapparaten(apparaten, self.hostapis, self.logboek)
        self.assertEqual(resultaat.apparaten[0].aantal_invoerkanalen, 1)


if __name__ == "__main__":
    unittest.main()
