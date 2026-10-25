"""Exporteer één bibliotheekgeluid als MP3, MP4 met audio of stille GIF.

De geselecteerde audiotijden komen uit dezelfde SQLite-instellingen als de
fragmenteditor. FFmpeg draait in een gewone HTTP-werkdraad en raakt nooit
de realtime audiocallback aan. Originele media worden uitsluitend gelezen.
"""
from __future__ import annotations

import math
from pathlib import Path
import re
import shutil
import subprocess

from app.diagnostiek.vensterloze_windowsprocessen import geef_opstartopties_zonder_console
from tempfile import NamedTemporaryFile
import unicodedata

from app.audio.mp4_verwerken import geef_meegeleverde_ffmpeg
from app.webinterface.favorieten_en_instellingen import controleer_afspeelinstellingen

FORMATTEN = {'mp3': ('audio/mpeg', '.mp3'), 'mp4': ('video/mp4', '.mp4'), 'gif': ('image/gif', '.gif'), 'afbeelding': ('', '')}
MAX_BRONBESTAND = 250 * 1024 * 1024
MAX_EXPORTBESTAND = {'mp3': 12 * 1024 * 1024, 'mp4': 160 * 1024 * 1024, 'gif': 32 * 1024 * 1024, 'afbeelding': 8 * 1024 * 1024}
MAX_GIF_DUUR = 12.0
MAX_GIF_NAAR_MP4_DUUR = 120.0


class LosseMediaExportFout(ValueError):
    """Verwachte fout met een concrete exportcode voor scherm en logging."""


def maak_veilige_downloadnaam(naam: str, formaat: str) -> str:
    """Gebruik nooit gebruikersinvoer rechtstreeks in een HTTP-header.

    Dat voorkomt dat een geluidsnaam met bijvoorbeeld regeleinden of quotes
    onbedoeld de Content-Disposition-header beïnvloedt.
    """
    basis = unicodedata.normalize('NFKD', naam).encode('ascii', 'ignore').decode('ascii')
    basis = re.sub(r'[^A-Za-z0-9_-]+', '_', basis).strip('_-')[:70]
    return f'{basis or "geluid"}.{formaat}'


def geef_mogelijke_exportformaten(
    bediening, media_map: Path, geluid_id: str, *, bron: Path | None = None, instellingen=None,
) -> list[str]:
    """Geef alleen opties die we echt kunnen downloaden.

    We baseren de keuzes op bestaande bestanden, niet op alleen een extensie
    in de browser. Daardoor verdwijnt een optie als de bron is verwijderd.
    Het optioneel meegegeven item voorkomt dubbele databaselezingen bij een
    bibliotheek met honderden bestanden.
    """
    if bron is None:
        item = bediening.zoek_geluid_met_id(geluid_id)
        bron = Path(item.bestandspad)
    if not bron.is_file():
        return []
    if instellingen is None:
        instellingen = bediening.favorieten.geef_instellingen_van_geluid(geluid_id)
    afbeelding = zoek_gekoppelde_afbeelding(media_map, instellingen.afbeelding_bestandsnaam)
    is_gif = afbeelding is not None and afbeelding.suffix.lower() == '.gif'
    is_video = bron.suffix.lower() == '.mp4'
    opties = ['mp3'] if bron.suffix.lower() in ('.mp3', '.wav', '.mp4') else []
    if is_video or is_gif:
        opties.append('mp4')
    if afbeelding is not None and not is_gif:
        opties.append('afbeelding')
    if is_gif or is_video:
        opties.append('gif')
    return opties


def zoek_gekoppelde_afbeelding(media_map: Path, bestandsnaam: str | None) -> Path | None:
    """Bied uitsluitend de originele, lokaal beheerde afbeelding aan.

    Een databaseverwijzing mag geen eigen bestandspad leveren. We controleren
    daarom UUID-naam, mapgrenzen, maximale grootte en bestandshandtekening.
    """
    if not isinstance(bestandsnaam, str) or not re.fullmatch(
        r'[0-9a-f-]{36}\.(?:png|jpg|jpeg|webp|gif)', bestandsnaam
    ):
        return None
    afbeeldingenmap = (media_map / 'afbeeldingen').resolve()
    pad = (afbeeldingenmap / bestandsnaam).resolve()
    if not pad.is_relative_to(afbeeldingenmap) or not pad.is_file():
        return None
    if pad.stat().st_size <= 0 or pad.stat().st_size > MAX_EXPORTBESTAND['afbeelding']:
        return None
    with pad.open('rb') as bestand:
        begin = bestand.read(16)
    geldig = {
        '.png': begin.startswith(b'\x89PNG\r\n\x1a\n'),
        '.jpg': begin.startswith(b'\xff\xd8\xff'),
        '.jpeg': begin.startswith(b'\xff\xd8\xff'),
        '.webp': begin.startswith(b'RIFF') and begin[8:12] == b'WEBP',
        '.gif': begin.startswith((b'GIF87a', b'GIF89a')),
    }
    return pad if geldig.get(pad.suffix.lower(), False) else None


def zoek_gekoppelde_gif(media_map: Path, bestandsnaam: str | None) -> Path | None:
    """Een GIF moet ook echt een GIF zijn. Een PNG-miniatuur telt niet mee."""
    pad = zoek_gekoppelde_afbeelding(media_map, bestandsnaam)
    return pad if pad is not None and pad.suffix.lower() == '.gif' else None


def controleer_geselecteerd_fragment(
    bediening, geluid_id: str, aangepast_begin: float | None, aangepaste_duur: float | None,
) -> tuple[Path, float, float, str]:
    """Controleer op bronduur en maximaal 120 seconden vóór FFmpeg start.

    In de editor mag je direct een nog niet opgeslagen selectie exporteren.
    In de bibliotheek gebruiken we gewoon de reeds opgeslagen knippunten.
    """
    item = bediening.zoek_geluid_met_id(geluid_id)
    bron = Path(item.bestandspad)
    if not bron.is_file() or bron.suffix.lower() not in ('.mp3', '.wav', '.mp4'):
        raise LosseMediaExportFout('EXP-001: dit geluidsbestand ontbreekt of wordt niet ondersteund.')
    if bron.stat().st_size > MAX_BRONBESTAND:
        raise LosseMediaExportFout('EXP-002: het geluidsbestand is groter dan 250 MiB.')
    opgeslagen = bediening.favorieten.geef_instellingen_van_geluid(geluid_id)
    begin = opgeslagen.begint_bij_seconden if aangepast_begin is None else aangepast_begin
    duur = opgeslagen.maximale_duur_seconden if aangepaste_duur is None else aangepaste_duur
    # Gebruik exact dezelfde grenzen als bij het afspelen, inclusief NaN en null.
    try:
        controleer_afspeelinstellingen(begin, opgeslagen.volume, duur)
    except ValueError as fout:
        raise LosseMediaExportFout('EXP-003: begin of duur is ongeldig. Maximaal 120 seconden.') from fout
    bronduur = bediening.geef_echte_duur_van_geluid(item)
    if bronduur is None or not math.isfinite(bronduur) or begin >= bronduur:
        raise LosseMediaExportFout('EXP-004: beginpunt ligt buiten het bronbestand.')
    werkelijk = min(float(duur), bronduur - float(begin), 120.0)
    if werkelijk < 0.001:
        raise LosseMediaExportFout('EXP-005: het gekozen fragment is te kort.')
    return bron, float(begin), werkelijk, item.eigen_naam


def _voer_ffmpeg_uit(commando: list[str], doel: Path, formaat: str) -> None:
    """Zorg voor maximale verwerkingstijd en een gecontroleerd eindbestand.

    De uitvoer wordt niet in RAM geladen. Bij een fout bewaren we de originele
    FFmpeg-uitvoer in de Python-traceback, maar geven een korte melding aan UI.
    """
    try:
        resultaat = subprocess.run(
            commando, capture_output=True, timeout=240 if formaat != 'mp3' else 100,
            check=False,
            **geef_opstartopties_zonder_console(),
        )
    except (OSError, subprocess.TimeoutExpired) as fout:
        raise LosseMediaExportFout('EXP-006: converter kon niet starten of de tijdslimiet is bereikt.') from fout
    if resultaat.returncode != 0:
        uitleg = resultaat.stderr.decode('utf-8', errors='replace')[-1200:]
        raise LosseMediaExportFout(f'EXP-007: converter kon het bestand niet maken: {uitleg}')
    if not doel.is_file() or doel.stat().st_size <= 20:
        raise LosseMediaExportFout('EXP-008: conversie leverde geen bruikbaar bestand op.')
    if doel.stat().st_size > MAX_EXPORTBESTAND[formaat]:
        raise LosseMediaExportFout(f'EXP-009: de {formaat.upper()} is te groot. Kies een korter fragment.')
    with doel.open('rb') as bestand:
        handtekening = bestand.read(16)
    if formaat == 'gif' and not handtekening.startswith((b'GIF87a', b'GIF89a')):
        raise LosseMediaExportFout('EXP-010: uitvoerbestand is geen geldige GIF.')
    if formaat == 'mp4' and handtekening[4:8] != b'ftyp':
        raise LosseMediaExportFout('EXP-011: uitvoerbestand is geen geldige MP4.')
    if formaat == 'mp3' and not (handtekening.startswith(b'ID3') or (handtekening[0] == 255 and handtekening[1] & 224 == 224)):
        raise LosseMediaExportFout('EXP-012: uitvoerbestand is geen geldige MP3.')


def exporteer_geluid_als_los_bestand(
    bediening, media_map: Path, geluid_id: str, formaat: str,
    begin: float | None = None, duur: float | None = None,
) -> tuple[Path, str, str, float]:
    """Lever een tijdelijk bestand voor de browserdownload, zonder bronwijziging.

    MP3 bevat alleen de geknipte audio, op de originele geluidssterkte.
    MP4 bevat het gekozen beeld én het bijbehorende audiodeel als AAC.
    GIF is de los gekoppelde animatie, of een maximaal 12 s lange conversie
    van het videofragment. Dat laatste voorkomt gigantische GIF-bestanden.
    """
    if type(formaat) is not str or formaat not in FORMATTEN:
        raise LosseMediaExportFout('EXP-013: kies MP3, MP4, afbeelding of GIF.')
    bron, begin_seconden, selectie_duur, naam = controleer_geselecteerd_fragment(
        bediening, geluid_id, begin, duur,
    )
    mogelijk = geef_mogelijke_exportformaten(bediening, media_map, geluid_id)
    if formaat not in mogelijk:
        raise LosseMediaExportFout(f'EXP-014: voor dit geluid is geen {formaat.upper()} beschikbaar.')
    instellingen = bediening.favorieten.geef_instellingen_van_geluid(geluid_id)
    gekoppelde_gif = zoek_gekoppelde_gif(media_map, instellingen.afbeelding_bestandsnaam)
    gekoppelde_afbeelding = zoek_gekoppelde_afbeelding(media_map, instellingen.afbeelding_bestandsnaam)
    inhoudstype, extensie = FORMATTEN[formaat]
    if formaat == 'afbeelding':
        if gekoppelde_afbeelding is None or gekoppelde_afbeelding.suffix.lower() == '.gif':
            raise LosseMediaExportFout('EXP-016: er is geen losse afbeelding beschikbaar.')
        extensie = gekoppelde_afbeelding.suffix.lower()
        inhoudstype = {'.png': 'image/png', '.jpg': 'image/jpeg',
                       '.jpeg': 'image/jpeg', '.webp': 'image/webp'}[extensie]
    tijdelijk_pad = None
    try:
        with NamedTemporaryFile(prefix='drost_losse_export_', suffix=extensie, delete=False) as tijdelijk:
            tijdelijk_pad = Path(tijdelijk.name)
        if formaat == 'afbeelding':
            # Kopieer het eigen bestand byte-voor-byte, zonder overbodige
            # hercompressie of onverwacht kwaliteitsverlies.
            shutil.copyfile(gekoppelde_afbeelding, tijdelijk_pad)
            werkelijk_geexporteerd = 0.0
        elif formaat == 'gif' and gekoppelde_gif is not None:
            # Een gekoppelde GIF moet als originele animatie mee, zonder dat
            # ffmpeg er een andere framerate of nieuwe kleuren van maakt.
            shutil.copyfile(gekoppelde_gif, tijdelijk_pad)
            werkelijk_geexporteerd = 0.0  # De GIF heeft een eigen tijdlijn.
        else:
            ffmpeg = geef_meegeleverde_ffmpeg()
            gif_naar_mp4 = formaat == 'mp4' and bron.suffix.lower() != '.mp4'
            bron_voor_ffmpeg = gekoppelde_gif if gif_naar_mp4 else bron
            if gif_naar_mp4 and bron_voor_ffmpeg is None:
                raise LosseMediaExportFout('EXP-014: er is geen video of gekoppelde GIF beschikbaar.')
            daadwerkelijk_begin = 0.0 if gif_naar_mp4 else begin_seconden
            werkelijk_geexporteerd = (
                min(selectie_duur, MAX_GIF_NAAR_MP4_DUUR) if gif_naar_mp4 else
                min(selectie_duur, MAX_GIF_DUUR) if formaat == 'gif' else selectie_duur
            )
            commando = [ffmpeg, '-nostdin', '-hide_banner', '-loglevel', 'error', '-y', '-threads', '2']
            if gif_naar_mp4:
                # De GIF wordt geloopt voor het beeld. De audio komt uit de
                # oorspronkelijke WAV/MP3, met precies dezelfde knipselectie.
                # Twee expliciete inputs voorkomen dat -an of de video zonder
                # audiokanaal een onbedoeld stil MP4-bestand oplevert.
                commando.extend(['-stream_loop', '-1', '-i', str(bron_voor_ffmpeg)])
                commando.extend(['-ss', f'{begin_seconden:.6f}', '-i', str(bron)])
            else:
                # Deze bron bevat zelf audio én video. Beide sporen moeten
                # vanaf hetzelfde tijdstip worden geknipt en opnieuw gecodeerd.
                commando.extend(['-ss', f'{daadwerkelijk_begin:.6f}', '-i', str(bron_voor_ffmpeg)])
            commando.extend(['-t', f'{werkelijk_geexporteerd:.6f}'])
            if formaat == 'mp3':
                commando.extend(['-map', '0:a:0', '-vn', '-c:a', 'libmp3lame',
                                 '-b:a', '192k', '-ar', '48000', '-ac', '2', '-threads:a', '1'])
            elif formaat == 'mp4':
                # Het MP4-resultaat bevat altijd beeld én geluid. Bij een
                # gekoppelde GIF komt audio uit input 1, anders uit de MP4.
                # AAC is geschikt voor moderne browsers en Windows-spelers.
                audiobron = '1:a:0' if gif_naar_mp4 else '0:a:0'
                commando.extend(['-map', '0:v:0', '-map', audiobron,
                                 '-c:v', 'libx264', '-preset', 'veryfast',
                                 '-crf', '25', '-pix_fmt', 'yuv420p',
                                 '-vf', 'scale=w=\'min(1280,iw)\':h=-2:flags=lanczos',
                                 '-c:a', 'aac', '-b:a', '192k', '-ar', '48000', '-ac', '2',
                                 '-movflags', '+faststart', '-threads:v', '2', '-threads:a', '1'])
            else:
                # Eén filterketen met beeldspecifiek kleurenpalet voor kleine,
                # herkenbare GIF's. GIF bevat nooit een audiospoor.
                commando.extend([
                    '-filter_complex',
                    "[0:v]fps=10,scale=w='min(480,iw)':h=-2:flags=lanczos,split[a][b];"
                    '[a]palettegen=max_colors=128[p];[b][p]paletteuse=dither=bayer[gifuit]',
                    '-map', '[gifuit]', '-an', '-loop', '0',
                ])
            # Geen onbedoelde tags, cameragegevens of hoofdstuktitels van de bron meenemen.
            commando.extend(['-map_metadata', '-1', '-map_chapters', '-1'])
            commando.append(str(tijdelijk_pad))
            _voer_ffmpeg_uit(commando, tijdelijk_pad, formaat)
        # Ook gekopieerde GIF's worden vooraf gecontroleerd op formaat en grootte.
        if formaat == 'gif' and gekoppelde_gif is not None:
            if tijdelijk_pad.stat().st_size > MAX_EXPORTBESTAND['gif']:
                raise LosseMediaExportFout('EXP-009: deze GIF is groter dan het toegestane maximum.')
        downloadnaam = maak_veilige_downloadnaam(naam, extensie.lstrip('.'))
        return tijdelijk_pad, downloadnaam, inhoudstype, werkelijk_geexporteerd
    except Exception:
        if tijdelijk_pad is not None:
            tijdelijk_pad.unlink(missing_ok=True)
        raise
