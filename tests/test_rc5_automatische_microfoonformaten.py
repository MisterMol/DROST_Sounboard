"""RC5: native microfoonsamplefrequentie en realtime fallback met nepdrivers."""

import logging
import threading
import time
import unittest
from unittest.mock import MagicMock

import numpy as np

from app.audio.apparatenbeheer import GevondenAudioapparaat
from app.audio.automatische_microfoonformaten import (
    _BegrensdeAudiobuffer, _geldige_frequentie, zoek_microfoonformaat,
    GescheidenMicrofoonEnUitvoer,
)
from app.audio.live_audiomixer import LiveAudiomixer
from app.webinterface.gebruikersmeldingen import gebruikersmelding


class FormaatDriver:
    def __init__(self, geldig=(16000,), standaard=16000, max_channels=1,
                 duplex_weigert=False):
        self.geldig = set(geldig)
        self.duplex_weigert = duplex_weigert
        self.standaard = standaard
        self.max_channels = max_channels
        self.queries = []
        self.streams = []
        self.output = None
        self.input = None

    def query_devices(self, device):
        return {'default_samplerate': self.standaard}

    def check_input_settings(self, **kwargs):
        self.queries.append(kwargs)
        if kwargs['samplerate'] not in self.geldig or kwargs['channels'] > self.max_channels:
            raise ValueError('PortAudioError: Invalid sample rate [PaErrorCode -9997]')

    def check_output_settings(self, **kwargs):
        if kwargs['samplerate'] != 48000:
            raise ValueError('CABLE vereist 48000')

    def Stream(self, **kwargs):
        self.streams.append(kwargs)
        if self.duplex_weigert:
            raise ValueError('PortAudioError: Invalid sample rate [PaErrorCode -9997]')
        return _FakeDuplex(kwargs['callback'])

    def InputStream(self, **kwargs):
        self.input = _FakeInput(kwargs['callback'], kwargs['channels'], kwargs['samplerate'])
        return self.input

    def OutputStream(self, **kwargs):
        self.output = _FakeOutput(kwargs['callback'], kwargs['samplerate'])
        return self.output


class _FakeDuplex:
    def __init__(self, callback):
        self.callback = callback
        self.active = False
        self.latency = (0.06, 0.06)

    def start(self):
        self.active = True

    def stop(self, ignore_errors=False):
        self.active = False

    def close(self, ignore_errors=False):
        self.active = False


class _FakeInput(_FakeDuplex):
    def __init__(self, callback, channels, samplerate):
        super().__init__(callback)
        self.channels = channels
        self.rate = samplerate
        self.thread = None

    def start(self):
        super().start()
        def send():
            while self.active:
                frames = int(self.rate / 200)
                self.callback(np.full((frames, self.channels), .32, dtype=np.float32),
                              frames, None, False)
                time.sleep(.005)
        self.thread = threading.Thread(target=send, daemon=True)
        self.thread.start()

    def stop(self, ignore_errors=False):
        super().stop(ignore_errors)
        if self.thread:
            self.thread.join(timeout=.2)


class _FakeOutput(_FakeDuplex):
    def __init__(self, callback, samplerate):
        super().__init__(callback)
        self.rate = samplerate
        self.received = []
        self.thread = None

    def start(self):
        super().start()
        def read():
            while self.active:
                frames = int(self.rate / 200)
                outdata = np.zeros((frames, 2), dtype=np.float32)
                self.callback(outdata, frames, None, False)
                self.received.append(outdata.copy())
                time.sleep(.005)
        self.thread = threading.Thread(target=read, daemon=True)
        self.thread.start()

    def stop(self, ignore_errors=False):
        super().stop(ignore_errors)
        if self.thread:
            self.thread.join(timeout=.2)


class TestFormaten(unittest.TestCase):
    def test_native_16k_wint_en_mono(self):
        driver = FormaatDriver(geldig=(16000, 24000), standaard=16000)
        f = zoek_microfoonformaat(driver, 26, 1)
        self.assertEqual((f.samplefrequentie, f.aantal_kanalen), (16000, 1))
        self.assertEqual(f.ondersteunde_samplefrequenties, (16000, 24000))
        self.assertNotIn(48000, f.ondersteunde_samplefrequenties)

    def test_standaard_onbekend_geeft_44100(self):
        d = FormaatDriver(geldig=(44100,), standaard=float('nan'))
        f = zoek_microfoonformaat(d, 26, 1)
        self.assertEqual(f.samplefrequentie, 44100)
        self.assertIsNone(f.standaard_samplefrequentie)

    def test_ongeldige_driverwaarden_worden_genegeerd(self):
        for r in (None, '', -1, 0, float('nan'), float('inf'), 'nan', object(), 384000):
            self.assertIsNone(_geldige_frequentie(r))

    def test_geen_formats_levert_geen_speculatieve_oplossing(self):
        d = FormaatDriver(geldig=(), standaard=16000)
        self.assertIsNone(zoek_microfoonformaat(d, 26, 1))

    def test_maximaal_een_kanaal_gecontroleerd(self):
        d = FormaatDriver(geldig=(16000,), standaard=16000)
        zoek_microfoonformaat(d, 26, 1)
        self.assertTrue(all(kw['channels'] == 1 for kw in d.queries))


class TestRingbuffer(unittest.TestCase):
    def test_lege_buffer_is_stil(self):
        b = _BegrensdeAudiobuffer(1, max_frames=9)
        self.assertEqual(b.lees(4).shape, (4, 1))
        self.assertEqual(b.lege_frames, 4)

    def test_overloop_gooit_oudste_frames_weg(self):
        b = _BegrensdeAudiobuffer(1, max_frames=6)
        b.schrijf(np.ones((4,1), dtype=np.float32))
        b.schrijf(np.full((4,1), 2, dtype=np.float32))
        self.assertEqual(b.beschikbare_frames, 4)
        np.testing.assert_array_equal(b.lees(4), np.full((4,1), 2, dtype=np.float32))
        self.assertGreater(b.verloren_frames, 0)

    def test_geleidelijke_consumptie_houdt_offset_bij(self):
        b = _BegrensdeAudiobuffer(2, max_frames=12)
        b.schrijf(np.full((10,2), 3, dtype=np.float32))
        self.assertEqual(b.lees(3).sum(), 18)
        self.assertEqual(b.lees(7).sum(), 42)
        self.assertEqual(b.beschikbare_frames, 0)


class TestEchteMixerMetNepdriver(unittest.TestCase):
    """Classic: bewaak de oude Beta 4.10 duplexroute, geen RC6-fallback."""

    def setUp(self):
        self.logger = MagicMock(spec=logging.Logger)
        self.audit = MagicMock(spec=logging.Logger)
        self.microfoon = GevondenAudioapparaat(
            26, 'Hoofdtelefoon (HyperX Cloud Jet)', 'Windows WASAPI', 1, 0,
        )
        self.kabel = GevondenAudioapparaat(
            21, 'CABLE Input (VB-Audio Virtual Cable)', 'Windows WASAPI', 0, 2,
        )

    def _wacht(self, mixer, status, timeout=1.5):
        einde = time.monotonic() + timeout
        while time.monotonic() < einde:
            if mixer.geef_huidige_status().toestand == status:
                return
            time.sleep(.01)
        self.fail(f'Verwacht {status}, kreeg {mixer.geef_huidige_status()}')

    def test_bestaande_48k_duplexblijft_onaangeroerd(self):
        driver = FormaatDriver(geldig=(48000,), standaard=48000)
        mixer = LiveAudiomixer(driver, self.logger, self.audit)
        try:
            mixer.verbind_de_microfoon_met_vb_cable(self.microfoon, self.kabel)
            self._wacht(mixer, 'verbonden')
            self.assertEqual(len(driver.streams), 1)
            self.assertEqual(driver.streams[0]['device'], (26, 21))
            self.assertEqual(driver.streams[0]['samplerate'], 48000)
            self.assertEqual(driver.streams[0]['latency'], 'high')
            self.assertFalse(mixer.geef_huidige_status().aangepast_microfoonformaat)
            self.assertIsNone(driver.input)
            self.assertIsNone(driver.output)
        finally:
            mixer.verbreek_de_verbinding()
            mixer.wacht_tot_verbinding_echt_weg_is()

    def test_classic_verbergt_geen_geweigerde_duplexdriver_met_tweede_stream(self):
        driver = FormaatDriver(geldig=(48000,), standaard=48000,
                              duplex_weigert=True)
        mixer = LiveAudiomixer(driver, self.logger, self.audit)
        try:
            mixer.verbind_de_microfoon_met_vb_cable(self.microfoon, self.kabel)
            self._wacht(mixer, 'fout')
            self.assertEqual(len(driver.streams), 1)
            self.assertIsNone(driver.input)
            self.assertIsNone(driver.output)
            self.assertIn('Invalid sample rate', mixer.geef_huidige_status().laatst_bekende_fout)
        finally:
            mixer.verbreek_de_verbinding()
            mixer.wacht_tot_verbinding_echt_weg_is()

    def test_classic_16k_microfoon_geeft_oude_directe_fout(self):
        driver = FormaatDriver(geldig=(16000,), standaard=16000)
        mixer = LiveAudiomixer(driver, self.logger, self.audit)
        try:
            mixer.verbind_de_microfoon_met_vb_cable(self.microfoon, self.kabel)
            self._wacht(mixer, 'fout')
            self.assertFalse(driver.streams)
            self.assertIsNone(driver.input)
            self.assertIsNone(driver.output)
            self.assertIn('LIVE-003', mixer.geef_huidige_status().laatst_bekende_fout)
            self.assertIn('microfoon', gebruikersmelding(mixer.geef_huidige_status().laatst_bekende_fout))
        finally:
            mixer.verbreek_de_verbinding()
            mixer.wacht_tot_verbinding_echt_weg_is()

    def test_classic_44100_microfoon_geeft_oude_directe_fout(self):
        driver = FormaatDriver(geldig=(44100,), standaard=44100)
        mixer = LiveAudiomixer(driver, self.logger, self.audit)
        try:
            mixer.verbind_de_microfoon_met_vb_cable(self.microfoon, self.kabel)
            self._wacht(mixer, 'fout')
            self.assertFalse(driver.streams)
            self.assertIn('LIVE-003', mixer.geef_huidige_status().laatst_bekende_fout)
        finally:
            mixer.verbreek_de_verbinding()
            mixer.wacht_tot_verbinding_echt_weg_is()

    def test_classic_geen_ondersteund_formaat_is_directe_fout(self):
        driver = FormaatDriver(geldig=(), standaard=16000)
        mixer = LiveAudiomixer(driver, self.logger, self.audit)
        try:
            mixer.verbind_de_microfoon_met_vb_cable(self.microfoon, self.kabel)
            self._wacht(mixer, 'fout')
            status = mixer.geef_huidige_status()
            self.assertTrue(status.microfoon_formaat_fout)
            self.assertIn('LIVE-003', status.laatst_bekende_fout)
            self.assertEqual(status.toestand, 'fout')
        finally:
            mixer.verbreek_de_verbinding()
            mixer.wacht_tot_verbinding_echt_weg_is()


if __name__ == '__main__':
    unittest.main()
