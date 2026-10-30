"""Regressies voor de live tijdlijn, herhalen en automatische microfoonkeuze.

Alle audiosamples zijn synthetisch: deze tests hebben geen Windows-driver nodig.
"""
from __future__ import annotations

import logging
import shutil
import subprocess
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch
from uuid import uuid4
import unittest
import math

import numpy as np

from app.audio.geluidsbestanden import VoorbereidGeluidsfragment
from app.audio.live_audiomixer import LiveAudiomixer, LiveVerbindingFout
from app.webinterface.bediening_van_de_audiomotor import WebbedieningVanDrostSoundboard, OngeldigeWebactie


def maak_clip(frames=1000):
    # Een stabiele niet-nul bron, zodat looping zonder gaten zichtbaar wordt.
    samples = np.full((frames, 2), .2, dtype=np.float32)
    return VoorbereidGeluidsfragment(
        naam_van_het_geluid='Test', bestandspad=Path('test.wav'),
        vingerafdruk_van_audio='testhash', ruwe_float32_stereo_audio=samples.tobytes(),
        aantal_frames=frames, oorspronkelijke_samplefrequentie=48000,
        oorspronkelijke_aantal_kanalen=2, ingesteld_volume=1.0,
    )


class TestLiveSpeler647(unittest.TestCase):
    def setUp(self):
        self.mixer = LiveAudiomixer(Mock(), Mock(spec=logging.Logger), Mock(spec=logging.Logger))
        self.mixer._toestand = 'verbonden'
        self.mixer._geluidseffecten_ingeschakeld = True

    def begin(self, frames=1000):
        nummer = self.mixer.speel_een_voorbereid_geluid(maak_clip(frames), geluid_id='geluid-x')
        self.mixer._voer_wachtende_opdrachten_uit()
        self.assertEqual(self.mixer.geef_huidige_status().afspeelbeurt_id, nummer)
        return nummer

    def test_seek_bedient_alleen_de_juiste_afspeelbeurt(self):
        nummer = self.begin(48000)
        self.mixer.zoek_in_lopend_geluid(str(uuid4()), .75)
        self.mixer._voer_wachtende_opdrachten_uit()
        self.assertEqual(self.mixer.geef_huidige_status().afgespeelde_seconden, 0)
        self.mixer.zoek_in_lopend_geluid(nummer, .5)
        self.mixer._voer_wachtende_opdrachten_uit()
        status = self.mixer.geef_huidige_status()
        self.assertAlmostEqual(status.afgespeelde_seconden, .5, places=4)
        self.assertEqual(status.positie_wijzigingsnummer, 1)
        self.assertEqual(status.toestand, 'verbonden')

    def test_herhalen_vult_het_hele_audioblok_en_kan_worden_uitgezet(self):
        nummer = self.begin(800)
        self.mixer.stel_lopend_geluid_herhalen_in(nummer, True)
        self.mixer._voer_wachtende_opdrachten_uit()
        self.assertTrue(self.mixer.geef_huidige_status().live_herhalen)
        buffer = np.zeros((4800, 2), dtype=np.float32)
        self.mixer._verwerk_het_lopende_geluid_in_het_audioblok(buffer)
        self.assertIsNotNone(self.mixer._huidige_geluid)
        self.assertGreater(float(np.count_nonzero(buffer)), len(buffer))
        self.assertEqual(self.mixer.geef_huidige_status().positie_wijzigingsnummer, 6)
        self.mixer.stel_lopend_geluid_herhalen_in(nummer, False)
        self.mixer._voer_wachtende_opdrachten_uit()
        self.assertFalse(self.mixer.geef_huidige_status().live_herhalen)
        self.mixer._verwerk_het_lopende_geluid_in_het_audioblok(np.zeros_like(buffer))
        self.assertIsNone(self.mixer._huidige_geluid)
        self.assertEqual(self.mixer.geef_huidige_status().toestand, 'verbonden')

    def test_verouderde_loopopdracht_verandert_nieuwe_clip_niet(self):
        oud = self.begin(1200)
        nieuw = self.begin(1200)
        self.mixer.stel_lopend_geluid_herhalen_in(oud, True)
        self.mixer._voer_wachtende_opdrachten_uit()
        self.assertEqual(self.mixer.geef_huidige_status().afspeelbeurt_id, nieuw)
        self.assertFalse(self.mixer.geef_huidige_status().live_herhalen)

    def test_ongeldige_seek_en_herhaal_worden_geweigerd(self):
        nummer = self.begin()
        for waarde in (float('nan'), math.inf, -1, 1.3, True):
            with self.subTest(waarde=waarde), self.assertRaises(LiveVerbindingFout):
                self.mixer.zoek_in_lopend_geluid(nummer, waarde)
        with self.assertRaises(LiveVerbindingFout):
            self.mixer.stel_lopend_geluid_herhalen_in(nummer, 1)

    def test_webactie_is_gebonden_aan_de_huidige_afspeelbeurt(self):
        nummer = self.begin(48000)
        bediening = object.__new__(WebbedieningVanDrostSoundboard)
        bediening.mixer = self.mixer
        bediening.bedien_lopend_geluid(nummer, fractie=.2)
        self.mixer._voer_wachtende_opdrachten_uit()
        self.assertAlmostEqual(self.mixer.geef_huidige_status().afgespeelde_seconden, .2, places=4)
        with self.assertRaisesRegex(OngeldigeWebactie, 'SPELER-001'):
            bediening.bedien_lopend_geluid(str(uuid4()), fractie=.9)
        with self.assertRaisesRegex(OngeldigeWebactie, 'SPELER-003'):
            bediening.bedien_lopend_geluid(nummer, fractie='0.2')

    @unittest.skipUnless(shutil.which('node'), 'Node.js niet beschikbaar')
    def test_javascript_live_spelerbediening(self):
        pad = Path(__file__).resolve().parent / 'hulpmiddelen' / 'test_live_speler_beta647.js'
        resultaat = subprocess.run(['node', str(pad)], capture_output=True, text=True, timeout=15)
        self.assertEqual(resultaat.returncode, 0, resultaat.stdout + resultaat.stderr)
        self.assertIn('live seek, herhalen', resultaat.stdout)

    def test_standaard_microfoon_enkele_fallback_of_geen_keuze(self):
        bediening = object.__new__(WebbedieningVanDrostSoundboard)
        bediening.audioapparaten = Mock()
        bediening.logboeken = SimpleNamespace(softwarelogboek=Mock())
        met_een = [{'nummer': 8, 'naam': 'Microfoon (Logitech)'}]
        met_twee = met_een + [{'nummer': 17, 'naam': 'Microfoon (USB)'}]
        with patch('app.webinterface.bediening_van_de_audiomotor.vind_wasapi_standaardapparaat', return_value=None):
            self.assertEqual(bediening.geef_standaard_microfoonnummer_voor_de_webpagina(met_een), 8)
            self.assertIsNone(bediening.geef_standaard_microfoonnummer_voor_de_webpagina(met_twee))
        with patch('app.webinterface.bediening_van_de_audiomotor.vind_wasapi_standaardapparaat', return_value=(17, 'Microfoon (USB)')):
            self.assertEqual(bediening.geef_standaard_microfoonnummer_voor_de_webpagina(met_twee), 17)


if __name__ == '__main__':
    unittest.main()
