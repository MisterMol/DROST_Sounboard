"""Een vensterloze smoke-test die een PyInstaller-build kan uitvoeren.

Schrijft JSON voor het bouwscript en opent geen microfoon of server.
"""
from __future__ import annotations

import json
from pathlib import Path
import sys


def controleer_gebundelde_release(uitvoerbestand: str) -> int:
    from app.diagnostiek.logboek import VERSIE_VAN_DE_APP
    verslag = {'versie': VERSIE_VAN_DE_APP, 'vensterloos_buildtype': bool(getattr(sys, 'frozen', False)),
               'statische_bestanden': False, 'ffmpeg_gevonden': False,
               'audiobibliotheken': False, 'velopack_sdk': False,
               'repository_geverifieerd': False, 'stemvoorbeelden': False, 'signalsmith': False, 'llvc_worker': False, 'fouten': []}
    try:
        from app.webinterface.lokale_webserver import STATISCHE_MAP
        verslag['statische_bestanden'] = all(
            (STATISCHE_MAP / n).is_file() for n in ('dashboard.html', 'dashboard.js', 'stijl.css', 'drost-logo.svg', 'drost-logo.png', 'favicon.ico')
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
        from app.audio.ingebouwde_stemvoorbeelden import geef_voorbeeldpad
        verslag['stemvoorbeelden'] = all(geef_voorbeeldpad(s).is_file() for s in ('bob','elise'))
    except Exception as fout:
        verslag['fouten'].append('stemvoorbeelden: ' + str(fout)[:180])
    try:
        from app.audio.signalsmith_motor import SignalsmithMotor
        import numpy as np
        motor = SignalsmithMotor()
        try:
            geluid = (.12*np.sin(2*np.pi*220*np.arange(48000)/48000)).astype(np.float32)[:, None]
            uit = np.concatenate([motor.verwerk_blok(geluid[i:i+480], toonhoogte=12)
                                  for i in range(0, len(geluid), 480)])
            deel = uit[-24000:, 0]
            frequentie = float(np.fft.rfftfreq(len(deel), 1/48000)[
                np.argmax(np.abs(np.fft.rfft(deel*np.hanning(len(deel)))))] )
            verslag['signalsmith'] = bool(np.isfinite(uit).all() and 430 < frequentie < 450)
        finally:
            motor.sluiten()
    except Exception as fout:
        verslag['fouten'].append('stemmotor: ' + str(fout)[:180])
    try:
        import tempfile
        import logging
        import time
        from app.audio.natuurlijke_stem.dienst import NatuurlijkeStemDienst
        with tempfile.TemporaryDirectory(prefix='DrostStem_release_') as folder:
            motor = NatuurlijkeStemDienst(Path(folder)/'keuze.json', logging.getLogger('stem_release'), autostart=False)
            try:
                motor.stel_in(True, bewaren=False)
                deadline = time.monotonic() + 50
                while time.monotonic() < deadline and motor.status()['toestand'] == 'laden':
                    time.sleep(.1)
                verslag['llvc_worker'] = motor.status()['toestand'] == 'gereed'
                verslag['llvc_computertest'] = motor.status().get('computertest')
                if not verslag['llvc_worker']:
                    verslag['fouten'].append('LLVC-worker: ' + motor.status()['melding'])
            finally:
                motor.sluiten()
    except Exception as fout:
        verslag['fouten'].append('LLVC-worker: ' + str(fout)[:180])
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
                                'audiobibliotheken', 'velopack_sdk', 'stemvoorbeelden', 'signalsmith', 'llvc_worker'))
    try:
        Path(uitvoerbestand).write_text(json.dumps(verslag, ensure_ascii=False, indent=2), encoding='utf-8')
    except OSError:
        return 2
    return 0 if verslag['geslaagd'] else 1
