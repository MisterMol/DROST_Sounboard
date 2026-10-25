"""Voorkom dat twee processen tegelijk VB-CABLE en dezelfde logboeken openen.

Windows gebruikt een benoemde mutex. Die wordt door Windows zelf vrijgegeven
bij een crash, dus een achtergebleven toestand.json blokkeert geen nieuwe start.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
import sys
from typing import IO


class ErDraaitAlEenInstantie(RuntimeError):
    """Een ander proces bezit de vergrendeling van deze Windows-sessie."""


def geef_map_voor_desktopinstellingen() -> Path:
    basis = os.environ.get('LOCALAPPDATA')
    return (Path(basis) / 'DrostSoundboard' if basis else
            Path.home() / '.drostsoundboard' / 'DrostSoundboard')


class EenActieveInstantie:
    """Houd de Windows-mutex open zolang het volledige achtergrondproces leeft."""

    def __init__(self, gegevensmap: Path | None = None):
        self.gegevensmap = Path(gegevensmap) if gegevensmap is not None else geef_map_voor_desktopinstellingen()
        self.toestandbestand = self.gegevensmap / 'actieve_desktopinstantie.json'
        self._windows_mutex: int | None = None
        self._unix_bestand: IO[bytes] | None = None
        self._eigenaar = False

    def probeer_eigenaarschap_te_krijgen(self) -> bool:
        if self._eigenaar:
            return True
        self.gegevensmap.mkdir(parents=True, exist_ok=True)
        if sys.platform == 'win32':
            import ctypes
            from ctypes import wintypes
            kernel32 = ctypes.WinDLL('kernel32', use_last_error=True)
            kernel32.CreateMutexW.argtypes = [ctypes.c_void_p, wintypes.BOOL, wintypes.LPCWSTR]
            kernel32.CreateMutexW.restype = wintypes.HANDLE
            kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
            kernel32.CloseHandle.restype = wintypes.BOOL
            # Local beperkt de mutex tot dezelfde interactieve Windows-sessie.
            # Er is geen administrator- of globale privilege nodig.
            mutex = kernel32.CreateMutexW(None, False, 'Local\\DrostSoundboard_Desktop_EenProces_v1')
            if not mutex:
                raise OSError(ctypes.get_last_error(), 'DESKTOP-001: Windows-mutex kon niet gemaakt worden.')
            if ctypes.get_last_error() == 183:  # ERROR_ALREADY_EXISTS
                kernel32.CloseHandle(mutex)
                return False
            self._windows_mutex = mutex
        else:
            # Alleen voor automatische tests / ontwikkeling buiten Windows.
            import fcntl
            bestand = (self.gegevensmap / 'proces.lock').open('a+b')
            try:
                fcntl.flock(bestand.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                bestand.close()
                return False
            self._unix_bestand = bestand
        self._eigenaar = True
        return True

    def schrijf_lokaal_dashboardadres(self, poort: int) -> None:
        if not self._eigenaar:
            raise ErDraaitAlEenInstantie('DESKTOP-002: alleen de eigen instantie mag zijn poort publiceren.')
        if type(poort) is not int or not 1 <= poort <= 65535:
            raise ValueError('DESKTOP-003: ongeldige lokale serverpoort.')
        inhoud = {'proces_id': os.getpid(), 'poort': poort}
        tijdelijk = self.toestandbestand.with_suffix('.tmp')
        tijdelijk.write_text(json.dumps(inhoud), encoding='utf-8')
        os.replace(tijdelijk, self.toestandbestand)

    def lees_adres_van_bestaande_instantie(self) -> str | None:
        try:
            gegevens = json.loads(self.toestandbestand.read_text(encoding='utf-8'))
            poort = gegevens.get('poort')
            if type(poort) is int and 1 <= poort <= 65535:
                return f'http://127.0.0.1:{poort}/'
        except (OSError, ValueError, TypeError, AttributeError):
            pass
        return None

    def laat_vergrendeling_los(self) -> None:
        if not self._eigenaar:
            return
        # Bestand verwijderen vóór de mutex, zodat een opvolgend proces nooit
        # de poortinformatie van een reeds afgesloten server gebruikt.
        self.toestandbestand.unlink(missing_ok=True)
        if self._windows_mutex is not None:
            import ctypes
            from ctypes import wintypes
            kernel32 = ctypes.WinDLL('kernel32', use_last_error=True)
            kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
            kernel32.CloseHandle(self._windows_mutex)
            self._windows_mutex = None
        if self._unix_bestand is not None:
            import fcntl
            fcntl.flock(self._unix_bestand.fileno(), fcntl.LOCK_UN)
            self._unix_bestand.close()
            self._unix_bestand = None
        self._eigenaar = False

    def __enter__(self):
        if not self.probeer_eigenaarschap_te_krijgen():
            raise ErDraaitAlEenInstantie('DESKTOP-004: er draait al een DrostSoundboard.')
        return self

    def __exit__(self, *_):
        self.laat_vergrendeling_los()
