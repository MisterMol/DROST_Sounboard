"""Open zonder argumenten een klein testvenster om WAV naar VB-CABLE af te spelen."""

from __future__ import annotations

import platform
import sys

from app.diagnostiek.logboek import (
    maak_logboeken_klaar,
    schrijf_auditgebeurtenis,
    sluit_logboeken_netjes_af,
    zet_uitgebreide_foutafhandeling_aan,
)


def open_het_venster_om_een_eigen_wav_te_testen() -> int:
    """Open eerst logging, daarna pas Tk en de benodigde audiodrivers."""
    try:
        logboeken = maak_logboeken_klaar()
    except OSError as fout_bij_openen_van_de_logmap:
        print(f"LOG-001: logbestanden konden niet worden geopend: {fout_bij_openen_van_de_logmap}")
        return 1

    zet_uitgebreide_foutafhandeling_aan()
    logboeken.softwarelogboek.info(
        "Geluidstest wordt geopend",
        extra={
            "gebeurtenis": "wav_testvenster_wordt_geopend",
            "gegevens": {"pythonversie": platform.python_version(), "systeem": platform.platform()},
        },
    )
    schrijf_auditgebeurtenis(logboeken.auditlogboek, "wav_testvenster_gestart")
    try:
        import tkinter as tkinterbibliotheek
        from app.vensters.venster_voor_geluidstest import VensterVoorWavGeluidstest

        venster = tkinterbibliotheek.Tk()
        VensterVoorWavGeluidstest(venster, tkinterbibliotheek, logboeken)
        venster.mainloop()
        schrijf_auditgebeurtenis(logboeken.auditlogboek, "wav_testvenster_gesloten")
        return 0
    except Exception as oorspronkelijke_fout:
        logboeken.softwarelogboek.exception(
            "Het WAV-testvenster kon niet geopend of uitgevoerd worden",
            extra={
                "gebeurtenis": "wav_testvenster_mislukt",
                "gegevens": {
                    "foutcode": "VENSTER-001",
                    "actie_bij_fout": "openen of afhandelen van het testvenster",
                    "type_van_fout": type(oorspronkelijke_fout).__name__,
                },
            },
        )
        print(f"VENSTER-001: Kan WAV-testvenster niet uitvoeren: {oorspronkelijke_fout}")
        print(f"Meer informatie: {logboeken.map_met_logbestanden / 'software.jsonl'}")
        return 1
    finally:
        sluit_logboeken_netjes_af(logboeken)


if __name__ == "__main__":
    sys.exit(open_het_venster_om_een_eigen_wav_te_testen())
