"""Controleer echte losse downloads, veilige beperkingen en HTTP-authenticatie."""
from __future__ import annotations

import json
import math
import os
from pathlib import Path
import subprocess
from tempfile import TemporaryDirectory
import threading
import unittest
import wave
from urllib.error import HTTPError
from urllib.request import Request, urlopen
from uuid import uuid4

import numpy as np
import soundfile as sf
from PIL import Image

from app.audio.mp4_verwerken import geef_meegeleverde_ffmpeg
from app.diagnostiek.logboek import maak_logboeken_klaar, sluit_logboeken_netjes_af
from app.webinterface.bediening_van_de_audiomotor import WebbedieningVanDrostSoundboard
from app.webinterface.losse_media_exporteren import (
    LosseMediaExportFout, exporteer_geluid_als_los_bestand,
    geef_mogelijke_exportformaten, maak_veilige_downloadnaam,
)
from app.webinterface.lokale_webserver import LokaleWebserverVanDrostSoundboard


class TestLosseMediaExport(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tijdelijk = TemporaryDirectory()
        cls.map = Path(cls.tijdelijk.name)
        cls.vorig_appdata = os.environ.get('LOCALAPPDATA')
        os.environ['LOCALAPPDATA'] = str(cls.map)
        cls.logs = maak_logboeken_klaar(cls.map / 'logs')
        cls.bediening = WebbedieningVanDrostSoundboard(object(), cls.logs, cls.map / 'database.sqlite3')
        cls.server = LokaleWebserverVanDrostSoundboard(('127.0.0.1', 0), cls.bediening)
        cls.draad = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.draad.start()
        cls.url = f'http://127.0.0.1:{cls.server.server_port}'
        cls.wav = cls.server.media_map / 'geluiden' / 'bron.wav'
        samplefrequentie = 48000
        samples = (0.2 * np.sin(2 * np.pi * 330 * np.arange(samplefrequentie * 2) / samplefrequentie)).astype('float32')
        sf.write(cls.wav, samples, samplefrequentie, subtype='PCM_16')
        cls.wav_item = cls.bediening.geluidenbibliotheek.voeg_geluidsbestanden_toe([cls.wav])[0]
        cls.mp4 = cls.server.media_map / 'geluiden' / 'bron.mp4'
        proces = subprocess.run([
            geef_meegeleverde_ffmpeg(), '-nostdin', '-hide_banner', '-loglevel', 'error', '-y',
            '-f', 'lavfi', '-i', 'testsrc2=size=160x90:rate=12:duration=2',
            '-f', 'lavfi', '-i', 'sine=frequency=500:sample_rate=48000:duration=2',
            '-map', '0:v:0', '-map', '1:a:0', '-c:v', 'libx264', '-threads', '2',
            '-pix_fmt', 'yuv420p', '-c:a', 'aac', '-shortest', str(cls.mp4)
        ], capture_output=True, timeout=45, check=False)
        if proces.returncode:
            raise RuntimeError(proces.stderr.decode('utf8', 'replace')[-2000:])
        cls.mp4_item = cls.bediening.geluidenbibliotheek.voeg_geluidsbestanden_toe([cls.mp4])[0]

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.draad.join(timeout=5)
        cls.bediening.sluit_alle_audio_af()
        sluit_logboeken_netjes_af(cls.logs)
        if cls.vorig_appdata is None:
            os.environ.pop('LOCALAPPDATA', None)
        else:
            os.environ['LOCALAPPDATA'] = cls.vorig_appdata
        cls.tijdelijk.cleanup()

    def verzoek(self, nummer, formaat, begin=None, duur=None, gebruik_token=True, methode='POST'):
        headers = {'Content-Type': 'application/json'}
        if gebruik_token:
            headers['X-Drost-Token'] = self.server.schrijf_token
        gegevens = json.dumps({'formaat': formaat, 'begin': begin, 'duur': duur}).encode('utf-8')
        verzoek = Request(self.url + f'/api/geluiden/{nummer}/exporteer',
                          data=gegevens if methode == 'POST' else None,
                          method=methode, headers=headers)
        with urlopen(verzoek, timeout=40) as antwoord:
            return antwoord.status, antwoord.read(), antwoord.headers

    @staticmethod
    def _meet_geexporteerde_audio(pad: Path, vanaf=0.05, lengte=0.25) -> float:
        """Decodeer zelf het echte MP4-audiospoor; headers kunnen misleiden."""
        proc = subprocess.run([
            geef_meegeleverde_ffmpeg(), '-nostdin', '-hide_banner', '-loglevel', 'error',
            '-ss', str(vanaf), '-i', str(pad), '-t', str(lengte),
            '-map', '0:a:0', '-vn', '-ac', '1', '-ar', '48000',
            '-f', 'f32le', 'pipe:1'
        ], capture_output=True, timeout=20, check=False)
        if proc.returncode != 0:
            raise AssertionError(proc.stderr.decode('utf-8', 'replace')[-1200:])
        samples = np.frombuffer(proc.stdout, dtype='<f4')
        if not len(samples):
            raise AssertionError('Geëxporteerde audio bevat geen samples.')
        return float(np.sqrt(np.mean(samples ** 2)))

    def test_mp4_download_via_http_heeft_audio_en_video(self):
        status, data, koppen = self.verzoek(self.mp4_item.geluid_id, 'mp4', .2, .6)
        self.assertEqual(status, 200)
        self.assertEqual(koppen.get_content_type(), 'video/mp4')
        self.assertEqual(data[4:8], b'ftyp')
        pad = self.map / 'http_video_met_geluid.mp4'
        pad.write_bytes(data)
        self.assertGreater(self._meet_geexporteerde_audio(pad), .01)
        pad.unlink(missing_ok=True)

    def test_gif_mp4_duurt_langer_dan_oude_20_seconden_limiet(self):
        # We gebruiken hier 25 seconden bronmateriaal om te controleren dat
        # de oude stilvideo-limiet van 20 seconden niet de audio afbreekt.
        lang_wav = self.server.media_map / 'geluiden' / 'lang_geluid.wav'
        sf.write(str(lang_wav), np.full(48_000 * 25, 0.12, dtype=np.float32), 48_000)
        item = self.bediening.geluidenbibliotheek.voeg_geluidsbestanden_toe([lang_wav])[0]
        gif = self.server.media_map / 'afbeeldingen' / f'{uuid4()}.gif'
        Image.new('RGB', (24, 24), 'blue').save(gif, format='GIF')
        self.bediening.favorieten.bewaar_afbeelding_voor_geluid(item.geluid_id, gif.name)
        pad, _, _, duur = exporteer_geluid_als_los_bestand(
            self.bediening, self.server.media_map, item.geluid_id, 'mp4', 0.0, 24.0,
        )
        try:
            self.assertAlmostEqual(duur, 24, delta=.1)
            self.assertGreater(self._meet_geexporteerde_audio(pad, vanaf=22, lengte=.3), .05)
        finally:
            pad.unlink(missing_ok=True)

    def test_audio_van_gif_mp4_begint_bij_het_geselecteerde_knippunt(self):
        """Controleer sample-inhoud, niet alleen aanwezigheid van de audiospoorheader.

        Dit vangt de fout waarbij het videobeeld wordt geknipt maar de audio
        ongemerkt weer bij seconde nul begint.
        """
        samplefrequentie = 48000
        tijd = np.arange(samplefrequentie, dtype=np.float32) / samplefrequentie
        eerste = 0.2 * np.sin(2 * np.pi * 220 * tijd)
        tweede = 0.2 * np.sin(2 * np.pi * 880 * tijd)
        bronpad = self.server.media_map / 'geluiden' / 'twee_tonen.wav'
        sf.write(bronpad, np.concatenate([eerste, tweede]), samplefrequentie)
        item = self.bediening.geluidenbibliotheek.voeg_geluidsbestanden_toe([bronpad])[0]
        gif = self.server.media_map / 'afbeeldingen' / f'{uuid4()}.gif'
        Image.new('RGB', (24, 24), 'blue').save(gif, format='GIF')
        self.bediening.favorieten.bewaar_afbeelding_voor_geluid(item.geluid_id, gif.name)
        video, _, _, _ = exporteer_geluid_als_los_bestand(
            self.bediening, self.server.media_map, item.geluid_id, 'mp4', 1.15, .50)
        try:
            resultaat = subprocess.run([
                geef_meegeleverde_ffmpeg(), '-nostdin', '-hide_banner', '-loglevel', 'error',
                '-i', str(video), '-t', '0.25', '-map', '0:a:0', '-vn',
                '-ac', '1', '-ar', '48000', '-f', 'f32le', 'pipe:1',
            ], capture_output=True, timeout=30, check=False)
            self.assertEqual(resultaat.returncode, 0, resultaat.stderr.decode('utf8', 'replace'))
            samples = np.frombuffer(resultaat.stdout, dtype='<f4')
            self.assertGreater(len(samples), 1000)
            spectrum = np.abs(np.fft.rfft(samples))
            frequenties = np.fft.rfftfreq(len(samples), d=1 / samplefrequentie)
            grootste_frequentie = frequenties[int(np.argmax(spectrum))]
            self.assertAlmostEqual(grootste_frequentie, 880, delta=12)
        finally:
            video.unlink(missing_ok=True)

    def test_naam_is_veilig_voor_http_header_en_windows(self):
        self.assertEqual(maak_veilige_downloadnaam('Een \r\nmalware:name<>?*', 'mp3'), 'Een_malware_name.mp3')
        self.assertEqual(maak_veilige_downloadnaam('??', 'mp4'), 'geluid.mp4')

    def test_audiobestand_wordt_als_echte_mp3_geexporteerd(self):
        omvang = self.wav.stat().st_size
        pad, naam, media_type, duur = exporteer_geluid_als_los_bestand(
            self.bediening, self.server.media_map, self.wav_item.geluid_id, 'mp3', .31, .51)
        try:
            self.assertEqual(pad.suffix, '.mp3')
            self.assertEqual(media_type, 'audio/mpeg')
            self.assertAlmostEqual(duur, .51, places=3)
            self.assertAlmostEqual(sf.info(str(pad)).duration, .51, delta=.05)
            self.assertTrue(naam.endswith('.mp3'))
            self.assertEqual(self.wav.stat().st_size, omvang)
        finally:
            pad.unlink(missing_ok=True)

    def test_uit_mp4_beeld_en_audio_samen_in_mp4(self):
        pad, _, mime, duur = exporteer_geluid_als_los_bestand(
            self.bediening, self.server.media_map, self.mp4_item.geluid_id, 'mp4', .4, .75)
        try:
            self.assertEqual(mime, 'video/mp4')
            info = subprocess.run([geef_meegeleverde_ffmpeg(), '-hide_banner', '-i', str(pad)],
                                  capture_output=True, text=True, timeout=15)
            self.assertIn('Video:', info.stderr)
            self.assertIn('Audio:', info.stderr)
            # Niet alleen een audiospoor in de header, maar hoorbare samples.
            self.assertGreater(self._meet_geexporteerde_audio(pad), 0.01)
            self.assertAlmostEqual(duur, .75, places=2)
        finally:
            pad.unlink(missing_ok=True)

    def test_videogif_heeft_echte_gif_headers_en_korte_duur(self):
        pad, _, media_type, duur = exporteer_geluid_als_los_bestand(
            self.bediening, self.server.media_map, self.mp4_item.geluid_id, 'gif', 0, 1.0)
        try:
            self.assertEqual(media_type, 'image/gif')
            with Image.open(pad) as gif:
                self.assertGreater(gif.n_frames, 2)
            self.assertEqual(duur, 1.0)
        finally:
            pad.unlink(missing_ok=True)

    def test_gekoppelde_gif_blijft_exact_hetzelfde_bestand(self):
        pad = self.server.media_map / 'afbeeldingen' / f'{uuid4()}.gif'
        Image.new('RGB', (24, 24), 'red').save(pad, format='GIF')
        self.bediening.favorieten.bewaar_afbeelding_voor_geluid(self.wav_item.geluid_id, pad.name)
        self.assertIn('gif', geef_mogelijke_exportformaten(self.bediening, self.server.media_map, self.wav_item.geluid_id))
        tijdelijk, _, _, _ = exporteer_geluid_als_los_bestand(
            self.bediening, self.server.media_map, self.wav_item.geluid_id, 'gif')
        try:
            self.assertEqual(tijdelijk.read_bytes(), pad.read_bytes())
        finally:
            tijdelijk.unlink(missing_ok=True)

    def test_gekoppelde_gif_met_bronaudio_als_mp4_wordt_gedownload(self):
        gifnaam = self.bediening.favorieten.geef_instellingen_van_geluid(self.wav_item.geluid_id).afbeelding_bestandsnaam
        self.assertIsNotNone(gifnaam)
        self.assertIn('mp4', geef_mogelijke_exportformaten(
            self.bediening, self.server.media_map, self.wav_item.geluid_id,
        ))
        pad, _, mime, duur = exporteer_geluid_als_los_bestand(
            self.bediening, self.server.media_map, self.wav_item.geluid_id, 'mp4', 0, 1.5,
        )
        try:
            self.assertEqual(mime, 'video/mp4')
            self.assertAlmostEqual(duur, 1.5, places=2)
            info = subprocess.run([geef_meegeleverde_ffmpeg(), '-hide_banner', '-i', str(pad)],
                                  capture_output=True, text=True, timeout=15)
            self.assertIn('Video:', info.stderr)
            self.assertIn('Audio:', info.stderr)
            self.assertGreater(self._meet_geexporteerde_audio(pad), 0.05)
        finally:
            pad.unlink(missing_ok=True)

    def test_ongeldige_tijden_worden_geweigerd_en_naam_geen_pad(self):
        with self.assertRaisesRegex(LosseMediaExportFout, 'EXP-003'):
            exporteer_geluid_als_los_bestand(self.bediening, self.server.media_map,
                                            self.wav_item.geluid_id, 'mp3', float('nan'), 1)
        with self.assertRaisesRegex(LosseMediaExportFout, 'EXP-004'):
            exporteer_geluid_als_los_bestand(self.bediening, self.server.media_map,
                                            self.wav_item.geluid_id, 'mp3', 5000, 2)
        with self.assertRaisesRegex(LosseMediaExportFout, 'EXP-013'):
            exporteer_geluid_als_los_bestand(self.bediening, self.server.media_map,
                                            self.wav_item.geluid_id, 'exe')

    def test_http_audio_download_heeft_juiste_mime_en_audit(self):
        status, data, koppen = self.verzoek(self.wav_item.geluid_id, 'mp3', .1, .4)
        self.assertEqual(status, 200)
        self.assertEqual(koppen.get_content_type(), 'audio/mpeg')
        self.assertIn('attachment;', koppen['Content-Disposition'])
        self.assertTrue(data.startswith((b'ID3', b'\xff')))
        audit = (self.map / 'logs' / 'audit.jsonl').read_text(encoding='utf-8')
        self.assertIn('los_mediaformaat_geexporteerd', audit)

    def test_export_vereist_correct_token_en_geen_get(self):
        with self.assertRaises(HTTPError) as fout:
            self.verzoek(self.wav_item.geluid_id, 'mp3', gebruik_token=False)
        self.assertEqual(fout.exception.code, 400)
        with self.assertRaises(HTTPError) as fout:
            self.verzoek(self.wav_item.geluid_id, 'mp3', methode='GET')
        self.assertEqual(fout.exception.code, 404)

    def test_download_mp4_kan_niet_van_wav(self):
        with self.assertRaises(HTTPError) as fout:
            self.verzoek(self.wav_item.geluid_id, 'mp4')
        self.assertEqual(fout.exception.code, 400)
        self.assertIn(b'EXP-014', fout.exception.read())

    def test_audio_kan_ook_los_uit_mp4_worden_gedownload(self):
        status, data, koppen = self.verzoek(self.mp4_item.geluid_id, 'mp3', .1, .5)
        self.assertEqual(status, 200)
        self.assertEqual(koppen.get_content_type(), 'audio/mpeg')
        self.assertGreater(len(data), 200)


if __name__ == '__main__':
    unittest.main()
