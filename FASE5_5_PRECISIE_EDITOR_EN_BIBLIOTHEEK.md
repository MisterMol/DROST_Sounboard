# DrostSoundboard 5.5 | Precisie-editor en bibliotheekbeheer

Deze versie verbetert het knippen en organiseren van audio. De Razer-microfoon, VB-CABLE en de bestaande audiomixer veranderen niet.

## Eenmalig installeren op je bestaande Windows-pc

Sluit eerst DrostSoundboard en alle geopende dashboardvensters. Download `DrostSoundboard_Fase5_5_Update.zip` en bewaar het in je Downloads-map.

Open PowerShell en voer de volgende opdrachten een voor een uit:

```powershell
cd "$env:USERPROFILE\Desktop\pythonProjects"

Compress-Archive -Path .\DrostSoundboard\app,.\DrostSoundboard\tests,.\DrostSoundboard\*.md -DestinationPath .\DrostSoundboard_backup_voor_55.zip -Force

Expand-Archive -LiteralPath "$env:USERPROFILE\Downloads\DrostSoundboard_Fase5_5_Update.zip" -DestinationPath . -Force

cd .\DrostSoundboard

Test-Path .\app\webinterface\statisch\dashboard.js

.\.venv\Scripts\python.exe -m unittest discover -s tests -q

.\Start_DrostSoundboard.bat
```

De eerste controle moet `True` tonen. Verwacht bij de tests `Ran 223 tests` en `OK`.

Ververs de browser na de update met `Ctrl + Shift + R`. Python hoeft niet opnieuw te worden geïnstalleerd, want de bestaande versie heeft alle benodigde afhankelijkheden.

Als je browser of Defender een bestand blokkeert, onderzoek dan de detectienaam. Schakel de beveiliging niet uit.

## Knippen met drie decimalen

1. Open een geluid met **Bewerken**.
2. Klik of sleep aan de groene beginrand of de gele eindrand in de golfvorm.
3. Houd een van de randen ongeveer een halve seconde vast. Het venster zoomt in op ongeveer 1,5 seconde rondom die rand.
4. Gebruik **Plus** en **Min** om verder in of uit te zoomen. **Volledig** toont de volledige selectieomgeving, tot maximaal twee minuten per venster.
5. Scroll met de muis boven de golfvorm om horizontaal te bewegen. Houd `Ctrl` ingedrukt tijdens het scrollen om in te zoomen bij de muispositie.
6. Voer desgewenst exact `1.235` bij **Begin (seconden)** en `0.750` bij **Duur (seconden)** in.
7. Klik op de golfvorm voor de previewcursor en gebruik **Spatie** voor afspelen en pauzeren. Met de pijltjestoetsen kun je de cursor verplaatsen. Met `Alt` en een pijltjestoets verplaats je de cursor 1 ms.
8. Klik op **Wijzigingen opslaan**.

De selectie wordt als beginpunt en lengte opgeslagen, met drie decimalen. Het oorspronkelijke bronbestand wordt niet overschreven. Een fragment mag maximaal 120 seconden duren, maar een kort bronbestand behoudt zijn werkelijke lengte.

**Technische nauwkeurigheid:** het beginpunt wordt door Python op samplegrenzen toegepast. De editor slaat tijden tot op 0,001 seconde op. De browserpreview en codecs zoals MP3 en MP4 kunnen bij het zoeken minder nauwkeurig zijn. Eén milliseconde numerieke precisie betekent daarom niet dat ieder gecomprimeerd fragment exact op die milliseconde hoorbaar begint.

## Naam, beschrijving, gesproken tekst en zoekwoorden

Bij het bewerken van een geluid kun je nu behalve de naam ook het volgende bewaren:

* **Beschrijving**, bijvoorbeeld: `Cartman klaagt over zijn leraar`.
* **Wat wordt er gezegd?**, bijvoorbeeld: `Respect my authoritah!`.
* **Zoekwoorden**, bijvoorbeeld: `cartman, south park, roepen`.

Al deze velden worden in SQLite bewaard en zijn doorzoekbaar. De tekst wordt niet automatisch uit het geluid getranscribeerd en verandert niets aan het videobeeld. De metadata kunnen later worden gebruikt voor ondertiteling, maar dat is nu nog geen functie.

## Groot bibliotheekvenster

Klik in de zijbalk op **Bibliotheek beheren**. Dit opent een bredere weergave zonder je audiomixer te stoppen.

Je kunt daar:

* Zoeken op naam, bestandsnaam, beschrijving, gesproken tekst, zoekwoorden en groepsnaam.
* Filteren op groep, bijvoorbeeld `South Park`.
* Meerdere geluiden aanvinken, of de zichtbare resultaten selecteren.
* De selectie in één handeling aan een groep toevoegen.
* De selectie als ZIP exporteren.
* Een eerder geëxporteerde ZIP importeren.
* Geselecteerde geluiden uit de bibliotheek verwijderen. De echte bronbestanden blijven op schijf staan.

Lijsten tonen eerst 60 resultaten. Klik op **Meer tonen** om verder te bladeren, zodat honderden geluiden geen onnodig zware pagina opleveren.

## Bibliotheek exporteren en importeren

Een ZIP-export bevat de **oorspronkelijke** MP3-, WAV- en MP4-bestanden plus een leesbaar `manifest.json` met naam, kniptijden, volume, groepen, optionele afbeelding, uitgesproken tekst, beschrijving en favorietpositie.

Een ZIP is dus een draagbare **DrostSoundboard-bibliotheek**, niet één opnieuw geknipt WAV- of MP3-bestand. Bij import worden nieuwe bibliotheek-ID's gebruikt. Bestaande favorieten worden niet overschreven. Alleen lege favorietplekken kunnen vanuit het archief worden gevuld.

Per export/import gelden limieten: maximaal 250 geluiden, 250 MiB per geluidsbestand en een totale ongecomprimeerde inhoud van 500 MiB. Bij import is het geüploade ZIP-bestand maximaal 512 MiB. Bij een fout in een import worden nieuwe onderdelen van die poging opgeruimd. Een bronbestand wordt nooit door het verwijderen van een bibliotheekitem gewist.

**Importeer alleen vertrouwde ZIP-bestanden.** Een archief kan mediasporen bevatten die een decoder activeren. DrostSoundboard controleert bestandstypen en paden, maar kan de veiligheid van externe audio niet volledig garanderen.

## Logging

Bij instellingen opslaan logt de applicatie het geluidsnummer, knipwaarden, volume en **de lengte** van beschrijving en tekst. De geschreven inhoud wordt niet als platte tekst in de auditlog gezet.

Export, import, groepstoewijzing en bulk verwijderen krijgen auditgebeurtenissen. Fouten krijgen de volledige traceback in `software.jsonl`.

Logboeken openen:

```powershell
.\Open_Logboeken.bat
```

## Testscenario

Maak een geluid van 29 seconden beschikbaar. Kies een begin van `1.234` en duur van `2.345`. Het geselecteerde fragment moet worden getoond als `0:02.345`. Houd de linkerrand vast; het zichtbare venster moet inzoomen naar ongeveer `0:01.500`. Sla de instellingen op en open dezelfde clip opnieuw.

Maak daarna de groep `South Park`, voeg drie geluiden toe, zoek een woord uit de gesproken tekst, exporteer de selectie en importeer de ZIP opnieuw. Controleer dat de nieuwe exemplaren hun metadata en fragmentlengte behouden.
