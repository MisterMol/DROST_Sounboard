"""Regressies voor versie 5.9.2 zonder echte Windows-audiohardware.

Een eerdere release liet zwart oplichtende FFmpeg-consoles zien en een
CFFI-callback kon crashen tijdens snel stoppen. Deze controles bewaken
beide oorzaken en het herstel van de bediening in het webdashboard.
"""
from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory
from threading import Event, Thread
import unittest
from unittest.mock import Mock, patch

import numpy as np

from app.audio.mp4_verwerken import geef_meegeleverde_ffmpeg, MP4VerwerkingFout
from app.audio.monitor_voor_eigen_headset import MonitorVoorEigenHeadset


BASIS = Path(__file__).resolve().parents[1]


class TestDecoderZonderInternControleproces(unittest.TestCase):
    def test_windows_vindt_de_meegeleverde_binary_zonder_ffmpeg_versieproces(self):
        import imageio_ffmpeg
        with TemporaryDirectory() as basis:
            pakket = Path(basis) / 'imageio_ffmpeg'
            binair = pakket / 'binaries' / 'ffmpeg-win-x86_64-v7.1.exe'
            binair.parent.mkdir(parents=True)
            binair.write_bytes(b'placeholder voor een meegeleverde decoder')
            with patch('app.audio.mp4_verwerken.sys.platform', 'win32'):
                with patch('app.audio.mp4_verwerken.sys.maxsize', 2 ** 63 - 1):
                    with patch.object(imageio_ffmpeg, '__file__', str(pakket / '__init__.py')):
                        with patch.object(imageio_ffmpeg, 'get_ffmpeg_exe', side_effect=AssertionError('mag niet worden aangeroepen')):
                            self.assertEqual(geef_meegeleverde_ffmpeg(), str(binair))

    def test_windows_meldt_ontbrekende_decoder_zonder_een_extern_proces_te_starten(self):
        import imageio_ffmpeg
        with TemporaryDirectory() as basis:
            pakket = Path(basis) / 'imageio_ffmpeg'
            pakket.mkdir(parents=True)
            with patch('app.audio.mp4_verwerken.sys.platform', 'win32'):
                with patch('app.audio.mp4_verwerken.sys.maxsize', 2 ** 63 - 1):
                    with patch.object(imageio_ffmpeg, '__file__', str(pakket / '__init__.py')):
                        with patch.object(imageio_ffmpeg, 'get_ffmpeg_exe', side_effect=AssertionError('mag niet worden aangeroepen')):
                            with self.assertRaisesRegex(MP4VerwerkingFout, 'VIDEO-012'):
                                geef_meegeleverde_ffmpeg()


class VertraagdBlok:
    """Houd de callback vast tijdens het kopiëren om de oude race na te bootsen."""

    def __init__(self, beginnen: Event, doorgaan: Event):
        self.samples = np.full((16, 2), .4, dtype=np.float32)
        self.beginnen = beginnen
        self.doorgaan = doorgaan

    def __len__(self):
        return len(self.samples)

    def __getitem__(self, sleutel):
        self.beginnen.set()
        if not self.doorgaan.wait(2):
            raise RuntimeError('Timeout in de testsimulatie')
        return self.samples[sleutel]


class TestHeadsetMonitorGeenNoneTypeRace(unittest.TestCase):
    def test_buffer_leegmaken_tijdens_callback_geeft_geen_crash(self):
        monitor = MonitorVoorEigenHeadset(Mock(), Mock())
        beginnen, doorgaan = Event(), Event()
        monitor._restblok = VertraagdBlok(beginnen, doorgaan)
        monitor._restpositie = 0
        gevonden_fouten: list[Exception] = []
        resultaat = np.zeros((16, 2), dtype=np.float32)

        def audiowerk():
            try:
                monitor._verwerk_eigen_headset_audio(resultaat, 16, None, False)
            except Exception as fout:
                gevonden_fouten.append(fout)

        draad = Thread(target=audiowerk, daemon=True)
        draad.start()
        try:
            self.assertTrue(beginnen.wait(2), 'Audiocallback is niet bij het kopiëren gekomen')
            monitor.maak_monitorbuffer_leeg()
        finally:
            doorgaan.set()
            draad.join(timeout=2)
        self.assertFalse(draad.is_alive())
        self.assertFalse(gevonden_fouten, f'Audio callback crashte: {gevonden_fouten}')
        nieuw_blok = np.full((16, 2), 0.8, dtype=np.float32)
        monitor._verwerk_eigen_headset_audio(nieuw_blok, 16, None, False)
        np.testing.assert_allclose(nieuw_blok, 0, atol=0)


class TestSpelerEnFoutbegeleiding(unittest.TestCase):
    def setUp(self):
        self.js = (BASIS / 'app/webinterface/statisch/dashboard.js').read_text(encoding='utf-8')
        self.html = (BASIS / 'app/webinterface/statisch/dashboard.html').read_text(encoding='utf-8')
        self.css = (BASIS / 'app/webinterface/statisch/stijl.css').read_text(encoding='utf-8')

    def test_leeg_scherm_heeft_uitgeschakelde_stopknop(self):
        self.assertIn('id="knop-stop" class="knop knop-stop" type="button" disabled', self.html)
        self.assertIn('speler-inactief', self.html)
        self.assertIn('function stelSpelerActiefIn(actief)', self.js)
        self.assertIn('stelSpelerActiefIn(false)', self.js)
        self.assertIn('stelSpelerActiefIn(true)', self.js)
        self.assertIn('speler-inactief .player-knoppen .knop:disabled', self.css)

    def test_fout_bij_uitgeschakeld_soundboard_wijst_de_schakelaar_aan(self):
        self.assertIn('function wijsBijInstelfoutDeOplossingAan(bericht)', self.js)
        self.assertIn('wijsBenodigdeInstellingAan("knop-effecten")', self.js)
        self.assertIn('wijsBenodigdeInstellingAan("knop-verbinden")', self.js)
        self.assertIn('scrollIntoView(', self.js)
        self.assertIn('prefers-reduced-motion', self.js)
        self.assertIn('.instelling-nodig', self.css)


if __name__ == '__main__':
    unittest.main()
