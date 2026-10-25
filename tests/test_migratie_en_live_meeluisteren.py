"""Behoud oude bibliotheekdata en geef de headset alleen geluidseffecten."""
import logging
from pathlib import Path
import sqlite3
from contextlib import closing
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import Mock

import numpy as np

from app.audio.geluidsbestanden import VoorbereidGeluidsfragment
from app.audio.live_audiomixer import LiveAudiomixer
from app.webinterface.favorieten_en_instellingen import (
    VasteFavorietenEnInstellingen, OngeldigeFavorietOfInstelling,
)


class TestBestaandeDatabaseMigreren(unittest.TestCase):
    def test_oudere_bibliotheek_behoudt_alle_reeds_bewaarde_geluiden(self):
        with TemporaryDirectory() as temp:
            pad = Path(temp)/'oud.db'
            with closing(sqlite3.connect(pad)) as db:
                db.execute('CREATE TABLE geluiden (geluid_id TEXT PRIMARY KEY, eigen_naam TEXT, bestandspad TEXT)')
                db.execute("INSERT INTO geluiden VALUES ('oud-id','Oude favoriete muziek','oud.mp3')")
                db.execute('CREATE TABLE geluidsinstellingen (geluid_id TEXT PRIMARY KEY, beginpositie REAL, volume REAL, maximale_duur REAL, afbeelding TEXT)')
                db.execute("INSERT INTO geluidsinstellingen VALUES ('oud-id',3.0,.4,80.0,NULL)")
                db.commit()
            instellingen = VasteFavorietenEnInstellingen(pad)
            ouder = instellingen.geef_instellingen_van_geluid('oud-id')
            self.assertEqual(ouder.begint_bij_seconden, 3.0)
            self.assertEqual(ouder.maximale_duur_seconden, 80.0)
            self.assertEqual(ouder.beeldvoorkeur, 'automatisch')
            instellingen.bewaar_afspeelinstellingen('oud-id', 4.0, .2, 100.0, 'afbeelding')
            heropend = VasteFavorietenEnInstellingen(pad)
            self.assertEqual(heropend.geef_instellingen_van_geluid('oud-id').beeldvoorkeur, 'afbeelding')
            with self.assertRaisesRegex(OngeldigeFavorietOfInstelling, 'FAV-010'):
                instellingen.bewaar_afspeelinstellingen('oud-id', 0, .3, 120, 'html_script')


class TestLiveMonitorKrijgtAlleenEffect(unittest.TestCase):
    def test_stem_wordt_nooit_naar_eigen_headset_gestuurd(self):
        log = Mock(spec=logging.Logger)
        mixer = LiveAudiomixer(Mock(), log, log)
        op_headset = []
        leegmaken = Mock()
        mixer.koppel_monitor_voor_effecten(lambda samples: op_headset.append(samples.copy()), leegmaken)
        mixer._verander_status('verbonden')
        mixer._geluidseffecten_ingeschakeld = True
        geluid = np.full((240,2), .25, dtype=np.float32)
        fragment = VoorbereidGeluidsfragment(
            naam_van_het_geluid='Effect', bestandspad=Path('effect.wav'),
            vingerafdruk_van_audio='hash', ruwe_float32_stereo_audio=geluid.tobytes(),
            aantal_frames=240, oorspronkelijke_samplefrequentie=48000,
            oorspronkelijke_aantal_kanalen=2, ingesteld_volume=.25,
        )
        mixer.speel_een_voorbereid_geluid(fragment, geluid_id='geluid-123')
        uit = np.zeros((240,2),dtype=np.float32)
        stem = np.full((240,1), .5,dtype=np.float32)
        mixer.verwerk_een_blok_live_audio(stem,uit,240,None,False)
        # De virtuele microfoon bevat stem (.5 * .8) plus effect (.25).
        np.testing.assert_allclose(uit, .65)
        # De eigen headset krijgt alléén het effect, dus geen tweede stem.
        self.assertEqual(len(op_headset),1)
        np.testing.assert_allclose(op_headset[0], .25)


if __name__ == '__main__': unittest.main()
