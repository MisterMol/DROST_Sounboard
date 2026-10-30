"""Desktopstart zonder parameters, onafhankelijk van het geopende browservenster.

De audiomixer leeft precies zolang als dit ene Windows-achtergrondproces.
Een traymenu of een globale sneltoets bedient dezelfde bestaande mixer.
"""
from __future__ import annotations

import argparse
import platform
import os
import sys
import threading
import webbrowser

from app.desktop.afsluitbeheer import sluit_onderdelen_af, sluit_webserver_af
from app.desktop.een_actieve_instantie import EenActieveInstantie
from app.desktop.release_updates import ReleaseUpdateService, initialiseer_velopack_bij_start
from app.diagnostiek.logboek import (maak_logboeken_klaar, sluit_logboeken_netjes_af,
                                    schrijf_auditgebeurtenis, zet_uitgebreide_foutafhandeling_aan,
                                    VERSIE_VAN_DE_APP)


def start_drostsoundboard_als_desktopprogramma(*, open_browser: bool = True) -> int:
    if sys.platform != 'win32':
        print('DESKTOP-100: systeemvak en globale sneltoetsen werken alleen op Windows.')
        return 2
    instantie = EenActieveInstantie()
    try:
        als_eerste = instantie.probeer_eigenaarschap_te_krijgen()
    except Exception:
        # Nog vóór het openen van logs: een kapot mutex-pad zou een dubbele
        # audioverbinding kunnen veroorzaken. Stop dan veilig met een fout.
        print('DESKTOP-101: controle of er al een instantie draait is mislukt.')
        return 1
    if not als_eerste:
        if open_browser:
            adres = instantie.lees_adres_van_bestaande_instantie()
            if adres:
                webbrowser.open(adres, new=2)
        return 0

    logboeken = None
    server = None
    bediening = None
    sneltoetsen = None
    serverdraad = None
    server_gestart = False
    icoon = None
    afsluiten_gevraagd = threading.Event()
    update_service = ReleaseUpdateService()
    normaal_afgesloten = False
    try:
        # Er draait dankzij de mutex nu geen andere mixer. Een eerder
        # gedownloade update mag hier worden toegepast VOORDAT audio start.
        if update_service.pas_toe_voor_audio_start(achtergrond=not open_browser):
            return 0
        logboeken = maak_logboeken_klaar()
        update_service.softwarelogboek = logboeken.softwarelogboek
        zet_uitgebreide_foutafhandeling_aan()
        import sounddevice as audiobibliotheek
        import numpy  # noqa: F401
        import soundfile  # noqa: F401
        import soxr  # noqa: F401
        import pystray  # noqa: F401
        from app.webinterface.bediening_van_de_audiomotor import WebbedieningVanDrostSoundboard
        from app.webinterface.lokale_webserver import LokaleWebserverVanDrostSoundboard
        from app.desktop.bediening_van_sneltoetsen import BedieningVanGlobaleSneltoetsen
        from app.desktop.sneltoetsinstellingen import OpslagVanSneltoetsinstellingen
        from app.desktop.systeemvak import maak_systeemvakicoon

        bediening = WebbedieningVanDrostSoundboard(audiobibliotheek, logboeken)
        sneltoetsen = BedieningVanGlobaleSneltoetsen(bediening, OpslagVanSneltoetsinstellingen())
        sneltoetsen.start()
        try:
            server = LokaleWebserverVanDrostSoundboard(('127.0.0.1', 8765), bediening)
        except OSError:
            # Alleen als het echt een ANDER lokaal proces is. De mutex zorgt
            # dat twee DrostSoundboards nooit beide een audiomixer openen.
            server = LokaleWebserverVanDrostSoundboard(('127.0.0.1', 0), bediening)
        server.sneltoetsbediening = sneltoetsen
        server.afsluitverzoek = afsluiten_gevraagd
        instantie.schrijf_lokaal_dashboardadres(server.server_port)
        adres = f'http://127.0.0.1:{server.server_port}/'
        serverdraad = threading.Thread(target=server.serve_forever, kwargs={'poll_interval': 0.2},
                                      name='Lokale-webserver', daemon=True)
        serverdraad.start()
        server_gestart = True
        logboeken.softwarelogboek.info('Desktopproces is gestart', extra={
            'gebeurtenis': 'desktopproces_gestart',
            'gegevens': {'poort': server.server_port, 'python': platform.python_version(),
                        'appversie': VERSIE_VAN_DE_APP, 'proces_id': os.getpid()},
        })
        schrijf_auditgebeurtenis(logboeken.auditlogboek, 'desktopproces_gestart', {'poort': server.server_port})
        icoon = maak_systeemvakicoon(
            bediening, adres, afsluiten_gevraagd.set,
            logboeken.map_met_logbestanden, logboeken.softwarelogboek, sneltoetsen,
            release_updates=update_service,
        )
        update_service.start_automatisch()
        if open_browser:
            webbrowser.open(adres, new=2)
        # pystray.run() verzorgt het Windows-systeemvak. De HTTP-server leeft
        # op een andere draad en stopt niet wanneer het tabblad wordt gesloten.
        def verzorg_systeemvak(klaar_icoon):
            # pystray roept setup pas aan zodra de Windows-berichtenlus draait.
            # Ook een vroeg afsluitverzoek vanuit de browser blijft zo bewaard.
            try:
                klaar_icoon.visible = True
                afsluiten_gevraagd.wait()
            finally:
                klaar_icoon.stop()

        icoon.run(setup=verzorg_systeemvak)
        normaal_afgesloten = True
        afsluiten_gevraagd.set()
        return 0
    except KeyboardInterrupt:
        # Voor ontwikkelaars die de desktopstarter bewust met python.exe
        # starten. De finally-clausule sluit server en audio ook hier af.
        return 0
    except Exception as fout:
        if logboeken is not None:
            logboeken.softwarelogboek.exception('Desktopapp is vastgelopen of kon niet starten', extra={
                'gebeurtenis': 'desktop_start_mislukt',
                'gegevens': {'foutcode': 'DESKTOP-999', 'type': type(fout).__name__},
            })
        else:
            print(f'DESKTOP-999: {type(fout).__name__}: {fout}')
        return 1
    finally:
        afsluiten_gevraagd.set()
        logger = logboeken.softwarelogboek if logboeken is not None else None
        if server is not None:
            server.wordt_afgesloten.set()
        # Iedere stap wordt geprobeerd, ook als de vorige faalt. Een False van
        # sluit_alle_audio_af is geen geslaagde afsluiting.
        stappen = [('updatecontrole', update_service.stop)]
        if icoon is not None:
            stappen.append(('systeemvak', icoon.stop))
        if sneltoetsen is not None:
            stappen.append(('sneltoetsen', sneltoetsen.stop))
        stappen.append(('lokale webserver',
                        lambda: sluit_webserver_af(server, serverdraad, server_gestart)))
        if bediening is not None:
            stappen.append(('audio en stemverwerking', bediening.sluit_alle_audio_af))
        netjes = sluit_onderdelen_af(logger, stappen)
        try:
            if logboeken is not None:
                netjes = sluit_onderdelen_af(logger, [
                    ('afsluitregistratie', lambda: schrijf_auditgebeurtenis(
                        logboeken.auditlogboek, 'desktopproces_afgesloten', {'volledig': netjes})),
                    ('logboeken', lambda: sluit_logboeken_netjes_af(logboeken)),
                ]) and netjes
        finally:
            # De mutex blijft vast tot alle eigen onderdelen aan bod zijn geweest.
            instantie.laat_vergrendeling_los()
        if normaal_afgesloten and netjes:
            update_service.pas_toe_na_audio_stop()
        if not netjes:
            return 1


def geef_startargumenten(argv=None):
    parser = argparse.ArgumentParser(description='DrostSoundboard-desktopapp')
    parser.add_argument('--achtergrond', action='store_true',
                        help='Start alleen in het Windows-systeemvak, zonder browservenster.')
    parser.add_argument('--controleer-release', metavar='JSON_PAD',
                        help='Bouwdiagnose uitvoeren en JSON schrijven zonder audio te starten.')
    return parser.parse_args(argv)


if __name__ == '__main__':
    # Deze Velopack-hook MOET vóór gewone app-startcode komen; de SDK mag
    # NIET automatisch toepassen bij een tweede klik op de snelkoppeling.
    initialiseer_velopack_bij_start()
    args = geef_startargumenten()
    if args.controleer_release:
        from app.desktop.release_zelftest import controleer_gebundelde_release
        sys.exit(controleer_gebundelde_release(args.controleer_release))
    sys.exit(start_drostsoundboard_als_desktopprogramma(open_browser=not args.achtergrond))
