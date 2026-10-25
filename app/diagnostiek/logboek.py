"""Zorg dat diagnosegegevens vanaf de start van het programma bewaard blijven.

We zetten deze module los van de audiomotor, omdat informatie over een fout
beschikbaar moet blijven, zelfs wanneer een audiomodule niet meer kan starten.
"""

from __future__ import annotations

import faulthandler
import json
import logging
from logging.handlers import TimedRotatingFileHandler
import os
from pathlib import Path
import sys
import threading
from dataclasses import dataclass
from datetime import datetime, timezone
from types import TracebackType
from typing import Any
from uuid import uuid4


VERSIE_VAN_DE_APP = "6.0.0-beta.1"


@dataclass(frozen=True)
class BeschikbareLogboeken:
    """Bewaar de loggers en map als één duidelijk geheel."""

    softwarelogboek: logging.Logger
    auditlogboek: logging.Logger
    map_met_logbestanden: Path
    sessie_id: str


class NederlandseJsonLogregel(logging.Formatter):
    """Maak van iedere logregel één leesbaar JSON-object.

    Met één JSON-object per regel kunnen we later op foutcode, tijdstip en
    sessie filteren zonder dat de volledige traceback verloren gaat.
    """

    def __init__(self, sessie_id: str) -> None:
        super().__init__()
        self.sessie_id = sessie_id

    def format(self, logregel: logging.LogRecord) -> str:
        gegevens = getattr(logregel, "gegevens", {})
        if not isinstance(gegevens, dict):
            gegevens = {"ongeldige_extra_gegevens_van_type": type(gegevens).__name__}

        uitzondering = logregel.exc_info[1] if logregel.exc_info else None
        volledige_traceback = (
            self.formatException(logregel.exc_info) if logregel.exc_info else None
        )

        loggegevens: dict[str, Any] = {
            "tijd_utc": datetime.fromtimestamp(logregel.created, timezone.utc).isoformat(),
            "niveau": logregel.levelname,
            "sessie_id": self.sessie_id,
            "gebeurtenis": getattr(logregel, "gebeurtenis", "softwaremelding"),
            "component": logregel.name,
            "functie": logregel.funcName,
            "bestandsnaam": logregel.filename,
            "regelnummer": logregel.lineno,
            "proces_id": logregel.process,
            "draadnaam": logregel.threadName,
            "appversie": VERSIE_VAN_DE_APP,
            "bericht": logregel.getMessage(),
            "foutcode": gegevens.get("foutcode"),
            "fouttype": type(uitzondering).__name__ if uitzondering else None,
            "foutmelding": str(uitzondering) if uitzondering else None,
            "traceback": volledige_traceback,
            "gegevens": gegevens,
        }
        return json.dumps(loggegevens, ensure_ascii=False, default=str)


def bepaal_logmap_voor_deze_computer() -> Path:
    """Sla gebruikersbestanden niet op onder Program Files.

    Een normaal Windows-account heeft daar geen schrijfrechten. LOCALAPPDATA
    blijft bovendien beschikbaar als de definitieve app geïnstalleerd is.
    """
    windows_appgegevens = os.environ.get("LOCALAPPDATA")
    if windows_appgegevens:
        return Path(windows_appgegevens) / "DrostSoundboard" / "logboeken"

    # Dit pad is alleen een bruikbare uitwijkmogelijkheid bij ontwikkeling
    # buiten Windows. De uiteindelijke release richt zich op Windows.
    return Path.home() / ".drostsoundboard" / "logboeken"


def _maak_nieuwe_bestandslogger(
    loggernaam: str,
    bestandsnaam: str,
    logmap: Path,
    sessie_id: str,
) -> logging.Logger:
    logger = logging.getLogger(loggernaam)
    logger.setLevel(logging.INFO)
    logger.propagate = False

    # Tijdens tests of een herstart in hetzelfde proces willen we niet
    # dezelfde logregel twee keer opslaan via oude handlers.
    for bestaande_handler in logger.handlers[:]:
        logger.removeHandler(bestaande_handler)
        bestaande_handler.close()

    handler = TimedRotatingFileHandler(
        filename=logmap / bestandsnaam,
        when="midnight",
        interval=1,
        backupCount=14,
        utc=True,
        encoding="utf-8",
    )
    handler.setFormatter(NederlandseJsonLogregel(sessie_id=sessie_id))
    logger.addHandler(handler)
    return logger


def maak_logboeken_klaar(logmap: Path | None = None) -> BeschikbareLogboeken:
    """Open alle logbestanden voordat we afhankelijkheden laden.

    De bewaartermijn van veertien geroteerde bestanden geldt alleen voor de
    starter. De latere app krijgt apart instelbare termijnen voor audit en
    technische logs en limieten om onbeperkte groei te voorkomen.
    """
    gekozen_logmap = logmap if logmap is not None else bepaal_logmap_voor_deze_computer()
    gekozen_logmap.mkdir(parents=True, exist_ok=True)
    nieuwe_sessie_id = str(uuid4())

    softwarelogboek = _maak_nieuwe_bestandslogger(
        "drostsoundboard.software", "software.jsonl", gekozen_logmap, nieuwe_sessie_id
    )
    auditlogboek = _maak_nieuwe_bestandslogger(
        "drostsoundboard.audit", "audit.jsonl", gekozen_logmap, nieuwe_sessie_id
    )
    _schakel_crashregistratie_in(gekozen_logmap, softwarelogboek)

    return BeschikbareLogboeken(
        softwarelogboek=softwarelogboek,
        auditlogboek=auditlogboek,
        map_met_logbestanden=gekozen_logmap,
        sessie_id=nieuwe_sessie_id,
    )


_bestand_voor_crashes = None


def _schakel_crashregistratie_in(
    gekozen_logmap: Path, softwarelogboek: logging.Logger
) -> None:
    """Bewaar ook informatie over sommige fatale fouten buiten gewone logging.

    Dit is geen garantie voor gegevensbehoud bij een harde pc-reset of een
    volledig vastgelopen proces. Daarom blijft ook de gewone logger nodig.
    """
    global _bestand_voor_crashes

    try:
        if _bestand_voor_crashes is not None:
            faulthandler.disable()
            _bestand_voor_crashes.close()

        _bestand_voor_crashes = (gekozen_logmap / "crashes.txt").open(
            "a", encoding="utf-8"
        )
        faulthandler.enable(file=_bestand_voor_crashes, all_threads=True)
    except (OSError, RuntimeError) as oorspronkelijke_fout:
        softwarelogboek.exception(
            "De extra crashregistratie kon niet worden ingeschakeld",
            extra={
                "gebeurtenis": "crashregistratie_mislukt",
                "gegevens": {"foutcode": "LOG-002", "soort_fout": type(oorspronkelijke_fout).__name__},
            },
        )


def schrijf_auditgebeurtenis(
    auditlogboek: logging.Logger,
    naam_van_de_gebeurtenis: str,
    aanvullende_gegevens: dict[str, Any] | None = None,
) -> None:
    """Registreer een gebruikersactie of controle apart van technische fouten."""
    auditlogboek.info(
        "Auditgebeurtenis: %s",
        naam_van_de_gebeurtenis,
        extra={
            "gebeurtenis": naam_van_de_gebeurtenis,
            "gegevens": aanvullende_gegevens or {},
        },
    )


def leg_onverwachte_hoofdfout_vast(
    soort_fout: type[BaseException],
    fout: BaseException,
    traceback_van_de_fout: TracebackType | None,
) -> None:
    """Verwerk onverwachte hoofdfouten zonder hun traceback kwijt te raken."""
    logboek = logging.getLogger("drostsoundboard.software")
    if logboek.handlers:
        logboek.error(
            "Er ontstond een onverwachte fout buiten de normale foutafhandeling",
            exc_info=(soort_fout, fout, traceback_van_de_fout),
            extra={
                "gebeurtenis": "onafgehandelde_hoofdfout",
                "gegevens": {"foutcode": "APP-999"},
            },
        )
    else:
        sys.__excepthook__(soort_fout, fout, traceback_van_de_fout)


def leg_onverwachte_draadfout_vast(gegevens: threading.ExceptHookArgs) -> None:
    """Leg fouten uit achtergrondthreads vast, want die zijn anders snel onzichtbaar."""
    logboek = logging.getLogger("drostsoundboard.software")
    if logboek.handlers:
        logboek.error(
            "Achtergrondthread is onverwacht gestopt",
            exc_info=(gegevens.exc_type, gegevens.exc_value, gegevens.exc_traceback),
            extra={
                "gebeurtenis": "onafgehandelde_draadfout",
                "gegevens": {
                    "foutcode": "APP-998",
                    "draadnaam": getattr(gegevens.thread, "name", "onbekend"),
                },
            },
        )
    else:
        threading.__excepthook__(gegevens)



def sluit_logboeken_netjes_af(logboeken: BeschikbareLogboeken) -> None:
    """Maak bestanden vrij zodat Windows ze na afsluiten kan verplaatsen of wissen.

    Dit is vooral belangrijk voor rotatie, unit-tests met tijdelijke mappen
    en latere installerupdates. Windows laat open logbestanden vaak niet wissen.
    """
    global _bestand_voor_crashes

    for logger in (logboeken.softwarelogboek, logboeken.auditlogboek):
        for handler in logger.handlers[:]:
            logger.removeHandler(handler)
            handler.flush()
            handler.close()

    if _bestand_voor_crashes is not None:
        faulthandler.disable()
        _bestand_voor_crashes.close()
        _bestand_voor_crashes = None


def zet_uitgebreide_foutafhandeling_aan() -> None:
    """Registreer ook fouten die geen gewone try/except hebben geraakt."""
    sys.excepthook = leg_onverwachte_hoofdfout_vast
    threading.excepthook = leg_onverwachte_draadfout_vast
