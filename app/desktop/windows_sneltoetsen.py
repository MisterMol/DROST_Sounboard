"""Herken uitsluitend aangewezen Windows-hotkeys via RegisterHotKey.

De Windows-berichtenlus zit op een aparte werkdraad. De audiomixer ontvangt
opdrachten via een begrensde wachtrij; geen toetsaanslag wordt opgeslagen.
"""
from __future__ import annotations

import ctypes
from ctypes import wintypes
import logging
from queue import Empty, Full, Queue
import sys
import threading
from typing import Callable

from app.desktop.sneltoetsinstellingen import controleer_sneltoetsinstellingen

WM_HOTKEY = 0x0312
WM_QUIT = 0x0012
WM_HERLAAD_SNELTOETSEN = 0x8024
MOD_ALT = 0x0001
MOD_CONTROL = 0x0002
MOD_SHIFT = 0x0004
MOD_NOREPEAT = 0x4000
EERSTE_SNELTOETSNUMMER = 0x4500


class _WindowsPunt(ctypes.Structure):
    _fields_ = [('x', wintypes.LONG), ('y', wintypes.LONG)]


class _WindowsBericht(ctypes.Structure):
    _fields_ = [
        ('hwnd', wintypes.HWND), ('message', wintypes.UINT), ('wParam', wintypes.WPARAM),
        ('lParam', wintypes.LPARAM), ('time', wintypes.DWORD), ('pt', _WindowsPunt),
        ('lPrivate', wintypes.DWORD),
    ]


def vertaal_sneltoets_naar_windows(sneltoets: str) -> tuple[int, int]:
    """Vertaal alleen getoetste, toegestane combinaties naar Win32-waarden."""
    controleer_sneltoetsinstellingen({'ingeschakeld': True, 'combinaties': {'stop': sneltoets}})
    delen = sneltoets.upper().replace(' ', '').split('+')
    mods = MOD_NOREPEAT
    if 'CTRL' in delen: mods |= MOD_CONTROL
    if 'ALT' in delen: mods |= MOD_ALT
    if 'SHIFT' in delen: mods |= MOD_SHIFT
    toets = delen[-1]
    virtuele_toets = ord(toets) if len(toets) == 1 else 111 + int(toets[1:])
    return mods, virtuele_toets


class GlobaleSneltoetsenVanWindows:
    """Beheer registraties op een eigen Windows-thread, niet in de audio-callback."""

    def __init__(self, voer_actie_uit: Callable[[str], None], logboek: logging.Logger,
                 instellingen: dict):
        self.voer_actie_uit = voer_actie_uit
        self.logboek = logboek
        self._instellingen = controleer_sneltoetsinstellingen(instellingen)
        self._wachtrij: Queue[str | None] = Queue(maxsize=32)
        self._wacht_op_start = threading.Event()
        self._wacht_op_herladen = threading.Event()
        self._thread_id: int | None = None
        self._luisterdraad: threading.Thread | None = None
        self._actiedraad: threading.Thread | None = None
        self._registraties: dict[int, str] = {}
        self._mislukte_combinaties: dict[str, str] = {}
        self._bescherm = threading.RLock()
        self._wordt_afgesloten = False

    def start(self) -> None:
        if sys.platform != 'win32':
            # Tijdens ontwikkeling en in Linux-CI: test configuratie zonder
            # te doen alsof Windows-globale toetsen hier worden geregistreerd.
            return
        if self._luisterdraad is not None:
            return
        self._actiedraad = threading.Thread(target=self._verwerk_gevraagde_acties,
                                           name='Sneltoets-acties', daemon=True)
        self._actiedraad.start()
        self._luisterdraad = threading.Thread(target=self._windows_berichtenlus,
                                             name='Windows-sneltoetsen', daemon=True)
        self._luisterdraad.start()
        if not self._wacht_op_start.wait(5):
            raise RuntimeError('HOTKEY-010: Windows-berichtenlus start niet binnen vijf seconden.')
        if self._thread_id is None:
            raise RuntimeError('HOTKEY-011: Windows-sneltoetsen konden niet gestart worden; zie software.jsonl.')

    def geef_huidige_instellingen(self) -> dict:
        with self._bescherm:
            return {'ingeschakeld': self._instellingen['ingeschakeld'],
                    'combinaties': dict(self._instellingen['combinaties']),
                    'mislukte_registraties': dict(self._mislukte_combinaties)}

    def pas_instellingen_aan(self, instellingen: object) -> dict:
        nieuwe = controleer_sneltoetsinstellingen(instellingen)
        with self._bescherm:
            self._instellingen = nieuwe
            self._wacht_op_herladen.clear()
        if self._thread_id is not None:
            self._plaats_windows_bericht(WM_HERLAAD_SNELTOETSEN)
            if not self._wacht_op_herladen.wait(4):
                raise RuntimeError('HOTKEY-012: Windows bevestigde herregistratie niet op tijd.')
        return self.geef_huidige_instellingen()

    def _plaats_windows_bericht(self, bericht: int) -> None:
        if self._thread_id is None:
            return
        user32 = ctypes.WinDLL('user32', use_last_error=True)
        user32.PostThreadMessageW.argtypes = [wintypes.DWORD, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM]
        user32.PostThreadMessageW.restype = wintypes.BOOL
        if not user32.PostThreadMessageW(self._thread_id, bericht, 0, 0):
            raise OSError(ctypes.get_last_error(), 'HOTKEY-013: Windows-bericht kon niet worden verstuurd.')

    def _registreer_nieuwe_combinaties(self, user32) -> None:
        # Registreren en vrijgeven gebeurt altijd op dezelfde Windows-thread.
        for nummer in self._registraties:
            user32.UnregisterHotKey(None, nummer)
        self._registraties.clear()
        foutmeldingen = {}
        with self._bescherm:
            configuratie = {'ingeschakeld': self._instellingen['ingeschakeld'],
                            'combinaties': dict(self._instellingen['combinaties'])}
        if configuratie['ingeschakeld']:
            for index, (actie, combinatie) in enumerate(configuratie['combinaties'].items()):
                nummer = EERSTE_SNELTOETSNUMMER + index
                modificatoren, toets = vertaal_sneltoets_naar_windows(combinatie)
                if not user32.RegisterHotKey(None, nummer, modificatoren, toets):
                    foutcode = ctypes.get_last_error()
                    foutmeldingen[actie] = f'{combinatie}: Windows-weigering {foutcode} (mogelijk al bezet)'
                    self.logboek.warning('Sneltoets kon niet worden geregistreerd', extra={
                        'gebeurtenis': 'sneltoets_conflict',
                        'gegevens': {'actie': actie, 'combinatie': combinatie, 'win32_fout': foutcode},
                    })
                    continue
                self._registraties[nummer] = actie
        with self._bescherm:
            self._mislukte_combinaties = foutmeldingen
        self._wacht_op_herladen.set()

    def _windows_berichtenlus(self) -> None:
        user32 = ctypes.WinDLL('user32', use_last_error=True)
        kernel32 = ctypes.WinDLL('kernel32', use_last_error=True)
        user32.PeekMessageW.argtypes = [ctypes.POINTER(_WindowsBericht), wintypes.HWND,
                                        wintypes.UINT, wintypes.UINT, wintypes.UINT]
        user32.GetMessageW.argtypes = [ctypes.POINTER(_WindowsBericht), wintypes.HWND,
                                       wintypes.UINT, wintypes.UINT]
        user32.GetMessageW.restype = ctypes.c_int
        user32.RegisterHotKey.argtypes = [wintypes.HWND, ctypes.c_int, wintypes.UINT, wintypes.UINT]
        user32.RegisterHotKey.restype = wintypes.BOOL
        user32.UnregisterHotKey.argtypes = [wintypes.HWND, ctypes.c_int]
        user32.UnregisterHotKey.restype = wintypes.BOOL
        kernel32.GetCurrentThreadId.restype = wintypes.DWORD
        bericht = _WindowsBericht()
        try:
            # Een Windows-berichtenwachtrij ontstaat pas na de eerste PeekMessage.
            user32.PeekMessageW(ctypes.byref(bericht), None, 0, 0, 0)
            self._thread_id = int(kernel32.GetCurrentThreadId())
            self._registreer_nieuwe_combinaties(user32)
            self._wacht_op_start.set()
            while True:
                resultaat = user32.GetMessageW(ctypes.byref(bericht), None, 0, 0)
                if resultaat == 0:
                    break
                if resultaat == -1:
                    raise OSError(ctypes.get_last_error(), 'HOTKEY-014: Windows-berichtenlus is afgebroken.')
                if bericht.message == WM_HERLAAD_SNELTOETSEN:
                    self._registreer_nieuwe_combinaties(user32)
                elif bericht.message == WM_HOTKEY:
                    actie = self._registraties.get(int(bericht.wParam))
                    if actie:
                        try:
                            self._wachtrij.put_nowait(actie)
                        except Full:
                            self.logboek.warning('Te veel sneltoetsacties tegelijk, actie overgeslagen', extra={
                                'gebeurtenis': 'sneltoets_wachtrij_vol', 'gegevens': {'actie': actie}})
        except Exception:
            self.logboek.exception('Sneltoetsberichtenlus is mislukt', extra={
                'gebeurtenis': 'windows_hotkey_loop_mislukt', 'gegevens': {'foutcode': 'HOTKEY-015'}})
        finally:
            for nummer in self._registraties:
                user32.UnregisterHotKey(None, nummer)
            self._registraties.clear()
            self._thread_id = None
            self._wacht_op_start.set()
            self._wacht_op_herladen.set()

    def _verwerk_gevraagde_acties(self) -> None:
        while not self._wordt_afgesloten:
            try:
                actie = self._wachtrij.get(timeout=0.25)
            except Empty:
                continue
            if actie is None:
                break
            try:
                self.voer_actie_uit(actie)
            except Exception:
                self.logboek.exception('Sneltoetsactie kon niet worden uitgevoerd', extra={
                    'gebeurtenis': 'sneltoets_actie_mislukt', 'gegevens': {'foutcode': 'HOTKEY-016', 'actie': actie}})
            finally:
                self._wachtrij.task_done()

    def stop(self) -> None:
        self._wordt_afgesloten = True
        if self._thread_id is not None:
            try:
                self._plaats_windows_bericht(WM_QUIT)
            except OSError:
                self.logboek.exception('Windows-sneltoetslus kon niet netjes worden gestopt')
        if self._luisterdraad is not None:
            self._luisterdraad.join(timeout=3)
        try:
            self._wachtrij.put_nowait(None)
        except Full:
            pass
        if self._actiedraad is not None:
            self._actiedraad.join(timeout=3)
