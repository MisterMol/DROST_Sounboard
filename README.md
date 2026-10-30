# DrostSoundboard

Een soundboard voor Windows, gemaakt als hobbyproject. Speel geluiden af via je headset, verzend ze via een virtuele microfoon en beheer je eigen geluidsbibliotheek.

**Huidige versie: 6.1.0 RC4 (testversie).**

## Downloaden

**[DrostSoundboard voor Windows downloaden](https://github.com/MisterMol/DROST_Sounboard/releases)**

Download bij de nieuwste release `DrostSoundboard.Desktop-beta-Setup.exe`, open het bestand en start de app via het Startmenu of de bureaubladsnelkoppeling. Python en Git zijn niet nodig.

Staat er nog geen Setup op de Releases-pagina? Dan is de installer nog niet openbaar geüpload.

## VB-CABLE (vereist voor Uitzenden)

**VB-CABLE is een aparte afhankelijkheid** en moet worden geïnstalleerd om geluiden via een virtuele microfoon uit te zenden. Download het via de [officiële VB-Audio-website](https://vb-audio.com/Cable/). Zonder VB-CABLE werken Preview en bibliotheekbeheer gewoon.

[Installatiehandleiding](INSTALLEREN.md)

## Wat zit erin?

15 favorieten, snelle zoek- en mapfilters, drie dashboardindelingen, thema's, Preview en Uitzenden, volume en tijdlijn, stemvervorming en een aparte pagina om je geluiden te beheren.

## Broncode

Deze repository bevat de broncode, tests en ontwikkelhulpmiddelen. Wie wil meekijken kan hem clonen:

```powershell
git clone https://github.com/MisterMol/DROST_Sounboard.git
cd DROST_Sounboard
.\Start_Na_Git_Clone.cmd
```

Een clone bevat de Bob- en Elise-stemvoorbeelden, maar niet de volledige stemruntime of modelgewichten. Voor gewoon gebruik is de Windows Setup bedoeld.

DrostSoundboard valt onder de [MIT-licentie](LICENSE). Voor externe onderdelen gelden aanvullende voorwaarden in [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md). De Setup is nog niet digitaal ondertekend. Updates worden momenteel handmatig gedeeld.
