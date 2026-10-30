"""Lokale microfoonpreview zonder VB-CABLE, opname of netwerkuitvoer.

Dezelfde Stemvervormer wordt gebruikt als in de uiteindelijke audiomixer.
Bij de preview wordt een eigen fysieke outputstream gebruikt, uitsluitend
wanneer er geen live VB-CABLE-verbinding is. Zo is er geen dubbele opname.
"""
from __future__ import annotations

import logging
import threading
import time
from typing import Any

import numpy as np

from app.audio.apparatenbeheer import GevondenAudioapparaat
from app.audio.live_audiomixer import kies_het_juiste_aantal_microfoonkanalen, controleer_of_microfoon_een_echt_opnameapparaat_is
from app.audio.windows_com_context import houd_com_beschikbaar_tijdens_audioverbinding
from app.audio.stemvervorming import Stemvervormer, controleer_stemprofiel, STANDAARD_INTENSITEITEN, controleer_stemintensiteit
from app.audio.stemparameters import standaard_parameters, controleer_parameters


class StemvoorbeeldFout(RuntimeError):
    pass


class LokaalStemvoorbeeld:
    """Een previewstream in een COM-beheerthread; geen bestandsopslag."""

    def __init__(self, audiobibliotheek: Any, softwarelogboek: logging.Logger):
        self.audiobibliotheek = audiobibliotheek
        self.softwarelogboek = softwarelogboek
        self._draad: threading.Thread | None = None
        self._stop = threading.Event()
        self._gereed = threading.Event()
        self._draait = False
        self._startfout: BaseException | None = None
        self._processor = Stemvervormer()
        self.natuurlijke_stem = None
        self._natuurlijk_was_actief = False
        self._gewenst_profiel = 'normaal'
        self._gewenste_intensiteiten = dict(STANDAARD_INTENSITEITEN)
        self._gewenste_parameters = standaard_parameters()
        self._rms_in = 0.0
        self._piek_in = 0.0
        self._rms_uit = 0.0
        self._piek_uit = 0.0
        self._driverproblemen = 0
        self._laatste_meettijd: float | None = None

    @property
    def actief(self) -> bool:
        return self._draait and self._draad is not None and self._draad.is_alive()

    def stel_stemprofiel_in(self, profiel: str) -> None:
        self._gewenst_profiel = controleer_stemprofiel(profiel)

    def stel_stemintensiteiten_in(self, waarden: dict[str, int]) -> None:
        if set(waarden) != set(STANDAARD_INTENSITEITEN):
            raise ValueError('STEM-031: onvolledige stemprofielinstellingen.')
        self._gewenste_intensiteiten = {
            naam: controleer_stemintensiteit(waarde) for naam, waarde in waarden.items()
        }

    def stel_stemparameters_in(self, waarden: dict[str,dict]) -> None:
        if set(waarden) != set(standaard_parameters()):
            raise ValueError('STEM-053: onvolledige effectinstellingen.')
        self._gewenste_parameters = {naam: controleer_parameters(naam, params) for naam, params in waarden.items()}

    def start(self, microfoon: GevondenAudioapparaat,
              uitvoer: GevondenAudioapparaat, profiel: str) -> None:
        controleer_of_microfoon_een_echt_opnameapparaat_is(microfoon)
        if (not isinstance(uitvoer, GevondenAudioapparaat)
                or uitvoer.api_naam.casefold() != 'windows wasapi'
                or uitvoer.aantal_uitvoerkanalen < 2
                or 'cable' in uitvoer.naam.casefold()
                or 'vb-audio' in uitvoer.naam.casefold()):
            raise StemvoorbeeldFout('STEM-010: kies een fysiek luisterapparaat, niet de virtuele kabel.')
        if self._draad is not None and self._draad.is_alive():
            raise StemvoorbeeldFout('STEM-011: een stempreview draait al.')
        self._gewenst_profiel = controleer_stemprofiel(profiel)
        self._processor = Stemvervormer(profiel, intensiteit=self._gewenste_intensiteiten[profiel],
                                         parameters=self._gewenste_parameters)
        self._rms_in = self._piek_in = self._rms_uit = self._piek_uit = 0.0
        self._driverproblemen = 0
        self._laatste_meettijd = None
        self._stop = threading.Event()
        self._gereed = threading.Event()
        self._startfout = None
        self._draait = False
        self._draad = threading.Thread(target=self._voer_uit,
                                      args=(microfoon, uitvoer),
                                      daemon=True, name='Lokale-stempreview-COM')
        self._draad.start()
        if not self._gereed.wait(5) or not self._draait:
            self.stop()
            fout = self._startfout
            if fout is not None:
                raise StemvoorbeeldFout('STEM-012: preview kon niet starten. Controleer microfoon en luisterapparaat.') from fout
            raise StemvoorbeeldFout('STEM-013: geluidsapparaat reageerde niet op tijd.')

    def _audio_callback(self, invoer, uitvoer, aantal_frames, tijdinfo, status):
        uitvoer.fill(0)
        if status:
            self._driverproblemen += 1
        dienst = self.natuurlijke_stem
        natuurlijk_actief = dienst is not None and dienst.aan
        try:
            if natuurlijk_actief != self._natuurlijk_was_actief:
                self._processor.herstel_audiobuffers()
                self._natuurlijk_was_actief = natuurlijk_actief
            if natuurlijk_actief:
                verwerkt = dienst.verwerk(invoer, 'preview')
            else:
                if self._processor.profiel != self._gewenst_profiel:
                    self._processor.kies_profiel(self._gewenst_profiel)
                if self._processor._bron_parameters_ref is not self._gewenste_parameters:
                    self._processor.neem_gecontroleerde_parameters_over(self._gewenste_parameters)
                intensiteit = self._gewenste_intensiteiten[self._gewenst_profiel]
                if self._processor.intensiteit != intensiteit:
                    self._processor.stel_intensiteit_in(intensiteit)
                verwerkt = self._processor.verwerk(invoer)
        except Exception as fout:
            # Geen onverwachte originele stem bij een effectfout. Niet loggen in de callback.
            if self._startfout is None:
                self._startfout = fout
            verwerkt = (invoer if not natuurlijk_actief and self._gewenst_profiel == 'normaal'
                        else np.zeros_like(invoer))
        # Alleen numerieke niveaus bewaren; geen audio naar web of schijf.
        # 480 frames per blok: gemiddeld 100 updates/s, geen extra stream.
        if len(invoer):
            self._rms_in = float(np.sqrt(np.mean(np.square(invoer, dtype=np.float64))))
            self._piek_in = float(np.max(np.abs(invoer)))
            self._rms_uit = float(np.sqrt(np.mean(np.square(verwerkt, dtype=np.float64))))
            self._piek_uit = float(np.max(np.abs(verwerkt)))
            self._laatste_meettijd = time.monotonic()
        # Preview moet comfortabel en zonder feedback zijn.
        if verwerkt.shape[1] == 1:
            uitvoer[:, 0] = verwerkt[:, 0] * .65
            uitvoer[:, 1] = verwerkt[:, 0] * .65
        else:
            uitvoer[:, :] = verwerkt[:, :2] * .65
        np.nan_to_num(uitvoer, copy=False, nan=0.0, posinf=0.0, neginf=0.0)
        np.clip(uitvoer, -.88, .88, out=uitvoer)

    def _voer_uit(self, microfoon, uitvoer):
        try:
            with houd_com_beschikbaar_tijdens_audioverbinding():
                kanalen = kies_het_juiste_aantal_microfoonkanalen(
                    self.audiobibliotheek, microfoon)
                self.audiobibliotheek.check_output_settings(
                    device=uitvoer.huidig_apparaatnummer, channels=2,
                    dtype='float32', samplerate=48000)
                with self.audiobibliotheek.Stream(
                    device=(microfoon.huidig_apparaatnummer, uitvoer.huidig_apparaatnummer),
                    channels=(kanalen, 2), dtype='float32', samplerate=48000,
                    blocksize=480, latency='high', callback=self._audio_callback,
                ) as stroom:
                    self._draait = True
                    self._gereed.set()
                    # De preview eindigt ook als het browsertabblad verdwijnt.
                    self._stop.wait(timeout=90)
        except Exception as fout:
            self._startfout = fout
            self.softwarelogboek.exception(
                'Lokale stempreview kon niet starten of stopte onverwacht',
                extra={'gebeurtenis': 'stemvoorbeeld_fout',
                       'gegevens': {'foutcode': 'STEM-012', 'fouttype': type(fout).__name__}},
            )
        finally:
            self._draait = False
            self._gereed.set()

    def stop(self) -> None:
        self._stop.set()
        draad = self._draad
        if draad is not None and draad.is_alive() and draad is not threading.current_thread():
            draad.join(timeout=5)
            if draad.is_alive():
                raise StemvoorbeeldFout('STEM-014: preview-audiostream is nog niet vrijgegeven.')
        self._draait = False

    def status(self) -> dict[str, object]:
        actief = self.actief
        # Een geopende stream bewijst niet dat er recent audio binnenkwam.
        # Na een USB-hapering mag de UI geen oud niveau blijven tonen.
        gemeten = (actief and self._laatste_meettijd is not None
                   and time.monotonic() - self._laatste_meettijd <= 0.35)
        return {'actief': actief, 'gemeten': gemeten,
                'profiel': self._gewenst_profiel,
                'driverproblemen': self._driverproblemen,
                'microfoon_rms': self._rms_in if gemeten else 0.0,
                'microfoon_piek': self._piek_in if gemeten else 0.0,
                'stem_rms': self._rms_uit if gemeten else 0.0,
                'stem_piek': self._piek_uit if gemeten else 0.0}
