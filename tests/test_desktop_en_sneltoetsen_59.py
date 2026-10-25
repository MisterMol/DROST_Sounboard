"""Tests zonder echte Windows-hotkeys of Razer-microfoon."""
from __future__ import annotations

import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import MagicMock, patch

from app.desktop.een_actieve_instantie import EenActieveInstantie
from app.desktop.sneltoetsinstellingen import (
    OpslagVanSneltoetsinstellingen, OngeldigeSneltoetsinstelling,
    controleer_sneltoetsinstellingen, geef_standaard_sneltoetsen,
)
from app.desktop.windows_sneltoetsen import vertaal_sneltoets_naar_windows, MOD_CONTROL, MOD_ALT, MOD_NOREPEAT
from app.desktop.bediening_van_sneltoetsen import BedieningVanGlobaleSneltoetsen


class TestVeiligeSneltoetsinstellingen(unittest.TestCase):
    def test_standaard_staan_sneltoetsen_uit(self):
        standaard = geef_standaard_sneltoetsen()
        self.assertFalse(standaard['ingeschakeld'])
        self.assertEqual(standaard['combinaties']['favoriet_1'], 'CTRL+ALT+1')
        self.assertEqual(standaard['combinaties']['stop'], 'CTRL+ALT+0')

    def test_gebruikersinstellingen_blijven_na_herstart_staan(self):
        with tempfile.TemporaryDirectory() as mapnaam:
            opslag = OpslagVanSneltoetsinstellingen(Path(mapnaam) / 'toetsen.json')
            opslag.bewaar_instellingen({'ingeschakeld': True, 'combinaties': {'favoriet_15': 'CTRL+SHIFT+F15'}})
            self.assertEqual(OpslagVanSneltoetsinstellingen(opslag.opslagpad).lees_instellingen(),
                             {'ingeschakeld': True, 'combinaties': {'favoriet_15': 'CTRL+SHIFT+F15'}})

    def test_onjuiste_en_gevaarlijke_combinaties_worden_geweigerd(self):
        for combinatie in ('ALT+TAB', 'WIN+R', 'CTRL+C', 'CTRL+ALT+DELETE', 'CTRL+SHIFT+A', '', None):
            with self.subTest(combinatie=combinatie), self.assertRaises(OngeldigeSneltoetsinstelling):
                controleer_sneltoetsinstellingen({'ingeschakeld': True, 'combinaties': {'favoriet_1': combinatie}})

    def test_dubbele_combinatie_wordt_afgewezen(self):
        with self.assertRaises(OngeldigeSneltoetsinstelling):
            controleer_sneltoetsinstellingen({'ingeschakeld': True, 'combinaties': {
                'favoriet_1': 'CTRL+ALT+1', 'stop': 'CTRL+ALT+1'}})

    def test_onbekende_actie_wordt_afgewezen(self):
        with self.assertRaises(OngeldigeSneltoetsinstelling):
            controleer_sneltoetsinstellingen({'ingeschakeld': True, 'combinaties': {'spel_kijken': 'CTRL+ALT+1'}})

    def test_ongeldig_bestand_wordt_nooit_automatisch_overschreven(self):
        with tempfile.TemporaryDirectory() as mapnaam:
            locatie = Path(mapnaam) / 'sneltoetsen.json'
            locatie.write_text('{geen geldige json', encoding='utf-8')
            opslag = OpslagVanSneltoetsinstellingen(locatie)
            with self.assertRaises(OngeldigeSneltoetsinstelling):
                opslag.lees_instellingen()
            self.assertEqual(locatie.read_text(encoding='utf-8'), '{geen geldige json')

    def test_windows_sneltoets_wordt_naar_juiste_modifiers_vertaald(self):
        mods, toetsenbordcode = vertaal_sneltoets_naar_windows('CTRL+ALT+1')
        self.assertEqual(toetsenbordcode, ord('1'))
        self.assertEqual(mods, MOD_CONTROL | MOD_ALT | MOD_NOREPEAT)

    def test_functietoets_wordt_ook_ondersteund(self):
        mods, code = vertaal_sneltoets_naar_windows('CTRL+SHIFT+F15')
        self.assertEqual(code, 126)
        self.assertTrue(mods & MOD_CONTROL)


@unittest.skipIf(sys.platform == 'win32', 'De Windows-mutex wordt afzonderlijk op een Windows-machine getest')
class TestEenActieveInstantie(unittest.TestCase):
    def test_maar_een_proces_mag_het_dashboard_beheren(self):
        with tempfile.TemporaryDirectory() as mapnaam:
            eerste = EenActieveInstantie(Path(mapnaam))
            tweede = EenActieveInstantie(Path(mapnaam))
            self.assertTrue(eerste.probeer_eigenaarschap_te_krijgen())
            self.assertFalse(tweede.probeer_eigenaarschap_te_krijgen())
            eerste.schrijf_lokaal_dashboardadres(8765)
            self.assertEqual(tweede.lees_adres_van_bestaande_instantie(), 'http://127.0.0.1:8765/')
            eerste.laat_vergrendeling_los()
            self.assertTrue(tweede.probeer_eigenaarschap_te_krijgen())
            tweede.laat_vergrendeling_los()

    def test_oude_poortgegevens_zijn_geen_bewijs_van_een_levend_proces(self):
        with tempfile.TemporaryDirectory() as mapnaam:
            eerste = EenActieveInstantie(Path(mapnaam))
            eerste.toestandbestand.write_text(json.dumps({'poort': 8765}), encoding='utf-8')
            self.assertTrue(eerste.probeer_eigenaarschap_te_krijgen())
            eerste.laat_vergrendeling_los()


class TestHotkeyActies(unittest.TestCase):
    def maak_bediening_en_sneltoetsen(self, databasepad: Path):
        bediening = MagicMock()
        bediening.favorieten.geef_alle_favorietplekken.return_value = ['geluid-van-favoriet-1'] + [None]*14
        bediening.logboeken.softwarelogboek = MagicMock()
        bediening.logboeken.auditlogboek = MagicMock()
        opslag = OpslagVanSneltoetsinstellingen(databasepad)
        service = BedieningVanGlobaleSneltoetsen(bediening, opslag)
        return bediening, service

    def test_favoriet_1_wordt_naar_de_bestaande_mixer_gestuurd(self):
        with tempfile.TemporaryDirectory() as mapnaam:
            bediening, service = self.maak_bediening_en_sneltoetsen(Path(mapnaam) / 'sneltoets.json')
            with patch('app.desktop.bediening_van_sneltoetsen.schrijf_auditgebeurtenis'):
                service.voer_ingestelde_actie_uit('favoriet_1')
            bediening.speel_geluid_uit_de_bibliotheek.assert_called_once_with('geluid-van-favoriet-1')

    def test_stop_blijft_los_van_microfoonverbinding(self):
        with tempfile.TemporaryDirectory() as mapnaam:
            bediening, service = self.maak_bediening_en_sneltoetsen(Path(mapnaam) / 'sneltoets.json')
            with patch('app.desktop.bediening_van_sneltoetsen.schrijf_auditgebeurtenis'):
                service.voer_ingestelde_actie_uit('stop')
            bediening.stop_het_huidige_geluid.assert_called_once()
            bediening.verbreek_de_verbinding.assert_not_called()

    def test_lege_favoriet_geeft_geen_audio(self):
        with tempfile.TemporaryDirectory() as mapnaam:
            bediening, service = self.maak_bediening_en_sneltoetsen(Path(mapnaam) / 'sneltoets.json')
            with patch('app.desktop.bediening_van_sneltoetsen.schrijf_auditgebeurtenis'):
                service.voer_ingestelde_actie_uit('favoriet_2')
            bediening.speel_geluid_uit_de_bibliotheek.assert_not_called()

    def test_beschadigde_config_zet_hotkeys_veilig_uit_zonder_audio_te_blokkeren(self):
        with tempfile.TemporaryDirectory() as mapnaam:
            locatie = Path(mapnaam) / 'sneltoets.json'
            locatie.write_text('{kapot', encoding='utf-8')
            bediening, service = self.maak_bediening_en_sneltoetsen(locatie)
            self.assertFalse(service.geef_huidige_instellingen()['ingeschakeld'])
            self.assertEqual(locatie.read_text(encoding='utf-8'), '{kapot')
            bediening.logboeken.softwarelogboek.exception.assert_called_once()

    def test_instellingen_worden_zonder_wijziging_van_de_audiomixer_bewaard(self):
        with tempfile.TemporaryDirectory() as mapnaam:
            bediening, service = self.maak_bediening_en_sneltoetsen(Path(mapnaam) / 'sneltoets.json')
            with patch('app.desktop.bediening_van_sneltoetsen.schrijf_auditgebeurtenis'):
                resultaat = service.pas_instellingen_aan({'ingeschakeld': False, 'combinaties': {'stop': 'CTRL+SHIFT+F12'}})
            self.assertEqual(resultaat['combinaties']['stop'], 'CTRL+SHIFT+F12')
            self.assertEqual(service.opslag.lees_instellingen()['combinaties']['stop'], 'CTRL+SHIFT+F12')
            bediening.mixer.assert_not_called()


if __name__ == '__main__':
    unittest.main()
