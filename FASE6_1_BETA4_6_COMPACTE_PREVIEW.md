# DrostSoundboard 6.1.0 Beta 4.6: compacte lokale preview

Deze patch verandert de dashboardspeler, niet de audiomixer of de importgegevens.

## Nieuwe bediening

- Tijdens een lokale preview kun je in de voortgangsbalk klikken of slepen. De sprong blijft binnen het ingestelde begin en einde van het fragment. Het toetsenbord kan de balk eveneens bedienen.
- **Herhalen** schakelt een loop in of uit en start het fragment opnieuw bij het ingestelde beginpunt. De keuze geldt voor je previews zolang de dashboardpagina open is.
- **Volume** is een kleine schuifregelaar in de speler. Deze verandert de preview direct en bewaart bij loslaten dezelfde algemene soundboardvolumewaarde als op de instellingenpagina. Het microfoonvolume blijft onaangetast.
- De technische preview-uitleg is vervangen door `Preview, alleen lokaal.` en een compact label voor de eventuele normalisatiecorrectie.
- Eén zichtbare **Stop**-knop werkt voor preview en live uitvoer. Bij alleen een lokale preview wordt geen overbodige `/api/stop`-aanvraag verzonden.
- De voortgangsbalk gebruikt de browseraudioklok en `requestAnimationFrame` om zichtbaar vloeiend te bewegen. De achtergrondcontrole bewaakt ook korte fragmenten wanneer het browsertabblad niet zichtbaar is.

## Synchronisatie en grenzen

Een MP4 gebruikt tijdens preview hetzelfde media-element voor beeld en geluid, ook na doorspoelen. Een GIF kan in een browser niet naar een exact frame worden gezocht; hij wordt alleen opnieuw gestart wanneer de preview naar het fragmentbegin teruggaat. Deze beperking hoort niet als aparte foutmelding in het dashboard.

De zoek- en loopknoppen zijn niet actief tijdens live uitsturen. Voor live-video blijft de bestaande afzonderlijke synchronisatie aan de Python-audioklok leidend. Er wordt geen extra microfoon, videostream of decoder geopend.

## Regressietests

`python -m unittest discover -s tests -q`

`node tests/hulpmiddelen/test_preview_speler_beta646.js`

`node tests/hulpmiddelen/test_preview_normalisatie_beta41.js`

## Praktijktest op Windows

1. Open Dashboard en kies een fragment met een beginpositie voorbij 0:00.
2. Start Preview en klik op het midden van de voortgangsbalk. Controleer of de positie binnen het fragment ligt.
3. Test een MP4 met beeld, en schakel Herhalen in. Bij het einde begint dezelfde preview opnieuw.
4. Verplaats de volumeschuif naar 50% en kijk of de instelling onder Instellingen > Geluid dezelfde waarde bewaart.
5. Schakel Herhalen uit en druk op Stop. Het geluid stopt lokaal, maar de virtuele microfoon blijft verbonden.
6. Probeer daarna een live soundboardgeluid. De zoekbalk is informatief; klikken mag het uitgezonden geluid niet verplaatsen.
7. Controleer korte fragmenten, een gekoppelde GIF en de bediening bij een smal browservenster.

Automatische updates via GitHub blijven buiten deze patch. De normale updater van het ontwikkelproject maakt vóór het vervangen van bestanden een back-up en voert de tests uit. Werk niet bij tijdens een gesprek.
