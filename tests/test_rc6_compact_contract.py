"""Controleer dat RC6 geen grote AI-runtime meelevert en de basisapp bruikbaar blijft."""
from pathlib import Path
import unittest

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

if __name__=='__main__':
    unittest.main()
