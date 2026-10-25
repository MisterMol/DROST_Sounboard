"""Controleer VB-CABLE vanaf Windows met één dubbelklik en zonder argumenten.

Dit is een losse test voor fase 1; main.py blijft gewoon de
apparaatcontrole uitvoeren totdat de volledige soundboardinterface bestaat.
"""

from __future__ import annotations

import platform
import sys
from uuid import uuid4

from app.audio.apparatenbeheer import controleer_werkelijk_aangesloten_audioapparaten
from app.audio.kabelcontrole import (
    KabelcontroleFout,
    voer_korte_test_van_de_virtuele_kabel_uit,
    selecteer_de_twee_uiteinden_van_vb_cable,
)
from app.diagnostiek.logboek import (
    maak_logboeken_klaar,
    schrijf_auditgebeurtenis,
    sluit_logboeken_netjes_af,
    zet_uitgebreide_foutafhandeling_aan,
)


def voer_de_eerste_echte_kabeltest_uit() -> int:
    """Speel één veilige testtoon en leg resultaat en fouten reproduceerbaar vast."""
    try:
        logboeken = maak_logboeken_klaar()
    except OSError as fout_bij_openen_van_logmap:
        print(
            "LOG-001: Kan de logbestanden niet openen: "
            f"{fout_bij_openen_van_logmap}"
        )
        return 1

    zet_uitgebreide_foutafhandeling_aan()
    testnummer = str(uuid4())
    huidige_actie = "voorbereiding"
    print("\nDrostSoundboard, fase 1: controle van de virtuele kabel")
    print("Er wordt een zachte testtoon van 1,8 seconde doorgestuurd.")
    print("De echte microfoon wordt NIET geopend en instellingen blijven gelijk.")
    print("We meten het signaal aan de andere kant van VB-CABLE.")
    print(f"Logbestanden: {logboeken.map_met_logbestanden}\n")

    schrijf_auditgebeurtenis(
        logboeken.auditlogboek,
        "kabeltest_gestart",
        {"testnummer": testnummer, "fase": 1},
    )
    logboeken.softwarelogboek.info(
        "Kabeltest begonnen",
        extra={
            "gebeurtenis": "kabeltest_gestart",
            "gegevens": {
                "testnummer": testnummer,
                "fase": 1,
                "pythonversie": platform.python_version(),
                "windowsversie": platform.platform(),
            },
        },
    )

    try:
        huidige_actie = "audioapparaten opzoeken"
        apparaatcontrole = controleer_werkelijk_aangesloten_audioapparaten(
            softwarelogboek=logboeken.softwarelogboek
        )
        gekozen_apparaten = selecteer_de_twee_uiteinden_van_vb_cable(
            apparaatcontrole.apparaten
        )
        print("Automatisch geselecteerd:")
        print(
            f"  Afspelen: {gekozen_apparaten.afspeelkant.naam} "
            f"(WASAPI {gekozen_apparaten.afspeelkant.huidig_apparaatnummer})"
        )
        print(
            f"  Opnemen:  {gekozen_apparaten.opnamekant.naam} "
            f"(WASAPI {gekozen_apparaten.opnamekant.huidig_apparaatnummer})"
        )
        print("\nTest wordt uitgevoerd...\n")
        logboeken.softwarelogboek.info(
            "Virtuele kabelapparaten gekozen voor de test",
            extra={
                "gebeurtenis": "kabel_apparaten_geselecteerd",
                "gegevens": {
                    "testnummer": testnummer,
                    "uitvoer_naam": gekozen_apparaten.afspeelkant.naam,
                    "uitvoer_huidig_nummer": gekozen_apparaten.afspeelkant.huidig_apparaatnummer,
                    "opname_naam": gekozen_apparaten.opnamekant.naam,
                    "opname_huidig_nummer": gekozen_apparaten.opnamekant.huidig_apparaatnummer,
                },
            },
        )

        # Pas importeren nadat het logboek bestaat. Ontbreekt de dependency,
        # dan komt de echte ModuleNotFoundError dus alsnog in de traceback.
        import sounddevice as audiobibliotheek

        huidige_actie = "testtoon afspelen en virtuele kabel meten"
        resultaat = voer_korte_test_van_de_virtuele_kabel_uit(
            audiobibliotheek=audiobibliotheek,
            geselecteerde_apparaten=gekozen_apparaten,
            softwarelogboek=logboeken.softwarelogboek,
            auditlogboek=logboeken.auditlogboek,
        )

        print("Uitkomst:")
        print(f"  Testtoon aangeboden: {resultaat.speelduur_van_testtoon_in_seconden:.2f} s")
        print(f"  Opgenomen frames:    {resultaat.aantal_opgenomen_frames}")
        print(
            "  Ontvangen niveau:   "
            f"{resultaat.gemiddelde_effectieve_samplewaarde:.5f} RMS"
        )
        print(f"  Herkende testtoon:   {resultaat.herkende_toonssterkte:.5f}")
        print(f"  Bufferproblemen:    {resultaat.aantal_waargenomen_bufferproblemen}")
        print()

        schrijf_auditgebeurtenis(
            logboeken.auditlogboek,
            "kabeltest_afgerond",
            {
                "testnummer": testnummer,
                "resultaat": "geslaagd" if resultaat.is_gelukt else "onvoldoende_signaal",
                "ontvangen_rms": resultaat.gemiddelde_effectieve_samplewaarde,
                "herkende_toonssterkte": resultaat.herkende_toonssterkte,
                "aantal_bufferproblemen": resultaat.aantal_waargenomen_bufferproblemen,
            },
        )

        if resultaat.is_gelukt:
            print("GESLAAGD: CABLE Output ontvangt audio van CABLE Input.")
            print("Dit bewijst nog niet dat Discord of je microfoon werkt.")
            return 0

        print("NOG NIET GOED: er kwam onvoldoende schoon signaal door.")
        print("Controleer de niveaus van VB-CABLE in mmsys.cpl en bekijk de logs.")
        return 2

    except Exception as oorspronkelijke_fout:
        # Alleen hier aan de buitenrand vangen we onverwachte fouten op.
        # De echte uitzondering en eventuele oorzaakketen blijven behouden.
        logboeken.softwarelogboek.exception(
            "De kabeltest is mislukt",
            extra={
                "gebeurtenis": "kabeltest_mislukt",
                "gegevens": {
                    "foutcode": (
                        "KABEL-999" if not isinstance(oorspronkelijke_fout, KabelcontroleFout)
                        else "KABEL-TEST"
                    ),
                    "testnummer": testnummer,
                    "actie_bij_fout": huidige_actie,
                    "soort_exception": type(oorspronkelijke_fout).__name__,
                    "hersteladvies": "Bekijk software.jsonl met de volledige traceback",
                },
            },
        )
        schrijf_auditgebeurtenis(
            logboeken.auditlogboek,
            "kabeltest_mislukt",
            {
                "testnummer": testnummer,
                "actie_bij_fout": huidige_actie,
                "fouttype": type(oorspronkelijke_fout).__name__,
            },
        )
        print(f"MISLUKT bij '{huidige_actie}': {oorspronkelijke_fout}")
        print("De volledige traceback staat in software.jsonl.")
        return 1

    finally:
        print(f"\nLogmap: {logboeken.map_met_logbestanden}")
        sluit_logboeken_netjes_af(logboeken)


if __name__ == "__main__":
    sys.exit(voer_de_eerste_echte_kabeltest_uit())
