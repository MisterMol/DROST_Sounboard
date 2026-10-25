"""Verbind vaste favoriete plekken aan veilige, instelbare Windows-hotkeys."""
from __future__ import annotations

import sys
from typing import Any

from app.desktop.sneltoetsinstellingen import (OpslagVanSneltoetsinstellingen,
    OngeldigeSneltoetsinstelling, controleer_sneltoetsinstellingen, geef_standaard_sneltoetsen)
from app.desktop.windows_sneltoetsen import GlobaleSneltoetsenVanWindows
from app.diagnostiek.logboek import schrijf_auditgebeurtenis


class BedieningVanGlobaleSneltoetsen:
    """De HTTP-server, het systeemvak en Windows delen één instellingenobject."""

    def __init__(self, bediening: Any, opslag: OpslagVanSneltoetsinstellingen):
        self.bediening = bediening
        self.opslag = opslag
        self.logboeken = bediening.logboeken
        try:
            configuratie = opslag.lees_instellingen()
        except OngeldigeSneltoetsinstelling:
            # Een oud of beschadigd instellingenbestand mag nooit de complete
            # audiomixer blokkeren. Bewaar het origineel voor diagnose en start
            # met veilig uitgeschakelde sneltoetsen.
            self.logboeken.softwarelogboek.exception('Sneltoetsinstellingen zijn ongeldig; standaard uit', extra={
                'gebeurtenis': 'sneltoetsen_veilige_start',
                'gegevens': {'foutcode': 'HOTKEY-031', 'instellingenbestand': str(opslag.opslagpad)},
            })
            configuratie = geef_standaard_sneltoetsen()
        self.windows = GlobaleSneltoetsenVanWindows(
            self.voer_ingestelde_actie_uit,
            self.logboeken.softwarelogboek,
            configuratie,
        )

    def start(self) -> None:
        self.windows.start()

    def geef_huidige_instellingen(self) -> dict:
        gegevens = self.windows.geef_huidige_instellingen()
        gegevens['ondersteund'] = sys.platform == 'win32'
        return gegevens

    def pas_instellingen_aan(self, gegevens: object) -> dict:
        nieuwe = controleer_sneltoetsinstellingen(gegevens)
        oude = self.windows.geef_huidige_instellingen()
        oude.pop('mislukte_registraties', None)
        try:
            resultaat = self.windows.pas_instellingen_aan(nieuwe)
            self.opslag.bewaar_instellingen(nieuwe)
        except Exception:
            # Registreren lukt bijvoorbeeld niet meer na een Windows-fout.
            # Maak de vorige instellingen weer actief en geef de traceback door.
            try:
                self.windows.pas_instellingen_aan(oude)
            except Exception:
                self.logboeken.softwarelogboek.exception('Terugzetten van sneltoetsen mislukte')
            raise
        schrijf_auditgebeurtenis(self.logboeken.auditlogboek, 'sneltoetsinstellingen_aangepast', {
            'ingeschakeld': nieuwe['ingeschakeld'],
            'acties': sorted(nieuwe['combinaties']),
            'conflicten': resultaat['mislukte_registraties'],
        })
        return self.geef_huidige_instellingen()

    def voer_ingestelde_actie_uit(self, actie: str) -> None:
        if actie == 'stop':
            self.bediening.stop_het_huidige_geluid()
            schrijf_auditgebeurtenis(self.logboeken.auditlogboek, 'sneltoets_stop', {'actie': 'stop'})
            return
        if not actie.startswith('favoriet_'):
            raise ValueError(f'HOTKEY-020: ongeldige sneltoetsactie: {actie!r}')
        plek = int(actie.split('_', 1)[1])
        favorieten = self.bediening.favorieten.geef_alle_favorietplekken()
        geluid_id = favorieten[plek - 1]
        if geluid_id is None:
            schrijf_auditgebeurtenis(self.logboeken.auditlogboek, 'sneltoets_lege_favoriet', {'plek': plek})
            return
        # De bestaande afspeelfunctie controleert verbinding en rechten
        # en decodeert audio buiten de realtime audiowerkdraad.
        self.bediening.speel_geluid_uit_de_bibliotheek(geluid_id)
        schrijf_auditgebeurtenis(self.logboeken.auditlogboek, 'sneltoets_geluid_aangevraagd', {
            'plek': plek, 'geluid_id': geluid_id, 'bron': 'globale_sneltoets',
        })

    def stop(self) -> None:
        self.windows.stop()
