"""RC2 regressietests voor dashboardvoorkeuren en behoud van bestaande bediening."""
from __future__ import annotations
import ast
from contextlib import closing
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import http.client
import json
from pathlib import Path
import re
import secrets
import sqlite3
import tempfile
import threading
import time
from types import SimpleNamespace
import unittest
from unittest.mock import Mock
from urllib.parse import urlsplit

from app.webinterface.dashboardvoorkeuren import Dashboardvoorkeuren, STANDAARD

ROOT = Path(__file__).resolve().parents[1]
SERVER = ROOT / 'app/webinterface/lokale_webserver.py'
HTML = ROOT / 'app/webinterface/statisch/dashboard.html'
JS = ROOT / 'app/webinterface/statisch/dashboard.js'
CSS = ROOT / 'app/webinterface/statisch/stijl.css'

class TestDashboardvoorkeuren(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.db = Path(self.tmp.name) / 'bibliotheek.db'
        with closing(sqlite3.connect(self.db)) as conn, conn:
            conn.execute('CREATE TABLE andere_instellingen (naam TEXT PRIMARY KEY, waarde TEXT)')
            conn.execute("INSERT INTO andere_instellingen VALUES ('bestaand', 'bewaren')")
        self.store = Dashboardvoorkeuren(self.db)

    def test_klassiek_standaard(self):
        self.assertEqual(self.store.geef(), STANDAARD)

    def test_drie_indelingen_worden_bewaard(self):
        for indeling in ('bibliotheek', 'favorieten', 'klassiek'):
            with self.subTest(indeling=indeling):
                self.store.bewaar({'indeling': indeling})
                self.assertEqual(Dashboardvoorkeuren(self.db).geef()['indeling'], indeling)
        with closing(sqlite3.connect(self.db)) as conn, conn:
            self.assertEqual(conn.execute("SELECT waarde FROM andere_instellingen WHERE naam='bestaand'").fetchone()[0], 'bewaren')

    def test_opmaak_apart_van_indeling(self):
        self.store.bewaar({'indeling': 'favorieten'})
        result = self.store.bewaar({'tekstgrootte': 'groot', 'hoeken': 'strak'})
        self.assertEqual(result, {'indeling': 'favorieten', 'tekstgrootte': 'groot', 'hoeken': 'strak'})

    def test_ongeldige_waarden_worden_geweigerd_zonder_wijziging(self):
        for payload in ({'indeling': 'onbekend'}, {'tekstgrootte': None},
                        {'hoeken': '../aanval'}, {'ongeoorloofd': 'data'}, {}, [], None):
            with self.subTest(payload=payload), self.assertRaises(ValueError):
                self.store.bewaar(payload)
        self.assertEqual(self.store.geef(), STANDAARD)

class TestBehoudInterface(unittest.TestCase):
    def test_bestaande_navigatie_en_beheerpagina(self):
        html = HTML.read_text(encoding='utf-8')
        self.assertIn('id="knop-bibliotheek-pagina"', html)
        self.assertIn('href="#bibliotheek"', html)
        self.assertIn('id="bibliotheek-pagina"', html)
        self.assertIn('id="beheer-lijst"', html)
        self.assertIn('id="beheer-groepkaarten"', html)
        self.assertIn('id="knop-beheer-losmaak-groep"', html)
        self.assertIn('id="zoeken"', html)
        self.assertIn('id="dashboard-snelfilters"', html)

    def test_geen_verlies_aan_volumeregeling_en_favorieten(self):
        html = HTML.read_text(encoding='utf-8')
        for element in ('speler-volume-schuif', 'tijdlijn-schuif', 'knop-speler-opnieuw',
                        'knop-preview-herhaal', 'knop-stop', 'favorieten-raster',
                        'knop-editor-uitzenden', 'knop-eigen-stem',
                        'meter-microfoon', 'meter-uitvoer'):
            with self.subTest(element=element): self.assertIn('id="'+element+'"', html)
        self.assertIn('max="200"', html)

    def test_weergave_houdt_alle_bestaande_instellingen(self):
        html = HTML.read_text(encoding='utf-8')
        for element in ('thema-keuzes', 'thema-accent', 'thema-gradient', 'thema-richting',
                        'thema-compact', 'eigen-thema-lijst', 'thema-voorbeeld',
                        'knop-eigen-thema-opslaan', 'knop-thema-opslaan',
                        'thema-accentpresets', 'thema-lettergrootte', 'thema-hoeken'):
            with self.subTest(element=element): self.assertIn('id="'+element+'"', html)
        js = JS.read_text(encoding='utf-8')
        for naam in ('Obsidian','Midnight','Amethyst','Ember','Monochrome'):
            self.assertIn(naam, js)

    def test_drie_indelingen_en_toegankelijke_status(self):
        html = HTML.read_text(encoding='utf-8')
        for indeling in ('klassiek', 'bibliotheek', 'favorieten'):
            self.assertIn('data-indeling="' + indeling + '"', html)
        self.assertIn('id="dashboard-indeling-status" role="status"', html)
        self.assertIn('id="dashboard-indeling-terug"', html)
        css = CSS.read_text(encoding='utf-8')
        for indeling in ('bibliotheek', 'favorieten'):
            self.assertIn('data-dashboardindeling="' + indeling + '"', css)

class TestDashboardHTTP(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        db = Path(self.tmp.name) / 'bibliotheek.db'
        tree = ast.parse(SERVER.read_text(encoding='utf-8-sig'))
        wanted = {'OngeldigWebverzoek', 'LokaleWebserverVanDrostSoundboard', 'DrostVerzoekAfhandeling'}
        nodes = [n for n in tree.body if isinstance(n, ast.ClassDef) and n.name in wanted]
        nodes.insert(0, ast.ImportFrom(module='__future__', names=[ast.alias(name='annotations')],level=0))
        def foutantwoord(error, action):
            code = str(error).split(':')[0]
            return SimpleNamespace(http_status=400,
                inhoud={'fout':str(error), 'foutcode':code, 'oorzaakcode':code}, logreferentie='test')
        scope = dict(BaseHTTPRequestHandler=BaseHTTPRequestHandler,ThreadingHTTPServer=ThreadingHTTPServer,
            threading=threading,secrets=secrets,json=json,urlsplit=urlsplit,time=time,re=re,
            geef_map_voor_beheerde_bestanden=lambda:Path(self.tmp.name), GROOTSTE_JSON_IN_BYTES=100000,
            Dashboardvoorkeuren=Dashboardvoorkeuren,
            schrijf_auditgebeurtenis=lambda *args,**kwargs:None,
            maak_webfoutantwoord=foutantwoord,gebruikersmelding=lambda e,**kw:str(e),
            maak_webantwoord_voor_onbekende_route=lambda code,msg:{'fout':msg,'foutcode':code})
        exec(compile(ast.fix_missing_locations(ast.Module(body=nodes, type_ignores=[])), str(SERVER),'exec'),scope)
        bediening = Mock()
        bediening.geluidenbibliotheek.databasepad = db
        self.server = scope['LokaleWebserverVanDrostSoundboard'](('127.0.0.1',0),bediening)
        self.thread = threading.Thread(target=self.server.serve_forever,
            kwargs={'poll_interval':.01}, daemon=True)
        self.thread.start()
        self.addCleanup(self.close_server)

    def close_server(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(2)

    def request(self, method='GET', data=None, headers=None):
        koppen = {'X-Drost-Token':self.server.schrijf_token,
                  'Origin':f'http://127.0.0.1:{self.server.server_port}',
                  'Content-Type':'application/json'}
        koppen.update(headers or {})
        conn=http.client.HTTPConnection('127.0.0.1',self.server.server_port,timeout=3)
        try:
            body = json.dumps(data or {}).encode() if method == 'POST' else None
            conn.request(method,'/api/instellingen/dashboard',body,koppen)
            antwoord=conn.getresponse()
            return antwoord.status,json.loads(antwoord.read())
        finally:
            conn.close()

    def test_http_opslag_en_nieuwe_sessie(self):
        code, data = self.request()
        self.assertEqual(code,200)
        self.assertEqual(data,STANDAARD)
        self.assertEqual(self.request('POST',{'indeling':'bibliotheek'})[0],200)
        self.assertEqual(self.request()[1]['indeling'],'bibliotheek')
        self.assertEqual(self.request('POST',{'indeling':'favorieten'})[1]['indeling'],'favorieten')

    def test_onbekende_indeling_en_onbeveiligde_write_worden_geweigerd(self):
        self.assertEqual(self.request('POST',{'indeling':'verkeerd'})[0],400)
        self.assertEqual(self.request('POST',{'indeling':'klassiek'},headers={'X-Drost-Token':''})[0],400)
        self.assertEqual(self.request('POST',{'indeling':'klassiek'},headers={'Origin':'https://vreemd.example'})[0],400)
        self.assertEqual(self.request()[1],STANDAARD)

if __name__ == '__main__': unittest.main()
