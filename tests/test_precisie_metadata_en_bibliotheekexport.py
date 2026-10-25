"""Regressies voor precisieknippen, tekstvelden en draagbare ZIP-bibliotheken."""
from __future__ import annotations

from contextlib import closing
from io import BytesIO
import json
import os
from pathlib import Path
import sqlite3
from tempfile import TemporaryDirectory
import unittest
import wave
from zipfile import ZipFile

from app.audio.bronduur_en_golfvorm import maak_gedetailleerde_golfvorm_voor_tijdsvenster
from app.diagnostiek.logboek import maak_logboeken_klaar, sluit_logboeken_netjes_af
from app.webinterface.bediening_van_de_audiomotor import WebbedieningVanDrostSoundboard
from app.webinterface.bibliotheek_archieven import (
    OngeldigBibliotheekarchief, _controleer_archief,
    maak_draagbaar_bibliotheekarchief, importeer_draagbaar_bibliotheekarchief,
)
from app.webinterface.extra_geluidsinformatie import (
    BeheerVanExtraGeluidsinformatie, OngeldigeGeluidsinformatie,
)
from app.webinterface.favorieten_en_instellingen import controleer_afspeelinstellingen


class TestBibliotheekEnEditorPrecisie(unittest.TestCase):
    def setUp(self):
        self.tijdelijk = TemporaryDirectory()
        self.map = Path(self.tijdelijk.name)
        self.logs = maak_logboeken_klaar(self.map / 'logs')
        self.bediening = WebbedieningVanDrostSoundboard(object(), self.logs, self.map / 'bron.sqlite3')
        self.media = self.map / 'media'
        (self.media / 'geluiden').mkdir(parents=True)
        (self.media / 'afbeeldingen').mkdir(parents=True)
        self.wav = self.media / 'geluiden' / 'test.wav'
        with wave.open(str(self.wav), 'wb') as bron:
            bron.setnchannels(1)
            bron.setsampwidth(2)
            bron.setframerate(48000)
            bron.writeframes(b'\x00\x00' * 48000)
        self.geluid = self.bediening.geluidenbibliotheek.voeg_geluidsbestanden_toe([self.wav])[0]

    def tearDown(self):
        self.bediening.sluit_alle_audio_af()
        sluit_logboeken_netjes_af(self.logs)
        self.tijdelijk.cleanup()

    def test_fragment_van_een_milliseconde_en_nauwkeurige_golfvorm(self):
        instelling = controleer_afspeelinstellingen(.251, .3, .001)
        self.assertEqual(instelling.begint_bij_seconden, .251)
        self.assertEqual(instelling.maximale_duur_seconden, .001)
        waarden = maak_gedetailleerde_golfvorm_voor_tijdsvenster(self.wav, .251, .05, 300)
        self.assertEqual(len(waarden['pieken']), 300)

    def test_metadata_blijft_na_herstart_en_wordt_aan_bibliotheek_toegevoegd(self):
        self.bediening.extra_informatie.bewaar_informatie(
            self.geluid.geluid_id, 'Stem van Cartman', 'Respect my authoritah', 'south park, grap',
        )
        heropend = BeheerVanExtraGeluidsinformatie(self.bediening.geluidenbibliotheek.databasepad)
        extra = heropend.geef_alle_informatie()[self.geluid.geluid_id]
        self.assertEqual(extra.gesproken_tekst, 'Respect my authoritah')
        item = self.bediening.geef_geluidsbibliotheek()['geluiden'][0]
        self.assertEqual(item['beschrijving'], 'Stem van Cartman')
        self.assertEqual(item['zoekwoorden'], 'south park, grap')

    def test_foutieve_tekst_wordt_geweigerd_met_herleidbare_fout(self):
        with self.assertRaisesRegex(OngeldigeGeluidsinformatie, 'INFO-001'):
            self.bediening.extra_informatie.bewaar_informatie(self.geluid.geluid_id, 'x' * 2001, '', '')
        self.assertFalse(self.bediening.extra_informatie.geef_alle_informatie())

    def test_export_import_neemt_geluid_groep_favoriet_knip_en_gesproken_tekst_mee(self):
        groep = self.bediening.groepen.maak_groep('South Park')
        self.bediening.groepen.verander_lidmaatschap(groep, self.geluid.geluid_id, True)
        self.bediening.favorieten.zet_een_geluid_op_een_vaste_plek(5, self.geluid.geluid_id)
        self.bediening.favorieten.bewaar_afspeelinstellingen(self.geluid.geluid_id, .123, .42, .530)
        self.bediening.extra_informatie.bewaar_informatie(self.geluid.geluid_id,
            'Beschrijving met <b>HTML</b>', 'Dit is de tekst', 'cartman')
        zip_pad = maak_draagbaar_bibliotheekarchief(self.bediening, self.media, [self.geluid.geluid_id])
        try:
            with ZipFile(zip_pad) as bestand:
                manifest = json.loads(bestand.read('manifest.json'))
                self.assertEqual(manifest['geluiden'][0]['groepen'], ['South Park'])
                self.assertIn('geluiden/', manifest['geluiden'][0]['bron'])
            nieuwe_media = self.map / 'nieuw_media'
            doel = WebbedieningVanDrostSoundboard(object(), self.logs, self.map / 'nieuw.sqlite3')
            try:
                resultaat = importeer_draagbaar_bibliotheekarchief(doel, nieuwe_media, zip_pad)
                self.assertEqual(resultaat['aantal'], 1)
                nieuw = doel.geef_geluidsbibliotheek()['geluiden'][0]
                self.assertEqual(nieuw['fragmentduur'], .53)
                self.assertEqual(nieuw['beginpositie'], .123)
                self.assertEqual(nieuw['groep_ids'], [doel.groepen.geef_alle_groepen()[0]['id']])
                self.assertEqual(nieuw['gesproken_tekst'], 'Dit is de tekst')
                self.assertEqual(nieuw['beschrijving'], 'Beschrijving met <b>HTML</b>')
                self.assertEqual(doel.favorieten.geef_alle_favorietplekken()[4], nieuw['id'])
                self.assertTrue(Path(nieuwe_media / 'geluiden').is_dir())
            finally:
                doel.sluit_alle_audio_af()
        finally:
            zip_pad.unlink(missing_ok=True)

    def test_zip_kan_geen_bestanden_met_verdachte_paden_importeren(self):
        archiefbuffer = BytesIO()
        with ZipFile(archiefbuffer, 'w') as archief:
            archief.writestr('manifest.json', json.dumps({'type': 'DrostSoundboard', 'versie': 1,
                'geluiden': [{'naam': 'fout', 'bron': '../escape.wav'}]}))
            archief.writestr('../escape.wav', b'waarschijnlijk niet geldig')
        archiefbuffer.seek(0)
        with ZipFile(archiefbuffer) as archief:
            with self.assertRaisesRegex(OngeldigBibliotheekarchief, 'ARCH-012'):
                _controleer_archief(archief)
        self.assertFalse((self.map / 'escape.wav').exists())

    def test_mislukte_zip_import_rollt_eerdere_geluiden_terug(self):
        from uuid import uuid4
        importeer_db = self.map / 'mislukte.sqlite3'
        doel = WebbedieningVanDrostSoundboard(object(), self.logs, importeer_db)
        try:
            zip_pad = self.map / 'fout.zip'
            eerste = str(uuid4())
            tweede = str(uuid4())
            geluiden = []
            with ZipFile(zip_pad, 'w') as archief:
                for nummer, audio in [(eerste, self.wav.read_bytes()), (tweede, b'geen WAV')]:
                    naam = f'geluiden/{nummer}.wav'
                    archief.writestr(naam, audio)
                    geluiden.append({'naam': 'test', 'bron': naam, 'begin': 0.0,
                        'duur': 1.0, 'volume': .4, 'groepen': ['South Park']})
                archief.writestr('manifest.json', json.dumps({'type': 'DrostSoundboard', 'versie': 1,
                    'geluiden': geluiden}))
            with self.assertRaisesRegex(OngeldigBibliotheekarchief, 'ARCH-020'):
                importeer_draagbaar_bibliotheekarchief(doel, self.map / 'mislukt_media', zip_pad)
            self.assertEqual(doel.geluidenbibliotheek.geef_alle_geluiden(), [])
            self.assertEqual(doel.groepen.geef_alle_groepen(), [])
        finally:
            doel.sluit_alle_audio_af()

    def test_bulk_groepen_koppelen_is_atomair_en_werkt_na_restart(self):
        groep = self.bediening.groepen.maak_groep('Memes')
        with self.assertRaisesRegex(ValueError, 'GROEP-007'):
            self.bediening.groepen.voeg_meerdere_geluiden_toe_aan_groep(
                groep, [self.geluid.geluid_id, 'niet_bestaand'])
        self.assertEqual(self.bediening.groepen.geef_alle_groepen()[0]['aantal_geluiden'], 0)
        aantal = self.bediening.groepen.voeg_meerdere_geluiden_toe_aan_groep(
            groep, [self.geluid.geluid_id, self.geluid.geluid_id])
        self.assertEqual(aantal, 1)
        self.assertEqual(self.bediening.groepen.geef_alle_groepen()[0]['aantal_geluiden'], 1)

    def test_bulk_verwijderen_bewaart_bronbestanden_en_verwijdert_ook_extra_gegevens(self):
        self.bediening.extra_informatie.bewaar_informatie(self.geluid.geluid_id, 'Test', 'tekst', 'tag')
        self.bediening.favorieten.zet_een_geluid_op_een_vaste_plek(3, self.geluid.geluid_id)
        aantal = self.bediening.geluidenbibliotheek.haal_meerdere_geluiden_uit_de_bibliotheek([self.geluid.geluid_id])
        self.assertEqual(aantal, 1)
        self.assertTrue(self.wav.exists())
        self.assertEqual(self.bediening.favorieten.geef_alle_favorietplekken()[2], None)
        self.assertEqual(self.bediening.extra_informatie.geef_alle_informatie(), {})

    def test_lege_selectie_exporteert_alleen_manifest(self):
        pad = maak_draagbaar_bibliotheekarchief(self.bediening, self.media, [])
        try:
            with ZipFile(pad) as archief:
                self.assertEqual(archief.namelist(), ['manifest.json'])
        finally:
            pad.unlink(missing_ok=True)


if __name__ == '__main__':
    unittest.main()
