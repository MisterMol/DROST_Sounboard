# DrostSoundboard 6.1.0-beta.3.2: Stoorzender

## Wat is veranderd?

Het experimentele profiel **Autotune** heet nu **Stoorzender**. Het effect bootst een
haperend digitaal audiosignaal na. Dit is geen echte radiostoorzender en de app
zendt geen radiosignalen uit.

De nieuwe regelaars staan onder **Instellingen > Geluid > Stemvervormer**:

- **Digitale ruis:** krassende storing die alleen hoorbaar wordt als de microfoon
  een signaal ontvangt.
- **Signaalhaperingen:** korte dipjes alsof de verbinding soms wegvalt. De
  overgang is afgerond om onverwachte blokgrensklikken te voorkomen.
- **Digitale vervorming:** korrelige, lage-resolutie audioklank.

De algemene **Intensiteit** van het profiel blijft van 0 tot 100 procent werken.
Je kunt met Bob, Elise of **Mijn eigen stem testen** meteen luisteren. De
bestaande **Reset** en **Reset alles** gelden ook voor deze drie regelaars.

## Bewaren en oudere instellingen

De interne profielcode blijft om technische redenen `autotune`. Hierdoor blijven
het geselecteerde profiel en de opgeslagen intensiteit behouden. Eerdere
muzikale instellingen (toonsoort, toonladder, correctiesnelheid) zijn niet meer
van toepassing op de nieuwe Stoorzender en worden niet uitgevoerd. De nieuwe
regelaars starten op hun eigen standaardwaarden. Wanneer je deze aanpast,
worden ze per profiel in SQLite opgeslagen.

## Audio en grenzen

De effecten worden in de bestaande audioketen toegepast vóór de mix met
soundboardgeluiden. Het toevoegen van ruis is gekoppeld aan het microfoonniveau:
als het bronmateriaal stil is, wordt geen permanente achtergrondruis gegenereerd.
De korte haperingen zijn bewust onderdeel van het effect. Het gaat dus om
**gesimuleerde digitale audioverstoring**, niet om een defect apparaat. De
bestaande meters blijven zichtbaar voor eventuele echte driveronderbrekingen.

Er is geen nieuwe Python-bibliotheek nodig. Bob, Elise en andere stemprofielen
worden niet gewijzigd. Het Windows-buildscript blijft bruikbaar voor `beta.3.2`.

## Testen op Windows

1. Verbreek de live microfoonverbinding en sluit een headset aan.
2. Ga naar Instellingen > Geluid > Stemvervormer > Stoorzender.
3. Luister met Bob of Elise en vergelijk Intensiteit 0, 50 en 100 procent.
4. Zet vervolgens Digitale ruis, Signaalhaperingen en Digitale vervorming
   één voor één tussen 0 en 100 procent.
5. Test **Mijn eigen stem testen**. Hiervoor wordt nooit automatisch Bob of
   Elise afgespeeld.
6. Sla de instellingen op, herstart de applicatie en controleer of de waardes
   terugkomen. Test **Reset**.
7. Test daarna pas een live microfoonverbinding.

## Wat wordt niet beloofd?

De softwaretests controleren signaalbewerking, piekgrenzen, verwerkingstijd en
instellingen. Een echte luistertest en een test van het USB/WASAPI-apparaat
moeten op Windows gebeuren. De app verandert geen audioapparaatstuurprogramma's.

## Windows-herstel voor tijdelijke SQLite-testdatabase

In `tests/test_stemherstel_beta631.py` wordt de SQLite-verbinding nu
expliciet gesloten met `contextlib.closing`. De standaard contextmanager
van `sqlite3.Connection` sluit de verbinding niet en liet op Windows het
bestand `db.sqlite` vergrendeld bij het opruimen van `TemporaryDirectory`.
Dezelfde test controleert dat de verbinding daadwerkelijk dicht is.
Deze correctie raakt de gebruikersdatabase of de werkende audio niet.
