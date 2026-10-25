"""Geen echte Windows Registry, netwerk, audio of update tijdens deze tests."""
from __future__ import annotations

import json
import contextlib
import sys
import types
from pathlib import Path
import tempfile
import unittest
from unittest import mock

from app.desktop import opstartinstellingen, release_updates
from start_desktop import geef_startargumenten, start_drostsoundboard_als_desktopprogramma


class NepReleaseManager:
    def __init__(self, *, info=None, pending=None):
        self.info = info
        self.pending = pending
        self.controles = 0
        self.downloads = 0
        self.toegepast = []

    def check_for_updates(self):
        self.controles += 1
        return self.info

    def get_update_pending_restart(self):
        return self.pending

    def download_updates(self, info):
        self.downloads += 1
        self.pending = info

    def wait_exit_then_apply_updates(self, item, silent, restart, restart_args):
        self.toegepast.append((item, silent, restart, restart_args))


class TestReleaseZestig(unittest.TestCase):
    def test_achtergrondparameter(self):
        self.assertTrue(geef_startargumenten(['--achtergrond']).achtergrond)
        self.assertFalse(geef_startargumenten([]).achtergrond)
        self.assertEqual(geef_startargumenten(['--controleer-release', 'test.json']).controleer_release, 'test.json')

    def test_bestaand_proces_opent_niet_in_achtergrondmodus(self):
        with mock.patch('start_desktop.sys.platform', 'win32'), \
             mock.patch('start_desktop.EenActieveInstantie') as instantie, \
             mock.patch('start_desktop.webbrowser.open') as browser:
            instantie.return_value.probeer_eigenaarschap_te_krijgen.return_value = False
            instantie.return_value.lees_adres_van_bestaande_instantie.return_value = 'http://127.0.0.1:8765/'
            self.assertEqual(start_drostsoundboard_als_desktopprogramma(open_browser=False), 0)
            browser.assert_not_called()
            self.assertEqual(start_drostsoundboard_als_desktopprogramma(open_browser=True), 0)
            browser.assert_called_once()

    def test_reponiet_geconfigureerd(self):
        with tempfile.TemporaryDirectory() as mapnaam:
            pad = Path(mapnaam) / 'releasebron.json'
            pad.write_text('{"repository_url": "", "channel": "beta"}', encoding='utf-8')
            self.assertEqual(release_updates.lees_releasebron(pad), ('', 'beta'))
            pad.write_text('{"repository_url": "http://example.com/evil", "channel": "beta"}', encoding='utf-8')
            self.assertEqual(release_updates.lees_releasebron(pad), ('', 'beta'))
            pad.write_text('{"repository_url": "https://github.com/owner/repo", "channel": "stable"}', encoding='utf-8')
            self.assertEqual(release_updates.lees_releasebron(pad), ('https://github.com/owner/repo', 'stable'))

    @mock.patch.object(release_updates, 'is_release_installatie', return_value=True)
    @mock.patch.object(release_updates, 'lees_releasebron', return_value=('https://github.com/owner/repo', 'beta'))
    def test_update_downloadt_zonder_toepassen(self, _url, _install):
        manager = NepReleaseManager(info=object())
        service = release_updates.ReleaseUpdateService(manager_factory=lambda: manager)
        service.controleer_en_download()
        self.assertEqual(manager.controles, 1)
        self.assertEqual(manager.downloads, 1)
        self.assertEqual(manager.toegepast, [])
        self.assertIn('gereed', service.geef_status())
        service.stop()
        self.assertTrue(service.pas_toe_na_audio_stop())
        self.assertEqual(len(manager.toegepast), 1)

    @mock.patch.object(release_updates, 'is_release_installatie', return_value=True)
    @mock.patch.object(release_updates, 'lees_releasebron', return_value=('https://github.com/owner/repo', 'beta'))
    def test_update_alleen_expliciet_na_stop(self, _url, _install):
        manager = NepReleaseManager(pending=object())
        service = release_updates.ReleaseUpdateService(manager_factory=lambda: manager)
        self.assertTrue(service.pas_toe_na_audio_stop())
        self.assertEqual(len(manager.toegepast), 1)
        self.assertEqual(manager.toegepast[0][1:], (True, False, None))

    @mock.patch.object(release_updates, 'is_release_installatie', return_value=True)
    @mock.patch.object(release_updates, 'lees_releasebron', return_value=('https://github.com/owner/repo', 'beta'))
    def test_update_voor_audio_start_en_na_mutex(self, _url, _install):
        manager = NepReleaseManager(pending=object())
        service = release_updates.ReleaseUpdateService(manager_factory=lambda: manager)
        self.assertTrue(service.pas_toe_voor_audio_start(achtergrond=True))
        self.assertEqual(manager.toegepast[0][1:], (True, True, ['--achtergrond']))

    @mock.patch.object(release_updates, 'is_release_installatie', return_value=True)
    @mock.patch.object(release_updates, 'lees_releasebron', return_value=('https://github.com/owner/repo', 'beta'))
    def test_update_installatie_nooit_tijdens_download(self, _url, _install):
        manager = NepReleaseManager(pending=object())
        service = release_updates.ReleaseUpdateService(manager_factory=lambda: manager)
        service._busy.acquire()
        try:
            self.assertFalse(service.pas_toe_na_audio_stop())
            self.assertEqual(manager.toegepast, [])
        finally:
            service._busy.release()

    @mock.patch.object(release_updates, 'is_release_installatie', return_value=True)
    @mock.patch.object(release_updates, 'lees_releasebron', return_value=('https://github.com/owner/repo', 'beta'))
    def test_netwerkfout_bewaart_oude_installatie(self, _url, _install):
        def kapot():
            raise TimeoutError('offline')
        service = release_updates.ReleaseUpdateService(manager_factory=kapot)
        service.controleer_en_download()
        self.assertIn('mislukt', service.geef_status())

    def test_ontwikkelomgeving_krijgt_geen_updates(self):
        manager = NepReleaseManager(info=object())
        service = release_updates.ReleaseUpdateService(manager_factory=lambda: manager)
        with mock.patch.object(release_updates, 'is_release_installatie', return_value=False):
            service.controleer_en_download()
        self.assertEqual(manager.controles, 0)

    def test_start_met_windows_schrijft_stabiel_pad_en_uninstall_ruimt_op(self):
        opslag = {}

        @contextlib.contextmanager
        def sleutel(*_):
            yield object()

        def lees(*_):
            if 'DrostSoundboard' not in opslag:
                raise FileNotFoundError()
            return opslag['DrostSoundboard'], 1

        winreg = types.SimpleNamespace(
            HKEY_CURRENT_USER=1, KEY_SET_VALUE=2, KEY_READ=4, REG_SZ=1,
            OpenKey=sleutel, CreateKeyEx=sleutel, QueryValueEx=lees,
            SetValueEx=lambda key, naam, r, soort, inhoud: opslag.__setitem__(naam, inhoud),
            DeleteValue=lambda key, naam: opslag.pop(naam)
        )
        launcher = Path('C:/Users/test/AppData/Local/DrostSoundboard.Desktop/DrostSoundboard.exe')
        with mock.patch.object(opstartinstellingen.sys, 'platform', 'win32'), \
             mock.patch.dict(sys.modules, {'winreg': winreg}), \
             mock.patch.object(opstartinstellingen, 'bepaal_stabiele_launcher', return_value=launcher):
            self.assertFalse(opstartinstellingen.start_met_windows_ingeschakeld())
            opstartinstellingen.wijzig_start_met_windows(True)
            self.assertEqual(opslag['DrostSoundboard'], f'"{launcher}" --achtergrond')
            self.assertTrue(opstartinstellingen.start_met_windows_ingeschakeld())
            self.assertTrue(opstartinstellingen.verwijder_start_met_windows_bij_verwijderen(launcher=launcher))
            self.assertFalse(opstartinstellingen.start_met_windows_ingeschakeld())

    def test_uninstall_laat_onbekende_registrywaarde_met_rust(self):
        opslag = {'DrostSoundboard': '"C:/AndereApp.exe"'}
        @contextlib.contextmanager
        def sleutel(*_):
            yield object()
        winreg = types.SimpleNamespace(
            HKEY_CURRENT_USER=1, KEY_SET_VALUE=2, KEY_READ=4, REG_SZ=1,
            OpenKey=sleutel, QueryValueEx=lambda *_: (opslag['DrostSoundboard'], 1),
            DeleteValue=lambda *_: opslag.pop('DrostSoundboard'),
        )
        with mock.patch.object(opstartinstellingen.sys, 'platform', 'win32'), \
             mock.patch.dict(sys.modules, {'winreg': winreg}):
            verwijderd = opstartinstellingen.verwijder_start_met_windows_bij_verwijderen(
                launcher=Path('C:/Gebruiker/DrostSoundboard.Desktop/DrostSoundboard.exe'))
        self.assertFalse(verwijderd)
        self.assertEqual(opslag['DrostSoundboard'], '"C:/AndereApp.exe"')

    def test_stabiele_launcher_in_velopack_root(self):
        with tempfile.TemporaryDirectory() as mapnaam:
            root = Path(mapnaam)
            current = root / 'current'
            current.mkdir()
            exe = current / 'DrostSoundboard.exe'
            exe.write_bytes(b'')
            (root / 'DrostSoundboard.exe').write_bytes(b'')
            (root / 'Update.exe').write_bytes(b'')
            p = opstartinstellingen.bepaal_stabiele_launcher(executable=str(exe), frozen=True,
                                                              platformnaam='win32')
            self.assertEqual(p, root / 'DrostSoundboard.exe')
            self.assertIsNone(opstartinstellingen.bepaal_stabiele_launcher(
                executable=str(exe), frozen=False, platformnaam='win32'))
            (root / 'Update.exe').unlink()
            self.assertIsNone(opstartinstellingen.bepaal_stabiele_launcher(
                executable=str(exe), frozen=True, platformnaam='win32'))


if __name__ == '__main__':
    unittest.main()
