"""Nieuwe tests: MP4, headsetmonitor en beveiligd uitlezen via HTTP."""
from io import BytesIO
import logging
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import Mock
import subprocess
import unittest

import numpy as np

from app.audio.monitor_voor_eigen_headset import MonitorVoorEigenHeadset, MonitorFout
from app.audio.mp4_verwerken import (
    MP4VerwerkingFout, controleer_of_mp4_audio_en_video_bevat,
    geef_meegeleverde_ffmpeg, lees_een_mp4_fragment_als_stereo_float32,
)
from app.audio.mp3_en_wav_fragmenten import lees_en_bereid_mp3_of_wav_voor
from app.audio.live_audiomixer import LiveAudiomixer


class NepHeadset:
    def __init__(self, callback, **kwargs):
        self.callback = callback
        self.active = False
        self.stoppen = 0

    def start(self): self.active = True
    def stop(self): self.active = False; self.stoppen += 1
    def close(self): pass


class NepWindowsAudio:
    def __init__(self):
        self.stream = None
    def query_devices(self):
        return [
            {'name': 'CABLE Input (VB-Audio Virtual Cable)', 'max_output_channels': 2, 'hostapi': 0},
            {'name': 'Luidsprekers (Razer USB Sound Card)', 'max_output_channels': 2, 'hostapi': 0},
            {'name': 'Oude geluidskaart', 'max_output_channels': 1, 'hostapi': 0},
        ]
    def query_hostapis(self): return [{'name': 'Windows WASAPI'}]
    def OutputStream(self, **kwargs):
        self.gekozen_apparaat = kwargs['device']
        self.stream = NepHeadset(**kwargs)
        return self.stream


class TestEigenHeadsetMonitor(unittest.TestCase):
    def setUp(self):
        self.library = NepWindowsAudio()
        self.monitor = MonitorVoorEigenHeadset(self.library, Mock(spec=logging.Logger))
        self.assertTrue(self.monitor.zorg_dat_monitor_kan_afspelen())

    def tearDown(self): self.monitor.sluit_monitor()

    def test_automatisch_razer_en_nooit_cable_uitvoer(self):
        self.assertEqual(self.library.gekozen_apparaat, 1)
        self.assertIn('Razer', self.monitor.huidige_apparaatnaam)

    def test_headset_speelt_effect_zonder_microfoon(self):
        self.monitor.ontvang_alleen_effectsamples(np.full((160, 2), .3, dtype=np.float32))
        buffer = np.zeros((160, 2), dtype=np.float32)
        self.library.stream.callback(buffer, 160, None, False)
        np.testing.assert_allclose(buffer, .3)

    def test_stop_haalt_alle_nog_te_spelen_samples_weg(self):
        self.monitor.ontvang_alleen_effectsamples(np.full((160, 2), .3, dtype=np.float32))
        self.monitor.maak_monitorbuffer_leeg()
        buffer = np.full((160, 2), .8, dtype=np.float32)
        self.library.stream.callback(buffer, 160, None, False)
        self.assertEqual(float(np.max(buffer)), 0.0)

    def test_verkeerde_headset_krijgt_een_duidelijke_fout(self):
        self.monitor.kies_uitvoerapparaat(100)
        with self.assertRaisesRegex(MonitorFout, 'MON-001'):
            self.monitor.zorg_dat_monitor_kan_afspelen()


class TestMp4AudioEnVideo(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = TemporaryDirectory()
        cls.pad = Path(cls.temp.name) / 'test_met_bewegend_beeld.mp4'
        cls.geen_audio = Path(cls.temp.name) / 'test_zonder_audio.mp4'
        cls.ffmpeg = geef_meegeleverde_ffmpeg()
        # Genereer zelf een onschuldige MP4. Geen muziek of videos van derden.
        commando = [cls.ffmpeg, '-y', '-nostdin', '-loglevel', 'error',
                    '-f', 'lavfi', '-i', 'color=c=blue:s=160x90:r=15:d=1.25',
                    '-f', 'lavfi', '-i', 'sine=frequency=660:duration=1.25',
                    '-c:v', 'libx264', '-pix_fmt', 'yuv420p',
                    '-c:a', 'aac', '-b:a', '96k', '-shortest', str(cls.pad)]
        resultaat = subprocess.run(commando, capture_output=True, timeout=20)
        if resultaat.returncode != 0:
            raise RuntimeError(resultaat.stderr.decode(errors='replace'))
        resultaat = subprocess.run([
            cls.ffmpeg, '-y', '-nostdin', '-loglevel', 'error',
            '-f', 'lavfi', '-i', 'color=c=red:s=160x90:r=15:d=1.25',
            '-c:v', 'libx264', '-pix_fmt', 'yuv420p', str(cls.geen_audio),
        ], capture_output=True, timeout=20)
        if resultaat.returncode != 0:
            raise RuntimeError(resultaat.stderr.decode(errors='replace'))

    @classmethod
    def tearDownClass(cls): cls.temp.cleanup()

    def test_mp4_bevat_beide_sporen(self):
        duur = controleer_of_mp4_audio_en_video_bevat(self.pad)
        self.assertGreater(duur, 1.0)

    def test_mp4_wordt_mono_of_stereo_naar_48khz_gebracht(self):
        samples, bronduur = lees_een_mp4_fragment_als_stereo_float32(self.pad, 0, .6)
        self.assertEqual(samples.ndim, 2)
        self.assertEqual(samples.shape[1], 2)
        self.assertGreater(len(samples), 10000)
        self.assertLessEqual(len(samples), 48_000)
        self.assertGreater(float(np.max(np.abs(samples))), .001)
        self.assertGreater(bronduur, 1)

    def test_mp4_gaat_naar_de_bestaande_audio_mixer(self):
        fragment = lees_en_bereid_mp3_of_wav_voor(self.pad, maximale_duur_seconden=.75)
        self.assertGreater(fragment.aantal_frames, 1000)
        self.assertEqual(fragment.oorspronkelijke_aantal_kanalen, 2)
        self.assertEqual(fragment.aantal_frames * 8, len(fragment.ruwe_float32_stereo_audio))

    def test_video_zonder_audio_wordt_geweigerd(self):
        with self.assertRaisesRegex(MP4VerwerkingFout, 'VIDEO-004'):
            controleer_of_mp4_audio_en_video_bevat(self.geen_audio)

    def test_startpositie_na_eind_wordt_geweigerd(self):
        with self.assertRaisesRegex(MP4VerwerkingFout, 'VIDEO-007'):
            lees_een_mp4_fragment_als_stereo_float32(self.pad, 40, .4)

if __name__ == '__main__': unittest.main()
