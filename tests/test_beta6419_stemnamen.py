"""Catalogus, migratie en naamgeving. Geen microfoon, model of Windowsdriver.

De instellingsopslag en modelkeuze zijn echt. De audiomixer en het starten van
modelverwerking zijn testvervangers. Voor ontbrekende projectmodules wordt
alleen de betrokken methode uit de ongewijzigde broncode geladen.
"""
from __future__ import annotations
import ast
from contextlib import closing
import json
import logging
from pathlib import Path
import sqlite3
import sys
import tempfile
import threading
from types import ModuleType, SimpleNamespace
import unittest
from unittest.mock import Mock, patch

from app.audio.stemvervorming import (
    PROFIELEN, VERVALLEN_STEMPROFIELEN, controleer_stemprofiel,
    controleer_kiesbaar_stemprofiel, profiel_catalogus_voor_api,
)
from app.audio.natuurlijke_stem.varianten import VARIANTEN, catalogus
from app.audio.natuurlijke_stem.dienst import NatuurlijkeStemDienst
from app.webinterface.stemkeuze import StemKeuzeBediening
from app.diagnostiek.logboek import VERSIE_VAN_DE_APP

ROOT = Path(__file__).resolve().parents[1]


def laad_opslag():
    """Laad echte opslag; vervang alleen het ontbrekende standaardpad-hulpmiddel."""
    path = ROOT / 'app/webinterface/favorieten_en_instellingen.py'
    tree = ast.parse(path.read_text(encoding='utf-8'))
    tree.body = [n for n in tree.body if not (
        isinstance(n, ast.ImportFrom) and n.module == 'app.audio.geluidenbibliotheek')]
    mod = ModuleType('stemnamen419_opslag')
    sys.modules[mod.__name__] = mod
    mod.__dict__['bepaal_standaardlocatie_van_de_bibliotheek'] = lambda: Path('niet-gebruikt.sqlite')
    exec(compile(tree, str(path), 'exec'), mod.__dict__)
    return mod.VasteFavorietenEnInstellingen


def webmethode(name):
    path = ROOT / 'app/webinterface/bediening_van_de_audiomotor.py'
    nodes = [n for n in ast.walk(ast.parse(path.read_text(encoding='utf-8')))
             if isinstance(n, ast.FunctionDef) and n.name == name]
    if len(nodes) != 1:
        raise AssertionError(name)
    tree = ast.Module(body=[ast.ImportFrom(module='__future__', names=[ast.alias(name='annotations')], level=0), nodes[0]], type_ignores=[])
    scope = dict(controleer_kiesbaar_stemprofiel=controleer_kiesbaar_stemprofiel)
    exec(compile(ast.fix_missing_locations(tree), str(path), 'exec'), scope)
    return scope[name]


class TestCatalogus419(unittest.TestCase):
    def test_18_kiesbare_effecten(self):
        self.assertEqual(len(profiel_catalogus_voor_api()), 18)

    def test_geen_leeftijdseffect_in_api(self):
        ids = {p['id'] for p in profiel_catalogus_voor_api()}
        self.assertFalse(ids & VERVALLEN_STEMPROFIELEN)
        self.assertEqual(ids, set(PROFIELEN) - VERVALLEN_STEMPROFIELEN)

    def test_oude_ids_alleen_intern_leesbaar(self):
        for old in VERVALLEN_STEMPROFIELEN:
            with self.subTest(old=old):
                self.assertEqual(controleer_stemprofiel(old), old)
                with self.assertRaisesRegex(ValueError, 'verwijderd'):
                    controleer_kiesbaar_stemprofiel(old)

    def test_andere_effecten_blijven_kiesbaar(self):
        for p in profiel_catalogus_voor_api():
            self.assertEqual(controleer_kiesbaar_stemprofiel(p['id']), p['id'])

    def test_namen_en_ids(self):
        self.assertEqual({p['id']: p['naam'] for p in catalogus()}, {
            'llvc_basis': 'Nova', 'llvc_warm': 'Ruben',
            'llvc_helder': 'Linde', 'llvc_radio': 'Omroeper'})

    def test_geen_nieuwe_modellen_voorgespiegeld(self):
        self.assertEqual({p['model_id'] for p in catalogus()}, {'koeai-llvc-proef-1'})
        self.assertTrue(all(p['soort'] == 'klankvariant' for p in catalogus()))

    def test_klankparameters_ongewijzigd(self):
        self.assertEqual([(v.id, v.toonhoogte, v.klankkleur, v.effect, v.sterkte,
                           v.instelling1, v.instelling2, v.nabewerking) for v in VARIANTEN], [
            ('llvc_basis', 0., 0., 0, 1., .5, .5, False),
            ('llvc_warm', -2.5, -1.2, 0, 1., .5, .5, True),
            ('llvc_helder', 2.5, 1.3, 0, 1., .5, .5, True),
            ('llvc_radio', 0., 0., 2, .78, .22, .27, True)])

    def test_geen_oude_verborgen_groep_in_html(self):
        html = (ROOT/'app/webinterface/statisch/dashboard.html').read_text(encoding='utf-8')
        for token in ('oude-stemeffecten', 'oude-stemprofielen-raster', 'Oude stijleffecten'):
            self.assertNotIn(token, html)


class TestMigratie419(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.database = self.root/'bibliotheek.db'
        with closing(sqlite3.connect(self.database)) as db, db:
            db.execute('CREATE TABLE geluiden (geluid_id TEXT PRIMARY KEY, naam TEXT)')
            db.execute("INSERT INTO geluiden VALUES ('a', 'Eigen geluid')")
        self.fav = laad_opslag()(self.database)
        self.fav.bewaar_algemeen_effectvolume(137)
        self.fav.bewaar_stemprofiel('oudeman')
        self.fav.bewaar_stemvervormer_aan(True)
        self.fav.bewaar_stemintensiteit('oudeman', 62)
        self.path = self.root/'stem2_keuze.json'
        self.dienst = NatuurlijkeStemDienst(self.path, logging.getLogger('419-test'), autostart=False)
        self.addCleanup(self.dienst.sluiten)
        no_model = patch.object(self.dienst, '_run')
        no_model.start()
        self.addCleanup(no_model.stop)
        self.c = StemKeuzeBediening()
        self.c._bescherm_toestand = threading.RLock()
        self.c._wordt_afgesloten = False
        self.c._stemkeuze_generatie = 0
        self.c.stemkeuze_voorbeelden = Mock()
        self.c.natuurlijke_stem = self.dienst
        self.c.favorieten = self.fav
        self.c.mixer = Mock()
        self.c.stemvoorbeeld = Mock(actief=False)
        self.c.geef_steminstellingen = Mock(return_value={})
        self.c.stop_stemvoorbeeld = Mock()
        self.c.stel_stemvervormer_aan_in = Mock()

    def test_actieve_oude_keuze_wordt_nova_met_behouden_aanstand(self):
        self.c.migreer_vervallen_stemkeuze()
        self.assertTrue(self.dienst.aan)
        self.assertTrue(self.dienst.gekozen)
        self.assertEqual(self.dienst.variant, 'llvc_basis')
        self.assertEqual(self.fav.geef_stemprofiel(), 'normaal')
        self.assertFalse(self.fav.geef_stemvervormer_aan())
        self.assertIn('Nova', self.c._stemkeuze_migratiemelding)
        data = json.loads(self.path.read_text())
        self.assertTrue(data['aan'])
        self.assertTrue(data['gekozen'])

    def test_uit_blijft_uit(self):
        self.fav.bewaar_stemvervormer_aan(False)
        self.c.migreer_vervallen_stemkeuze()
        self.assertTrue(self.dienst.gekozen)
        self.assertFalse(self.dienst.aan)
        self.dienst._run.assert_not_called()

    def test_alle_vier_oude_keuzes_worden_vervangen(self):
        for old in sorted(VERVALLEN_STEMPROFIELEN):
            with self.subTest(profiel=old):
                self.dienst.kies_gewone_effecten()
                self.fav.bewaar_stemprofiel(old)
                self.fav.bewaar_stemvervormer_aan(False)
                self.c.migreer_vervallen_stemkeuze()
                self.assertEqual(self.dienst.variant, 'llvc_basis')
                self.assertTrue(self.dienst.gekozen)
                self.assertFalse(self.dienst.aan)

    def test_andere_effectkeuze_blijft_ongewijzigd(self):
        self.fav.bewaar_stemprofiel('robot')
        self.c.migreer_vervallen_stemkeuze()
        self.assertEqual(self.fav.geef_stemprofiel(), 'robot')
        self.assertTrue(self.fav.geef_stemvervormer_aan())
        self.assertFalse(self.dienst.gekozen)
        self.assertFalse(self.path.exists())
        self.c.mixer.stel_stemprofiel_in.assert_not_called()

    def test_bestaande_modelvariant_blijft_behouden(self):
        for variant in ('llvc_basis', 'llvc_warm', 'llvc_helder', 'llvc_radio'):
            with self.subTest(variant=variant):
                self.fav.bewaar_stemprofiel('meisje')
                self.dienst.kies_variant(variant, aan=False)
                self.c.migreer_vervallen_stemkeuze()
                self.assertEqual(self.dienst.variant, variant)
                self.assertFalse(self.dienst.aan)
                self.assertEqual(self.c._stemkeuze_migratiemelding, '')

    def test_actieve_modelvariant_niet_herladen(self):
        self.dienst.kies_variant('llvc_warm', aan=True)
        with patch.object(self.dienst, 'kies_variant', wraps=self.dienst.kies_variant) as choose:
            self.c.migreer_vervallen_stemkeuze()
        choose.assert_not_called()
        self.assertTrue(self.dienst.aan)
        self.assertEqual(self.dienst.variant, 'llvc_warm')

    def test_modelroute_eerst_dan_oude_effecten_uit(self):
        events = []
        original = self.dienst.kies_variant
        def pick(*a, **kw):
            result = original(*a, **kw)
            events.append(('model', self.dienst.aan))
            return result
        self.c.mixer.stel_stemvervormer_aan_in.side_effect = lambda x: events.append(('effect', x))
        with patch.object(self.dienst, 'kies_variant', side_effect=pick):
            self.c.migreer_vervallen_stemkeuze()
        self.assertEqual(events, [('model', True), ('effect', False)])

    def test_opslaan_model_mislukt_wijzigt_database_niet(self):
        with patch.object(self.dienst, '_save', side_effect=OSError('test')), self.assertRaises(OSError):
            self.c.migreer_vervallen_stemkeuze()
        self.assertEqual(self.fav.geef_stemprofiel(), 'oudeman')
        self.assertTrue(self.fav.geef_stemvervormer_aan())
        self.c.mixer.stel_stemprofiel_in.assert_not_called()

    def test_mislukte_database_wissel_geeft_geen_droge_microfoon(self):
        with patch.object(self.fav, 'bewaar_stemprofiel', side_effect=OSError('test')), self.assertRaises(OSError):
            self.c.migreer_vervallen_stemkeuze()
        self.assertTrue(self.dienst.aan)
        self.assertTrue(self.dienst.gekozen)
        self.assertTrue(json.loads(self.path.read_text())['aan'])

    def test_nogmaals_migreren_start_niet_opnieuw(self):
        self.c.migreer_vervallen_stemkeuze()
        with patch.object(self.dienst, 'kies_variant') as choose:
            self.c.migreer_vervallen_stemkeuze()
        choose.assert_not_called()

    def test_bibliotheek_volume_en_oude_parameters_behouden(self):
        self.c.migreer_vervallen_stemkeuze()
        self.assertEqual(self.fav.geef_algemeen_effectvolume(), 137)
        self.assertEqual(self.fav.geef_stemintensiteiten()['oudeman'], 62)
        with closing(sqlite3.connect(self.database)) as db:
            self.assertEqual(db.execute('SELECT * FROM geluiden').fetchall(), [('a', 'Eigen geluid')])

    def test_bewaarde_modelselectie_na_herstart(self):
        self.fav.bewaar_stemvervormer_aan(False)
        self.c.migreer_vervallen_stemkeuze()
        new = NatuurlijkeStemDienst(self.path, logging.getLogger('419-herstart'))
        try:
            self.assertEqual(new.variant, 'llvc_basis')
            self.assertTrue(new.gekozen)
            self.assertFalse(new.aan)
        finally:
            new.sluiten()

    def test_oude_keuze_via_nieuwe_api_geweigerd_zonder_bijwerking(self):
        for old in VERVALLEN_STEMPROFIELEN:
            with self.subTest(old=old), self.assertRaises(ValueError):
                self.c.kies_stem(old)
        self.c.stemkeuze_voorbeelden.annuleer.assert_not_called()
        self.c.mixer.stel_stemprofiel_in.assert_not_called()
        self.assertFalse(self.path.exists())

    def test_migratiemelding_verdwijnt_na_bewuste_keuze(self):
        self.fav.bewaar_stemvervormer_aan(False)
        self.c.migreer_vervallen_stemkeuze()
        self.c.kies_stem('robot')
        self.assertEqual(self.c._stemkeuze_migratiemelding, '')
        self.assertFalse(self.dienst.gekozen)
        self.assertFalse(self.fav.geef_stemvervormer_aan())

    def test_status_en_rapport_gebruiken_nieuwe_namen(self):
        for item in catalogus():
            self.dienst.kies_variant(item['id'], aan=False)
            self.assertEqual(self.dienst.status()['stemnaam'], item['naam'])
            self.assertEqual(self.dienst.geef_rapport()['stemnaam'], item['naam'])
            self.assertEqual(self.dienst.geef_rapport()['appversie'], VERSIE_VAN_DE_APP)


class TestOudeAPIRoutes419(unittest.TestCase):
    def test_oude_profielroute_weigert_vervallen_keuze(self):
        f = webmethode('stel_stemprofiel_in')
        c = SimpleNamespace(_controleer_gewone_stemkeuze=Mock(), favorieten=Mock(), mixer=Mock(), stemvoorbeeld=Mock())
        for old in VERVALLEN_STEMPROFIELEN:
            with self.subTest(old=old), self.assertRaisesRegex(ValueError, 'verwijderd'):
                f(c, old)
        c.favorieten.bewaar_stemprofiel.assert_not_called()

    def test_intensiteit_voor_oude_profielen_geweigerd(self):
        f = webmethode('stel_stemintensiteit_in')
        c = SimpleNamespace(favorieten=Mock())
        for old in VERVALLEN_STEMPROFIELEN:
            with self.subTest(old=old), self.assertRaises(ValueError):
                f(c, old, 75)
        c.favorieten.bewaar_stemintensiteit.assert_not_called()

    def test_individuele_reset_voor_oude_profielen_geweigerd(self):
        f = webmethode('herstel_stemintensiteit')
        c = SimpleNamespace(favorieten=Mock())
        for old in VERVALLEN_STEMPROFIELEN:
            with self.subTest(old=old), self.assertRaises(ValueError):
                f(c, old)
        c.favorieten.herstel_stemintensiteit.assert_not_called()


if __name__ == '__main__':
    unittest.main()
