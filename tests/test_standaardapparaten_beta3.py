"""Tests voor merkonafhankelijke Windows-standaardselectie en neutrale UI."""
import logging
import shutil
import subprocess
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import Mock

from app.audio.windows_standaardapparaten import vind_wasapi_standaardapparaat
from app.audio.monitor_voor_eigen_headset import MonitorVoorEigenHeadset, MonitorFout
from app.webinterface.bediening_van_de_audiomotor import WebbedieningVanDrostSoundboard


class NepAudio:
    def __init__(self, default_input=2, default_output=3):
        self.default_input = default_input
        self.default_output = default_output
        self.apparaten = [
            {'name': 'CABLE Input (VB-Audio Virtual Cable)', 'hostapi': 0,
             'max_input_channels': 0, 'max_output_channels': 2},
            {'name': 'CABLE Output (VB-Audio Virtual Cable)', 'hostapi': 0,
             'max_input_channels': 2, 'max_output_channels': 0},
            {'name': 'Microfoon (Logitech Blue)', 'hostapi': 0,
             'max_input_channels': 1, 'max_output_channels': 0},
            {'name': 'Luidsprekers (Realtek USB Audio)', 'hostapi': 0,
             'max_input_channels': 0, 'max_output_channels': 2},
            {'name': 'Headset (SteelSeries)', 'hostapi': 0,
             'max_input_channels': 0, 'max_output_channels': 2},
            {'name': 'Microfoon (Razer)', 'hostapi': 0,
             'max_input_channels': 2, 'max_output_channels': 0},
            {'name': 'Speaker (oud)', 'hostapi': 1,
             'max_input_channels': 0, 'max_output_channels': 2},
        ]

    def query_devices(self):
        return self.apparaten

    def query_hostapis(self):
        return [
            {'name': 'Windows WASAPI', 'default_input_device': self.default_input,
             'default_output_device': self.default_output},
            {'name': 'Windows MME', 'default_input_device': -1,
             'default_output_device': 6},
        ]


class TestWindowsStandaardapparaten(unittest.TestCase):
    def setUp(self):
        self.audio = NepAudio()

    def test_merk_onafhankelijke_standaard_microfoon(self):
        self.assertEqual(
            vind_wasapi_standaardapparaat(self.audio.query_devices(),
                self.audio.query_hostapis(), 'invoer'),
            (2, 'Microfoon (Logitech Blue)'),
        )

    def test_merk_onafhankelijke_standaard_uitvoer(self):
        self.assertEqual(vind_wasapi_standaardapparaat(self.audio.query_devices(),
            self.audio.query_hostapis(), 'uitvoer'), (3, 'Luidsprekers (Realtek USB Audio)'))

    def test_eerste_of_razer_apparaat_krijgt_geen_voorkeur(self):
        self.audio.default_input = 5
        self.audio.default_output = 4
        self.assertEqual(vind_wasapi_standaardapparaat(self.audio.query_devices(),
            self.audio.query_hostapis(), 'invoer')[0], 5)
        self.assertEqual(vind_wasapi_standaardapparaat(self.audio.query_devices(),
            self.audio.query_hostapis(), 'uitvoer')[0], 4)

    def test_kabel_is_nooit_lokale_monitor_ook_als_windows_daarnaar_wijst(self):
        self.audio.default_output = 0
        self.assertIsNone(vind_wasapi_standaardapparaat(self.audio.query_devices(),
            self.audio.query_hostapis(), 'uitvoer'))
        self.audio.default_input = 1
        self.assertIsNone(vind_wasapi_standaardapparaat(self.audio.query_devices(),
            self.audio.query_hostapis(), 'invoer'))

    def test_geen_of_ongeldige_standaard_krijgt_geen_willekeurige_fallback(self):
        for nummer in (-1, 999, None, True, 6):
            with self.subTest(nummer=nummer):
                self.audio.default_output = nummer
                self.assertIsNone(vind_wasapi_standaardapparaat(
                    self.audio.query_devices(), self.audio.query_hostapis(), 'uitvoer'))

    def test_alleen_apparaten_uit_wasapi(self):
        self.audio.default_output = 6
        self.assertIsNone(vind_wasapi_standaardapparaat(
            self.audio.query_devices(), self.audio.query_hostapis(), 'uitvoer'))

    def test_verkeerde_richting_geeft_echte_programmeerfout(self):
        with self.assertRaisesRegex(ValueError, 'STANDAARD-001'):
            vind_wasapi_standaardapparaat([], [], 'iets')

    def test_handmatige_monitor_keuze_heeft_voorrang(self):
        monitor = MonitorVoorEigenHeadset(self.audio, Mock(spec=logging.Logger))
        monitor.kies_uitvoerapparaat(4)
        self.assertEqual(monitor._vind_geschikt_uitvoerapparaat()[0], 4)
        self.assertEqual(monitor.gekozen_apparaatnummer, 4)

    def test_automatische_monitor_weigert_virtuele_kabel(self):
        self.audio.default_output = 0
        monitor = MonitorVoorEigenHeadset(self.audio, Mock(spec=logging.Logger))
        with self.assertRaisesRegex(MonitorFout, 'MON-006'):
            monitor._vind_geschikt_uitvoerapparaat()

    def test_explicit_virtueel_apparaat_niet_toegestaan(self):
        monitor = MonitorVoorEigenHeadset(self.audio, Mock(spec=logging.Logger))
        monitor.kies_uitvoerapparaat(0)
        with self.assertRaisesRegex(MonitorFout, 'MON-001'):
            monitor._vind_geschikt_uitvoerapparaat()

    def test_webbediening_geeft_windows_microfoon_en_verifieert_wasapi(self):
        bediening = object.__new__(WebbedieningVanDrostSoundboard)
        bediening.audioapparaten = self.audio
        bediening.logboeken = SimpleNamespace(softwarelogboek=Mock(spec=logging.Logger))
        microfoons = [{'nummer': 2, 'naam': 'Microfoon (Logitech Blue)'},
                      {'nummer': 5, 'naam': 'Microfoon (Razer)'}]
        self.assertEqual(bediening.geef_standaard_microfoonnummer_voor_de_webpagina(microfoons), 2)
        self.audio.default_input = 0
        self.assertIsNone(bediening.geef_standaard_microfoonnummer_voor_de_webpagina(microfoons))
        self.audio.default_input = 2
        self.assertIsNone(bediening.geef_standaard_microfoonnummer_voor_de_webpagina([]))

    def test_javascript_keuze_en_handmatige_voorkeur(self):
        node = shutil.which('node')
        if node is None:
            self.skipTest('Node.js is niet beschikbaar in deze testomgeving.')
        js = Path(__file__).resolve().parent / 'hulpmiddelen' / 'test_standaardapparaten_beta3.js'
        resultaat = subprocess.run([node, str(js)], capture_output=True, text=True, timeout=12)
        self.assertEqual(resultaat.returncode, 0, resultaat.stdout + resultaat.stderr)
        self.assertIn('zes apparaatkeuze', resultaat.stdout)

    def test_dashboard_gebruikt_neutrale_strings_zonder_dubbele_status(self):
        pad = Path(__file__).resolve().parents[1] / 'app' / 'webinterface' / 'statisch'
        html = (pad / 'dashboard.html').read_text(encoding='utf-8')
        js = (pad / 'dashboard.js').read_text(encoding='utf-8')
        self.assertNotIn('id="badge-status"', html)
        self.assertNotIn('element("badge-status")', js)
        self.assertNotIn('Razer als beschikbaar', html + js)
        self.assertNotIn('includes("razer")', js)
        # Mapnamen mogen Discord bevatten; de apparaatkeuze mag dat niet afdwingen.
        begin = js.index('async function laadApparaten() {')
        apparaatscode = js[begin:].split('\n}\n', 1)[0]
        self.assertIn('antwoord.standaard_microfoonnummer', apparaatscode)
        self.assertNotIn('Discord', apparaatscode)
        self.assertNotIn('WhatsApp', html + js)
        self.assertNotIn('Naar call', html + js)
        self.assertIn('standaard_microfoonnummer', js)
        self.assertIn('Windows-standaard', js)
        self.assertIn('alleen lokaal', js)


if __name__ == '__main__':
    unittest.main()
