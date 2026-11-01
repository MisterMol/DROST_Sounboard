"""Beta 5.1: compacte hoofdpagina, aparte geluidspagina en een enkele verbindingsknop."""
from __future__ import annotations

from html.parser import HTMLParser
from pathlib import Path
import shutil
import subprocess
import unittest

PROJECT = Path(__file__).resolve().parents[1]
HTML = PROJECT / "app/webinterface/statisch/dashboard.html"
JS = PROJECT / "app/webinterface/statisch/dashboard.js"
CSS = PROJECT / "app/webinterface/statisch/stijl.css"


class VindPositiesVanIds(HTMLParser):
    """Kijk naar de werkelijke HTML-ouders van instellingen, niet naar losse tekstmatches."""

    VOID_TAGS = {"area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta", "param", "source", "track", "wbr"}

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.stapel = []
        self.parents = {}
        self.aantallen = {}
        self.elementen = {}

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        gevonden = a.get("id")
        if gevonden:
            self.parents[gevonden] = tuple(self.stapel)
            self.elementen[gevonden] = (tag, a)
            self.aantallen[gevonden] = self.aantallen.get(gevonden, 0) + 1
        if tag not in self.VOID_TAGS:
            self.stapel.append((tag, gevonden))

    def handle_endtag(self, tag):
        for i in range(len(self.stapel) - 1, -1, -1):
            if self.stapel[i][0] == tag:
                del self.stapel[i:]
                return

    def voorouders(self, id):
        return {ouder_id for _, ouder_id in self.parents[id]}


class TestBeta51InstellingenEnVerbinding(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.html = HTML.read_text(encoding="utf-8")
        cls.js = JS.read_text(encoding="utf-8")
        cls.css = CSS.read_text(encoding="utf-8")
        cls.dom = VindPositiesVanIds()
        cls.dom.feed(cls.html)

    def test_geen_dubbele_ids_voor_schakelaars(self):
        for id in ("normalisatie-keuze", "normalisatie-preview-resultaat", "knop-limiter", "limiter-reductie", "knop-verbinden"):
            with self.subTest(id=id):
                self.assertEqual(self.dom.aantallen.get(id), 1)
        self.assertEqual([i for i, count in self.dom.aantallen.items() if count > 1], [])

    def test_normalisatie_en_limiter_alleen_op_instellingen_geluid(self):
        for id in ("normalisatie-keuze", "normalisatie-preview-resultaat", "knop-limiter", "limiter-reductie"):
            with self.subTest(id=id):
                voorouders = self.dom.voorouders(id)
                self.assertIn("instellingen-pagina", voorouders)
                self.assertIn("instellingen-geluid-titel", set(self.dom.aantallen))
                self.assertNotIn("dashboard", voorouders)
        self.assertIn('id="instellingen-pagina"', self.html)
        self.assertIn('aria-labelledby="instellingen-geluid-titel"', self.html)
        self.assertEqual(self.dom.elementen["instellingen-pagina"][1].get("hidden"), None)
        self.assertIn('[hidden] { display: none !important; }', self.css)

    def test_het_dashboard_houdt_een_verbindingsknop_over(self):
        self.assertIn("dashboard", self.dom.voorouders("knop-verbinden"))
        self.assertNotIn("knop-verbreken", self.dom.aantallen)
        self.assertNotIn('element("knop-verbreken")', self.js)
        self.assertNotIn("#knop-verbreken", self.css)

    def test_navigatie_is_een_echte_verborgen_pagina_met_terugpad(self):
        self.assertEqual(self.dom.elementen["knop-instellingen"][1]["href"], "#instellingen")
        self.assertIn('window.addEventListener("hashchange", toonGekozenPagina)', self.js)
        self.assertIn("element('dashboard').hidden = instellingen || bibliotheek;", self.js)
        self.assertIn("element('instellingen-pagina').hidden = !instellingen;", self.js)
        self.assertIn("['knop-instellingen', instellingen]", self.js)
        self.assertIn("['knop-dashboard-pagina', !instellingen && !bibliotheek]", self.js)

    def test_verbindingsfout_staat_direct_onder_de_knop(self):
        self.assertEqual(self.dom.aantallen.get("microfoon-verbinding-fout"), 1)
        self.assertEqual(self.dom.elementen["microfoon-verbinding-fout"][1].get("role"), "alert")
        self.assertIn("dashboard", self.dom.voorouders("microfoon-verbinding-fout"))
        self.assertIn(".microfoon-verbinding-fout[hidden]", self.css)
        self.assertIn("toonMicrofoonVerbindingsfout(fouttekst)", self.js)
        self.assertIn("await wachtOpBevestigdeMicrofoonverbinding()", self.js)
        self.assertIn('if (status.toestand === "verbonden") return status;', self.js)
        self.assertIn('if (status.toestand === "fout")', self.js)
        self.assertNotIn('toonMelding(automatisch ? "Enige microfoon automatisch verbonden." : "De microfoon wordt verbonden.");', self.js)

    def test_een_verbindingsactie_controleert_actuele_serverstatus(self):
        self.assertIn('const actueleStatus = await vraagAanPython("GET", "/api/status");', self.js)
        self.assertIn('await vraagAanPython("POST", "/api/verbinden"', self.js)
        self.assertIn('await vraagAanPython("POST", "/api/verbreken"', self.js)
        self.assertIn('if (toestand.verbindingInBehandeling) return;', self.js)
        self.assertIn('werkVerbindingsknopBij(status);', self.js)
        self.assertEqual(self.js.count('element("knop-verbinden").addEventListener("click"'), 1)

    @unittest.skipUnless(shutil.which("node"), "Node.js is optioneel bij het ontwikkelen")
    def test_echte_javascript_router_en_verbinding(self):
        test_js = PROJECT / "tests/hulpmiddelen/test_navigatie_verbindingsknop_beta5_1.js"
        resultaat = subprocess.run(["node", str(test_js)], cwd=PROJECT, capture_output=True, text=True, timeout=15)
        self.assertEqual(resultaat.returncode, 0, resultaat.stdout + resultaat.stderr)
        self.assertIn("OK: pagina navigatie", resultaat.stdout)


if __name__ == "__main__":
    unittest.main()
