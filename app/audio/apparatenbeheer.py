"""Zoek de audioapparaten van Windows zonder al geluid af te spelen.

Fase 0 is bewust alleen een inventarisatie. Daardoor kunnen we eerst zien hoe
Windows de fysieke microfoons en VB-CABLE noemt voordat we ze openen.
"""

from __future__ import annotations

import logging
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class GevondenAudioapparaat:
    """Een gecontroleerd overzicht van één gevonden Windows-audioapparaat."""

    huidig_apparaatnummer: int
    naam: str
    api_naam: str
    aantal_invoerkanalen: int
    aantal_uitvoerkanalen: int


@dataclass(frozen=True)
class ResultaatVanApparaatcontrole:
    """Houd aanwezigheid en aantallen bij elkaar voor scherm en auditlog."""

    apparaten: list[GevondenAudioapparaat]
    cable_input_aanwezig: bool
    cable_output_aanwezig: bool
    fysieke_microfoon_mogelijk_aanwezig: bool


def _lees_kanaalaantal_of_nul(
    apparaatgegevens: Mapping[str, Any], naam_van_veld: str, apparaatnummer: int
) -> int:
    opgegeven_waarde = apparaatgegevens.get(naam_van_veld)
    if type(opgegeven_waarde) is not int or opgegeven_waarde < 0:
        # Een vreemde of ontbrekende apparaatwaarde mag nooit automatisch als
        # een bruikbare audio-ingang gelden. We weigeren die interpretatie.
        raise ValueError(
            f"APPARAAT-002: apparaat {apparaatnummer}, veld {naam_van_veld}: "
            f"verwacht een geheel getal vanaf 0, ontvangen "
            f"{type(opgegeven_waarde).__name__}."
        )
    return opgegeven_waarde


def maak_veilig_overzicht_van_audioapparaten(
    gevonden_apparaatgegevens: Sequence[Mapping[str, Any] | None],
    gevonden_hostapis: Sequence[Mapping[str, Any] | None],
    softwarelogboek: logging.Logger,
) -> ResultaatVanApparaatcontrole:
    """Controleer drivergegevens voordat we er later apparaten mee openen.

    Bij afwijkende gegevens slaan we één onbruikbaar apparaat over met een
    volledige foutmelding. De overige apparaten blijven daardoor zichtbaar.
    """
    overzicht: list[GevondenAudioapparaat] = []

    for apparaatnummer, apparaatgegevens in enumerate(gevonden_apparaatgegevens):
        try:
            if not isinstance(apparaatgegevens, Mapping):
                raise TypeError(
                    "APPARAAT-001: apparaat "
                    f"{apparaatnummer}: verwacht apparaatgegevens als object, "
                    f"ontvangen {type(apparaatgegevens).__name__}."
                )

            naam_van_apparaat = apparaatgegevens.get("name")
            if not isinstance(naam_van_apparaat, str) or not naam_van_apparaat.strip():
                raise ValueError(
                    f"APPARAAT-003: apparaat {apparaatnummer}: ontbrekende of lege naam, "
                    f"ontvangen {type(naam_van_apparaat).__name__}."
                )

            nummer_van_hostapi = apparaatgegevens.get("hostapi")
            if type(nummer_van_hostapi) is not int or not (
                0 <= nummer_van_hostapi < len(gevonden_hostapis)
            ):
                raise ValueError(
                    f"APPARAAT-004: apparaat {apparaatnummer}: ongeldig hostapi-nummer "
                    f"van type {type(nummer_van_hostapi).__name__}."
                )

            gegevens_van_hostapi = gevonden_hostapis[nummer_van_hostapi]
            if not isinstance(gegevens_van_hostapi, Mapping):
                raise TypeError(
                    f"APPARAAT-005: hostapi {nummer_van_hostapi} bevat geen object."
                )

            overzicht.append(
                GevondenAudioapparaat(
                    huidig_apparaatnummer=apparaatnummer,
                    naam=naam_van_apparaat.strip(),
                    api_naam=str(gegevens_van_hostapi.get("name", "Onbekende audio-API")),
                    aantal_invoerkanalen=_lees_kanaalaantal_of_nul(
                        apparaatgegevens, "max_input_channels", apparaatnummer
                    ),
                    aantal_uitvoerkanalen=_lees_kanaalaantal_of_nul(
                        apparaatgegevens, "max_output_channels", apparaatnummer
                    ),
                )
            )

        except (TypeError, ValueError):
            # Zonder traceback en apparaatnummer kunnen we een vreemde
            # driverrespons later niet verklaren. We loggen en gaan door.
            softwarelogboek.exception(
                "Een audioapparaat gaf ongeldige of onvolledige gegevens terug",
                extra={
                    "gebeurtenis": "ongeldige_apparaatgegevens",
                    "gegevens": {
                        "foutcode": "APPARAAT-006",
                        "apparaatnummer": apparaatnummer,
                        "ontvangen_type": type(apparaatgegevens).__name__,
                    },
                },
            )

    # Gebruik de naam plus de richting van het apparaat. Op een Windows-pc
    # kan de VB-CABLE-kant voor afspelen anders zijn dan die voor opnemen.
    cable_input_aanwezig = any(
        "cable input" in apparaat.naam.casefold()
        and apparaat.aantal_uitvoerkanalen > 0
        for apparaat in overzicht
    )
    cable_output_aanwezig = any(
        "cable output" in apparaat.naam.casefold()
        and apparaat.aantal_invoerkanalen > 0
        for apparaat in overzicht
    )
    fysieke_microfoon_mogelijk_aanwezig = any(
        apparaat.api_naam.casefold() == 'windows wasapi'
        and apparaat.aantal_invoerkanalen > 0
        and 'cable' not in apparaat.naam.casefold()
        and 'vb-audio' not in apparaat.naam.casefold()
        for apparaat in overzicht
    )

    return ResultaatVanApparaatcontrole(
        apparaten=overzicht,
        cable_input_aanwezig=cable_input_aanwezig,
        cable_output_aanwezig=cable_output_aanwezig,
        fysieke_microfoon_mogelijk_aanwezig=fysieke_microfoon_mogelijk_aanwezig,
    )


def controleer_werkelijk_aangesloten_audioapparaten(
    softwarelogboek: logging.Logger,
) -> ResultaatVanApparaatcontrole:
    """Vraag actuele apparaten op, zonder te gokken welk nummer we moeten gebruiken."""
    # Pas hier importeren: als de afhankelijkheid ontbreekt, bestaat het
    # softwarelogboek al en bewaren we de exacte ModuleNotFoundError.
    import sounddevice as geluidsapparatenbibliotheek

    gegevens_van_apparaten = geluidsapparatenbibliotheek.query_devices()
    gegevens_van_hostapis = geluidsapparatenbibliotheek.query_hostapis()
    return maak_veilig_overzicht_van_audioapparaten(
        gevonden_apparaatgegevens=gegevens_van_apparaten,
        gevonden_hostapis=gegevens_van_hostapis,
        softwarelogboek=softwarelogboek,
    )
