"""Meet de werkelijke verwerking, los van buffers en geluidskwaliteit.

De normen zijn productkeuzes, geen garantie op een bepaalde audiovertraging.
Dit onderdeel opent geen microfoon en heeft geen modelafhankelijkheden.
"""
from __future__ import annotations
from collections import deque
from datetime import datetime, timezone
import math
import threading

BLOK_MS = 52.0
BUFFERPROFIELEN = {
    'direct': {'naam': 'Direct', 'blokken': 1, 'buffer_ms': 52},
    'gebalanceerd': {'naam': 'Gebalanceerd', 'blokken': 2, 'buffer_ms': 104},
    'stabiel': {'naam': 'Extra buffer', 'blokken': 3, 'buffer_ms': 156},
}


def controleer_profiel(profiel: str) -> str:
    if not isinstance(profiel, str) or profiel not in BUFFERPROFIELEN:
        raise ValueError('Kies Direct, Gebalanceerd of Extra buffer.')
    return profiel


def percentiel(waarden, fractie=0.95):
    """Lineaire interpolatie op een kopie, zodat meetgegevens intact blijven."""
    data = sorted(float(x) for x in waarden)
    if not data:
        return None
    plaats = (len(data) - 1) * fractie
    laag = int(plaats)
    hoog = min(laag + 1, len(data) - 1)
    return data[laag] + (data[hoog] - data[laag]) * (plaats - laag)


def samenvatting(waarden):
    data = tuple(float(x) for x in waarden)
    if any(not math.isfinite(x) or x < 0 for x in data):
        raise ValueError('Ongeldige verwerkingstijd.')
    if not data:
        return {'blokken': 0, 'gemiddeld_ms': None, 'p95_ms': None,
                'maximum_ms': None, 'te_laat': 0, 'budget_procent': None}
    return {'blokken': len(data), 'gemiddeld_ms': round(sum(data)/len(data), 2),
            'p95_ms': round(percentiel(data), 2), 'maximum_ms': round(max(data), 2),
            'te_laat': sum(x > BLOK_MS for x in data),
            'budget_procent': round(100*sum(data)/len(data)/BLOK_MS, 1)}


def beoordeel(waarden, modelwaarden, *, niet_stil: bool, model_sha: str):
    tijden, motor = tuple(waarden), tuple(modelwaarden)
    if len(tijden) != len(motor) or len(tijden) < 24:
        raise ValueError('Onvoldoende meetblokken voor een processortest.')
    s, m = samenvatting(tijden), samenvatting(motor)
    # Beoordeel ongeronde getallen: afronden mag de uitslag niet veranderen.
    snel = sum(tijden)/len(tijden) < BLOK_MS*.70 and percentiel(tijden) < BLOK_MS*.95
    geslaagd = bool(snel and niet_stil)
    return {'schema': 1, 'tijd_utc': datetime.now(timezone.utc).isoformat(timespec='seconds'),
            'model_sha256': model_sha, 'uitvoering': 'processor', 'blok_ms': BLOK_MS,
            'inclusief_procescommunicatie': True, 'meting': s, 'modelmeting': m,
            'grens_gemiddeld_ms': BLOK_MS*.70, 'grens_p95_ms': BLOK_MS*.95,
            'niet_stil': bool(niet_stil), 'geslaagd': geslaagd,
            'oordeel': 'voldoende' if geslaagd else 'te_langzaam' if not snel else 'geen_audio',
            'geluidskwaliteit_getest': False, 'totale_audiovertraging_ms': None,
            'uitleg': 'Lokale test met kunstmatige audio. Geen microfoonopname, luistertest of totale audiovertraging gemeten.'}


class Meetvenster:
    """Een begrensde recente meting; nooit groeiende lijsten tijdens een gesprek."""
    def __init__(self, lengte=120):
        self._lock = threading.Lock()
        self._waarden = deque(maxlen=lengte)

    def voeg_toe(self, milliseconden):
        if not math.isfinite(milliseconden) or milliseconden < 0:
            raise ValueError('Ongeldige verwerkingstijd.')
        with self._lock:
            self._waarden.append(float(milliseconden))

    def wis(self):
        with self._lock:
            self._waarden.clear()

    def status(self):
        with self._lock:
            kopie = tuple(self._waarden)
        return samenvatting(kopie)
