"""Optionele Windows-aanmeldstart via de blijvende Velopack-launcher.

Geen adminrechten, geen geplande taken en geen instabiel current-pad.
In een broncode- of losse EXE-uitvoering wordt niets in het register gezet.
"""
from __future__ import annotations

import os
from pathlib import Path
import sys

REGISTER_PAD = r'Software\Microsoft\Windows\CurrentVersion\Run'
REGISTER_WAARDE = 'DrostSoundboard'


def bepaal_stabiele_launcher(*, executable: str | None = None,
                              frozen: bool | None = None,
                              platformnaam: str | None = None) -> Path | None:
    """Zoek het permanente EXE-startpunt buiten de vervangbare map ``current``."""
    if (platformnaam or sys.platform) != 'win32':
        return None
    if frozen is None:
        frozen = bool(getattr(sys, 'frozen', False))
    if not frozen:
        return None
    app = Path(executable or sys.executable)
    if app.name.casefold() != 'drostsoundboard.exe' or app.parent.name.casefold() != 'current':
        return None
    root = app.parent.parent
    starter = root / 'DrostSoundboard.exe'
    if not starter.is_file() or not (root / 'Update.exe').is_file():
        return None
    return starter


def _commando(starter: Path) -> str:
    return f'"{starter}" --achtergrond'


def _lees_huidige_registerwaarde():
    import winreg
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, REGISTER_PAD, 0, winreg.KEY_READ) as sleutel:
            waarde, soort = winreg.QueryValueEx(sleutel, REGISTER_WAARDE)
        return waarde if soort == winreg.REG_SZ and isinstance(waarde, str) else None
    except FileNotFoundError:
        return None


def start_met_windows_ingeschakeld(starter: Path | None = None) -> bool:
    """Controleer het register zonder er iets aan te veranderen."""
    if sys.platform != 'win32':
        return False
    launcher = starter if starter is not None else bepaal_stabiele_launcher()
    return bool(launcher and _lees_huidige_registerwaarde() == _commando(launcher))


def wijzig_start_met_windows(ingeschakeld: bool) -> None:
    """Pas uitsluitend onze eigen HKCU Run-waarde aan; geen adminrechten."""
    if sys.platform != 'win32':
        raise OSError('Start met Windows is alleen op Windows beschikbaar.')
    import winreg
    launcher = bepaal_stabiele_launcher()
    if launcher is None:
        raise RuntimeError('Start met Windows is alleen beschikbaar na installatie met DrostSoundboard Setup.')
    if ingeschakeld:
        with winreg.CreateKeyEx(winreg.HKEY_CURRENT_USER, REGISTER_PAD, 0, winreg.KEY_SET_VALUE) as sleutel:
            winreg.SetValueEx(sleutel, REGISTER_WAARDE, 0, winreg.REG_SZ, _commando(launcher))
    else:
        verwijder_start_met_windows_bij_verwijderen(launcher=launcher)


def verwijder_start_met_windows_bij_verwijderen(*, launcher: Path | None = None) -> bool:
    """Ruim bij uninstall uitsluitend het exacte eigen aanmeldcommando op."""
    if sys.platform != 'win32':
        return False
    import winreg
    # Tijdens uninstall is de rootstub mogelijk al weg: bepaal dan het pad
    # vanuit de locatie van de oude executable, zonder rootbestanden te eisen.
    if launcher is None:
        exe = Path(sys.executable)
        if exe.parent.name.casefold() != 'current' or exe.name.casefold() != 'drostsoundboard.exe':
            return False
        launcher = exe.parent.parent / 'DrostSoundboard.exe'
    if _lees_huidige_registerwaarde() != _commando(launcher):
        return False
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, REGISTER_PAD, 0, winreg.KEY_SET_VALUE) as sleutel:
            winreg.DeleteValue(sleutel, REGISTER_WAARDE)
        return True
    except FileNotFoundError:
        return False
