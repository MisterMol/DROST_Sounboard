"""Maak overal dezelfde veilige foutantwoorden voor het lokale webdashboard.

Waarom apart? De HTTP-router hoeft niet zelf te beslissen welke velden bij een
fout horen. Een junior kan hier het antwoordformaat vinden. Behoud de bestaande
velden ``fout``, ``fouttype`` en ``foutcode``: oudere dashboardversies gebruiken
``fout`` nog en mogen niet breken door een serverupdate.

De volledige traceback hoort alleen in software.jsonl, nooit in de browser.
"""

from __future__ import annotations

from dataclasses import dataclass
import re
from uuid import uuid4


FOUTCODE_IN_BERICHT = re.compile(r"^([A-Z][A-Z0-9_]*-\d{3}):")


@dataclass(frozen=True)
class Webfoutantwoord:
    """HTTP-status en JSON-inhoud blijven bij elkaar zodat ze niet verschillen."""

    http_status: int
    inhoud: dict[str, str | None]
    logreferentie: str


def maak_webfoutantwoord(fout: Exception, actie: str) -> Webfoutantwoord:
    """Vertaal een opgevangen fout naar een voorspelbaar, veilig API-antwoord.

    ``ValueError`` betekent doorgaans ongeldige invoer (HTTP 400). Andere
    fouten zijn onverwacht (500). Geef daarvan alleen een neutrale melding
    terug: paden, Python-code en beveiligingsgegevens blijven in de logs.
    """
    gebruikersfout = isinstance(fout, ValueError)
    status = 400 if gebruikersfout else 500
    fouttekst = str(fout)
    herkende_code = FOUTCODE_IN_BERICHT.match(fouttekst)
    referentie = uuid4().hex[:12]
    return Webfoutantwoord(
        http_status=status,
        inhoud={
            "fout": fouttekst if gebruikersfout else "Er ging iets mis. Zie software.jsonl voor de volledige traceback.",
            "fouttype": type(fout).__name__,
            "foutcode": "WEB-400" if gebruikersfout else "WEB-999",
            "oorzaakcode": herkende_code.group(1) if herkende_code else None,
            "referentie": referentie,
            "actie": actie,
        },
        logreferentie=referentie,
    )


def maak_webantwoord_voor_onbekende_route(foutcode: str, bericht: str) -> dict[str, str]:
    """Gebruik één vorm voor 404/429 zonder een niet-bestaande traceback te verzinnen."""
    return {"fout": f"{foutcode}: {bericht}", "foutcode": foutcode, "fouttype": "OngeldigWebverzoek"}
