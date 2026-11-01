"""Automatisch microfoonformaat kiezen zonder de 48 kHz-soundboardmix aan te passen.

De snelle WASAPI-duplexstream blijft de normale route. Alleen bij een
samplefrequentieverschil gebruiken we twee losse streams en een begrensde
realtime-buffer. Een aparte werkdraad zet microfoonsamples met SoXR om.
Geen driver- of bestandstoegang vanuit de PortAudio-callbacks.
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from queue import Empty, Full, Queue
import math
import threading
from typing import Any, Callable

import numpy as np

from app.audio.geluidsbestanden import SAMPLEFREQUENTIE_VAN_DE_UITVOER


# Het Windows-standaardformaat krijgt voorrang boven willekeurige frequenties.
# Er wordt NIET aangenomen dat een frequentie wordt ondersteund: iedere
# combinatie gaat eerst langs PortAudio.check_input_settings().
KANDIDAAT_FREQUENTIES = (48000, 44100, 32000, 24000, 16000, 22050, 8000, 96000, 88200)


@dataclass(frozen=True)
class MicrofoonFormaat:
    samplefrequentie: int
    aantal_kanalen: int
    standaard_samplefrequentie: int | None
    geteste_samplefrequenties: tuple[int, ...]
    ondersteunde_samplefrequenties: tuple[int, ...]


def _geldige_frequentie(waarde: Any) -> int | None:
    """Weiger onzinnige driverwaarden en onbedoeld extreem hoge frequenties."""
    try:
        frequentie = float(waarde)
    except (TypeError, ValueError, OverflowError):
        return None
    if not math.isfinite(frequentie) or not 8000 <= frequentie <= 192000:
        return None
    afgerond = int(round(frequentie))
    return afgerond if abs(frequentie - afgerond) < 0.1 else None


def zoek_microfoonformaat(audiobibliotheek: Any, apparaatnummer: int,
                           maximale_kanalen: int) -> MicrofoonFormaat | None:
    """Onderzoek driverformaten zonder de microfoon al te openen.

    Geeft None als geen bruikbaar formaat is gevonden. De beller kan voor een
    gerichte foutmelding alsnog het door de driver genoemde standaardformaat
    opvragen; een standaardformaat is NIET automatisch een bewezen werkend formaat.
    """
    standaard = None
    try:
        gegevens = audiobibliotheek.query_devices(apparaatnummer)
        standaard = _geldige_frequentie(gegevens.get('default_samplerate'))
    except (AttributeError, TypeError, ValueError, OSError):
        pass
    kandidaten = tuple(dict.fromkeys(
        ([standaard] if standaard is not None else []) + list(KANDIDAAT_FREQUENTIES)
    ))
    gevonden: list[tuple[int, int]] = []
    for frequentie in kandidaten:
        for kanalen in (1, 2):
            if kanalen > maximale_kanalen:
                continue
            try:
                audiobibliotheek.check_input_settings(
                    device=apparaatnummer, channels=kanalen,
                    dtype='float32', samplerate=frequentie,
                )
            except Exception:
                continue
            gevonden.append((frequentie, kanalen))
            break  # mono heeft voorrang; geen onnodig tweede driververzoek
    if not gevonden:
        return None
    rate, channels = gevonden[0]
    return MicrofoonFormaat(
        samplefrequentie=rate, aantal_kanalen=channels,
        standaard_samplefrequentie=standaard,
        geteste_samplefrequenties=kandidaten,
        ondersteunde_samplefrequenties=tuple(f for f, _ in gevonden),
    )


class _BegrensdeAudiobuffer:
    """Sla 48kHz-samples met een vaste maximale wachttijd op.

    Een niet beschikbare lock geeft kort stilte, nooit een haperende callback.
    Een te volle buffer gooit oudste frames weg in plaats van achter te lopen.
    """

    def __init__(self, kanalen: int, max_frames: int = 12000) -> None:
        self.kanalen = kanalen
        self.max_frames = max_frames
        self._slot = threading.Lock()
        self._blokken: deque[np.ndarray] = deque()
        self._offset = 0
        self._frames = 0
        self.verloren_frames = 0
        self.lege_frames = 0

    @property
    def beschikbare_frames(self) -> int:
        with self._slot:
            return self._frames

    def schrijf(self, blok: np.ndarray) -> None:
        if not len(blok):
            return
        stuk = np.ascontiguousarray(blok, dtype=np.float32)
        if stuk.ndim != 2 or stuk.shape[1] != self.kanalen:
            raise ValueError('De microfoonbuffer verwacht het gekozen kanaalaantal.')
        with self._slot:
            if len(stuk) >= self.max_frames:
                self.verloren_frames += self._frames + len(stuk) - self.max_frames
                self._blokken.clear()
                self._frames = 0
                self._offset = 0
                stuk = stuk[-self.max_frames:]
            while self._frames + len(stuk) > self.max_frames:
                oud = self._blokken.popleft()
                verwijderd = len(oud) - self._offset
                self.verloren_frames += verwijderd
                self._frames -= verwijderd
                self._offset = 0
            self._blokken.append(stuk)
            self._frames += len(stuk)

    def lees(self, aantal_frames: int) -> np.ndarray:
        # Het volledige block wordt altijd opgevuld, desnoods met stilte.
        resultaat = np.zeros((aantal_frames, self.kanalen), dtype=np.float32)
        if not self._slot.acquire(blocking=False):
            self.lege_frames += aantal_frames
            return resultaat
        try:
            positie = 0
            while positie < aantal_frames and self._blokken:
                bron = self._blokken[0]
                aantal = min(aantal_frames - positie, len(bron) - self._offset)
                resultaat[positie:positie + aantal] = bron[self._offset:self._offset + aantal]
                positie += aantal
                self._offset += aantal
                self._frames -= aantal
                if self._offset == len(bron):
                    self._blokken.popleft()
                    self._offset = 0
            self.lege_frames += aantal_frames - positie
            return resultaat
        finally:
            self._slot.release()


class AudioApparaatOpenFout(RuntimeError):
    """Houd bij een mislukte losse stream bij welk endpoint Windows weigerde.

    De oorspronkelijke PortAudioError blijft beschikbaar in de chained
    traceback. Het dashboard kan hierdoor een gerichte melding geven.
    """

    def __init__(self, kant: str, oorspronkelijke_fout: Exception) -> None:
        self.kant = kant
        super().__init__(
            f"Losse {'microfoon' if kant == 'invoer' else 'VB-CABLE-uitvoer'} "
            f"kon niet worden geopend: {type(oorspronkelijke_fout).__name__}: "
            f"{oorspronkelijke_fout}"
        )


class GescheidenMicrofoonEnUitvoer:
    """Gedraagt zich als een PortAudio-stream voor de bestaande mixer.

    De inputcallback maakt alleen een kopie en zet die in een begrensde rij.
    SoXR draait in een gewone werkdraad, nooit op de audio-callback-thread.
    De outputcallback gebruikt de bestaande mixercallback op 48 kHz. Daardoor
    blijven effectduur, tijdlijn, pieklimiter en stemvervormers intact.
    """

    def __init__(self, audiobibliotheek: Any, invoernummer: int, uitvoernummer: int,
                 formaat: MicrofoonFormaat, uitvoercallback: Callable[..., None],
                 *, omzetter_factory: Callable[..., Any] | None = None) -> None:
        self._bibliotheek = audiobibliotheek
        self.formaat = formaat
        self._uitvoercallback = uitvoercallback
        self._wachtrij: Queue[np.ndarray] = Queue(maxsize=12)
        self._buffer = _BegrensdeAudiobuffer(formaat.aantal_kanalen)
        self._stop = threading.Event()
        self._werkdraad: threading.Thread | None = None
        self._werkfout: BaseException | None = None
        self._invoer = None
        self._uitvoer = None
        self._omzetter_factory = omzetter_factory
        self._uitvoer_api = 'Windows WASAPI'
        # Windows WASAPI Shared accepteert niet altijd een ander kanaal- of
        # sampleformaat dan het ingestelde Windows-mixerformaat. Op de
        # gescheiden herstelroute mag de Windows-mixer veilig converteren.
        # De bestaande werkende duplexroute verandert hierdoor niet.
        wasapi = getattr(audiobibliotheek, 'WasapiSettings', None)
        extra_settings = (
            {'extra_settings': wasapi(exclusive=False, auto_convert=True)}
            if callable(wasapi) else {}
        )
        try:
            try:
                self._invoer = audiobibliotheek.InputStream(
                    samplerate=formaat.samplefrequentie, blocksize=0,
                    device=invoernummer, channels=formaat.aantal_kanalen,
                    dtype='float32', latency='high', callback=self._vang_microfoon_op,
                    **extra_settings,
                )
            except Exception as fout:
                raise AudioApparaatOpenFout('invoer', fout) from fout
            try:
                self._uitvoer = self._open_uitvoer(uitvoernummer, extra_settings)
            except Exception as fout:
                # Een specifieke WASAPI-uitvoerfout mag één reservepoging
                # activeren op exact dezelfde VB-CABLE via DirectSound.
                if not self._probeer_directsound_kabeluitvoer(fout):
                    raise AudioApparaatOpenFout('uitvoer', fout) from fout
        except Exception:
            self.close(ignore_errors=True)
            raise

    def _open_uitvoer(self, nummer: int, extra_settings: dict | None = None):
        """Open 48 kHz stereo naar een vooraf gevalideerd kabelapparaat."""
        return self._bibliotheek.OutputStream(
            samplerate=SAMPLEFREQUENTIE_VAN_DE_UITVOER, blocksize=0,
            device=nummer, channels=2, dtype='float32', latency='high',
            callback=self._stuur_naar_kabel, **(extra_settings or {}),
        )

    def _probeer_directsound_kabeluitvoer(self, eerste_fout: Exception) -> bool:
        """Probeer nooit de systeemuitvoer: uitsluitend de unieke VB-CABLE.

        DirectSound is een gerichte reserve voor de bekende -9996 fout.
        Andere driverfouten en ontbrekende of meerdere kabels stoppen.
        """
        omschrijving = str(eerste_fout).casefold()
        if not ('paerrorcode -9996' in omschrijving and
                'invalid device' in omschrijving):
            return False
        reservetoestel = zoek_veilige_directsound_kabeluitvoer(self._bibliotheek)
        if reservetoestel is None:
            return False
        try:
            self._uitvoer = self._open_uitvoer(reservetoestel)
        except Exception as fout:
            raise AudioApparaatOpenFout('uitvoer', fout) from fout
        self._uitvoer_api = 'Windows DirectSound'
        return True

    @property
    def uitvoer_api(self) -> str:
        return self._uitvoer_api

    @property
    def active(self) -> bool:
        return bool(self._invoer and self._uitvoer and self._invoer.active
                    and self._uitvoer.active and self._werkdraad
                    and self._werkdraad.is_alive() and self._werkfout is None)

    @property
    def latency(self) -> tuple[float, float]:
        return (getattr(self._invoer, 'latency', 0.0),
                getattr(self._uitvoer, 'latency', 0.0))

    @property
    def werkfout(self) -> BaseException | None:
        return self._werkfout

    def _vang_microfoon_op(self, indata, frames, tijdinformatie, status) -> None:
        # Queue is begrensd: microfoondata mag nooit onbeperkt RAM vullen.
        # Als de verwerking achterloopt, laten we een oud blok vervallen.
        blok = indata.copy()
        try:
            self._wachtrij.put_nowait(blok)
        except Full:
            try:
                self._wachtrij.get_nowait()
            except Empty:
                pass
            try:
                self._wachtrij.put_nowait(blok)
            except Full:
                pass

    def _omzetten(self) -> None:
        try:
            if self._omzetter_factory is None:
                import soxr
                factory = soxr.ResampleStream
            else:
                factory = self._omzetter_factory
            omzetter = factory(
                self.formaat.samplefrequentie, SAMPLEFREQUENTIE_VAN_DE_UITVOER,
                self.formaat.aantal_kanalen, dtype='float32',
            )
            while not self._stop.is_set():
                try:
                    blok = self._wachtrij.get(timeout=0.06)
                except Empty:
                    continue
                omgezet = omzetter.resample_chunk(blok)
                self._buffer.schrijf(omgezet)
        except Exception as fout:
            self._werkfout = fout
            self._stop.set()

    def _stuur_naar_kabel(self, outdata, frames, tijdinformatie, status) -> None:
        invoer = self._buffer.lees(frames)
        self._uitvoercallback(invoer, outdata, frames, tijdinformatie, status)

    def start(self) -> None:
        self._stop.clear()
        self._werkfout = None
        self._werkdraad = threading.Thread(target=self._omzetten,
                                           name='Microfoon-sampleomzetting', daemon=True)
        self._werkdraad.start()
        try:
            self._invoer.start()
        except Exception as fout:
            raise AudioApparaatOpenFout('invoer', fout) from fout
        # Een klein voorloopblok verkleint de kans op stilte bij de eerste mix.
        self._stop.wait(timeout=0.035)
        if self._werkfout:
            raise self._werkfout
        try:
            self._uitvoer.start()
        except Exception as fout:
            if self._uitvoer_api != 'Windows WASAPI':
                raise AudioApparaatOpenFout('uitvoer', fout) from fout
            # Ook als pas .start() wordt geweigerd moet de oude stream
            # eerst volledig worden vrijgegeven.
            omschrijving = str(fout).casefold()
            if not ('paerrorcode -9996' in omschrijving and
                    'invalid device' in omschrijving):
                raise AudioApparaatOpenFout('uitvoer', fout) from fout
            reserve = zoek_veilige_directsound_kabeluitvoer(self._bibliotheek)
            if reserve is None:
                raise AudioApparaatOpenFout('uitvoer', fout) from fout
            try:
                self._uitvoer.close(ignore_errors=False)
            except Exception as sluitfout:
                raise AudioApparaatOpenFout('uitvoer', sluitfout) from sluitfout
            try:
                self._uitvoer = self._open_uitvoer(reserve)
                self._uitvoer_api = 'Windows DirectSound'
                self._uitvoer.start()
            except Exception as reservefout:
                raise AudioApparaatOpenFout('uitvoer', reservefout) from reservefout

    def stop(self, ignore_errors: bool = False) -> None:
        self._stop.set()
        eerste_fout = None
        for stream in (self._uitvoer, self._invoer):
            if stream is None or not getattr(stream, 'active', False):
                continue
            try:
                stream.stop(ignore_errors=ignore_errors)
            except Exception as fout:
                if eerste_fout is None:
                    eerste_fout = fout
        if self._werkdraad is not None and self._werkdraad.is_alive():
            self._werkdraad.join(timeout=1.0)
        if eerste_fout is not None and not ignore_errors:
            raise eerste_fout

    def close(self, ignore_errors: bool = False) -> None:
        self._stop.set()
        eerste_fout = None
        try:
            self.stop(ignore_errors=ignore_errors)
        except Exception as fout:
            eerste_fout = fout
        for stream in (self._uitvoer, self._invoer):
            if stream is None:
                continue
            try:
                stream.close(ignore_errors=ignore_errors)
            except Exception as fout:
                if eerste_fout is None:
                    eerste_fout = fout
        if eerste_fout is not None and not ignore_errors:
            raise eerste_fout


def zoek_veilige_directsound_kabeluitvoer(audiobibliotheek: Any) -> int | None:
    """Zoek één echte VB-CABLE-uitgang bij Windows DirectSound.

    Alleen bedoeld als WASAPI CABLE Input zelf niet opent. Er wordt nooit
    teruggevallen op de systeemstandaard, een headset of een andere kabel.
    DirectSound kan apparaatnamen afkorten; het stabiele begin blijft herkenbaar.
    """
    try:
        apparaten = audiobibliotheek.query_devices()
        hostapis = audiobibliotheek.query_hostapis()
    except (AttributeError, TypeError, ValueError, OSError):
        return None
    kandidaten: list[int] = []
    for nummer, apparaat in enumerate(apparaten):
        try:
            naam = apparaat['name'].strip().casefold()
            hostnummer = apparaat['hostapi']
            if (naam.startswith('cable input (vb-audio virtual')
                    and apparaat['max_output_channels'] >= 2
                    and isinstance(hostnummer, int)
                    and 0 <= hostnummer < len(hostapis)
                    and hostapis[hostnummer]['name'].casefold() == 'windows directsound'):
                kandidaten.append(nummer)
        except (TypeError, ValueError, AttributeError, KeyError, IndexError):
            continue
    # Meerdere mogelijke VB-CABLE-uitgangen zijn ambigu. Nooit gokken.
    return kandidaten[0] if len(kandidaten) == 1 else None


class _AdapterVoorGescheidenStreams:
    """Geef de bestaande begrensde Windows-startretry dezelfde Stream-API."""

    def __init__(self, audiobibliotheek: Any, formaat: MicrofoonFormaat,
                 uitvoer_overschrijven: int | None = None) -> None:
        self.audiobibliotheek = audiobibliotheek
        self.formaat = formaat
        self.uitvoer_overschrijven = uitvoer_overschrijven

    def Stream(self, **kwargs):
        return GescheidenMicrofoonEnUitvoer(
            self.audiobibliotheek, kwargs['device'][0],
            (self.uitvoer_overschrijven if self.uitvoer_overschrijven is not None
             else kwargs['device'][1]),
            self.formaat, kwargs['callback'],
        )


def maak_streamadapter(audiobibliotheek: Any, formaat: MicrofoonFormaat,
                       *, uitvoer_overschrijven: int | None = None):
    return _AdapterVoorGescheidenStreams(
        audiobibliotheek, formaat, uitvoer_overschrijven
    )
