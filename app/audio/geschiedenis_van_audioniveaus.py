"""Bewaar uitsluitend recente geluidsniveaus voor de live meters.

De audiocallback levert bij elk blok gemeten RMS, piek en frameaantal aan.
De webserver leest daarvan een kort venster van 50 ms. Zo verdwijnen korte geluidspieken niet
zomaar tussen twee HTTP-verzoeken, terwijl we geen audiomonsters bewaren.
"""

from __future__ import annotations

from collections import deque
import math
import time


DUUR_VAN_RMS_VENSTER_IN_SECONDEN = 0.05
DUUR_VAN_PIEK_VENSTER_IN_SECONDEN = 0.12
MAXIMALE_AANTAL_RECENTE_METINGEN = 128


class GeschiedenisVanAudioniveaus:
    """Meet een representatieve RMS en de hoogste recente echte samplepiek.

    RMS wordt op basis van het aantal frames gewogen, zodat een audioblok
    van 240 frames niet even zwaar telt als een blok van 960 frames.
    Een deque met vaste lengte voorkomt dat het geheugen blijft groeien.
    50 milliseconden is een bewuste keuze: een langere RMS-meting oogt
    rustiger, maar vertraagt de spraakreactie en maskeert korte klanken.
    De piek wordt 120 ms vastgehouden, apart van de RMS-schaal.
    """

    def __init__(self) -> None:
        self._metingen = deque(maxlen=MAXIMALE_AANTAL_RECENTE_METINGEN)

    def onthoud_gemeten_audioblok(
        self, rms: float, piek: float, aantal_frames: int,
        tijdstip: float | None = None,
    ) -> None:
        """Ontvang lichte, al berekende niveaucijfers vanuit de audiocallback.

        We doen hier geen schijfwerk, audiodirecte conversie of logging, want
        dat zou de realtime geluidsverwerking kunnen ophouden.
        """
        if (
            not math.isfinite(rms) or not math.isfinite(piek)
            or rms < 0 or piek < 0
            or type(aantal_frames) is not int or aantal_frames <= 0
        ):
            raise ValueError("NIVEAU-001: ongeldige geluidsmeting of ongeldig frameaantal.")
        gemeten_op = time.monotonic() if tijdstip is None else tijdstip
        if not math.isfinite(gemeten_op):
            raise ValueError("NIVEAU-002: het meettijdstip is ongeldig.")
        self._metingen.append((gemeten_op, rms, piek, aantal_frames))

    def geef_recente_rms_en_piek(self, tijdstip: float | None = None) -> tuple[float, float]:
        """Bekijk de laatste echte metingen zonder de audiocallback te blokkeren.

        De tuple-kopie van de kleine deque maakt het uitlezen onafhankelijk
        van een volgende append door de werkdraad. Oude pieken verdwijnen
        vanzelf wanneer de microfoon stil wordt of de stream ophoudt.
        """
        nu = time.monotonic() if tijdstip is None else tijdstip
        som_van_kwadraten = 0.0
        aantal_frames = 0
        hoogste_piek = 0.0
        for gemeten_op, rms, piek, frames in tuple(self._metingen):
            verstreken = nu - gemeten_op
            if verstreken < 0:
                continue
            if verstreken <= DUUR_VAN_RMS_VENSTER_IN_SECONDEN:
                som_van_kwadraten += rms * rms * frames
                aantal_frames += frames
            if verstreken <= DUUR_VAN_PIEK_VENSTER_IN_SECONDEN:
                hoogste_piek = max(hoogste_piek, piek)
        gemiddelde_rms = math.sqrt(som_van_kwadraten / aantal_frames) if aantal_frames else 0.0
        return gemiddelde_rms, hoogste_piek
