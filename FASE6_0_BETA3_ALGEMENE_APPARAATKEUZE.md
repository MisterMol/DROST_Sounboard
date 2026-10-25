# DrostSoundboard 6.0.0-beta.3: algemene apparaatkeuze en teksten

## Wat is veranderd

- De dubbele status rechtsboven in het instellingenpaneel is verwijderd. De algemene status boven in het dashboard blijft zichtbaar.
- Previews krijgen algemene uitleg over lokaal afspelen, zonder verwijzingen naar individuele communicatieplatforms.
- De app veronderstelt niet langer dat de gebruiker een bepaald merk microfoon of headset heeft.
- Bij het openen van het dashboard selecteert het microfoonmenu de **Windows WASAPI-standaardinvoer**, tenzij de gebruiker op het huidige scherm zelf een apparaat heeft gekozen.
- **Automatisch** voor meeluisteren gebruikt de **Windows WASAPI-standaarduitvoer**. Een handmatig gekozen luisterapparaat heeft voorrang.
- De virtuele kabel wordt nooit automatisch als lokaal luisterapparaat gebruikt; dat kan terugkoppeling veroorzaken.
- Als geen bruikbaar standaardapparaat bestaat, wordt niet het eerste willekeurige apparaat geselecteerd. De gebruiker kan expliciet een keuze maken.
- De backend controleert een Windows-apparaatnummer bij het verbinden opnieuw. Apparaten kunnen bij aansluiten en loskoppelen een ander nummer krijgen.

## Wat de patch niet doet

De reeds draaiende audiostream wordt niet meteen omgeleid als Windows tijdens gebruik het standaardapparaat verandert. Vernieuw de apparaten en verbind de audio opnieuw wanneer het standaardapparaat is veranderd. Er is geen nieuwe driver, geen bibliotheekmigratie en geen wijziging in de PortAudio-callback.

## Acceptatietests op Windows

1. Zet in Windows een andere standaardmicrofoon dan het eerste apparaat in de lijst. Start DrostSoundboard en controleer dat dit de geselecteerde microfoon is.
2. Verander het standaardluisterapparaat van Windows. Start opnieuw met meeluisteren op Automatisch en controleer dat het juiste apparaat wordt gebruikt.
3. Selecteer een ander luisterapparaat met de hand en controleer dat Windows standaard het niet onverwacht overschrijft.
4. Kies geen bruikbaar standaardluisterapparaat of maak het los. De app mag nooit zomaar VB-CABLE gebruiken voor lokaal meeluisteren.
5. Luister een preview; de melding noemt geen externe app en er wordt geen geluid via de virtuele microfoon uitgezonden.
6. Controleer dat slechts één verbindingsstatus zichtbaar is en dat verbinden/verbreken de audiomixer correct aanstuurt.

## Installatie

Gebruik de meegeleverde gecontroleerde installatiestarter met Updater 1.2. Installeer niet tijdens een gesprek. De updater maakt een back-up, voert de tests uit en controleert de draaiende versie. De zelfstandige Velopack-installer voor eindgebruikers kan pas worden vrijgegeven nadat die apart op Windows is getest.
