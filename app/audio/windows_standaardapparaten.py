"""Vind de standaardinvoer of standaarduitvoer via Windows WASAPI.

De PortAudio-host-API geeft de standaardapparaten als apparaatnummers.
Kies nooit een willekeurig apparaat of de virtuele kabel als lokale
headsetmonitor. Deze helper opent zelf geen audiostream.
"""
from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any, Literal


def vind_wasapi_standaardapparaat(
    apparaten: Sequence[Mapping[str, Any]],
    hostapis: Sequence[Mapping[str, Any]],
    richting: Literal['invoer', 'uitvoer'],
) -> tuple[int, str] | None:
    """Geef (apparaatnummer, echte Windows-naam) of None terug.

    De minimale kanaalvereisten zijn gelijk aan de bestaande interface:
    mono invoer is toegestaan; de effectenmonitor gebruikt stereo uitvoer.
    """
    if richting not in ('invoer', 'uitvoer'):
        raise ValueError('STANDAARD-001: onbekende richting voor een audioapparaat.')
    sleutel = ('default_input_device' if richting == 'invoer'
              else 'default_output_device')
    kanaalveld = ('max_input_channels' if richting == 'invoer'
                  else 'max_output_channels')
    minimaal = 1 if richting == 'invoer' else 2

    for hostapi_nummer, api in enumerate(hostapis):
        if not isinstance(api, Mapping) or str(api.get('name', '')).casefold() != 'windows wasapi':
            continue
        nummer = api.get(sleutel, -1)
        if type(nummer) is not int or not 0 <= nummer < len(apparaten):
            continue
        apparaat = apparaten[nummer]
        if not isinstance(apparaat, Mapping) or apparaat.get('hostapi') != hostapi_nummer:
            continue
        kanalen = apparaat.get(kanaalveld, 0)
        if type(kanalen) is not int or kanalen < minimaal:
            continue
        naam = apparaat.get('name')
        if not isinstance(naam, str) or not naam.strip():
            continue
        if 'cable' in naam.casefold() or 'vb-audio' in naam.casefold():
            continue
        return nummer, naam.strip()
    return None
