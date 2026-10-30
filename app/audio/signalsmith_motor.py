"""Streaming C-ABI voor de ingebouwde Signalsmith-motor, zonder GPU of netwerk.

De DLL wordt bij het maken van de processor geladen, niet in de audiocallback.
Een ontbrekende motor levert een fout op. Er is geen verborgen oude pitchfallback.
"""
from __future__ import annotations

import ctypes
import hashlib
import json
import math
from pathlib import Path
import sys
import weakref

import numpy as np

MAX_FRAMES = 4096
_LIB = None


def _configureer_abi(lib):
    pointer = ctypes.POINTER(ctypes.c_float)
    lib.ds_abi.argtypes = []
    lib.ds_abi.restype = ctypes.c_int
    lib.ds_create.argtypes = [ctypes.c_int]
    lib.ds_create.restype = ctypes.c_void_p
    lib.ds_destroy.argtypes = [ctypes.c_void_p]
    lib.ds_destroy.restype = None
    for name in ('ds_reset', 'ds_latency'):
        fn = getattr(lib, name)
        fn.argtypes = [ctypes.c_void_p]
        fn.restype = ctypes.c_int
    lib.ds_process.argtypes = [ctypes.c_void_p, pointer, pointer, ctypes.c_int,
                              ctypes.c_int, ctypes.c_int] + [ctypes.c_float] * 5
    lib.ds_process.restype = ctypes.c_int
    if lib.ds_abi() != 1:
        raise RuntimeError('STEM-090: Deze versie van de stemmotor past niet bij de app.')
    return lib


def laad_library(pad: Path | None = None):
    """Laad uitsluitend het absolute app-pad. Een expliciet pad is voor de bouwtest."""
    global _LIB
    if pad is None and _LIB is not None:
        return _LIB
    standaard = pad is None
    if standaard:
        root = Path(__file__).resolve().parent / 'native'
        if sys.platform != 'win32':
            raise RuntimeError('STEM-090: Deze stembuild is voor Windows x64.')
        pad = root / 'win-x64/drost_stem.dll'
        try:
            info = json.loads((root / 'stembouw.json').read_text(encoding='utf-8'))
            if hashlib.sha256(pad.read_bytes()).hexdigest() != info['dll_sha256']:
                raise ValueError('bestandscontrole mislukt')
        except (OSError, ValueError, KeyError) as exc:
            raise RuntimeError('STEM-090: De stemmotor ontbreekt of is beschadigd. Installeer de stempatch opnieuw.') from exc
    pad = Path(pad).resolve()
    try:
        lib = _configureer_abi(ctypes.CDLL(str(pad)))
    except (OSError, AttributeError) as exc:
        raise RuntimeError('STEM-090: De stemmotor kan niet starten. Controleer de installatie.') from exc
    if standaard:
        _LIB = lib
    return lib


class SignalsmithMotor:
    """Een blijvende motor per audiostream. Dezelfde instantie is niet thread-safe."""
    def __init__(self, samplefrequentie: int = 48000, *, library=None):
        if type(samplefrequentie) is not int or not 16000 <= samplefrequentie <= 96000:
            raise ValueError('STEM-002: ongeldige samplefrequentie.')
        self.samplefrequentie = samplefrequentie
        self._lib = laad_library() if library is None else library
        self._handle = self._lib.ds_create(samplefrequentie)
        if not self._handle:
            raise RuntimeError('STEM-091: De stemmotor kon geen audiobuffers maken.')
        self._opruimen = weakref.finalize(self, self._lib.ds_destroy, self._handle)
        self.vertraging_samples = int(self._lib.ds_latency(self._handle))

    def sluiten(self) -> None:
        self._opruimen()
        self._handle = None

    def reset(self) -> None:
        if not self._handle:
            raise RuntimeError('STEM-092: De stemmotor is afgesloten.')
        if self._lib.ds_reset(self._handle) != 0:
            raise RuntimeError('STEM-093: De audiobuffers konden niet worden leeggemaakt.')

    def verwerk_blok(self, invoer: np.ndarray, *, toonhoogte: float = 0,
                     klankkleur: float = 0, effect: int = 0, sterkte: float = 1,
                     instelling1: float = 0.5, instelling2: float = 0.5) -> np.ndarray:
        if not self._handle:
            raise RuntimeError('STEM-092: De stemmotor is afgesloten.')
        if (not isinstance(invoer, np.ndarray) or invoer.dtype != np.float32 or
                invoer.ndim != 2 or invoer.shape[1] not in (1, 2)):
            raise ValueError('STEM-003: verwacht mono/stereo float32-microfoonframes.')
        waarden = (toonhoogte, klankkleur, sterkte, instelling1, instelling2)
        if (any(not math.isfinite(float(x)) for x in waarden) or
                abs(toonhoogte) > 12 or abs(klankkleur) > 6 or
                not all(0 <= x <= 1 for x in (sterkte, instelling1, instelling2)) or
                type(effect) is not int or effect not in range(5)):
            raise ValueError('STEM-094: ongeldige instellingen voor de stemmotor.')
        if not np.isfinite(invoer).all():
            raise ValueError('STEM-004: ongeldige microfoonsamples.')
        bron = np.ascontiguousarray(invoer)
        uitvoer = np.empty_like(bron)
        pointer = ctypes.POINTER(ctypes.c_float)
        for begin in range(0, len(bron), MAX_FRAMES):
            eind = min(begin + MAX_FRAMES, len(bron))
            x, y = bron[begin:eind], uitvoer[begin:eind]
            code = self._lib.ds_process(self._handle, x.ctypes.data_as(pointer),
                                       y.ctypes.data_as(pointer), len(x), bron.shape[1], effect,
                                       float(toonhoogte), float(klankkleur), float(sterkte),
                                       float(instelling1), float(instelling2))
            if code != 0:
                raise RuntimeError(f'STEM-095: De stemverwerking is gestopt (controle {code}).')
        if not np.isfinite(uitvoer).all():
            raise RuntimeError('STEM-004: De stemmotor gaf ongeldige samples terug.')
        return uitvoer
