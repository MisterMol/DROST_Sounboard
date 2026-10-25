"""Geluid mag niet starten als er tijdens het decoderen op Stop is geklikt."""

from dataclasses import dataclass
from pathlib import Path
from tempfile import TemporaryDirectory
import threading
import time
import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

from app.diagnostiek.logboek import maak_logboeken_klaar, sluit_logboeken_netjes_af
from app.webinterface.bediening_van_de_audiomotor import WebbedieningVanDrostSoundboard


class TestWebGeluidAnnuleren(unittest.TestCase):
    def setUp(self):
        self.temp = TemporaryDirectory()
        self.map = Path(self.temp.name)
        self.logs = maak_logboeken_klaar(self.map / 'logs')
        self.bediening = WebbedieningVanDrostSoundboard(object(), self.logs, self.map / 'geluiden.db')
        wav = self.map / 'geluid.wav'
        wav.write_bytes(b'nep')
        self.item = self.bediening.geluidenbibliotheek.voeg_geluidsbestanden_toe([wav])[0]
        self.bediening.mixer.geef_huidige_status = Mock(return_value=SimpleNamespace(
            toestand='verbonden', geluidseffecten_aan=True,
        ))
        self.bediening.mixer.speel_een_voorbereid_geluid = Mock(return_value='audio-123')
        self.bediening.mixer.stop_het_huidige_geluid = Mock()
        self.bediening.mixer.verbreek_de_verbinding = Mock()

    def tearDown(self):
        self.bediening._werkdraad_voor_decoderen.shutdown(wait=True, cancel_futures=True)
        sluit_logboeken_netjes_af(self.logs)
        self.temp.cleanup()

    def test_stop_tijdens_decode_begint_oud_fragment_niet_alsnog(self):
        bezig = threading.Event()
        verder = threading.Event()

        def trage_decoder(*args, **kwargs):
            bezig.set()
            if not verder.wait(timeout=4):
                raise TimeoutError('testdecoder wachtte te lang')
            return SimpleNamespace(naam_van_het_geluid='oorspronkelijk')

        with patch('app.webinterface.bediening_van_de_audiomotor.lees_en_bereid_mp3_of_wav_voor',trage_decoder):
            self.bediening.speel_geluid_uit_de_bibliotheek(self.item.geluid_id)
            self.assertTrue(bezig.wait(timeout=2))
            self.bediening.stop_het_huidige_geluid()
            verder.set()
            self.bediening._werkdraad_voor_decoderen.shutdown(wait=True)
            self.bediening.mixer.speel_een_voorbereid_geluid.assert_not_called()


if __name__ == '__main__':
    unittest.main()
