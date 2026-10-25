"""Meet zonder argumenten of de actieve live-mixer echt bij CABLE Output aankomt."""

from __future__ import annotations

import sys
from uuid import uuid4

from app.audio.apparatenbeheer import controleer_werkelijk_aangesloten_audioapparaten
from app.audio.kabel_ontvangstmeting import (
    meet_echt_ontvangen_signaal_van_cable_output,
)
from app.diagnostiek.logboek import (
    bepaal_logmap_voor_deze_computer,
    maak_logboeken_klaar,
    schrijf_auditgebeurtenis,
    sluit_logboeken_netjes_af,
    zet_uitgebreide_foutafhandeling_aan,
)


def controleer_wat_cable_output_daadwerkelijk_ontvangt() -> int:
    """Open alleen de opnamekant en registreer uitsluitend getallen."""
    # De live-mixer kan op hetzelfde moment software.jsonl open hebben.
    # Daarom krijgt iedere ontvangsttest een eigen submap met aparte logs.
    # Zo verhinderen we gelijktijdige bestandsrotatie of Windows-filelocks.
    testnummer = str(uuid4())
    eigen_logmap = bepaal_logmap_voor_deze_computer() / "ontvangstmetingen" / testnummer
    try:
        logboeken = maak_logboeken_klaar(logmap=eigen_logmap)
    except OSError as fout:
        print(f"LOG-001: De logmap kon niet worden geopend: {fout}")
        return 1
    zet_uitgebreide_foutafhandeling_aan()
    huidige_actie = "audioapparaten zoeken"
    try:
        print("\nDrostSoundboard, controle van CABLE Output")
        print("Deze test MEET wat VB-CABLE ontvangt, maar speelt zelf niets af.")
        print("Laat DrostSoundboard geopend en verbonden met de Razer-microfoon.")
        print("Zet Soundboard aan en kies controletoon_12seconden.wav.")
        print("Het geluid wordt niet opgenomen of opgeslagen, alleen de niveaus worden gemeten.\n")
        apparaatcontrole = controleer_werkelijk_aangesloten_audioapparaten(
            logboeken.softwarelogboek
        )
        import sounddevice as audiobibliotheek

        input("Druk op Enter en klik daarna binnen 20 seconden op Geluid afspelen... ")
        huidige_actie = "CABLE Output twintig seconden opnemen en analyseren"
        schrijf_auditgebeurtenis(
            logboeken.auditlogboek,
            "cable_ontvangstmeting_gestart",
            {"testnummer": testnummer, "meetduur_seconden": 20, "audio_bewaren": False},
        )
        resultaat, opnamekant = meet_echt_ontvangen_signaal_van_cable_output(
            audiobibliotheek, apparaatcontrole.apparaten,
        )
        resultaatstekst = (
            "controletoon_ontvangen" if resultaat.is_de_controletoon_echt_ontvangen
            else "alleen_ander_geluid_of_geen_signaal"
        )
        bevindingen = {
            "testnummer": testnummer,
            "resultaat": resultaatstekst,
            "opnameapparaat": opnamekant.naam,
            "aantal_opgenomen_frames": resultaat.aantal_ontvangen_frames,
            "hoogste_rms": round(resultaat.hoogste_effectieve_sterkte, 6),
            "hoogste_piek": round(resultaat.hoogste_piekwaarde, 6),
            "hoogste_controletoonsterkte": round(resultaat.hoogste_sterkte_van_controletoon, 6),
            "blokken_met_controletoon": resultaat.aantal_blokken_met_controletoon,
            "langste_reeks_blokken_met_toon": resultaat.langste_reeks_herkende_toonblokken,
            "bufferproblemen": resultaat.aantal_bufferproblemen,
            "audio_bewaren": False,
        }
        schrijf_auditgebeurtenis(
            logboeken.auditlogboek, "cable_ontvangstmeting_afgerond", bevindingen,
        )
        logboeken.softwarelogboek.info(
            "De ontvangstmeting is afgerond",
            extra={"gebeurtenis": "cable_ontvangstmeting_afgerond", "gegevens": bevindingen},
        )
        print("\nUitslag van de onafhankelijke CABLE Output-meting:")
        print(f"  Opnameapparaat:        {opnamekant.naam}")
        print(f"  Hoogste RMS:           {resultaat.hoogste_effectieve_sterkte:.5f}")
        print(f"  Hoogste piek:          {resultaat.hoogste_piekwaarde:.5f}")
        print(f"  Herkende 660 Hz-toon:  {'JA' if resultaat.is_de_controletoon_echt_ontvangen else 'NEE'}")
        print(f"  Blokken met toon:      {resultaat.aantal_blokken_met_controletoon}")
        print(f"  Langste toonreeks:     {resultaat.langste_reeks_herkende_toonblokken}")
        print(f"  Bufferproblemen:       {resultaat.aantal_bufferproblemen}")
        print(f"  Logmap:                {logboeken.map_met_logbestanden}")
        if resultaat.is_de_controletoon_echt_ontvangen:
            print("\nGESLAAGD: CABLE Output ontvangt de controletoon van het soundboard.")
            print("Als een belapp dit niet laat horen, moeten we die app afzonderlijk controleren.")
            return 0
        if resultaat.hoogste_effectieve_sterkte >= 0.003:
            print("\nER IS GELUID: CABLE Output ontvangt een signaal, maar geen duidelijke 660 Hz-toon.")
            print("Controleer of de nieuwe controletoon is gekozen en tijdens de meting is afgespeeld.")
            return 2
        print("\nGEEN BRUIKBAAR SIGNAAL: er kwam vrijwel niets aan bij CABLE Output.")
        print("Controleer of de live-mixer verbonden is en de WAV werkelijk wordt gestart.")
        return 3
    except (EOFError, KeyboardInterrupt):
        print("\nDe test is afgebroken zonder conclusies.")
        schrijf_auditgebeurtenis(logboeken.auditlogboek, "cable_ontvangstmeting_afgebroken", {
            "testnummer": testnummer,
        })
        return 130
    except Exception as oorspronkelijke_fout:
        logboeken.softwarelogboek.exception(
            "CABLE Output meten is mislukt",
            extra={"gebeurtenis": "cable_ontvangstmeting_mislukt", "gegevens": {
                "foutcode": "ONTVANGST-999",
                "testnummer": testnummer,
                "actie_bij_fout": huidige_actie,
                "fouttype": type(oorspronkelijke_fout).__name__,
            }},
        )
        schrijf_auditgebeurtenis(
            logboeken.auditlogboek, "cable_ontvangstmeting_mislukt",
            {"testnummer": testnummer, "fouttype": type(oorspronkelijke_fout).__name__},
        )
        print(f"\nFOUT tijdens '{huidige_actie}': {oorspronkelijke_fout}")
        print("De oorspronkelijke traceback staat in software.jsonl.")
        return 1
    finally:
        sluit_logboeken_netjes_af(logboeken)


if __name__ == "__main__":
    sys.exit(controleer_wat_cable_output_daadwerkelijk_ontvangt())
