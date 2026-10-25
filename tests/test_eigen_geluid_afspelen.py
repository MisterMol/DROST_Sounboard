"""Test starten, stoppen en exception-registratie met een nep-WASAPI-apparaat."""

from pathlib import Path
import logging
import struct
import threading
import unittest
from unittest.mock import Mock

from app.audio.apparatenbeheer import GevondenAudioapparaat
from app.audio.geluid_afspelen import (
    GeluidAfspelenFout,
    speel_voorbereid_geluid_naar_de_virtuele_kabel,
)
from app.audio.geluidsbestanden import VoorbereidGeluidsfragment


class LogberichtenVerzamelaar(logging.Handler):
    def __init__(self):
        super().__init__()
        self.gebeurtenissen = []
        self.logregels = []

    def emit(self, logregel):
        self.gebeurtenissen.append(getattr(logregel, "gebeurtenis", "onbekend"))
        self.logregels.append(logregel)


class NepUitvoerStream:
    def __init__(self, stop_na_eerste_blok=False, stoppen_via=None, fout_in_stream=False, fout_na_stream=False, **instellingen):
        self.blokken = []
        self.als_geannuleerd = False
        self.stop_na_eerste_blok = stop_na_eerste_blok
        self.stoppen_via = stoppen_via
        self.fout_in_stream = fout_in_stream
        self.fout_na_stream = fout_na_stream

    def __enter__(self):
        return self

    def __exit__(self, soort_fout, fout, traceback):
        if self.fout_na_stream:
            raise RuntimeError("PortAudio sluit de geluidskaart onverwacht af")
        return False

    def write(self, blok):
        if self.fout_in_stream:
            raise OSError("Windows heeft de geluidskaart losgekoppeld")
        self.blokken.append(blok)
        if self.stop_na_eerste_blok and self.stoppen_via is not None:
            self.stoppen_via.set()
        return False

    def abort(self, ignore_errors=True):
        self.als_geannuleerd = True

    def stop(self, ignore_errors=True):
        return None


class NepAudioBibliotheek:
    def __init__(self, stop_na_eerste_blok=False, stoppen_via=None, fout_in_stream=False, fout_na_stream=False):
        self.gekozen_stroom = None
        self.stop_na_eerste_blok = stop_na_eerste_blok
        self.stoppen_via = stoppen_via
        self.fout_in_stream = fout_in_stream
        self.fout_na_stream = fout_na_stream
        self.aantal_vooraf_controles = 0

    def check_output_settings(self, **instellingen):
        self.aantal_vooraf_controles += 1
        if instellingen["device"] != 21:
            raise AssertionError("Niet het bedoelde apparaat")

    def RawOutputStream(self, **instellingen):
        self.gekozen_stroom = NepUitvoerStream(
            self.stop_na_eerste_blok, self.stoppen_via,
            self.fout_in_stream, self.fout_na_stream, **instellingen,
        )
        return self.gekozen_stroom


class TestEigenGeluidAfspelen(unittest.TestCase):
    def setUp(self):
        self.apparaat = GevondenAudioapparaat(
            21, "CABLE Input (VB-Audio Virtual Cable)", "Windows WASAPI", 0, 2
        )
        self.geluid = VoorbereidGeluidsfragment(
            naam_van_het_geluid="ping",
            bestandspad=Path("ping.wav"),
            vingerafdruk_van_audio="12345",
            ruwe_float32_stereo_audio=struct.pack("<ff", 0.1, 0.1) * 2500,
            aantal_frames=2500,
            oorspronkelijke_samplefrequentie=48000,
            oorspronkelijke_aantal_kanalen=1,
            ingesteld_volume=0.35,
        )
        self.softwarelogboek = logging.getLogger("test.audio.soft")
        self.auditlogboek = logging.getLogger("test.audio.audit")
        self.auditlogboek.setLevel(logging.INFO)
        self.handler = LogberichtenVerzamelaar()
        self.auditlogboek.addHandler(self.handler)

    def tearDown(self):
        self.auditlogboek.removeHandler(self.handler)

    def speel_af(self, bibliotheek, stopsignaal=None):
        return speel_voorbereid_geluid_naar_de_virtuele_kabel(
            audiobibliotheek=bibliotheek,
            uitvoerapparaat=self.apparaat,
            voorbereid_geluid=self.geluid,
            softwarelogboek=self.softwarelogboek,
            auditlogboek=self.auditlogboek,
            signaal_om_te_stoppen=stopsignaal or threading.Event(),
        )

    def test_volledige_afronding_heeft_start_stop_en_duur(self):
        resultaat = self.speel_af(NepAudioBibliotheek())
        self.assertEqual(resultaat.resultaat, "volledig_aangeleverd")
        self.assertEqual(resultaat.aantal_verstuurde_frames, 2500)
        self.assertEqual(self.handler.gebeurtenissen, ["geluid_gestart", "geluid_gestopt"])
        start = self.handler.logregels[0].gegevens
        einde = self.handler.logregels[1].gegevens
        self.assertEqual(start["afspeelbeurt_id"], einde["afspeelbeurt_id"])
        self.assertEqual(start["naam"], "ping")
        self.assertEqual(einde["aangeleverde_audio_seconden"], round(2500 / 48000, 3))

    def test_handmatig_stoppen_logt_verzoek_en_slaat_rest_over(self):
        stopsignaal = threading.Event()
        bibliotheek = NepAudioBibliotheek(stop_na_eerste_blok=True, stoppen_via=stopsignaal)
        resultaat = self.speel_af(bibliotheek, stopsignaal)
        self.assertEqual(resultaat.resultaat, "handmatig_gestopt")
        self.assertTrue(bibliotheek.gekozen_stroom.als_geannuleerd)
        self.assertEqual(resultaat.aantal_verstuurde_frames, 1024)
        self.assertEqual(self.handler.logregels[-1].gegevens["stopreden"], "gebruikersverzoek")

    def test_al_gestopt_signaal_opent_geen_apparaat(self):
        stopsignaal = threading.Event()
        stopsignaal.set()
        bibliotheek = NepAudioBibliotheek()
        resultaat = self.speel_af(bibliotheek, stopsignaal)
        self.assertEqual(resultaat.resultaat, "voor_start_geannuleerd")
        self.assertEqual(bibliotheek.aantal_vooraf_controles, 0)
        self.assertEqual(self.handler.gebeurtenissen, [])

    def test_fout_na_gestarte_audio_krijgt_stop_audit_met_mislukt(self):
        with self.assertRaisesRegex(OSError, "losgekoppeld"):
            self.speel_af(NepAudioBibliotheek(fout_in_stream=True))
        self.assertEqual(self.handler.gebeurtenissen, ["geluid_gestart", "geluid_gestopt"])
        self.assertEqual(self.handler.logregels[-1].gegevens["resultaat"], "mislukt")
        self.assertEqual(self.handler.logregels[-1].gegevens["fouttype"], "OSError")

    def test_fout_bij_afsluiten_stream_is_geen_succes(self):
        with self.assertRaisesRegex(RuntimeError, "PortAudio sluit"):
            self.speel_af(NepAudioBibliotheek(fout_na_stream=True))
        self.assertEqual(self.handler.logregels[-1].gegevens["resultaat"], "mislukt")

    def test_fout_bij_stoppen_van_de_driver_wordt_niet_als_succes_gelogd(self):
        class NepBibliotheekMetKapotteStop(NepAudioBibliotheek):
            def RawOutputStream(self, **instellingen):
                stroom = super().RawOutputStream(**instellingen)
                def geef_driverfout_bij_stop(ignore_errors=True):
                    if not ignore_errors:
                        raise OSError("PortAudio geeft fout bij stoppen")
                stroom.stop = geef_driverfout_bij_stop
                return stroom

        with self.assertRaisesRegex(OSError, "fout bij stoppen"):
            self.speel_af(NepBibliotheekMetKapotteStop())
        self.assertEqual(self.handler.logregels[-1].gegevens["resultaat"], "mislukt")

    def test_geen_audio_naar_verkeerde_apparaat(self):
        verkeerd_apparaat = GevondenAudioapparaat(19, "Luidsprekers (Razer USB Sound Card)", "Windows WASAPI", 0, 2)
        bibliotheek = NepAudioBibliotheek()
        with self.assertRaisesRegex(GeluidAfspelenFout, "AFSPELEN-002"):
            speel_voorbereid_geluid_naar_de_virtuele_kabel(
                audiobibliotheek=bibliotheek,
                uitvoerapparaat=verkeerd_apparaat,
                voorbereid_geluid=self.geluid,
                softwarelogboek=self.softwarelogboek,
                auditlogboek=self.auditlogboek,
                signaal_om_te_stoppen=threading.Event(),
            )
        self.assertEqual(bibliotheek.aantal_vooraf_controles, 0)


if __name__ == "__main__":
    unittest.main()
