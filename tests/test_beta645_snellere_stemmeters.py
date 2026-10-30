"""Stemmeters horen bij de 30 Hz-stream, ook in lokale previewmodus.

Gebruik uitsluitend nepdrivers en numerieke audioblokken. De tests openen geen
microfoon en versturen geen audiogegevens naar de browser.
"""
from __future__ import annotations

import json
import logging
import time
import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock

import numpy as np

from app.audio.stemvoorbeeld import LokaalStemvoorbeeld
from app.webinterface.bediening_van_de_audiomotor import WebbedieningVanDrostSoundboard


class TestSnelleStemmeters(unittest.TestCase):
    def maak_status(self, **wijzigingen):
        gegevens = dict(
            toestand='verbroken', is_signaal_gemeten=False,
            seconden_sinds_laatste_callback=None,
            laatst_gemeten_microfoon_rms=0.0, laatst_gemeten_microfoon_piek=0.0,
            laatst_gemeten_kabel_rms=0.0, laatst_gemeten_kabel_piek=0.0,
            stem_rms=0.0, stem_piek=0.0, aantal_bufferproblemen=0,
            limiter_reductie_db=0.0, effect_actief=False,
            effect_rms_voor=0.0, effect_rms_na=0.0,
        )
        gegevens.update(wijzigingen)
        return SimpleNamespace(**gegevens)

    def maak_bediening(self, status, preview):
        bediening = object.__new__(WebbedieningVanDrostSoundboard)
        bediening.mixer = MagicMock()
        bediening.mixer.geef_huidige_status.return_value = status
        bediening.stemvoorbeeld = MagicMock()
        bediening.stemvoorbeeld.status.return_value = preview
        return bediening

    def test_verbonden_microfoon_heeft_snellere_invoer_en_stemuitvoer(self):
        bediening = self.maak_bediening(self.maak_status(
            toestand='verbonden', is_signaal_gemeten=True,
            seconden_sinds_laatste_callback=0.03,
            laatst_gemeten_microfoon_rms=0.2, laatst_gemeten_microfoon_piek=0.4,
            stem_rms=0.1, stem_piek=0.3, aantal_bufferproblemen=2,
        ), {'actief': False, 'gemeten': False})
        gemeten = bediening.geef_directe_audioniveaus()
        self.assertTrue(gemeten['gemeten'])
        self.assertEqual(gemeten['toestand'], 'verbonden')
        self.assertEqual(gemeten['microfoon_rms'], 0.2)
        self.assertEqual(gemeten['stem_rms'], 0.1)
        self.assertEqual(gemeten['bufferproblemen'], 2)
        self.assertFalse(gemeten['stemvoorbeeld']['actief'])
        json.dumps(gemeten, allow_nan=False)

    def test_preview_werkt_zonder_liveverbinding_en_andere_meters_blijven_stil(self):
        preview = dict(actief=True, gemeten=True,
                       microfoon_rms=0.17, stem_rms=0.09,
                       microfoon_piek=0.3, stem_piek=0.22, driverproblemen=0)
        bediening = self.maak_bediening(self.maak_status(), preview)
        gemeten = bediening.geef_directe_audioniveaus()
        self.assertFalse(gemeten['gemeten'])
        self.assertEqual(gemeten['microfoon_rms'], 0)
        self.assertEqual(gemeten['kabel_rms'], 0)
        self.assertEqual(gemeten['stemvoorbeeld'], preview)
        json.dumps(gemeten, allow_nan=False)

    def test_stilgevallen_livecallback_levert_geen_spookniveaus(self):
        bediening = self.maak_bediening(self.maak_status(
            toestand='verbonden', is_signaal_gemeten=True,
            seconden_sinds_laatste_callback=0.5,
            laatst_gemeten_microfoon_rms=0.8, stem_rms=0.7, stem_piek=0.9,
        ), {'actief': False, 'gemeten': False})
        gemeten = bediening.geef_directe_audioniveaus()
        self.assertFalse(gemeten['is_signaal_gemeten'])
        self.assertEqual(gemeten['stem_rms'], 0)
        self.assertEqual(gemeten['stem_piek'], 0)

    def test_preview_volgt_echte_audio_en_wordt_stil_bij_driverstilstand(self):
        voorbeeld = LokaalStemvoorbeeld(MagicMock(), MagicMock(spec=logging.Logger))
        voorbeeld._draait = True
        voorbeeld._draad = MagicMock()
        voorbeeld._draad.is_alive.return_value = True
        invoer = np.full((480, 1), .12, dtype=np.float32)
        uitvoer = np.zeros((480, 2), dtype=np.float32)
        voorbeeld._audio_callback(invoer, uitvoer, 480, None, None)
        meting = voorbeeld.status()
        self.assertTrue(meting['gemeten'])
        self.assertAlmostEqual(meting['microfoon_rms'], .12, places=5)
        self.assertAlmostEqual(meting['stem_rms'], .12, places=5)
        self.assertGreater(float(np.max(uitvoer)), 0)
        voorbeeld._laatste_meettijd = time.monotonic() - 1
        verouderd = voorbeeld.status()
        self.assertTrue(verouderd['actief'])
        self.assertFalse(verouderd['gemeten'])
        self.assertEqual(verouderd['microfoon_rms'], 0)
        self.assertEqual(verouderd['stem_rms'], 0)
        voorbeeld._draait = False
        self.assertFalse(voorbeeld.status()['gemeten'])


if __name__ == '__main__':
    unittest.main()
