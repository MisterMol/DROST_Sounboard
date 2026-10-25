"""Een klein Windows-menu zonder extra browser- of geluidsprocessen."""
from __future__ import annotations

import webbrowser
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.webinterface.bediening_van_de_audiomotor import WebbedieningVanDrostSoundboard


def maak_eenvoudig_soundboard_pictogram(verbonden: bool = False):
    """Teken de tray-icoon lokaal; er zijn geen externe afbeeldingen nodig."""
    from PIL import Image, ImageDraw
    afbeelding = Image.new('RGBA', (64, 64), (0, 0, 0, 0))
    tekenaar = ImageDraw.Draw(afbeelding)
    tekenaar.rounded_rectangle((4, 4, 60, 60), radius=18, fill=(20, 29, 38, 255))
    kleur = (105, 207, 178, 255) if verbonden else (144, 161, 173, 255)
    # Minimalistische golfvorm die in het Windows-systeemvak leesbaar blijft.
    for x, hoogte in ((17, 13), (26, 25), (35, 34), (44, 20)):
        tekenaar.rounded_rectangle((x, 32 - hoogte // 2, x + 5, 32 + hoogte // 2), radius=2, fill=kleur)
    return afbeelding


def maak_systeemvakicoon(bediening: 'WebbedieningVanDrostSoundboard',
                          adres: str, vraag_afsluiten, logmap, softwarelogboek,
                          sneltoetsen=None, release_updates=None):
    """Laat menuacties altijd de bestaande Python-bediening gebruiken."""
    import os
    import pystray
    from app.desktop.opstartinstellingen import (
        bepaal_stabiele_launcher, start_met_windows_ingeschakeld,
        wijzig_start_met_windows,
    )

    def open_dashboard(_icoon=None, _item=None):
        webbrowser.open(adres, new=2)

    def voer_trayactie_uit(naam, actie):
        try:
            actie()
        except Exception:
            softwarelogboek.exception('Systeemvakactie mislukt', extra={
                'gebeurtenis': 'systeemvak_actie_mislukt',
                'gegevens': {'actie': naam, 'foutcode': 'DESKTOP-030'}})

    def schakel_effecten(_icoon, _item):
        def uitvoeren():
            status = bediening.geef_huidige_webstatus()
            if status['toestand'] == 'verbonden':
                bediening.zet_soundboard_aan_of_uit(not status['effecten_aan'])
                _icoon.update_menu()
            else:
                open_dashboard()
        voer_trayactie_uit('effecten_schakelen', uitvoeren)

    def stop_geluiden(_icoon, _item):
        voer_trayactie_uit('stop_geluid', bediening.stop_het_huidige_geluid)

    def open_logboeken(_icoon, _item):
        voer_trayactie_uit('logboeken_openen', lambda: os.startfile(str(logmap)))

    def schakel_sneltoetsen(_icoon, _item):
        def uitvoeren():
            if sneltoetsen is None:
                return
            huidig = sneltoetsen.geef_huidige_instellingen()
            huidig['ingeschakeld'] = not huidig['ingeschakeld']
            huidig.pop('mislukte_registraties', None)
            sneltoetsen.pas_instellingen_aan(huidig)
            _icoon.update_menu()
        voer_trayactie_uit('sneltoetsen_schakelen', uitvoeren)

    def start_met_windows_schakelen(_icoon, _item):
        def uitvoeren():
            wijzig_start_met_windows(not start_met_windows_ingeschakeld())
            _icoon.update_menu()
        voer_trayactie_uit('start_met_windows_schakelen', uitvoeren)

    def controleer_updates(_icoon, _item):
        if release_updates is None:
            return
        voer_trayactie_uit('controleer_updates', release_updates.controleer_handmatig)

    def update_status(_item):
        status = release_updates.geef_status() if release_updates is not None else 'Niet beschikbaar'
        return f'Updates: {status}'

    def sluit_app(_icoon, _item):
        # Niet alleen browser sluiten: de eigenlijke applicatie stopt hier,
        # en ruimt vervolgens zowel VB-CABLE als de sneltoetsregistraties op.
        vraag_afsluiten()
        _icoon.stop()

    menu = pystray.Menu(
        pystray.MenuItem('Dashboard openen', open_dashboard, default=True),
        pystray.Menu.SEPARATOR,
        pystray.MenuItem('Geluidseffecten aan/uit', schakel_effecten),
        pystray.MenuItem('Alle geluiden stoppen', stop_geluiden),
        pystray.MenuItem('Globale sneltoetsen actief', schakel_sneltoetsen,
                          checked=lambda item: bool(sneltoetsen and sneltoetsen.geef_huidige_instellingen()['ingeschakeld'])),
        pystray.Menu.SEPARATOR,
        pystray.MenuItem('Start met Windows', start_met_windows_schakelen,
                          checked=lambda item: start_met_windows_ingeschakeld(),
                          enabled=lambda item: bepaal_stabiele_launcher() is not None),
        pystray.Menu.SEPARATOR,
        pystray.MenuItem('Op updates controleren', controleer_updates,
                          enabled=lambda item: bool(release_updates and release_updates.beschikbaar())),
        pystray.MenuItem(update_status, lambda *_: None, enabled=False),
        pystray.Menu.SEPARATOR,
        pystray.MenuItem('Logboeken openen', open_logboeken),
        pystray.MenuItem('Afsluiten (virtuele microfoon stopt)', sluit_app),
    )
    from app.diagnostiek.logboek import VERSIE_VAN_DE_APP
    return pystray.Icon('DrostSoundboard', maak_eenvoudig_soundboard_pictogram(), f'DrostSoundboard {VERSIE_VAN_DE_APP}', menu)
