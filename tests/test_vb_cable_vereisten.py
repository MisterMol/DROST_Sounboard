"""Statuscontrole zonder echte driver, registerwijzigingen of audiostreams."""
from __future__ import annotations

import json
from pathlib import Path
import unittest
from unittest import mock

from app.audio.apparatenbeheer import GevondenAudioapparaat, ResultaatVanApparaatcontrole
from app.audio.kabelcontrole import selecteer_de_twee_uiteinden_van_vb_cable, KabelcontroleFout
from app.audio.vb_cable_vereisten import beoordeel_vb_cable, resultaat_voor_mislukte_controle
from app.webinterface.bediening_van_de_audiomotor import WebbedieningVanDrostSoundboard


def apparaat(nummer, naam, *, invoer=0, uitvoer=0, api='Windows WASAPI'):
    return GevondenAudioapparaat(nummer, naam, api, invoer, uitvoer)


AFSPEEL = apparaat(21, 'CABLE Input (VB-Audio Virtual Cable)', uitvoer=2)
OPNAME = apparaat(23, 'CABLE Output (VB-Audio Virtual Cable)', invoer=2)


class TestVBCheck(unittest.TestCase):
    def test_gereed_bij_precies_twee_gebruikbare_kanten(self):
        status = beoordeel_vb_cable([OPNAME, AFSPEEL])
        self.assertEqual(status['status'], 'gereed')
        self.assertTrue(status['bruikbaar'])
        self.assertEqual(status['aantal_afspeelpunten'], 1)
        self.assertEqual(status['aantal_opnamepunten'], 1)
        selectie = selecteer_de_twee_uiteinden_van_vb_cable([OPNAME, AFSPEEL])
        self.assertEqual(selectie.afspeelkant.huidig_apparaatnummer, 21)
        self.assertEqual(selectie.opnamekant.huidig_apparaatnummer, 23)

    def test_ontbreekt_met_gewoon_microfoon_of_alleen_andere_kabel(self):
        andere = apparaat(2, 'CABLE A Input (VB-Audio Cable A)', uitvoer=2)
        status = beoordeel_vb_cable([andere, apparaat(3, 'Headset Mic', invoer=1)])
        self.assertEqual(status['status'], 'ontbreekt')
        self.assertFalse(status['bruikbaar'])
        with self.assertRaises(KabelcontroleFout):
            selecteer_de_twee_uiteinden_van_vb_cable([andere])

    def test_onvolledig_met_alleen_een_kant(self):
        self.assertEqual(beoordeel_vb_cable([AFSPEEL])['status'], 'onvolledig')
        self.assertEqual(beoordeel_vb_cable([OPNAME])['status'], 'onvolledig')

    def test_dubbele_kabel_wordt_niet_goedgekeurd(self):
        dubbel = [AFSPEEL, OPNAME, apparaat(25, AFSPEEL.naam, uitvoer=2)]
        self.assertEqual(beoordeel_vb_cable(dubbel)['status'], 'meerdere')
        self.assertFalse(beoordeel_vb_cable(dubbel)['bruikbaar'])

    def test_wasapi_en_kanalen_zijn_verplicht(self):
        niet_wasapi = apparaat(99, AFSPEEL.naam, uitvoer=2, api='MME')
        geen_kanalen = apparaat(98, OPNAME.naam, invoer=0)
        self.assertEqual(beoordeel_vb_cable([niet_wasapi, geen_kanalen])['status'], 'ontbreekt')

    def test_onbekende_controlefout_is_niet_ontbrekende_driver(self):
        antwoord = resultaat_voor_mislukte_controle()
        self.assertEqual(antwoord['status'], 'controle_mislukt')
        self.assertFalse(antwoord['bruikbaar'])
        self.assertNotIn('ontbreekt', antwoord['melding'])

    def test_alleen_officiele_website(self):
        antwoord = beoordeel_vb_cable([])
        self.assertEqual(antwoord['officiele_website'], 'https://vb-audio.com/Cable/')
        self.assertTrue(json.loads(json.dumps(antwoord)))

    def test_uitlezen_begint_geen_audio_en_slaat_fouten_op(self):
        # Gebruik bewust geen WebbedieningVanDrostSoundboard.__init__: die
        # maakt echte bibliotheek-/mixobjecten aan, niet nodig voor diagnose.
        webbediening = object.__new__(WebbedieningVanDrostSoundboard)
        fake_logger = mock.Mock()
        webbediening.logboeken = mock.Mock(softwarelogboek=fake_logger)
        overzicht = ResultaatVanApparaatcontrole([AFSPEEL, OPNAME], True, True, False)
        with mock.patch('app.webinterface.bediening_van_de_audiomotor.controleer_werkelijk_aangesloten_audioapparaten', return_value=overzicht) as inspecteer:
            self.assertEqual(webbediening.geef_vb_cable_status()['status'], 'gereed')
            inspecteer.assert_called_once_with(fake_logger)
        with mock.patch('app.webinterface.bediening_van_de_audiomotor.controleer_werkelijk_aangesloten_audioapparaten', side_effect=OSError('nepportaudio')):
            self.assertEqual(webbediening.geef_vb_cable_status()['status'], 'controle_mislukt')
            fake_logger.exception.assert_called_once()

    def test_dashboard_heeft_reactieve_inline_melding_en_officiele_link(self):
        html = (Path(__file__).parents[1] / 'app/webinterface/statisch/dashboard.html').read_text(encoding='utf-8')
        js = (Path(__file__).parents[1] / 'app/webinterface/statisch/dashboard.js').read_text(encoding='utf-8')
        self.assertIn('id="vb-cable-waarschuwing"', html)
        self.assertIn('https://vb-audio.com/Cable/', html)
        self.assertIn('rel="noopener noreferrer"', html)
        self.assertIn('id="vb-cable-opnieuw"', html)
        self.assertIn("'/api/vereisten/vb-cable'", js)
        self.assertIn('vak.hidden = true;', js)
        self.assertIn('element(\'vb-cable-omschrijving\').textContent', js)


if __name__ == '__main__':
    unittest.main()
