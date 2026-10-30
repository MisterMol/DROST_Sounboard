"""Lees kleine WAV-fragmenten in voor de geluidstest, zonder audiostreams te openen.

We zetten het bestand vooraf om naar float32, stereo en 48 kHz. Daardoor
hoeft de uitvoerstroom tijdens het afspelen alleen kant-en-klare bytes door
te sturen. Dat voorkomt schijfwerk en omzetten binnen de audioverwerking.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import math
from pathlib import Path
import wave

import numpy as np


SAMPLEFREQUENTIE_VAN_DE_UITVOER = 48_000
AANTAL_UITVOERKANALEN = 2
MAXIMALE_GELUIDSDUUR_IN_SECONDEN = 120
MAXIMALE_BESTANDSGROOTTE_IN_BYTES = 40 * 1024 * 1024
STANDAARD_GELUIDSVOLUME = 1.0


def versterk_samples_zonder_digitaal_te_oversturen(samples: np.ndarray, volume: float) -> np.ndarray:
    """Versterk de bron; behoud de golfvorm wanneer 200% digitale ruimte tekortkomt.

    Het opgegeven volume is een gevraagde versterking, geen garantie op 2 keer
    zo luid. Als een bron al tegen 0 dBFS zit, zouden harde clips hoorbare
    vervorming veroorzaken. Daarom schalen we in dat geval het hele fragment.
    Deze bewerking vindt buiten de realtime audiocallback plaats.
    """
    samples *= volume
    hoogste_piek = float(np.max(np.abs(samples))) if samples.size else 0.0
    if hoogste_piek > 1.0:
        samples *= 1.0 / hoogste_piek
    return samples


class GeluidsbestandOngeldigFout(ValueError):
    """Meld duidelijk waarom een geluidsbestand nog niet gebruikt kan worden."""


@dataclass(frozen=True)
class VoorbereidGeluidsfragment:
    """Een gecontroleerd geluid met alle gegevens voor uitvoer en auditlog."""

    naam_van_het_geluid: str
    bestandspad: Path
    vingerafdruk_van_audio: str
    ruwe_float32_stereo_audio: bytes
    aantal_frames: int
    oorspronkelijke_samplefrequentie: int
    oorspronkelijke_aantal_kanalen: int
    ingesteld_volume: float
    # Extra metadata met defaults houdt bestaande WAV-tests en oudere spelers werkend.
    fragment_begint_bij_seconden: float = 0.0
    bronduur_in_seconden: float | None = None
    fragment_ingekort: bool = False
    normalisatiestand: str = 'uit'
    normalisatiefactor: float = 1.0

    @property
    def duur_in_seconden(self) -> float:
        return self.aantal_frames / SAMPLEFREQUENTIE_VAN_DE_UITVOER


def _controleer_bestandspad_voordat_we_gaan_lezen(bestandspad: str | Path) -> Path:
    """Weiger lege of onverwachte parameters voordat ze naar wave.open gaan."""
    if not isinstance(bestandspad, (str, Path)):
        raise GeluidsbestandOngeldigFout(
            "GELUID-001: verwacht een bestandspad als tekst of Path, "
            f"maar ontving {type(bestandspad).__name__}."
        )
    if not str(bestandspad).strip():
        raise GeluidsbestandOngeldigFout("GELUID-002: er is geen bestand gekozen.")

    gekozen_bestand = Path(bestandspad).expanduser()
    if gekozen_bestand.suffix.casefold() != ".wav":
        raise GeluidsbestandOngeldigFout(
            "GELUID-003: kies een WAV-bestand. MP3 en MP4 volgen in een latere fase."
        )
    if not gekozen_bestand.is_file():
        raise GeluidsbestandOngeldigFout(
            f"GELUID-004: het gekozen WAV-bestand bestaat niet: {gekozen_bestand.name}."
        )

    grootte_in_bytes = gekozen_bestand.stat().st_size
    if grootte_in_bytes == 0:
        raise GeluidsbestandOngeldigFout("GELUID-005: dit WAV-bestand is leeg.")
    if grootte_in_bytes > MAXIMALE_BESTANDSGROOTTE_IN_BYTES:
        raise GeluidsbestandOngeldigFout(
            "GELUID-006: het bestand is groter dan 40 MiB. "
            "Gebruik voor deze test een kort fragment."
        )
    return gekozen_bestand


def _zet_pcm_samples_om_naar_float32(
    ruwe_pcm_audio: bytes, aantal_bytes_per_sample: int
):
    """Maak van integer PCM getallen tussen min één en plus één.

    WAV met 8 bits gebruikt unsigned getallen; de andere hier ondersteunde
    PCM-formaten zijn signed little-endian. Een onjuiste interpretatie geeft
    hele harde ruis, dus iedere breedte heeft bewust een eigen omzetting.
    """
    import numpy as np

    if aantal_bytes_per_sample == 1:
        return (np.frombuffer(ruwe_pcm_audio, dtype=np.uint8).astype(np.float32) - 128.0) / 128.0
    if aantal_bytes_per_sample == 2:
        return np.frombuffer(ruwe_pcm_audio, dtype="<i2").astype(np.float32) / 32768.0
    if aantal_bytes_per_sample == 3:
        drie_bytes_per_sample = np.frombuffer(ruwe_pcm_audio, dtype=np.uint8).reshape(-1, 3)
        hele_samplewaarden = (
            drie_bytes_per_sample[:, 0].astype(np.int32)
            | (drie_bytes_per_sample[:, 1].astype(np.int32) << 8)
            | (drie_bytes_per_sample[:, 2].astype(np.int32) << 16)
        )
        # Zonder sign extension zouden negatieve 24-bit samples als
        # extreem positieve getallen klinken. Dit veroorzaakt harde vervorming.
        hele_samplewaarden[hele_samplewaarden >= 0x800000] -= 0x1000000
        return hele_samplewaarden.astype(np.float32) / 8_388_608.0
    if aantal_bytes_per_sample == 4:
        return np.frombuffer(ruwe_pcm_audio, dtype="<i4").astype(np.float32) / 2_147_483_648.0
    raise GeluidsbestandOngeldigFout(
        f"GELUID-007: PCM met {aantal_bytes_per_sample * 8} bits is niet ondersteund."
    )


def _zet_audio_om_naar_stereo_op_48000_hertz(
    ruwe_pcm_audio: bytes,
    aantal_bytes_per_sample: int,
    aantal_invoerkanalen: int,
    samplefrequentie_in_hertz: int,
    ingesteld_volume: float,
) -> tuple[bytes, int]:
    """Maak voor het uitvoerapparaat altijd dezelfde indeling.

    Lineair resamplen is licht en voor deze korte geluidstest voldoende.
    Voor de definitieve import bouwen we later een hoogwaardige converter,
    zodat ook langere muziekfragmenten netjes worden verwerkt.
    """
    import numpy as np

    samples_als_float32 = _zet_pcm_samples_om_naar_float32(
        ruwe_pcm_audio, aantal_bytes_per_sample
    )
    if len(samples_als_float32) % aantal_invoerkanalen != 0:
        raise GeluidsbestandOngeldigFout(
            "GELUID-008: het audiobestand eindigt midden in een sampleframe."
        )

    samples_per_frame = samples_als_float32.reshape(-1, aantal_invoerkanalen)
    frames_in_bron = len(samples_per_frame)
    if frames_in_bron == 0:
        raise GeluidsbestandOngeldigFout("GELUID-009: het bestand bevat geen audiosamples.")

    if aantal_invoerkanalen == 1:
        # Een monobestand moet op beide virtuele kanalen te horen zijn.
        stereo_audio = np.repeat(samples_per_frame, AANTAL_UITVOERKANALEN, axis=1)
    else:
        stereo_audio = samples_per_frame

    if samplefrequentie_in_hertz != SAMPLEFREQUENTIE_VAN_DE_UITVOER:
        aantal_frames_uitvoer = max(
            1, round(frames_in_bron * SAMPLEFREQUENTIE_VAN_DE_UITVOER / samplefrequentie_in_hertz)
        )
        bronposities = np.arange(frames_in_bron, dtype=np.float64)
        doelposities = np.minimum(
            np.arange(aantal_frames_uitvoer, dtype=np.float64)
            * (samplefrequentie_in_hertz / SAMPLEFREQUENTIE_VAN_DE_UITVOER),
            frames_in_bron - 1,
        )
        omgezette_audio = np.empty((aantal_frames_uitvoer, AANTAL_UITVOERKANALEN), dtype=np.float32)
        for kanaalnummer in range(AANTAL_UITVOERKANALEN):
            omgezette_audio[:, kanaalnummer] = np.interp(
                doelposities, bronposities, stereo_audio[:, kanaalnummer]
            ).astype(np.float32)
        stereo_audio = omgezette_audio

    # Bij deze test beperken we het volume om een onverwacht hard bestand
    # niet op volle sterkte de virtuele microfoon in te sturen.
    uitvoer_audio = np.ascontiguousarray(
        versterk_samples_zonder_digitaal_te_oversturen(stereo_audio, ingesteld_volume), dtype="<f4"
    )
    return uitvoer_audio.tobytes(), len(uitvoer_audio)


def lees_en_bereid_wav_geluid_voor(
    bestandspad: str | Path,
    ingesteld_volume: float = STANDAARD_GELUIDSVOLUME,
) -> VoorbereidGeluidsfragment:
    """Open een korte ongecomprimeerde WAV en bereid veilige uitvoer voor.

    Een WAV met MP3 of IEEE-float codering wordt hier nog afgewezen. Dat is
    bewust: de standaard wave-lezer van Python 3.13 leest alleen PCM WAV.
    """
    if isinstance(ingesteld_volume, bool) or not isinstance(ingesteld_volume, (int, float)):
        raise GeluidsbestandOngeldigFout(
            "GELUID-010: volume moet een getal tussen nul en twee zijn; "
            f"ontvangen {type(ingesteld_volume).__name__}."
        )
    if not math.isfinite(ingesteld_volume) or not 0.0 <= ingesteld_volume <= 2.0:
        raise GeluidsbestandOngeldigFout("GELUID-011: volume moet tussen 0 en 2 liggen.")

    gekozen_bestand = _controleer_bestandspad_voordat_we_gaan_lezen(bestandspad)
    try:
        with wave.open(str(gekozen_bestand), "rb") as geopend_wav_bestand:
            aantal_kanalen = geopend_wav_bestand.getnchannels()
            samplefrequentie = geopend_wav_bestand.getframerate()
            aantal_bytes_per_sample = geopend_wav_bestand.getsampwidth()
            aantal_frames = geopend_wav_bestand.getnframes()
            compressiesoort = geopend_wav_bestand.getcomptype()

            if compressiesoort != "NONE":
                raise GeluidsbestandOngeldigFout(
                    f"GELUID-012: dit WAV-bestand gebruikt compressie {compressiesoort}; alleen PCM werkt."
                )
            if aantal_kanalen not in (1, 2):
                raise GeluidsbestandOngeldigFout(
                    f"GELUID-013: verwacht mono of stereo, ontvangen {aantal_kanalen} kanalen."
                )
            if aantal_bytes_per_sample not in (1, 2, 3, 4):
                raise GeluidsbestandOngeldigFout(
                    f"GELUID-014: {aantal_bytes_per_sample * 8} bit PCM is niet ondersteund."
                )
            if not 8_000 <= samplefrequentie <= 96_000:
                raise GeluidsbestandOngeldigFout(
                    "GELUID-015: samplefrequentie valt buiten 8.000 tot 96.000 Hz."
                )
            if aantal_frames == 0:
                raise GeluidsbestandOngeldigFout("GELUID-016: het WAV-bestand bevat geen frames.")
            als_seconden = aantal_frames / samplefrequentie
            if als_seconden > MAXIMALE_GELUIDSDUUR_IN_SECONDEN:
                raise GeluidsbestandOngeldigFout(
                    "GELUID-017: een geluid mag in deze test maximaal 120 seconden duren."
                )

            ruwe_pcm_audio = geopend_wav_bestand.readframes(aantal_frames)
            verwachte_aantal_bytes = aantal_frames * aantal_kanalen * aantal_bytes_per_sample
            if len(ruwe_pcm_audio) != verwachte_aantal_bytes:
                raise GeluidsbestandOngeldigFout(
                    "GELUID-018: het WAV-bestand bevat minder audiodata dan de header aangeeft. "
                    f"Verwacht {verwachte_aantal_bytes} bytes, gelezen {len(ruwe_pcm_audio)}."
                )
    except (OSError, EOFError, wave.Error) as oorspronkelijke_fout:
        raise GeluidsbestandOngeldigFout(
            f"GELUID-019: het WAV-bestand '{gekozen_bestand.name}' kon niet worden gelezen."
        ) from oorspronkelijke_fout

    bytes_voor_uitvoer, aantal_frames_uitvoer = _zet_audio_om_naar_stereo_op_48000_hertz(
        ruwe_pcm_audio=ruwe_pcm_audio,
        aantal_bytes_per_sample=aantal_bytes_per_sample,
        aantal_invoerkanalen=aantal_kanalen,
        samplefrequentie_in_hertz=samplefrequentie,
        ingesteld_volume=float(ingesteld_volume),
    )
    return VoorbereidGeluidsfragment(
        naam_van_het_geluid=gekozen_bestand.stem,
        bestandspad=gekozen_bestand,
        vingerafdruk_van_audio=hashlib.sha256(ruwe_pcm_audio).hexdigest(),
        ruwe_float32_stereo_audio=bytes_voor_uitvoer,
        aantal_frames=aantal_frames_uitvoer,
        oorspronkelijke_samplefrequentie=samplefrequentie,
        oorspronkelijke_aantal_kanalen=aantal_kanalen,
        ingesteld_volume=float(ingesteld_volume),
    )
