"""Regressies voor de bibliotheekacties, losse afbeeldingsdownloads en 200% volume."""
from __future__ import annotations

import json
import os
from pathlib import Path
from tempfile import TemporaryDirectory
import threading
import unittest
from urllib.request import Request, urlopen
from uuid import uuid4

import numpy as np
from PIL import Image
import soundfile as sf

from app.audio.geluidsbestanden import versterk_samples_zonder_digitaal_te_oversturen
from app.audio.mp3_en_wav_fragmenten import lees_en_bereid_mp3_of_wav_voor
from app.diagnostiek.logboek import maak_logboeken_klaar, sluit_logboeken_netjes_af
from app.webinterface.bediening_van_de_audiomotor import WebbedieningVanDrostSoundboard
from app.webinterface.favorieten_en_instellingen import (
    OngeldigeFavorietOfInstelling, controleer_afspeelinstellingen,
)
from app.webinterface.losse_media_exporteren import (
    exporteer_geluid_als_los_bestand, geef_mogelijke_exportformaten,
)
from app.webinterface.lokale_webserver import LokaleWebserverVanDrostSoundboard


class TestSnelleBibliotheekacties(unittest.TestCase):
    def setUp(self):
        self.temporary = TemporaryDirectory()
        self.map = Path(self.temporary.name)
        self.oude_appdata = os.environ.get('LOCALAPPDATA')
        os.environ['LOCALAPPDATA'] = str(self.map)
        self.logs = maak_logboeken_klaar(self.map / 'logs')
        self.bediening = WebbedieningVanDrostSoundboard(object(), self.logs, self.map / 'bibliotheek.db')
        self.server = LokaleWebserverVanDrostSoundboard(('127.0.0.1', 0), self.bediening)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.url = f'http://127.0.0.1:{self.server.server_port}'
        bron = self.server.media_map / 'geluiden' / 'test.wav'
        sf.write(bron, np.full(4800, 0.15, dtype=np.float32), 48000, subtype='PCM_16')
        self.item = self.bediening.geluidenbibliotheek.voeg_geluidsbestanden_toe([bron])[0]

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=3)
        self.bediening.sluit_alle_audio_af()
        sluit_logboeken_netjes_af(self.logs)
        if self.oude_appdata is None:
            os.environ.pop('LOCALAPPDATA', None)
        else:
            os.environ['LOCALAPPDATA'] = self.oude_appdata
        self.temporary.cleanup()

    def test_nieuwe_geluiden_standaard_op_100_procent_en_boost_tot_200(self):
        id = self.item.geluid_id
        self.assertEqual(self.bediening.favorieten.geef_instellingen_van_geluid(id).volume, 1.0)
        self.bediening.favorieten.bewaar_afspeelinstellingen(id, 0.01, 2, 0.07)
        opnieuw = self.bediening.favorieten.geef_instellingen_van_geluid(id)
        self.assertEqual((opnieuw.volume, opnieuw.begint_bij_seconden, opnieuw.maximale_duur_seconden), (2, .01, .07))
        for verkeerd in (-.01, 2.01, float('inf'), True, None):
            with self.subTest(verkeerd=verkeerd), self.assertRaises(OngeldigeFavorietOfInstelling):
                controleer_afspeelinstellingen(0, verkeerd, 1)

    def test_bestaand_handmatig_volume_blijft_bewaard_totdat_gebruiker_wijzigt(self):
        id = self.item.geluid_id
        self.bediening.favorieten.bewaar_afspeelinstellingen(id, .012, .35, .065)
        self.assertEqual(self.bediening.favorieten.geef_instellingen_van_geluid(id).volume, .35)
        aantal = self.bediening.favorieten.zet_volumes_van_geluiden_in_een_keer([id], 1.0)
        self.assertEqual(aantal, 1)
        gegevens = self.bediening.favorieten.geef_instellingen_van_geluid(id)
        self.assertEqual((gegevens.volume, gegevens.begint_bij_seconden, gegevens.maximale_duur_seconden), (1.0, .012, .065))

    def test_meerdere_volumes_worden_alleen_samen_aangepast(self):
        bestaand = self.item.geluid_id
        self.bediening.favorieten.bewaar_afspeelinstellingen(bestaand, 0, .25, .08)
        with self.assertRaises(OngeldigeFavorietOfInstelling):
            self.bediening.favorieten.zet_volumes_van_geluiden_in_een_keer([bestaand, str(uuid4())], 1.0)
        self.assertEqual(self.bediening.favorieten.geef_instellingen_van_geluid(bestaand).volume, .25)

    def test_http_meerdere_geluiden_op_100_en_auditlog(self):
        gegevens = json.dumps({'geluid_ids': [self.item.geluid_id], 'volume': 1.0}).encode('utf-8')
        verzoek = Request(self.url + '/api/bibliotheek/volume', data=gegevens, method='POST', headers={
            'Content-Type': 'application/json', 'X-Drost-Token': self.server.schrijf_token,
        })
        with urlopen(verzoek, timeout=5) as antwoord:
            self.assertEqual(antwoord.status, 200)
            self.assertEqual(json.loads(antwoord.read())['aantal'], 1)

    def test_echte_afbeelding_wordt_als_origineel_bestand_gedownload(self):
        afbeelding = self.server.media_map / 'afbeeldingen' / f'{uuid4()}.png'
        Image.new('RGB', (17, 11), 'teal').save(afbeelding)
        id = self.item.geluid_id
        self.bediening.favorieten.bewaar_afbeelding_voor_geluid(id, afbeelding.name)
        formaat = geef_mogelijke_exportformaten(self.bediening, self.server.media_map, id)
        self.assertEqual(formaat, ['mp3', 'afbeelding'])
        pad, naam, soort, duur = exporteer_geluid_als_los_bestand(
            self.bediening, self.server.media_map, id, 'afbeelding')
        try:
            self.assertEqual(naam.split('.')[-1], 'png')
            self.assertEqual(soort, 'image/png')
            self.assertEqual(pad.read_bytes(), afbeelding.read_bytes())
            self.assertEqual(duur, 0)
        finally:
            pad.unlink(missing_ok=True)
        self.assertIn('afbeelding', self.bediening.geef_geluidsbibliotheek()['geluiden'][0]['exportformaten'])

    def test_http_kan_gekoppelde_afbeelding_direct_downloaden(self):
        """De downloadknop moet echte bytes sturen, niet alleen een knop tonen.

        Dit is belangrijk omdat een lokale PNG wel in het menu kan staan,
        terwijl een ontbrekende Content-Type of een fout in de HTTP-route
        alsnog een kapot downloadbestand zou opleveren.
        """
        afbeelding = self.server.media_map / 'afbeeldingen' / f'{uuid4()}.png'
        Image.new('RGB', (21, 13), 'navy').save(afbeelding)
        geluid_id = self.item.geluid_id
        self.bediening.favorieten.bewaar_afbeelding_voor_geluid(geluid_id, afbeelding.name)
        verzoek = Request(
            self.url + f'/api/geluiden/{geluid_id}/exporteer',
            data=json.dumps({'formaat': 'afbeelding', 'begin': None, 'duur': None}).encode('utf-8'),
            method='POST', headers={
                'Content-Type': 'application/json',
                'X-Drost-Token': self.server.schrijf_token,
            },
        )
        with urlopen(verzoek, timeout=5) as antwoord:
            self.assertEqual(antwoord.status, 200)
            self.assertEqual(antwoord.headers.get_content_type(), 'image/png')
            self.assertIn('attachment', antwoord.headers['Content-Disposition'])
            self.assertEqual(antwoord.read(), afbeelding.read_bytes())

    def test_gif_wordt_alleen_aangeboden_als_koppeling_echt_bestaat(self):
        gif = self.server.media_map / 'afbeeldingen' / f'{uuid4()}.gif'
        Image.new('RGB', (16, 16), 'blue').save(gif, format='GIF')
        self.bediening.favorieten.bewaar_afbeelding_voor_geluid(self.item.geluid_id, gif.name)
        opties = geef_mogelijke_exportformaten(self.bediening, self.server.media_map, self.item.geluid_id)
        self.assertEqual(opties, ['mp3', 'mp4', 'gif'])
        gif.unlink()
        self.assertEqual(geef_mogelijke_exportformaten(
            self.bediening, self.server.media_map, self.item.geluid_id), ['mp3'])

    def test_200_procent_versterking_werkt_ook_echt_zonder_hard_afknippen(self):
        geluid = np.array([[-.25, .1], [.5, -.4], [.25, .1]], dtype=np.float32)
        sterker = versterk_samples_zonder_digitaal_te_oversturen(geluid.copy(), 2.0)
        self.assertAlmostEqual(float(np.max(np.abs(sterker))), 1.0, places=4)
        # De gehele golfvorm krijgt één schaalfactor en wordt niet per piek geknipt.
        self.assertAlmostEqual(float(stronger_ratio := sterker[0, 0] / sterker[1, 0]), -.5, places=4)
        heet = np.array([.8, -.8, .4], dtype=np.float32)
        begrensd = versterk_samples_zonder_digitaal_te_oversturen(heet.copy(), 2.0)
        self.assertAlmostEqual(float(np.max(np.abs(begrensd))), 1.0, places=4)
        zelfde = versterk_samples_zonder_digitaal_te_oversturen(heet.copy(), 1.0)
        np.testing.assert_allclose(zelfde, heet)

    def test_geluidsbibliotheek_kan_boost_verwerken_tot_twee(self):
        fragment = lees_en_bereid_mp3_of_wav_voor(self.item.bestandspad, ingesteld_volume=2.0)
        self.assertAlmostEqual(fragment.ingesteld_volume, 2.0)
        stereo = np.frombuffer(fragment.ruwe_float32_stereo_audio, dtype='<f4')
        self.assertLessEqual(float(np.max(np.abs(stereo))), 1.0)

    def test_html_bevat_geen_ongevraagde_hulpteksten_meer(self):
        tekst = (Path(__file__).resolve().parents[1] / 'app/webinterface/statisch/dashboard.html').read_text(encoding='utf-8')
        for verwijderd in ('Lokale opslag', 'Originele bestanden blijven bewaard',
                           'Alles blijft op je eigen pc', 'Microfoon en fragmenten via VB-CABLE.',
                           'MP3, WAV of MP4. Maximaal 2:00 per fragment.',
                           'Klik op een kaart om uit te zenden.'):
            self.assertNotIn(verwijderd, tekst)
        self.assertIn('max="200" value="100"', tekst)
        self.assertIn('id="geluid-actiemenu"', tekst)


if __name__ == '__main__':
    unittest.main()
