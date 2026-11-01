"""RC5: native microfoonsamplefrequentie en realtime fallback met nepdrivers."""

import logging
import threading
import time
import unittest
from unittest.mock import MagicMock, patch

import numpy as np

from app.audio.apparatenbeheer import GevondenAudioapparaat
from app.audio.automatische_microfoonformaten import (
    _BegrensdeAudiobuffer, _geldige_frequentie, zoek_microfoonformaat,
    GescheidenMicrofoonEnUitvoer, zoek_veilige_directsound_kabeluitvoer,
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


class WdmDuplexDriver(FormaatDriver):
    """48 kHz lukt in de drivercontrole, maar duplex weigert definitief."""

    def Stream(self, **kwargs):
        self.streams.append(kwargs)
        raise RuntimeError(
            "WdmSyncIoctl: DeviceIoControl GLE = 0x00000006 [PaErrorCode -9999]"
        )


class OngeldigeDuplexCombinatie(FormaatDriver):
    """Echte Windows-fout -9996: losse endpoints goed, duplex ongeldig."""

    def Stream(self, **kwargs):
        self.streams.append(kwargs)
        raise ValueError(
            'Error opening Stream: Invalid device [PaErrorCode -9996]'
        )


class WeggevallenKabelBijFallback(OngeldigeDuplexCombinatie):
    """De kabel verdwijnt tussen de eerdere controle en de fallback."""

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.output_controles = 0

    def check_output_settings(self, **kwargs):
        self.output_controles += 1
        if self.output_controles > 1:
            raise ValueError(
                'Error querying device: Invalid device [PaErrorCode -9996]'
            )
        return super().check_output_settings(**kwargs)


class WeggevallenMicrofoonBijFallback(OngeldigeDuplexCombinatie):
    """De gekozen microfoon verdwijnt tijdens het openen van de duplexstream."""

    def Stream(self, **kwargs):
        self.streams.append(kwargs)
        self.geldig.clear()
        raise ValueError(
            'Error opening Stream: Invalid device [PaErrorCode -9996]'
        )


class WeggevallenUitvoerBijFallback(OngeldigeDuplexCombinatie):
    """Het kabelapparaat wordt pas bij het openen echt ongeldig."""

    def OutputStream(self, **kwargs):
        raise ValueError(
            'Error opening OutputStream: Invalid device [PaErrorCode -9996]'
        )


class WeggevallenInvoerBijFallback(OngeldigeDuplexCombinatie):
    """De fysieke microfoon weigert alleen bij het werkelijk openen."""

    def InputStream(self, **kwargs):
        raise ValueError('Error opening InputStream: Invalid device [PaErrorCode -9996]')


class DriverMetWasapiConversie(OngeldigeDuplexCombinatie):
    """WASAPI weigert het originele format, Windows-conversie helpt."""

    def WasapiSettings(self, *, exclusive, auto_convert):
        return {'exclusive': exclusive, 'auto_convert': auto_convert}

    def InputStream(self, **kwargs):
        self.input_inst = kwargs
        return super().InputStream(**kwargs)

    def OutputStream(self, **kwargs):
        self.output_inst = kwargs
        if not kwargs.get('extra_settings', {}).get('auto_convert'):
            raise ValueError('Error opening OutputStream: Invalid device [PaErrorCode -9996]')
        return super().OutputStream(**kwargs)


class FoutBijStartenVanKabel(OngeldigeDuplexCombinatie):
    """PortAudio maakt outputstream wel, maar Windows weigert pas bij start."""

    def OutputStream(self, **kwargs):
        self.output = super().OutputStream(**kwargs)
        def weiger_start():
            raise ValueError('Error starting OutputStream: Invalid device [PaErrorCode -9996]')
        self.output.start = weiger_start
        return self.output


class FoutBijStartenVanMicrofoon(OngeldigeDuplexCombinatie):
    """PortAudio maakt inputstream wel, maar Windows weigert pas bij start."""

    def InputStream(self, **kwargs):
        self.input = super().InputStream(**kwargs)
        def weiger_start():
            raise ValueError('Error starting InputStream: Invalid device [PaErrorCode -9996]')
        self.input.start = weiger_start
        return self.input


class DriverMetDirectSoundKabel(OngeldigeDuplexCombinatie):
    """De echte -9996 op WASAPI, dezelfde VB-CABLE werkt via DirectSound."""

    def __init__(self, *, weigeren_bij_start=False, meerdere_kabels=False, **kwargs):
        super().__init__(**kwargs)
        self.weigeren_bij_start = weigeren_bij_start
        self.meerdere_kabels = meerdere_kabels
        self.uitvoerpogingen = []
        self.apis = [{'name': 'Windows WASAPI'}, {'name': 'Windows DirectSound'}]
        self.apparaten = [
            {'name': 'Luidsprekers (Razer USB Sound Card)',
             'hostapi': 0, 'max_output_channels': 2}
            for _ in range(33)
        ]
        self.apparaten[21] = {
            'name': 'CABLE Input (VB-Audio Virtual Cable)',
            'hostapi': 0, 'max_output_channels': 2,
        }
        # DirectSound kort apparaatnamen soms af.
        self.apparaten[30] = {
            'name': 'CABLE Input (VB-Audio Virtual C',
            'hostapi': 1, 'max_output_channels': 2,
        }
        self.apparaten[31] = {
            'name': 'CABLE Input (Andere Kabel)',
            'hostapi': 1, 'max_output_channels': 2,
        }
        if meerdere_kabels:
            self.apparaten[32] = dict(self.apparaten[30])

    def query_devices(self, device=None):
        return self.apparaten if device is None else super().query_devices(device)

    def query_hostapis(self):
        return self.apis

    def OutputStream(self, **kwargs):
        nummer = kwargs['device']
        self.uitvoerpogingen.append(nummer)
        if nummer == 21 and not self.weigeren_bij_start:
            raise ValueError('Error opening OutputStream: Invalid device [PaErrorCode -9996]')
        if nummer == 21:
            stream = super().OutputStream(**kwargs)
            def weiger():
                raise ValueError('Error starting OutputStream: Invalid device [PaErrorCode -9996]')
            stream.start = weiger
            return stream
        if nummer != 30:
            raise AssertionError('Soundboard mag nooit naar luidsprekers of een andere kabel.')
        return super().OutputStream(**kwargs)


class AndereDuplexFout(FormaatDriver):
    """Een onbekende driverfout mag nooit extra audiostreams openen."""

    def Stream(self, **kwargs):
        self.streams.append(kwargs)
        raise RuntimeError("Niet-herkenbare fout tijdens openen van duplex")


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
    def setUp(self):
        self.logger = MagicMock(spec=logging.Logger)
        self.audit = MagicMock(spec=logging.Logger)
        self.microfoon = GevondenAudioapparaat(26, 'Hoofdtelefoon (HyperX Cloud Jet)', 'Windows WASAPI', 1, 0)
        self.kabel = GevondenAudioapparaat(21, 'CABLE Input (VB-Audio Virtual Cable)', 'Windows WASAPI', 0, 2)

    def _wacht(self, mixer, status, timeout=1.5):
        eind=time.monotonic()+timeout
        while time.monotonic()<eind:
            if mixer.geef_huidige_status().toestand == status:
                return
            time.sleep(.01)
        self.fail(f'Verwacht {status}, kreeg {mixer.geef_huidige_status()}')

    def test_bluetooth_16k_wordt_naar_48k_gemengd(self):
        driver=FormaatDriver(geldig=(16000,), standaard=16000)
        mixer=LiveAudiomixer(driver, self.logger, self.audit)
        try:
            mixer.verbind_de_microfoon_met_vb_cable(self.microfoon, self.kabel)
            self._wacht(mixer, 'verbonden')
            self.assertFalse(driver.streams, '48k-duplex mag niet gestart worden')
            self.assertEqual(driver.input.rate,16000)
            self.assertEqual(driver.output.rate,48000)
            self.assertTrue(mixer.geef_huidige_status().aangepast_microfoonformaat)
            self.assertEqual(mixer.geef_huidige_status().microfoon_samplefrequentie, 16000)
            time.sleep(.1)
            self.assertTrue(any(np.max(b) > .1 for b in driver.output.received),
                            'echte microfoonstem moet hoorbaar zijn via de virtuele uitvoer')
            self.assertEqual(mixer.geef_huidige_status().toestand,'verbonden')
        finally:
            mixer.verbreek_de_verbinding()
            mixer.wacht_tot_verbinding_echt_weg_is()
            self.assertFalse(driver.input.active)
            self.assertFalse(driver.output.active)

    def test_48k_behoudt_bestaande_duplexroute(self):
        driver=FormaatDriver(geldig=(48000,), standaard=48000)
        mixer=LiveAudiomixer(driver, self.logger, self.audit)
        try:
            mixer.verbind_de_microfoon_met_vb_cable(self.microfoon, self.kabel)
            self._wacht(mixer, 'verbonden')
            self.assertEqual(len(driver.streams),1)
            self.assertFalse(mixer.geef_huidige_status().aangepast_microfoonformaat)
        finally:
            mixer.verbreek_de_verbinding()
            mixer.wacht_tot_verbinding_echt_weg_is()

    def test_duplex_weigert_48k_na_geslaagde_preflight(self):
        driver = FormaatDriver(geldig=(48000,), standaard=48000,
                              duplex_weigert=True)
        mixer = LiveAudiomixer(driver, self.logger, self.audit)
        try:
            mixer.verbind_de_microfoon_met_vb_cable(self.microfoon, self.kabel)
            self._wacht(mixer, 'verbonden')
            self.assertEqual(driver.input.rate, 48000)
            self.assertEqual(driver.output.rate, 48000)
            self.assertTrue(mixer.geef_huidige_status().aangepast_microfoonformaat)
            time.sleep(.05)
            self.assertTrue(any(np.max(b) > .1 for b in driver.output.received))
        finally:
            mixer.verbreek_de_verbinding()
            mixer.wacht_tot_verbinding_echt_weg_is()

    def test_na_uitgeputte_wdm_duplex_fout_werken_gescheiden_streams(self):
        driver = WdmDuplexDriver(geldig=(48000,), standaard=48000)
        mixer = LiveAudiomixer(driver, self.logger, self.audit)
        try:
            # De normale Windows-start probeert dezelfde kapotte duplex
            # maximaal zes keer. Voorkom echte wachttijd in de test.
            with patch(
                "app.audio.automatisch_audioherstel.PAUZES_VOOR_HERSTEL_IN_SECONDEN",
                (0, 0, 0, 0, 0),
            ):
                mixer.verbind_de_microfoon_met_vb_cable(self.microfoon, self.kabel)
                self._wacht(mixer, 'verbonden')
            self.assertEqual(len(driver.streams), 6)
            self.assertIsNotNone(driver.input)
            self.assertIsNotNone(driver.output)
            self.assertEqual(driver.input.rate, 48000)
            self.assertEqual(driver.output.rate, 48000)
            time.sleep(.05)
            self.assertTrue(any(np.max(b) > .1 for b in driver.output.received))
            self.assertTrue(any(
                call.kwargs.get('extra', {}).get('gebeurtenis')
                == 'duplex_fallback_naar_gescheiden_streams'
                for call in self.logger.warning.call_args_list
            ))
        finally:
            mixer.verbreek_de_verbinding()
            mixer.wacht_tot_verbinding_echt_weg_is()

    def test_echte_razermicrofoon_en_vb_cable_openen_gescheiden_bij_invalid_device(self):
        driver = OngeldigeDuplexCombinatie(geldig=(48000,), standaard=48000)
        mixer = LiveAudiomixer(driver, self.logger, self.audit)
        try:
            mixer.verbind_de_microfoon_met_vb_cable(self.microfoon, self.kabel)
            self._wacht(mixer, 'verbonden')
            self.assertEqual(len(driver.streams), 1)
            self.assertEqual(driver.input.rate, 48000)
            self.assertEqual(driver.output.rate, 48000)
            self.assertTrue(mixer.geef_huidige_status().aangepast_microfoonformaat)
            time.sleep(.06)
            self.assertTrue(any(np.max(b) > .1 for b in driver.output.received))
            meldingen = [
                c.kwargs.get('extra', {}) for c in self.logger.warning.call_args_list
            ]
            self.assertTrue(any(
                x.get('gebeurtenis') == 'duplex_fallback_naar_gescheiden_streams'
                and x.get('gegevens', {}).get('oorzaak')
                    == 'ongeldige_duplex_apparaatcombinatie'
                for x in meldingen
            ))
        finally:
            mixer.verbreek_de_verbinding()
            mixer.wacht_tot_verbinding_echt_weg_is()

    def test_ongeldige_kabel_na_duplexfout_stopt_zonder_nieuwe_streams(self):
        driver = WeggevallenKabelBijFallback(geldig=(48000,), standaard=48000)
        mixer = LiveAudiomixer(driver, self.logger, self.audit)
        try:
            mixer.verbind_de_microfoon_met_vb_cable(self.microfoon, self.kabel)
            self._wacht(mixer, 'fout')
            self.assertIn('LIVE-025', mixer.geef_huidige_status().laatst_bekende_fout)
            self.assertIsNone(driver.input)
            self.assertIsNone(driver.output)
            self.assertEqual(driver.output_controles, 2)
        finally:
            mixer.verbreek_de_verbinding()
            mixer.wacht_tot_verbinding_echt_weg_is()

    def test_ongeldige_microfoon_na_duplexfout_levert_gerichte_melding(self):
        driver = WeggevallenMicrofoonBijFallback(geldig=(48000,), standaard=48000)
        mixer = LiveAudiomixer(driver, self.logger, self.audit)
        try:
            mixer.verbind_de_microfoon_met_vb_cable(self.microfoon, self.kabel)
            self._wacht(mixer, 'fout')
            self.assertIn('LIVE-025', mixer.geef_huidige_status().laatst_bekende_fout)
            self.assertIsNone(driver.input)
            self.assertIsNone(driver.output)
        finally:
            mixer.verbreek_de_verbinding()
            mixer.wacht_tot_verbinding_echt_weg_is()

    def test_gescheiden_stream_die_invalid_device_geeft_wordt_niet_herhaald(self):
        driver = WeggevallenUitvoerBijFallback(geldig=(48000,), standaard=48000)
        mixer = LiveAudiomixer(driver, self.logger, self.audit)
        try:
            mixer.verbind_de_microfoon_met_vb_cable(self.microfoon, self.kabel)
            self._wacht(mixer, 'fout')
            self.assertIn('LIVE-027', mixer.geef_huidige_status().laatst_bekende_fout)
            self.assertEqual(len(driver.streams), 1)
            self.assertIsNotNone(driver.input)
            self.assertFalse(driver.input.active)
        finally:
            mixer.verbreek_de_verbinding()
            mixer.wacht_tot_verbinding_echt_weg_is()

    def test_mislukte_losse_microfoon_toont_eigen_foutcode(self):
        driver = WeggevallenInvoerBijFallback(geldig=(48000,), standaard=48000)
        mixer = LiveAudiomixer(driver, self.logger, self.audit)
        try:
            mixer.verbind_de_microfoon_met_vb_cable(self.microfoon, self.kabel)
            self._wacht(mixer, 'fout')
            self.assertIn('LIVE-026', mixer.geef_huidige_status().laatst_bekende_fout)
            self.assertIsNone(driver.output)
            self.assertIn('fysieke microfoon',
                gebruikersmelding(mixer.geef_huidige_status().laatst_bekende_fout))
        finally:
            mixer.verbreek_de_verbinding()
            mixer.wacht_tot_verbinding_echt_weg_is()

    def test_wasapi_shared_converter_herstelt_ongeldig_outputformaat(self):
        driver = DriverMetWasapiConversie(geldig=(48000,), standaard=48000)
        mixer = LiveAudiomixer(driver, self.logger, self.audit)
        try:
            mixer.verbind_de_microfoon_met_vb_cable(self.microfoon, self.kabel)
            self._wacht(mixer, 'verbonden')
            self.assertTrue(driver.input_inst['extra_settings']['auto_convert'])
            self.assertTrue(driver.output_inst['extra_settings']['auto_convert'])
            self.assertFalse(driver.output_inst['extra_settings']['exclusive'])
            self.assertEqual(driver.output.rate, 48000)
            time.sleep(.06)
            self.assertTrue(any(np.max(b) > .1 for b in driver.output.received))
        finally:
            mixer.verbreek_de_verbinding()
            mixer.wacht_tot_verbinding_echt_weg_is()

    def test_virtuele_uitvoer_die_bij_start_weigert_toont_live_027(self):
        driver = FoutBijStartenVanKabel(geldig=(48000,), standaard=48000)
        mixer = LiveAudiomixer(driver, self.logger, self.audit)
        try:
            mixer.verbind_de_microfoon_met_vb_cable(self.microfoon, self.kabel)
            self._wacht(mixer, 'fout')
            self.assertIn('LIVE-027', mixer.geef_huidige_status().laatst_bekende_fout)
            self.assertFalse(driver.input.active)
            self.assertFalse(driver.output.active)
        finally:
            mixer.verbreek_de_verbinding()
            mixer.wacht_tot_verbinding_echt_weg_is()

    def test_microfoon_die_bij_start_weigert_toont_live_026(self):
        driver = FoutBijStartenVanMicrofoon(geldig=(48000,), standaard=48000)
        mixer = LiveAudiomixer(driver, self.logger, self.audit)
        try:
            mixer.verbind_de_microfoon_met_vb_cable(self.microfoon, self.kabel)
            self._wacht(mixer, 'fout')
            self.assertIn('LIVE-026', mixer.geef_huidige_status().laatst_bekende_fout)
            self.assertFalse(driver.input.active)
            self.assertFalse(driver.output.active)
        finally:
            mixer.verbreek_de_verbinding()
            mixer.wacht_tot_verbinding_echt_weg_is()

    def test_directsound_reserve_is_exact_dezelfde_vb_cable(self):
        for fout_bij_start in (False, True):
            with self.subTest(fout_bij_start=fout_bij_start):
                driver = DriverMetDirectSoundKabel(
                    geldig=(48000,), standaard=48000,
                    weigeren_bij_start=fout_bij_start,
                )
                mixer = LiveAudiomixer(driver, self.logger, self.audit)
                try:
                    self.assertEqual(zoek_veilige_directsound_kabeluitvoer(driver), 30)
                    mixer.verbind_de_microfoon_met_vb_cable(self.microfoon, self.kabel)
                    self._wacht(mixer, 'verbonden')
                    self.assertEqual(driver.uitvoerpogingen, [21, 30])
                    self.assertEqual(driver.output.rate, 48000)
                    time.sleep(.07)
                    self.assertTrue(any(np.max(b) > .1 for b in driver.output.received))
                    self.assertTrue(any(
                        c.kwargs.get('extra', {}).get('gebeurtenis') ==
                        'vb_cable_directsound_herstel'
                        for c in self.logger.warning.call_args_list
                    ))
                finally:
                    mixer.verbreek_de_verbinding()
                    mixer.wacht_tot_verbinding_echt_weg_is()

    def test_nooit_gokken_bij_twee_directsound_kabels(self):
        driver = DriverMetDirectSoundKabel(
            geldig=(48000,), standaard=48000, meerdere_kabels=True,
        )
        self.assertIsNone(zoek_veilige_directsound_kabeluitvoer(driver))
        mixer = LiveAudiomixer(driver, self.logger, self.audit)
        try:
            mixer.verbind_de_microfoon_met_vb_cable(self.microfoon, self.kabel)
            self._wacht(mixer, 'fout')
            self.assertIn('LIVE-027', mixer.geef_huidige_status().laatst_bekende_fout)
            self.assertEqual(driver.uitvoerpogingen, [21])
        finally:
            mixer.verbreek_de_verbinding()
            mixer.wacht_tot_verbinding_echt_weg_is()

    def test_onbekende_duplex_fout_opent_geen_extra_microfoonstream(self):
        driver = AndereDuplexFout(geldig=(48000,), standaard=48000)
        mixer = LiveAudiomixer(driver, self.logger, self.audit)
        try:
            mixer.verbind_de_microfoon_met_vb_cable(self.microfoon, self.kabel)
            self._wacht(mixer, 'fout')
            self.assertEqual(len(driver.streams), 1)
            self.assertIsNone(driver.input)
            self.assertIsNone(driver.output)
            self.assertIn('Niet-herkenbare fout', mixer.geef_huidige_status().laatst_bekende_fout)
        finally:
            mixer.verbreek_de_verbinding()
            mixer.wacht_tot_verbinding_echt_weg_is()

    def test_usb_44100_werkt_ook_via_eigen_streams(self):
        driver=FormaatDriver(geldig=(44100,), standaard=44100)
        mixer=LiveAudiomixer(driver, self.logger, self.audit)
        try:
            mixer.verbind_de_microfoon_met_vb_cable(self.microfoon, self.kabel)
            self._wacht(mixer, 'verbonden')
            self.assertEqual(driver.input.rate, 44100)
            self.assertEqual(driver.output.rate, 48000)
            time.sleep(.09)
            self.assertTrue(any(np.max(b) > .1 for b in driver.output.received))
        finally:
            mixer.verbreek_de_verbinding()
            mixer.wacht_tot_verbinding_echt_weg_is()

    def test_meldingen_voor_driver_en_vb_cable_zijn_bruikbaar(self):
        self.assertIn(
            'VB-CABLE',
            gebruikersmelding('KABEL-002: virtuele kabel ontbreekt'),
        )
        self.assertIn(
            'Windows',
            gebruikersmelding('LIVE-024: gescheiden audiostreams geweigerd'),
        )
        self.assertIn(
            'audioverbinding',
            gebruikersmelding('LIVE-025: apparaatcombinatie ongeldig'),
        )
        self.assertIn(
            'fysieke microfoon',
            gebruikersmelding('LIVE-026: opname-ingang onbereikbaar'),
        )
        self.assertIn(
            'CABLE Input',
            gebruikersmelding('LIVE-027: virtuele uitvoer onbereikbaar'),
        )

    def test_geen_ondersteund_formaat_is_duidelijke_fout(self):
        driver=FormaatDriver(geldig=(), standaard=16000)
        mixer=LiveAudiomixer(driver, self.logger, self.audit)
        mixer.verbind_de_microfoon_met_vb_cable(self.microfoon, self.kabel)
        self._wacht(mixer, 'fout')
        status = mixer.geef_huidige_status()
        self.assertTrue(status.microfoon_formaat_fout)
        self.assertIn('LIVE-003',status.laatst_bekende_fout)
        self.assertEqual(status.standaard_microfoonfrequentie,16000)
        self.assertIn('microfoon',gebruikersmelding(status.laatst_bekende_fout))


if __name__ == '__main__':
    unittest.main()
