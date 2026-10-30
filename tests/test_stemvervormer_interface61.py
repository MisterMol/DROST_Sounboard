"""6.1: UI blijft onder Instellingen, niet op het dashboard."""
from html.parser import HTMLParser
from pathlib import Path
import shutil
import subprocess
import unittest

ROOT = Path(__file__).resolve().parents[1]

class Parser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.stack=[]
        self.parents={}
        self.count={}
    def handle_starttag(self, tag, attrs):
        a=dict(attrs)
        if a.get('id'):
            self.parents[a['id']]=list(self.stack)
            self.count[a['id']]=self.count.get(a['id'],0)+1
        if tag not in ('meta','link','input','hr','br','img','source','wbr','area','base','col','embed','param','track'):
            self.stack.append((tag,a.get('id')))
    def handle_endtag(self,tag):
        for i in range(len(self.stack)-1,-1,-1):
            if self.stack[i][0]==tag:
                del self.stack[i:]
                return

class TestUI(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.html=(ROOT/'app/webinterface/statisch/dashboard.html').read_text(encoding='utf-8')
        cls.js=(ROOT/'app/webinterface/statisch/dashboard.js').read_text(encoding='utf-8')
        cls.parser=Parser();cls.parser.feed(cls.html)
    def test_controls_alleen_bij_instellingen(self):
        for id in ('stemprofiel-keuze','knop-stemvoorbeeld','stemvoorbeeld-status'):
            self.assertEqual(self.parser.count.get(id),1)
            ouders={name for _,name in self.parser.parents[id]}
            self.assertIn('instellingen-pagina',ouders)
            self.assertNotIn('dashboard',ouders)
    def test_live_preview_en_profile_use_python_api(self):
        self.assertRegex(self.js, r"vraagAanPython\(\s*['\"]POST['\"]\s*,\s*['\"]/api/stemkeuze['\"]")
        self.assertRegex(self.js, r"vraagAanPython\(\s*['\"]POST['\"]\s*,\s*['\"]/api/stemkeuze/actief['\"]")
        self.assertIn('"/api/stemvoorbeeld/start"',self.js)
        self.assertIn('"/api/stemvoorbeeld/stop"',self.js)
        self.assertIn('window.addEventListener("pagehide"',self.js)
        self.assertIn('keepalive: true',self.js)
    @unittest.skipUnless(shutil.which('node'), 'node is optioneel')
    def test_javascript_syntaxis(self):
        result=subprocess.run(['node','--check',str(ROOT/'app/webinterface/statisch/dashboard.js')],capture_output=True,text=True)
        self.assertEqual(result.returncode,0,result.stderr)

if __name__ == '__main__':
    unittest.main()
