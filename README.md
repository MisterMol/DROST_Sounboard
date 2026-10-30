# DrostSoundboard

Een soundboard voor Windows dat ik als hobbyproject bouw. Je kunt geluiden snel terugvinden, lokaal beluisteren of via een virtuele microfoon naar bijvoorbeeld Discord sturen. Het dashboard ziet eruit als een webpagina, maar de audio draait lokaal op je eigen pc.

**Huidige versie: 6.1.0 RC4.** Dit is een releasekandidaat, nog geen definitieve 6.1.0. Ik test hem eerst op andere Windowscomputers voordat ik hem als stabiel uitbreng.

## Gewoon gebruiken

Download de **Windows Setup** onder [GitHub Releases](https://github.com/MisterMol/DROST_Sounboard/releases). Kies de nieuwste geteste release en open het bestand dat eindigt op `Setup.exe`. Je hoeft hiervoor geen Python of Git te installeren.

**Let op:** als er nog geen Release met Setup.exe staat, is er nog geen publieke installatie beschikbaar. De broncode-ZIP op GitHub is geen kant-en-klare installer.

Na de installatie start je DrostSoundboard via het Startmenu of bureaublad. De app laat een waarschuwing zien als VB-CABLE ontbreekt en geeft meteen een link naar de maker.

### VB-CABLE voor Discord en andere apps

- **[Officiële VB-CABLE-download bij VB-Audio](https://vb-audio.com/Cable/)**
- Download het Windows-pakket, pak de ZIP volledig uit en start `VBCABLE_Setup_x64.exe` als administrator.
- Herstart Windows, start DrostSoundboard en klik zo nodig op **Opnieuw controleren**.
- Kies in Discord bij het invoerapparaat **CABLE Output (VB-Audio Virtual Cable)**. DrostSoundboard gebruikt de andere kabelkant om audio uit te zenden.

VB-CABLE is een aparte donationware-driver, geen onderdeel van DrostSoundboard. Zonder de driver kun je wel de bibliotheek beheren en Preview gebruiken, maar niet uitzenden als virtuele microfoon. Meer uitleg: [INSTALLEREN.md](INSTALLEREN.md).

## Wat zit erin?

- Drie dashboardindelingen: **Klassiek**, **Bibliotheek centraal** en **Favorieten eerst**. De keuze wordt onthouden.
- 15 vaste favorieten, eigen mappen, snelle zoekfilters en een aparte beheerbibliotheek.
- Preview via je headset en Uitzenden via de virtuele microfoon.
- Een kleine speler met tijdlijn, Stop, Opnieuw afspelen, herhalen en volume tot 200 procent.
- Fragmenten knippen, geluiden toevoegen, importeren en exporteren als audiopack.
- Eigen thema's, accentkleuren en extra instellingen in **Weergave**.
- Geluidseffecten, stemprofielen en een experimentele natuurlijke stemmotor (LLVC).
- Optionele globale sneltoetsen en bediening vanuit het Windows-systeemvak.

De aparte pagina **Bibliotheek** is voor beheer. De bibliotheek op het dashboard is om snel een geluid te zoeken en af te spelen.

## Logo

Het logo met de vijf geluidsbalkjes is overal hetzelfde: in de webinterface,
het systeemvak, de Windows EXE en de Setup. Het originele vectorbestand staat
in `assets/branding/DrostSoundboard.svg` (meer uitleg in [LOGO_EN_ICONEN.md](LOGO_EN_ICONEN.md)). Wil je het ooit aanpassen, dan kun je
met `python -m hulpmiddelen.maak_logo_bestanden` de iconen opnieuw maken.

Het dashboard draait in je gewone browser. Die browser heeft op de Windows
taakbalk zijn **eigen** icoon; de DrostSoundboard EXE, de snelkoppelingen en het
systeemvak krijgen wel het DrostSoundboard-logo.

## Broncode klonen

Wil je meekijken of zelf bijdragen? Installeer Git en Python 3.13 op Windows, en gebruik:

```powershell
git clone https://github.com/MisterMol/DROST_Sounboard.git
cd DROST_Sounboard
.\Start_Na_Git_Clone.cmd
```

**Belangrijk:** de twee ingebouwde stemvoorbeeld-MP3’s van Bob en Elise horen wél bij de broncode en moeten in de GitHub-clone meekomen. De publieke Git-repository bevat verder bewust geen grote stemmodellen, lokale binaire stemruntime of persoonlijke geluiden. De starter controleert dit en zegt eerlijk wanneer je voor volledig gebruik de Windows Setup nodig hebt. Een gewone `git clone` is dus vooral de ontwikkelroute, niet de makkelijkste installatie voor vrienden.

Wil je lokaal ontwikkelen, lees dan [CONTRIBUTING.md](CONTRIBUTING.md), [ARCHITECTUUR.md](ARCHITECTUUR.md) en [GITHUB_PUBLICEREN.md](GITHUB_PUBLICEREN.md). De code van het project staat onder [MIT](LICENSE); externe modellen en bibliotheken houden hun eigen voorwaarden. Zie [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md).

## Problemen?

Kijk eerst bij [INSTALLEREN.md](INSTALLEREN.md). Voor technische fouten staan de logboeken onder `%LOCALAPPDATA%\DrostSoundboard\logboeken`. Deel geen volledige logboeken, tokens, persoonlijke bestanden of privéopnames in een openbaar GitHub-issue.

**Updates:** voorlopig deel ik nieuwe versies als losse Windows Setup via GitHub Releases. Automatische updates zijn nog niet bevestigd. Sluit de app volledig af voordat je een nieuwere Setup start.
