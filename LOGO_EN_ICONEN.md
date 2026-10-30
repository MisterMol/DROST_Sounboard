# Logo en iconen

DrostSoundboard heeft één logo: het afgeronde vierkant met vijf geluidsbalken.
De originele vector staat in `assets/branding/DrostSoundboard.svg`.

De andere afbeeldingen komen uit die ene bron:

| Waar | Bestand |
| --- | --- |
| Navigatie en opstartscherm | `app/webinterface/statisch/drost-logo.svg` |
| Favicon in browser | `app/webinterface/statisch/favicon.ico` |
| Systeemvak | `app/webinterface/statisch/drost-logo.png` |
| Windows EXE en Velopack Setup | `assets/release/DrostSoundboard.ico` |
| Installatiescherm | `assets/release/DrostSoundboard_Installatie.png` |

## Het logo aanpassen

Pas het vectorbestand aan en voer vanuit de projectmap uit:

```powershell
.\.venv\Scripts\python.exe -m hulpmiddelen.maak_logo_bestanden
```

Hiervoor is alleen Pillow nodig. De bestanden worden lokaal gegenereerd, zonder downloads.
Bouw daarna een nieuwe versie van de Windows Setup zodat het nieuwe EXE-icoon mee kan.

## Verschil tussen browser en Windows

Het dashboard opent in de standaardbrowser. De browser blijft in de Windows-taakbalk
zijn eigen applicatiepictogram gebruiken. Het tabblad en de bladwijzer gebruiken
het DrostSoundboard-favicon. De DrostSoundboard EXE, de snelkoppelingen die bij
Velopack horen en het systeemvak gebruiken wel het DrostSoundboard-icoon.

Dit is een hobbyproject. De hele applicatie hoeft niet in een andere browser
of een vensterframework om alleen het icoon te veranderen.
