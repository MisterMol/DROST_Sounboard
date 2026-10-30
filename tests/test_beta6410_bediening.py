"""Gerichte tests met echte methodecode en vervangende randafhankelijkheden.
De uploads zijn patches, geen volledig project; AST-extractie voorkomt dat
ontbrekende audioapparaatmodules de afzonderlijke bedieningstests blokkeren.
Dit is geen volledige appintegratietest en geen Windows-audiotest.
"""
from __future__ import annotations
import ast
import math
from pathlib import Path
import unittest
from types import SimpleNamespace
from unittest.mock import Mock
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parents[1]
SERVICE = ROOT / 'app/webinterface/bediening_van_de_audiomotor.py'
SERVER = ROOT / 'app/webinterface/lokale_webserver.py'
MIXER = ROOT / 'app/audio/live_audiomixer.py'


def method(path: Path, name: str, **dependencies):
    tree = ast.parse(path.read_text(encoding='utf-8'))
    nodes = [n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef) and n.name == name]
    if len(nodes) != 1:
        raise AssertionError(f'Methode niet uniek: {name}')
    node = nodes[0]
    node.decorator_list = []
    module = ast.Module(body=[ast.ImportFrom(module='__future__', names=[ast.alias(name='annotations')], level=0), node], type_ignores=[])
    scope = {'OngeldigeWebactie': ValueError, 'OngeldigWebverzoek': ValueError,
             'math': math, 'urlsplit': urlsplit, **dependencies}
    exec(compile(ast.fix_missing_locations(module), str(path), 'exec'), scope)
    return scope[name]


class TestVolumeEnSpeler(unittest.TestCase):
    def test_tijdelijk_volume_verandert_mixer_zonder_opslaan(self):
        service = SimpleNamespace(mixer=Mock(), favorieten=Mock(), logboeken=Mock())
        action = method(SERVICE, 'stel_tijdelijk_effectvolume_in')
        for value in (0, 30, 100):
            self.assertEqual(action(service, value), value)
            service.mixer.stel_algemeen_effectvolume_in.assert_called_with(value)
        self.assertFalse(service.favorieten.mock_calls)
        self.assertFalse(service.logboeken.mock_calls)

    def test_tijdelijk_volume_weigert_ongeldige_invoer(self):
        service = SimpleNamespace(mixer=Mock())
        action = method(SERVICE, 'stel_tijdelijk_effectvolume_in')
        for value in (-1, 201, 2.5, True, None, '30', [], {}):
            with self.subTest(value=value), self.assertRaises(ValueError): action(service, value)
        service.mixer.stel_algemeen_effectvolume_in.assert_not_called()

    def test_opslaan_gebruikt_bestaande_instellingenroute(self):
        audit = Mock()
        service = SimpleNamespace(mixer=Mock(), favorieten=Mock(), logboeken=SimpleNamespace(auditlogboek=Mock()))
        service.favorieten.bewaar_algemeen_effectvolume.return_value = 65
        result = method(SERVICE, 'stel_algemeen_effectvolume_in', schrijf_auditgebeurtenis=audit)(service, 65)
        self.assertEqual(result, 65)
        service.favorieten.bewaar_algemeen_effectvolume.assert_called_once_with(65)
        service.mixer.stel_algemeen_effectvolume_in.assert_called_once_with(65)
        audit.assert_called_once()

    def test_opslaan_mislukt_niet_als_succes_melden(self):
        service = SimpleNamespace(mixer=Mock(), favorieten=Mock(), logboeken=Mock())
        service.favorieten.bewaar_algemeen_effectvolume.side_effect = OSError('schijf niet beschikbaar')
        with self.assertRaises(OSError):
            method(SERVICE, 'stel_algemeen_effectvolume_in', schrijf_auditgebeurtenis=Mock())(service, 65)
        service.mixer.stel_algemeen_effectvolume_in.assert_not_called()

    def handler(self, data):
        service = Mock()
        service.stel_tijdelijk_effectvolume_in.return_value = 40
        handler = SimpleNamespace(path='/api/speler/volume', server=SimpleNamespace(bediening=service),
            _controleer_herkomst=Mock(), _lees_invoer_json=Mock(return_value=data),
            _stuur_json=Mock(), _verwerk_fout=Mock())
        return handler, service

    def test_http_tijdelijk_volume_vereist_bestaande_herkomstcontrole(self):
        handler, service = self.handler({'percentage': 40})
        method(SERVER, 'do_POST')(handler)
        handler._controleer_herkomst.assert_called_once_with(True)
        service.stel_tijdelijk_effectvolume_in.assert_called_once_with(40)
        handler._stuur_json.assert_called_once_with(200, {'percentage': 40})
        handler._verwerk_fout.assert_not_called()

    def test_http_geen_extra_of_ontbrekende_velden(self):
        for data in ({}, {'percentage': 40, 'bestand': 'x'}):
            with self.subTest(data=data):
                handler, service = self.handler(data)
                method(SERVER, 'do_POST')(handler)
                handler._verwerk_fout.assert_called_once()
                service.stel_tijdelijk_effectvolume_in.assert_not_called()

    def test_http_geweigerde_herkomst_verandert_niets(self):
        handler, service = self.handler({'percentage':40})
        handler._controleer_herkomst.side_effect = ValueError('Geen toegang')
        method(SERVER, 'do_POST')(handler)
        handler._lees_invoer_json.assert_not_called()
        service.stel_tijdelijk_effectvolume_in.assert_not_called()

    def test_live_opnieuw_gebruikt_begin_van_de_afspeelbeurt(self):
        service = SimpleNamespace(mixer=Mock())
        service.mixer.geef_huidige_status.return_value = SimpleNamespace(toestand='verbonden', afspeelbeurt_id='a')
        method(SERVICE,'bedien_lopend_geluid')(service,'a',fractie=0)
        service.mixer.zoek_in_lopend_geluid.assert_called_once_with('a',0)

    def test_oude_afspeelbeurt_mag_nieuwe_niet_terugspoelen(self):
        service = SimpleNamespace(mixer=Mock())
        service.mixer.geef_huidige_status.return_value = SimpleNamespace(toestand='verbonden', afspeelbeurt_id='nieuw')
        with self.assertRaises(ValueError):method(SERVICE,'bedien_lopend_geluid')(service,'oud',fractie=0)
        service.mixer.zoek_in_lopend_geluid.assert_not_called()

    def test_blijven_herhalen_is_een_aparte_opdracht(self):
        service = SimpleNamespace(mixer=Mock())
        service.mixer.geef_huidige_status.return_value = SimpleNamespace(toestand='verbonden', afspeelbeurt_id='a')
        method(SERVICE,'bedien_lopend_geluid')(service,'a',herhalen=True)
        service.mixer.stel_lopend_geluid_herhalen_in.assert_called_once_with('a',True)
        service.mixer.zoek_in_lopend_geluid.assert_not_called()

    def test_mixer_volume_verandert_samples_zonder_afspeelpositie_reset(self):
        try: import numpy as np
        except ImportError: self.skipTest('numpy ontbreekt')
        fragment = SimpleNamespace(voorbereide_samples=np.full((4096,2),.2,dtype=np.float32),
            huidige_framepositie=0,herhalen=False,fade_in_frames=0)
        mixer = SimpleNamespace(_huidige_geluid=fragment,_algemeen_effectvolume_percentage=100,
            _vorige_effectvolume_factor=1.,_stuur_effect_naar_eigen_headset=None,
            _eigen_stem_monitor_aan=False,_sluit_lopend_geluid_af=Mock())
        rms=lambda frames:float(np.sqrt(np.mean(frames*frames)))
        render=method(MIXER,'_verwerk_het_lopende_geluid_in_het_audioblok',np=np,
                      _meet_effect_rms_zonder_audio_te_onderbreken=rms)
        set_volume=method(MIXER,'stel_algemeen_effectvolume_in')
        a=np.zeros((256,2),dtype=np.float32);render(mixer,a)
        set_volume(mixer,25)
        ramp=np.zeros_like(a);render(mixer,ramp)
        b=np.zeros_like(a);render(mixer,b)
        self.assertAlmostEqual(float(a.mean()),.2,places=5)
        self.assertAlmostEqual(float(b.mean()),.05,places=5)
        self.assertEqual(fragment.huidige_framepositie,768)
        self.assertIs(mixer._huidige_geluid,fragment)
        set_volume(mixer,100);render(mixer,np.zeros_like(a))
        c=np.zeros_like(a);render(mixer,c)
        self.assertAlmostEqual(float(c.mean()),.2,places=5)
        mixer._sluit_lopend_geluid_af.assert_not_called()

    def test_spelerknoppen_en_volume_hebben_unieke_ids(self):
        markup = (ROOT/'app/webinterface/statisch/dashboard.html').read_text(encoding='utf-8')
        for identifier in ('knop-speler-opnieuw','knop-preview-herhaal','speler-volume-schuif','zoeken'):
            self.assertEqual(markup.count(f'id="{identifier}"'),1)
        self.assertNotIn('id="speler-volume-regelaar" class="player-volume-regelaar" hidden',markup)

if __name__ == '__main__': unittest.main()
