"""Verbind een echte microfoon met VB-CABLE en meng optionele WAV-geluiden.

Deze module kent geen venster, bestandskiezer of Discord-instellingen. Dat is
bewust: later kan het HTML-dashboard dezelfde audiomotor aansturen.

We gebruiken bij voorkeur één WASAPI-duplexstream op 48 kHz. Bij een
niet passend microfoonformaat valt de app terug op gescheiden streams. De werkdraad
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
from app.audio.automatische_microfoonformaten import (
    KANDIDAAT_FREQUENTIES, maak_streamadapter, zoek_microfoonformaat,
)
from app.audio.automatisch_audioherstel import (
    MAXIMALE_STARTPOGINGEN,
    is_het_bekende_tijdelijke_windows_driverprobleem,
    open_en_start_de_audiostream_met_herstel,
)
from app.audio.windows_com_context import houd_com_beschikbaar_tijdens_audioverbinding
from app.audio.geluid_afspelen import controleer_of_de_uitvoer_echt_de_gewone_vb_cable_is
from app.audio.signaaldiagnose import meet_rms_en_piek_van_een_audioblok
from app.audio.pieklimiter import PiekLimiter, PIEKPLAFOND
from app.audio.stemvervorming import Stemvervormer, controleer_stemprofiel, controleer_stemintensiteit, STANDAARD_INTENSITEITEN
from app.audio.stemparameters import standaard_parameters, controleer_parameters
from app.audio.geschiedenis_van_audioniveaus import GeschiedenisVanAudioniveaus
from app.audio.geluidsbestanden import (
    SAMPLEFREQUENTIE_VAN_DE_UITVOER,
    VoorbereidGeluidsfragment,
)
from app.diagnostiek.logboek import schrijf_auditgebeurtenis


MICROFOONVOLUME = 0.8
MAXIMALE_PIEKWAARDE = PIEKPLAFOND
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
    live_herhalen: bool = False
    live_basisvolume: float | None = None
    positie_wijzigingsnummer: int = 0
    limiter_aan: bool = True
    limiter_reductie_db: float = 0.0
    limiter_terugvallen: int = 0
    stemprofiel: str = "normaal"
    stemvervorming_terugvallen: int = 0
    stemvervorming_geblokkeerd: bool = False
    stem_rms: float = 0.0
    stem_piek: float = 0.0
    effect_actief: bool = False
    effect_rms_voor: float = 0.0
    effect_rms_na: float = 0.0
    microfoon_samplefrequentie: int | None = None
    uitvoer_samplefrequentie: int = SAMPLEFREQUENTIE_VAN_DE_UITVOER
    aangepast_microfoonformaat: bool = False
    microfoon_formaten_geprobeerd: tuple[int, ...] = ()
    microfoon_formaten_geschikt: tuple[int, ...] = ()
    standaard_microfoonfrequentie: int | None = None
    microfoon_formaat_fout: bool = False


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
    herhalen: bool = False
    positie_wijzigingsnummer: int = 0
    fade_in_frames: int = 0
    # None houdt het oude contract voor reeds versterkte fragmenten intact.
    basisvolume: float | None = None
    vorige_basisvolume_factor: float = 1.0


def _meet_effect_rms_zonder_audio_te_onderbreken(blok: np.ndarray) -> float:
    """Een defect meetblok mag nooit een lopende microfoonstream onderbreken."""
    try:
        return meet_rms_en_piek_van_een_audioblok(blok)[0]
    except Exception:
        return 0.0


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
        # Extern geconfigureerde factor, uitsluitend voor soundboardfragmenten.
        # De audiocallback leest deze waarde maar doet geen database-I/O.
        self._algemeen_effectvolume_percentage = 100
        self._vorige_effectvolume_factor = 1.0
        self._effect_actief = False
        self._effect_rms_voor = 0.0
        self._effect_rms_na = 0.0
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
        self._microfoon_samplefrequentie: int | None = None
        self._aangepast_microfoonformaat = False
        self._microfoon_formaten_geprobeerd: tuple[int, ...] = ()
        self._microfoon_formaten_geschikt: tuple[int, ...] = ()
        self._standaard_microfoonfrequentie: int | None = None
        self._stuur_effect_naar_eigen_headset = None
        self._maak_headsetbuffer_leeg = None
        self._stuur_live_mix_naar_headset = None
        self._eigen_stem_monitor_aan = False
        self._limiter = PiekLimiter()
        self._limiter_ingeschakeld = True
        self._limiter_vorige_stand = True
        self._limiter_reductie_db = 0.0
        self._limiter_reductie_tijd = 0.0
        self._limiter_terugvallen = 0
        self._limiter_laatste_fout: BaseException | None = None
        self._stemprofiel = "normaal"
        self._stemvervormer_aan = False
        self._stemintensiteiten = dict(STANDAARD_INTENSITEITEN)
        self._stemparameters = standaard_parameters()
        self._stem_rms = 0.0
        self._stem_piek = 0.0
        self._stem_was_actief = False
        self._stemvervormer = Stemvervormer()
        self.natuurlijke_stem = None
        self._stem_natuurlijk_was_actief = False
        self._stemvervorming_terugvallen = 0
        self._stemvervorming_geblokkeerd = False
        self._stemvervorming_laatste_fout: BaseException | None = None

    def stel_stemprofiel_in(self, profiel: str) -> None:
        """Atomic string assignment. De audiocallback wijzigt zijn eigen DSP-state."""
        self._stemprofiel = controleer_stemprofiel(profiel)

    def is_stemvervormer_ingeschakeld(self) -> bool:
        """Laat de actuele live-schakelstand zien zonder database-I/O."""
        return self._stemvervormer_aan

    def stel_stemvervormer_aan_in(self, aan: bool) -> None:
        # Callback leest uitsluitend geheugen; geen databaseverbinding.
        if type(aan) is not bool:
            raise ValueError('STEM-082: aan moet een boolean zijn.')
        self._stemvervormer_aan = aan

    def stel_stemintensiteiten_in(self, waarden: dict[str, int]) -> None:
        """Vervang één immutable snapshot; callback leest enkel geheugen."""
        if set(waarden) != set(STANDAARD_INTENSITEITEN):
            raise ValueError('STEM-031: onvolledige stemprofielinstellingen.')
        nieuw = {controleer_stemprofiel(naam): controleer_stemintensiteit(sterkte)
                 for naam, sterkte in waarden.items()}
        self._stemintensiteiten = nieuw

    def stel_stemparameters_in(self, waarden: dict[str, dict]) -> None:
        if set(waarden) != set(standaard_parameters()):
            raise ValueError('STEM-053: onvolledige effectinstellingen.')
        self._stemparameters = {naam: controleer_parameters(naam, params) for naam, params in waarden.items()}

    def stel_algemeen_effectvolume_in(self, percentage: int) -> None:
        """Stel het algemene effectvolume in zonder een audiostream te herstarten."""
        if type(percentage) is not int or not 0 <= percentage <= 200:
            raise ValueError('VOLUME-001: verwacht een percentage van 0 tot 200.')
        self._algemeen_effectvolume_percentage = percentage

    def geef_algemeen_effectvolume(self) -> int:
        return self._algemeen_effectvolume_percentage

    def stel_limiter_in(self, ingeschakeld: bool) -> None:
        """Wissel alleen een bool; geen schijf-I/O of audiostream-herstart."""
        if type(ingeschakeld) is not bool:
            raise ValueError('LIMITER-004: ingeschakeld moet true of false zijn.')
        self._limiter_ingeschakeld = ingeschakeld

    def stel_eigen_stem_monitor_in(self, aan: bool) -> None:
        if type(aan) is not bool:
            raise ValueError('MON-010: stemmonitor moet true of false zijn.')
        self._eigen_stem_monitor_aan = aan

    def koppel_monitor_voor_effecten(self, stuur_samples, maak_buffer_leeg, stuur_live_mix=None) -> None:
        """Bewaar optionele monitorfuncties, maar laat microfoonuitvoer onafhankelijk.

        De gekoppelde monitor krijgt uitsluitend het kant-en-klare effectblok.
        Daardoor komt de stem niet vertraagd terug in de eigen headset.
        """
        self._stuur_effect_naar_eigen_headset = stuur_samples
        self._maak_headsetbuffer_leeg = maak_buffer_leeg
        self._stuur_live_mix_naar_headset = stuur_live_mix

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
                live_herhalen=bool(self._huidige_geluid and self._huidige_geluid.herhalen),
                live_basisvolume=self._huidige_geluid.basisvolume if self._huidige_geluid else None,
                positie_wijzigingsnummer=(self._huidige_geluid.positie_wijzigingsnummer
                                          if self._huidige_geluid else 0),
                limiter_aan=self._limiter_ingeschakeld,
                limiter_reductie_db=(
                    round(self._limiter_reductie_db, 2)
                    if self._limiter_ingeschakeld
                    and nu - self._limiter_reductie_tijd <= 0.55 else 0.0
                ),
                limiter_terugvallen=self._limiter_terugvallen,
                stemprofiel=self._stemprofiel,
                stemvervorming_terugvallen=self._stemvervorming_terugvallen,
                stemvervorming_geblokkeerd=self._stemvervorming_geblokkeerd,
                stem_rms=self._stem_rms if self._is_signaal_gemeten and self._toestand == "verbonden" else 0.0,
                stem_piek=self._stem_piek if self._is_signaal_gemeten and self._toestand == "verbonden" else 0.0,
                effect_actief=self._effect_actief and self._toestand == "verbonden",
                effect_rms_voor=self._effect_rms_voor if self._toestand == "verbonden" else 0.0,
                effect_rms_na=self._effect_rms_na if self._toestand == "verbonden" else 0.0,
                microfoon_samplefrequentie=self._microfoon_samplefrequentie,
                aangepast_microfoonformaat=self._aangepast_microfoonformaat,
                microfoon_formaten_geprobeerd=self._microfoon_formaten_geprobeerd,
                microfoon_formaten_geschikt=self._microfoon_formaten_geschikt,
                standaard_microfoonfrequentie=self._standaard_microfoonfrequentie,
                microfoon_formaat_fout=bool(self._laatste_fout and self._laatste_fout.startswith('LIVE-003:')),
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
            self._effect_actief = False
            self._effect_rms_voor = 0.0
            self._effect_rms_na = 0.0
            self._recente_microfoonmetingen = GeschiedenisVanAudioniveaus()
            self._recente_kabelmetingen = GeschiedenisVanAudioniveaus()
            self._huidige_startpoging = 0
            self._com_stand = "niet_gecontroleerd"
            self._microfoon_samplefrequentie = None
            self._aangepast_microfoonformaat = False
            self._microfoon_formaten_geprobeerd = ()
            self._microfoon_formaten_geschikt = ()
            self._standaard_microfoonfrequentie = None
            self._limiter = PiekLimiter()
            self._limiter_vorige_stand = self._limiter_ingeschakeld
            self._limiter_reductie_db = 0.0
            self._limiter_reductie_tijd = 0.0
            self._limiter_terugvallen = 0
            self._limiter_laatste_fout = None
            self._stem_was_actief = False
            self._stemvervormer = Stemvervormer(self._stemprofiel,
                                                    intensiteit=self._stemintensiteiten[self._stemprofiel],
                                                    parameters=self._stemparameters)
            self._stem_rms = 0.0
            self._stem_piek = 0.0
            self._stemvervorming_terugvallen = 0
            self._stemvervorming_geblokkeerd = False
            self._stemvervorming_laatste_fout = None
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

    def speel_een_voorbereid_geluid(self, geluid: VoorbereidGeluidsfragment, geluid_id: str | None = None,
                                    *, herhalen: bool = False, basisvolume: float | None = None) -> str:
        """Leg bytes buiten de callback om als samples klaar, dan pas aanbieden."""
        if not isinstance(geluid, VoorbereidGeluidsfragment):
            raise LiveVerbindingFout("LIVE-011: een voorbereid geluidsfragment ontbreekt.")
        if type(herhalen) is not bool:
            raise LiveVerbindingFout("LIVE-027: herhalen moet true of false zijn.")
        if self.geef_huidige_status().toestand != "verbonden":
            schrijf_auditgebeurtenis(self.auditlogboek, "geluid_geweigerd", {"reden": "geen_verbinding"})
            raise LiveVerbindingFout("LIVE-012: druk eerst op Verbinden.")
        if not self.geef_huidige_status().geluidseffecten_aan:
            schrijf_auditgebeurtenis(self.auditlogboek, "geluid_geweigerd", {"reden": "soundboard_uit"})
            raise LiveVerbindingFout("LIVE-013: zet Soundboard aan om een geluid af te spelen.")
        if basisvolume is not None and (type(basisvolume) not in (int, float)
                or not np.isfinite(basisvolume) or not 0 <= basisvolume <= 2):
            raise LiveVerbindingFout('VOLUME-005: kies een basisvolume van 0 tot 200%.')
        samples = np.frombuffer(geluid.ruwe_float32_stereo_audio, dtype=np.float32)
        if samples.size == 0 or samples.size != geluid.aantal_frames * 2:
            raise LiveVerbindingFout("LIVE-014: voorbereid geluid bevat geen volledige stereoframes.")
        nieuw_geluid = _LopendGeluidsfragment(
            afspeelbeurt_id=str(uuid4()),
            geluid=geluid,
            voorbereide_samples=samples.reshape((-1, 2)),
            geluid_id=geluid_id,
            herhalen=herhalen,
            basisvolume=basisvolume,
            vorige_basisvolume_factor=1.0 if basisvolume is None else float(basisvolume),
        )
        self._audio_opdrachten.put(_AudioOpdracht("speel_geluid", nieuw_geluid))
        return nieuw_geluid.afspeelbeurt_id

    def stop_het_huidige_geluid(self) -> None:
        """Stop een geluidsfragment, zonder ook de live microfoon te stoppen."""
        self._audio_opdrachten.put(_AudioOpdracht("stop_geluid"))

    def zoek_in_lopend_geluid(self, afspeelbeurt_id: str, fractie: float) -> None:
        """Verplaats een reeds gedecodeerd fragment via de audiowachtrij.

        Geen audiofile openen, database lezen of wachten op het callback in HTTP.
        De unieke afspeelbeurt voorkomt dat een oude seek een nieuwe clip raakt.
        """
        if not isinstance(afspeelbeurt_id, str) or len(afspeelbeurt_id) != 36:
            raise LiveVerbindingFout('LIVE-023: ongeldige afspeelbeurt.')
        if not isinstance(fractie, (float, int)) or isinstance(fractie, bool) or not np.isfinite(fractie) or not 0 <= fractie <= 1:
            raise LiveVerbindingFout('LIVE-024: positie moet tussen 0 en 1 liggen.')
        self._audio_opdrachten.put(_AudioOpdracht('zoek_geluid', (afspeelbeurt_id, float(fractie))))

    def stel_lopend_geluid_herhalen_in(self, afspeelbeurt_id: str, aan: bool) -> None:
        """Herhalen geldt uitsluitend voor déze afspeelbeurt, nooit voor een volgende."""
        if not isinstance(afspeelbeurt_id, str) or len(afspeelbeurt_id) != 36:
            raise LiveVerbindingFout('LIVE-025: ongeldige afspeelbeurt.')
        if type(aan) is not bool:
            raise LiveVerbindingFout('LIVE-026: herhalen moet true of false zijn.')
        self._audio_opdrachten.put(_AudioOpdracht('herhaal_geluid', (afspeelbeurt_id, aan)))

    def stel_lopend_basisvolume_in(self, afspeelbeurt_id: str, volume: float) -> None:
        """Pas alleen deze afspeelbeurt aan, zonder decoden of de microfoon te wijzigen."""
        if not isinstance(afspeelbeurt_id, str) or len(afspeelbeurt_id) != 36:
            raise LiveVerbindingFout('SPELER-001: dit fragment speelt niet meer.')
        if type(volume) not in (int, float) or not np.isfinite(volume) or not 0 <= volume <= 2:
            raise LiveVerbindingFout('VOLUME-005: kies een basisvolume van 0 tot 200%.')
        self._audio_opdrachten.put(_AudioOpdracht('basisvolume_geluid', (afspeelbeurt_id, float(volume))))

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
            elif opdracht.soort == "zoek_geluid":
                afspeelbeurt, fractie = opdracht.gegevens
                actief = self._huidige_geluid
                if actief is not None and actief.afspeelbeurt_id == afspeelbeurt:
                    lengte = len(actief.voorbereide_samples)
                    if lengte:
                        actief.huidige_framepositie = min(lengte - 1, int(fractie * lengte))
                        actief.positie_wijzigingsnummer += 1
                        actief.fade_in_frames = min(144, lengte)
                        if self._maak_headsetbuffer_leeg is not None:
                            self._maak_headsetbuffer_leeg()
            elif opdracht.soort == "herhaal_geluid":
                afspeelbeurt, aan = opdracht.gegevens
                actief = self._huidige_geluid
                if actief is not None and actief.afspeelbeurt_id == afspeelbeurt:
                    actief.herhalen = aan
            elif opdracht.soort == 'basisvolume_geluid':
                afspeelbeurt, volume = opdracht.gegevens
                actief = self._huidige_geluid
                if (actief is not None and actief.afspeelbeurt_id == afspeelbeurt
                        and actief.basisvolume is not None):
                    actief.basisvolume = volume
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
        # Alleen getallen voor UI, geen audio-opnames. Reset zodra het geluid stopt.
        self._effect_actief = False
        self._effect_rms_voor = 0.0
        self._effect_rms_na = 0.0
        lopend = self._huidige_geluid
        if lopend is None:
            # Een nieuwe clip begint op de gekozen stand, zonder oude ramp.
            self._vorige_effectvolume_factor = self._algemeen_effectvolume_percentage / 100.0
            return
        bron = lopend.voorbereide_samples
        aantal_bronframes = len(bron)
        lengte_blok = len(uitvoerbuffer)
        if aantal_bronframes <= 0 or lengte_blok <= 0:
            self._sluit_lopend_geluid_af("leeg_fragment")
            return
        begin_frame = lopend.huidige_framepositie
        if lopend.herhalen:
            # De volledige uitvoerbuffer vullen, ook als de loop middenin eindigt.
            # Dit voorkomt steeds korte stiltes op de rand van een herhaling.
            indices = (np.arange(lengte_blok, dtype=np.int64) + begin_frame) % aantal_bronframes
            effecten_dit_blok = bron[indices, :].copy()
            aantalloops = (begin_frame + lengte_blok) // aantal_bronframes
            lopend.huidige_framepositie = (begin_frame + lengte_blok) % aantal_bronframes
            if aantalloops:
                lopend.positie_wijzigingsnummer += aantalloops
            # Twee milliseconden rond de lusgrens zijn licht afgezwakt om een
            # klik te voorkomen wanneer het einde niet precies op nul uitkomt.
            rand = min(96, max(0, aantal_bronframes // 4))
            if rand:
                afstand = indices.astype(np.int64)
                envelop = np.minimum(1., np.minimum(afstand, aantal_bronframes - 1 - afstand) / rand)
                effecten_dit_blok *= envelop.astype(np.float32)[:, None]
            aantal_frames_dit_blok = lengte_blok
        else:
            beschikbaar = aantal_bronframes - begin_frame
            aantal_frames_dit_blok = min(lengte_blok, max(0, beschikbaar))
            effecten_dit_blok = bron[begin_frame:begin_frame + aantal_frames_dit_blok, :]
            lopend.huidige_framepositie += aantal_frames_dit_blok
        if aantal_frames_dit_blok > 0:
            if lopend.fade_in_frames:
                # Na een gebruikers-seek nooit met een harde samplegrens starten.
                effecten_dit_blok = effecten_dit_blok.copy()
                aantal = min(lopend.fade_in_frames, aantal_frames_dit_blok)
                effecten_dit_blok[:aantal, :] *= np.linspace(
                    0, 1, aantal, dtype=np.float32)[:, None]
                lopend.fade_in_frames -= aantal
            # De samples zijn bij de webspeler op basisvolume 100% voorbereid.
            # Zo blijft ook een fragment dat op 0% begon later versterkbaar.
            basisvolume = getattr(lopend, 'basisvolume', None)
            if basisvolume is not None:
                vorige = lopend.vorige_basisvolume_factor
                if abs(basisvolume - vorige) > 1e-6:
                    ramp = np.linspace(vorige, basisvolume, aantal_frames_dit_blok + 1,
                                       dtype=np.float32)[1:]
                    effecten_dit_blok = effecten_dit_blok * ramp[:, None]
                elif basisvolume != 1.0:
                    effecten_dit_blok = effecten_dit_blok * basisvolume
                lopend.vorige_basisvolume_factor = basisvolume
            self._effect_rms_voor = _meet_effect_rms_zonder_audio_te_onderbreken(effecten_dit_blok)
            gewenste_factor = self._algemeen_effectvolume_percentage / 100.0
            vorige_factor = self._vorige_effectvolume_factor
            if abs(gewenste_factor - vorige_factor) > 1e-6:
                ramp = np.linspace(vorige_factor, gewenste_factor,
                                   aantal_frames_dit_blok + 1, dtype=np.float32)[1:]
                effecten_dit_blok = effecten_dit_blok * ramp[:, None]
            elif gewenste_factor != 1.0:
                effecten_dit_blok = effecten_dit_blok * gewenste_factor
            self._vorige_effectvolume_factor = gewenste_factor
            self._effect_rms_na = _meet_effect_rms_zonder_audio_te_onderbreken(effecten_dit_blok)
            self._effect_actief = True
            uitvoerbuffer[:aantal_frames_dit_blok, :] += effecten_dit_blok
            if self._stuur_effect_naar_eigen_headset is not None and not self._eigen_stem_monitor_aan:
                self._stuur_effect_naar_eigen_headset(effecten_dit_blok)
        if not lopend.herhalen and lopend.huidige_framepositie >= aantal_bronframes:
            self._sluit_lopend_geluid_af("volledig_aangeleverd")

    def verwerk_een_blok_live_audio(
        self, inkomende_microfoonframes: np.ndarray, uitgaande_audio: np.ndarray,
        aantal_frames: int, tijdinformatie: Any, status_van_driver: Any,
    ) -> None:
        """De realtime callback: niets lezen van schijf en geen logbestanden schrijven."""
        try:
            if status_van_driver:
                self._bufferproblemen += 1
            # Pas alleen de fysieke stem aan. Soundboardgeluiden worden PAS
            # daarna toegevoegd. Bij een stemfout nooit de originele stem lekken.
            microfoon_voor_mix = inkomende_microfoonframes
            dienst = self.natuurlijke_stem
            natuurlijk_actief = dienst is not None and dienst.aan
            stem_actief = natuurlijk_actief or (self._stemvervormer_aan and self._stemprofiel != 'normaal')
            self._stemvervorming_geblokkeerd = False
            try:
                if (stem_actief != self._stem_was_actief
                        or natuurlijk_actief != self._stem_natuurlijk_was_actief):
                    self._stemvervormer.herstel_audiobuffers()
                    self._stem_was_actief = stem_actief
                    self._stem_natuurlijk_was_actief = natuurlijk_actief
                if natuurlijk_actief:
                    microfoon_voor_mix = dienst.verwerk(inkomende_microfoonframes, 'live')
                else:
                    if self._stemvervormer.profiel != self._stemprofiel:
                        self._stemvervormer.kies_profiel(self._stemprofiel)
                    # Parameters bijstellen zonder herverbinden en zonder schijf-I/O.
                    if self._stemvervormer._bron_parameters_ref is not self._stemparameters:
                        self._stemvervormer.neem_gecontroleerde_parameters_over(self._stemparameters)
                    intensiteit = self._stemintensiteiten[self._stemprofiel]
                    if self._stemvervormer.intensiteit != intensiteit:
                        self._stemvervormer.stel_intensiteit_in(intensiteit)
                    if stem_actief:
                        microfoon_voor_mix = self._stemvervormer.verwerk(inkomende_microfoonframes)
                if stem_actief:
                    if (not isinstance(microfoon_voor_mix, np.ndarray)
                            or microfoon_voor_mix.shape != inkomende_microfoonframes.shape
                            or microfoon_voor_mix.dtype != np.float32
                            or not np.isfinite(microfoon_voor_mix).all()):
                        raise ValueError('STEM-004: de stemverwerking gaf ongeldige samples terug.')
            except Exception as stemfout:
                self._stemvervorming_terugvallen += 1
                if self._stemvervorming_laatste_fout is None:
                    self._stemvervorming_laatste_fout = stemfout
                self._stemvervorming_geblokkeerd = bool(stem_actief)
                microfoon_voor_mix = (np.zeros_like(inkomende_microfoonframes)
                                      if stem_actief else inkomende_microfoonframes)
            maak_stereoblok_met_microfoon(microfoon_voor_mix, uitgaande_audio)
            stem_voor_headset = (uitgaande_audio.copy() if self._eigen_stem_monitor_aan
                                 and self._stuur_live_mix_naar_headset is not None else None)
            self._voer_wachtende_opdrachten_uit()
            self._verwerk_het_lopende_geluid_in_het_audioblok(uitgaande_audio)
            # Voor headsetmonitoring bewaren we alleen bij ingeschakelde eigen
            # stem de mix vóór de limiter. Zo kan het lokaal beluisterde
            # stemdeel dezelfde piekbeperking volgen als VB-CABLE.
            mix_voor_begrenzen = uitgaande_audio.copy() if stem_voor_headset is not None else None
            # Eindmix eerst met een dynamische peak-gain beperken. Geen extra
            # bufferlatentie, disk-I/O of Python-lus over audioframes.
            # Uit schakelt de limiter uit voor vergelijking; de oude harde
            # veiligheidsgrens blijft in beide standen bestaan.
            if self._limiter_vorige_stand != self._limiter_ingeschakeld:
                self._limiter.herstel()
                self._limiter_vorige_stand = self._limiter_ingeschakeld
                self._limiter_reductie_db = 0.0
            if self._limiter_ingeschakeld:
                try:
                    reductie = self._limiter.verwerk_in_place(uitgaande_audio)
                    if reductie >= 0.05:
                        self._limiter_reductie_db = reductie
                        self._limiter_reductie_tijd = time.monotonic()
                except Exception as fout:
                    # Een defecte limiter mag de stem niet onderbreken.
                    # Diagnose wordt pas in de beheerthread weggeschreven.
                    self._limiter_terugvallen += 1
                    if self._limiter_terugvallen == 1:
                        self._limiter_laatste_fout = fout
                        self._zet_audio_audit_klaar('limiter_terugval', {
                            'fouttype': type(fout).__name__, 'aantal': 1})
                    self._limiter.herstel()
            # Altijd het laatste veiligheidsnet, ook bij uitgeschakelde limiter.
            # Non-finite audio wordt in de foutuitwijk geneutraliseerd.
            np.nan_to_num(uitgaande_audio, copy=False, nan=0.0, posinf=0.0, neginf=0.0)
            np.clip(uitgaande_audio, -MAXIMALE_PIEKWAARDE, MAXIMALE_PIEKWAARDE, out=uitgaande_audio)
            if stem_voor_headset is not None:
                # Het stemdeel volgt dezelfde samplebegrenzing als de totale
                # uitgang. De eigen volumenregelaar mag vervolgens uitsluitend
                # dit stemdeel aanpassen; het echte VB-CABLE-signaal blijft intact.
                verhouding = np.ones_like(uitgaande_audio)
                np.divide(uitgaande_audio, mix_voor_begrenzen, out=verhouding,
                          where=np.abs(mix_voor_begrenzen) > 1e-6)
                np.clip(verhouding, 0.0, 1.0, out=verhouding)
                stem_voor_headset *= verhouding
                # Alleen de al bestaande headset-output krijgt deze kopie.
                try:
                    self._stuur_live_mix_naar_headset(uitgaande_audio, stem_voor_headset)
                except Exception:
                    # Een monitorfout mag de virtuele microfoon nooit stoppen.
                    pass
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
                self._stem_rms, self._stem_piek = (
                    meet_rms_en_piek_van_een_audioblok(microfoon_voor_mix)
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
        stemfout = self._stemvervorming_laatste_fout
        if stemfout is not None:
            self._stemvervorming_laatste_fout = None
            self.softwarelogboek.error(
                'Stemverwerking gaf een fout; een actieve effectstem wordt niet onbewerkt doorgestuurd',
                exc_info=(type(stemfout), stemfout, stemfout.__traceback__),
                extra={'gebeurtenis': 'stemvervorming_terugval', 'gegevens': {'foutcode': 'STEM-999'}},
            )
        # Tracebacks worden pas op de beheerthread weggeschreven; een
        # audiocallback mag nooit op een schijfhandler blokkeren.
        limiterfout = self._limiter_laatste_fout
        if limiterfout is not None:
            self._limiter_laatste_fout = None
            self.softwarelogboek.error(
                'De pieklimiter is teruggevallen op de veilige piekbegrenzing',
                exc_info=(type(limiterfout), limiterfout, limiterfout.__traceback__),
                extra={'gebeurtenis': 'pieklimiter_terugval', 'gegevens': {'foutcode': 'LIMITER-999'}},
            )
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
            # Bestaande snelle duplexroute blijft exact gelijk voor werkende
            # apparaten. Pas wanneer 48 kHz wordt geweigerd zoeken we naar
            # daadwerkelijk door PortAudio geaccepteerde alternatieven.
            gescheiden_formaat = None
            try:
                gekozen_aantal_invoerkanalen = kies_het_juiste_aantal_microfoonkanalen(
                    self.audiobibliotheek, microfoon
                )
                self._microfoon_samplefrequentie = SAMPLEFREQUENTIE_VAN_DE_UITVOER
                self._microfoon_formaten_geschikt = (SAMPLEFREQUENTIE_VAN_DE_UITVOER,)
                self._microfoon_formaten_geprobeerd = (SAMPLEFREQUENTIE_VAN_DE_UITVOER,)
            except LiveVerbindingFout as fout_48khz:
                if not str(fout_48khz).startswith('LIVE-003:'):
                    raise
                gescheiden_formaat = zoek_microfoonformaat(
                    self.audiobibliotheek, microfoon.huidig_apparaatnummer,
                    microfoon.aantal_invoerkanalen,
                )
                if gescheiden_formaat is None:
                    # Het door de driver gemelde standaardformaat is géén
                    # bewijs van daadwerkelijke ondersteuning.
                    self._microfoon_formaten_geprobeerd = KANDIDAAT_FREQUENTIES
                    try:
                        standaard = self.audiobibliotheek.query_devices(
                            microfoon.huidig_apparaatnummer)['default_samplerate']
                        self._standaard_microfoonfrequentie = int(float(standaard))
                    except (AttributeError, KeyError, ValueError, TypeError, OverflowError):
                        pass
                    raise LiveVerbindingFout(
                        'LIVE-003: deze microfoon accepteert geen van de geteste '                        'opnameformaten. Controleer de microfoon in Windows '                        'Geluid > Meer geluidsinstellingen > Opnemen > Eigenschappen '                        '> Geavanceerd, of kies een andere microfooningang.'
                    ) from fout_48khz
                gekozen_aantal_invoerkanalen = gescheiden_formaat.aantal_kanalen
                self._microfoon_samplefrequentie = gescheiden_formaat.samplefrequentie
                self._standaard_microfoonfrequentie = gescheiden_formaat.standaard_samplefrequentie
                self._microfoon_formaten_geprobeerd = gescheiden_formaat.geteste_samplefrequenties
                self._microfoon_formaten_geschikt = gescheiden_formaat.ondersteunde_samplefrequenties
                self._aangepast_microfoonformaat = (
                    gescheiden_formaat.samplefrequentie != SAMPLEFREQUENTIE_VAN_DE_UITVOER
                )
                if not self._aangepast_microfoonformaat:
                    gescheiden_formaat = None
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
            werkelijke_bibliotheek = (maak_streamadapter(self.audiobibliotheek, gescheiden_formaat)
                                      if gescheiden_formaat is not None else self.audiobibliotheek)
            try:
                audiostroom, aantal_startpogingen = open_en_start_de_audiostream_met_herstel(
                    audiobibliotheek=werkelijke_bibliotheek,
                    instellingen_van_stream=instellingen_van_stream,
                    stoppen_gevraagd=self._stop_de_verbinding,
                    softwarelogboek=self.softwarelogboek,
                    auditlogboek=self.auditlogboek,
                    zet_huidige_poging=self._zet_huidige_startpoging,
                )
            except Exception as fout_bij_duplex:
                # Sommige WASAPI-drivers weigeren de gecombineerde duplexstream,
                # terwijl twee losse audiostreams wel kunnen werken.
                # Probeer dit ALLEEN bij een herkenbaar formaatprobleem of als
                # de specifieke WdmSyncIoctl-herstelpogingen zijn uitgeput.
                # Programmeerfouten en een niet veilig gesloten audiohandle
                # mogen geen nieuwe streams starten.
                rate_fout = str(fout_bij_duplex).casefold()
                ongeldige_frequentie = ('invalid sample rate' in rate_fout or
                                        'paerrorcode -9997' in rate_fout)
                bekende_wdm_fout = is_het_bekende_tijdelijke_windows_driverprobleem(
                    fout_bij_duplex
                )
                if not (ongeldige_frequentie or bekende_wdm_fout):
                    raise
                if gescheiden_formaat is not None:
                    if bekende_wdm_fout:
                        raise LiveVerbindingFout(
                            'LIVE-024: Windows kon ook de afzonderlijke microfoon- '
                            'en kabelstreams niet openen. Sluit andere audioprogramma’s '
                            'en controleer de Windows-audiodrivers.'
                        ) from fout_bij_duplex
                    raise LiveVerbindingFout(
                        'LIVE-003: Windows accepteerde het opnameformaat bij de controle, '
                        'maar de headset weigerde de echte audiostream. Controleer '
                        'in Windows het opnameformaat en probeer een andere microfooningang.'
                    ) from fout_bij_duplex
                self.softwarelogboek.warning(
                    'WASAPI-duplex kon niet starten; twee afzonderlijke streams proberen',
                    extra={'gebeurtenis': 'duplex_fallback_naar_gescheiden_streams',
                           'gegevens': {
                               'oorzaak': 'wdmsyncioctl' if bekende_wdm_fout else 'samplefrequentie',
                               'microfoon': microfoon.naam,
                               'kabel': kabel.naam,
                           }},
                )
                gescheiden_formaat = zoek_microfoonformaat(
                    self.audiobibliotheek, microfoon.huidig_apparaatnummer,
                    microfoon.aantal_invoerkanalen,
                )
                if gescheiden_formaat is None:
                    raise LiveVerbindingFout(
                        'LIVE-003: ook na het automatisch onderzoeken van andere '
                        'opnameformaten kon deze microfoon niet worden geopend. '
                        'Controleer het opnameformaat in de Windows-geluidsinstellingen.'
                    ) from fout_bij_duplex
                self._microfoon_samplefrequentie = gescheiden_formaat.samplefrequentie
                self._standaard_microfoonfrequentie = gescheiden_formaat.standaard_samplefrequentie
                self._microfoon_formaten_geprobeerd = gescheiden_formaat.geteste_samplefrequenties
                self._microfoon_formaten_geschikt = gescheiden_formaat.ondersteunde_samplefrequenties
                self._aangepast_microfoonformaat = True
                audiostroom, aantal_startpogingen = open_en_start_de_audiostream_met_herstel(
                    audiobibliotheek=maak_streamadapter(self.audiobibliotheek, gescheiden_formaat),
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
                    "microfoon_samplefrequentie": self._microfoon_samplefrequentie,
                    "automatische_sampleomzetting": self._aangepast_microfoonformaat,
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
