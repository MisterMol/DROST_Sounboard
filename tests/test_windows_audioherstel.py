"""Tests voor Windows COM en herstel bij een tijdelijk driverprobleem.

Alle audioapparaten en COM-functies zijn nagebootst. Deze tests openen geen
microfoon en veranderen geen Windows-geluidsinstellingen.
"""

from __future__ import annotations

from unittest import TestCase
from unittest.mock import MagicMock, patch
import threading

from app.audio import automatisch_audioherstel as audioherstel
from app.audio import windows_com_context as com_context


VOORBEELD_VAN_ECHTE_STARTFOUT = (
    "Error starting stream: Unanticipated host error [PaErrorCode -9999]: "
    "'WdmSyncIoctl: DeviceIoControl GLE = 0x00000006 "
    "(prop_set = {A855A48C-2F78-4729-9051-1968746B9EEF}, prop_id = 8)' "
    "[Windows WDM-KS error 0]"
)


class NepAudiostroom:
    def __init__(self, fout_bij_starten=None, fout_bij_sluiten=None):
        self.fout_bij_starten = fout_bij_starten
        self.fout_bij_sluiten = fout_bij_sluiten
        self.active = False
        self.is_gesloten = False
        self.aantal_stops = 0

    def start(self):
        if self.fout_bij_starten:
            raise self.fout_bij_starten
        self.active = True

    def stop(self, ignore_errors=False):
        self.aantal_stops += 1
        self.active = False

    def close(self, ignore_errors=False):
        self.is_gesloten = True
        if self.fout_bij_sluiten:
            raise self.fout_bij_sluiten


class NepAudiobibliotheek:
    def __init__(self, fouten_bij_starten):
        self.fouten_bij_starten = list(fouten_bij_starten)
        self.stromen = []
        self.laatste_streaminstellingen = None

    def Stream(self, **instellingen):
        self.laatste_streaminstellingen = instellingen
        fout = self.fouten_bij_starten.pop(0) if self.fouten_bij_starten else None
        nieuwe_stroom = NepAudiostroom(fout_bij_starten=fout)
        self.stromen.append(nieuwe_stroom)
        return nieuwe_stroom


class TestAudioherstel(TestCase):
    def setUp(self):
        self.software = MagicMock()
        self.audit = MagicMock()
        self.stopgebeurtenis = threading.Event()
        self.pogingen = []
        # Tijdens tests niet enkele seconden wachten op een nepdriver.
        self.patcher = patch.object(
            audioherstel, "PAUZES_VOOR_HERSTEL_IN_SECONDEN", (0, 0, 0, 0, 0)
        )
        self.patcher.start()

    def tearDown(self):
        self.patcher.stop()

    def voer_een_startpoging_uit(self, nepbibliotheek):
        return audioherstel.open_en_start_de_audiostream_met_herstel(
            audiobibliotheek=nepbibliotheek,
            instellingen_van_stream={
                "device": (24, 21),
                "channels": (1, 2),
                "samplerate": 48000,
                "dtype": "float32",
            },
            stoppen_gevraagd=self.stopgebeurtenis,
            softwarelogboek=self.software,
            auditlogboek=self.audit,
            zet_huidige_poging=self.pogingen.append,
        )

    def test_herkent_specifieke_windows_fout_en_geen_andere_fout(self):
        self.assertTrue(audioherstel.is_het_bekende_tijdelijke_windows_driverprobleem(
            RuntimeError(VOORBEELD_VAN_ECHTE_STARTFOUT)
        ))
        self.assertFalse(audioherstel.is_het_bekende_tijdelijke_windows_driverprobleem(
            RuntimeError("PaErrorCode -9999: verkeerd audioformaat")
        ))
        self.assertFalse(audioherstel.is_het_bekende_tijdelijke_windows_driverprobleem(
            ValueError("paramater ontbreekt")
        ))

    def test_normale_start_opent_een_stream_en_laat_hem_actief(self):
        nepbibliotheek = NepAudiobibliotheek([])
        stroom, pogingen = self.voer_een_startpoging_uit(nepbibliotheek)
        self.assertEqual(pogingen, 1)
        self.assertEqual(self.pogingen, [1])
        self.assertTrue(stroom.active)
        self.assertFalse(stroom.is_gesloten)
        self.assertEqual(nepbibliotheek.laatste_streaminstellingen["device"], (24, 21))
        self.assertFalse(self.software.warning.called)

    def test_tijdelijke_driverfouten_krijgen_automatisch_nieuwe_poging(self):
        fout = RuntimeError(VOORBEELD_VAN_ECHTE_STARTFOUT)
        nepbibliotheek = NepAudiobibliotheek([fout, fout, None])
        stroom, pogingen = self.voer_een_startpoging_uit(nepbibliotheek)
        self.assertEqual(pogingen, 3)
        self.assertEqual(self.pogingen, [1, 2, 3])
        self.assertTrue(stroom.active)
        self.assertTrue(all(stroom.is_gesloten for stroom in nepbibliotheek.stromen[:2]))
        self.assertFalse(nepbibliotheek.stromen[2].is_gesloten)
        self.assertEqual(self.software.warning.call_count, 2)
        for call in self.software.warning.call_args_list:
            self.assertEqual(call.kwargs["extra"]["gebeurtenis"], "tijdelijke_audio_startfout")
            self.assertIs(call.kwargs["exc_info"][1], fout)
        self.assertTrue(self.software.info.called)
        self.assertTrue(self.audit.info.called)

    def test_zes_fouten_worden_een_definitieve_fout(self):
        fouten = [RuntimeError(VOORBEELD_VAN_ECHTE_STARTFOUT) for _ in range(6)]
        nepbibliotheek = NepAudiobibliotheek(fouten)
        with self.assertRaises(RuntimeError) as gebeurtenis:
            self.voer_een_startpoging_uit(nepbibliotheek)
        self.assertIs(gebeurtenis.exception, fouten[-1])
        self.assertEqual(len(nepbibliotheek.stromen), 6)
        self.assertTrue(all(stroom.is_gesloten for stroom in nepbibliotheek.stromen))
        self.assertEqual(self.software.warning.call_count, 5)
        self.assertFalse(self.audit.info.called)

    def test_gewone_programmeerfout_wordt_niet_opnieuw_geprobeerd(self):
        nepbibliotheek = NepAudiobibliotheek([ValueError("verkeerd parameterformaat")])
        with self.assertRaisesRegex(ValueError, "verkeerd parameterformaat"):
            self.voer_een_startpoging_uit(nepbibliotheek)
        self.assertEqual(len(nepbibliotheek.stromen), 1)
        self.assertTrue(nepbibliotheek.stromen[0].is_gesloten)
        self.assertEqual(self.software.warning.call_count, 0)

    def test_verbreken_tijdens_herstel_stopt_het_proberen(self):
        nepbibliotheek = NepAudiobibliotheek([
            RuntimeError(VOORBEELD_VAN_ECHTE_STARTFOUT), None
        ])
        with patch.object(self.stopgebeurtenis, "wait", side_effect=lambda seconden: True):
            stroom, pogingen = self.voer_een_startpoging_uit(nepbibliotheek)
        self.assertIsNone(stroom)
        self.assertEqual(pogingen, 1)
        self.assertTrue(nepbibliotheek.stromen[0].is_gesloten)
        self.assertEqual(len(nepbibliotheek.stromen), 1)

    def test_sluitfout_stopt_herstel_en_bewaart_fouten_in_logs(self):
        foute_stream = NepAudiostroom(
            fout_bij_starten=RuntimeError(VOORBEELD_VAN_ECHTE_STARTFOUT),
            fout_bij_sluiten=RuntimeError("Sluiten van audiohandle lukt niet"),
        )
        nepbibliotheek = MagicMock()
        nepbibliotheek.Stream.return_value = foute_stream
        with self.assertRaisesRegex(audioherstel.AudioherstelAfgebrokenFout, "LIVE-021"):
            self.voer_een_startpoging_uit(nepbibliotheek)
        nepbibliotheek.Stream.assert_called_once()
        self.assertTrue(self.software.exception.called)


class TestWindowsComBeheer(TestCase):
    def test_geen_windows_betekent_geen_aanroep_naar_com(self):
        with patch.object(com_context.platform, "system", return_value="Linux"):
            with patch.object(com_context, "haal_com_bibliotheek_van_windows_op") as ophalen:
                with com_context.houd_com_beschikbaar_tijdens_audioverbinding() as stand:
                    self.assertEqual(stand, "niet_van_toepassing")
                ophalen.assert_not_called()

    def maak_nep_com(self, hresult):
        bibliotheek = MagicMock()
        bibliotheek.CoInitializeEx.return_value = hresult
        return bibliotheek

    def test_com_wordt_een_keer_op_dezelfde_draad_geopend_en_gesloten(self):
        bibliotheek = self.maak_nep_com(0)
        with patch.object(com_context.platform, "system", return_value="Windows"):
            with patch.object(com_context, "haal_com_bibliotheek_van_windows_op", return_value=bibliotheek):
                with com_context.houd_com_beschikbaar_tijdens_audioverbinding() as stand:
                    self.assertEqual(stand, "sta_ingeschakeld")
                    bibliotheek.CoUninitialize.assert_not_called()
                bibliotheek.CoUninitialize.assert_called_once()
                bibliotheek.CoInitializeEx.assert_called_once_with(None, 2)

    def test_bestaande_com_referentie_wordt_correct_afgesloten(self):
        bibliotheek = self.maak_nep_com(1)
        with patch.object(com_context.platform, "system", return_value="Windows"):
            with patch.object(com_context, "haal_com_bibliotheek_van_windows_op", return_value=bibliotheek):
                with com_context.houd_com_beschikbaar_tijdens_audioverbinding():
                    pass
        bibliotheek.CoUninitialize.assert_called_once()

    def test_andere_reeds_bestaande_com_stand_wordt_niet_weggehaald(self):
        bibliotheek = self.maak_nep_com(0x80010106)
        with patch.object(com_context.platform, "system", return_value="Windows"):
            with patch.object(com_context, "haal_com_bibliotheek_van_windows_op", return_value=bibliotheek):
                with com_context.houd_com_beschikbaar_tijdens_audioverbinding() as stand:
                    self.assertEqual(stand, "al_geinitialiseerd_met_andere_stand")
        bibliotheek.CoUninitialize.assert_not_called()

    def test_com_fout_behoudt_volledige_hexcode(self):
        bibliotheek = self.maak_nep_com(0x80004005)
        with patch.object(com_context.platform, "system", return_value="Windows"):
            with patch.object(com_context, "haal_com_bibliotheek_van_windows_op", return_value=bibliotheek):
                with self.assertRaisesRegex(com_context.WindowsComInitialisatieFout, "0x80004005"):
                    with com_context.houd_com_beschikbaar_tijdens_audioverbinding():
                        pass
        bibliotheek.CoUninitialize.assert_not_called()
