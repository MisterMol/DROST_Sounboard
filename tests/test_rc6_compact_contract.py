"""Controleer dat RC6 geen grote AI-runtime meelevert en de basisapp bruikbaar blijft."""
from pathlib import Path
import json
import logging
import tempfile
import unittest
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1]

class CompacteRelease(unittest.TestCase):
    def test_builder_heeft_explicit_compacte_variant(self):
        script=(ROOT/'Bouw_Windows_Release.ps1').read_text(encoding='utf-8-sig')
        self.assertIn('[switch] $Compact',script)
        self.assertIn("if (-not $Compact)",script)
        self.assertIn("RELEASE-029",script)
        self.assertIn("stem-runtime:stem-runtime",script)
    def test_status_zonder_ai_maar_met_gewone_effecten(self):
        js=(ROOT/'app/webinterface/statisch/dashboard.js').read_text(encoding='utf-8')
        self.assertIn("toestand.natuurlijkeStem?.beschikbaar ?",js)
        dienst=(ROOT/'app/audio/natuurlijke_stem/dienst.py').read_text(encoding='utf-8')
        self.assertIn('AI-stemmen zijn niet meegeleverd.',dienst)
        profiles=(ROOT/'app/audio/stemvervorming.py').read_text(encoding='utf-8')
        for profile in ('diep','hoog','robot','radio'):
            self.assertIn("'"+profile+"'",profiles)
    def test_nieuw_versienummer(self):
        self.assertIn('6.1.0-rc.6',(ROOT/'app/diagnostiek/logboek.py').read_text(encoding='utf-8'))

    def test_oude_ai_keuze_blokkeert_compacte_app_niet(self):
        from app.audio.natuurlijke_stem.dienst import NatuurlijkeStemDienst
        with tempfile.TemporaryDirectory() as tijdelijk:
            pad = Path(tijdelijk) / 'stem2_keuze.json'
            bewaard = {'schema': 2, 'aan': True, 'gekozen': True,
                       'variant': 'llvc_warm', 'bufferprofiel': 'gebalanceerd'}
            pad.write_text(json.dumps(bewaard), encoding='utf-8')
            with patch('app.audio.natuurlijke_stem.dienst.ai_stemmen_ingeschakeld', return_value=False):
                dienst = NatuurlijkeStemDienst(pad, logging.getLogger('compact-test'),
                                              root=Path(tijdelijk) / 'zonder_model')
                try:
                    self.assertFalse(dienst.aan)
                    self.assertFalse(dienst.gekozen)
                    self.assertFalse(dienst.status()['beschikbaar'])
                    with self.assertRaisesRegex(ValueError, 'niet inbegrepen'):
                        dienst.stel_in(True)
                    with self.assertRaisesRegex(ValueError, 'niet inbegrepen'):
                        dienst.kies_variant('llvc_basis')
                finally:
                    dienst.sluiten()
            self.assertEqual(json.loads(pad.read_text(encoding='utf-8')), bewaard)

    def test_bouwprofiel_herkent_compacte_installer(self):
        from app.desktop.bouwprofiel import ai_stemmen_ingeschakeld
        with tempfile.TemporaryDirectory() as tijdelijk:
            pad = Path(tijdelijk) / 'releasebron.json'
            pad.write_text('{"ai_stemmen_meeleveren":false}', encoding='utf-8')
            self.assertFalse(ai_stemmen_ingeschakeld(pad))
            pad.write_text('{"ai_stemmen_meeleveren":true}', encoding='utf-8')
            self.assertTrue(ai_stemmen_ingeschakeld(pad))

if __name__=='__main__':
    unittest.main()
