"""Release-updates voor de geïnstalleerde Windows-app (niet voor broncodepatches).

Controle en download draaien op een aparte daemonthread. Toepassen mag pas
na nette audiostop, of vóór audio-start wanneer wij de enige instantie zijn.
"""
from __future__ import annotations

import json
from pathlib import Path
import re
import sys
import threading
from typing import Any

BRONBESTAND = Path(__file__).with_name('releasebron.json')
GITHUB_URL = re.compile(r'^https://github\.com/[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+/?$')
CONTROLE_INTERVAL_SECONDEN = 12 * 60 * 60
EERSTE_CONTROLE_NA_SECONDEN = 45


class GeenReleaseInstallatie(RuntimeError):
    """Geen officiële Velopack-installatie of geen bekende updatebron."""


def lees_releasebron(bestand: Path = BRONBESTAND) -> tuple[str, str]:
    """Lees de door de releasebouwer verpakte, vaste publieke GitHub-bron."""
    try:
        config = json.loads(bestand.read_text(encoding='utf-8-sig'))
    except (OSError, ValueError, TypeError):
        return '', 'beta'
    url = config.get('repository_url', '')
    kanaal = config.get('channel', '')
    if not isinstance(url, str) or not GITHUB_URL.fullmatch(url):
        return '', 'beta'
    if kanaal not in ('beta', 'stable'):
        return '', 'beta'
    return url.rstrip('/'), kanaal


def is_release_installatie() -> bool:
    """Ontwikkelomgevingen krijgen nooit stilletjes een binaire update."""
    if sys.platform != 'win32' or not getattr(sys, 'frozen', False):
        return False
    exe = Path(sys.executable)
    return (exe.name.casefold() == 'drostsoundboard.exe'
            and exe.parent.name.casefold() == 'current'
            and (exe.parent.parent / 'Update.exe').is_file())


def _maak_velopack_manager():
    url, kanaal = lees_releasebron()
    if not is_release_installatie() or not url:
        raise GeenReleaseInstallatie('Updates zijn pas beschikbaar na installatie van de officiële GitHub-release.')
    # Native SDK alleen laden wanneer nodig, nooit in de audiocallback.
    from velopack import UpdateManager
    from velopack.Sources import GithubSource
    bron = GithubSource(url, access_token=None, prerelease=(kanaal == 'beta'))
    return UpdateManager(bron)


def initialiseer_velopack_bij_start() -> None:
    """Velopack-hooks vroeg uitvoeren, maar automatisch toepassen is UIT.

    Een tweede dubbelklik mag immers niet een draaiende audiomixer afsluiten.
    De release-update wordt expliciet toegepast wanneer de mutex vrij is.
    """
    if not getattr(sys, 'frozen', False) or sys.platform != 'win32':
        return
    import velopack
    from app.desktop.opstartinstellingen import verwijder_start_met_windows_bij_verwijderen
    app = velopack.App().set_auto_apply_on_startup(False)
    app.on_before_uninstall_fast_callback(
        lambda *_: verwijder_start_met_windows_bij_verwijderen()
    )
    app.run()


class ReleaseUpdateService:
    """Eén kleine, threadveilige toestandmachine voor downloads en installatie."""

    def __init__(self, softwarelogboek=None, *, manager_factory=_maak_velopack_manager):
        self.softwarelogboek = softwarelogboek
        self._manager_factory = manager_factory
        self._stop = threading.Event()
        self._busy = threading.Lock()
        self._status_lock = threading.Lock()
        self._status = 'Nog niet gecontroleerd'
        self._thread: threading.Thread | None = None
        self._achtergrond: threading.Thread | None = None

    def _set_status(self, tekst: str) -> None:
        with self._status_lock:
            self._status = tekst

    def geef_status(self) -> str:
        with self._status_lock:
            return self._status

    def beschikbaar(self) -> bool:
        return bool(is_release_installatie() and lees_releasebron()[0])

    def _log_fout(self, bericht: str, fout: Exception) -> None:
        if self.softwarelogboek:
            self.softwarelogboek.warning(bericht, extra={
                'gebeurtenis': 'release_update_mislukt',
                'gegevens': {'foutcode': 'UPDATE-600', 'fouttype': type(fout).__name__,
                             'fout': str(fout)[:250]},
            })

    def controleer_en_download(self) -> None:
        """Alleen netwerkcontrole en download, dus nooit een lopende call stoppen."""
        if not self.beschikbaar() or self._stop.is_set():
            self._set_status('Niet beschikbaar in ontwikkelmodus')
            return
        if not self._busy.acquire(blocking=False):
            return
        try:
            self._set_status('Update controleren...')
            beheer = self._manager_factory()
            gereed = beheer.get_update_pending_restart()
            if gereed is not None:
                self._set_status('Update gereed voor veilig afsluiten')
                return
            info = beheer.check_for_updates()
            if info is None:
                self._set_status('Je gebruikt de nieuwste versie')
                return
            if self._stop.is_set():
                return
            self._set_status('Update downloaden...')
            beheer.download_updates(info)
            self._set_status('Update gereed voor veilig afsluiten')
        except Exception as fout:
            self._set_status('Updatecontrole mislukt; huidige versie blijft werken')
            self._log_fout('Release-update kon niet gecontroleerd of gedownload worden', fout)
        finally:
            self._busy.release()

    def _controlethread(self) -> None:
        if self._stop.wait(EERSTE_CONTROLE_NA_SECONDEN):
            return
        while not self._stop.is_set():
            self.controleer_en_download()
            if self._stop.wait(CONTROLE_INTERVAL_SECONDEN):
                return

    def start_automatisch(self) -> None:
        if self.beschikbaar() and self._achtergrond is None:
            self._achtergrond = threading.Thread(target=self._controlethread,
                                                 daemon=True, name='Release-updatecontrole')
            self._achtergrond.start()

    def controleer_handmatig(self) -> bool:
        if not self.beschikbaar() or self._stop.is_set():
            return False
        if self._thread and self._thread.is_alive():
            return True
        self._thread = threading.Thread(target=self.controleer_en_download,
                                        daemon=True, name='Release-update-handmatig')
        self._thread.start()
        return True

    def stop(self) -> None:
        self._stop.set()

    def _pas_gereed_toe(self, *, herstart: bool, achtergrond: bool = False) -> bool:
        if not self.beschikbaar():
            return False
        # Nooit toepassen tijdens downloaden of voordat de audiomixer netjes
        # uitgeschakeld is. Wanneer bezig, blijft het pakket voor volgende start.
        if not self._busy.acquire(blocking=False):
            return False
        try:
            beheer = self._manager_factory()
            pakket = beheer.get_update_pending_restart()
            if pakket is None:
                return False
            self._set_status('Update toepassen na afsluiten')
            # De aparte Velopack-updater wacht op ons proces. Max. 60s is
            # Velopack-gedrag: wij starten hem uitsluitend NA audiostop.
            argumenten = ['--achtergrond'] if achtergrond else None
            beheer.wait_exit_then_apply_updates(
                pakket, silent=True, restart=herstart, restart_args=argumenten)
            return True
        except Exception as fout:
            self._set_status('Installeren mislukt; huidige versie behouden')
            self._log_fout('Gedownloade update kon niet worden ingepland', fout)
            return False
        finally:
            self._busy.release()

    def pas_toe_voor_audio_start(self, *, achtergrond: bool = False) -> bool:
        """AANROEPEN ALLEEN NA verkrijgen van de single-instance mutex."""
        return self._pas_gereed_toe(herstart=True, achtergrond=achtergrond)

    def pas_toe_na_audio_stop(self) -> bool:
        """AANROEPEN ALLEEN nadat streams en sneltoetsen zijn afgesloten."""
        return self._pas_gereed_toe(herstart=False)
