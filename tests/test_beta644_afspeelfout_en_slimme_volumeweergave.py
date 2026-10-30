"""Regressietests: echte geluidstart, masterdemping en rustige UI-polling."""
from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from unittest import TestCase
from unittest.mock import MagicMock, patch
import logging
import tempfile

import numpy as np

from app.audio.geluidsbestanden import VoorbereidGeluidsfragment
from app.audio.live_audiomixer import LiveAudiomixer, _LopendGeluidsfragment, _meet_effect_rms_zonder_audio_te_onderbreken
from app.diagnostiek.logboek import BeschikbareLogboeken
from app.webinterface.bediening_van_de_audiomotor import WebbedieningVanDrostSoundboard
from app.webinterface.favorieten_en_instellingen import VasteFavorietenEnInstellingen


class TestGeluidStartZonderOntbrekendeTeller(TestCase):
    """Deze fout ontstond in de decode-werkdraad, niet tijdens de HTTP-aanvraag."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        pad = Path(self.tmp.name) / 'database.sqlite3'
        logger = MagicMock(spec=logging.Logger)
        logs = BeschikbareLogboeken(logger, logger, Path(self.tmp.name), 'test')
        self.service = WebbedieningVanDrostSoundboard(MagicMock(), logs, pad)
        self.addCleanup(self.service.sluit_alle_audio_af)
        self.item = SimpleNamespace(
            geluid_id='test-audio', eigen_naam='Voorbeeld',
            bestandspad=Path(self.tmp.name) / 'voorbeeld.wav',
        )
        self.settings = SimpleNamespace(
            begint_bij_seconden=0, volume=1.0,
            maximale_duur_seconden=5,
        )
        self.prepared = MagicMock()
        self.prepared.normalisatiefactor = 1.0
        self.prepared.normalisatiestand = 'uit'
        self.service._volgnummer_van_voorbereiden = 1
        self.service._wordt_voorbereid = self.item.eigen_naam

    @patch('app.webinterface.bediening_van_de_audiomotor.lees_en_bereid_mp3_of_wav_voor')
    @patch('app.webinterface.bediening_van_de_audiomotor.replace')
    def test_voltooide_start_werkt_ook_zonder_afspeelaantallen_variabele(self, vervang, lees):
        lees.return_value = self.prepared
        vervang.return_value = self.prepared
        with patch.object(self.service.mixer, 'geef_huidige_status', return_value=SimpleNamespace(
             toestand='verbonden', geluidseffecten_aan=True)), patch.object(
                 self.service.mixer, 'speel_een_voorbereid_geluid', return_value='beurt1') as start, patch.object(
                 self.service.recent_en_weergave, 'registreer_afspelen') as historie:
            self.service._bereid_geluid_voor_en_start_als_het_nog_mag(
                1, self.item, self.settings, 'uit')
        start.assert_called_once()
        historie.assert_called_once_with('test-audio', 'Voorbeeld', 'gesprek', 'beurt1')
        self.assertIsNone(self.service._laatste_afspeelfout)
        self.assertIsNone(self.service._wordt_voorbereid)

    @patch('app.webinterface.bediening_van_de_audiomotor.lees_en_bereid_mp3_of_wav_voor')
    @patch('app.webinterface.bediening_van_de_audiomotor.replace')
    def test_geweigerde_start_heeft_geen_ontbrekende_teller(self, vervang, lees):
        vervang.return_value = self.prepared
        with patch.object(self.service.mixer, 'geef_huidige_status', return_value=SimpleNamespace(
             toestand='verbroken', geluidseffecten_aan=False)):
            self.service._bereid_geluid_voor_en_start_als_het_nog_mag(
                1, self.item, self.settings, 'uit')
        self.assertIsNone(self.service._laatste_afspeelfout)
        self.assertIsNone(self.service._wordt_voorbereid)


class TestSoundboardDemping(TestCase):
    def test_standaard_75_behoudt_opgeslagen_100(self):
        with tempfile.TemporaryDirectory() as mapnaam:
            pad = Path(mapnaam) / 'lib.sqlite3'
            obj = VasteFavorietenEnInstellingen(pad)
            self.assertEqual(obj.geef_algemeen_effectvolume(),75)
            obj.bewaar_algemeen_effectvolume(100)
            self.assertEqual(VasteFavorietenEnInstellingen(pad).geef_algemeen_effectvolume(),100)

    def test_werkelijk_effectniveau_voor_en_na_kleiner_en_microfoon_hetzelfde(self):
        mixer = LiveAudiomixer(MagicMock(), MagicMock(spec=logging.Logger),
                               MagicMock(spec=logging.Logger))
        mixer._toestand = 'verbonden'  # Gesimuleerde stream, geen audiodevice geopend.
        mixer._geluidseffecten_ingeschakeld = True
        mic = np.full((480, 1), .1, dtype=np.float32)
        mixer.stel_algemeen_effectvolume_in(75)
        # Maak de volumestand actueel voordat de clip begint.
        leeg = np.zeros((480, 2), dtype=np.float32)
        mixer.verwerk_een_blok_live_audio(mic, leeg, 480, None, False)
        audio = np.full((960, 2), .3, dtype=np.float32)
        fragment = VoorbereidGeluidsfragment(
            naam_van_het_geluid='test', bestandspad=Path('test.wav'),
            vingerafdruk_van_audio='test', ruwe_float32_stereo_audio=audio.tobytes(),
            aantal_frames=len(audio), oorspronkelijke_samplefrequentie=48000,
            oorspronkelijke_aantal_kanalen=2, ingesteld_volume=1.0,
        )
        mixer._huidige_geluid = _LopendGeluidsfragment(
            afspeelbeurt_id='test', geluid=fragment, voorbereide_samples=audio)
        output = np.zeros((480, 2), dtype=np.float32)
        mixer.verwerk_een_blok_live_audio(mic, output, 480, None, False)
        status = mixer.geef_huidige_status()
        self.assertTrue(status.effect_actief)
        self.assertAlmostEqual(status.effect_rms_voor, .3, places=5)
        self.assertAlmostEqual(status.effect_rms_na, .225, places=5)
        np.testing.assert_allclose(output, .08 + .225, atol=1e-5)
        self.assertFalse(mixer._stop_de_verbinding.is_set())
        output.fill(0)
        mixer.verwerk_een_blok_live_audio(mic, output, 480, None, False)
        output.fill(0)
        mixer.verwerk_een_blok_live_audio(mic, output, 480, None, False)
        self.assertFalse(mixer.geef_huidige_status().effect_actief)

    def test_niveauweergave_mag_audiostream_nooit_onderbreken(self):
        ongeldig = np.asarray([[float('nan'), 1]], dtype=np.float32)
        self.assertEqual(_meet_effect_rms_zonder_audio_te_onderbreken(ongeldig), 0.0)
        self.assertEqual(_meet_effect_rms_zonder_audio_te_onderbreken(np.zeros((0,2))), 0.0)

    def test_browser_pollt_niet_meer_elke_200ms(self):
        inhoud = (Path(__file__).resolve().parents[1] / 'app/webinterface/statisch/dashboard.js').read_text(encoding='utf-8')
        self.assertNotIn('setInterval(vernieuwStatus, 200)', inhoud)
        self.assertIn('setInterval(() => { if (!document.hidden) vernieuwStatus(); }, 1500)', inhoud)
        self.assertIn('function toonLiveSoundboardniveau(waarden, gemeten)', inhoud)
        self.assertIn('function berekenSoundboardDempingDb(percentage)', inhoud)
