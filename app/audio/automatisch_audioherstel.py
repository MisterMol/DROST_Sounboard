"""Herstel een specifiek tijdelijk Windows-driverprobleem bij het verbinden.

We proberen alleen het bekende WdmSyncIoctl-probleem met ongeldige handle
opnieuw. Een verkeerde samplefrequentie, ontbrekende parameter of onbekende
fout mag niet verhuld worden door telkens opnieuw te proberen.
"""

from __future__ import annotations

import logging
import threading
from typing import Any, Callable

from app.diagnostiek.logboek import schrijf_auditgebeurtenis


# De eerste poging is direct. Daarna hooguit vijf nieuwe pogingen. Dit is
# begrensd zodat een defecte audiodriver geen oneindige opstartlus veroorzaakt.
PAUZES_VOOR_HERSTEL_IN_SECONDEN = (0.35, 0.50, 0.80, 1.10, 1.40)
MAXIMALE_STARTPOGINGEN = len(PAUZES_VOOR_HERSTEL_IN_SECONDEN) + 1


class AudioherstelAfgebrokenFout(RuntimeError):
    """Een oude of half geopende stream kon niet veilig worden vrijgegeven."""


def is_het_bekende_tijdelijke_windows_driverprobleem(fout: BaseException) -> bool:
    """Herken uitsluitend het probleem dat daadwerkelijk optrad op de pc.

    De generieke code -9999 kan veel totaal verschillende oorzaken hebben.
    Alleen daarop testen zou programmeerfouten onnodig opnieuw uitvoeren.
    """
    omschrijving = "".join(str(fout).casefold().split())
    return "wdmsyncioctl" in omschrijving and "gle=0x00000006" in omschrijving


def sluit_mislukte_audio_start_netjes_af(audiostroom: Any, softwarelogboek: logging.Logger) -> None:
    """Laat PortAudio los voordat een nieuwe poging met dezelfde kabel start."""
    if audiostroom is None:
        return

    eerste_fout_bij_afsluiten: BaseException | None = None
    acties = []
    if getattr(audiostroom, "active", False):
        acties.append(("stoppen", lambda: audiostroom.stop(ignore_errors=False)))
    acties.append(("sluiten", lambda: audiostroom.close(ignore_errors=False)))

    for naam_van_actie, actie in acties:
        try:
            actie()
        except Exception as fout:
            if eerste_fout_bij_afsluiten is None:
                eerste_fout_bij_afsluiten = fout
            softwarelogboek.exception(
                "Audiostream vrijgeven na mislukte start is mislukt",
                extra={
                    "gebeurtenis": "audio_start_opruimen_mislukt",
                    "gegevens": {
                        "foutcode": "LIVE-021",
                        "mislukte_actie": naam_van_actie,
                        "fouttype": type(fout).__name__,
                    },
                },
            )

    if eerste_fout_bij_afsluiten is not None:
        raise AudioherstelAfgebrokenFout(
            "LIVE-021: de vorige audiostream kon niet worden vrijgegeven. "
            "Er worden daarom geen nieuwe startpogingen gedaan."
        ) from eerste_fout_bij_afsluiten


def open_en_start_de_audiostream_met_herstel(
    audiobibliotheek: Any,
    instellingen_van_stream: dict[str, Any],
    stoppen_gevraagd: threading.Event,
    softwarelogboek: logging.Logger,
    auditlogboek: logging.Logger,
    zet_huidige_poging: Callable[[int], None],
) -> tuple[Any | None, int]:
    """Start de stream en herstel het bekende WDM-probleem maximaal vijf keer.

    Returns:
        (stream, pogingen): de werkende stream en het aantal startpogingen.
        (None, pogingen): de gebruiker heeft tijdens het starten afgebroken.

    Belangrijk: er draait hier nog geen Python-audiocallback als .start() faalt.
    Sluiten voor een volgende poging voorkomt dat oude driverhandles blijven
    bestaan. Iedere herstelbare fout krijgt zijn originele Python-traceback.
    """
    aantal_gedane_pogingen = 0
    for poging in range(1, MAXIMALE_STARTPOGINGEN + 1):
        if stoppen_gevraagd.is_set():
            return None, aantal_gedane_pogingen

        aantal_gedane_pogingen = poging
        zet_huidige_poging(poging)
        audiostroom = None
        try:
            audiostroom = audiobibliotheek.Stream(**instellingen_van_stream)
            if stoppen_gevraagd.is_set():
                sluit_mislukte_audio_start_netjes_af(audiostroom, softwarelogboek)
                return None, poging
            audiostroom.start()
            if stoppen_gevraagd.is_set():
                sluit_mislukte_audio_start_netjes_af(audiostroom, softwarelogboek)
                return None, poging

            if poging > 1:
                softwarelogboek.info(
                    "Audioverbinding hersteld na een tijdelijke Windows-driverfout",
                    extra={
                        "gebeurtenis": "audio_start_automatisch_hersteld",
                        "gegevens": {
                            "aantal_pogingen": poging,
                            "aantal_tijdelijke_fouten": poging - 1,
                            "aanpak": "stream_sluiten_en_opnieuw_starten",
                        },
                    },
                )
                schrijf_auditgebeurtenis(
                    auditlogboek,
                    "audio_start_automatisch_hersteld",
                    {"aantal_pogingen": poging, "aantal_tijdelijke_fouten": poging - 1},
                )
            return audiostroom, poging
        except Exception as oorspronkelijke_fout:
            tijdelijke_driverfout = is_het_bekende_tijdelijke_windows_driverprobleem(
                oorspronkelijke_fout
            )
            # Alleen als de stream veilig is opgeruimd mogen we nog een
            # startpoging doen. Een mislukte close() is een aparte ernstige fout.
            sluit_mislukte_audio_start_netjes_af(audiostroom, softwarelogboek)
            if not tijdelijke_driverfout or poging == MAXIMALE_STARTPOGINGEN:
                raise

            softwarelogboek.warning(
                "Windows-driver weigerde de audiostream tijdelijk; automatisch herstel wordt geprobeerd",
                exc_info=(
                    type(oorspronkelijke_fout),
                    oorspronkelijke_fout,
                    oorspronkelijke_fout.__traceback__,
                ),
                extra={
                    "gebeurtenis": "tijdelijke_audio_startfout",
                    "gegevens": {
                        "foutcode": "LIVE-022",
                        "poging": poging,
                        "maximale_startpogingen": MAXIMALE_STARTPOGINGEN,
                        "volgende_poging": poging + 1,
                        "pauze_in_seconden": PAUZES_VOOR_HERSTEL_IN_SECONDEN[poging - 1],
                        "driverantwoord": str(oorspronkelijke_fout),
                    },
                },
            )
            # Event.wait kan direct stoppen als de gebruiker Verbreken klikt.
            # time.sleep zou het venster onnodig lang in 'Verbinden' laten staan.
            if stoppen_gevraagd.wait(PAUZES_VOOR_HERSTEL_IN_SECONDEN[poging - 1]):
                return None, poging

    # De lus geeft altijd een stream, een afbreekresultaat of een uitzondering.
    raise AssertionError("LIVE-023: onbereikbare toestand van automatisch audioherstel")
