"""Test de besturing met nepstreams. Dit vervangt nooit een echte Windows-test."""

import logging
import math
import struct
import unittest
from unittest.mock import patch

from app.audio.apparatenbeheer import GevondenAudioapparaat
from app.audio.kabelcontrole import (
    GeselecteerdeKabelapparaten,
    voer_korte_test_van_de_virtuele_kabel_uit,
)


class LoggerDieGebeurtenissenBewaart(logging.Handler):
    def __init__(self):
        super().__init__()
        self.gebeurtenissen = []

    def emit(self, logregel):
        self.gebeurtenissen.append(getattr(logregel, "gebeurtenis", "onbekend"))


class NepOpnameStream:
    def __init__(self, **instellingen):
        self.aantal_frames_gelezen = 0

    def __enter__(self):
        return self

    def __exit__(self, soort_fout, fout, traceback):
        return False

    def read(self, gevraagd_aantal_frames):
        # Lever een nep-440-Hz-signaal aan; dit bewijst alleen dat de code
        # het juiste pad afloopt, niet dat een echte kabel werkt.
        gegevens = bytearray()
        for huidig_framenummer in range(
            self.aantal_frames_gelezen,
            self.aantal_frames_gelezen + gevraagd_aantal_frames,
        ):
            sample = 0.05 * math.sin(2 * math.pi * 440 * huidig_framenummer / 48_000)
            gegevens.extend(struct.pack("<ff", sample, sample))
        self.aantal_frames_gelezen += gevraagd_aantal_frames
        return bytes(gegevens), False


class NepUitvoerStream:
    aantal_weggeschreven_bytes = 0

    def __init__(self, **instellingen):
        self.aantal_weggeschreven_bytes = 0

    def __enter__(self):
        return self

    def __exit__(self, soort_fout, fout, traceback):
        return False

    def write(self, ruwe_bytes):
        self.aantal_weggeschreven_bytes += len(ruwe_bytes)
        return False


class NepAudiobibliotheek:
    RawInputStream = NepOpnameStream
    RawOutputStream = NepUitvoerStream

    @staticmethod
    def check_output_settings(**instellingen):
        return None

    @staticmethod
    def check_input_settings(**instellingen):
        return None


class TestCompleteKabeltestMetNepapparaten(unittest.TestCase):
    def setUp(self):
        self.kabel = GeselecteerdeKabelapparaten(
            afspeelkant=GevondenAudioapparaat(
                21, "CABLE Input (VB-Audio Virtual Cable)", "Windows WASAPI", 0, 2
            ),
            opnamekant=GevondenAudioapparaat(
                23, "CABLE Output (VB-Audio Virtual Cable)", "Windows WASAPI", 2, 0
            ),
        )
        self.softwarelogger = logging.getLogger("test.kabel.software")
        self.auditlogger = logging.getLogger("test.kabel.audit")
        self.auditlogger.setLevel(logging.INFO)
        self.gebeurtenissen = LoggerDieGebeurtenissenBewaart()
        self.auditlogger.addHandler(self.gebeurtenissen)

    def tearDown(self):
        self.auditlogger.removeHandler(self.gebeurtenissen)

    def test_testtoon_heeft_een_start_een_stop_en_meetresultaat(self):
        with patch("app.audio.kabelcontrole.time.sleep", return_value=None):
            resultaat = voer_korte_test_van_de_virtuele_kabel_uit(
                audiobibliotheek=NepAudiobibliotheek,
                geselecteerde_apparaten=self.kabel,
                softwarelogboek=self.softwarelogger,
                auditlogboek=self.auditlogger,
            )

        self.assertTrue(resultaat.is_gelukt)
        self.assertEqual(resultaat.aantal_verstuurde_frames, 86_400)
        self.assertEqual(resultaat.aantal_opgenomen_frames, 153_600)
        self.assertGreater(resultaat.herkende_toonssterkte, 0.001)
        self.assertEqual(
            self.gebeurtenissen.gebeurtenissen,
            ["geluid_gestart", "geluid_gestopt"],
        )

    def test_onbruikbare_audioinstellingen_geeft_originele_fout(self):
        class NepBibliotheekMetKapotteUitvoer(NepAudiobibliotheek):
            @staticmethod
            def check_output_settings(**instellingen):
                raise RuntimeError("PortAudio-driver weigert 48000 Hz")

        with self.assertRaisesRegex(RuntimeError, "weigert 48000 Hz"):
            voer_korte_test_van_de_virtuele_kabel_uit(
                audiobibliotheek=NepBibliotheekMetKapotteUitvoer,
                geselecteerde_apparaten=self.kabel,
                softwarelogboek=self.softwarelogger,
                auditlogboek=self.auditlogger,
            )


if __name__ == "__main__":
    unittest.main()
