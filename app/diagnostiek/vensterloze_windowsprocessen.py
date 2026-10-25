"""Laat externe hulpprogramma's draaien zonder flitsende consolevensters.

Pythonw draait zelf zonder terminal, maar FFmpeg is een consoleprogramma.
Zonder expliciete Windows-instelling opent FFmpeg alsnog kort een zwart
venster bij het inlezen, knippen of exporteren van een MP4.

De instelling onderdrukt alleen het VENSTER, niet het programma of zijn
foutmeldingen. De aanroeper blijft stderr en de oorspronkelijke traceback
registreren zoals voorheen. Op andere besturingssystemen veranderen we niets.
"""
from __future__ import annotations

import subprocess
import sys


def geef_opstartopties_zonder_console() -> dict[str, object]:
    """Geef de Windows-vlag die een nieuw consolevenster voorkomt.

    Waarom beide Windows-opties? Een consoleproces heeft een andere
    vensterlevenscyclus dan een grafisch programma. De combinatie voorkomt
    beide soorten flitsen, zonder stderr, timeouts of de audiomixer te wijzigen.
    """
    if sys.platform != 'win32':
        return {}

    # Twee onafhankelijke Windows-maatregelen. CREATE_NO_WINDOW voorkomt
    # dat een consoleprogramma een eigen console opent. STARTUPINFO met
    # SW_HIDE voorkomt bovendien dat een eerste, door het hulpprogramma
    # gemaakt venster zichtbaar wordt. We gebruiken geen DETACHED_PROCESS,
    # omdat die vlag CREATE_NO_WINDOW juist kan overrulen.
    vensterinstellingen = subprocess.STARTUPINFO()
    vensterinstellingen.dwFlags |= subprocess.STARTF_USESHOWWINDOW
    vensterinstellingen.wShowWindow = subprocess.SW_HIDE
    return {
        'creationflags': subprocess.CREATE_NO_WINDOW,
        'startupinfo': vensterinstellingen,
    }
