"""6.1 Beta 4.1: monitor zonder tweede microfoon en betrouwbare ZIP-import."""
from __future__ import annotations

from contextlib import closing
from io import BytesIO
import json
import logging
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import Mock
import wave
from zipfile import ZipFile

import numpy as np

from app.audio.monitor_voor_eigen_headset import MonitorVoorEigenHeadset, MonitorFout
from app.audio.live_audiomixer import LiveAudiomixer
from app.audio.geluidenbibliotheek import PersoonlijkeGeluidenbibliotheek
from app.webinterface.favorieten_en_instellingen import VasteFavorietenEnInstellingen, OngeldigeFavorietOfInstelling
from app.webinterface.bibliotheek_archieven import (
    MAX_GELUIDEN_PER_ARCHIEF, MAX_ARCHIEFINHOUD_BYTES,
    OngeldigBibliotheekarchief, _controleer_archief, bekijk_inhoud_audiopack,
    importeer_draagbaar_bibliotheekarchief, maak_draagbaar_bibliotheekarchief,
    overzicht_volledige_bibliotheek,
)
from app.webinterface.bediening_van_de_audiomotor import WebbedieningVanDrostSoundboard
from app.diagnostiek.logboek import maak_logboeken_klaar, sluit_logboeken_netjes_af


def maak_wav(pad: Path, signaal=100):
    pad.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(pad), 'wb') as bestand:
        bestand.setnchannels(1)
        bestand.setsampwidth(2)
        bestand.setframerate(16000)
        bestand.writeframes(int(signaal).to_bytes(2, 'little', signed=True) * 1600)


class DummyStream:
    active = True


class TestEigenStemHoren(unittest.TestCase):
    def setUp(self):
        self.monitor = MonitorVoorEigenHeadset(Mock(), Mock(spec=logging.Logger))
        self.monitor._stroom = DummyStream()

    def test_standaard_uit_en_een_volume_van_25_procent(self):
        self.assertFalse(self.monitor.eigen_stem_ingeschakeld)
        self.assertEqual(self.monitor.eigen_stem_volume, 25)

    def test_alleen_bewerkte_stem_gaat_naar_headset_bij_uitgeschakelde_effectmonitor(self):
        self.monitor.ingeschakeld = False
        self.monitor.stel_eigen_stem_in(True, 40)
        mic = np.full((240, 2), .35, np.float32)
        self.monitor.ontvang_live_mix(np.full((240, 2), .75, np.float32), mic)
        geluid = self.monitor._klaarstaande_blokken.popleft()
        np.testing.assert_allclose(geluid, .14, atol=1e-6)

    def test_schuif_regelt_alleen_stem_en_niet_soundboard(self):
        self.monitor.stel_eigen_stem_in(True, 25)
        mic = np.full((240, 2), .2, np.float32)
        totaal = np.full((240, 2), .5, np.float32)
        origineel = totaal.copy()
        self.monitor.ontvang_live_mix(totaal, mic)
        np.testing.assert_allclose(self.monitor._klaarstaande_blokken.popleft(), .35, atol=1e-6)
        np.testing.assert_array_equal(totaal, origineel)
        self.monitor.stel_eigen_stem_in(True, 100)
        self.monitor.ontvang_live_mix(totaal, mic)
        np.testing.assert_allclose(self.monitor._klaarstaande_blokken.popleft(), .5)

    def test_ongeldige_percentages_worden_geweigerd(self):
        for getal in (0, 101, 1.5, True, None):
            with self.assertRaises(MonitorFout):
                self.monitor.stel_eigen_stem_in(True, getal)

    def test_mixer_kopieert_bewerkte_stem_na_mix_en_stuurt_live_mix(self):
        mixer = LiveAudiomixer(Mock(), Mock(), Mock())
        opgevangen = []
        mixer.koppel_monitor_voor_effecten(lambda a: None, lambda: None,
                                          lambda gemengd, stem: opgevangen.append((gemengd.copy(), stem.copy())))
        mixer.stel_eigen_stem_monitor_in(True)
        binnen = np.full((240, 1), .3, np.float32)
        buiten = np.zeros((240, 2), np.float32)
        mixer.verwerk_een_blok_live_audio(binnen, buiten, 240, None, None)
        self.assertEqual(len(opgevangen), 1)
        np.testing.assert_allclose(opgevangen[0][0], buiten)
        np.testing.assert_allclose(opgevangen[0][1], .24, atol=1e-6)

    def test_lokaal_stemvolume_volgt_de_limiter_zonder_de_uitvoer_te_wijzigen(self):
        mixer = LiveAudiomixer(Mock(), Mock(), Mock())
        monitor = MonitorVoorEigenHeadset(Mock(), Mock(spec=logging.Logger))
        monitor._stroom = DummyStream()
        monitor.ingeschakeld = True
        monitor.stel_eigen_stem_in(True, 25)
        mixer.koppel_monitor_voor_effecten(lambda a: None, lambda: None, monitor.ontvang_live_mix)
        mixer.stel_eigen_stem_monitor_in(True)
        uitgaand = np.zeros((240, 2), np.float32)
        mixer.verwerk_een_blok_live_audio(np.full((240, 1), 2.0, np.float32),
                                         uitgaand, 240, None, None)
        lokaal = monitor._klaarstaande_blokken.popleft()
        self.assertGreater(float(uitgaand.mean()), 0.0)
        self.assertLessEqual(float(uitgaand.max()), 0.98)
        # Zonder soundboardgeluid en met een sterke limiet hoort 25% monitoring
        # overeen te komen met 25% van de daadwerkelijke VB-CABLE-uitvoer.
        np.testing.assert_allclose(lokaal, uitgaand * 0.25, atol=1e-5)

    def test_stemmonitorfout_mag_vb_cable_niet_stilleggen(self):
        mixer = LiveAudiomixer(Mock(), Mock(), Mock())
        def fout(*args):
            raise RuntimeError('nep headset-fout')
        mixer.koppel_monitor_voor_effecten(lambda a: None, lambda: None, fout)
        mixer.stel_eigen_stem_monitor_in(True)
        buiten = np.zeros((240, 2), np.float32)
        mixer.verwerk_een_blok_live_audio(np.full((240, 1), .3, np.float32), buiten, 240, None, None)
        self.assertGreater(float(buiten.mean()), 0.2)
        self.assertIsNone(mixer._fout_in_audio_callback)


class TestStemMonitorOpslag(unittest.TestCase):
    def test_persistent_en_standaard_uit(self):
        with TemporaryDirectory() as tmp:
            db = Path(tmp) / 'bibliotheek.sqlite3'
            PersoonlijkeGeluidenbibliotheek(db)
            favorieten = VasteFavorietenEnInstellingen(db)
            self.assertEqual(favorieten.geef_eigen_stem_monitor(), {'aan': False, 'volume': 25})
            favorieten.bewaar_eigen_stem_monitor(True, 70)
            self.assertEqual(VasteFavorietenEnInstellingen(db).geef_eigen_stem_monitor(),
                             {'aan': True, 'volume': 70})
            with self.assertRaises(OngeldigeFavorietOfInstelling):
                favorieten.bewaar_eigen_stem_monitor(True, 0)


class TestAudiopackUitbreiding(unittest.TestCase):
    def setUp(self):
        self.temp = TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.basis = Path(self.temp.name)
        self.logs = maak_logboeken_klaar(self.basis / 'logs')
        self.addCleanup(sluit_logboeken_netjes_af, self.logs)
        self.bediening = WebbedieningVanDrostSoundboard(Mock(), self.logs, self.basis / 'db.sqlite3')
        self.addCleanup(self.bediening.sluit_alle_audio_af)
        self.media = self.basis / 'media'
        self.media.mkdir()
        self.wav = self.basis / 'ping.wav'
        maak_wav(self.wav)
        self.item = self.bediening.geluidenbibliotheek.voeg_geluidsbestanden_toe([self.wav])[0]

    def test_te_groot_zip_wordt_geweigerd_zonder_een_gigabyte_te_alloceren(self):
        class Regel:
            file_size = MAX_ARCHIEFINHOUD_BYTES + 1
        class NepArchief:
            def infolist(self): return [Regel()]
        with self.assertRaisesRegex(OngeldigBibliotheekarchief, 'ARCH-007'):
            _controleer_archief(NepArchief())

    def test_grenzen_exact_500_en_1_gib(self):
        self.assertEqual(MAX_GELUIDEN_PER_ARCHIEF, 500)
        self.assertEqual(MAX_ARCHIEFINHOUD_BYTES, 1024**3)
        zip_pad = self.basis / 'vijfhonderd.zip'
        with ZipFile(zip_pad, 'w') as zipf:
            for i in range(500):
                zipf.writestr(f'{i:03d}.wav', b'data')
        with ZipFile(zip_pad) as zipf:
            self.assertEqual(len(_controleer_archief(zipf)), 500)
        with ZipFile(zip_pad, 'a') as zipf:
            zipf.writestr('501.wav', b'data')
        with ZipFile(zip_pad) as zipf:
            with self.assertRaises(OngeldigBibliotheekarchief):
                _controleer_archief(zipf)

    def test_herkent_bestaande_audio_met_verschillende_naam_en_ook_pack_dubbel(self):
        zip_pad = self.basis / 'vergelijk.zip'
        with ZipFile(zip_pad, 'w') as z:
            z.write(self.wav, 'Hernoemd.wav')
            z.write(self.wav, 'Kopie.wav')
        resultaat = bekijk_inhoud_audiopack(zip_pad,
                    self.bediening.geluidenbibliotheek.geef_alle_geluiden())
        self.assertEqual(resultaat['al_aanwezig'], 2)
        self.assertTrue(resultaat['geluiden'][0]['al_aanwezig'])
        self.assertTrue(resultaat['geluiden'][1]['dubbel_in_pakket'])
        antwoord = importeer_draagbaar_bibliotheekarchief(
            self.bediening, self.media, zip_pad, sla_dubbelen_over=True)
        self.assertEqual(antwoord['aantal'], 0)
        self.assertEqual(antwoord['overgeslagen'], 2)
        self.assertEqual(len(self.bediening.geluidenbibliotheek.geef_alle_geluiden()), 1)
        antwoord = importeer_draagbaar_bibliotheekarchief(
            self.bediening, self.media, zip_pad, selectie=[0], sla_dubbelen_over=False)
        self.assertEqual(antwoord['aantal'], 1)

    def test_exportoverzicht_en_lege_mappen_bij_volledige_export(self):
        hoofd = self.bediening.groepen.maak_groep('Movies')
        self.bediening.groepen.maak_groep('Star Wars', hoofd)
        overzicht = overzicht_volledige_bibliotheek(self.bediening)
        self.assertIn('Movies / Star Wars', overzicht['mappaden'])
        self.assertTrue(overzicht['kan_exporteren'])
        zip_pad = maak_draagbaar_bibliotheekarchief(self.bediening, self.media, None)
        self.addCleanup(zip_pad.unlink, missing_ok=True)
        with ZipFile(zip_pad) as z:
            manifest = json.loads(z.read('manifest.json'))
        self.assertIn(['Movies', 'Star Wars'], manifest['mappen'])
        logs = maak_logboeken_klaar(self.basis / 'extra-logs')
        self.addCleanup(sluit_logboeken_netjes_af, logs)
        tweede = WebbedieningVanDrostSoundboard(Mock(), logs, self.basis / 'andere.sqlite3')
        self.addCleanup(tweede.sluit_alle_audio_af)
        result = importeer_draagbaar_bibliotheekarchief(tweede, self.media, zip_pad)
        self.assertEqual(result['aantal'], 1)
        self.assertEqual({g['naam'] for g in tweede.groepen.geef_alle_groepen()}, {'Movies', 'Star Wars'})
        self.assertEqual(len(tweede.geluidenbibliotheek.geef_alle_geluiden()), 1)


class TestBibliotheekInterface(unittest.TestCase):
    def test_dashboard_en_import_hebben_1_stemslider_en_geen_extra_meter(self):
        root=Path(__file__).resolve().parents[1]
        html=(root/'app/webinterface/statisch/dashboard.html').read_text(encoding='utf-8')
        js=(root/'app/webinterface/statisch/dashboard.js').read_text(encoding='utf-8')
        self.assertEqual(html.count('id="knop-eigen-stem"'),1)
        self.assertEqual(html.count('id="eigen-stem-volume"'),1)
        self.assertEqual(html.count('id="audiopack-ook-dubbelen"'),1)
        self.assertIn('/api/monitor-stem', js)
        self.assertIn('/api/bibliotheek/exportoverzicht', js)
        self.assertIn('al_aanwezig', js)
        self.assertNotIn('id="meter-eigen-stem"', html)


if __name__ == '__main__':
    unittest.main()
