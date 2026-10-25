"""Favorieten moeten vijftien vaste posities behouden na herstart."""

from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from app.audio.geluidenbibliotheek import PersoonlijkeGeluidenbibliotheek
from app.webinterface.favorieten_en_instellingen import (
    AANTAL_FAVORIETE_PLEKKEN, OngeldigeFavorietOfInstelling,
    VasteFavorietenEnInstellingen, controleer_afspeelinstellingen,
)


class TestVasteFavorietenEnInstellingen(unittest.TestCase):
    def setUp(self):
        self.tijdelijke_map = TemporaryDirectory()
        self.map = Path(self.tijdelijke_map.name)
        self.pad = self.map / 'bibliotheek.sqlite3'
        self.bibliotheek = PersoonlijkeGeluidenbibliotheek(self.pad)
        self.favorieten = VasteFavorietenEnInstellingen(self.pad)
        self.eerste_bestand = self.map / 'geluid een.mp3'
        self.tweede_bestand = self.map / 'geluid twee.wav'
        self.eerste_bestand.write_bytes(b'geluid')
        self.tweede_bestand.write_bytes(b'geluid')
        self.eerste, self.tweede = self.bibliotheek.voeg_geluidsbestanden_toe([
            self.eerste_bestand, self.tweede_bestand,
        ])

    def tearDown(self):
        self.tijdelijke_map.cleanup()

    def test_er_zijn_altijd_exact_vijftien_plekken(self):
        self.assertEqual(AANTAL_FAVORIETE_PLEKKEN, 15)
        self.assertEqual(self.favorieten.geef_alle_favorietplekken(), [None] * 15)

    def test_favorieten_houden_positie_na_herstart(self):
        self.favorieten.zet_een_geluid_op_een_vaste_plek(3, self.eerste.geluid_id)
        heropend = VasteFavorietenEnInstellingen(self.pad)
        self.assertEqual(heropend.geef_alle_favorietplekken()[2], self.eerste.geluid_id)
        self.assertEqual(heropend.geef_alle_favorietplekken()[0], None)

    def test_verslepen_naar_bezette_plek_verwisselt_de_geluiden(self):
        self.favorieten.zet_een_geluid_op_een_vaste_plek(1, self.eerste.geluid_id)
        self.favorieten.zet_een_geluid_op_een_vaste_plek(2, self.tweede.geluid_id)
        self.favorieten.zet_een_geluid_op_een_vaste_plek(2, self.eerste.geluid_id)
        plekken = self.favorieten.geef_alle_favorietplekken()
        self.assertEqual(plekken[0], self.tweede.geluid_id)
        self.assertEqual(plekken[1], self.eerste.geluid_id)
        self.assertEqual(plekken.count(self.eerste.geluid_id), 1)

    def test_losse_favorieten_kunnen_verwisselen_en_leeggemaakt_worden(self):
        self.favorieten.zet_een_geluid_op_een_vaste_plek(15, self.eerste.geluid_id)
        self.favorieten.wissel_twee_favorietplekken(15, 1)
        self.assertEqual(self.favorieten.geef_alle_favorietplekken()[0], self.eerste.geluid_id)
        self.favorieten.maak_een_favorietplek_leeg(1)
        self.assertEqual(self.favorieten.geef_alle_favorietplekken(), [None] * 15)

    def test_ongeldige_plekken_worden_geweigerd(self):
        for plek in (0, 16, -1, True, None, '1'):
            with self.subTest(plek=plek), self.assertRaises(OngeldigeFavorietOfInstelling):
                self.favorieten.zet_een_geluid_op_een_vaste_plek(plek, self.eerste.geluid_id)

    def test_bestaande_bibliotheekwordt_niet_leeggemaakt(self):
        heropend = PersoonlijkeGeluidenbibliotheek(self.pad)
        self.assertEqual(len(heropend.geef_alle_geluiden()), 2)

    def test_instellingen_voor_120_seconden_blijven_bewaard(self):
        self.favorieten.bewaar_afspeelinstellingen(self.eerste.geluid_id, 15.5, 0.6, 120)
        opnieuw = VasteFavorietenEnInstellingen(self.pad)
        data = opnieuw.geef_instellingen_van_geluid(self.eerste.geluid_id)
        self.assertEqual((data.begint_bij_seconden, data.volume, data.maximale_duur_seconden), (15.5, 0.6, 120))
        self.assertEqual(opnieuw.geef_instellingen_van_geluid(self.tweede.geluid_id).maximale_duur_seconden, 120)

    def test_ongeldige_volume_duur_start_en_null_worden_geweigerd(self):
        for waarden in ((None,.35,120), (0,float('nan'),120),(0,.35,121),
                        (0,.35,0),(-1,.35,1),(0,2.5,1),(0,True,15)):
            with self.subTest(waarden=waarden), self.assertRaises(OngeldigeFavorietOfInstelling):
                controleer_afspeelinstellingen(*waarden)

    def test_oude_items_verliezen_favoriet_na_verwijderen(self):
        self.favorieten.zet_een_geluid_op_een_vaste_plek(1, self.eerste.geluid_id)
        self.favorieten.verwijder_referenties_naar_geluid(self.eerste.geluid_id)
        self.bibliotheek.haal_geluid_uit_de_bibliotheek(self.eerste.geluid_id)
        self.assertIsNone(self.favorieten.geef_alle_favorietplekken()[0])
        self.assertTrue(self.eerste_bestand.exists())


if __name__ == '__main__':
    unittest.main()
