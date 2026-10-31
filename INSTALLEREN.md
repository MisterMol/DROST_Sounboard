# DrostSoundboard installeren

## Voor gebruikers: één EXE

### Zichtbare RC6-installatie testen

De technische `DrostSoundboard.Desktop-beta-Setup.exe` is een vrijwel stille
Velopack-installer. **Dat is niet de bedoelde download voor eindgebruikers.**

Gebruik voor een test de nieuwe **DrostSoundboard-Installeren-RC6-Test.exe**,
te vinden onder het GitHub Actions-artefact
`DrostSoundboard-RC6-Een-EXE-Met-Geluidskeuze`.

Deze nieuwe EXE bevat de complete compacte RC6 Setup en opent eerst een echt
installatievenster. De stappen voor een tester zijn:

1. Download het bouwartefact en haal de EXE uit het GitHub-artefact-ZIP.
   Op de testcomputer heb je alleen de EXE nodig.
2. Start die EXE met een dubbelklik.
3. Kies eventueel **Ook het startersoundpack met 141 geluiden toevoegen**.
   Die keuze is standaard uit. Het pakket vergt ongeveer 310 MiB extra download.
4. Klik **Installeren**. De installer toont de voortgang, start de
   bijgevoegde RC6 Setup en controleert of DrostSoundboard aanwezig is.
5. Als je de geluiden hebt gekozen, worden ze daarna opgehaald en waar
   mogelijk automatisch aan de bibliotheek toegevoegd.
6. Klik **DrostSoundboard openen**.

**Zelf importeren wanneer nodig:** het ZIP-bestand blijft in Downloads staan.
Open DrostSoundboard, ga naar **Bibliotheek**, kies
**Audiopack importeren**, selecteer de ZIP, kies **Alle nieuwe**
en klik **Geselecteerde geluiden importeren**. De ZIP hoeft niet uitgepakt
te worden.

Voor publicatie testen: installeer op een tweede Windows-pc, start
de app, speel geluiden af, controleer de gewone stemfilters, voeg een
soundpack toe en test afsluiten en herinstalleren. De test-EXE is
nog niet digitaal ondertekend. Schakel Windows-beveiliging niet uit.

### Na afronding van de praktijktest


1. Download **DrostSoundboard-Installeren.exe** via de officiële [GitHub Releases](https://github.com/MisterMol/DROST_Sounboard/releases).
2. Dubbelklik op de EXE en kies **Installeren**.
3. De installer haalt de officiële Windows-app op, controleert de download en voert Setup uit. De voortgang verschijnt in het installatievenster.
4. Daarna staat DrostSoundboard in het Startmenu en kun je direct je eigen geluiden toevoegen.

Je hoeft **geen Git, Python, .NET SDK, PowerShell of winget** te installeren of te gebruiken.

**Extra geluiden:** de volgende verbeterde installerstarter biedt een optioneel
vinkje voor een geluidenpakket van ongeveer 310 MiB. Als je dat aanvinkt,
wordt het pakket na installatie automatisch in de bibliotheek geïmporteerd,
met controle op reeds aanwezige geluiden. Je kunt het vinkje uitlaten
om alleen het compacte soundboard te downloaden. Bij een importfout blijft
de ZIP in je map Downloads voor een eventuele handmatige herstart.

De huidige [RC5-installatie-EXE](https://github.com/MisterMol/DROST_Sounboard/releases/download/v6.1.0-rc.5/DrostSoundboard-Installeren.exe)
installeert **nog RC5** en biedt de automatische import hierboven nog
niet. De nieuwe RC6-installatie wordt pas aangeboden nadat de compacte
Windows Setup gebouwd, getest en als aparte release gepubliceerd is.
De oude RC5-release blijft staan.

## Uitzenden met VB-CABLE

DrostSoundboard kan geluiden lokaal als preview afspelen zonder VB-CABLE.
Wil je geluiden uitzenden via een virtuele microfoon in bijvoorbeeld Discord,
dan heb je de aparte [VB-CABLE-driver](https://vb-audio.com/Cable/) nodig.
Deze systeemdriver kan om administratorrechten en een Windows-herstart vragen.
De gewone DrostSoundboard-installer installeert de driver niet ongemerkt.

## Gegevens blijven bewaard

Gewoon bijwerken of opnieuw installeren hoort je bestaande bibliotheek,
favorieten en persoonlijke instellingen te behouden. Verwijder niet
zomaar de map `%LOCALAPPDATA%\DrostSoundboard`, want daarin staan
persoonlijke gegevens en media. Maak bij twijfel eerst een bibliotheekexport.

De EXE-bestanden zijn nog niet digitaal ondertekend. Controleer altijd
de herkomst via de officiële GitHub Release en schakel Windows-beveiliging
niet uit.

## Voor de beheerder

De [RC6-bouwinstructies](RC6_COMPACT_BOUWEN.md) beschrijven hoe GitHub
Actions zelf de compacte Setup en installerstarter bouwt.
Eindgebruikers hoeven die bouwstappen niet uit te voeren.
