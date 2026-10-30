"""Regression tests for audible tuning, click-free block transitions and own mic preview."""
from __future__ import annotations

from contextlib import closing

import math
import subprocess
import shutil
import time
import unittest
from pathlib import Path

import numpy as np

from app.audio.stemparameters import standaard_parameters
from app.audio.stemvervorming import Stemvervormer, STANDAARD_INTENSITEITEN
from app.webinterface.favorieten_en_instellingen import VasteFavorietenEnInstellingen

ROOT = Path(__file__).resolve().parents[1]
FS = 48000


def verwerkt(profiel, x, **kwargs):
    p = Stemvervormer(profiel, **kwargs)
    y = np.concatenate([p.verwerk(x[i:i+480]) for i in range(0,len(x),480)])
    return y[:,0], p


def toonhoogte(y):
    deel = y[-FS//2:]
    spectrum = np.abs(np.fft.rfft(deel*np.hanning(len(deel))))
    f = np.fft.rfftfreq(len(deel), 1/FS)
    geldig = np.flatnonzero((f >= 90) & (f <= 700))
    return float(f[geldig[np.argmax(spectrum[geldig])]])


class StemDSPHerstel(unittest.TestCase):
    def test_stoorzender_is_nu_bewust_digitale_storing(self):
        t = np.arange(FS * 2)/FS
        bron = (.20*np.sin(2*np.pi*233*t)).astype(np.float32)[:,None]
        y, p = verwerkt('autotune', bron, intensiteit=100)
        self.assertGreater(float(np.sqrt(np.mean((y-bron[:,0])**2))), .10)
        self.assertEqual(p._stoorzender_frames, len(bron))
        self.assertEqual(standaard_parameters()['autotune']['ruis_pct'], 60)

    def test_stoorzender_uitgeschakeld_kiest_bypass(self):
        t = np.arange(FS)/FS
        x = (.25*np.sin(2*np.pi*233*t)).astype(np.float32)[:,None]
        y,p = verwerkt('autotune', x, intensiteit=0)
        np.testing.assert_array_equal(y, x[:,0])
        self.assertEqual(p._stoorzender_frames,0)

    def test_profielen_veranderen_hoorbaar_frequentie_en_klank(self):
        t=np.arange(FS)/FS
        stem=(.21*np.sin(2*np.pi*215*t) + .04*np.sin(2*np.pi*645*t)).astype(np.float32)[:,None]
        verwachte={'jongen': (260,310),'meisje': (305,360),
                   'oudeman': (142,188),'oudevrouw':(158,212)}
        for profiel,(onder,boven) in verwachte.items():
            with self.subTest(profiel=profiel):
                y,_=verwerkt(profiel,stem,intensiteit=100)
                frequentie=toonhoogte(y)
                self.assertLess(onder,frequentie)
                self.assertLess(frequentie,boven)
                self.assertGreater(float(np.sqrt(np.mean((y-stem[:,0])**2))),.08)
                self.assertTrue(np.isfinite(y).all())

    def test_stoorzender_signaalhaperingen_begrensd_op_blokgrenzen(self):
        n = FS*3
        frequenties = 205 + 36*np.sin(np.arange(n)/FS*2*np.pi*1.7)
        fase = 2*np.pi*np.cumsum(frequenties)/FS
        x = (.17*np.sin(fase)).astype(np.float32)[:,None]
        y,p = verwerkt('autotune',x,intensiteit=100)
        grenzen = np.abs(y[480::480]-y[479:-1:480])
        # Bewuste digitale korrel is toegestaan. Geen explosieve framegrens.
        self.assertLess(float(np.max(grenzen)), .8)
        self.assertTrue(np.isfinite(y).all())
        self.assertEqual(p._stoorzender_frames, n)

    def test_profielwissel_en_snelle_sterktewisseling_blijven_eindig(self):
        p=Stemvervormer('meisje')
        blok=np.full((480,1), .21, dtype=np.float32)
        reeks=[]
        for i in range(50):
            if i==15: p.kies_profiel('oudeman')
            if i==27: p.stel_intensiteit_in(0)
            if i==33: p.stel_intensiteit_in(100)
            if i==38: p.kies_profiel('autotune')
            reeks.append(p.verwerk(blok).copy())
        r=np.concatenate(reeks)
        self.assertTrue(np.isfinite(r).all())
        self.assertLess(float(np.max(np.abs(r))),1.01)

    def test_lage_callback_belasting(self):
        # Ruime grens zodat deze test ook op tragere CI-machines slaagt.
        p=Stemvervormer('autotune')
        x=np.full((480,1), .1, dtype=np.float32)
        start=time.perf_counter()
        for _ in range(100): p.verwerk(x)
        gemiddeld=(time.perf_counter()-start)/100
        self.assertLess(gemiddeld,.015)

    def test_oude_autotune_instellingen_vervallen_maar_profiel_en_intensiteit_blijven(self):
        import tempfile, json, sqlite3
        with tempfile.TemporaryDirectory() as t:
            pad = Path(t)/'db.sqlite'
            db=VasteFavorietenEnInstellingen(pad)
            db.bewaar_stemprofiel('autotune')
            db.bewaar_stemintensiteit('autotune',67)
            oud={'toonsoort':'A','toonladder':'chromatisch','snelheid_pct':45}
            # SQLite context managers commit or roll back, but DO NOT close.
            # On Windows an open handle blocks TemporaryDirectory cleanup.
            with closing(sqlite3.connect(pad)) as con, con:
                con.execute('INSERT INTO stemprofiel_parameters(profiel,instellingen_json) VALUES (?,?)',
                            ('autotune',json.dumps(oud)))
            # Prove that no SQLite handle survives into temporary-directory cleanup.
            with self.assertRaises(sqlite3.ProgrammingError):
                con.execute('SELECT 1')
            opnieuw=VasteFavorietenEnInstellingen(pad)
            self.assertEqual(opnieuw.geef_stemprofiel(),'autotune')
            self.assertEqual(opnieuw.geef_stemintensiteiten()['autotune'],67)
            self.assertEqual(opnieuw.geef_stemparameters()['autotune'],standaard_parameters()['autotune'])
            nieuw = {'ruis_pct':33,'haperingen_pct':55,'korrel_pct':80}
            opnieuw.bewaar_stemparameters('autotune',nieuw)
            self.assertEqual(VasteFavorietenEnInstellingen(pad).geef_stemparameters()['autotune'],nieuw)
            opnieuw.herstel_stemparameters('autotune')
            self.assertEqual(opnieuw.geef_stemparameters()['autotune'],standaard_parameters()['autotune'])

    def test_audioonderbreking_krijgt_eigen_diagnose(self):
        bron=(ROOT/'app/webinterface/statisch/dashboard.js').read_text(encoding='utf-8')
        self.assertIn('preview.driverproblemen',bron)
        self.assertIn('status?.bufferproblemen',bron)
        self.assertIn('Audioapparaat meldt',bron)

    def test_preview_interface_is_helder_gescheiden_en_reset(self):
        html=(ROOT/'app/webinterface/statisch/dashboard.html').read_text(encoding='utf-8')
        js=(ROOT/'app/webinterface/statisch/dashboard.js').read_text(encoding='utf-8')
        self.assertIn('Mijn eigen stem testen',html)
        self.assertIn('Test uitsluitend je eigen microfoon',html)
        self.assertIn('id="stem-eigen-test"',html)
        self.assertIn('>Reset</button>',html)
        self.assertIn('>Reset alles</button>',html)
        self.assertEqual(html.count('id="stem-eigen-test"'), 1)
        self.assertEqual(html.count('id="stem-demo-spreker"'), 1)
        self.assertIn('if (toestand.stemkeuzeBezig || toestand.natuurlijkeStem?.test_bezig) return;', js)
        self.assertIn('if (keuze === gekozenStemId()) return;', js)
        self.assertIn('Mijn stemtest stoppen',js)
        self.assertNotIn('>Herstel dit profiel</button>',html)

    @unittest.skipUnless(shutil.which('node'), 'Node.js ontbreekt')
    def test_eigen_microfoon_preview_blokkeert_bob_in_js(self):
        result=subprocess.run(['node',str(ROOT/'tests/hulpmiddelen/test_eigen_stempreview_beta631.js')],
                              capture_output=True,text=True,timeout=10)
        self.assertEqual(result.returncode,0,result.stderr+result.stdout)


if __name__=='__main__': unittest.main()
