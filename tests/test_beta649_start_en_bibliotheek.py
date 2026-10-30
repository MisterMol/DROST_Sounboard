"""Beta 4.9: één microfoon automatisch verbinden en compacte bibliotheek."""
from __future__ import annotations

import shutil
import subprocess
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class TestBeta49(unittest.TestCase):
    def test_frontendstructuur(self):
        js = (ROOT / 'app/webinterface/statisch/dashboard.js').read_text(encoding='utf-8')
        html = (ROOT / 'app/webinterface/statisch/dashboard.html').read_text(encoding='utf-8')
        self.assertIn('function maakUitzendknopVoorGeluid(', js)
        self.assertIn('toestand.automatischEenMicrofoon', js)
        self.assertIn('verbindEnigeMicrofoonBijStart', js)
        self.assertIn("if (!automatisch) markeerHandmatigVerbroken(true)", js)
        self.assertIn('const uitzenden = maakUitzendknopVoorGeluid(geluid)', js)
        self.assertIn('function werkPreviewEnStopknoppenBij()', js)
        self.assertIn('id="knop-preview-herhaal"', html)
        self.assertIn('for="zoeken">Zoeken</label>', html)
        self.assertIn('id="dashboard-snelfilters"', html)
        # Één zoekveld, geen extra onnodige controls in de bibliotheek.
        self.assertEqual(html.count('id="zoeken"'), 1)

    def test_loop_kan_al_bij_starten_aan_staan(self):
        import logging
        from unittest.mock import Mock
        import numpy as np
        from app.audio.live_audiomixer import LiveAudiomixer
        from app.audio.geluidsbestanden import VoorbereidGeluidsfragment
        mixer = LiveAudiomixer(Mock(), Mock(spec=logging.Logger), Mock(spec=logging.Logger))
        mixer._toestand = 'verbonden'
        mixer._geluidseffecten_ingeschakeld = True
        fragment = VoorbereidGeluidsfragment(
            naam_van_het_geluid='Kort geluid', bestandspad=Path('nep.wav'),
            vingerafdruk_van_audio='test',
            ruwe_float32_stereo_audio=np.full((100, 2), .1, dtype=np.float32).tobytes(),
            aantal_frames=100, oorspronkelijke_samplefrequentie=48000,
            oorspronkelijke_aantal_kanalen=2, ingesteld_volume=1.0)
        mixer.speel_een_voorbereid_geluid(fragment, herhalen=True)
        mixer._voer_wachtende_opdrachten_uit()
        self.assertTrue(mixer.geef_huidige_status().live_herhalen)
        blok = np.zeros((480, 2), dtype=np.float32)
        mixer._verwerk_het_lopende_geluid_in_het_audioblok(blok)
        self.assertIsNotNone(mixer._huidige_geluid)
        self.assertGreater(np.count_nonzero(blok), 0)
        self.assertTrue(mixer.geef_huidige_status().live_herhalen)

    def test_loop_wordt_meegegeven_met_startaanvraag(self):
        js = (ROOT / 'app/webinterface/statisch/dashboard.js').read_text(encoding='utf-8')
        service = (ROOT / 'app/webinterface/bediening_van_de_audiomotor.py').read_text(encoding='utf-8')
        self.assertIn('herhalen: toestand.previewHerhalen', js)
        self.assertIn("herhalen = tijdelijk.get('herhalen', False)", service)
        self.assertIn("**({'herhalen': True} if herhalen else {})", service)

    def test_node_gebruikersbediening(self):
        node = shutil.which('node')
        if node is None:
            self.skipTest('Node.js ontbreekt; JavaScript-interacties niet getest.')
        script = ROOT / 'tests/hulpmiddelen/test_snelle_bibliotheek_beta649.js'
        run = subprocess.run([node, str(script)], cwd=ROOT, capture_output=True,
                             text=True, encoding='utf-8', timeout=20)
        self.assertEqual(run.returncode, 0, run.stdout + run.stderr)


if __name__ == '__main__':
    unittest.main()
