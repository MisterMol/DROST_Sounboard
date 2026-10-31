"""De eigen namen blijven behouden na herstart, zonder bestanden te verwijderen."""

from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from app.audio.geluidenbibliotheek import (
    BibliotheekFout,
    PersoonlijkeGeluidenbibliotheek,
    bepaal_standaardlocatie_van_de_bibliotheek,
)


class TestPersoonlijkeGeluidenbibliotheek(unittest.TestCase):
    def setUp(self):
        self.tijdelijke_map = TemporaryDirectory()
        self.map = Path(self.tijdelijke_map.name)
        self.database = self.map / "persoonlijk.sqlite3"
        self.bibliotheek = PersoonlijkeGeluidenbibliotheek(self.database)

    def tearDown(self):
        self.tijdelijke_map.cleanup()

    def maak_audio(self, naam: str = "discord-call-sound.mp3") -> Path:
        bestand = self.map / naam
        bestand.write_bytes(b"test-audio")
        return bestand

    def test_toevoegen_en_heropenen_van_bibliotheek(self):
        bestand = self.maak_audio()
        toegevoegd = self.bibliotheek.voeg_geluidsbestanden_toe([bestand])
        heropend = PersoonlijkeGeluidenbibliotheek(self.database)
        uitkomst = heropend.geef_alle_geluiden()
        self.assertEqual(len(uitkomst), 1)
        self.assertEqual(uitkomst[0].geluid_id, toegevoegd[0].geluid_id)
        self.assertEqual(uitkomst[0].eigen_naam, "discord-call-sound")
        # Windows kan hetzelfde tijdelijke pad onder de korte 8.3-naam tonen.
        self.assertTrue(uitkomst[0].bestandspad.samefile(bestand))

    def test_opnieuw_toevoegen_maakt_geen_dubbele_regel(self):
        bestand = self.maak_audio()
        eerste = self.bibliotheek.voeg_geluidsbestanden_toe([bestand])
        tweede = self.bibliotheek.voeg_geluidsbestanden_toe([bestand])
        self.assertEqual(eerste[0].geluid_id, tweede[0].geluid_id)
        self.assertEqual(len(self.bibliotheek.geef_alle_geluiden()), 1)

    def test_eigen_naam_blijft_ook_na_opnieuw_importeren_bewaard(self):
        bestand = self.maak_audio()
        item = self.bibliotheek.voeg_geluidsbestanden_toe([bestand])[0]
        self.bibliotheek.verander_de_naam_van_een_geluid(item.geluid_id, "Discord oproep")
        self.bibliotheek.voeg_geluidsbestanden_toe([bestand])
        self.assertEqual(self.bibliotheek.geef_alle_geluiden()[0].eigen_naam, "Discord oproep")

    def test_verwijderen_laat_het_originele_bestand_staan(self):
        bestand = self.maak_audio()
        item = self.bibliotheek.voeg_geluidsbestanden_toe([bestand])[0]
        self.bibliotheek.haal_geluid_uit_de_bibliotheek(item.geluid_id)
        self.assertTrue(bestand.exists())
        self.assertEqual(self.bibliotheek.geef_alle_geluiden(), [])

    def test_onjuiste_geluidsnamen_worden_geweigerd(self):
        bestand = self.maak_audio()
        item = self.bibliotheek.voeg_geluidsbestanden_toe([bestand])[0]
        for waarde in (None, 5, "", "   ", "a\nb", "x" * 110):
            with self.subTest(waarde=waarde), self.assertRaises(BibliotheekFout):
                self.bibliotheek.verander_de_naam_van_een_geluid(item.geluid_id, waarde)

    def test_ontbrekend_geluidsnummer_geeft_een_duidelijke_fout(self):
        with self.assertRaisesRegex(BibliotheekFout, "BIB-009"):
            self.bibliotheek.verander_de_naam_van_een_geluid("bestaat-niet", "Voorbeeld")
        with self.assertRaisesRegex(BibliotheekFout, "BIB-012"):
            self.bibliotheek.haal_geluid_uit_de_bibliotheek("bestaat-niet")

    def test_meerdere_importeren_geeft_een_lijst_van_items(self):
        bestanden = [self.maak_audio("een.mp3"), self.maak_audio("twee.wav")]
        toegevoegd = self.bibliotheek.voeg_geluidsbestanden_toe(bestanden)
        self.assertEqual(len(toegevoegd), 2)
        self.assertEqual(len(self.bibliotheek.geef_alle_geluiden()), 2)

    def test_lege_import_en_onjuist_type(self):
        self.assertEqual(self.bibliotheek.voeg_geluidsbestanden_toe([]), [])
        with self.assertRaisesRegex(BibliotheekFout, "BIB-005"):
            self.bibliotheek.voeg_geluidsbestanden_toe("enkel-pad.mp3")

    def test_ongeldige_import_voert_geen_half_afgemaakte_import_uit(self):
        geldig = self.maak_audio()
        with self.assertRaises(ValueError):
            self.bibliotheek.voeg_geluidsbestanden_toe([geldig, self.map / "niet_gevonden.wav"])
        self.assertEqual(self.bibliotheek.geef_alle_geluiden(), [])


if __name__ == "__main__":
    unittest.main()
