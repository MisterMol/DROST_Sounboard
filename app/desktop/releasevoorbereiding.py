"""Voorbereiding en resultaatcontrole van een lokale, handmatig te delen release.

Elke bouw krijgt een lege eigen map. Bestaande installers, feeds en releases
worden nooit verwijderd of overschreven. Dit is geen upload- of publicatietool.
"""
from __future__ import annotations

import argparse
from dataclasses import dataclass
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re

from app.desktop.deelpakket import bestandsha, maak_deelmap


@dataclass(frozen=True)
class ReleaseVersie:
    versie: str
    kanaal: str
    soort: str


def lees_releaseversie(versie: str) -> ReleaseVersie:
    """Accepteer vaste versienummers, zonder automatische ophoging of metadata."""
    nummer = r'(?:0|[1-9][0-9]*)'
    patroon = rf'{nummer}\.{nummer}\.{nummer}(?:-(beta|rc)\.({nummer})(?:\.({nummer}))?)?'
    match = re.fullmatch(patroon, versie)
    if match is None:
        raise ValueError('Gebruik een versie zoals 6.1.0-beta.4.20, 6.1.0-rc.1 of 6.1.0.')
    if match[1] == 'rc' and match[3] is not None:
        raise ValueError('Een releasekandidaat krijgt één volgnummer, bijvoorbeeld 6.1.0-rc.1.')
    soort = match[1] or 'stable'
    # RC blijft op hetzelfde testkanaal als beta. De uiteindelijke release is apart.
    return ReleaseVersie(versie, 'stable' if soort == 'stable' else 'beta', soort)


def _id(bouw_id: str) -> str:
    if not re.fullmatch(r'[a-f0-9]{32}', bouw_id):
        raise ValueError('Ongeldig bouwkenmerk.')
    return bouw_id


def _geen_links(pad: Path) -> None:
    """Volg geen directorylinks of Windows-junctions in de release-uitvoer."""
    for onderdeel in (pad, *pad.parents):
        try:
            st = onderdeel.lstat()
        except FileNotFoundError:
            continue
        if onderdeel.is_symlink() or getattr(st, 'st_file_attributes', 0) & 0x400:
            raise ValueError('Een releasepad mag geen link of junction bevatten.')


def schrijf_json_nieuw(pad: Path, inhoud: dict) -> None:
    """Schrijf een nieuw document; vervang geen resultaat van een vorige poging."""
    pad = Path(pad)
    _geen_links(pad)
    pad.parent.mkdir(parents=True, exist_ok=True)
    # Een onvolledig JSON-resultaat bij stroomuitval kan nooit als succes worden gelezen.
    with pad.open('x', encoding='utf-8') as stream:
        json.dump(inhoud, stream, ensure_ascii=False, indent=2)
        stream.write('\n')
        stream.flush()
        os.fsync(stream.fileno())


def maak_bouwplan(project: Path, versie: str, bouw_id: str) -> dict:
    """Maak uitsluitend een lege uitvoermap voor deze lokale bouwpoging."""
    info = lees_releaseversie(versie)
    _id(bouw_id)
    project = Path(project).absolute()
    _geen_links(project)
    project = project.resolve()
    if not project.is_dir():
        raise ValueError('De projectmap ontbreekt.')
    root = project / 'release-velopack'
    _geen_links(root)
    root.mkdir(exist_ok=True)
    # Het volledige bouwkenmerk voorkomt botsingen, ook bij twee snelle starts.
    uitvoer = root / f'Bouw-{versie}-{bouw_id}'
    _geen_links(uitvoer)
    uitvoer.mkdir(exist_ok=False)
    return {
        'schema': 1, 'bouw_id': bouw_id, 'versie': versie,
        'kanaal': info.kanaal, 'soort': info.soort,
        'uitvoer': str(uitvoer),
        'installer_naam': f'DrostSoundboard.Desktop-{info.kanaal}-Setup.exe',
        'publicatie': 'handmatig; deze bouw publiceert niets',
    }


def rond_bouw_af(project: Path, plan: dict, exerapport: Path,
                 stemrapport: Path, resultaat: Path) -> dict:
    """Leg alleen een nieuw, gecontroleerd bouwresultaat vast, na geslaagde vpk."""
    project = Path(project).resolve()
    info = lees_releaseversie(plan.get('versie', ''))
    bouw_id = _id(plan.get('bouw_id', ''))
    verwacht = project / 'release-velopack' / f'Bouw-{info.versie}-{bouw_id}'
    _geen_links(verwacht)
    if (plan.get('schema') != 1 or Path(plan.get('uitvoer', '')).resolve() != verwacht
            or plan.get('kanaal') != info.kanaal):
        raise ValueError('Het bouwplan hoort niet bij deze release en uitvoermap.')
    naam = f'DrostSoundboard.Desktop-{info.kanaal}-Setup.exe'
    if plan.get('installer_naam') != naam:
        raise ValueError('De installernaam in het bouwplan klopt niet.')
    installer = verwacht / naam
    _geen_links(installer)
    if not installer.is_file():
        raise ValueError('Er is geen nieuwe installer in de uitvoermap gemaakt.')
    # Een geslaagde packer hoort ook een release-index voor hetzelfde kanaal te leveren.
    feed = verwacht / f'releases.{info.kanaal}.json'
    _geen_links(feed)
    if not feed.is_file():
        raise ValueError('De release-index van de nieuwe installer ontbreekt.')
    index = json.loads(feed.read_text(encoding='utf-8-sig'))
    assets = index.get('Assets', []) if isinstance(index, dict) else []
    gekozen = [a for a in assets if isinstance(a, dict)
               and a.get('PackageId') == 'DrostSoundboard.Desktop'
               and a.get('Version') == info.versie and a.get('Type') == 'Full']
    if not gekozen:
        raise ValueError('De release-index bevat geen volledig pakket voor deze versie.')
    for asset in gekozen:
        filename = asset.get('FileName', '')
        if (not isinstance(filename, str) or not filename or '/' in filename or '\\' in filename
                or ':' in filename or filename in ('.', '..') or not filename.endswith('.nupkg')):
            raise ValueError('Ongeldige bestandsnaam in de release-index.')
        bestand = verwacht / filename
        _geen_links(bestand)
        if not bestand.is_file() or bestand.stat().st_size == 0:
            raise ValueError('Het volledige releasepakket ontbreekt of is leeg.')
        if 'Size' in asset and (type(asset['Size']) is not int or asset['Size'] != bestand.stat().st_size):
            raise ValueError('De grootte van het releasepakket klopt niet met de release-index.')
        if 'SHA256' in asset:
            digest = asset['SHA256']
            if not isinstance(digest, str) or not re.fullmatch(r'[a-fA-F0-9]{64}', digest) or bestandsha(bestand) != digest.lower():
                raise ValueError('Het releasepakket klopt niet met de controlesom in de release-index.')
    resultaat = Path(resultaat).absolute()
    _geen_links(resultaat)
    if resultaat.exists():
        raise ValueError('Het resultaatbestand bestaat al; gebruik een nieuwe bouwpoging.')
    deelmap = maak_deelmap(installer, verwacht, info.versie, exerapport, stemrapport)
    rapport = {
        'schema': 1, 'bouw_id': bouw_id, 'versie': info.versie,
        'kanaal': info.kanaal, 'geslaagd': True,
        'gemaakt_utc': datetime.now(timezone.utc).isoformat(timespec='seconds'),
        'installer': str(installer.relative_to(project)),
        'installer_sha256': bestandsha(installer),
        'deelmap': str(deelmap.relative_to(project)),
        'productie_goedgekeurd': False,
        'uitleg': 'Bouwcontroles geslaagd. Praktijktests en distributierechten apart controleren.',
    }
    schrijf_json_nieuw(resultaat, rapport)
    return rapport


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='actie', required=True)
    plan = sub.add_parser('plan')
    plan.add_argument('--project', type=Path, required=True)
    plan.add_argument('--versie', required=True)
    plan.add_argument('--bouw-id', required=True)
    plan.add_argument('--uitvoer-json', type=Path, required=True)
    klaar = sub.add_parser('afronden')
    klaar.add_argument('--project', type=Path, required=True)
    klaar.add_argument('--plan', type=Path, required=True)
    klaar.add_argument('--exe-rapport', type=Path, required=True)
    klaar.add_argument('--stem-rapport', type=Path, required=True)
    klaar.add_argument('--resultaat', type=Path, required=True)
    args = parser.parse_args(argv)
    if args.actie == 'plan':
        plan = maak_bouwplan(args.project, args.versie, args.bouw_id)
        schrijf_json_nieuw(args.uitvoer_json, plan)
        print('Nieuwe, afzonderlijke bouwmap: ' + plan['uitvoer'])
    else:
        plan = json.loads(args.plan.read_text(encoding='utf-8-sig'))
        result = rond_bouw_af(args.project, plan, args.exe_rapport, args.stem_rapport, args.resultaat)
        print('Deelmap: ' + str(args.project / result['deelmap']))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
