"""Eenduidige releasekeuze voor AI-modelstemmen.

In een gewone broncodeomgeving blijven legacy-tests van de oude AI-route
mogelijk. Een verpakte RC6 Compact krijgt expliciet ai_stemmen_meeleveren=false.
Vertrouw niet op het toevallig bestaan van een modelbestand voor deze keuze.
"""
from __future__ import annotations
import json
from pathlib import Path
import sys

CONFIGURATIE = Path(__file__).with_name("releasebron.json")


def ai_stemmen_ingeschakeld(configuratie: Path | None = None) -> bool:
    """Is de AI-stemfunctie onderdeel van deze expliciete releasebuild?"""
    pad = Path(configuratie) if configuratie is not None else CONFIGURATIE
    # Bij een beschadigde geïnstalleerde config nooit op AI terugvallen.
    reserve = not bool(getattr(sys, "frozen", False))
    try:
        gegevens = json.loads(pad.read_text(encoding="utf-8-sig"))
    except (OSError, UnicodeError, ValueError, TypeError):
        return reserve
    if not isinstance(gegevens, dict):
        return reserve
    instelling = gegevens.get("ai_stemmen_meeleveren", reserve)
    return instelling if type(instelling) is bool else reserve
