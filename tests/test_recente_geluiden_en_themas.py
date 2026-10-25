"""Regressies voor de lokale, beperkte geschiedenis en schermpersonalisatie."""
from pathlib import Path
import sqlite3
from contextlib import closing
import tempfile
import unittest

from app.audio.geluidenbibliotheek import PersoonlijkeGeluidenbibliotheek
from app.webinterface.geluidsgroepen import PersoonlijkeGeluidsgroepen
from app.webinterface.recente_geluiden_en_weergave import (
    BASISTHEMAS, MAX_GESCHIEDENIS, OngeldigeWeergaveOfGeschiedenis,
    RecenteGeluidenEnWeergave, controleer_weergave_instellingen,
)


class TestRecenteGeluidenEnThemas(unittest.TestCase):
    def setUp(self):
        self.map = tempfile.TemporaryDirectory()
        self.database = Path(self.map.name) / 'bibliotheek.sqlite3'
        PersoonlijkeGeluidenbibliotheek(self.database)
        self.groepen = PersoonlijkeGeluidsgroepen(self.database)
        self.beheer = RecenteGeluidenEnWeergave(self.database)
        with closing(sqlite3.connect(self.database)) as verbinding:
            with verbinding:
                for nummer in range(7):
                    geluid_id = f'geluid-{nummer}'
                    verbinding.execute('INSERT INTO geluiden VALUES (?, ?, ?, ?, ?)',
                                       (geluid_id, f'Geluid {nummer}', f'C:/test/{nummer}.wav',
                                        f'c:/test/{nummer}.wav', '2026-01-01T12:00:00Z'))
        self.groep_ids = [self.groepen.maak_groep(f'Groep {nummer}') for nummer in range(7)]
        for nummer, groep_id in enumerate(self.groep_ids):
            self.groepen.verander_lidmaatschap(groep_id, f'geluid-{nummer}', True)

    def tearDown(self):
        self.map.cleanup()

    def test_vijf_basisthemas_en_standaardinstellingen(self):
        self.assertEqual(len(BASISTHEMAS), 5)
        instellingen = self.beheer.geef_weergave()
        self.assertEqual(instellingen['thema'], 'obsidian')
        self.assertFalse(instellingen['compact'])
        self.assertIsNone(instellingen['accentkleur'])

    def test_thema_kleur_gradient_en_compact_worden_bewaard(self):
        opgeslagen = self.beheer.bewaar_weergave({
            'thema': 'amethyst', 'accentkleur': '#F0CAFF', 'gradient': 'duidelijk',
            'gradientrichting': 'linksboven', 'compact': True,
        })
        self.assertEqual(opgeslagen['palet']['accent'], '#F0CAFF')
        opnieuw = RecenteGeluidenEnWeergave(self.database).geef_weergave()
        self.assertEqual(opnieuw['thema'], 'amethyst')
        self.assertTrue(opnieuw['compact'])
        self.assertEqual(opnieuw['gradientrichting'], 'linksboven')

    def test_verkeerde_themas_en_css_injectie_worden_geweigerd(self):
        goed = {'thema': 'midnight', 'accentkleur': None, 'gradient': 'uit',
                'gradientrichting': 'onder', 'compact': False}
        foutgevallen = [
            {**goed, 'thema': 'bestaat niet'},
            {**goed, 'accentkleur': 'red; background:url(https://voorbeeld.test)'},
            {**goed, 'accentkleur': '#000000'},
            {**goed, 'gradient': '<script>'},
            {**goed, 'compact': 'false'},
            {**goed, 'gradientrichting': '90deg;filter:blur(1px)'},
            {**goed, 'onbekend': 'waarde'},
        ]
        for fout in foutgevallen:
            with self.subTest(fout=fout), self.assertRaises(OngeldigeWeergaveOfGeschiedenis):
                controleer_weergave_instellingen(fout)
        self.assertEqual(self.beheer.geef_weergave()['thema'], 'obsidian')

    def test_recent_gebruik_toon_maximaal_vijf_groepen_in_gebruiksvolgorde(self):
        for groep in self.groep_ids:
            self.beheer.registreer_groep_geopend(groep)
        resultaat = self.beheer.geef_recente_gebruik()
        self.assertEqual(len(resultaat['groepen']), 5)
        self.assertEqual(resultaat['groepen'][0]['id'], self.groep_ids[6])
        self.assertNotIn(self.groep_ids[0], [x['id'] for x in resultaat['groepen']])
        self.beheer.registreer_groep_geopend(self.groep_ids[1])
        self.assertEqual(self.beheer.geef_recente_gebruik()['groepen'][0]['id'], self.groep_ids[1])

    def test_afspelen_maakt_gekoppelde_groep_automatisch_recent(self):
        self.beheer.registreer_afspelen('geluid-3', 'Geluid 3', 'preview', 'beurt-1')
        self.beheer.registreer_afspeel_einde('geluid-3', 'preview', 'klaar', 1.25, 'beurt-1')
        resultaten = self.beheer.geef_recente_gebruik()
        self.assertEqual(resultaten['groepen'][0]['id'], self.groep_ids[3])
        item = resultaten['geluiden'][0]
        self.assertEqual(item['wijze'], 'preview')
        self.assertEqual(item['afgespeelde_seconden'], 1.25)
        self.assertEqual(item['status'], 'klaar')
        self.assertTrue(item['bestaat_nog'])

    def test_preview_en_uitzenden_worden_niet_door_elkaar_gehaald(self):
        self.beheer.registreer_afspelen('geluid-1', 'Geluid 1', 'preview', 'beurt-p')
        self.beheer.registreer_afspelen('geluid-1', 'Geluid 1', 'gesprek', 'beurt-c')
        self.beheer.registreer_afspeel_einde('geluid-1', 'preview', 'handmatig', .6, 'beurt-p')
        resultaten = self.beheer.geef_recente_gebruik()['geluiden']
        self.assertEqual(len(resultaten), 2)
        self.assertEqual(next(x for x in resultaten if x['wijze'] == 'preview')['status'], 'handmatig')
        self.assertEqual(next(x for x in resultaten if x['wijze'] == 'gesprek')['status'], 'gestart')
        self.beheer.registreer_afspelen('geluid-1', 'Geluid 1', 'gesprek', 'beurt-c')
        self.assertEqual(len(self.beheer.geef_recente_gebruik()['geluiden']), 2)

    def test_geschiedenis_behoudt_geen_audio_en_kan_worden_gewist(self):
        self.beheer.registreer_afspelen('geluid-2', 'Geluid 2', 'gesprek')
        self.assertEqual(len(self.beheer.geef_recente_gebruik()['geluiden']), 1)
        self.beheer.wis_afspeelgeschiedenis()
        self.assertEqual(self.beheer.geef_recente_gebruik(), {'groepen': [], 'geluiden': []})
        with closing(sqlite3.connect(self.database)) as verbinding:
            self.assertEqual(verbinding.execute('SELECT COUNT(*) FROM geluiden').fetchone()[0], 7)
            self.assertEqual(verbinding.execute('SELECT COUNT(*) FROM geluidsgroepen').fetchone()[0], 7)

    def test_eigen_themaprofiel_bewaren_laden_en_verwijderen(self):
        waarden = {'thema': 'midnight', 'accentkleur': '#90BFFF',
                  'gradient': 'subtiel', 'gradientrichting': 'onder', 'compact': False}
        eerste = self.beheer.bewaar_eigen_themaprofiel('Mijn blauw', waarden)
        self.assertEqual(len(self.beheer.geef_eigen_themaprofielen()), 1)
        self.assertEqual(self.beheer.geef_eigen_themaprofielen()[0]['instellingen'], waarden)
        gewijzigd = {**waarden, 'compact': True}
        tweede = self.beheer.bewaar_eigen_themaprofiel('mijn blauw', gewijzigd)
        self.assertEqual(eerste['id'], tweede['id'])
        self.assertEqual(len(self.beheer.geef_eigen_themaprofielen()), 1)
        opnieuw = RecenteGeluidenEnWeergave(self.database)
        self.assertTrue(opnieuw.geef_eigen_themaprofielen()[0]['instellingen']['compact'])
        opnieuw.verwijder_eigen_themaprofiel(eerste['id'])
        self.assertEqual(opnieuw.geef_eigen_themaprofielen(), [])
        # Een profiel verwijderen verandert de actieve weergave niet.
        self.assertEqual(self.beheer.geef_weergave()['thema'], 'obsidian')

    def test_eigen_thema_weigert_ongeldige_naam_en_profielnummer(self):
        waarden = {'thema': 'obsidian', 'accentkleur': None,
                  'gradient': 'uit', 'gradientrichting': 'rechtsboven', 'compact': False}
        for fout in ['', '   ', 'a' * 41, 'een\nander']:
            with self.subTest(fout=fout), self.assertRaises(OngeldigeWeergaveOfGeschiedenis):
                self.beheer.bewaar_eigen_themaprofiel(fout, waarden)
        with self.assertRaises(OngeldigeWeergaveOfGeschiedenis):
            self.beheer.verwijder_eigen_themaprofiel('../../etc/passwd')

    def test_geschiedenis_is_begrensd_en_bestaat_na_herstart(self):
        for nummer in range(MAX_GESCHIEDENIS + 2):
            self.beheer.registreer_afspelen('geluid-1', 'Geluid 1', 'gesprek', f'beurt-{nummer}')
        met_nieuwe_instantie = RecenteGeluidenEnWeergave(self.database)
        with closing(sqlite3.connect(self.database)) as verbinding:
            self.assertEqual(verbinding.execute('SELECT COUNT(*) FROM recent_afgespeeld').fetchone()[0], MAX_GESCHIEDENIS)
        self.assertEqual(len(met_nieuwe_instantie.geef_recente_gebruik(12)['geluiden']), 12)
        with self.assertRaises(OngeldigeWeergaveOfGeschiedenis):
            met_nieuwe_instantie.geef_recente_gebruik(101)


if __name__ == '__main__':
    unittest.main()
