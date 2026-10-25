"""Houd COM beschikbaar in de Windows-draad die de WASAPI-stream opent.

Op Windows worden audioapparaten via COM-interfaces aangesproken. Een eigen
Python-achtergronddraad erft de COM-initialisatie van de UI-draad niet.
Daarom initialiseren én beëindigen we COM in precies die audiowerkdraad.
"""

from __future__ import annotations

from contextlib import contextmanager
import ctypes
import platform
from typing import Iterator


# STA wordt hier bewust gebruikt. Windows documenteert dat de eerste toegang
# tot IAudioClient op oudere ondersteunde Windows-versies vanuit een STA-draad
# hoort te gebeuren. Het is geen wijziging van Windows-instellingen.
COM_APARTMENT_VOOR_AUDIO = 0x2
COM_IS_AL_GEINITIALISEERD_IN_EEN_ANDERE_STAND = 0x80010106


class WindowsComInitialisatieFout(RuntimeError):
    """COM kon niet op een betrouwbare manier worden voorbereid."""


def haal_com_bibliotheek_van_windows_op():
    """Laad ole32 pas op Windows zodat tests ook op Linux kunnen draaien."""
    return ctypes.WinDLL("ole32", use_last_error=True)


@contextmanager
def houd_com_beschikbaar_tijdens_audioverbinding() -> Iterator[str]:
    """Open COM op de aanroepende draad en sluit alleen eigen initialisatie af.

    Een al geïnitialiseerde COM-draad mag niet zomaar worden afgesloten. Bij een
    afwijkende COM-stand geven we dat terug aan de aanroeper voor diagnose.
    """
    if platform.system() != "Windows":
        yield "niet_van_toepassing"
        return

    windows_com = haal_com_bibliotheek_van_windows_op()
    initialiseren = windows_com.CoInitializeEx
    initialiseren.argtypes = [ctypes.c_void_p, ctypes.c_uint32]
    initialiseren.restype = ctypes.c_long

    resultaat = int(initialiseren(None, COM_APARTMENT_VOOR_AUDIO))
    resultaat_als_unsigned = resultaat & 0xFFFFFFFF
    eigen_initialisatie = resultaat_als_unsigned in (0, 1)

    if eigen_initialisatie:
        stand = "sta_ingeschakeld"
    elif resultaat_als_unsigned == COM_IS_AL_GEINITIALISEERD_IN_EEN_ANDERE_STAND:
        # COM is al beschikbaar. Wij zijn niet de eigenaar van de initialisatie
        # en mogen daarom later geen CoUninitialize aanroepen.
        stand = "al_geinitialiseerd_met_andere_stand"
    else:
        raise WindowsComInitialisatieFout(
            "LIVE-020: Windows COM kon niet worden gestart in de audio-werkdraad. "
            f"HRESULT: 0x{resultaat_als_unsigned:08X}."
        )

    try:
        yield stand
    finally:
        if eigen_initialisatie:
            windows_com.CoUninitialize()
