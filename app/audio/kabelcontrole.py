"""Meet of een testtoon via VB-CABLE van afspelen naar opnemen gaat.

Deze module opent GEEN fysieke microfoon en verandert geen Windows-standaarden.
Hij kijkt eerst welke apparaten nú aanwezig zijn, opent daarna uitsluitend
CABLE Output om te meten en CABLE Input om de testtoon af te spelen.
"""

from __future__ import annotations

import logging
import math
import struct
import threading
import time
from uuid import uuid4
from dataclasses import dataclass
from typing import Any

from app.audio.apparatenbeheer import GevondenAudioapparaat
from app.audio.signaalherkenning import HerkennerVoorEenVasteToon
from app.audio.testtoon import (
    InstellingenVoorTesttoon,
    maak_testtoon_voor_de_virtuele_kabel,
    verdeel_testtoon_in_kleine_audio_blokken,
)
from app.diagnostiek.logboek import schrijf_auditgebeurtenis


class KabelcontroleFout(RuntimeError):
    """Geef een heldere foutcode aan de gebruikersinterface en de logs."""


@dataclass(frozen=True)
class GeselecteerdeKabelapparaten:
    """De twee uiteinden van één VB-CABLE, op het moment van de test."""

    afspeelkant: GevondenAudioapparaat
    opnamekant: GevondenAudioapparaat


@dataclass(frozen=True)
class MeetresultaatVanKabeltest:
    """Bevat alleen niveaus, geen opgenomen gesprekken of audio-inhoud."""

    is_gelukt: bool
    aantal_opgenomen_frames: int
    hoogste_samplewaarde: float
    gemiddelde_effectieve_samplewaarde: float
    herkende_toonssterkte: float
    aantal_waargenomen_bufferproblemen: int
    aantal_verstuurde_frames: int
    speelduur_van_testtoon_in_seconden: float


def selecteer_de_twee_uiteinden_van_vb_cable(
    beschikbare_apparaten: list[GevondenAudioapparaat],
) -> GeselecteerdeKabelapparaten:
    """Gebruik namen en WASAPI in plaats van nummers die later kunnen veranderen.

    Bij meerdere identieke kandidaten stoppen we liever dan dat we geluid
    naar de verkeerde kabel sturen. CABLE In 16ch is hier bewust uitgesloten.
    """
    if not isinstance(beschikbare_apparaten, list):
        raise TypeError(
            "KABEL-001: beschikbare_apparaten moet een lijst zijn; "
            f"ontvangen: {type(beschikbare_apparaten).__name__}."
        )

    afspeelkandidaten = [
        apparaat
        for apparaat in beschikbare_apparaten
        if apparaat.api_naam.casefold() == "windows wasapi"
        and apparaat.naam.casefold().startswith("cable input (")
        and "vb-audio virtual cable" in apparaat.naam.casefold()
        and apparaat.aantal_uitvoerkanalen >= 2
    ]
    opnamekandidaten = [
        apparaat
        for apparaat in beschikbare_apparaten
        if apparaat.api_naam.casefold() == "windows wasapi"
        and apparaat.naam.casefold().startswith("cable output (")
        and "vb-audio virtual cable" in apparaat.naam.casefold()
        and apparaat.aantal_invoerkanalen >= 2
    ]

    if len(afspeelkandidaten) != 1 or len(opnamekandidaten) != 1:
        raise KabelcontroleFout(
            "KABEL-002: er moet precies één gewone VB-CABLE Input en één "
            "VB-CABLE Output via Windows WASAPI zijn. "
            f"Gevonden: {len(afspeelkandidaten)} afspeelapparaten en "
            f"{len(opnamekandidaten)} opnameapparaten. "
            "Bekijk de apparaatcontrole en software.jsonl."
        )

    return GeselecteerdeKabelapparaten(
        afspeelkant=afspeelkandidaten[0],
        opnamekant=opnamekandidaten[0],
    )


def bereken_signaalsterkte_van_ruwe_audio(
    ruwe_audio: bytes,
) -> tuple[int, float, float]:
    """Geef samples, hoogste absolute waarde en som van kwadraten terug.

    Zo kan een samenvatting worden bewaard zonder het geluid zelf op schijf
    te zetten. De functie is bewust los te testen, zonder audioapparaten.
    """
    if len(ruwe_audio) % 4:
        raise ValueError("KABEL-003: audio bevat een onvolledige float32-sample.")

    hoogste_waarde = 0.0
    som_van_kwadraten = 0.0
    aantal_samples = 0

    for (samplewaarde,) in struct.iter_unpack("<f", ruwe_audio):
        if not math.isfinite(samplewaarde):
            raise ValueError("KABEL-004: audio bevat een oneindige of NaN-samplewaarde.")
        hoogste_waarde = max(hoogste_waarde, abs(samplewaarde))
        som_van_kwadraten += samplewaarde * samplewaarde
        aantal_samples += 1

    return aantal_samples, hoogste_waarde, som_van_kwadraten


def _neem_tijdelijk_audio_op_uit_de_virtuele_kabel(
    audiobibliotheek: Any,
    opnameapparaat: GevondenAudioapparaat,
    testinstellingen: InstellingenVoorTesttoon,
    opname_is_gestart: threading.Event,
    opname_resultaat: dict[str, Any],
) -> None:
    """Lees kort de virtuele kabel en gooi ruwe samples direct weer weg.

    Deze functie loopt in een aparte draad. Zo loopt het schrijven naar de
    kabel door terwijl we aan de andere kant kijken of het signaal aankomt.
    """
    try:
        aantal_frames = 0
        aantal_samples = 0
        hoogste_waarde = 0.0
        som_van_kwadraten = 0.0
        aantal_bufferproblemen = 0
        totaal_te_meten_frames = round(testinstellingen.samplefrequentie * 3.2)
        herkenner = HerkennerVoorEenVasteToon(
            samplefrequentie=testinstellingen.samplefrequentie,
            toonhoogte_in_hertz=testinstellingen.toonhoogte_in_hertz,
        )

        with audiobibliotheek.RawInputStream(
            samplerate=testinstellingen.samplefrequentie,
            device=opnameapparaat.huidig_apparaatnummer,
            channels=testinstellingen.aantal_kanalen,
            dtype="float32",
            latency="high",
        ) as opname_stream:
            opname_is_gestart.set()
            while aantal_frames < totaal_te_meten_frames:
                frames_voor_dit_blok = min(
                    1024, totaal_te_meten_frames - aantal_frames
                )
                ruwe_audio, is_buffer_overgelopen = opname_stream.read(
                    frames_voor_dit_blok
                )
                if is_buffer_overgelopen:
                    aantal_bufferproblemen += 1

                gelezen_audioblok = bytes(ruwe_audio)
                aantal_samples_in_blok, blok_piek, blok_som = (
                    bereken_signaalsterkte_van_ruwe_audio(gelezen_audioblok)
                )
                herkenner.verwerk_nieuw_audioblok(gelezen_audioblok)
                verwachte_samples = frames_voor_dit_blok * testinstellingen.aantal_kanalen
                if aantal_samples_in_blok != verwachte_samples:
                    raise KabelcontroleFout(
                        "KABEL-005: het aantal opgenomen samples komt niet overeen. "
                        f"Verwacht {verwachte_samples}, ontvangen {aantal_samples_in_blok}."
                    )

                aantal_frames += frames_voor_dit_blok
                aantal_samples += aantal_samples_in_blok
                hoogste_waarde = max(hoogste_waarde, blok_piek)
                som_van_kwadraten += blok_som

        opname_resultaat.update(
            {
                "aantal_opgenomen_frames": aantal_frames,
                "aantal_samples": aantal_samples,
                "hoogste_waarde": hoogste_waarde,
                "som_van_kwadraten": som_van_kwadraten,
                "aantal_bufferproblemen": aantal_bufferproblemen,
                "herkende_toonssterkte": herkenner.bereken_sterkte_van_de_herkende_toon(),
            }
        )
    except Exception as oorspronkelijke_fout:
        # Bewaar het exception-object inclusief de oorspronkelijke traceback.
        # De hoofdthread maakt er later één volledige softwarefout van.
        opname_resultaat["fout"] = oorspronkelijke_fout
    finally:
        opname_is_gestart.set()


def voer_korte_test_van_de_virtuele_kabel_uit(
    audiobibliotheek: Any,
    geselecteerde_apparaten: GeselecteerdeKabelapparaten,
    softwarelogboek: logging.Logger,
    auditlogboek: logging.Logger,
    testinstellingen: InstellingenVoorTesttoon | None = None,
) -> MeetresultaatVanKabeltest:
    """Speel de toon, meet de kabel en leg beide kanten vast in de logboeken.

    Het enige geluidsbestand is een zelfgemaakte toon in het geheugen. We
    openen niet je Razer-microfoon en schrijven geen WAV-opname naar schijf.
    """
    instellingen = testinstellingen or InstellingenVoorTesttoon()
    testtoon_als_bytes = maak_testtoon_voor_de_virtuele_kabel(instellingen)
    totaal_aantal_uitvoerframes = len(testtoon_als_bytes) // (
        4 * instellingen.aantal_kanalen
    )

    # Foutmelding vóór open() voorkomt een halve test als een driver dit
    # audiotype weigert. Exclusive is uit: andere apps blijven bruikbaar.
    audiobibliotheek.check_output_settings(
        device=geselecteerde_apparaten.afspeelkant.huidig_apparaatnummer,
        channels=instellingen.aantal_kanalen,
        dtype="float32",
        samplerate=instellingen.samplefrequentie,
    )
    audiobibliotheek.check_input_settings(
        device=geselecteerde_apparaten.opnamekant.huidig_apparaatnummer,
        channels=instellingen.aantal_kanalen,
        dtype="float32",
        samplerate=instellingen.samplefrequentie,
    )

    gegevens_voor_opname: dict[str, Any] = {}
    signaal_opname_begonnen = threading.Event()
    opnamedraad = threading.Thread(
        target=_neem_tijdelijk_audio_op_uit_de_virtuele_kabel,
        args=(
            audiobibliotheek,
            geselecteerde_apparaten.opnamekant,
            instellingen,
            signaal_opname_begonnen,
            gegevens_voor_opname,
        ),
        name="VB-CABLE-meetdraad",
        daemon=True,
    )
    opnamedraad.start()

    if not signaal_opname_begonnen.wait(timeout=5):
        raise KabelcontroleFout(
            "KABEL-006: CABLE Output kon niet binnen vijf seconden geopend worden."
        )
    if "fout" in gegevens_voor_opname:
        raise KabelcontroleFout(
            "KABEL-007: CABLE Output kon niet worden opgenomen."
        ) from gegevens_voor_opname["fout"]

    # De opname loopt al. We wachten kort om ook het begin van het signaal
    # mee te pakken wanneer Windows eerst buffers moet voorbereiden.
    time.sleep(0.2)
    opname_uitvoer_onderlopen = 0
    afspeelbeurt_id = str(uuid4())
    gestarte_afspeelbeurt = False
    afspeel_starttijd = 0.0
    aantal_verstuurde_frames = 0

    try:
        with audiobibliotheek.RawOutputStream(
            samplerate=instellingen.samplefrequentie,
            device=geselecteerde_apparaten.afspeelkant.huidig_apparaatnummer,
            channels=instellingen.aantal_kanalen,
            dtype="float32",
            latency="high",
        ) as afspeel_stream:
            afspeel_starttijd = time.perf_counter()
            gestarte_afspeelbeurt = True
            schrijf_auditgebeurtenis(
                auditlogboek,
                "geluid_gestart",
                {
                    "geluid_id": "ingebouwde_testtoon_440hz",
                    "afspeelbeurt_id": afspeelbeurt_id,
                    "naam": "Kabeltest, toon van 440 hertz",
                    "uitvoerapparaat": geselecteerde_apparaten.afspeelkant.naam,
                    "volume": instellingen.volume,
                    "beoogde_duur_seconden": instellingen.duur_in_seconden,
                },
            )

            for audioblok in verdeel_testtoon_in_kleine_audio_blokken(
                testtoon_als_bytes, instellingen.aantal_kanalen
            ):
                is_buffer_ondergelopen = afspeel_stream.write(audioblok)
                aantal_verstuurde_frames += len(audioblok) // (
                    4 * instellingen.aantal_kanalen
                )
                if is_buffer_ondergelopen:
                    opname_uitvoer_onderlopen += 1

    finally:
        if gestarte_afspeelbeurt:
            # Ook bij een fout moet bekend zijn hoelang de afgespeelde
            # sessie daadwerkelijk openstond en hoeveel we hebben verstuurd.
            schrijf_auditgebeurtenis(
                auditlogboek,
                "geluid_gestopt",
                {
                    "geluid_id": "ingebouwde_testtoon_440hz",
                    "afspeelbeurt_id": afspeelbeurt_id,
                    "resultaat": (
                        "volledig_aangeleverd"
                        if aantal_verstuurde_frames == totaal_aantal_uitvoerframes
                        else "voortijdig_onderbroken"
                    ),
                    "aangeleverde_audio_seconden": round(
                        aantal_verstuurde_frames / instellingen.samplefrequentie, 3
                    ),
                    "werkelijke_verstreken_tijd_seconden": round(
                        time.perf_counter() - afspeel_starttijd, 3
                    ),
                    "aantal_onderlopen": opname_uitvoer_onderlopen,
                },
            )

        # Wacht ook bij een mislukte afspeelbeurt op de meetdraad. Zonder
        # deze cleanup zou de tijdelijke opname nog even door kunnen lopen.
        opnamedraad.join(timeout=6)

    if opnamedraad.is_alive():
        raise KabelcontroleFout(
            "KABEL-008: CABLE Output bleef langer dan verwacht opnemen. "
            "Controleer de Windows-driver en bekijk de logs."
        )
    if "fout" in gegevens_voor_opname:
        raise KabelcontroleFout(
            "KABEL-009: tijdens het opnemen van CABLE Output ontstond een fout."
        ) from gegevens_voor_opname["fout"]

    aantal_opgenomen_samples = gegevens_voor_opname.get("aantal_samples", 0)
    if aantal_opgenomen_samples == 0:
        raise KabelcontroleFout(
            "KABEL-010: er werden geen samples ontvangen van CABLE Output."
        )

    effectieve_waarde = math.sqrt(
        gegevens_voor_opname["som_van_kwadraten"] / aantal_opgenomen_samples
    )
    # Deze grens is laag omdat sommige Windows-gebruikers het apparaatvolume
    # al hebben verlaagd. Het is een signaaltest, geen beoordeling van kwaliteit.
    voldoende_signaal_ontvangen = (
        effectieve_waarde >= 0.0005
        and gegevens_voor_opname["herkende_toonssterkte"] >= 0.001
    )

    meetresultaat = MeetresultaatVanKabeltest(
        is_gelukt=(
            voldoende_signaal_ontvangen
            and opname_uitvoer_onderlopen == 0
            and gegevens_voor_opname["aantal_bufferproblemen"] == 0
        ),
        aantal_opgenomen_frames=gegevens_voor_opname["aantal_opgenomen_frames"],
        hoogste_samplewaarde=gegevens_voor_opname["hoogste_waarde"],
        gemiddelde_effectieve_samplewaarde=effectieve_waarde,
        herkende_toonssterkte=gegevens_voor_opname["herkende_toonssterkte"],
        aantal_waargenomen_bufferproblemen=(
            gegevens_voor_opname["aantal_bufferproblemen"]
            + opname_uitvoer_onderlopen
        ),
        aantal_verstuurde_frames=aantal_verstuurde_frames,
        speelduur_van_testtoon_in_seconden=(
            aantal_verstuurde_frames / instellingen.samplefrequentie
        ),
    )
    softwarelogboek.info(
        "De doorgifte via de virtuele kabel is gemeten",
        extra={
            "gebeurtenis": "kabel_signaal_gemeten",
            "gegevens": {
                "hoogste_samplewaarde": meetresultaat.hoogste_samplewaarde,
                "effectieve_samplewaarde": (
                    meetresultaat.gemiddelde_effectieve_samplewaarde
                ),
                "herkende_toonssterkte": meetresultaat.herkende_toonssterkte,
                "aantal_bufferproblemen": (
                    meetresultaat.aantal_waargenomen_bufferproblemen
                ),
                "aantal_opgenomen_frames": meetresultaat.aantal_opgenomen_frames,
                "test_gelukt": meetresultaat.is_gelukt,
            },
        },
    )
    return meetresultaat
