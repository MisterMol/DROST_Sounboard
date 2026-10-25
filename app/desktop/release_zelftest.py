"""Een vensterloze smoke-test die een PyInstaller-build kan uitvoeren.

Schrijft JSON voor het bouwscript en opent geen microfoon of server.
"""
from __future__ import annotations

import json
from pathlib import Path
import sys


def controleer_gebundelde_release(uitvoerbestand: str) -> int:
    verslag = {'vensterloos_buildtype': bool(getattr(sys, 'frozen', False)),
               'statische_bestanden': False, 'ffmpeg_gevonden': False,
               'audiobibliotheken': False, 'velopack_sdk': False,
               'repository_geverifieerd': False, 'fouten': []}
    try:
        from app.webinterface.lokale_webserver import STATISCHE_MAP
        verslag['statische_bestanden'] = all(
            (STATISCHE_MAP / n).is_file() for n in ('dashboard.html', 'dashboard.js', 'stijl.css')
        )
    except Exception as fout:
        verslag['fouten'].append('statische bestanden: ' + str(fout)[:180])
    try:
        import imageio_ffmpeg
        verslag['ffmpeg_gevonden'] = Path(imageio_ffmpeg.get_ffmpeg_exe()).is_file()
    except Exception as fout:
        verslag['fouten'].append('FFmpeg: ' + str(fout)[:180])
    try:
        import sounddevice, numpy, soundfile, soxr, pystray  # noqa: F401
        verslag['audiobibliotheken'] = True
    except Exception as fout:
        verslag['fouten'].append('audiobibliotheken: ' + str(fout)[:180])
    try:
        import velopack  # noqa: F401
        verslag['velopack_sdk'] = True
    except Exception as fout:
        verslag['fouten'].append('Velopack SDK: ' + str(fout)[:180])
    try:
        from app.desktop.release_updates import lees_releasebron
        verslag['repository_geverifieerd'] = bool(lees_releasebron()[0])
    except Exception as fout:
        verslag['fouten'].append('updatebron: ' + str(fout)[:180])
    verslag['geslaagd'] = all(verslag[k] for k in
                               ('vensterloos_buildtype', 'statische_bestanden', 'ffmpeg_gevonden',
                                'audiobibliotheken', 'velopack_sdk'))
    try:
        Path(uitvoerbestand).write_text(json.dumps(verslag, ensure_ascii=False, indent=2), encoding='utf-8')
    except OSError:
        return 2
    return 0 if verslag['geslaagd'] else 1
