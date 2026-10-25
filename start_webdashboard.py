"""Start met een dubbelklik het lokale webdashboard, zonder argumenten.

Python blijft nodig voor de audiomixer. De browser toont alleen HTML, CSS en
JavaScript; hij krijgt geen rechtstreekse toegang tot Windows-audiodrivers.
"""

from __future__ import annotations

import platform
import sys
import webbrowser

from app.diagnostiek.logboek import (
    maak_logboeken_klaar, schrijf_auditgebeurtenis,
    sluit_logboeken_netjes_af, zet_uitgebreide_foutafhandeling_aan,
)


def start_het_lokale_webdashboard() -> int:
    try:
        logboeken = maak_logboeken_klaar()
    except OSError as fout:
        print(f'WEBSTART-001: kon logmap niet aanmaken: {fout}')
        return 1
    zet_uitgebreide_foutafhandeling_aan()
    server = None
    bediening = None
    try:
        import sounddevice as audiobibliotheek
        import numpy  # noqa: F401
        import soundfile  # noqa: F401
        import soxr  # noqa: F401
        from app.webinterface.bediening_van_de_audiomotor import WebbedieningVanDrostSoundboard
        from app.webinterface.lokale_webserver import LokaleWebserverVanDrostSoundboard

        bediening = WebbedieningVanDrostSoundboard(audiobibliotheek, logboeken)
        try:
            server = LokaleWebserverVanDrostSoundboard(('127.0.0.1', 8765), bediening)
        except OSError as oorspronkelijke_fout:
            logboeken.softwarelogboek.warning(
                'Poort 8765 was bezet; er wordt een vrije lokale poort gekozen',
                extra={'gebeurtenis': 'webpoort_bezet', 'gegevens': {
                    'foutcode': 'WEBSTART-002', 'fout': str(oorspronkelijke_fout),
                }},
            )
            server = LokaleWebserverVanDrostSoundboard(('127.0.0.1', 0), bediening)

        adres = f'http://127.0.0.1:{server.server_port}/'
        logboeken.softwarelogboek.info(
            'Lokaal webdashboard gestart',
            extra={'gebeurtenis': 'webdashboard_gestart', 'gegevens': {
                'adres': adres, 'python': platform.python_version(),
            }},
        )
        schrijf_auditgebeurtenis(logboeken.auditlogboek, 'webdashboard_gestart', {'poort': server.server_port})
        print('\nDrostSoundboard is gestart.')
        print('Open de webpagina:', adres)
        print('Laat dit venster open terwijl je belt. Sluiten stopt de virtuele microfoon.\n')
        webbrowser.open(adres, new=2)
        server.serve_forever(poll_interval=0.5)
        return 0
    except KeyboardInterrupt:
        print('\nDrostSoundboard wordt afgesloten...')
        return 0
    except Exception as fout:
        logboeken.softwarelogboek.exception(
            'Webdashboard kon niet worden gestart',
            extra={'gebeurtenis': 'webdashboard_start_mislukt', 'gegevens': {
                'foutcode': 'WEBSTART-999', 'fouttype': type(fout).__name__,
            }},
        )
        if isinstance(fout, ModuleNotFoundError):
            print(f'WEBSTART-003: afhankelijkheid ontbreekt: {fout.name}')
            print('Voer eerst Installeer_ontwikkelomgeving.bat uit.')
        else:
            print(f'WEBSTART-999: {fout}')
        print('Volledige traceback:', logboeken.map_met_logbestanden / 'software.jsonl')
        return 1
    finally:
        if server is not None:
            server.server_close()
        if bediening is not None:
            try:
                netjes = bediening.sluit_alle_audio_af()
                if not netjes:
                    logboeken.softwarelogboek.error(
                        'Audiostream was niet tijdig afgesloten',
                        extra={'gebeurtenis': 'audio_niet_afgesloten', 'gegevens': {'foutcode': 'WEBSTART-004'}},
                    )
            except Exception:
                logboeken.softwarelogboek.exception(
                    'De audio kon bij afsluiten niet worden vrijgegeven',
                    extra={'gebeurtenis': 'webdashboard_afsluiten_mislukt', 'gegevens': {'foutcode': 'WEBSTART-005'}},
                )
        schrijf_auditgebeurtenis(logboeken.auditlogboek, 'webdashboard_afgesloten')
        sluit_logboeken_netjes_af(logboeken)


if __name__ == '__main__':
    sys.exit(start_het_lokale_webdashboard())
