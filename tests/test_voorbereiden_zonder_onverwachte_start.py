"""Stoppen tijdens decoderen mag nooit alsnog een geluid starten."""

from queue import SimpleQueue
from types import SimpleNamespace
import unittest
from unittest.mock import Mock

from app.vensters.venster_voor_live_mixer import VensterVoorLiveMixer


class TestAudioVoorbereidenZonderOnverwachteStart(unittest.TestCase):
    def maak_venster_zonder_windows_gui(self):
        venster = VensterVoorLiveMixer.__new__(VensterVoorLiveMixer)
        venster.resultaten_van_audio_voorbereiden = SimpleQueue()
        venster._volgnummer_van_voorbereiden = 5
        venster._geluid_wordt_voorbereid = True
        venster.venster_is_bezig_met_sluiten = False
        venster.status_onderaan = Mock()
        venster.mixer = Mock()
        venster.logboeken = SimpleNamespace(auditlogboek=Mock(), softwarelogboek=Mock())
        return venster

    def test_oud_geluid_wordt_niet_afgespeeld_na_annulering(self):
        venster = self.maak_venster_zonder_windows_gui()
        venster.resultaten_van_audio_voorbereiden.put((4, object(), None))
        venster._verwerk_voorbereide_geluiden_op_de_vensterdraad()
        venster.mixer.speel_een_voorbereid_geluid.assert_not_called()

    def test_stop_tijdens_decoderen_maakt_een_auditregel_en_verhoogt_volgnummer(self):
        venster = self.maak_venster_zonder_windows_gui()
        venster.stop_het_huidige_geluid()
        self.assertEqual(venster._volgnummer_van_voorbereiden, 6)
        self.assertFalse(venster._geluid_wordt_voorbereid)
        venster.mixer.stop_het_huidige_geluid.assert_called_once()

    def test_nieuw_geluid_wordt_pas_na_decoderen_aan_de_mixer_aangeboden(self):
        venster = self.maak_venster_zonder_windows_gui()
        venster.mixer.speel_een_voorbereid_geluid.return_value = "12345678-audio-id"
        geluid = SimpleNamespace(naam_van_het_geluid="Mijn effect", fragment_ingekort=True)
        venster.resultaten_van_audio_voorbereiden.put((5, geluid, None))
        venster._verwerk_voorbereide_geluiden_op_de_vensterdraad()
        venster.mixer.speel_een_voorbereid_geluid.assert_called_once_with(geluid)
        self.assertFalse(venster._geluid_wordt_voorbereid)


if __name__ == '__main__':
    unittest.main()
