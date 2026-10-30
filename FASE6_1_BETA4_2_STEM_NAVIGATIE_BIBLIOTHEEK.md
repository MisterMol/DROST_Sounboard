# DrostSoundboard 6.1.0-beta.4.2: bediening, navigatie en bibliotheekreset

## Doel

Deze patch bouwt voort op versie `6.1.0-beta.4.1`. Hij verandert de gebruikersinterface en voegt een gecontroleerde bibliotheekreset toe. Er worden geen nieuwe audiodependencies geïnstalleerd.

## Stemvervormer

Het gekozen stemprofiel en de schakelaar voor **live stemvervorming** zijn apart opgeslagen. Een stemkaart of het kiezen van Bob/Elise start niets. Alleen **Inschakelen** op het dashboard schakelt de live stemvervorming in. De standaardstand bij de eerste start na deze patch is **uit**. De knop **Uitschakelen** zet de live verwerking uit zonder de microfoon te verbreken. De lokale optie **Mijn eigen stem testen** gebruikt bewust het geselecteerde profiel, ook wanneer de live optie uit staat. Deze test start alleen na een klik en alleen als de live verbinding is verbroken. Bij een actieve microfoonverbinding verschijnt een duidelijke boodschap.

## Navigatie

**Dashboard**, **Bibliotheek** en **Instellingen** blijven altijd in de navigatie staan. De gekozen pagina krijgt een subtiele omlijning en `aria-current="page"` voor toegankelijkheid.

## Bibliotheek leegmaken

Op de bibliotheekpagina staat een ingetrokken sectie **Bibliotheek opnieuw beginnen**. Voor bevestiging moet je exact `BEVESTIG` typen. De server vereist hetzelfde woord en het lokale schrijftoken. Eerst wordt via de SQLite-back-upfunctie een consistente herstelkopie van de volledige database gemaakt, daarna worden alleen bibliotheektabellen in één transactie geleegd. De applicatie bewaart de originele audiobestanden, stemprofielen, normalisatie, thema's, sneltoetsen en andere algemene instellingen. Dit is **geen optie om bestanden fysiek van de computer te wissen**. De reset is alleen bedoeld om een lege bibliotheek te beginnen. Herstel gebeurt bij problemen vanuit de getoonde reservekopie, bij voorkeur terwijl de app uit staat.

## Metadata en teksten

Bestandstype, fragmentduur en aantal keer via de virtuele microfoon uitgezonden worden afzonderlijk getoond. Beweeg de muis over een waarde of focus erop met het toetsenbord voor uitleg. Overbodige puntseparatoren in weergaveteksten zijn verwijderd.

## Belangrijke testgevallen

1. Kies een stemprofiel in Instellingen. De stem in een bestaande live verbinding verandert **niet** wanneer de dashboardknop uit staat.
2. Klik op **Inschakelen** in het dashboard. Het gekozen filter wordt in de live verbinding gebruikt. Klik op **Uitschakelen**, zonder dat de verbinding wegvalt.
3. Klik in Instellingen op een stemkaart. Bob en Elise mogen niet vanzelf afspelen. Klik op **Voorbeeld afspelen** voor een bewust voorbeeld.
4. Start **Mijn eigen stem testen** terwijl de microfoon **verbroken** is. Alleen nu speelt de lokale microfoontest met het filter. Is de liveverbinding actief, dan volgt een instructie die eerst te verbreken.
5. Navigeer naar alle drie de pagina's. Alle drie de labels blijven zichtbaar en alleen de actieve pagina krijgt een ring.
6. Open Bibliotheek opnieuw beginnen. Typ iets anders dan `BEVESTIG`; verwijderen moet onmogelijk zijn. Test alleen met een **aparte testbibliotheek** het bevestigde leegmaken. Controleer de herstelkopie en dat audiobestanden op schijf blijven staan.
7. Beweeg de muis over bestandstype, fragmentduur en afspeelteller in de bibliotheek. De tooltip moet duidelijk zijn.

## Teststatus

De automatische Python-testsuite en de JavaScript-syntaxis zijn gecontroleerd in de ontwikkelomgeving. Een Windows-installatie, browserinteractie op echte hardware en de uiteindelijke audioweergave zijn **niet** in deze omgeving gevalideerd.

## Installatie

Gebruik de meegeleverde gecontroleerde PowerShell-starter op de bestaande 6.1.0-beta.4.1-broncode. Hij vergelijkt de SHA256 van het pakket en de te vervangen bronbestanden. Bij een afwijking wordt niets overschreven. De bestaande Updater 1.2 maakt reservekopieën, voert regressietests uit en start opnieuw. Installeer niet tijdens een gesprek en sluit de bestaande geïnstalleerde Setup.exe-versie eerst af als die draait.

De ontwikkelpatch verandert niet automatisch de bestaande **Velopack-geïnstalleerde EXE**. Bouw na een geslaagde test een nieuwe Setup.exe met `Bouw_Windows_Release.ps1` om de zelfstandige versie bij te werken.
