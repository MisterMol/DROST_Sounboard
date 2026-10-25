"""Verifieer dat de aparte CABLE Output-proef geluid kan onderscheiden van stilte."""

from __future__ import annotations

import unittest
import numpy as np

from app.audio.apparatenbeheer import GevondenAudioapparaat
from app.audio.kabel_ontvangstmeting import (
    CableOntvangstFout,
    ResultaatVanCableOntvangstmeting,
    meet_signaal_en_herken_controletoon,
    meet_echt_ontvangen_signaal_van_cable_output,
)


def maak_een_toonsignaal_voor_test(frequentie=660, amplitude=.2, stereo=False):
    """Een gecontroleerde synthetische testtoon, zonder Windows-audio."""
    sampleposities = np.arange(4800, dtype=np.float32)
    mono = (amplitude * np.sin(2 * np.pi * frequentie * sampleposities / 48_000)).astype(
        np.float32
    )
    if stereo:
        return np.column_stack((mono, mono)).astype(np.float32)
    return mono.reshape((-1, 1))


class TestDeOpnamekantApartControleren(unittest.TestCase):
    def test_echte_660_hertz_toon_wordt_herkend(self):
        resultaat = meet_signaal_en_herken_controletoon(maak_een_toonsignaal_voor_test())
        self.assertTrue(resultaat.controletoon_herkend)
        self.assertGreater(resultaat.sterkte_van_controletoon, .19)

    def test_stilte_is_geen_gevonden_toon(self):
        resultaat = meet_signaal_en_herken_controletoon(np.zeros((4800, 2), dtype=np.float32))
        self.assertEqual(resultaat.effectieve_sterkte, 0)
        self.assertFalse(resultaat.controletoon_herkend)

    def test_toevallige_andere_toon_bewijst_niets(self):
        resultaat = meet_signaal_en_herken_controletoon(maak_een_toonsignaal_voor_test(540))
        self.assertFalse(resultaat.controletoon_herkend)

    def test_tegengestelde_stereokanalen_worden_niet_weggemiddeld(self):
        audio = maak_een_toonsignaal_voor_test()[:, 0]
        resultaat = meet_signaal_en_herken_controletoon(np.column_stack((audio, -audio)))
        self.assertTrue(resultaat.controletoon_herkend)

    def test_nan_wordt_niet_als_normaal_geluid_beschouwd(self):
        audio = maak_een_toonsignaal_voor_test()
        audio[1, 0] = np.nan
        with self.assertRaisesRegex(CableOntvangstFout, "ONTVANGST-004"):
            meet_signaal_en_herken_controletoon(audio)

    def test_geen_volledige_samples_levert_duidelijke_fout_op(self):
        with self.assertRaisesRegex(CableOntvangstFout, "ONTVANGST-003"):
            meet_signaal_en_herken_controletoon(np.zeros((0, 1), dtype=np.float32))

    def test_onverwacht_type_heeft_duidelijke_foutcode(self):
        with self.assertRaisesRegex(CableOntvangstFout, "ONTVANGST-001"):
            meet_signaal_en_herken_controletoon(None)

    def test_opgenomen_data_wordt_niet_in_meetresultaat_bewaard(self):
        meting = ResultaatVanCableOntvangstmeting()
        opname = maak_een_toonsignaal_voor_test()
        meting.voeg_nieuwe_meting_toe(meet_signaal_en_herken_controletoon(opname), len(opname), False)
        self.assertEqual(meting.aantal_ontvangen_frames, 4800)
        self.assertFalse(hasattr(meting, "opgenomen_audio"))
        self.assertFalse(meting.is_de_controletoon_echt_ontvangen)  # één blok is onvoldoende

    def test_drie_goede_blokken_bevestigen_de_ontvangen_toon(self):
        meting = ResultaatVanCableOntvangstmeting()
        blok = maak_een_toonsignaal_voor_test()
        for _ in range(3):
            meting.voeg_nieuwe_meting_toe(meet_signaal_en_herken_controletoon(blok), len(blok), False)
        self.assertTrue(meting.is_de_controletoon_echt_ontvangen)

    def test_losse_korte_toonflitsen_bewijzen_niet_dat_de_kabel_werkt(self):
        meting = ResultaatVanCableOntvangstmeting()
        toon = maak_een_toonsignaal_voor_test()
        stilte = np.zeros((4800, 1), dtype=np.float32)
        for blok in (toon, stilte, toon, stilte, toon):
            meting.voeg_nieuwe_meting_toe(meet_signaal_en_herken_controletoon(blok), len(blok), False)
        self.assertEqual(meting.aantal_blokken_met_controletoon, 3)
        self.assertEqual(meting.langste_reeks_herkende_toonblokken, 1)
        self.assertFalse(meting.is_de_controletoon_echt_ontvangen)

    def test_ongeldige_duur_wordt_van_tevoren_geweigerd(self):
        with self.assertRaisesRegex(CableOntvangstFout, "ONTVANGST-009"):
            meet_echt_ontvangen_signaal_van_cable_output(None, [], duur_in_seconden=0)

    def test_we_lezen_echt_het_opnameapparaat_en_niet_de_afspeelkant(self):
        class NepOpnameStream:
            def __init__(self, instellingen):
                self.instellingen = instellingen
            def __enter__(self):
                return self
            def __exit__(self, exception_type, exception_value, traceback):
                return False
            def read(self, frames):
                assert frames == 4800
                return maak_een_toonsignaal_voor_test(), False

        class NepAudiobibliotheek:
            def __init__(self):
                self.gecontroleerde_invoer = None

            def check_input_settings(self, **instellingen):
                self.gecontroleerde_invoer = instellingen

            def InputStream(self, **instellingen):
                self.open_invoer = instellingen
                return NepOpnameStream(instellingen)

        kabelinput = GevondenAudioapparaat(21, "CABLE Input (VB-Audio Virtual Cable)", "Windows WASAPI", 0, 2)
        kabeloutput = GevondenAudioapparaat(23, "CABLE Output (VB-Audio Virtual Cable)", "Windows WASAPI", 2, 0)
        nepbibliotheek = NepAudiobibliotheek()
        meting, apparaat = meet_echt_ontvangen_signaal_van_cable_output(
            nepbibliotheek,
            [kabelinput, kabeloutput],
            toon_resultaat=lambda tekst: None,
            duur_in_seconden=1,
        )
        self.assertTrue(meting.is_de_controletoon_echt_ontvangen)
        self.assertEqual(apparaat.huidig_apparaatnummer, 23)
        self.assertEqual(nepbibliotheek.open_invoer["device"], 23)
        self.assertEqual(meting.aantal_ontvangen_frames, 48000)


if __name__ == "__main__":
    unittest.main()
