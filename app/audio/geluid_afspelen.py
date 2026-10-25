"""Speel één voorbereid fragment naar VB-CABLE met een volledige auditgeschiedenis.

Deze laag toont geen vensters en kiest geen bestanden. Het toekomstige
HTML-dashboard kan daardoor dezelfde afspeelfunctie opnieuw gebruiken.
"""

from __future__ import annotations

from dataclasses import dataclass
import logging
import threading
import time
from typing import Any, Callable
from uuid import uuid4

from app.audio.apparatenbeheer import GevondenAudioapparaat
from app.audio.geluidsbestanden import (
    AANTAL_UITVOERKANALEN,
    SAMPLEFREQUENTIE_VAN_DE_UITVOER,
    VoorbereidGeluidsfragment,
)
from app.diagnostiek.logboek import schrijf_auditgebeurtenis


AANTAL_FRAMES_PER_AUDIOBLOK = 1024


class GeluidAfspelenFout(RuntimeError):
    """Een herkenbare fout als de virtuele kabel niet veilig bruikbaar is."""


@dataclass(frozen=True)
class ResultaatVanEenAfspeelbeurt:
    """Hiermee weet het venster wat er werkelijk naar PortAudio ging."""

    afspeelbeurt_id: str
    resultaat: str
    aantal_verstuurde_frames: int
    aantal_bufferproblemen: int
    verstreken_tijd_in_seconden: float

    @property
    def aangeleverde_audio_in_seconden(self) -> float:
        return self.aantal_verstuurde_frames / SAMPLEFREQUENTIE_VAN_DE_UITVOER


def controleer_of_de_uitvoer_echt_de_gewone_vb_cable_is(
    uitvoerapparaat: GevondenAudioapparaat,
) -> None:
    """Verhinder dat een verkeerde apparaatselectie onbedoeld audio uitstuurd.

    De index kan verschuiven bij het aansluiten van een USB-apparaat. De
    aanroepende laag zoekt daarom bij iedere speelactie opnieuw het apparaat.
    """
    if not isinstance(uitvoerapparaat, GevondenAudioapparaat):
        raise GeluidAfspelenFout(
            "AFSPELEN-001: geen geldig uitvoerapparaat meegegeven."
        )
    if not (
        uitvoerapparaat.api_naam.casefold() == "windows wasapi"
        and uitvoerapparaat.naam.casefold().startswith("cable input (")
        and "vb-audio virtual cable" in uitvoerapparaat.naam.casefold()
        and uitvoerapparaat.aantal_uitvoerkanalen >= 2
    ):
        raise GeluidAfspelenFout(
            "AFSPELEN-002: het geselecteerde apparaat is niet de gewone CABLE Input "
            "van VB-Audio met Windows WASAPI. Afspelen is voor de zekerheid geweigerd."
        )


def speel_voorbereid_geluid_naar_de_virtuele_kabel(
    audiobibliotheek: Any,
    uitvoerapparaat: GevondenAudioapparaat,
    voorbereid_geluid: VoorbereidGeluidsfragment,
    softwarelogboek: logging.Logger,
    auditlogboek: logging.Logger,
    signaal_om_te_stoppen: threading.Event,
    afspeelbeurt_id: str | None = None,
    meld_dat_audio_echt_gestart_is: Callable[[], None] | None = None,
) -> ResultaatVanEenAfspeelbeurt:
    """Schrijf het WAV-fragment in kleine blokken en log begin en eind.

    Het totale bestand is al voorbereid. Tijdens het afspelen lezen we niet
    van schijf en starten we geen audioconversie. Stoppen kan na ieder blok.
    """
    controleer_of_de_uitvoer_echt_de_gewone_vb_cable_is(uitvoerapparaat)
    if not isinstance(voorbereid_geluid, VoorbereidGeluidsfragment):
        raise GeluidAfspelenFout("AFSPELEN-003: verwacht een voorbereid geluidsfragment.")
    if not isinstance(signaal_om_te_stoppen, threading.Event):
        raise GeluidAfspelenFout("AFSPELEN-004: het stopsignaal ontbreekt of is ongeldig.")

    if afspeelbeurt_id is None:
        afspeelbeurt_id = str(uuid4())
    elif not isinstance(afspeelbeurt_id, str) or not afspeelbeurt_id.strip():
        raise GeluidAfspelenFout("AFSPELEN-005: afspeelbeurt_id moet niet-lege tekst zijn.")

    if signaal_om_te_stoppen.is_set():
        return ResultaatVanEenAfspeelbeurt(afspeelbeurt_id, "voor_start_geannuleerd", 0, 0, 0.0)

    # Hiermee krijgen we een leesbare apparaatfout vóór we een audiostream
    # openen en voorkomen we dat een andere samplerate stilzwijgend wordt gebruikt.
    audiobibliotheek.check_output_settings(
        device=uitvoerapparaat.huidig_apparaatnummer,
        channels=AANTAL_UITVOERKANALEN,
        dtype="float32",
        samplerate=SAMPLEFREQUENTIE_VAN_DE_UITVOER,
    )

    aantal_verstuurde_frames = 0
    aantal_waargenomen_bufferproblemen = 0
    afspeelbeurt_is_gestart = False
    starttijd = 0.0
    resultaat = "mislukt"
    soort_van_fout = None

    try:
        with audiobibliotheek.RawOutputStream(
            samplerate=SAMPLEFREQUENTIE_VAN_DE_UITVOER,
            device=uitvoerapparaat.huidig_apparaatnummer,
            channels=AANTAL_UITVOERKANALEN,
            dtype="float32",
            latency="high",
        ) as uitvoerstroom:
            if signaal_om_te_stoppen.is_set():
                uitvoerstroom.abort(ignore_errors=False)
                return ResultaatVanEenAfspeelbeurt(
                    afspeelbeurt_id, "voor_start_geannuleerd", 0, 0, 0.0
                )

            starttijd = time.perf_counter()
            afspeelbeurt_is_gestart = True
            schrijf_auditgebeurtenis(
                auditlogboek,
                "geluid_gestart",
                {
                    "afspeelbeurt_id": afspeelbeurt_id,
                    "geluid_id": voorbereid_geluid.vingerafdruk_van_audio,
                    "naam": voorbereid_geluid.naam_van_het_geluid,
                    "bestandsnaam": voorbereid_geluid.bestandspad.name,
                    "ingesteld_volume": voorbereid_geluid.ingesteld_volume,
                    "geplande_duur_seconden": round(voorbereid_geluid.duur_in_seconden, 3),
                    "uitvoerapparaat": uitvoerapparaat.naam,
                },
            )
            if meld_dat_audio_echt_gestart_is is not None:
                meld_dat_audio_echt_gestart_is()

            ruwe_audio = voorbereid_geluid.ruwe_float32_stereo_audio
            aantal_bytes_per_frame = AANTAL_UITVOERKANALEN * 4
            blokgrootte_in_bytes = AANTAL_FRAMES_PER_AUDIOBLOK * aantal_bytes_per_frame
            for positie_van_blok in range(0, len(ruwe_audio), blokgrootte_in_bytes):
                if signaal_om_te_stoppen.is_set():
                    # abort stopt zonder de resterende audiobuffer uit te spelen.
                    # Dat is belangrijk voor een directe Stop-knop in de GUI.
                    uitvoerstroom.abort(ignore_errors=False)
                    resultaat = "handmatig_gestopt"
                    break
                audio_voor_dit_blok = ruwe_audio[
                    positie_van_blok : positie_van_blok + blokgrootte_in_bytes
                ]
                als_buffer_onderliep = uitvoerstroom.write(audio_voor_dit_blok)
                aantal_verstuurde_frames += len(audio_voor_dit_blok) // aantal_bytes_per_frame
                if als_buffer_onderliep:
                    aantal_waargenomen_bufferproblemen += 1
            if resultaat != "handmatig_gestopt":
                # De contextmanager gebruikt standaard ignore_errors=True.
                # Daarom vragen we vóór het verlaten van 'with' expliciet
                # om een fout bij mislukte stop, anders lijkt de audit groen.
                uitvoerstroom.stop(ignore_errors=False)
        if resultaat != "handmatig_gestopt":
            # Pas na een geslaagde context-exit weten we dat ook de afsluitende
            # driverbewerking niet is mislukt. Anders was de audit te optimistisch.
            resultaat = "volledig_aangeleverd"

    except Exception as oorspronkelijke_fout:
        soort_van_fout = type(oorspronkelijke_fout).__name__
        raise
    finally:
        if afspeelbeurt_is_gestart:
            schrijf_auditgebeurtenis(
                auditlogboek,
                "geluid_gestopt",
                {
                    "afspeelbeurt_id": afspeelbeurt_id,
                    "geluid_id": voorbereid_geluid.vingerafdruk_van_audio,
                    "naam": voorbereid_geluid.naam_van_het_geluid,
                    "resultaat": resultaat,
                    "stopreden": (
                        "gebruikersverzoek" if resultaat == "handmatig_gestopt" else resultaat
                    ),
                    "aangeleverde_audio_seconden": round(
                        aantal_verstuurde_frames / SAMPLEFREQUENTIE_VAN_DE_UITVOER, 3
                    ),
                    "verstreken_tijd_seconden": round(time.perf_counter() - starttijd, 3),
                    "aantal_bufferproblemen": aantal_waargenomen_bufferproblemen,
                    "fouttype": soort_van_fout,
                },
            )
            softwarelogboek.info(
                "Afspeelbeurt beëindigd",
                extra={
                    "gebeurtenis": "afspeelbeurt_afgerond",
                    "gegevens": {
                        "afspeelbeurt_id": afspeelbeurt_id,
                        "geluidsnaam": voorbereid_geluid.naam_van_het_geluid,
                        "resultaat": resultaat,
                        "aantal_uitvoerbufferproblemen": aantal_waargenomen_bufferproblemen,
                    },
                },
            )

    return ResultaatVanEenAfspeelbeurt(
        afspeelbeurt_id=afspeelbeurt_id,
        resultaat=resultaat,
        aantal_verstuurde_frames=aantal_verstuurde_frames,
        aantal_bufferproblemen=aantal_waargenomen_bufferproblemen,
        verstreken_tijd_in_seconden=(time.perf_counter() - starttijd),
    )
