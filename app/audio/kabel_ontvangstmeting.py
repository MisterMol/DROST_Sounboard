"""Meet onafhankelijk wat er echt bij CABLE Output als opnamebron aankomt.

De live-mixer meet zijn eigen uitvoerbuffer, maar dat is geen bewijs dat
Windows of een belprogramma dezelfde samples ontvangt. Deze module leest
daarom uitsluitend de OPNAMEkant van VB-CABLE. De stem of geluiden worden
niet opgeslagen, ook niet bij een fout. Alleen signaalniveaus en de sterkte
van de herkenbare controletoon komen in de logboeken terecht.

De app gebruikt deze meting tijdelijk tijdens de diagnose. Later kan een
HTML-dashboard dezelfde kleine meetfuncties hergebruiken.
"""

from __future__ import annotations

from dataclasses import dataclass
import math
from typing import Any, Callable

import numpy as np

from app.audio.apparatenbeheer import GevondenAudioapparaat
from app.audio.geluidsbestanden import SAMPLEFREQUENTIE_VAN_DE_UITVOER
from app.audio.kabelcontrole import selecteer_de_twee_uiteinden_van_vb_cable
from app.audio.windows_com_context import houd_com_beschikbaar_tijdens_audioverbinding


CONTROLETOON_IN_HERTZ = 660
DUUR_VAN_DE_OPNAMETEST_IN_SECONDEN = 20
FRAMES_PER_MEETBLOK = 4800
MINIMALE_TOONAMPLITUDE = 0.02
MINIMAAL_AANTAL_BLOKKEN_MET_CONTROLETOON = 3


class CableOntvangstFout(RuntimeError):
    """Een leesbare melding voor een onbruikbare opnamekant of meetresultaat."""


@dataclass(frozen=True)
class SignaalVanEenOpgenomenBlok:
    """Bewaar alleen metingen over een kort blok, nooit de gesproken inhoud."""

    effectieve_sterkte: float
    piekwaarde: float
    sterkte_van_controletoon: float
    controletoon_herkend: bool


@dataclass
class ResultaatVanCableOntvangstmeting:
    """Spreektaalgegevens om een opname onafhankelijk van de mixer te beoordelen."""

    aantal_ontvangen_blokken: int = 0
    aantal_ontvangen_frames: int = 0
    aantal_bufferproblemen: int = 0
    hoogste_effectieve_sterkte: float = 0.0
    hoogste_piekwaarde: float = 0.0
    hoogste_sterkte_van_controletoon: float = 0.0
    aantal_blokken_met_controletoon: int = 0
    huidige_reeks_herkende_toonblokken: int = 0
    langste_reeks_herkende_toonblokken: int = 0

    @property
    def is_de_controletoon_echt_ontvangen(self) -> bool:
        """Een paar opeenvolgende treffers zijn overtuigender dan één ruispiek."""
        return self.langste_reeks_herkende_toonblokken >= MINIMAAL_AANTAL_BLOKKEN_MET_CONTROLETOON

    def voeg_nieuwe_meting_toe(
        self, gemeten_blok: SignaalVanEenOpgenomenBlok, aantal_frames: int, bufferprobleem: bool,
    ) -> None:
        """Tel een meting op zonder ruwe geluidsopnames vast te houden."""
        if type(aantal_frames) is not int or aantal_frames <= 0:
            raise CableOntvangstFout("ONTVANGST-005: aantal_frames moet positief zijn.")
        self.aantal_ontvangen_blokken += 1
        self.aantal_ontvangen_frames += aantal_frames
        self.aantal_bufferproblemen += int(bufferprobleem)
        self.hoogste_effectieve_sterkte = max(
            self.hoogste_effectieve_sterkte, gemeten_blok.effectieve_sterkte,
        )
        self.hoogste_piekwaarde = max(self.hoogste_piekwaarde, gemeten_blok.piekwaarde)
        self.hoogste_sterkte_van_controletoon = max(
            self.hoogste_sterkte_van_controletoon, gemeten_blok.sterkte_van_controletoon,
        )
        self.aantal_blokken_met_controletoon += int(gemeten_blok.controletoon_herkend)
        self.huidige_reeks_herkende_toonblokken = (
            self.huidige_reeks_herkende_toonblokken + 1
            if gemeten_blok.controletoon_herkend else 0
        )
        self.langste_reeks_herkende_toonblokken = max(
            self.langste_reeks_herkende_toonblokken,
            self.huidige_reeks_herkende_toonblokken,
        )


def meet_signaal_en_herken_controletoon(
    opgenomen_audio: np.ndarray,
    samplefrequentie: int = SAMPLEFREQUENTIE_VAN_DE_UITVOER,
    toonhoogte_in_hertz: int = CONTROLETOON_IN_HERTZ,
) -> SignaalVanEenOpgenomenBlok:
    """Zoek gericht de controletoon in de samples die uit CABLE Output komen.

    We beoordelen de audiokanalen afzonderlijk. Als twee kanalen toevallig
    tegengestelde polariteit hebben, zou eerst middelen alle geluid wegwerken.
    Dat willen we niet ten onrechte als een stille kabel bestempelen.
    """
    if not isinstance(opgenomen_audio, np.ndarray):
        raise CableOntvangstFout(
            "ONTVANGST-001: opgenomen_audio moet een NumPy-array zijn; "
            f"ontvangen {type(opgenomen_audio).__name__}."
        )
    if opgenomen_audio.ndim != 2 or opgenomen_audio.shape[1] not in (1, 2):
        raise CableOntvangstFout(
            "ONTVANGST-002: de opname moet mono of stereo bevatten, "
            f"ontvangen vorm {opgenomen_audio.shape}."
        )
    if len(opgenomen_audio) < 100:
        raise CableOntvangstFout("ONTVANGST-003: audioblok bevat te weinig frames.")
    if not isinstance(samplefrequentie, int) or samplefrequentie <= 0 or not (
        isinstance(toonhoogte_in_hertz, int)
        and 0 < toonhoogte_in_hertz < samplefrequentie / 2
    ):
        raise CableOntvangstFout("ONTVANGST-006: samplefrequentie of toonhoogte is ongeldig.")
    if not np.issubdtype(opgenomen_audio.dtype, np.number):
        raise CableOntvangstFout("ONTVANGST-007: opgenomen_audio bevat geen getallen.")
    if not bool(np.all(np.isfinite(opgenomen_audio))):
        raise CableOntvangstFout("ONTVANGST-004: de audiodriver gaf NaN of oneindige samples terug.")

    samples = opgenomen_audio.astype(np.float64, copy=False)
    effectieve_sterkte_per_kanaal = np.sqrt(np.mean(np.square(samples), axis=0))
    effectieve_sterkte = float(np.max(effectieve_sterkte_per_kanaal))
    piekwaarde = float(np.max(np.abs(samples)))

    sampleposities = np.arange(len(samples), dtype=np.float64)
    hoek_per_sample = 2.0 * math.pi * toonhoogte_in_hertz / samplefrequentie
    referentie_cosinus = np.cos(hoek_per_sample * sampleposities)
    referentie_sinus = np.sin(hoek_per_sample * sampleposities)
    projectie_op_cosinus = np.sum(samples * referentie_cosinus[:, None], axis=0)
    projectie_op_sinus = np.sum(samples * referentie_sinus[:, None], axis=0)
    toonsterkte = float(
        np.max(2 * np.hypot(projectie_op_cosinus, projectie_op_sinus) / len(samples))
    )

    # Een echt toonblok heeft én voldoende niveau én herkenbaar veel energie
    # precies op 660 Hz. Daarmee tellen spraak, ruis of andere tonen niet mee.
    controletoon_herkend = (
        toonsterkte >= MINIMALE_TOONAMPLITUDE
        and toonsterkte >= effectieve_sterkte * 0.50
    )
    return SignaalVanEenOpgenomenBlok(
        effectieve_sterkte=effectieve_sterkte,
        piekwaarde=piekwaarde,
        sterkte_van_controletoon=toonsterkte,
        controletoon_herkend=controletoon_herkend,
    )


def kies_kanaalaantal_voor_opnemen(
    audiobibliotheek: Any, opnamekant: GevondenAudioapparaat,
) -> int:
    """Probeer eerst stereo en dan mono omdat de kabel stereo ontvangt."""
    foutmeldingen: list[str] = []
    for aantal_kanalen in (2, 1):
        if opnamekant.aantal_invoerkanalen < aantal_kanalen:
            continue
        try:
            audiobibliotheek.check_input_settings(
                device=opnamekant.huidig_apparaatnummer,
                channels=aantal_kanalen,
                samplerate=SAMPLEFREQUENTIE_VAN_DE_UITVOER,
                dtype="float32",
            )
            return aantal_kanalen
        except Exception as oorspronkelijke_fout:
            foutmeldingen.append(
                f"{aantal_kanalen} kanaal: {type(oorspronkelijke_fout).__name__} "
                f"({oorspronkelijke_fout})"
            )
    raise CableOntvangstFout(
        "ONTVANGST-008: CABLE Output weigert opnemen op 48 kHz. "
        "Controleer de driver en opname-instellingen. " + "; ".join(foutmeldingen)
    )


def meet_echt_ontvangen_signaal_van_cable_output(
    audiobibliotheek: Any,
    beschikbare_apparaten: list[GevondenAudioapparaat],
    toon_resultaat: Callable[[str], None] = print,
    duur_in_seconden: int = DUUR_VAN_DE_OPNAMETEST_IN_SECONDEN,
) -> tuple[ResultaatVanCableOntvangstmeting, GevondenAudioapparaat]:
    """Lees twintig seconden uitsluitend de opnamekant van dezelfde VB-CABLE.

    We openen GEEN extra stream naar CABLE Input. De live soundboard-app moet
    zelf geluid daarheen sturen. Alleen zo meten we het echte gecombineerde
    resultaat van de lopende microfoon én het WAV-fragment.
    """
    if type(duur_in_seconden) is not int or not 1 <= duur_in_seconden <= 120:
        raise CableOntvangstFout("ONTVANGST-009: de meetduur moet 1 tot 120 seconden zijn.")
    gekozen_kabel = selecteer_de_twee_uiteinden_van_vb_cable(beschikbare_apparaten)
    opnamekant = gekozen_kabel.opnamekant

    meting = ResultaatVanCableOntvangstmeting()
    with houd_com_beschikbaar_tijdens_audioverbinding():
        kanaalaantal = kies_kanaalaantal_voor_opnemen(audiobibliotheek, opnamekant)
        with audiobibliotheek.InputStream(
            device=opnamekant.huidig_apparaatnummer,
            samplerate=SAMPLEFREQUENTIE_VAN_DE_UITVOER,
            channels=kanaalaantal,
            dtype="float32",
            blocksize=0,
            latency="high",
        ) as opname_stream:
            for bloknummer in range(duur_in_seconden * 10):
                opgenomen_audio, bufferprobleem = opname_stream.read(FRAMES_PER_MEETBLOK)
                blokmeting = meet_signaal_en_herken_controletoon(opgenomen_audio)
                meting.voeg_nieuwe_meting_toe(
                    blokmeting, len(opgenomen_audio), bool(bufferprobleem),
                )
                if bloknummer % 10 == 9:
                    toon_resultaat(
                        f"  {(bloknummer + 1) // 10:2d}/{duur_in_seconden:2d} seconden | "
                        f"laatste niveau: {blokmeting.effectieve_sterkte:.5f} RMS | "
                        f"sterkste niveau: {meting.hoogste_effectieve_sterkte:.5f} RMS | "
                        f"toon herkend: {'ja' if meting.is_de_controletoon_echt_ontvangen else 'nog niet'}"
                    )
    return meting, opnamekant
