"""6.1 beta 3.2: hoorbare digitale storing, lokale demo en bewaarde instellingen.

De oude interne sleutel autotune blijft gehandhaafd om bestaande databases te
kunnen openen. In de interface heet het effect Stoorzender.
"""
from __future__ import annotations

from io import BytesIO
from pathlib import Path
import time
import unittest
import wave

import numpy as np

from app.audio.stemparameters import controleer_parameters, parameters_voor_api, standaard_parameters
from app.audio.stemvervorming import Stemvervormer, profiel_catalogus_voor_api
from app.audio.ingebouwde_stemvoorbeelden import render_voorbeeld

FS = 48000
ROOT = Path(__file__).resolve().parents[1]


def teststem(duur=1.3):
    t = np.arange(int(FS * duur), dtype=np.float64) / FS
    return ((.19 * np.sin(2*np.pi*207*t) + .055*np.sin(2*np.pi*615*t))
            .astype(np.float32)[:,None])


def render_in_blokken(profiel, invoer, intensiteit=100, params=None):
    proces = Stemvervormer(profiel, intensiteit=intensiteit, parameters=params)
    return np.concatenate([proces.verwerk(invoer[i:i+480])
                           for i in range(0,len(invoer),480)])


class TestStoorzender(unittest.TestCase):
    def test_nieuwe_naam_en_icoon_en_zonder_muzikale_regelaars(self):
        alle = profiel_catalogus_voor_api()
        p = next(p for p in alle if p['id']=='autotune')
        self.assertEqual(p['naam'], 'Stoorzender')
        self.assertEqual(p['icoon'], 'radio-tower')
        labels = [d['label'] for d in parameters_voor_api()['autotune']]
        self.assertEqual(labels, ['Digitale ruis','Signaalhaperingen','Digitale vervorming'])
        self.assertNotIn('toonladder',standaard_parameters()['autotune'])
        bron = (ROOT/'app/webinterface/statisch/dashboard.js').read_text(encoding='utf-8')
        self.assertIn("'radio-tower'", bron)

    def test_effect_heeft_groot_verschil_en_bypass_bij_nul(self):
        x=teststem()
        droog=render_in_blokken('autotune',x,0)
        nat=render_in_blokken('autotune',x,100)
        np.testing.assert_array_equal(droog,x)
        self.assertGreater(float(np.sqrt(np.mean((nat-droog)**2))), .08)
        self.assertTrue(np.isfinite(nat).all())
        self.assertLessEqual(float(np.max(np.abs(nat))), .981)

    def test_wanneer_alle_regelaars_op_nul_staan_geen_verandering(self):
        params=standaard_parameters()
        params['autotune']={k:0 for k in params['autotune']}
        x=teststem()
        y=render_in_blokken('autotune',x,100,params)
        np.testing.assert_array_equal(y,x)

    def test_stilte_is_stil_en_beide_stereokanalen_gelijk(self):
        stilte=np.zeros((480*130,2),dtype=np.float32)
        y=render_in_blokken('autotune',stilte)
        self.assertEqual(int(np.count_nonzero(y)),0)
        x=np.repeat(teststem(),2,axis=1)
        y=render_in_blokken('autotune',x)
        np.testing.assert_array_equal(y[:,0],y[:,1])

    def test_afzonderlijke_storingsregelaars_hebben_hoorbaar_effect(self):
        x=teststem(1.8)
        for sleutel in ('ruis_pct','haperingen_pct','korrel_pct'):
            with self.subTest(sleutel=sleutel):
                laag=standaard_parameters()
                hoog=standaard_parameters()
                for naam in laag['autotune']:
                    laag['autotune'][naam] = 0
                    hoog['autotune'][naam] = 0
                hoog['autotune'][sleutel] = 100
                a=render_in_blokken('autotune',x,100,laag)
                b=render_in_blokken('autotune',x,100,hoog)
                self.assertGreater(float(np.sqrt(np.mean((b-a)**2))), .004)
                self.assertLessEqual(float(np.max(np.abs(b))), .981)

    def test_weigert_beschadigde_en_onveilige_parameters(self):
        goede=standaard_parameters()['autotune']
        self.assertEqual(controleer_parameters('autotune',goede),goede)
        for slechte in [dict(ruis_pct=-1,haperingen_pct=50,korrel_pct=70),
                        dict(ruis_pct=True,haperingen_pct=50,korrel_pct=70),
                        dict(ruis_pct=60,haperingen_pct=50,korrel_pct=101),
                        dict(toonsoort='C',toonladder='majeur',snelheid_pct=95)]:
            with self.subTest(waarden=slechte), self.assertRaises(ValueError):
                controleer_parameters('autotune',slechte)

    def test_verwerking_zonder_blokverschillen(self):
        x=teststem(1.6)
        p=Stemvervormer('autotune')
        y_blok=np.concatenate([p.verwerk(x[i:i+480]) for i in range(0,len(x),480)])
        p2=Stemvervormer('autotune')
        y_ineen=p2.verwerk(x)
        np.testing.assert_allclose(y_blok,y_ineen,atol=1e-6,rtol=1e-6)

    def test_demo_van_bob_en_elise_wijzigingen_doorvoeren(self):
        a=standaard_parameters()
        b=standaard_parameters()
        a['autotune']={'ruis_pct':5,'haperingen_pct':0,'korrel_pct':0}
        b['autotune']={'ruis_pct':95,'haperingen_pct':90,'korrel_pct':100}
        for spreker in ('bob','elise'):
            with self.subTest(spreker=spreker):
                kalm=render_voorbeeld(spreker,'autotune',100,a)
                sterk=render_voorbeeld(spreker,'autotune',100,b)
                with wave.open(BytesIO(sterk),'rb') as audio:
                    self.assertEqual(audio.getframerate(),FS)
                    self.assertGreater(audio.getnframes(),FS*2)
                self.assertNotEqual(kalm,sterk)

    def test_realtime_verwerking_snel_genoeg(self):
        x=np.full((480,1),.12,dtype=np.float32)
        p=Stemvervormer('autotune')
        start=time.perf_counter()
        for _ in range(200):p.verwerk(x)
        self.assertLess((time.perf_counter()-start)/200,.010)

if __name__ == '__main__':
    unittest.main()
