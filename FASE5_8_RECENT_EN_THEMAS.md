# DrostSoundboard 5.8: recent gebruikt en persoonlijke thema's

## Wat is nieuw?

De hoofdweergave blijft bewust klein. Je ziet je **15 vaste favorieten**, gevolgd door **Recent gebruikt** met twee tabbladen. **Groepen** laat maximaal vijf laatst gebruikte groepen zien. **Geluiden** toont vijf recente afspeelbeurten, met het tijdstip en het verschil tussen **Preview** en **Naar call**.

Met **Geschiedenis** open je een apart venster met maximaal honderd recente regels. In de database worden maximaal vijfhonderd regels bewaard. Via **Geschiedenis wissen** wis je de geluidshistorie en de lijst recente groepen. Dit verwijdert geen media, groepsindelingen of favorieten.

Een groep geldt als recent gebruikt wanneer je deze opent in het groepsfilter of wanneer je een geluid uit die groep afspeelt. Een geluid dat bij meer groepen hoort, kan meerdere groepen recent maken.

**Preview** wordt pas geregistreerd nadat je browser daadwerkelijk met afspelen begint. **Naar call** pas nadat de Python-mixer de afspeelbeurt aanvaardt. Dit is **geen bevestiging** dat iemand anders het geluid ook hoorde. Er wordt geen microfoon- of geluidsopname voor de geschiedenis bewaard.

De knop **Weergave** geeft vijf basisthema's: Obsidian, Midnight, Amethyst, Ember en Monochrome. Daarnaast kun je een eigen accentkleur, gradientsterkte en richting kiezen en een compacte schermindeling activeren. De wijziging is direct zichtbaar als voorbeeld, maar wordt pas permanent na **Opslaan**. Via **Mijn opgeslagen thema's** kun je tot twintig eigen combinaties onder een naam bewaren. Het oorspronkelijke thema komt terug als je op Annuleren drukt. **Beginwaarden** kiest weer de standaardinstellingen.

## Installeren op je bestaande Windows-project

Sluit eerst DrostSoundboard. Het browservenster en de draaiende Python-server moeten echt dicht zijn.

Open PowerShell:

```powershell
cd "$env:USERPROFILE\Desktop\pythonProjects"

# Bewaar broncode en tests voordat bestanden vervangen worden.
Compress-Archive -Path .\DrostSoundboard\app,.\DrostSoundboard\tests,.\DrostSoundboard\*.md -DestinationPath .\DrostSoundboard_backup_voor_58.zip -Force

# Dit ZIP-bestand hoort in je eigen Downloads-map te staan.
Expand-Archive -LiteralPath "$env:USERPROFILE\Downloads\DrostSoundboard_5_8_Update.zip" -DestinationPath . -Force

cd .\DrostSoundboard

.\.venv\Scripts\python.exe -m unittest discover -s tests -q
```

De verwachte uitslag van dit pakket is `Ran 262 tests` en `OK`. Een paar tests gebruiken opzettelijk een kapotte MP3 en kunnen meldingen over een ongeldige MPEG-header tonen. De testuiteinduitslag is beslissend.

Start daarna:

```powershell
.\Start_DrostSoundboard.bat
```

Ververs de browser met `Ctrl + Shift + R` wanneer nog oude CSS of JavaScript in de cache staat.

Je hoeft geen nieuwe afhankelijkheden te installeren. De huidige audiomixer, Webserver-start en VB-CABLE-instellingen zijn niet vervangen.

## Test na het installeren

1. Klik een groep aan in de zijbalk. Die groep moet vervolgens zichtbaar worden bij **Recent gebruikt**.
2. Beluister een geluid met **Preview**. Open het tabblad Geluiden. De naam en het label Preview moeten verschijnen.
3. Klik op een favoriet om naar de call te sturen, maar alleen wanneer je VB-CABLE-test en verbinding werken. Daarna moet die afspeelbeurt als Naar call verschijnen.
4. Open **Weergave**, kies Midnight, verander eventueel de kleur en stel Gradient in op Subtiel. Klik op Opslaan en herlaad het dashboard. De instellingen moeten behouden blijven.
5. Bewaar een eigen thema onder bijvoorbeeld `Gaming donker`. Kies daarna een ander basisthema en laad je eigen thema weer vanuit Mijn opgeslagen thema's.
6. Schakel **Compacte weergave** in. De favortieten blijven in dezelfde volgorde maar nemen minder verticale ruimte in.
7. Open de volledige geschiedenis en gebruik **Geschiedenis wissen** alleen wanneer je de afgelopen acties echt wilt verwijderen.

## Technische indeling en veiligheid

De database-aanpassingen staan in `app/webinterface/recente_geluiden_en_weergave.py`. Bij het starten worden nieuwe tabellen gemaakt in dezelfde SQLite-bibliotheek; bestaande tabellen blijven onaangeroerd. `bediening_van_de_audiomotor.py` registreert daadwerkelijk gestarte audiobewegingen buiten de realtime callback. `lokale_webserver.py` levert beveiligde JSON-routes. Alle schermcode staat in `dashboard.js`, de indeling in `dashboard.html` en de thema-kleuren in `stijl.css`.

De browser praat alleen met de lokale server. Wijzigingen zijn met het bestaande schrijftoken beveiligd. Een eigen accentkleur moet een geldige hexkleur met voldoende contrast zijn. Er wordt geen CSS-code van de gebruiker uitgevoerd. Fouten blijven met tracebacks in `software.jsonl`, expliciete wijzigingen in `audit.jsonl`.

De bestanden met eigen thema's en recente geschiedenis zijn lokaal gekoppeld aan je bestaande database. De **bibliotheek-ZIP** van de vorige versie bevat nog niet automatisch deze persoonlijke scherminstellingen en recente acties. Maak voor een volledige migratie ook een back-up van je lokale database.

Bij een antivirusmelding niet Defender uitschakelen. Controleer de concrete detectienaam voordat je een bestand herstelt of alsnog uitvoert.
