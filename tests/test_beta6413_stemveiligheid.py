"""Numerieke callbacktests, zonder PortAudio of een echte microfoon.

De mixer, limiter en stemeffecten komen uit het project. Apparaatdetectie,
logbestanden en niveaugeschiedenis zijn vervangen; de callbackcode is intact.
"""
from __future__ import annotations
import ast
import importlib.util
from pathlib import Path
import sys
from types import ModuleType
import unittest
from unittest.mock import Mock
import numpy as np

ROOT=Path(__file__).resolve().parents[1]

def isolated(path,name,**dependencies):
    tree=ast.parse(path.read_text(encoding='utf-8-sig'))
    tree.body=[n for n in tree.body if not isinstance(n,ast.ImportFrom) or not (n.module or '').startswith('app.')]
    module=ModuleType(name);sys.modules[name]=module;module.__dict__.update(dependencies)
    exec(compile(tree,str(path),'exec'),module.__dict__)
    return module

params=isolated(ROOT/'app/audio/stemparameters.py','test413_params')
voice=isolated(ROOT/'app/audio/stemvervorming.py','test413_voice',
               standaard_parameters=params.standaard_parameters,controleer_parameters=params.controleer_parameters)
limiter=isolated(ROOT/'app/audio/pieklimiter.py','test413_limiter',SAMPLEFREQUENTIE_VAN_DE_UITVOER=48000)
mixer=isolated(ROOT/'app/audio/live_audiomixer.py','test413_mixer',MAXIMALE_STARTPOGINGEN=3,
               PIEKPLAFOND=limiter.PIEKPLAFOND,PiekLimiter=limiter.PiekLimiter,
               Stemvervormer=voice.Stemvervormer,controleer_stemprofiel=voice.controleer_stemprofiel,
               controleer_stemintensiteit=voice.controleer_stemintensiteit,STANDAARD_INTENSITEITEN=voice.STANDAARD_INTENSITEITEN,
               standaard_parameters=params.standaard_parameters,controleer_parameters=params.controleer_parameters,
               SAMPLEFREQUENTIE_VAN_DE_UITVOER=48000,GeschiedenisVanAudioniveaus=Mock,
               schrijf_auditgebeurtenis=Mock(),
               meet_rms_en_piek_van_een_audioblok=lambda b:(float(np.sqrt(np.mean(b*b))),float(np.max(np.abs(b)))))

class TestStemveiligheid(unittest.TestCase):
    def setUp(self):
        self.m=mixer.LiveAudiomixer(Mock(),Mock(),Mock())
        self.m.stel_stemprofiel_in('robot');self.m.stel_stemvervormer_aan_in(True)
        self.x=np.full((480,1),.1,dtype=np.float32)
        self.m.stel_limiter_in(False)
        self.m._recente_microfoonmetingen.geef_recente_rms_en_piek.return_value=(0.0,0.0)
        self.m._recente_kabelmetingen.geef_recente_rms_en_piek.return_value=(0.0,0.0)
    def run_block(self):
        y=np.zeros((480,2),np.float32)
        self.m.verwerk_een_blok_live_audio(self.x,y,480,None,False)
        return y
    def test_fout_dempt_zonder_stream_te_stoppen(self):
        self.m._stemvervormer.verwerk=Mock(side_effect=RuntimeError('test'))
        np.testing.assert_array_equal(self.run_block(),0)
        self.assertTrue(self.m._stemvervorming_geblokkeerd)
        self.assertFalse(self.m._stop_de_verbinding.is_set())
    def test_stemfilter_krijgt_geen_soundboard_audio(self):
        self.m._stemvervormer.verwerk=Mock(side_effect=RuntimeError('test'))
        self.m._verwerk_het_lopende_geluid_in_het_audioblok=lambda y:y.__iadd__(.2)
        np.testing.assert_allclose(self.run_block(),.2,atol=1e-6)
        np.testing.assert_array_equal(self.m._stemvervormer.verwerk.call_args.args[0],self.x)
    def test_geen_schijflogboek_in_callback(self):
        self.m._stemvervormer.verwerk=Mock(side_effect=RuntimeError('test'))
        self.run_block();self.m.softwarelogboek.error.assert_not_called()
        self.m.softwarelogboek.exception.assert_not_called()
    def test_ongewijzigde_microfoon_bij_bewust_uitgeschakeld_effect(self):
        self.m.stel_stemvervormer_aan_in(False)
        np.testing.assert_allclose(self.run_block(),.08,atol=1e-6)
        self.assertFalse(self.m._stemvervorming_geblokkeerd)
    def test_normaal_profiel_blijft_normaal(self):
        self.m.stel_stemprofiel_in('normaal')
        np.testing.assert_allclose(self.run_block(),.08,atol=1e-6)
    def test_geldige_verwerking_kan_na_een_fout_herstellen(self):
        self.m._stemvervormer.verwerk=Mock(side_effect=[RuntimeError('test'),self.x*.5])
        np.testing.assert_array_equal(self.run_block(),0)
        np.testing.assert_allclose(self.run_block(),.04,atol=1e-6)
        self.assertFalse(self.m._stemvervorming_geblokkeerd)
    def test_ongeldige_uitvoer_lekt_geen_originele_stem(self):
        for bad in (np.full_like(self.x,np.nan),np.full_like(self.x,np.inf),np.zeros((1,1),np.float32),None,self.x.astype(np.float64)):
            with self.subTest(soort=type(bad).__name__):
                self.m._stemvervormer.verwerk=Mock(return_value=bad)
                np.testing.assert_array_equal(self.run_block(),0)
                self.assertTrue(self.m._stemvervorming_geblokkeerd)
    def test_bronframes_blijven_intact(self):
        original=self.x.copy();self.m._stemvervormer.verwerk=Mock(side_effect=RuntimeError('test'))
        self.run_block();np.testing.assert_array_equal(self.x,original)
    def test_status_toont_de_storing(self):
        self.m._stemvervormer.verwerk=Mock(side_effect=RuntimeError('test'));self.run_block()
        status=self.m.geef_huidige_status()
        self.assertTrue(status.stemvervorming_geblokkeerd);self.assertEqual(status.stemvervorming_terugvallen,1)

if __name__=='__main__':unittest.main()
