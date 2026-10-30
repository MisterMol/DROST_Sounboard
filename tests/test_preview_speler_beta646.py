"""Regressiecontrole voor de compacte speler, zoekfunctie en herhaalstand."""
from __future__ import annotations
from html.parser import HTMLParser
from pathlib import Path
import shutil
import subprocess
import unittest

ROOT = Path(__file__).resolve().parents[1]
HTML = ROOT / 'app/webinterface/statisch/dashboard.html'
CSS = ROOT / 'app/webinterface/statisch/stijl.css'
JS = ROOT / 'app/webinterface/statisch/dashboard.js'


class Ids(HTMLParser):
    def __init__(self):
        super().__init__()
        self.ids = []
    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if a.get('id'):
            self.ids.append(a['id'])


class TestPreviewBeta46(unittest.TestCase):
    def test_unieke_en_toegankelijke_bediening(self):
        tekst = HTML.read_text(encoding='utf-8')
        parser = Ids()
        parser.feed(tekst)
        self.assertEqual(len(parser.ids),len(set(parser.ids)))
        for naam in ('tijdlijn-schuif','knop-preview-herhaal','speler-volume-schuif','speler-volume-waarde'):
            self.assertIn(naam,parser.ids)
        self.assertIn('aria-label="Afspeelpositie van het huidige fragment"',tekst)
        self.assertIn('aria-pressed="false"',tekst)
        self.assertIn('type="range"',tekst)

    def test_seek_en_herhalen_zijn_ook_voor_live_beschikbaar(self):
        code = JS.read_text(encoding='utf-8')
        self.assertIn('if (toestand.preview !== preview || !preview.gestart) return;', code)
        self.assertIn("'/api/speler/live'",code)
        self.assertIn('element("tijdlijn-schuif").disabled = false;',code)
        self.assertIn('planExclusieveSpeleractie',code)

    def test_veilige_klok_en_gif_beperking(self):
        code = JS.read_text(encoding='utf-8')
        self.assertIn('window.requestAnimationFrame(() => animeerPreviewTijd(preview))',code)
        self.assertIn('preview.media.currentTime = positie;',code)
        self.assertIn('.endsWith(".gif")',code)
        self.assertIn('preview.duur',code)
        self.assertIn('window.cancelAnimationFrame(lopend.animatie)',code)
        self.assertNotIn('element("huidige-uitleg").textContent = `Je hoort deze preview alleen lokaal.',code)

    @unittest.skipUnless(shutil.which('node'), 'Node.js is optioneel bij het ontwikkelen')
    def test_zoek_loop_en_volume_gedrag(self):
        best = ROOT / 'tests/hulpmiddelen/test_preview_speler_beta646.js'
        result = subprocess.run(['node', str(best)],cwd=ROOT,capture_output=True,text=True,timeout=15)
        self.assertEqual(result.returncode,0,result.stdout+result.stderr)
        self.assertIn('OK: fragment zoeken',result.stdout)


if __name__ == '__main__':
    unittest.main()
