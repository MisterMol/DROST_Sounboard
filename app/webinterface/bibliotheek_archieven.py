"""Maak draagbare bibliotheekarchieven met geluidsbestanden en instellingen.

Een export bevat echte media en een leesbaar manifest. Bij import bepalen wij
zélf veilige bestandsnamen. Nooit een pad uit het ZIP-bestand naar schijf
uitpakken, ook niet als het manifest of de ZIP-vermelding betrouwbaar lijkt.
"""
from __future__ import annotations

import json
import hashlib
from collections import defaultdict
from pathlib import Path, PurePosixPath
import re
import shutil
from tempfile import NamedTemporaryFile
from uuid import UUID, uuid4
from zipfile import ZipFile, BadZipFile, ZIP_STORED

from app.audio.mp3_en_wav_fragmenten import controleer_of_geluidsbestand_gebruikt_mag_worden
from app.webinterface.extra_geluidsinformatie import controleer_aanvullende_informatie

# Beperk de hoeveelheid schijf- en geheugenwerk bij een ongeluk of kwaadaardig ZIP-bestand.
MAX_GELUIDEN_PER_ARCHIEF = 500
MAX_ARCHIEFINHOUD_BYTES = 1024 * 1024 * 1024
# De app accepteert per afzonderlijk mediabestand maximaal 250 MiB.
MAX_BESTAND_BYTES = 250 * 1024 * 1024
MAX_MANIFEST_BYTES = 2 * 1024 * 1024
GEACCEPTEERDE_AUDIO = {'.wav', '.mp3', '.mp4'}
GEACCEPTEERDE_AFBEELDING = {'.png', '.jpg', '.jpeg', '.webp', '.gif'}


class OngeldigBibliotheekarchief(ValueError):
    """Melding die naar de gebruiker kan zonder een traceback kwijt te raken."""


def _controleer_geluidsnummers(geluid_ids: list[str] | None, alle_geluiden: list) -> list:
    index = {item.geluid_id: item for item in alle_geluiden}
    if geluid_ids is None:
        if len(alle_geluiden) > MAX_GELUIDEN_PER_ARCHIEF:
            raise OngeldigBibliotheekarchief('ARCH-001: exporteer maximaal 500 geluiden tegelijk.')
        return alle_geluiden
    if not isinstance(geluid_ids, list) or len(geluid_ids) > MAX_GELUIDEN_PER_ARCHIEF:
        raise OngeldigBibliotheekarchief('ARCH-001: selecteer maximaal 500 geluiden.')
    if any(not isinstance(nummer, str) or nummer not in index for nummer in geluid_ids):
        raise OngeldigBibliotheekarchief('ARCH-002: een geselecteerd geluid bestaat niet meer.')
    return [index[nummer] for nummer in dict.fromkeys(geluid_ids)]


def maak_draagbaar_bibliotheekarchief(bediening, media_map: Path, geluid_ids: list[str] | None) -> Path:
    """Lever een tijdelijk ZIP-pad op; de webserver stuurt het in blokken terug."""
    items = _controleer_geluidsnummers(geluid_ids, bediening.geluidenbibliotheek.geef_alle_geluiden())
    groepen = bediening.groepen.geef_alle_groepen()
    groepsnamen = {groep['id']: groep['naam'] for groep in groepen}
    groepouders = {groep['id']: groep.get('ouder_id') for groep in groepen}
    def groepspad(groep_id):
        pad = []
        gezien = set()
        while groep_id in groepsnamen and groep_id not in gezien:
            gezien.add(groep_id)
            pad.insert(0, groepsnamen[groep_id])
            groep_id = groepouders.get(groep_id)
        return pad
    gekoppeld = bediening.groepen.geef_groepsnummers_per_geluid()
    extra = bediening.extra_informatie.geef_alle_informatie()
    favorieten = bediening.favorieten.geef_alle_favorietplekken()
    manifest = {'versie': 2, 'type': 'DrostSoundboard', 'geluiden': []}
    if geluid_ids is None:
        # Lege mappen horen ook bij een volledige bibliotheekexport.
        manifest['mappen'] = [groepspad(groep['id']) for groep in groepen]
    totaal = 0
    tijdelijk_pad = None
    try:
        with NamedTemporaryFile(prefix='drost_export_', suffix='.zip', delete=False) as tijdelijk:
            tijdelijk_pad = Path(tijdelijk.name)
        with ZipFile(tijdelijk_pad, 'w', compression=ZIP_STORED, allowZip64=True) as archief:
            for item in items:
                bron = item.bestandspad
                extensie = bron.suffix.lower()
                if extensie not in GEACCEPTEERDE_AUDIO or not bron.is_file():
                    raise OngeldigBibliotheekarchief(f'ARCH-003: bronbestand ontbreekt bij {item.eigen_naam}.')
                if bron.stat().st_size > MAX_BESTAND_BYTES:
                    raise OngeldigBibliotheekarchief('ARCH-004: een bestand is groter dan 250 MiB.')
                totaal += bron.stat().st_size
                bestand_in_archief = f'geluiden/{item.geluid_id}{extensie}'
                archief.write(bron, bestand_in_archief)
                instellingen = bediening.favorieten.geef_instellingen_van_geluid(item.geluid_id)
                beschrijving = extra.get(item.geluid_id)
                afbeelding_in_archief = None
                if instellingen.afbeelding_bestandsnaam:
                    afbeelding = (media_map / 'afbeeldingen' / instellingen.afbeelding_bestandsnaam).resolve()
                    veilige_map = (media_map / 'afbeeldingen').resolve()
                    if (afbeelding.is_relative_to(veilige_map) and afbeelding.is_file()
                            and afbeelding.suffix.lower() in GEACCEPTEERDE_AFBEELDING):
                        afbeelding_in_archief = f'afbeeldingen/{item.geluid_id}{afbeelding.suffix.lower()}'
                        totaal += afbeelding.stat().st_size
                        archief.write(afbeelding, afbeelding_in_archief)
                if totaal > MAX_ARCHIEFINHOUD_BYTES:
                    raise OngeldigBibliotheekarchief('ARCH-005: archief groter dan 1 GiB. Exporteer minder geluiden.')
                manifest['geluiden'].append({
                    'oude_id': item.geluid_id, 'naam': item.eigen_naam,
                    'bron': bestand_in_archief, 'afbeelding': afbeelding_in_archief,
                    'begin': instellingen.begint_bij_seconden,
                    'duur': instellingen.maximale_duur_seconden,
                    'volume': instellingen.volume, 'beeldvoorkeur': instellingen.beeldvoorkeur,
                    'beschrijving': beschrijving.beschrijving if beschrijving else '',
                    'gesproken_tekst': beschrijving.gesproken_tekst if beschrijving else '',
                    'zoekwoorden': beschrijving.zoekwoorden if beschrijving else '',
                    'groepen': [groepsnamen[nummer] for nummer in gekoppeld.get(item.geluid_id, []) if nummer in groepsnamen],
                    'groepspaden': [groepspad(nummer) for nummer in gekoppeld.get(item.geluid_id, []) if nummer in groepsnamen],
                    'favoriet_plek': (favorieten.index(item.geluid_id) + 1) if item.geluid_id in favorieten else None,
                })
            manifest_inhoud = json.dumps(manifest, ensure_ascii=False, indent=2).encode('utf-8')
            if len(manifest_inhoud) > MAX_MANIFEST_BYTES or totaal + len(manifest_inhoud) > MAX_ARCHIEFINHOUD_BYTES:
                raise OngeldigBibliotheekarchief(
                    'ARCH-005: archief groter dan 1 GiB, inclusief metadata. Exporteer minder geluiden.')
            archief.writestr('manifest.json', manifest_inhoud)
        return tijdelijk_pad
    except Exception:
        if tijdelijk_pad is not None:
            tijdelijk_pad.unlink(missing_ok=True)
        raise


def _controleer_archief(archief: ZipFile) -> list[dict]:
    """Lees geen gebruikerspad en weigert zipbombs nog vóór er iets wordt toegevoegd."""
    bestandsregels = archief.infolist()
    if len(bestandsregels) > MAX_GELUIDEN_PER_ARCHIEF * 15 + 1:
        raise OngeldigBibliotheekarchief('ARCH-006: te veel onderdelen in het archief.')
    if sum(regel.file_size for regel in bestandsregels) > MAX_ARCHIEFINHOUD_BYTES:
        raise OngeldigBibliotheekarchief('ARCH-007: uitgepakte inhoud is groter dan 1 GiB.')
    manifest_regel = next((regel for regel in bestandsregels if regel.filename == 'manifest.json'), None)
    if not manifest_regel:
        # Ook een normale ZIP met MP3, WAV of MP4 in mappen mag als audiopack dienen.
        # Alle paden blijven uitsluitend ZIP-leden; ze worden nooit letterlijk uitgepakt.
        from app.webinterface.geluidsgroepen import controleer_groepsnaam
        geluiden = []
        gezien = set()
        for regel in bestandsregels:
            naam = regel.filename
            delen = PurePosixPath(naam).parts
            if (naam in gezien or not naam or naam.startswith('/') or '\\' in naam
                    or any(deel in ('.', '..') for deel in delen)
                    or any(deel.startswith('.') for deel in delen)):
                raise OngeldigBibliotheekarchief('ARCH-021: onveilig ZIP-pad of dubbel bestand.')
            gezien.add(naam)
            if regel.is_dir():
                continue
            extensie = PurePosixPath(naam).suffix.lower()
            if extensie not in GEACCEPTEERDE_AUDIO:
                # Metadata uit losse ZIPs wordt genegeerd; alleen media importeren.
                continue
            if regel.file_size > MAX_BESTAND_BYTES:
                raise OngeldigBibliotheekarchief('ARCH-004: een audiobestand is groter dan 250 MiB.')
            if len(geluiden) >= MAX_GELUIDEN_PER_ARCHIEF:
                raise OngeldigBibliotheekarchief('ARCH-001: maximaal 500 geluiden per audiopack.')
            groep = [controleer_groepsnaam(deel[:60]) for deel in delen[:-1]][:12]
            basisnaam = Path(delen[-1]).stem[:100] or 'Geluid'
            geluiden.append({'naam': basisnaam, 'bron': naam, 'afbeelding': None,
                             'groepen': [groep[-1]] if groep else [],
                             'groepspaden': [groep] if groep else [],
                             'begin': 0, 'duur': 120, 'volume': 1.0})
        if not geluiden:
            raise OngeldigBibliotheekarchief('ARCH-008: dit ZIP-bestand bevat geen ondersteunde geluiden.')
        return geluiden
    if manifest_regel.file_size > MAX_MANIFEST_BYTES:
        raise OngeldigBibliotheekarchief('ARCH-008: manifest is te groot.')
    try:
        manifest = json.loads(archief.read('manifest.json'))
    except (ValueError, UnicodeError, BadZipFile) as fout:
        raise OngeldigBibliotheekarchief('ARCH-009: manifest heeft ongeldige JSON.') from fout
    if (not isinstance(manifest, dict) or manifest.get('type') != 'DrostSoundboard'
            or manifest.get('versie') not in (1, 2) or not isinstance(manifest.get('geluiden'), list)
            or len(manifest['geluiden']) > MAX_GELUIDEN_PER_ARCHIEF):
        raise OngeldigBibliotheekarchief('ARCH-010: onbekend archiefformaat.')
    mappen = manifest.get('mappen', [])
    if (not isinstance(mappen, list) or len(mappen) > 2000
            or any(not isinstance(pad, list) or not 1 <= len(pad) <= 12 for pad in mappen)):
        raise OngeldigBibliotheekarchief('ARCH-025: ongeldige maplijst.')
    from app.webinterface.geluidsgroepen import controleer_groepsnaam
    for pad in mappen:
        for deel in pad:
            controleer_groepsnaam(deel)
    toegelaten = {'manifest.json'}
    alle_namen = {regel.filename for regel in bestandsregels}
    if len(alle_namen) != len(bestandsregels):
        raise OngeldigBibliotheekarchief('ARCH-019: dubbele bestandsnamen in het ZIP-bestand.')
    from app.webinterface.geluidsgroepen import controleer_groepsnaam
    for geluid in manifest['geluiden']:
        if not isinstance(geluid, dict):
            raise OngeldigBibliotheekarchief('ARCH-011: geluidsgegevens missen velden.')
        bron = geluid.get('bron')
        if not isinstance(bron, str) or not re.fullmatch(r'geluiden/[0-9a-f-]{36}\.(mp3|wav|mp4)', bron):
            raise OngeldigBibliotheekarchief('ARCH-012: onveilige geluidsbestandsnaam.')
        try:
            UUID(bron.split('/')[-1].split('.')[0])
        except ValueError as fout:
            raise OngeldigBibliotheekarchief('ARCH-012: ongeldig geluidsnummer.') from fout
        gekoppelde_afbeelding = geluid.get('afbeelding')
        if gekoppelde_afbeelding is not None and (not isinstance(gekoppelde_afbeelding, str) or
                not re.fullmatch(r'afbeeldingen/[0-9a-f-]{36}\.(png|jpg|jpeg|webp|gif)', gekoppelde_afbeelding)):
            raise OngeldigBibliotheekarchief('ARCH-013: onveilige afbeeldingsbestandsnaam.')
        if not isinstance(geluid.get('naam'), str) or not 1 <= len(geluid['naam'].strip()) <= 100:
            raise OngeldigBibliotheekarchief('ARCH-014: ongeldige geluidsnaam.')
        controleer_aanvullende_informatie(geluid.get('beschrijving', ''), geluid.get('gesproken_tekst', ''), geluid.get('zoekwoorden', ''))
        if (not isinstance(geluid.get('groepen', []), list)
                or any(not isinstance(g, str) or len(g) > 60 for g in geluid.get('groepen', []))):
            raise OngeldigBibliotheekarchief('ARCH-015: ongeldige groep.')
        for groep in geluid.get('groepen', []):
            controleer_groepsnaam(groep)
        paden = geluid.get('groepspaden', [])
        if (not isinstance(paden, list) or len(paden) > 100
                or any(not isinstance(pad, list) or not 1 <= len(pad) <= 12
                       for pad in paden)):
            raise OngeldigBibliotheekarchief('ARCH-022: ongeldige mapstructuur in audiopack.')
        for pad in paden:
            for deel in pad:
                controleer_groepsnaam(deel)
        for naam in (bron, gekoppelde_afbeelding):
            if naam is not None:
                if naam not in alle_namen or naam in toegelaten:
                    raise OngeldigBibliotheekarchief('ARCH-016: dubbel of ontbrekend mediabestand.')
                regel = archief.getinfo(naam)
                limiet = 8 * 1024 * 1024 if naam == gekoppelde_afbeelding else MAX_BESTAND_BYTES
                if regel.file_size > limiet:
                    raise OngeldigBibliotheekarchief('ARCH-004: mediabestand is groter dan toegestaan.')
                toegelaten.add(naam)
    if alle_namen != toegelaten:
        raise OngeldigBibliotheekarchief('ARCH-017: onverwachte bestanden of paden in het ZIP-bestand.')
    return manifest['geluiden']


def importeer_draagbaar_bibliotheekarchief(bediening, media_map: Path, archiefpad: Path, selectie: list[int] | None = None, *, sla_dubbelen_over: bool = False) -> dict:
    """Importeer uitsluitend bekende media. Laat al bestaande favorieten intact."""
    from app.audio.mp4_verwerken import controleer_of_mp4_audio_en_video_bevat
    from app.webinterface.favorieten_en_instellingen import controleer_afspeelinstellingen
    import soundfile as sf

    aantal = 0
    overgeslagen = 0
    nieuwe_bestanden = []
    nieuw_toegevoegde_geluiden = []
    nieuw_aangemaakte_groepen = []
    try:
        with ZipFile(archiefpad, 'r') as archief:
            geluiden = _controleer_archief(archief)
            omvang_selectie = len(geluiden)
            if sla_dubbelen_over:
                vergelijkingen = _bepaal_dubbelen(archief, geluiden,
                    bediening.geluidenbibliotheek.geef_alle_geluiden())
            else:
                vergelijkingen = [{} for _ in geluiden]
            if selectie is not None:
                if (not isinstance(selectie, list) or len(selectie) > MAX_GELUIDEN_PER_ARCHIEF
                        or any(type(nummer) is not int or not 0 <= nummer < len(geluiden) for nummer in selectie)):
                    raise OngeldigBibliotheekarchief('ARCH-023: ongeldige selectie.')
                indices = list(dict.fromkeys(selectie))
            else:
                indices = list(range(len(geluiden)))
            overgeslagen = sum(bool(vergelijkingen[i].get('al_aanwezig') or
                vergelijkingen[i].get('dubbel_in_pakket')) for i in indices) if sla_dubbelen_over else 0
            gekozen = [geluiden[i] for i in indices
                      if not (sla_dubbelen_over and
                              (vergelijkingen[i].get('al_aanwezig') or vergelijkingen[i].get('dubbel_in_pakket')))]
            volledige_keuze = len(indices) == omvang_selectie
            geluiden = gekozen
            nodig = sum(archief.getinfo(item['bron']).file_size +
                        (archief.getinfo(item['afbeelding']).file_size if item.get('afbeelding') else 0)
                        for item in geluiden)
            # De mediadoelmap kan bij een eerste import nog niet bestaan.
            # Controleer de vrije ruimte op de dichtstbijzijnde bestaande oudermap.
            schijf_map = media_map
            while not schijf_map.exists() and schijf_map != schijf_map.parent:
                schijf_map = schijf_map.parent
            if nodig and shutil.disk_usage(schijf_map).free < nodig + 64 * 1024 * 1024:
                raise OngeldigBibliotheekarchief(
                    'ARCH-027: onvoldoende vrije schijfruimte voor deze import.')
            # Bij volledige bibliotheekimport ook de lege mappen herstellen.
            # Tijdens selectieve import worden geen niet-geselecteerde mappen gemaakt.
            lege_mappen = []
            if volledige_keuze and 'manifest.json' in archief.namelist():
                lege_mappen = json.loads(archief.read('manifest.json')).get('mappen', [])
            groepsregels = bediening.groepen.geef_alle_groepen()
            bestaande_groepen = {(groep['naam'].casefold(), groep.get('ouder_id')): groep['id'] for groep in groepsregels}
            for gegevens in geluiden:
                # Valideer met de bestaande afspeelinstellingen, dus de limiet
                # van 120 seconden geldt ook voor oude exports.
                controleer_afspeelinstellingen(gegevens.get('begin'), gegevens.get('volume'), gegevens.get('duur'))
                nieuwe_media = None
                afbeelding = None
                nieuw_geluid_id = None
                try:
                    ext = Path(gegevens['bron']).suffix
                    doelmap = media_map / 'geluiden'
                    doelmap.mkdir(parents=True, exist_ok=True)
                    nieuwe_media = doelmap / f'{uuid4()}{ext}'
                    with archief.open(gegevens['bron']) as bron, nieuwe_media.open('xb') as doel:
                        shutil.copyfileobj(bron, doel, length=256 * 1024)
                    try:
                        controleer_of_geluidsbestand_gebruikt_mag_worden(nieuwe_media)
                        if ext == '.mp4':
                            controleer_of_mp4_audio_en_video_bevat(nieuwe_media)
                        else:
                            sf.info(str(nieuwe_media))
                    except (RuntimeError, OSError, ValueError) as decoderfout:
                        # Een onleesbare bron is een importfout (HTTP 400),
                        # niet een onverklaarbare serverfout. De oorspronkelijke
                        # decoderfout blijft via de chained traceback zichtbaar.
                        raise OngeldigBibliotheekarchief('ARCH-020: onleesbare audio in het ZIP-bestand.') from decoderfout
                    item = bediening.geluidenbibliotheek.voeg_geluidsbestanden_toe([nieuwe_media])[0]
                    nieuw_geluid_id = item.geluid_id
                    bediening.geluidenbibliotheek.verander_de_naam_van_een_geluid(item.geluid_id, gegevens['naam'])
                    bediening.favorieten.bewaar_afspeelinstellingen(
                        item.geluid_id, gegevens['begin'], gegevens['volume'], gegevens['duur'],
                        gegevens.get('beeldvoorkeur', 'automatisch'))
                    bediening.extra_informatie.bewaar_informatie(
                        item.geluid_id, gegevens.get('beschrijving', ''),
                        gegevens.get('gesproken_tekst', ''), gegevens.get('zoekwoorden', ''))
                    if gegevens.get('afbeelding'):
                        ext_afbeelding = Path(gegevens['afbeelding']).suffix
                        afbeeldingsmap = media_map / 'afbeeldingen'
                        afbeeldingsmap.mkdir(parents=True, exist_ok=True)
                        afbeelding = afbeeldingsmap / f'{uuid4()}{ext_afbeelding}'
                        with archief.open(gegevens['afbeelding']) as bron, afbeelding.open('xb') as doel:
                            shutil.copyfileobj(bron, doel, length=64 * 1024)
                        from app.webinterface.lokale_webserver import controleer_of_afbeelding_echt_een_afbeelding_is
                        controleer_of_afbeelding_echt_een_afbeelding_is(afbeelding, ext_afbeelding)
                        bediening.favorieten.bewaar_afbeelding_voor_geluid(item.geluid_id, afbeelding.name)
                    paden = gegevens.get('groepspaden') or [[naam] for naam in gegevens.get('groepen', [])]
                    for pad in paden:
                        ouder = None
                        for naam in pad:
                            sleutel = (naam.casefold(), ouder)
                            nummer = bestaande_groepen.get(sleutel)
                            if nummer is None:
                                # Bestaande bibliotheken hebben nog een globale uniekheid op de naam.
                                # Een naam die elders al voorkomt gebruiken we niet als verkeerde map.
                                if any(k[0] == naam.casefold() for k in bestaande_groepen):
                                    raise OngeldigBibliotheekarchief(
                                        f'ARCH-024: mapnaam {naam!r} bestaat al op een andere plek.')
                                nummer = bediening.groepen.maak_groep(naam, ouder)
                                bestaande_groepen[sleutel] = nummer
                                nieuw_aangemaakte_groepen.append(nummer)
                            ouder = nummer
                        if ouder:
                            bediening.groepen.verander_lidmaatschap(ouder, item.geluid_id, True)
                    plek = gegevens.get('favoriet_plek')
                    if type(plek) is int and 1 <= plek <= 15:
                        if bediening.favorieten.geef_alle_favorietplekken()[plek - 1] is None:
                            bediening.favorieten.zet_een_geluid_op_een_vaste_plek(plek, item.geluid_id)
                    nieuwe_bestanden.append(nieuwe_media)
                    if afbeelding:
                        nieuwe_bestanden.append(afbeelding)
                    nieuw_toegevoegde_geluiden.append(item.geluid_id)
                    aantal += 1
                except Exception:
                    if nieuw_geluid_id:
                        bediening.favorieten.verwijder_referenties_naar_geluid(nieuw_geluid_id)
                        bediening.groepen.verwijder_koppelingen_naar_geluid(nieuw_geluid_id)
                        bediening.geluidenbibliotheek.haal_geluid_uit_de_bibliotheek(nieuw_geluid_id)
                    if afbeelding:
                        afbeelding.unlink(missing_ok=True)
                    if nieuwe_media:
                        nieuwe_media.unlink(missing_ok=True)
                    raise
            for pad in sorted(lege_mappen, key=len):
                ouder = None
                for naam in pad:
                    sleutel = (naam.casefold(), ouder)
                    nummer = bestaande_groepen.get(sleutel)
                    if nummer is None:
                        if any(k[0] == naam.casefold() for k in bestaande_groepen):
                            raise OngeldigBibliotheekarchief(
                                f'ARCH-024: mapnaam {naam!r} bestaat al op een andere plek.')
                        nummer = bediening.groepen.maak_groep(naam, ouder)
                        bestaande_groepen[sleutel] = nummer
                        nieuw_aangemaakte_groepen.append(nummer)
                    ouder = nummer
    except Exception as fout:
        # Een import met meerdere geluiden mag geen half gelukte collectie
        # achterlaten. Ruim alle items uit deze ene poging weer op.
        # Oude bibliotheekitems en oorspronkelijke bestanden blijven staan.
        for geluid_id in reversed(nieuw_toegevoegde_geluiden):
            bediening.favorieten.verwijder_referenties_naar_geluid(geluid_id)
            bediening.groepen.verwijder_koppelingen_naar_geluid(geluid_id)
            bediening.geluidenbibliotheek.haal_geluid_uit_de_bibliotheek(geluid_id)
        for bestand in reversed(nieuwe_bestanden):
            bestand.unlink(missing_ok=True)
        for groepsnummer in reversed(nieuw_aangemaakte_groepen):
            bediening.groepen.verwijder_groep(groepsnummer)
        if isinstance(fout, (BadZipFile, EOFError)):
            raise OngeldigBibliotheekarchief('ARCH-018: archief is beschadigd of onleesbaar.') from fout
        raise
    omschrijving = f'{aantal} geluiden geïmporteerd.'
    if overgeslagen:
        omschrijving += f' {overgeslagen} al aanwezige of dubbele geluiden overgeslagen.'
    return {'aantal': aantal, 'overgeslagen': overgeslagen, 'melding': omschrijving}


def _sha256_stream(stroom) -> str:
    """Hash in vaste kleine blokken. Houd ook bij grote audiopacks RAM begrensd."""
    digest = hashlib.sha256()
    for blok in iter(lambda: stroom.read(1024 * 1024), b''):
        digest.update(blok)
    return digest.hexdigest()


def _bepaal_dubbelen(archief: ZipFile, geluiden: list[dict], bestaande_geluiden: list) -> list[dict]:
    """Match byte-identieke media, onafhankelijk van naam of oorspronkelijke locatie.

    De schijfbestanden worden alleen gehasht als hun grootte in het pakket
    voorkomt. Bestanden die niet meer bestaan tellen niet mee.
    """
    maten = {archief.getinfo(item['bron']).file_size for item in geluiden}
    bestaande_per_grootte = defaultdict(list)
    namen = set()
    for item in bestaande_geluiden:
        namen.add(item.eigen_naam.casefold())
        try:
            grootte = item.bestandspad.stat().st_size
        except OSError:
            continue
        if grootte in maten:
            bestaande_per_grootte[grootte].append(item)
    hashes_per_grootte = {}
    gevonden_in_pack = {}
    resultaat = []
    for index, item in enumerate(geluiden):
        grootte = archief.getinfo(item['bron']).file_size
        if grootte not in hashes_per_grootte:
            hashes_per_grootte[grootte] = {}
            for bestaand in bestaande_per_grootte[grootte]:
                try:
                    with bestaand.bestandspad.open('rb') as bron:
                        vingerafdruk = _sha256_stream(bron)
                except OSError:
                    continue
                hashes_per_grootte[grootte].setdefault(vingerafdruk, bestaand.eigen_naam)
        with archief.open(item['bron']) as bron:
            vingerafdruk = _sha256_stream(bron)
        eerder = gevonden_in_pack.get((grootte, vingerafdruk))
        gevonden_in_pack.setdefault((grootte, vingerafdruk), index)
        match = hashes_per_grootte[grootte].get(vingerafdruk)
        resultaat.append({'al_aanwezig': match is not None,
                          'bestaande_naam': match,
                          'dubbel_in_pakket': eerder is not None,
                          'dubbel_met_index': eerder,
                          'zelfde_naam': item['naam'].casefold() in namen})
    return resultaat


def overzicht_volledige_bibliotheek(bediening) -> dict:
    """Toon inhoud voordat de gebruiker de volledige ZIP laat samenstellen."""
    items = bediening.geluidenbibliotheek.geef_alle_geluiden()
    groepen = bediening.groepen.geef_alle_groepen()
    totaal = 0
    ontbrekend = []
    bestanden = []
    koppelingen = bediening.groepen.geef_groepsnummers_per_geluid()
    for item in items:
        try:
            grootte = item.bestandspad.stat().st_size
            totaal += grootte
        except OSError:
            grootte = None
            ontbrekend.append(item.eigen_naam)
        bestanden.append({'naam': item.eigen_naam,
                          'formaat': item.bestandspad.suffix.lower().lstrip('.').upper(),
                          'media_bytes': grootte, 'groepen_ids': koppelingen.get(item.geluid_id, [])})
    groepsnamen = {groep['id']: groep['naam'] for groep in groepen}
    ouders = {groep['id']: groep.get('ouder_id') for groep in groepen}
    def volledig_pad(groep_id):
        namen, gezien = [], set()
        while groep_id in groepsnamen and groep_id not in gezien:
            gezien.add(groep_id)
            namen.insert(0, groepsnamen[groep_id])
            groep_id = ouders.get(groep_id)
        return ' / '.join(namen)
    return {'aantal': len(items), 'mappen': len(groepen),
            'mappaden': [volledig_pad(groep['id']) for groep in groepen],
            'geluiden': [{'naam': item['naam'], 'formaat': item['formaat'],
                          'mappen': [volledig_pad(gid) for gid in item['groepen_ids'] if gid in groepsnamen],
                          'media_bytes': item['media_bytes']} for item in bestanden],
            'media_bytes': totaal, 'ontbrekende_bestanden': ontbrekend,
            'max_geluiden': MAX_GELUIDEN_PER_ARCHIEF,
            'max_bytes': MAX_ARCHIEFINHOUD_BYTES,
            'kan_exporteren': len(items) <= MAX_GELUIDEN_PER_ARCHIEF
                and totaal <= MAX_ARCHIEFINHOUD_BYTES and not ontbrekend}


def bekijk_inhoud_audiopack(archiefpad: Path, bestaande_geluiden=None) -> dict:
    """Toon alleen gevalideerde manifestgegevens. Geen bestanden uitpakken."""
    try:
        with ZipFile(archiefpad, 'r') as archief:
            geluiden = _controleer_archief(archief)
            vergelijkingen = _bepaal_dubbelen(archief, geluiden, bestaande_geluiden or [])
    except (BadZipFile, EOFError) as fout:
        raise OngeldigBibliotheekarchief('ARCH-018: ZIP-bestand is beschadigd.') from fout
    return {'aantal': len(geluiden),
            'al_aanwezig': sum(int(x['al_aanwezig']) for x in vergelijkingen),
            'geluiden': [
        {'index': index, 'naam': item['naam'],
         'groepspaden': item.get('groepspaden') or [[naam] for naam in item.get('groepen', [])],
         'formaat': Path(item['bron']).suffix[1:].upper(),
         **vergelijkingen[index]}
        for index, item in enumerate(geluiden)]}
