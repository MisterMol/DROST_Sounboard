"""Tests voor fase 2 met nagebootste drivers, zonder microfoontoestemming."""

from __future__ import annotations

import logging
from pathlib import Path
import threading
import time
import unittest
from unittest.mock import MagicMock, patch

import numpy as np

from app.audio.apparatenbeheer import GevondenAudioapparaat
from app.audio.geluidsbestanden import VoorbereidGeluidsfragment
from app.audio.live_audiomixer import (
    LiveAudiomixer,
    LiveVerbindingFout,
    controleer_of_microfoon_een_echt_opnameapparaat_is,
    kies_het_juiste_aantal_microfoonkanalen,
    maak_stereoblok_met_microfoon,
)


def nep_microfoon(naam="Microfoon (Razer USB Sound Card)", kanalen=2):
    return GevondenAudioapparaat(24, naam, "Windows WASAPI", kanalen, 0)


def nep_kabel():
    return GevondenAudioapparaat(21, "CABLE Input (VB-Audio Virtual Cable)", "Windows WASAPI", 0, 2)


def maak_nep_wav():
    samples = np.full((240, 2), 0.1, dtype=np.float32)
    return VoorbereidGeluidsfragment(
        naam_van_het_geluid="Geluid A",
        bestandspad=Path("a.wav"),
        vingerafdruk_van_audio="gecontroleerd_wav",
        ruwe_float32_stereo_audio=samples.tobytes(),
        aantal_frames=len(samples),
        oorspronkelijke_samplefrequentie=48000,
        oorspronkelijke_aantal_kanalen=2,
        ingesteld_volume=0.35,
    )


class NepAudiostroom:
    def __init__(self, callback, fout_bij_starten=False, fout_bij_sluiten=False):
        self.callback = callback
        self.active = False
        self.fout_bij_starten = fout_bij_starten
        self.fout_bij_sluiten = fout_bij_sluiten
        self.gemengde_audio = []
        self._achtergronddraad = None

    def start(self):
        if self.fout_bij_starten:
            raise RuntimeError("NEP-DRIVER: Stream.start is mislukt")
        self.active = True
        self._achtergronddraad = threading.Thread(target=self._maak_nep_blokken, daemon=True)
        self._achtergronddraad.start()

    def _maak_nep_blokken(self):
        while self.active:
            uitvoer = np.zeros((240, 2), dtype=np.float32)
            microfoon = np.full((240, 1), 0.1, dtype=np.float32)
            self.callback(microfoon, uitvoer, 240, None, False)
            self.gemengde_audio.append(uitvoer.copy())
            time.sleep(0.006)

    def stop(self, ignore_errors=False):
        self.active = False
        if self._achtergronddraad is not None:
            self._achtergronddraad.join(timeout=1)

    def close(self, ignore_errors=False):
        if self.fout_bij_sluiten:
            raise RuntimeError("NEP-DRIVER: Stream.close is mislukt")


class NepBibliotheek:
    CallbackAbort = RuntimeError

    def __init__(self, faal_mono=False, faal_start=False, faal_sluiten=False):
        self.faal_mono = faal_mono
        self.faal_start = faal_start
        self.faal_sluiten = faal_sluiten
        self.gemaakte_stromen = []
        self.gebruikte_streaminstellingen = None

    def check_input_settings(self, **kwargs):
        if self.faal_mono and kwargs["channels"] == 1:
            raise RuntimeError("NEP-DRIVER: mono niet beschikbaar")

    def check_output_settings(self, **kwargs):
        return None

    def Stream(self, **kwargs):
        self.gebruikte_streaminstellingen = kwargs
        nieuwe_stroom = NepAudiostroom(kwargs["callback"], self.faal_start, self.faal_sluiten)
        self.gemaakte_stromen.append(nieuwe_stroom)
        return nieuwe_stroom


def wacht_op_verbindingsstatus(mixer, gewenste_toestand, maximaal=1.5):
    starttijd = time.monotonic()
    while time.monotonic() - starttijd < maximaal:
        if mixer.geef_huidige_status().toestand == gewenste_toestand:
            return True
        time.sleep(0.01)
    return False


class TestVeiligeApparaatkeuze(unittest.TestCase):
    def test_virtuele_cable_output_mag_nooit_je_microfoon_zijn(self):
        met_fout_apparaat = GevondenAudioapparaat(
            23, "CABLE Output (VB-Audio Virtual Cable)", "Windows WASAPI", 2, 0
        )
        with self.assertRaisesRegex(LiveVerbindingFout, "LIVE-002"):
            controleer_of_microfoon_een_echt_opnameapparaat_is(met_fout_apparaat)

    def test_ontbrekende_microfoon_geeft_herkenbare_foutcode(self):
        with self.assertRaisesRegex(LiveVerbindingFout, "LIVE-001"):
            controleer_of_microfoon_een_echt_opnameapparaat_is(None)

    def test_automatisch_stereo_als_driver_mono_niet_accepteert(self):
        gekozen = kies_het_juiste_aantal_microfoonkanalen(
            NepBibliotheek(faal_mono=True), nep_microfoon()
        )
        self.assertEqual(gekozen, 2)

    def test_stereo_wordt_geweigerd_als_apparaat_maar_een_kanaal_heeft(self):
        met_fout = NepBibliotheek(faal_mono=True)
        with self.assertRaisesRegex(LiveVerbindingFout, "LIVE-003"):
            kies_het_juiste_aantal_microfoonkanalen(met_fout, nep_microfoon(kanalen=1))


class TestGeluidMengen(unittest.TestCase):
    def test_eenkanaals_microfoon_komt_op_links_en_rechts(self):
        stem = np.asarray([[0.5], [-0.25]], dtype=np.float32)
        uitvoer = np.zeros((2, 2), dtype=np.float32)
        maak_stereoblok_met_microfoon(stem, uitvoer)
        np.testing.assert_allclose(uitvoer, [[0.4, 0.4], [-0.2, -0.2]])

    def test_stereomicrofoon_blijft_stereo(self):
        stem = np.asarray([[0.2, -0.3]], dtype=np.float32)
        uitvoer = np.zeros((1, 2), dtype=np.float32)
        maak_stereoblok_met_microfoon(stem, uitvoer)
        np.testing.assert_allclose(uitvoer, [[0.16, -0.24]])

    def test_onjuiste_aantallen_frames_krijgen_herkenbare_fout(self):
        with self.assertRaisesRegex(LiveVerbindingFout, "LIVE-005"):
            maak_stereoblok_met_microfoon(
                np.zeros((4, 1), dtype=np.float32), np.zeros((5, 2), dtype=np.float32)
            )


class TestLiveVerbinding(unittest.TestCase):
    def setUp(self):
        self.nepbibliotheek = NepBibliotheek()
        self.audit = MagicMock(spec=logging.Logger)
        self.software = MagicMock(spec=logging.Logger)
        self.mixer = LiveAudiomixer(self.nepbibliotheek, self.software, self.audit)

    def tearDown(self):
        self.mixer.verbreek_de_verbinding()
        self.assertTrue(self.mixer.wacht_tot_verbinding_echt_weg_is())

    def audit_gebeurtenissen(self):
        return [
            regel.kwargs.get("extra", {}).get("gebeurtenis")
            for regel in self.audit.info.call_args_list
        ]

    def test_bij_begin_is_niemand_verbonden_en_zijn_effecten_uit(self):
        status = self.mixer.geef_huidige_status()
        self.assertEqual(status.toestand, "verbroken")
        self.assertFalse(status.geluidseffecten_aan)

    def test_na_verbinden_stem_naar_de_kabel_en_soundboard_staat_uit(self):
        self.mixer.verbind_de_microfoon_met_vb_cable(nep_microfoon(), nep_kabel())
        self.assertTrue(wacht_op_verbindingsstatus(self.mixer, "verbonden"))
        self.assertFalse(self.mixer.geef_huidige_status().geluidseffecten_aan)
        self.assertEqual(self.nepbibliotheek.gebruikte_streaminstellingen["device"], (24, 21))
        # Het geopende stream-object hoeft nog niet meteen zijn eerste blok
        # te hebben verwerkt als de andere werkdraad precies nu wordt gepland.
        begin = time.monotonic()
        while not self.nepbibliotheek.gemaakte_stromen[0].gemengde_audio:
            self.assertLess(time.monotonic() - begin, 1.0)
            time.sleep(0.005)
        self.assertGreater(np.max(self.nepbibliotheek.gemaakte_stromen[0].gemengde_audio[0]), 0)
        self.mixer.verbreek_de_verbinding()
        self.assertTrue(wacht_op_verbindingsstatus(self.mixer, "verbroken"))
        self.assertIn("verbinding_gestart", self.audit_gebeurtenissen())
        self.assertIn("verbinding_verbroken", self.audit_gebeurtenissen())

    def test_effect_kan_worden_afgespeeld_en_stem_blijft_doorlopen(self):
        self.mixer.verbind_de_microfoon_met_vb_cable(nep_microfoon(), nep_kabel())
        self.assertTrue(wacht_op_verbindingsstatus(self.mixer, "verbonden"))
        self.mixer.zet_geluidseffecten_aan_of_uit(True)
        tijd_eerste = time.monotonic()
        while not self.mixer.geef_huidige_status().geluidseffecten_aan:
            self.assertLess(time.monotonic() - tijd_eerste, 1)
            time.sleep(0.01)
        afspeelbeurt = self.mixer.speel_een_voorbereid_geluid(maak_nep_wav())
        time.sleep(0.07)
        self.mixer.stop_het_huidige_geluid()
        time.sleep(0.05)
        self.mixer.verbreek_de_verbinding()
        self.assertTrue(self.mixer.wacht_tot_verbinding_echt_weg_is())
        self.assertIn("geluid_gestart", self.audit_gebeurtenissen())
        self.assertIn("geluid_gestopt", self.audit_gebeurtenissen())
        extra_geluid_start = [
            regel.kwargs["extra"]["gegevens"]
            for regel in self.audit.info.call_args_list
            if regel.kwargs.get("extra", {}).get("gebeurtenis") == "geluid_gestart"
        ]
        self.assertEqual(extra_geluid_start[0]["afspeelbeurt_id"], afspeelbeurt)
        self.assertTrue(any(np.max(blok) >= 0.15 for blok in self.nepbibliotheek.gemaakte_stromen[0].gemengde_audio))

    def test_soundboard_uitzetten_onderbreekt_de_stem_niet(self):
        self.mixer.verbind_de_microfoon_met_vb_cable(nep_microfoon(), nep_kabel())
        self.assertTrue(wacht_op_verbindingsstatus(self.mixer, "verbonden"))
        self.mixer.zet_geluidseffecten_aan_of_uit(True)
        uiterste_tijd = time.monotonic() + 1
        while not self.mixer.geef_huidige_status().geluidseffecten_aan:
            self.assertLess(time.monotonic(), uiterste_tijd)
            time.sleep(0.01)
        self.mixer.zet_geluidseffecten_aan_of_uit(False)
        while self.mixer.geef_huidige_status().geluidseffecten_aan:
            self.assertLess(time.monotonic(), uiterste_tijd)
            time.sleep(0.01)
        # Een auditregel gaat via een aparte wachtrij naar een werkthread.
        # De audiotoestand verandert dus eerder dan de schijfregistratie.
        while "soundboard_uitgeschakeld" not in self.audit_gebeurtenissen():
            self.assertLess(time.monotonic(), uiterste_tijd)
            time.sleep(0.01)
        self.assertEqual(self.mixer.geef_huidige_status().toestand, "verbonden")
        self.assertFalse(self.mixer.geef_huidige_status().geluidseffecten_aan)

    def test_stop_knop_stopt_lang_geluid_maar_microfoon_blijft_verbonden(self):
        self.mixer.verbind_de_microfoon_met_vb_cable(nep_microfoon(), nep_kabel())
        self.assertTrue(wacht_op_verbindingsstatus(self.mixer, "verbonden"))
        self.mixer.zet_geluidseffecten_aan_of_uit(True)
        tijdslimiet = time.monotonic() + 2
        while not self.mixer.geef_huidige_status().geluidseffecten_aan:
            self.assertLess(time.monotonic(), tijdslimiet)
            time.sleep(0.01)
        lang_geluid = maak_nep_wav()
        # Maak dit effect bewust langer dan één blok, zodat Stop echt midden
        # in het geluid moet ingrijpen in plaats van na een natuurlijke afloop.
        lang_samples = np.full((48000, 2), 0.1, dtype=np.float32)
        from dataclasses import replace
        lang_geluid = replace(
            lang_geluid,
            ruwe_float32_stereo_audio=lang_samples.tobytes(),
            aantal_frames=len(lang_samples),
        )
        self.mixer.speel_een_voorbereid_geluid(lang_geluid)
        while "geluid_gestart" not in self.audit_gebeurtenissen():
            self.assertLess(time.monotonic(), tijdslimiet)
            time.sleep(0.01)
        self.mixer.stop_het_huidige_geluid()
        while "geluid_gestopt" not in self.audit_gebeurtenissen():
            self.assertLess(time.monotonic(), tijdslimiet)
            time.sleep(0.01)
        stopgegevens = [
            regel.kwargs["extra"]["gegevens"]
            for regel in self.audit.info.call_args_list
            if regel.kwargs.get("extra", {}).get("gebeurtenis") == "geluid_gestopt"
        ]
        self.assertEqual(stopgegevens[0]["reden"], "handmatig_gestopt")
        self.assertLess(stopgegevens[0]["aangeleverde_audio_seconden"], 1.0)
        self.assertEqual(self.mixer.geef_huidige_status().toestand, "verbonden")

    def test_niet_afspelen_als_er_nog_geen_verbinding_is(self):
        with self.assertRaisesRegex(LiveVerbindingFout, "LIVE-012"):
            self.mixer.speel_een_voorbereid_geluid(maak_nep_wav())
        self.assertIn("geluid_geweigerd", self.audit_gebeurtenissen())

    def test_tweede_verbinding_wordt_niet_stiekem_geopend(self):
        self.mixer.verbind_de_microfoon_met_vb_cable(nep_microfoon(), nep_kabel())
        with self.assertRaisesRegex(LiveVerbindingFout, "LIVE-007"):
            self.mixer.verbind_de_microfoon_met_vb_cable(nep_microfoon(), nep_kabel())

    def test_fout_bij_openen_van_audiostroom_krijgt_software_traceback(self):
        nepbibliotheek = NepBibliotheek(faal_start=True)
        mixer = LiveAudiomixer(nepbibliotheek, self.software, self.audit)
        mixer.verbind_de_microfoon_met_vb_cable(nep_microfoon(), nep_kabel())
        self.assertTrue(wacht_op_verbindingsstatus(mixer, "fout"))
        self.assertTrue(mixer.wacht_tot_verbinding_echt_weg_is())
        self.assertIn("NEP-DRIVER", mixer.geef_huidige_status().laatst_bekende_fout)
        self.assertTrue(self.software.exception.called)
        self.assertIn("verbinding_mislukt", self.audit_gebeurtenissen())

    def test_fout_in_de_audio_callback_bewaart_originele_uitzondering(self):
        uitvoerbuffer = np.ones((2, 2), dtype=np.float32)
        with self.assertRaises(RuntimeError):
            self.mixer.verwerk_een_blok_live_audio(
                np.zeros((3, 1), dtype=np.float32), uitvoerbuffer, 2, None, False
            )
        self.assertTrue(self.mixer._stop_de_verbinding.is_set())
        self.assertIsInstance(self.mixer._fout_in_audio_callback, LiveVerbindingFout)
        np.testing.assert_array_equal(uitvoerbuffer, np.zeros((2, 2), dtype=np.float32))

    def test_niet_verbinden_als_uitvoer_de_fysieke_headset_is(self):
        verkeerde_uitvoer = GevondenAudioapparaat(
            19, "Luidsprekers (Razer USB Sound Card)", "Windows WASAPI", 0, 2
        )
        with self.assertRaisesRegex(Exception, "AFSPELEN-002"):
            self.mixer.verbind_de_microfoon_met_vb_cable(nep_microfoon(), verkeerde_uitvoer)
        self.assertEqual(self.mixer.geef_huidige_status().toestand, "verbroken")

    def test_soundboard_kan_niet_aangezet_worden_zonder_verbinding(self):
        with self.assertRaisesRegex(LiveVerbindingFout, "LIVE-010"):
            self.mixer.zet_geluidseffecten_aan_of_uit(True)

    def test_fout_bij_sluiten_mag_niet_succes_worden(self):
        nepbibliotheek = NepBibliotheek(faal_sluiten=True)
        mixer = LiveAudiomixer(nepbibliotheek, self.software, self.audit)
        mixer.verbind_de_microfoon_met_vb_cable(nep_microfoon(), nep_kabel())
        self.assertTrue(wacht_op_verbindingsstatus(mixer, "verbonden"))
        mixer.verbreek_de_verbinding()
        self.assertTrue(mixer.wacht_tot_verbinding_echt_weg_is())
        self.assertEqual(mixer.geef_huidige_status().toestand, "fout")
        self.assertIn("verbinding_afgebroken_met_fout", self.audit_gebeurtenissen())


class TestHerstelVanDeEchteMixer(unittest.TestCase):
    """Controleer de hele route van Verbinden tot aan automatisch herstel."""

    def test_doorsturen_werkt_na_twee_driverfouten_zonder_wav_te_kiezen(self):
        class NepBibliotheekMetTijdelijkeFouten(NepBibliotheek):
            def __init__(self):
                super().__init__()
                self.nog_te_weigeren_startpogingen = 2

            def Stream(self, **kwargs):
                nieuwe_stroom = super().Stream(**kwargs)
                gewone_startfunctie = nieuwe_stroom.start

                def start_met_een_mogelijke_driverfout():
                    if self.nog_te_weigeren_startpogingen > 0:
                        self.nog_te_weigeren_startpogingen -= 1
                        raise RuntimeError(
                            "PortAudioError [PaErrorCode -9999]: "
                            "WdmSyncIoctl: DeviceIoControl GLE = 0x00000006"
                        )
                    gewone_startfunctie()

                nieuwe_stroom.start = start_met_een_mogelijke_driverfout
                return nieuwe_stroom

        nepbibliotheek = NepBibliotheekMetTijdelijkeFouten()
        software = MagicMock(spec=logging.Logger)
        audit = MagicMock(spec=logging.Logger)
        mixer = LiveAudiomixer(nepbibliotheek, software, audit)
        with patch(
            "app.audio.automatisch_audioherstel.PAUZES_VOOR_HERSTEL_IN_SECONDEN",
            (0, 0, 0, 0, 0),
        ):
            mixer.verbind_de_microfoon_met_vb_cable(nep_microfoon(), nep_kabel())
            self.assertTrue(wacht_op_verbindingsstatus(mixer, "verbonden"))
        try:
            self.assertEqual(mixer.geef_huidige_status().huidige_startpoging, 3)
            self.assertEqual(len(nepbibliotheek.gemaakte_stromen), 3)
            self.assertTrue(all(
                not stroom.active for stroom in nepbibliotheek.gemaakte_stromen[:2]
            ))
            self.assertFalse(mixer.geef_huidige_status().geluidseffecten_aan)
            gebeurtenissen = [
                regel.kwargs.get("extra", {}).get("gebeurtenis")
                for regel in audit.info.call_args_list
            ]
            self.assertIn("audio_start_automatisch_hersteld", gebeurtenissen)
            self.assertIn("verbinding_gestart", gebeurtenissen)
            self.assertTrue(software.warning.called)
            self.assertTrue(any(
                regel.kwargs.get("extra", {}).get("gegevens", {}).get("aantal_startpogingen") == 3
                for regel in audit.info.call_args_list
                if regel.kwargs.get("extra", {}).get("gebeurtenis") == "verbinding_gestart"
            ))
        finally:
            mixer.verbreek_de_verbinding()
            self.assertTrue(mixer.wacht_tot_verbinding_echt_weg_is())
