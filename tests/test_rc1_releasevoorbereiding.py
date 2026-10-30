"""Release- en HTTP-controles zonder Windows, echte stemmotor of installerbouw.

EXE- en nupkg-bestanden zijn uitdrukkelijke testbestanden. De controles op
versies, bestandspaden, controlesommen en het bewaren van oude builds zijn echt.
"""
from __future__ import annotations
import ast
from http.server import BaseHTTPRequestHandler
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch

from app.desktop.releasevoorbereiding import lees_releaseversie, maak_bouwplan, rond_bouw_af
from app.desktop.deelpakket import bestandsha

ROOT = Path(__file__).resolve().parents[1]
MODEL = 'cceb7ab9621f84d62d283725ae3281cacb04f762d6a088fe3e97c1a29d4b8c0e'
from app.diagnostiek.logboek import VERSIE_VAN_DE_APP as VERSIE


class TestReleaseVersie(unittest.TestCase):
    def test_beta_blijft_beta(self):
        self.assertEqual(lees_releaseversie('6.1.0-beta.4.19').kanaal, 'beta')
    def test_rc_blijft_op_testkanaal(self):
        info = lees_releaseversie(VERSIE)
        self.assertEqual((info.versie, info.kanaal, info.soort), (VERSIE, 'beta', 'rc'))
    def test_stabiel_krijgt_eigen_kanaal(self):
        self.assertEqual(lees_releaseversie('6.1.0').kanaal, 'stable')
    def test_geen_stille_versieaanpassing(self):
        self.assertEqual(lees_releaseversie(VERSIE).versie, VERSIE)
    def test_ongeldige_versies(self):
        for value in ('6.1.0.1', '6.1.0-rc.2.2', '6.01.0', '../6.1.0', '6.1.0+build', '6.1.0\n', '', '6.1.0-beta.04.20'):
            with self.subTest(value=value), self.assertRaises(ValueError):
                lees_releaseversie(value)


class TestReleaseUitvoer(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.plan = maak_bouwplan(self.root, VERSIE, 'a'*32)
        self.map = Path(self.plan['uitvoer'])
        self.installer = self.map / self.plan['installer_naam']
        self.installer.write_bytes(b'MZ_GEEN_ECHTE_INSTALLER')
        self.nupkg = self.map / f'DrostSoundboard.Desktop-{VERSIE}-{lees_releaseversie(VERSIE).kanaal}-full.nupkg'
        self.nupkg.write_bytes(b'NEP_NUPKG')
        self.feed = self.map / 'releases.beta.json'
        self.index = {'Assets': [{'PackageId':'DrostSoundboard.Desktop','Version':VERSIE,'Type':'Full', 'FileName':self.nupkg.name}]}
        self.feed.write_text(json.dumps(self.index))
        self.exe = self.root/'exe.json'
        self.exe.write_text(json.dumps({'geslaagd':True,'versie':VERSIE}))
        self.stem = self.root/'stem.json'
        self.stem.write_text(json.dumps({'passed':True,'finite':True,'reset_ok':True,'model_sha256':MODEL}))
        self.result = self.root/'nieuw_resultaat.json'
    def klaar(self):
        return rond_bouw_af(self.root, self.plan, self.exe, self.stem, self.result)
    def test_elke_build_eigen_map_zelfde_versie(self):
        tweede = maak_bouwplan(self.root, VERSIE, 'b'*32)
        self.assertNotEqual(tweede['uitvoer'], self.plan['uitvoer'])
        self.assertEqual(list(Path(tweede['uitvoer']).iterdir()), [])
        self.assertEqual(self.installer.read_bytes(), b'MZ_GEEN_ECHTE_INSTALLER')
    def test_bestaande_root_release_blijft(self):
        bestaand = self.root/'release-velopack/releases.beta.json'
        bestaand.write_text('OUDE_RELEASES')
        maak_bouwplan(self.root, VERSIE, 'b'*32)
        self.assertEqual(bestaand.read_text(), 'OUDE_RELEASES')
    def test_dezelfde_poging_wordt_niet_hergebruikt(self):
        with self.assertRaises(FileExistsError):maak_bouwplan(self.root, VERSIE, 'a'*32)
    def test_geen_pad_in_bouw_id(self):
        with self.assertRaises(ValueError):maak_bouwplan(self.root, VERSIE, '../ontsnappen')
    def test_mislukte_versie_maakt_geen_map(self):
        voor = list((self.root/'release-velopack').iterdir())
        with self.assertRaises(ValueError):maak_bouwplan(self.root, 'niets', 'b'*32)
        self.assertEqual(list((self.root/'release-velopack').iterdir()), voor)
    def test_resultaat_en_deelmap(self):
        result = self.klaar()
        self.assertTrue(result['geslaagd'])
        self.assertEqual(result['bouw_id'], 'a'*32)
        self.assertEqual(result['installer_sha256'], bestandsha(self.installer))
        self.assertFalse(result['productie_goedgekeurd'])
        deel = self.root / result['deelmap']
        self.assertEqual((deel/self.installer.name).read_bytes(), self.installer.read_bytes())
    def test_rc_gebruikersinstructie(self):
        deel = self.root / self.klaar()['deelmap']
        text = (deel/'LEESMIJ_VOOR_GEBRUIKERS.txt').read_text(encoding='utf-8-sig')
        self.assertIn('releasekandidaat', text)
        self.assertIn('Probleemoplossing', text)
        self.assertNotIn('Kies bij Stemvervormer eerst Computer testen', text)
        self.assertNotIn('22 gewone effecten', text)
    def test_onjuiste_exeversie_geweigerd(self):
        self.exe.write_text('{"geslaagd":true,"versie":"6.1.0-beta.4.19"}')
        with self.assertRaises(ValueError):self.klaar()
        self.assertFalse(self.result.exists())
    def test_mislukte_modelcontrole_geweigerd(self):
        self.stem.write_text('{"passed":false}')
        with self.assertRaises(ValueError):self.klaar()
        self.assertFalse(self.result.exists())
    def test_verkeerde_package_id_geweigerd(self):
        self.index['Assets'][0]['PackageId'] = 'AnderProgramma'; self.feed.write_text(json.dumps(self.index))
        with self.assertRaises(ValueError):self.klaar()
    def test_releasepakket_hash_gecontroleerd(self):
        self.index['Assets'][0]['SHA256'] = bestandsha(self.nupkg).upper()
        self.index['Assets'][0]['Size'] = self.nupkg.stat().st_size
        self.feed.write_text(json.dumps(self.index));self.klaar()
    def test_onjuiste_releasepakket_hash_geweigerd(self):
        self.index['Assets'][0]['SHA256'] = 'f'*64; self.feed.write_text(json.dumps(self.index))
        with self.assertRaises(ValueError):self.klaar()
    def test_onjuiste_releasepakket_grootte_geweigerd(self):
        self.index['Assets'][0]['Size'] = 1; self.feed.write_text(json.dumps(self.index))
        with self.assertRaises(ValueError):self.klaar()
    def test_ontbrekende_feed_geweigerd(self):
        self.feed.unlink()
        with self.assertRaises(ValueError):self.klaar()
    def test_oude_versie_in_feed_geweigerd(self):
        self.index['Assets'][0]['Version'] = '6.1.0-beta.4.19'
        self.feed.write_text(json.dumps(self.index))
        with self.assertRaises(ValueError):self.klaar()
    def test_alleen_delta_is_onvoldoende(self):
        self.index['Assets'][0]['Type'] = 'Delta'; self.feed.write_text(json.dumps(self.index))
        with self.assertRaises(ValueError):self.klaar()
    def test_ontbrekend_nupkg_geweigerd(self):
        self.nupkg.unlink()
        with self.assertRaises(ValueError):self.klaar()
    def test_pad_buiten_feed_geweigerd(self):
        self.index['Assets'][0]['FileName'] = '../ander.nupkg'; self.feed.write_text(json.dumps(self.index))
        with self.assertRaises(ValueError):self.klaar()
    def test_oude_resultaatfile_blijft(self):
        self.result.write_text('OUD')
        with self.assertRaises(ValueError):self.klaar()
        self.assertEqual(self.result.read_text(), 'OUD')
    def test_verkeerd_bouwplan_geweigerd(self):
        self.plan['uitvoer'] = str(self.root)
        with self.assertRaises(ValueError):self.klaar()
    def test_geen_link_naar_andere_setup(self):
        # Geen Windowsrecht nodig om echte symlinks te maken in deze unit-test.
        with patch.object(Path, 'is_symlink', lambda p: p == self.installer):
            with self.assertRaises(ValueError):self.klaar()
    def test_releasepad_link_geweigerd(self):
        p=self.root/'ander'; p.mkdir(); target=p/'release-velopack'; target.mkdir()
        with patch.object(Path, 'is_symlink', lambda path: path == target):
            with self.assertRaises(ValueError):maak_bouwplan(p,VERSIE,'d'*32)


def laad_handler():
    """Gebruik de echte nieuwe handle-methode met de echte standaard HTTP-parser."""
    path=ROOT/'app/webinterface/lokale_webserver.py'
    tree=ast.parse(path.read_text(encoding='utf-8-sig'))
    orig=next(c for c in tree.body if isinstance(c,ast.ClassDef) and c.name=='DrostVerzoekAfhandeling')
    methods=[n for n in orig.body if isinstance(n,ast.FunctionDef) and n.name in ('handle','log_message')]
    cls=ast.ClassDef(name='HandlerOnderTest',bases=[ast.Name(id='BaseHTTPRequestHandler',ctx=ast.Load())],keywords=[],body=methods,decorator_list=[])
    scope={'BaseHTTPRequestHandler':BaseHTTPRequestHandler}
    module=ast.Module(body=[ast.ImportFrom(module='__future__',names=[ast.alias(name='annotations')],level=0),cls],type_ignores=[])
    exec(compile(ast.fix_missing_locations(module),str(path),'exec'),scope)
    return scope['HandlerOnderTest']


class TestHTTPVerbinding(unittest.TestCase):
    def setUp(self):
        self.handler=object.__new__(laad_handler())
        self.handler.close_connection=False
    def test_normale_afhandeling_blijft(self):
        with patch.object(BaseHTTPRequestHandler,'handle') as handle:self.handler.handle()
        handle.assert_called_once()
    def test_client_is_weg(self):
        for exc in (ConnectionAbortedError, ConnectionResetError, BrokenPipeError):
            with self.subTest(exc=exc),patch.object(BaseHTTPRequestHandler,'handle',side_effect=exc('verbinding weg')):
                self.handler.close_connection=False;self.handler.handle();self.assertTrue(self.handler.close_connection)
    def test_onverwachte_fout_blijft_zichtbaar(self):
        for exc in (RuntimeError, ValueError, PermissionError, OSError):
            with self.subTest(exc=exc),patch.object(BaseHTTPRequestHandler,'handle',side_effect=exc('ECHTE_FOUT')):
                with self.assertRaises(exc):self.handler.handle()
    def test_onjuist_http_verzoek_wordt_nog_geweigerd(self):
        h=self.handler;h.rfile=io.BytesIO(b'BAD COMMAND\r\n\r\n');h.wfile=io.BytesIO()
        h.client_address=('127.0.0.1',0);h.server=Mock()
        h.handle()
        self.assertIn(b'400',h.wfile.getvalue());self.assertTrue(h.close_connection)
    def test_verbroken_socket_tijdens_foutantwoord(self):
        h=self.handler;h.rfile=io.BytesIO(b'BAD COMMAND\r\n\r\n');h.wfile=Mock()
        h.wfile.write.side_effect=ConnectionAbortedError(10053,'client is weg')
        h.client_address=('127.0.0.1',0);h.server=Mock();h.handle()
        self.assertTrue(h.close_connection)


class TestInterfaceContract(unittest.TestCase):
    def test_proefpaneel_is_echt_verwijderd(self):
        html=(ROOT/'app/webinterface/statisch/dashboard.html').read_text(encoding='utf-8')
        self.assertNotIn('class="natuurlijke-stem-proef"',html)
        self.assertNotIn('Karakterstem: status, buffering en computertest',html)
        self.assertNotIn('Eén LLVC-model, vier klankvarianten',html)
    def test_afsluiten_tussen_sneltoetsen_en_weergave(self):
        html=(ROOT/'app/webinterface/statisch/dashboard.html').read_text(encoding='utf-8')
        self.assertLess(html.index('id="knop-sneltoetsen"'),html.index('id="knop-app-afsluiten"'))
        self.assertLess(html.index('id="knop-app-afsluiten"'),html.index('id="knop-weergave"'))
        self.assertEqual(html.count('id="knop-app-afsluiten"'),1)
    def test_status_en_laadroutes_behouden(self):
        html=(ROOT/'app/webinterface/statisch/dashboard.html').read_text(encoding='utf-8')
        for value in ('stem-laadstatus','knop-stem-demo','knop-stem-demo-bron','knop-natuurlijke-stem','dialoog-stemdiagnose'):
            self.assertIn(f'id="{value}"',html)
    def test_volledige_bouwcontroles_verplicht(self):
        script=(ROOT/'Bouw_Windows_Release.ps1').read_text(encoding='utf-8-sig')
        for value in ('-m unittest discover -s tests -q','RELEASE-008','RELEASE-015','RELEASE-017','RELEASE-021','releasevoorbereiding afronden','--packVersion $versie'):
            self.assertIn(value,script)
        self.assertNotIn('SkipTests',script)
        self.assertNotIn("--channel 'beta'",script)


if __name__=='__main__':unittest.main()
