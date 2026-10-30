"""Regressiecontroles voor de bedoelde Beta 4.19-interface.

Controleert structuur, catalogi en koppelingen in de echte projectbestanden.
Opent geen audioapparaat, laadt geen DLL/model en verandert geen instellingen.
Luisterkwaliteit en een echte Windowsbuild vallen buiten deze controles.
"""
from __future__ import annotations

import ast
from dataclasses import dataclass, field
from html.parser import HTMLParser
from pathlib import Path
import re
import unittest

ROOT = Path(__file__).resolve().parents[1]
VERVALLEN = {'jongen', 'meisje', 'oudeman', 'oudevrouw'}
NAMEN = {'llvc_basis': 'Nova', 'llvc_warm': 'Ruben',
         'llvc_helder': 'Linde', 'llvc_radio': 'Omroeper'}


@dataclass(eq=False)
class Element:
    tag: str
    attrs: dict
    ouder: 'Element | None' = None
    tekst: list[str] = field(default_factory=list)


class Structuur(HTMLParser):
    """Volg echte HTML-elementen, niet hun willekeurige bytepositie."""
    LEEG = {'area', 'base', 'br', 'col', 'embed', 'hr', 'img', 'input',
            'link', 'meta', 'param', 'source', 'track', 'wbr'}

    def __init__(self, html: str):
        super().__init__(convert_charrefs=True)
        self.stapel: list[Element] = []
        self.elementen: list[Element] = []
        self.feed(html)

    def handle_starttag(self, tag, attrs):
        node = Element(tag, dict(attrs), self.stapel[-1] if self.stapel else None)
        self.elementen.append(node)
        if tag not in self.LEEG:
            self.stapel.append(node)

    def handle_startendtag(self, tag, attrs):
        self.handle_starttag(tag, attrs)
        if tag not in self.LEEG:
            self.handle_endtag(tag)

    def handle_endtag(self, tag):
        for i in range(len(self.stapel)-1, -1, -1):
            if self.stapel[i].tag == tag:
                del self.stapel[i:]
                break

    def handle_data(self, data):
        for node in self.stapel:
            node.tekst.append(data)

    def bij_id(self, identiteit: str) -> Element:
        nodes = [n for n in self.elementen if n.attrs.get('id') == identiteit]
        if len(nodes) != 1:
            raise AssertionError(f'Verwacht precies een element {identiteit}, gevonden: {len(nodes)}')
        return nodes[0]


def ligt_binnen(node: Element, ouder: Element) -> bool:
    while node.ouder is not None:
        if node.ouder is ouder:
            return True
        node = node.ouder
    return False


def controleer_preview_scheiding(html: str) -> None:
    structuur = Structuur(html)
    eigen = structuur.bij_id('stem-eigen-test')
    knop = structuur.bij_id('knop-stemvoorbeeld')
    demo = structuur.bij_id('stem-demo-spreker')
    if not ligt_binnen(knop, eigen):
        raise AssertionError('De eigen microfoonknop hoort in het afzonderlijke testvak.')
    if ligt_binnen(demo, eigen):
        raise AssertionError('Bob en Elise mogen niet in het eigen-microfoonvak staan.')
    kop = demo.ouder
    if kop is None or 'stem-demo-kop' not in kop.attrs.get('class', '').split():
        raise AssertionError('Voorbeeldstemmen hebben een afzonderlijk bedieningsvak nodig.')
    for identiteit in ('knop-stem-demo', 'knop-stem-demo-bron', 'knop-stem-demo-stop'):
        if not ligt_binnen(structuur.bij_id(identiteit), kop):
            raise AssertionError(f'{identiteit} staat niet bij de voorbeeldstemmen.')
    if 'Test uitsluitend je eigen microfoon' not in ''.join(eigen.tekst):
        raise AssertionError('Uitleg over het eigen microfoonsignaal ontbreekt.')


def controleer_openbare_catalogus(intern, openbaar) -> None:
    ids = [p['id'] for p in openbaar]
    if set(ids) != set(intern) - VERVALLEN or set(intern) - set(ids) != VERVALLEN:
        raise AssertionError('Alleen de vier verwijderde leeftijdseffecten horen intern te blijven.')
    if len(ids) != 18 or len(set(ids)) != 18:
        raise AssertionError('Er moeten precies 18 unieke gewone stemkeuzes zijn.')
    if len({p['icoon'] for p in openbaar}) != len(openbaar):
        raise AssertionError('Iedere gewone stemkeuze moet een eigen pictogram houden.')


def python_aanroep(js: str, methode: str, route: str) -> bool:
    # Accepteer enkele en dubbele aanhalingstekens; verifieer methode EN pad.
    patroon = (r"vraagAanPython\(\s*['\"]" + re.escape(methode) +
               r"['\"]\s*,\s*['\"]" + re.escape(route) + r"['\"]")
    return re.search(patroon, js) is not None


def route_tak(boom: ast.Module, methode: str, route: str) -> list[ast.AST]:
    functies = [n for n in ast.walk(boom) if isinstance(n, ast.FunctionDef) and n.name == methode]
    if len(functies) != 1:
        raise AssertionError(f'Geen eenduidige serverfunctie {methode}.')
    for node in ast.walk(functies[0]):
        if not isinstance(node, ast.If):
            continue
        test = node.test
        if (isinstance(test, ast.Compare) and isinstance(test.left, ast.Name)
                and test.left.id == 'pad' and len(test.ops) == 1
                and isinstance(test.ops[0], ast.Eq) and len(test.comparators) == 1
                and isinstance(test.comparators[0], ast.Constant)
                and test.comparators[0].value == route):
            return node.body
    raise AssertionError(f'{methode}: serverroute ontbreekt: {route}')


class TestBouwcontract419(unittest.TestCase):
    maxDiff = 1200

    @classmethod
    def setUpClass(cls):
        statisch = ROOT / 'app/webinterface/statisch'
        cls.html = (statisch / 'dashboard.html').read_text(encoding='utf-8-sig')
        cls.js = (statisch / 'dashboard.js').read_text(encoding='utf-8-sig')
        cls.server = ast.parse((ROOT / 'app/webinterface/lokale_webserver.py').read_text(encoding='utf-8-sig'))

    def test_preview_vakken_zijn_gescheiden_ongeacht_volgorde(self):
        controleer_preview_scheiding(self.html)

    def test_bob_en_elise_beschikbaar(self):
        s = Structuur(self.html)
        menu = s.bij_id('stem-demo-spreker')
        waarden = {n.attrs.get('value') for n in s.elementen
                   if n.tag == 'option' and ligt_binnen(n, menu)}
        self.assertEqual(waarden, {'bob', 'elise'})

    def test_voorbeeld_audio_is_lokaal_en_start_niet_vanzelf(self):
        node = Structuur(self.html).bij_id('stem-demo-audio')
        self.assertEqual(node.tag, 'audio')
        self.assertNotIn('autoplay', node.attrs)
        self.assertNotIn('src', node.attrs)

    def test_resetknoppen_blijven_aanwezig(self):
        s = Structuur(self.html)
        for naam, tekst in (('knop-stem-reset', 'Reset'), ('knop-stem-reset-alles', 'Reset alles')):
            with self.subTest(knop=naam):
                self.assertEqual(''.join(s.bij_id(naam).tekst).strip(), tekst)

    def test_publieke_catalogus(self):
        from app.audio.stemvervorming import PROFIELEN, profiel_catalogus_voor_api
        controleer_openbare_catalogus(PROFIELEN, profiel_catalogus_voor_api())

    def test_oude_codes_blijven_leesbaar_maar_niet_kiesbaar(self):
        from app.audio.stemvervorming import controleer_stemprofiel, controleer_kiesbaar_stemprofiel
        for identiteit in sorted(VERVALLEN):
            with self.subTest(profiel=identiteit):
                self.assertEqual(controleer_stemprofiel(identiteit), identiteit)
                with self.assertRaises(ValueError):
                    controleer_kiesbaar_stemprofiel(identiteit)

    def test_karakternamen_en_aantal_zijn_vastgelegd(self):
        from app.audio.natuurlijke_stem.varianten import catalogus
        self.assertEqual({p['id']: p['naam'] for p in catalogus()}, NAMEN)
        self.assertEqual(len(catalogus()), 4)

    def test_alle_22_keuzes_hebben_unieke_ids_en_pictogrammen(self):
        from app.audio.stemvervorming import profiel_catalogus_voor_api
        from app.audio.natuurlijke_stem.varianten import catalogus
        alles = profiel_catalogus_voor_api() + catalogus()
        self.assertEqual(len(alles), 22)
        self.assertEqual(len({p['id'] for p in alles}), 22)
        self.assertEqual(len({p['icoon'] for p in alles}), 22)

    def test_stemkeuze_gebruikt_de_uniforme_schrijfroute(self):
        self.assertTrue(python_aanroep(self.js, 'POST', '/api/stemkeuze'))
        self.assertTrue(python_aanroep(self.js, 'POST', '/api/stemkeuze/actief'))
        self.assertFalse(python_aanroep(self.js, 'POST', '/api/instellingen/stemprofiel'))

    def test_profielgegevens_worden_nog_gelezen(self):
        self.assertTrue(python_aanroep(self.js, 'GET', '/api/instellingen/stemprofiel'))

    def test_voorbeeld_en_bron_en_stop_hebben_eigen_routes(self):
        for fragment in ('/api/stemkeuze/voorbeeld?spreker=', '/api/stemkeuze/bron?spreker=',
                         '/api/stemkeuze/voorbeeld/stop'):
            with self.subTest(route=fragment):
                self.assertTrue(fragment in self.js)

    def test_server_koppelt_selectie_en_aan_uit_aan_bediening(self):
        for route, naam in (('/api/stemkeuze', 'kies_stem'),
                            ('/api/stemkeuze/actief', 'schakel_stemkeuze'),
                            ('/api/stemkeuze/voorbeeld/stop', 'stop_stemkeuze_voorbeeld')):
            with self.subTest(route=route):
                body = ast.Module(body=route_tak(self.server, 'do_POST', route), type_ignores=[])
                calls = [n.func.attr for n in ast.walk(body) if isinstance(n, ast.Call)
                         and isinstance(n.func, ast.Attribute)]
                self.assertIn(naam, calls)

    def test_server_koppelt_voorbeeld_en_bron_aan_bediening(self):
        for route, naam in (('/api/stemkeuze/voorbeeld', 'maak_stemkeuze_voorbeeld'),
                            ('/api/stemkeuze/bron', 'maak_stemkeuze_bron')):
            with self.subTest(route=route):
                body = ast.Module(body=route_tak(self.server, 'do_GET', route), type_ignores=[])
                calls = [n.func.attr for n in ast.walk(body) if isinstance(n, ast.Call)
                         and isinstance(n.func, ast.Attribute)]
                self.assertIn(naam, calls)

    def test_microfoonpreview_heeft_nog_start_en_stop(self):
        self.assertTrue(python_aanroep(self.js, 'POST', '/api/stemvoorbeeld/start'))
        self.assertTrue(python_aanroep(self.js, 'POST', '/api/stemvoorbeeld/stop'))

    def test_releasebouw_blijft_volledige_suite_vereisen(self):
        code = (ROOT / 'Bouw_Windows_Release.ps1').read_text(encoding='utf-8-sig')
        self.assertIn('-m unittest discover -s tests -q', code)
        self.assertIn("if ($LASTEXITCODE -ne 0) { throw 'RELEASE-008: tests faalden; geen build gemaakt.' }", code)
        self.assertLess(code.index('-m unittest discover'), code.index('-m PyInstaller'))


if __name__ == '__main__':
    unittest.main()
