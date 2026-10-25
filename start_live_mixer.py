"""Open zonder verplichte parameters het fase 2-venster van DrostSoundboard."""

from __future__ import annotations

import platform
import sys

from app.diagnostiek.logboek import (
    maak_logboeken_klaar,
    schrijf_auditgebeurtenis,
    sluit_logboeken_netjes_af,
    zet_uitgebreide_foutafhandeling_aan,
)


def start_de_live_mixer_van_drostsoundboard() -> int:
    """Open logging eerst, zodat ook ontbrekende bibliotheken zichtbaar worden."""
    try:
        logboeken = maak_logboeken_klaar()
    except OSError as fout:
        print(f"LOG-001: logmap kon niet geopend worden: {fout}")
        return 1
    zet_uitgebreide_foutafhandeling_aan()
    try:
        import tkinter as tkinterbibliotheek
        import sounddevice as geluidsapparatenbibliotheek
        from app.vensters.venster_voor_live_mixer import VensterVoorLiveMixer

        logboeken.softwarelogboek.info(
            "Live mixer wordt geopend",
            extra={
                "gebeurtenis": "live_mixer_wordt_geopend",
                "gegevens": {"pythonversie": platform.python_version(), "systeem": platform.platform()},
            },
        )
        schrijf_auditgebeurtenis(logboeken.auditlogboek, "live_venster_gestart")
        venster = tkinterbibliotheek.Tk()
        VensterVoorLiveMixer(venster, logboeken, geluidsapparatenbibliotheek)
        venster.mainloop()
        schrijf_auditgebeurtenis(logboeken.auditlogboek, "live_venster_afgesloten")
        return 0
    except Exception as fout:
        logboeken.softwarelogboek.exception(
            "Het venster voor live audio kon niet worden gebruikt",
            extra={
                "gebeurtenis": "live_venster_mislukt",
                "gegevens": {"foutcode": "LIVEVENSTER-999", "fouttype": type(fout).__name__},
            },
        )
        print(f"LIVEVENSTER-999: {fout}")
        print(f"Volledige traceback: {logboeken.map_met_logbestanden / 'software.jsonl'}")
        return 1
    finally:
        sluit_logboeken_netjes_af(logboeken)


if __name__ == "__main__":
    sys.exit(start_de_live_mixer_van_drostsoundboard())
