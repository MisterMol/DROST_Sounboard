"""Laat de gebruiker eigen geluidseffecten horen zonder de microfoon terug te spelen.

De realtime audiomixer stuurt kleine blokken van ALLEEN het effect naar deze
monitor. De aparte uitvoercallback speelt ze via de gekozen headset. Een
begrensde deque voorkomt dat een vastlopende audiokaart onbeperkt RAM gebruikt.
"""
from __future__ import annotations

from collections import deque
import logging
import threading
from typing import Any
import numpy as np

from app.audio.windows_com_context import houd_com_beschikbaar_tijdens_audioverbinding


class MonitorFout(RuntimeError):
    """Herkenbare foutmelding voor een onbeschikbare lokale afspeeluitgang."""


class MonitorVoorEigenHeadset:
    """Een aparte audiostream die nooit het microfoonsignaal ontvangt."""

    def __init__(self, audiobibliotheek: Any, softwarelogboek: logging.Logger):
        self.audiobibliotheek = audiobibliotheek
        self.softwarelogboek = softwarelogboek
        self.ingeschakeld = True
        self.gekozen_apparaatnummer: int | None = None
        self.huidige_apparaatnaam = 'Nog geen uitvoer gekozen'
        self.laatste_fout: str | None = None
        self._stroom = None
        self._monitor_draad: threading.Thread | None = None
        self._stop_verzocht = threading.Event()
        self._klaar_met_opstarten = threading.Event()
        self._start_succesvol = False
        self._klaarstaande_blokken: deque[np.ndarray] = deque(maxlen=70)
        self._restblok: np.ndarray | None = None
        self._restpositie = 0
        # Alleen de PortAudio-callback bezit _restblok en _restpositie.
        # Andere draden vragen een flush aan via deze teller. Dat voorkomt
        # NoneType-races wanneer iemand meerdere keren snel op Stop klikt.
        self._leegmaakgeneratie = 0
        self._verwerkte_leegmaakgeneratie = 0
        self.aantal_overgelopen_blokken = 0
        self.aantal_ondergelopen_blokken = 0

    def _vind_geschikt_uitvoerapparaat(self) -> tuple[int, str]:
        """Gebruik Razer-WASAPI als die bestaat; anders het standaarduitvoerapparaat.

        Niet automatisch CABLE Input kiezen, want dat zou het monitorpad
        opnieuw in de virtuele microfoon kunnen terugkoppelen.
        """
        apparaten = self.audiobibliotheek.query_devices()
        apis = self.audiobibliotheek.query_hostapis()
        kandidaten = []
        for nummer, apparaat in enumerate(apparaten):
            naam = str(apparaat.get('name', ''))
            api_index = apparaat.get('hostapi')
            api_naam = str(apis[api_index].get('name', '')) if isinstance(api_index, int) and 0 <= api_index < len(apis) else ''
            if (apparaat.get('max_output_channels', 0) or 0) < 2 or api_naam.casefold() != 'windows wasapi':
                continue
            if 'cable' in naam.casefold() or 'vb-audio' in naam.casefold():
                continue
            kandidaten.append((nummer, naam))
        if self.gekozen_apparaatnummer is not None:
            gekozen = next((x for x in kandidaten if x[0] == self.gekozen_apparaatnummer), None)
            if gekozen is None:
                raise MonitorFout('MON-001: de geselecteerde headset is losgekoppeld. Kies een andere uitvoer.')
            return gekozen
        razer = next((x for x in kandidaten if 'razer' in x[1].casefold()), None)
        if razer:
            return razer
        if kandidaten:
            return kandidaten[0]
        raise MonitorFout('MON-002: er is geen geschikt WASAPI-afspeelapparaat beschikbaar.')

    def kies_uitvoerapparaat(self, nummer: int | None) -> None:
        if nummer is not None and type(nummer) is not int:
            raise MonitorFout('MON-003: uitvoerapparaatnummer moet een getal of null zijn.')
        if nummer == self.gekozen_apparaatnummer:
            return
        self.sluit_monitor()
        self.gekozen_apparaatnummer = nummer

    def zorg_dat_monitor_kan_afspelen(self) -> bool:
        """Start de headsetmonitor in een eigen Windows COM-draad.

        Het openen van een WASAPI-apparaat vanuit een HTTP-werkdraad kan fout
        gaan wanneer die draad al een andere COM-stand gebruikt. Daarom blijft
        één aparte monitorwerkdraad eigenaar van openen, afspelen én afsluiten.
        """
        if not self.ingeschakeld:
            return False
        if self._stroom is not None and self._stroom.active:
            return True
        if self._monitor_draad is not None and self._monitor_draad.is_alive():
            self._klaar_met_opstarten.wait(5)
            return self._start_succesvol
        nummer, naam = self._vind_geschikt_uitvoerapparaat()
        self._stop_verzocht = threading.Event()
        self._klaar_met_opstarten = threading.Event()
        self._start_succesvol = False
        self._monitor_draad = threading.Thread(
            target=self._voer_headsetmonitor_uit,
            args=(nummer, naam), name='Headsetmonitor-COM', daemon=True,
        )
        self._monitor_draad.start()
        self._klaar_met_opstarten.wait(5)
        return self._start_succesvol

    def _voer_headsetmonitor_uit(self, nummer: int, naam: str) -> None:
        stroom = None
        try:
            with houd_com_beschikbaar_tijdens_audioverbinding():
                stroom = self.audiobibliotheek.OutputStream(
                    device=nummer, samplerate=48000, channels=2, dtype='float32',
                    blocksize=0, latency='high', callback=self._verwerk_eigen_headset_audio,
                )
                self._stroom = stroom
                stroom.start()
                self.huidige_apparaatnaam = naam
                self.laatste_fout = None
                self._start_succesvol = True
                self._klaar_met_opstarten.set()
                self._stop_verzocht.wait()
        except Exception as fout:
            self.laatste_fout = str(fout)
            self.softwarelogboek.exception('Headsetmonitor kon niet starten of is gestopt', extra={
                'gebeurtenis': 'monitor_start_mislukt', 'gegevens': {
                    'foutcode': 'MON-004', 'apparaatnummer': nummer,
                    'apparaatnaam': naam, 'fouttype': type(fout).__name__,
                },
            })
        finally:
            self._start_succesvol = False
            self._klaar_met_opstarten.set()
            if stroom is not None:
                for actie in ('stop', 'close'):
                    try:
                        if actie == 'stop' and not stroom.active:
                            continue
                        getattr(stroom, actie)()
                    except Exception:
                        self.softwarelogboek.exception('Headsetmonitor kon niet netjes afsluiten', extra={
                            'gebeurtenis': 'monitor_afsluiten_mislukt', 'gegevens': {'handeling': actie}
                        })
            self._stroom = None
            self.maak_monitorbuffer_leeg()

    def _verwerk_eigen_headset_audio(self, uitvoer, aantal_frames, tijdinformatie, status):
        """Realtime pad: geen logs, geen bestandstoegang en nooit de fysieke microfoon."""
        uitvoer.fill(0)
        if self._verwerkte_leegmaakgeneratie != self._leegmaakgeneratie:
            self._restblok = None
            self._restpositie = 0
            self._verwerkte_leegmaakgeneratie = self._leegmaakgeneratie
        if status:
            self.aantal_ondergelopen_blokken += 1
        gevuld = 0
        while gevuld < aantal_frames:
            if self._restblok is None:
                try:
                    self._restblok = self._klaarstaande_blokken.popleft()
                    self._restpositie = 0
                except IndexError:
                    break
            nog_in_rest = len(self._restblok) - self._restpositie
            overnemen = min(aantal_frames - gevuld, nog_in_rest)
            uitvoer[gevuld:gevuld + overnemen] = self._restblok[
                self._restpositie:self._restpositie + overnemen
            ]
            gevuld += overnemen
            self._restpositie += overnemen
            if self._restpositie == len(self._restblok):
                self._restblok = None
                self._restpositie = 0

    def ontvang_alleen_effectsamples(self, samples: np.ndarray) -> None:
        """Kopieer alleen het effect. Spreekmicrofoon blijft buiten het lokale monitorpad."""
        if self._stroom is None or not self.ingeschakeld or not self._stroom.active:
            return
        if len(self._klaarstaande_blokken) == self._klaarstaande_blokken.maxlen:
            self.aantal_overgelopen_blokken += 1
        self._klaarstaande_blokken.append(samples.copy())

    def maak_monitorbuffer_leeg(self) -> None:
        # Niet rechtstreeks aan _restblok of _restpositie komen: de audio-
        # callback kan midden in het kopiëren van een blok zitten.
        # De volgende callback voert de flush zelf uit.
        self._leegmaakgeneratie += 1
        self._klaarstaande_blokken.clear()

    def sluit_monitor(self) -> None:
        """Vraag de eigen werkdraad om de stream gecontroleerd los te laten."""
        self._stop_verzocht.set()
        draad = self._monitor_draad
        if draad is not None and draad.is_alive() and draad is not threading.current_thread():
            draad.join(timeout=5)
            if draad.is_alive():
                self.softwarelogboek.error('Headsetmonitor bleef na sluiten actief', extra={
                    'gebeurtenis': 'monitor_afsluiten_timeout', 'gegevens': {'foutcode': 'MON-005'}
                })
        self.maak_monitorbuffer_leeg()
