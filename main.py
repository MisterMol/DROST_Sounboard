"""Start de eerste ontwikkelfase van DrostSoundboard zonder argumenten.

De volledige app krijgt later een dashboard. Voor nu kunnen we gecontroleerd
vaststellen welke audioapparaten aanwezig zijn en werken de logs al.
"""

from __future__ import annotations

import platform
import sys

from app.audio.apparatenbeheer import (
    ResultaatVanApparaatcontrole,
    controleer_werkelijk_aangesloten_audioapparaten,
)
from app.diagnostiek.logboek import (
    maak_logboeken_klaar,
    sluit_logboeken_netjes_af,
    schrijf_auditgebeurtenis,
    zet_uitgebreide_foutafhandeling_aan,
)


def toon_apparaten_in_overzicht(resultaat: ResultaatVanApparaatcontrole) -> None:
    """Toon de concrete namen, zodat we straks de juiste apparaten kiezen."""
    print("\nGevonden geluidsapparaten\n")
    print(f"{'Nr.':>4}  {'Soort':<17}  {'Audio-API':<23} Naam")
    print("=" * 88)

    for apparaat in resultaat.apparaten:
        richtingen = []
        if apparaat.aantal_invoerkanalen > 0:
            richtingen.append("opnemen")
        if apparaat.aantal_uitvoerkanalen > 0:
            richtingen.append("afspelen")

        print(
            f"{apparaat.huidig_apparaatnummer:>4}  "
            f"{', '.join(richtingen):<17}  "
            f"{apparaat.api_naam:<23} {apparaat.naam}"
        )

    print("\nUitkomst van de controle")
    print(
        "CABLE Input, de afspeelkant: "
        + ("gevonden" if resultaat.cable_input_aanwezig else "NIET gevonden")
    )
    print(
        "CABLE Output, de opnamekant: "
        + ("gevonden" if resultaat.cable_output_aanwezig else "NIET gevonden")
    )
    print(
        "Mogelijke fysieke microfoon: "
        + (
            "gevonden"
            if resultaat.fysieke_microfoon_mogelijk_aanwezig
            else "niet op naam herkend, controleer bovenstaande lijst"
        )
    )

    if not resultaat.cable_input_aanwezig or not resultaat.cable_output_aanwezig:
        print(
            "\nControleer VB-CABLE via Windows + R en mmsys.cpl. "
            "In INSTALLEREN.md staan de exacte stappen."
        )


def voer_eerste_apparaatcontrole_uit() -> int:
    """Controleer afhankelijkheden en apparaten, met volledige foutinformatie."""
    try:
        logboeken = maak_logboeken_klaar()
    except OSError as fout_met_logmap:
        # Als zelfs de map voor fouten niet kan worden geopend, moeten we dit
        # ten minste zichtbaar in de terminal melden in plaats van zwijgen.
        print(f"LOG-001: De logmap kan niet worden geopend: {fout_met_logmap}")
        return 1

    zet_uitgebreide_foutafhandeling_aan()
    logboeken.softwarelogboek.info(
        "Apparaatcontrole wordt gestart",
        extra={
            "gebeurtenis": "apparaatcontrole_gestart",
            "gegevens": {
                "pythonversie": platform.python_version(),
                "windowsversie": platform.platform(),
                "systeemarchitectuur": platform.machine(),
            },
        },
    )
    schrijf_auditgebeurtenis(
        logboeken.auditlogboek, "apparaatcontrole_gestart", {"fase": 0}
    )

    print("DrostSoundboard, apparaatcontrole voor fase 0")
    print("Dit programma speelt nog geen geluid af en opent je microfoon niet.")
    print(f"De logbestanden staan hier: {logboeken.map_met_logbestanden}")

    try:
        resultaat = controleer_werkelijk_aangesloten_audioapparaten(
            softwarelogboek=logboeken.softwarelogboek
        )
        toon_apparaten_in_overzicht(resultaat)

        gevonden_apparaatgegevens = [
            {
                "nummer": apparaat.huidig_apparaatnummer,
                "naam": apparaat.naam,
                "api": apparaat.api_naam,
                "invoerkanalen": apparaat.aantal_invoerkanalen,
                "uitvoerkanalen": apparaat.aantal_uitvoerkanalen,
            }
            for apparaat in resultaat.apparaten
        ]
        logboeken.softwarelogboek.info(
            "Audioapparaten zijn gecontroleerd",
            extra={
                "gebeurtenis": "apparaatcontrole_afgerond",
                "gegevens": {
                    "apparaten": gevonden_apparaatgegevens,
                    "aantal_apparaten": len(resultaat.apparaten),
                    "cable_input_aanwezig": resultaat.cable_input_aanwezig,
                    "cable_output_aanwezig": resultaat.cable_output_aanwezig,
                    "mogelijke_fysieke_microfoon": resultaat.fysieke_microfoon_mogelijk_aanwezig,
                },
            },
        )
        schrijf_auditgebeurtenis(
            logboeken.auditlogboek,
            "apparaatcontrole_afgerond",
            {
                "resultaat": "controle_uitgevoerd",
                "aantal_apparaten": len(resultaat.apparaten),
            },
        )
        return 0

    except ModuleNotFoundError as oorspronkelijke_fout:
        logboeken.softwarelogboek.exception(
            "Een Python-afhankelijkheid ontbreekt",
            extra={
                "gebeurtenis": "afhankelijkheid_ontbreekt",
                "gegevens": {
                    "foutcode": "APP-001",
                    "ontbrekende_module": oorspronkelijke_fout.name,
                    "hersteladvies": "Installeer requirements.txt in de projectomgeving",
                },
            },
        )
        print(
            "\nAPP-001: Er ontbreekt een Python-onderdeel: "
            f"{oorspronkelijke_fout.name}."
        )
        print("Voer uit: .\\.venv\\Scripts\\python.exe -m pip install -r requirements.txt")
        return 1

    except Exception:
        # Deze vangst is alleen voor de bovenste programmagrens. We bewaren
        # hier de volledige traceback; de app mag nooit schijnbaar slagen.
        logboeken.softwarelogboek.exception(
            "De controle kon niet worden afgerond",
            extra={
                "gebeurtenis": "apparaatcontrole_mislukt",
                "gegevens": {"foutcode": "APP-002"},
            },
        )
        print("\nAPP-002: De controle kon niet worden afgerond. Bekijk software.jsonl.")
        return 1

    finally:
        logboeken.softwarelogboek.info(
            "De apparaatcontrolesessie is afgesloten",
            extra={"gebeurtenis": "sessie_afgesloten"},
        )
        print(f"\nLogmap: {logboeken.map_met_logbestanden}")
        sluit_logboeken_netjes_af(logboeken)


if __name__ == "__main__":
    sys.exit(voer_eerste_apparaatcontrole_uit())
