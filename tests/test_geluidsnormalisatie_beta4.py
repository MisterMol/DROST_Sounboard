"""Beta 4: niveaus meten buiten de callback, zonder originele mediabestanden te wijzigen."""
from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

import numpy as np
import soundfile as sf

from app.audio.geluidsnormalisatie import (
    NORMALISATIESTANDEN,
    bereken_normalisatiefactor,
    controleer_normalisatiestand,
    normaliseer_fragment_in_geheugen,
)
from app.audio.mp3_en_wav_fragmenten import lees_en_bereid_mp3_of_wav_voor
from app.audio.geluidenbibliotheek import PersoonlijkeGeluidenbibliotheek
from app.webinterface.favorieten_en_instellingen import VasteFavorietenEnInstellingen


class TestLichteNormalisatie(unittest.TestCase):
    def test_vier_beschikbare_standen(self):
        self.assertEqual(NORMALISATIESTANDEN, ('uit', 'subtiel', 'normaal', 'sterk'))
        for stand in NORMALISATIESTANDEN:
            self.assertEqual(controleer_normalisatiestand(stand), stand)

    def test_ongeldige_waarden_worden_geweigerd(self):
        for waarde in (None, '', 'zeerhard', 1, True, [], 'STERK'):
            with self.subTest(waarde=waarde), self.assertRaisesRegex(ValueError, 'NORM-001'):
                controleer_normalisatiestand(waarde)

    def test_uit_verandert_geen_bestaande_samples(self):
        bron = np.array([[0.4, -0.8], [0.2, 0.0], [-0.1, 0.4]], dtype='float32')
        kopie = bron.copy()
        self.assertEqual(normaliseer_fragment_in_geheugen(kopie, 'uit'), 1.0)
        np.testing.assert_array_equal(kopie, bron)

    def test_zacht_fragment_wordt_versterkt(self):
        samples = np.full((48000, 2), 0.02, dtype=np.float32)
        factor = normaliseer_fragment_in_geheugen(samples, 'sterk')
        self.assertGreater(factor, 1.0)
        self.assertLessEqual(factor, 3.0)
        self.assertAlmostEqual(float(samples.max()), 0.02 * factor, places=5)

    def test_hard_fragment_wordt_afgezwakt(self):
        samples = np.full((48000, 2), 0.65, dtype=np.float32)
        factor = normaliseer_fragment_in_geheugen(samples, 'normaal')
        self.assertLess(factor, 1)
        self.assertGreaterEqual(factor, 0.6)
        self.assertLess(float(samples.max()), 0.65)

    def test_sterk_heeft_groter_effect_dan_subtiel(self):
        zacht = np.full((48000, 2), 0.03, dtype=np.float32)
        hard = np.full((48000, 2), 0.7, dtype=np.float32)
        self.assertGreater(bereken_normalisatiefactor(zacht, 'sterk'),
                           bereken_normalisatiefactor(zacht, 'subtiel'))
        self.assertLess(bereken_normalisatiefactor(hard, 'sterk'),
                        bereken_normalisatiefactor(hard, 'subtiel'))

    def test_lange_stilte_wordt_niet_opgepompt(self):
        audio = np.zeros((48000 * 2, 2), dtype=np.float32)
        audio[48000:96000] = 0.02
        self.assertGreater(bereken_normalisatiefactor(audio, 'sterk'), 1.0)
        self.assertEqual(bereken_normalisatiefactor(np.zeros_like(audio), 'sterk'), 1.0)
        self.assertEqual(bereken_normalisatiefactor(np.full((48000, 2), 0.0005, dtype=np.float32), 'sterk'), 1.0)

    def test_piekwaarde_blijft_onder_de_veilige_grens(self):
        audio = np.full((48000, 2), 0.014, dtype=np.float32)
        audio[25000, 0] = 0.9
        normaliseer_fragment_in_geheugen(audio, 'sterk')
        self.assertLessEqual(float(np.max(np.abs(audio))), 0.98001)

    def test_onjuiste_sampledata_geeft_fout(self):
        for samples in (np.ones((12,), dtype=np.float32),
                        np.zeros((0, 2), dtype=np.float32),
                        np.array([[float('nan'), 0.0]], dtype=np.float32),
                        np.array([[float('inf'), 0.0]], dtype=np.float32)):
            with self.subTest(vorm=samples.shape), self.assertRaises(ValueError):
                bereken_normalisatiefactor(samples, 'normaal')

    def test_geen_normalisatie_als_volume_nul_is(self):
        with TemporaryDirectory() as mapnaam:
            pad = Path(mapnaam) / 'fragment.wav'
            sf.write(pad, np.full((4800,), 0.1, dtype=np.float32), 48000)
            clip = lees_en_bereid_mp3_of_wav_voor(pad, ingesteld_volume=0.0, normalisatiestand='sterk')
            self.assertEqual(clip.normalisatiefactor, 1.0)
            self.assertFalse(np.frombuffer(clip.ruwe_float32_stereo_audio, dtype='<f4').any())

    def test_wav_normaal_voorbereid_met_ongewijzigde_bron(self):
        with TemporaryDirectory() as mapnaam:
            pad = Path(mapnaam) / 'fragment.wav'
            sf.write(pad, np.full((48000,), 0.025, dtype=np.float32), 48000)
            inhoud = pad.read_bytes()
            origineel = lees_en_bereid_mp3_of_wav_voor(pad, normalisatiestand='uit')
            normaal = lees_en_bereid_mp3_of_wav_voor(pad, normalisatiestand='normaal')
            self.assertEqual(pad.read_bytes(), inhoud)
            self.assertEqual(origineel.normalisatiestand, 'uit')
            self.assertEqual(origineel.normalisatiefactor, 1.0)
            self.assertEqual(normaal.normalisatiestand, 'normaal')
            self.assertGreater(normaal.normalisatiefactor, 1.0)
            self.assertGreater(np.max(np.frombuffer(normaal.ruwe_float32_stereo_audio, dtype='<f4')),
                               np.max(np.frombuffer(origineel.ruwe_float32_stereo_audio, dtype='<f4')))
            self.assertEqual(normaal.aantal_frames, origineel.aantal_frames)

    def test_wav_en_mp3_gebruiken_dezelfde_normalisatie(self):
        with TemporaryDirectory() as mapnaam:
            duur = 0.3
            golf = (np.sin(np.linspace(0, 660 * 2 * np.pi * duur, int(44100 * duur))) * .04).astype('float32')
            paden = [Path(mapnaam) / f'sample.{ext}' for ext in ('wav', 'mp3')]
            for pad in paden:
                sf.write(pad, golf, 44100)
                resultaat = lees_en_bereid_mp3_of_wav_voor(pad, normalisatiestand='sterk')
                self.assertGreater(resultaat.normalisatiefactor, 1.0)
                self.assertEqual(resultaat.aantal_frames, int(round(48000 * duur)))

    def test_instellingen_blijven_na_herstart_opgeslagen(self):
        with TemporaryDirectory() as mapnaam:
            bestand = Path(mapnaam) / 'bibliotheek.sqlite3'
            PersoonlijkeGeluidenbibliotheek(bestand)
            eerste = VasteFavorietenEnInstellingen(bestand)
            self.assertEqual(eerste.geef_normalisatiestand(), 'uit')
            self.assertEqual(eerste.bewaar_normalisatiestand('normaal'), 'normaal')
            tweede = VasteFavorietenEnInstellingen(bestand)
            self.assertEqual(tweede.geef_normalisatiestand(), 'normaal')
            self.assertEqual(tweede.bewaar_normalisatiestand('sterk'), 'sterk')
            self.assertEqual(eerste.geef_normalisatiestand(), 'sterk')
            with self.assertRaisesRegex(ValueError, 'NORM-001'):
                eerste.bewaar_normalisatiestand('1000%')
            self.assertEqual(tweede.geef_normalisatiestand(), 'sterk')


class TestNormalisatieBijSpelen(unittest.TestCase):
    def test_ingestelde_stand_gaat_mee_naar_decodewerkdraad(self):
        from types import SimpleNamespace
        from unittest.mock import patch
        from app.diagnostiek.logboek import maak_logboeken_klaar, sluit_logboeken_netjes_af
        from app.webinterface.bediening_van_de_audiomotor import WebbedieningVanDrostSoundboard
        with TemporaryDirectory() as mapnaam:
            mapje = Path(mapnaam)
            logger = maak_logboeken_klaar(mapje / 'logs')
            bediening = WebbedieningVanDrostSoundboard(object(), logger, mapje / 'db.sqlite3')
            try:
                bron = mapje / 'test.wav'
                sf.write(bron, np.full(4800, .02, dtype=np.float32), 48000)
                item = bediening.geluidenbibliotheek.voeg_geluidsbestanden_toe([bron])[0]
                bediening.favorieten.bewaar_normalisatiestand('sterk')
                met_status = SimpleNamespace(toestand='verbonden', geluidseffecten_aan=True)
                with patch.object(bediening.mixer, 'geef_huidige_status', return_value=met_status), \
                     patch.object(bediening, '_bereid_geluid_voor_en_start_als_het_nog_mag') as decode:
                    bediening.speel_geluid_uit_de_bibliotheek(item.geluid_id)
                    bediening._laatste_ingediende_decode.result(timeout=5)
                    self.assertEqual(decode.call_args.args[-1], 'sterk')
                    self.assertEqual(decode.call_args.args[1].geluid_id, item.geluid_id)
            finally:
                bediening.sluit_alle_audio_af()
                sluit_logboeken_netjes_af(logger)


if __name__ == '__main__':
    unittest.main()
