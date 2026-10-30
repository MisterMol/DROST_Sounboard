"""Maak pas na een geslaagde releasebouw een aparte map voor handmatig delen.

Dit hulpmiddel bouwt of installeert niets en verstuurt niets. Het kopieert alleen
het opgegeven nieuwe Setup-bestand en schrijft een minimale bouwverantwoording.
"""
from __future__ import annotations
import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import uuid


def bestandsha(path):
    digest=hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda:stream.read(1024*1024),b''):
            digest.update(block)
    return digest.hexdigest()


def maak_deelmap(installer, uitvoer, versie, exerapport, stemrapport):
    installer,uitvoer=Path(installer),Path(uitvoer)
    # Import binnen de functie voorkomt een circulaire import met de bouwcoördinator.
    from app.desktop.releasevoorbereiding import lees_releaseversie
    release = lees_releaseversie(versie)
    if not installer.is_file() or installer.is_symlink() or not installer.name.endswith('Setup.exe'):
        raise ValueError('Geen gewoon Setup.exe-bestand opgegeven.')
    with installer.open('rb') as stream:
        if stream.read(2)!=b'MZ':raise ValueError('De installer heeft geen Windows-uitvoerbaar formaat.')
    exestatus=json.loads(Path(exerapport).read_text(encoding='utf-8'))
    stemstatus=json.loads(Path(stemrapport).read_text(encoding='utf-8'))
    if exestatus.get('geslaagd') is not True or exestatus.get('versie')!=versie:
        raise ValueError('De controle van de nieuwe hoofdapp is niet geslaagd of hoort bij een andere versie.')
    if (stemstatus.get('passed') is not True or stemstatus.get('finite') is not True
            or stemstatus.get('reset_ok') is not True
            or stemstatus.get('model_sha256')!='cceb7ab9621f84d62d283725ae3281cacb04f762d6a088fe3e97c1a29d4b8c0e'):
        raise ValueError('De controle van de meegeleverde stemmotor is niet geslaagd.')
    uitvoer.mkdir(parents=True,exist_ok=True)
    suffix=datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')+'_'+uuid.uuid4().hex[:6]
    target=uitvoer/('Delen-'+versie+'-'+suffix)
    tijdelijk=uitvoer/('.deelmap-'+suffix)
    tijdelijk.mkdir()
    try:
        original=bestandsha(installer)
        copied=tijdelijk/installer.name
        shutil.copy2(installer,copied)
        if bestandsha(copied)!=original or bestandsha(installer)!=original:
            raise ValueError('De installer veranderde tijdens het maken van het deelpakket.')
        info={'schema':1,'versie':versie,'gemaakt_utc':datetime.now(timezone.utc).isoformat(timespec='seconds'),
              'installer':installer.name,'installer_sha256':original,
              'exe_controle_geslaagd':True,'stem_controle_geslaagd':True,
              'schone_windowsinstallatie_getest':False,'echte_audio_getest':False,
              'luisterkwaliteit_getest':False,'code_signing':'niet_door_deze_patch_toegevoegd',
              'stemuitvoering':'processor','stemmodel':'Nova, Ruben, Linde en Omroeper; één model met vier klankvarianten',
              'let_op':'Geslaagde bouwcontroles zijn geen praktijkgoedkeuring. Test op een tweede Windows-pc.'}
        (tijdelijk/'BOUWCONTROLE.json').write_text(json.dumps(info,indent=2,ensure_ascii=False)+'\n',encoding='utf-8')
        aanduiding = 'releasekandidaat' if release.soort == 'rc' else 'bètaversie' if release.soort == 'beta' else 'release'
        tekst=f'''DrostSoundboard {versie}

Windows x64 {aanduiding}. Start {installer.name} om te installeren.
Een schone installatie en echte audio moeten voor verspreiding zijn getest.
Die praktijktests zijn niet automatisch bevestigd door de bouwcontrole.

Eerste gebruik
1. Installeer de app en start DrostSoundboard via de nieuwe snelkoppeling.
2. Kies je microfoon en luisterapparaat. Gebruik een koptelefoon bij het testen.
3. Voor uitzenden via de virtuele microfoon is VB-CABLE nodig. De driver is
   niet meegeleverd. Officiële download: https://vb-audio.com/Cable/
   Pak de driver-ZIP volledig uit, start VBCABLE_Setup_x64.exe als
   administrator en herstart Windows. De app controleert dit bij de start.
   Zonder VB-CABLE werken Preview en bibliotheekbeheer nog wel.
4. Kies een stem in Instellingen en beluister Bob of Elise als lokaal voorbeeld.
   Nova, Ruben, Linde en Omroeper gebruiken hetzelfde model met andere klankinstellingen.
   Bij inschakelen controleert de app zelf de verwerking. Er is geen verplichte GPU.
5. Selecteer CABLE Output als microfoon in de toepassing waarin je wilt spreken.
6. Sluit af met App afsluiten of Afsluiten in het systeemvak. Alleen de
   browsertab sluiten beëindigt de app niet.

Je hoeft geen Python, compiler of afzonderlijke stemapp te installeren.
De ingebouwde stemmotor verwerkt audio lokaal. Bij laadproblemen blijft
het betreffende microfoonsignaal gedempt. Geluidsfragmenten blijven apart.
Stemdiagnose staat onder Instellingen, Probleemoplossing en is niet nodig
voor normaal gebruik. Een computertest neemt niets op en zendt niets uit.

Bijwerken en verwijderen
Sluit de bestaande app helemaal af voordat je bijwerkt. Bewaar vooraf een
bibliotheekexport. Controleer bij verwijderen en opnieuw installeren of
je eigen bibliotheek en instellingen behouden blijven.

Beveiliging en updates
Deze bouw voegt geen code signing toe. Windows kan een waarschuwing tonen.
Controleer de herkomst en de SHA256. Schakel beveiligingssoftware niet uit.
De standaardbouw gebruikt handmatige updates en publiceert niets automatisch.
Gewijzigde openbare releases krijgen altijd een nieuw versienummer.

BOUWCONTROLE.json bevat alleen de bouwresultaten. Het bevestigt geen
luisterkwaliteit, schone installatie of langdurige werking tijdens gamen.
Dit deelpakket bevat geen persoonlijke geluiden, opnames of logboeken.
'''
        (tijdelijk/'LEESMIJ_VOOR_GEBRUIKERS.txt').write_text(tekst,encoding='utf-8-sig')
        regels=[bestandsha(p)+'  '+p.name for p in sorted(tijdelijk.iterdir()) if p.is_file()]
        (tijdelijk/'SHA256SUMS.txt').write_text('\n'.join(regels)+'\n',encoding='utf-8')
        os.replace(tijdelijk,target)
        return target
    except BaseException:
        shutil.rmtree(tijdelijk,ignore_errors=True)
        raise


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--installer',type=Path,required=True)
    parser.add_argument('--uitvoer',type=Path,required=True)
    parser.add_argument('--versie',required=True)
    parser.add_argument('--exe-rapport',type=Path,required=True)
    parser.add_argument('--stem-rapport',type=Path,required=True)
    args=parser.parse_args(argv)
    print('Deelmap:',maak_deelmap(args.installer,args.uitvoer,args.versie,args.exe_rapport,args.stem_rapport))
    return 0


if __name__=='__main__':
    raise SystemExit(main())
