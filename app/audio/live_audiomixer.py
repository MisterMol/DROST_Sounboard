"""Verbind een echte microfoon met VB-CABLE en meng optionele WAV-geluiden.

Deze module kent geen venster, bestandskiezer of Discord-instellingen. Dat is
bewust: later kan het HTML-dashboard dezelfde audiomotor aansturen.

We gebruiken voorlopig één WASAPI-duplexstream op 48 kHz. De werkdraad
initialiseert expliciet Windows COM voordat PortAudio wordt aangeroepen.
Bij een specifieke tijdelijke WDM-KS-startfout kan de stream gecontroleerd
worden vrijgegeven en opnieuw gestart; alle fouten blijven volledig gelogd.
Een andere fout wordt niet verdoezeld door nieuwe pogingen.
"""

from __future__ import annotations

from dataclasses import dataclass
import logging
from queue import Empty, SimpleQueue
import threading
import time
from typing import Any
from uuid import uuid4

import numpy as np

from app.audio.apparatenbeheer import GevondenAudioapparaat
from app.audio.automatisch_audioherstel import (
    MAXIMALE_STARTPOGINGEN,
    open_en_start_de_audiostream_met_herstel,
)
from app.audio.windows_com_context import houd_com_beschikbaar_tijdens_audioverbinding
from app.audio.geluid_afspelen import controleer_of_de_uitvoer_echt_de_gewone_vb_cable_is
from app.audio.signaaldiagnose import meet_rms_en_piek_van_een_audioblok
from app.audio.geschiedenis_van_audioniveaus import GeschiedenisVanAudioniveaus
from app.audio.geluidsbestanden import (
    SAMPLEFREQUENTIE_VAN_DE_UITVOER,
    VoorbereidGeluidsfragment,
)
from app.diagnostiek.logboek import schrijf_auditgebeurtenis


MICROFOONVOLUME = 0.8
MAXIMALE_PIEKWAARDE = 0.98
MAXIMALE_AANTAL_OPDRACHTEN_PER_AUDIOBLOK = 8
AANTAL_CALLBACKS_TUSSEN_SIGNAALMETINGEN = 1
MAXIMALE_TIJD_ZONDER_AUDIO_CALLBACK_IN_SECONDEN = 3.0
TIJD_TUSSEN_TECHNISCHE_SIGNAALLOGREGELS = 5.0


class LiveVerbindingFout(RuntimeError):
    """Geeft met een herkenbare code aan waarom de verbinding niet werkt."""


@dataclass(frozen=True)
class StatusVanDeLiveVerbinding:
    """Een momentopname voor het venster, zonder verborgen audiotoestand."""

    toestand: str
    microfoon: str
    uitvoer: str
    geluidseffecten_aan: bool
    aantal_bufferproblemen: int
    laatst_bekende_fout: str | None
    aantal_audio_callbacks: int
    aantal_aangeleverde_frames: int
    laatst_gemeten_microfoon_rms: float
    laatst_gemeten_kabel_rms: float
    laatst_gemeten_microfoon_piek: float
    laatst_gemeten_kabel_piek: float
    seconden_sinds_laatste_callback: float | None
    is_signaal_gemeten: bool
    huidige_startpoging: int = 0
    maximale_startpogingen: int = MAXIMALE_STARTPOGINGEN
    huidig_geluid: str | None = None
    huidig_geluid_id: str | None = None
    afspeelbeurt_id: str | None = None
    afgespeelde_seconden: float = 0.0
    beginpositie_seconden: float = 0.0


@dataclass(frozen=True)
class _AudioOpdracht:
    """Een kleine opdracht voor de callback, zonder bestandstoegang."""

    soort: str
    gegevens: Any = None


@dataclass
class _LopendGeluidsfragment:
    """Alleen de audiocallback verandert de afspeelpositie."""

    afspeelbeurt_id: str
    geluid: VoorbereidGeluidsfragment
    voorbereide_samples: np.ndarray
    huidige_framepositie: int = 0
    gestart_op: float = 0.0
    geluid_id: str | None = None


def controleer_of_microfoon_een_echt_opnameapparaat_is(
    microfoon: GevondenAudioapparaat,
) -> None:
    """Voorkom een feedbacklus door CABLE Output niet als microfoon toe te staan."""
    if not isinstance(microfoon, GevondenAudioapparaat):
        raise LiveVerbindingFout("LIVE-001: er is geen geldig microfoonapparaat gekozen.")
    if (
        microfoon.api_naam.casefold() != "windows wasapi"
        or microfoon.aantal_invoerkanalen < 1
        or "cable" in microfoon.naam.casefold()
        or "vb-audio" in microfoon.naam.casefold()
    ):
        raise LiveVerbindingFout(
            "LIVE-002: kies een echte microfoon met Windows WASAPI. "
            "De virtuele CABLE Output mag niet als microfoon worden gebruikt, "
            "anders kan een feedbacklus ontstaan."
        )


def kies_het_juiste_aantal_microfoonkanalen(
    audiobibliotheek: Any,
    microfoon: GevondenAudioapparaat,
) -> int:
    """Probeer eerst mono en daarna stereo, omdat sommige drivers mono weigeren.

    We bewaren beide driverfouten. Zonder deze context lijkt een Windows-driver
    die een kanaalindeling weigert ten onrechte op een onvindbaar apparaat.
    """
    controleer_of_microfoon_een_echt_opnameapparaat_is(microfoon)
    fouten_per_kanaalaantal = []
    for aantal_kanalen in (1, 2):
        if aantal_kanalen > microfoon.aantal_invoerkanalen:
            continue
        try:
            audiobibliotheek.check_input_settings(
                device=microfoon.huidig_apparaatnummer,
                channels=aantal_kanalen,
                dtype="float32",
                samplerate=SAMPLEFREQUENTIE_VAN_DE_UITVOER,
            )
            return aantal_kanalen
        except Exception as oorspronkelijke_fout:
            fouten_per_kanaalaantal.append(
                f"{aantal_kanalen} kanalen: {type(oorspronkelijke_fout).__name__}: "
                f"{oorspronkelijke_fout}"
            )
    raise LiveVerbindingFout(
        "LIVE-003: microfoon accepteert geen mono- of stereostream op 48 kHz. "
        "Controleer het standaardformaat van de microfoon in mmsys.cpl. "
        f"Driverantwoorden: {'; '.join(fouten_per_kanaalaantal)}"
    )


def maak_stereoblok_met_microfoon(
    ontvangen_microfoonframes: np.ndarray,
    uitvoerbuffer: np.ndarray,
) -> None:
    """Zet de echte microfoon in de stereobuffer met ruimte voor geluidseffecten."""
    if ontvangen_microfoonframes.ndim != 2 or uitvoerbuffer.ndim != 2:
        raise LiveVerbindingFout("LIVE-004: audioblokken moeten tweedimensionaal zijn.")
    if len(ontvangen_microfoonframes) != len(uitvoerbuffer):
        raise LiveVerbindingFout("LIVE-005: aantal invoerframes is niet gelijk aan uitvoerframes.")
    if ontvangen_microfoonframes.shape[1] not in (1, 2) or uitvoerbuffer.shape[1] != 2:
        raise LiveVerbindingFout("LIVE-006: verwacht mono of stereo invoer en stereo uitvoer.")

    # Headroom van 20% voorkomt dat iedere piek van de stem direct de limiter
    # raakt zodra er een geluidseffect bovenop komt.
    if ontvangen_microfoonframes.shape[1] == 1:
        uitvoerbuffer[:, 0] = ontvangen_microfoonframes[:, 0] * MICROFOONVOLUME
        uitvoerbuffer[:, 1] = ontvangen_microfoonframes[:, 0] * MICROFOONVOLUME
    else:
        uitvoerbuffer[:, :] = ontvangen_microfoonframes[:, :2] * MICROFOONVOLUME


class LiveAudiomixer:
    """Eén actieve verbinding met veilige aan/uit-stand voor geluidseffecten."""

    def __init__(
        self,
        audiobibliotheek: Any,
        softwarelogboek: logging.Logger,
        auditlogboek: logging.Logger,
    ) -> None:
        self.audiobibliotheek = audiobibliotheek
        self.softwarelogboek = softwarelogboek
        self.auditlogboek = auditlogboek
        self._toestand = "verbroken"
        self._toestand_slot = threading.Lock()
        self._microfoon: GevondenAudioapparaat | None = None
        self._kabel: GevondenAudioapparaat | None = None
        self._geluidseffecten_ingeschakeld = False
        self._laatste_fout: str | None = None
        self._bufferproblemen = 0
        self._gestarte_draad: threading.Thread | None = None
        self._stop_de_verbinding = threading.Event()
        self._audio_opdrachten: SimpleQueue[_AudioOpdracht] = SimpleQueue()
        self._audit_vanuit_callback: SimpleQueue[tuple[str, dict[str, Any]]] = SimpleQueue()
        self._huidige_geluid: _LopendGeluidsfragment | None = None
        self._fout_in_audio_callback: BaseException | None = None
        self._aantal_audio_callbacks = 0
        self._aantal_aangeleverde_frames = 0
        self._laatste_callback_tijd: float | None = None
        self._microfoon_rms = 0.0
        self._kabel_rms = 0.0
        self._microfoon_piek = 0.0
        self._kabel_piek = 0.0
        self._is_signaal_gemeten = False
        self._recente_microfoonmetingen = GeschiedenisVanAudioniveaus()
        self._recente_kabelmetingen = GeschiedenisVanAudioniveaus()
        self._huidige_startpoging = 0
        self._com_stand = "niet_gecontroleerd"
        self._stuur_effect_naar_eigen_headset = None
        self._maak_headsetbuffer_leeg = None

    def koppel_monitor_voor_effecten(self, stuur_samples, maak_buffer_leeg) -> None:
        """Bewaar optionele monitorfuncties, maar laat microfoonuitvoer onafhankelijk.

        De gekoppelde monitor krijgt uitsluitend het kant-en-klare effectblok.
        Daardoor komt de stem niet vertraagd terug in de eigen headset.
        """
        self._stuur_effect_naar_eigen_headset = stuur_samples
        self._maak_headsetbuffer_leeg = maak_buffer_leeg

    def geef_huidige_status(self) -> StatusVanDeLiveVerbinding:
        """Maak een snapshot, inclusief echte signalen die de callback verwerkt.

        De UI toont de niveaus van de Python-mixer. Dat is iets anders dan
        een bevestiging dat Discord of de Windows-kabel audio heeft ontvangen.
        """
        nu = time.monotonic()
        # Korte meetvensters tonen de energie van meerdere audioblokken,
        # niet toevallig alleen het laatste blok op het HTTP-moment.
        microfoon_rms, microfoon_piek = self._recente_microfoonmetingen.geef_recente_rms_en_piek(nu)
        kabel_rms, kabel_piek = self._recente_kabelmetingen.geef_recente_rms_en_piek(nu)
        with self._toestand_slot:
            return StatusVanDeLiveVerbinding(
                toestand=self._toestand,
                microfoon=self._microfoon.naam if self._microfoon else "geen",
                uitvoer=self._kabel.naam if self._kabel else "geen",
                geluidseffecten_aan=self._geluidseffecten_ingeschakeld,
                aantal_bufferproblemen=self._bufferproblemen,
                laatst_bekende_fout=self._laatste_fout,
                aantal_audio_callbacks=self._aantal_audio_callbacks,
                aantal_aangeleverde_frames=self._aantal_aangeleverde_frames,
                laatst_gemeten_microfoon_rms=microfoon_rms,
                laatst_gemeten_kabel_rms=kabel_rms,
                laatst_gemeten_microfoon_piek=microfoon_piek,
                laatst_gemeten_kabel_piek=kabel_piek,
                seconden_sinds_laatste_callback=(
                    round(nu - self._laatste_callback_tijd, 2)
                    if self._laatste_callback_tijd is not None else None
                ),
                is_signaal_gemeten=self._is_signaal_gemeten,
                huidige_startpoging=self._huidige_startpoging,
                huidig_geluid=(
                    self._huidige_geluid.geluid.naam_van_het_geluid
                    if self._huidige_geluid is not None else None
                ),
                huidig_geluid_id=(self._huidige_geluid.geluid_id if self._huidige_geluid else None),
                afspeelbeurt_id=(self._huidige_geluid.afspeelbeurt_id if self._huidige_geluid else None),
                afgespeelde_seconden=(self._huidige_geluid.huidige_framepositie / SAMPLEFREQUENTIE_VAN_DE_UITVOER
                                     if self._huidige_geluid else 0.0),
                beginpositie_seconden=(self._huidige_geluid.geluid.fragment_begint_bij_seconden
                                       if self._huidige_geluid else 0.0),
            )

    def _verander_status(self, nieuwe_toestand: str, foutmelding: str | None = None) -> None:
        with self._toestand_slot:
            self._toestand = nieuwe_toestand
            if foutmelding is not None:
                self._laatste_fout = foutmelding

    def verbind_de_microfoon_met_vb_cable(
        self,
        gekozen_microfoon: GevondenAudioapparaat,
        uitvoer_van_vb_cable: GevondenAudioapparaat,
    ) -> None:
        """Start een achtergronddraad; de UI hoeft niet op PortAudio te wachten."""
        controleer_of_microfoon_een_echt_opnameapparaat_is(gekozen_microfoon)
        controleer_of_de_uitvoer_echt_de_gewone_vb_cable_is(uitvoer_van_vb_cable)
        with self._toestand_slot:
            if self._toestand in ("wordt_verbonden", "verbonden", "wordt_verbroken"):
                raise LiveVerbindingFout("LIVE-007: er bestaat al een actieve of lopende verbinding.")
            if self._gestarte_draad is not None and self._gestarte_draad.is_alive():
                raise LiveVerbindingFout("LIVE-008: de vorige verbinding wordt nog afgesloten.")
            self._toestand = "wordt_verbonden"
            self._microfoon = gekozen_microfoon
            self._kabel = uitvoer_van_vb_cable
            self._laatste_fout = None
            self._geluidseffecten_ingeschakeld = False
            self._bufferproblemen = 0
            self._fout_in_audio_callback = None
            self._huidige_geluid = None
            self._aantal_audio_callbacks = 0
            self._aantal_aangeleverde_frames = 0
            self._laatste_callback_tijd = None
            self._microfoon_rms = 0.0
            self._kabel_rms = 0.0
            self._microfoon_piek = 0.0
            self._kabel_piek = 0.0
            self._is_signaal_gemeten = False
            self._recente_microfoonmetingen = GeschiedenisVanAudioniveaus()
            self._recente_kabelmetingen = GeschiedenisVanAudioniveaus()
            self._huidige_startpoging = 0
            self._com_stand = "niet_gecontroleerd"
            self._stop_de_verbinding = threading.Event()
            self._audio_opdrachten = SimpleQueue()
            self._audit_vanuit_callback = SimpleQueue()
        schrijf_auditgebeurtenis(
            self.auditlogboek,
            "verbinding_aangevraagd",
            {"microfoon": gekozen_microfoon.naam, "uitvoer": uitvoer_van_vb_cable.naam},
        )
        self._gestarte_draad = threading.Thread(
            target=self._voer_live_verbinding_uit,
            args=(gekozen_microfoon, uitvoer_van_vb_cable),
            name="Live-audiomixer",
            daemon=True,
        )
        self._gestarte_draad.start()

    def verbreek_de_verbinding(self) -> None:
        """Vraag de audio-thread om te stoppen; nooit blokkeren in een Windows-knop."""
        status = self.geef_huidige_status()
        if status.toestand not in ("verbonden", "wordt_verbonden"):
            return
        self._verander_status("wordt_verbroken")
        schrijf_auditgebeurtenis(self.auditlogboek, "verbinding_verbreken_aangevraagd")
        self._stop_de_verbinding.set()

    def wacht_tot_verbinding_echt_weg_is(self, maximaal_seconden: float = 4.0) -> bool:
        """Bij sluiten eerst de driver loslaten en pas daarna logbestanden sluiten."""
        if self._gestarte_draad is not None:
            self._gestarte_draad.join(timeout=maximaal_seconden)
            return not self._gestarte_draad.is_alive()
        return True

    def zet_geluidseffecten_aan_of_uit(self, geluidseffecten_aan: bool) -> None:
        """Zet alleen de geluiden uit; de microfoon blijft verbonden en hoorbaar."""
        if type(geluidseffecten_aan) is not bool:
            raise LiveVerbindingFout("LIVE-009: geluidseffecten_aan moet True of False zijn.")
        if self.geef_huidige_status().toestand != "verbonden":
            raise LiveVerbindingFout("LIVE-010: verbind eerst de microfoon.")
        self._audio_opdrachten.put(_AudioOpdracht("effecten_aan_of_uit", geluidseffecten_aan))

    def speel_een_voorbereid_geluid(self, geluid: VoorbereidGeluidsfragment, geluid_id: str | None = None) -> str:
        """Leg bytes buiten de callback om als samples klaar, dan pas aanbieden."""
        if not isinstance(geluid, VoorbereidGeluidsfragment):
            raise LiveVerbindingFout("LIVE-011: een voorbereid geluidsfragment ontbreekt.")
        if self.geef_huidige_status().toestand != "verbonden":
            schrijf_auditgebeurtenis(self.auditlogboek, "geluid_geweigerd", {"reden": "geen_verbinding"})
            raise LiveVerbindingFout("LIVE-012: druk eerst op Verbinden.")
        if not self.geef_huidige_status().geluidseffecten_aan:
            schrijf_auditgebeurtenis(self.auditlogboek, "geluid_geweigerd", {"reden": "soundboard_uit"})
            raise LiveVerbindingFout("LIVE-013: zet Soundboard aan om een geluid af te spelen.")
        samples = np.frombuffer(geluid.ruwe_float32_stereo_audio, dtype=np.float32)
        if samples.size == 0 or samples.size != geluid.aantal_frames * 2:
            raise LiveVerbindingFout("LIVE-014: voorbereid geluid bevat geen volledige stereoframes.")
        nieuw_geluid = _LopendGeluidsfragment(
            afspeelbeurt_id=str(uuid4()),
            geluid=geluid,
            voorbereide_samples=samples.reshape((-1, 2)),
            geluid_id=geluid_id,
        )
        self._audio_opdrachten.put(_AudioOpdracht("speel_geluid", nieuw_geluid))
        return nieuw_geluid.afspeelbeurt_id

    def stop_het_huidige_geluid(self) -> None:
        """Stop een geluidsfragment, zonder ook de live microfoon te stoppen."""
        self._audio_opdrachten.put(_AudioOpdracht("stop_geluid"))

    def _zet_audio_audit_klaar(self, gebeurtenis: str, gegevens: dict[str, Any]) -> None:
        # Geen schijf-I/O in de callback. De verbindingsthread schrijft dit weg.
        self._audit_vanuit_callback.put((gebeurtenis, gegevens))

    def _sluit_lopend_geluid_af(self, reden: str) -> None:
        """Sluit exact één afspeelbeurt af met de daadwerkelijk gemengde frames."""
        lopend = self._huidige_geluid
        if lopend is None:
            return
        self._huidige_geluid = None
        # Handmatig stoppen of vervangen moet ook het lokale afspeelbuffer legen.
        # Bij natuurlijk einde blijft het laatste monitorblok wél spelen.
        if reden != "volledig_aangeleverd" and self._maak_headsetbuffer_leeg is not None:
            self._maak_headsetbuffer_leeg()
        self._zet_audio_audit_klaar(
            "geluid_gestopt",
            {
                "afspeelbeurt_id": lopend.afspeelbeurt_id,
                "geluid_id": lopend.geluid.vingerafdruk_van_audio,
                "naam": lopend.geluid.naam_van_het_geluid,
                "reden": reden,
                "aangeleverde_audio_seconden": round(
                    lopend.huidige_framepositie / SAMPLEFREQUENTIE_VAN_DE_UITVOER, 3
                ),
                "verstreken_tijd_seconden": round(time.monotonic() - lopend.gestart_op, 3),
            },
        )

    def _voer_wachtende_opdrachten_uit(self) -> None:
        """Pak hooguit enkele opdrachten per callback zodat audio voorrang houdt."""
        for _ in range(MAXIMALE_AANTAL_OPDRACHTEN_PER_AUDIOBLOK):
            try:
                opdracht = self._audio_opdrachten.get_nowait()
            except Empty:
                break
            if opdracht.soort == "effecten_aan_of_uit":
                nieuwe_stand = opdracht.gegevens
                with self._toestand_slot:
                    self._geluidseffecten_ingeschakeld = nieuwe_stand
                if not nieuwe_stand:
                    self._sluit_lopend_geluid_af("soundboard_uitgeschakeld")
                self._zet_audio_audit_klaar(
                    "soundboard_ingeschakeld" if nieuwe_stand else "soundboard_uitgeschakeld",
                    {"microfoon_blijft_verbonden": True},
                )
            elif opdracht.soort == "stop_geluid":
                self._sluit_lopend_geluid_af("handmatig_gestopt")
            elif opdracht.soort == "speel_geluid":
                nieuw_geluid = opdracht.gegevens
                if not self._geluidseffecten_ingeschakeld:
                    self._zet_audio_audit_klaar(
                        "geluid_geweigerd",
                        {"afspeelbeurt_id": nieuw_geluid.afspeelbeurt_id, "reden": "soundboard_uit"},
                    )
                else:
                    # Fase 2 ondersteunt bewust één fragment tegelijk. Een
                    # nieuwe afspeelbeurt vervangt de oude voorspelbaar.
                    self._sluit_lopend_geluid_af("vervangen_door_ander_geluid")
                    nieuw_geluid.gestart_op = time.monotonic()
                    self._huidige_geluid = nieuw_geluid
                    self._zet_audio_audit_klaar(
                        "geluid_gestart",
                        {
                            "afspeelbeurt_id": nieuw_geluid.afspeelbeurt_id,
                            "bibliotheek_id": nieuw_geluid.geluid_id,
                            "geluid_id": nieuw_geluid.geluid.vingerafdruk_van_audio,
                            "naam": nieuw_geluid.geluid.naam_van_het_geluid,
                            "bestandsnaam": nieuw_geluid.geluid.bestandspad.name,
                            "geplande_duur_seconden": round(nieuw_geluid.geluid.duur_in_seconden, 3),
                            "volume": nieuw_geluid.geluid.ingesteld_volume,
                            "beginpositie_seconden": nieuw_geluid.geluid.fragment_begint_bij_seconden,
                            "bronduur_seconden": nieuw_geluid.geluid.bronduur_in_seconden,
                            "fragment_ingekort": nieuw_geluid.geluid.fragment_ingekort,
                        },
                    )

    def _verwerk_het_lopende_geluid_in_het_audioblok(self, uitvoerbuffer: np.ndarray) -> None:
        lopend = self._huidige_geluid
        if lopend is None:
            return
        maximaal_aantal_frames = len(lopend.voorbereide_samples) - lopend.huidige_framepositie
        aantal_frames_dit_blok = min(len(uitvoerbuffer), maximaal_aantal_frames)
        if aantal_frames_dit_blok > 0:
            begin_frame = lopend.huidige_framepositie
            effecten_dit_blok = lopend.voorbereide_samples[
                begin_frame : begin_frame + aantal_frames_dit_blok, :
            ]
            uitvoerbuffer[:aantal_frames_dit_blok, :] += effecten_dit_blok
            if self._stuur_effect_naar_eigen_headset is not None:
                # De monitor krijgt precies de effecten, nooit het microfoondeel.
                # Geen logboekacties of bestands-I/O vanuit de realtime callback.
                self._stuur_effect_naar_eigen_headset(effecten_dit_blok)
            lopend.huidige_framepositie += aantal_frames_dit_blok
        if lopend.huidige_framepositie >= len(lopend.voorbereide_samples):
            self._sluit_lopend_geluid_af("volledig_aangeleverd")

    def verwerk_een_blok_live_audio(
        self, inkomende_microfoonframes: np.ndarray, uitgaande_audio: np.ndarray,
        aantal_frames: int, tijdinformatie: Any, status_van_driver: Any,
    ) -> None:
        """De realtime callback: niets lezen van schijf en geen logbestanden schrijven."""
        try:
            if status_van_driver:
                self._bufferproblemen += 1
            maak_stereoblok_met_microfoon(inkomende_microfoonframes, uitgaande_audio)
            self._voer_wachtende_opdrachten_uit()
            self._verwerk_het_lopende_geluid_in_het_audioblok(uitgaande_audio)
            # Dit is voorlopig een veiligheidsbegrenzing, nog geen verfijnde
            # look-ahead-limiter. Het voorkomt oversturing van de kabel.
            np.clip(uitgaande_audio, -MAXIMALE_PIEKWAARDE, MAXIMALE_PIEKWAARDE, out=uitgaande_audio)
            # De stream kan 'active' zijn zonder een hoorbaar signaal te leveren.
            # Daarom bewaren we het aantal callbacks en de werkelijk gemeten
            # invoer- en uitvoerniveaus. Nooit de ruwe spraak zelf.
            self._aantal_audio_callbacks += 1
            self._aantal_aangeleverde_frames += aantal_frames
            self._laatste_callback_tijd = time.monotonic()
            # Meet ELK audioblok, niet om de beurt. Anders kan een heel korte
            # medeklinker precies in het overgeslagen blok verdwijnen en is
            # de aflezing niet betrouwbaar. De berekening blijft op NumPy-arrays
            # en schrijft niets naar schijf of het netwerk in de callback.
            if self._aantal_audio_callbacks % AANTAL_CALLBACKS_TUSSEN_SIGNAALMETINGEN == 0:
                self._microfoon_rms, self._microfoon_piek = (
                    meet_rms_en_piek_van_een_audioblok(inkomende_microfoonframes)
                )
                self._kabel_rms, self._kabel_piek = (
                    meet_rms_en_piek_van_een_audioblok(uitgaande_audio)
                )
                # Bewaar alleen de getallen, nooit de microfoonopname.
                # Gebruik hetzelfde tijdstip voor beide kanalen, zodat
                # de meters onderling goed te vergelijken blijven.
                meettijd = self._laatste_callback_tijd
                self._recente_microfoonmetingen.onthoud_gemeten_audioblok(
                    self._microfoon_rms, self._microfoon_piek, aantal_frames, meettijd
                )
                self._recente_kabelmetingen.onthoud_gemeten_audioblok(
                    self._kabel_rms, self._kabel_piek, aantal_frames, meettijd
                )
                self._is_signaal_gemeten = True
        except Exception as oorspronkelijke_fout:
            # PortAudio geeft Python-uitzonderingen in callbacks niet netjes
            # terug aan de GUI. Bewaar het origineel en laat de werkthread
            # later de volledige traceback naar software.jsonl schrijven.
            self._fout_in_audio_callback = oorspronkelijke_fout
            uitgaande_audio.fill(0)
            self._stop_de_verbinding.set()
            raise self.audiobibliotheek.CallbackAbort from oorspronkelijke_fout

    def _schrijf_alle_uitgestelde_auditregels(self) -> None:
        while True:
            try:
                gebeurtenis, gegevens = self._audit_vanuit_callback.get_nowait()
            except Empty:
                break
            schrijf_auditgebeurtenis(self.auditlogboek, gebeurtenis, gegevens)

    def _annuleer_niet_verwerkte_opdrachten(self) -> None:
        """Noteer geweigerde geluiden bij verbreken, in plaats van auditregels te missen."""
        while True:
            try:
                opdracht = self._audio_opdrachten.get_nowait()
            except Empty:
                break
            if opdracht.soort == "speel_geluid":
                schrijf_auditgebeurtenis(
                    self.auditlogboek,
                    "geluid_geweigerd",
                    {"afspeelbeurt_id": opdracht.gegevens.afspeelbeurt_id, "reden": "verbinding_verbroken"},
                )

    def _zet_huidige_startpoging(self, poging: int) -> None:
        """Maak een lopende herstelpoging zichtbaar zonder de GUI te blokkeren."""
        with self._toestand_slot:
            self._huidige_startpoging = poging

    def _voer_live_verbinding_uit(
        self, microfoon: GevondenAudioapparaat, kabel: GevondenAudioapparaat,
    ) -> None:
        """Initialiseer Windows COM in de audiowerkdraad vóór PortAudio.

        De GUI gebruikt een andere draad. COM-initialisatie van de UI wordt
        niet door een nieuwe threading.Thread geërfd. Door dit vóór de
        eerste PortAudio-aanroep te doen, voorkomen we een mogelijke oorzaak
        van de WdmSyncIoctl-startfout bij sommige Windows-audiodrivers.
        """
        try:
            with houd_com_beschikbaar_tijdens_audioverbinding() as com_stand:
                self._com_stand = com_stand
                self.softwarelogboek.info(
                    "Audio-werkdraad is voorbereid voor Windows WASAPI",
                    extra={
                        "gebeurtenis": "windows_com_voor_audio_voorbereid",
                        "gegevens": {
                            "com_stand": com_stand,
                            "fysieke_microfoon": microfoon.naam,
                            "virtuele_uitvoer": kabel.naam,
                        },
                    },
                )
                self._voer_live_verbinding_met_gereed_com_uit(microfoon, kabel)
        except Exception as fout:
            # Een COM-initialisatiefout ontstaat vóórdat de normale
            # PortAudio-foutafhandeling loopt. Daarom loggen we hier ook de
            # volledige traceback én een eigen auditgebeurtenis.
            self._verander_status("fout", str(fout))
            self.softwarelogboek.exception(
                "Voorbereiden of afsluiten van Windows COM is mislukt",
                extra={
                    "gebeurtenis": "windows_com_audio_mislukt",
                    "gegevens": {
                        "foutcode": "LIVE-020",
                        "com_stand": self._com_stand,
                        "fouttype": type(fout).__name__,
                    },
                },
            )
            schrijf_auditgebeurtenis(
                self.auditlogboek,
                "verbinding_mislukt",
                {"reden": str(fout), "fase": "windows_com_initialiseren_of_afsluiten"},
            )

    def _voer_live_verbinding_met_gereed_com_uit(
        self, microfoon: GevondenAudioapparaat, kabel: GevondenAudioapparaat,
    ) -> None:
        """Controleer, open, bewaak en sluit streams op de voorbereide draad."""
        audiostroom = None
        fout_tijdens_verbinding: BaseException | None = None
        wat_was_bezig = "audio-instellingen controleren"
        verbinding_heeft_echt_gewerkt = False
        try:
            gekozen_aantal_invoerkanalen = kies_het_juiste_aantal_microfoonkanalen(
                self.audiobibliotheek, microfoon
            )
            self.audiobibliotheek.check_output_settings(
                device=kabel.huidig_apparaatnummer,
                channels=2, dtype="float32", samplerate=SAMPLEFREQUENTIE_VAN_DE_UITVOER,
            )
            if self._stop_de_verbinding.is_set():
                return
            wat_was_bezig = "duplex audiostream openen en starten met automatisch herstel"
            instellingen_van_stream = {
                "samplerate": SAMPLEFREQUENTIE_VAN_DE_UITVOER,
                "blocksize": 0,
                "device": (microfoon.huidig_apparaatnummer, kabel.huidig_apparaatnummer),
                "channels": (gekozen_aantal_invoerkanalen, 2),
                "dtype": "float32",
                "latency": "high",
                "callback": self.verwerk_een_blok_live_audio,
            }
            audiostroom, aantal_startpogingen = open_en_start_de_audiostream_met_herstel(
                audiobibliotheek=self.audiobibliotheek,
                instellingen_van_stream=instellingen_van_stream,
                stoppen_gevraagd=self._stop_de_verbinding,
                softwarelogboek=self.softwarelogboek,
                auditlogboek=self.auditlogboek,
                zet_huidige_poging=self._zet_huidige_startpoging,
            )
            if audiostroom is None:
                # Verbreken tijdens een herstelpauze is een normale actie.
                # We mogen dat niet als een werkende audioverbinding melden.
                return
            # De gevraagde WASAPI-latentie staat voorlopig bewust op "high".
            # Met eerdere Razer-drivers gaf een agressieve instelling problemen.
            # Log de door PortAudio gemelde WERKELIJKE input-/outputlatentie;
            # daarmee kunnen we op jouw pc later veilig een lagere stand testen.
            try:
                gerapporteerde_latentie = audiostroom.latency
                if isinstance(gerapporteerde_latentie, (tuple, list)):
                    latency_ms = [round(float(waarde) * 1000, 2)
                                  for waarde in gerapporteerde_latentie]
                elif isinstance(gerapporteerde_latentie, (int, float)):
                    latency_ms = round(float(gerapporteerde_latentie) * 1000, 2)
                else:
                    latency_ms = None
                self.softwarelogboek.info(
                    "Audioapparaat meldt zijn werkelijke streamlatentie",
                    extra={
                        "gebeurtenis": "audiostream_latentie_gemeld",
                        "gegevens": {"latentie_ms": latency_ms, "gevraagd_profiel": "high"},
                    },
                )
            except Exception:
                # Deze informatie is optionele diagnostiek. Een driver die
                # geen latency teruggeeft mag de werkende verbinding NIET stoppen.
                self.softwarelogboek.debug(
                    "De audiodriver kon geen latentie-informatie teruggeven", exc_info=True
                )
            verbinding_heeft_echt_gewerkt = True
            self._verander_status("verbonden")
            schrijf_auditgebeurtenis(
                self.auditlogboek,
                "verbinding_gestart",
                {
                    "microfoon": microfoon.naam,
                    "microfoon_nummer_op_dit_moment": microfoon.huidig_apparaatnummer,
                    "invoerkanalen": gekozen_aantal_invoerkanalen,
                    "uitvoer": kabel.naam,
                    "uitvoer_nummer_op_dit_moment": kabel.huidig_apparaatnummer,
                    "samplefrequentie": SAMPLEFREQUENTIE_VAN_DE_UITVOER,
                    "aantal_startpogingen": aantal_startpogingen,
                    "com_stand": self._com_stand,
                    "stand_bij_opstart": "geluidseffecten_uit, microfoon_doorgeven",
                },
            )
            wat_was_bezig = "de live-audiostream en het echte signaal bewaken"
            verbinding_gestart_op = time.monotonic()
            laatste_technische_meting = verbinding_gestart_op
            while not self._stop_de_verbinding.wait(timeout=0.08):
                self._schrijf_alle_uitgestelde_auditregels()
                if not audiostroom.active:
                    raise LiveVerbindingFout(
                        "LIVE-015: de audiostream is onverwacht gestopt. "
                        "Controleer USB, microfoonrechten en VB-CABLE."
                    )
                nu = time.monotonic()
                laatste_callback = self._laatste_callback_tijd
                tijd_van_meest_recente_audio = (
                    laatste_callback if laatste_callback is not None else verbinding_gestart_op
                )
                if nu - tijd_van_meest_recente_audio > MAXIMALE_TIJD_ZONDER_AUDIO_CALLBACK_IN_SECONDEN:
                    raise LiveVerbindingFout(
                        "LIVE-018: Windows meldt een actieve audioverbinding, "
                        "maar de mixer krijgt al meer dan drie seconden geen "
                        "audioblokken. Controleer de audio-API en apparaatinstellingen."
                    )
                if nu - laatste_technische_meting >= TIJD_TUSSEN_TECHNISCHE_SIGNAALLOGREGELS:
                    # Dit is softwarediagnostiek, geen auditgebeurtenis. Zo
                    # groeien auditbestanden niet per paar seconden mee.
                    self.softwarelogboek.info(
                        "Niveaumeting van de live audiomixer",
                        extra={
                            "gebeurtenis": "live_signaalmeting",
                            "gegevens": {
                                "aantal_callbacks": self._aantal_audio_callbacks,
                                "aantal_frames": self._aantal_aangeleverde_frames,
                                "microfoon_rms": round(self._microfoon_rms, 7),
                                "microfoon_piek": round(self._microfoon_piek, 7),
                                "naar_kabel_rms": round(self._kabel_rms, 7),
                                "naar_kabel_piek": round(self._kabel_piek, 7),
                                "aantal_bufferproblemen": self._bufferproblemen,
                                "seconden_sinds_callback": round(nu - tijd_van_meest_recente_audio, 3),
                                "fysieke_microfoon": microfoon.naam,
                                "virtuele_uitvoer": kabel.naam,
                            },
                        },
                    )
                    laatste_technische_meting = nu
            self._schrijf_alle_uitgestelde_auditregels()
            if self._fout_in_audio_callback is not None:
                raise LiveVerbindingFout(
                    "LIVE-016: de audiocallback is onverwacht gestopt. "
                    "Zie de volledige oorspronkelijke fout in software.jsonl."
                ) from self._fout_in_audio_callback
        except Exception as oorspronkelijke_fout:
            fout_tijdens_verbinding = oorspronkelijke_fout
            self._verander_status("fout", str(oorspronkelijke_fout))
            self.softwarelogboek.exception(
                "De live audioverbinding is mislukt",
                extra={
                    "gebeurtenis": "live_audioverbinding_mislukt",
                    "gegevens": {
                        "foutcode": "LIVE-999",
                        "actie_bij_fout": wat_was_bezig,
                        "microfoon": microfoon.naam,
                        "microfoon_nummer": microfoon.huidig_apparaatnummer,
                        "kabel": kabel.naam,
                        "kabel_nummer": kabel.huidig_apparaatnummer,
                        "samplefrequentie": SAMPLEFREQUENTIE_VAN_DE_UITVOER,
                        "type_fout": type(oorspronkelijke_fout).__name__,
                        "parameters_voor_stream": {
                            "blocksize": 0, "dtype": "float32", "latency": "high"
                        },
                        "aantal_gedane_startpogingen": self._huidige_startpoging,
                        "com_stand": self._com_stand,
                    },
                },
            )
            schrijf_auditgebeurtenis(
                self.auditlogboek,
                "verbinding_mislukt",
                {"reden": str(oorspronkelijke_fout), "microfoon": microfoon.naam},
            )
        finally:
            # Belangrijk: ook als openen of schrijven mislukt, sluiten we de
            # PortAudio-objecten. Anders blijft CABLE Input bezet na een fout.
            if audiostroom is not None:
                # Alleen een werkelijk lopende stream moet worden gestopt.
                # Een mislukte start kan anders een tweede 'not active'-fout
                # veroorzaken die de originele driverfout zou maskeren.
                acties_bij_afsluiten = []
                if audiostroom.active:
                    acties_bij_afsluiten.append(
                        ("stoppen", lambda: audiostroom.stop(ignore_errors=False))
                    )
                acties_bij_afsluiten.append(
                    ("sluiten", lambda: audiostroom.close(ignore_errors=False))
                )
                for actie, handeling in acties_bij_afsluiten:
                    try:
                        handeling()
                    except Exception as fout_bij_afsluiten:
                        # De eerste fout blijft de hoofdoorzaak. Secundaire
                        # fouten krijgen wel hun eigen volledige traceback.
                        if fout_tijdens_verbinding is None:
                            fout_tijdens_verbinding = fout_bij_afsluiten
                            self._verander_status("fout", str(fout_bij_afsluiten))
                        self.softwarelogboek.exception(
                            "De audiodriver kon niet netjes worden afgesloten",
                            extra={
                                "gebeurtenis": "afsluiten_audio_mislukt",
                                "gegevens": {"foutcode": "LIVE-017", "handeling": actie},
                            },
                        )
            if self._huidige_geluid is not None:
                self._sluit_lopend_geluid_af("verbinding_verbroken")
            self._schrijf_alle_uitgestelde_auditregels()
            self._annuleer_niet_verwerkte_opdrachten()
            schrijf_auditgebeurtenis(
                self.auditlogboek,
                "verbinding_verbroken" if fout_tijdens_verbinding is None else "verbinding_afgebroken_met_fout",
                {
                    "heeft_gewerkt": verbinding_heeft_echt_gewerkt,
                    "aantal_bufferproblemen": self._bufferproblemen,
                    "fouttype": type(fout_tijdens_verbinding).__name__ if fout_tijdens_verbinding else None,
                },
            )
            # Na echt verbreken moet een volgende verbinding altijd beginnen
            # met soundboard uit, ook als de vorige stand nog aan stond.
            with self._toestand_slot:
                self._geluidseffecten_ingeschakeld = False
            if fout_tijdens_verbinding is None:
                self._verander_status("verbroken")
            else:
                self._verander_status("fout", str(fout_tijdens_verbinding))
