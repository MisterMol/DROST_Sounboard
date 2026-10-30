# DrostSoundboard 6.1.0-beta.4.1: eigen stem horen en audiopacks

Deze patch is bedoeld als gerichte update voor `6.1.0-beta.4` met Updater 1.2.

## Eigen stem horen

Op het dashboard staat naast Geluidseffecten en Meeluisteren de schakelaar **Eigen stem horen** en een volumeregeling van 1 tot en met 100 procent. De standaardstand is **uit**, het standaardvolume is **25 procent**. De instelling blijft bewaard in de lokale SQLite-database.

De bestaande, al gebruikte microfoonstream levert de stem na de gekozen stemvervormer. Een kopie van het resultaat wordt uitsluitend naar het geselecteerde fysieke luisterapparaat gestuurd. Er wordt geen tweede microfoon geopend. De schuifregelaar past de uitvoer naar VB-CABLE niet aan. Als Meeluisteren ook ingeschakeld is, kun je daarnaast de geluidseffecten blijven horen.

De eigen stemmonitor gebruikt de bestaande headset-output. Bij onjuiste headsetselectie kan feedback of rondzingen ontstaan. Gebruik een koptelefoon en begin met laag volume. De monitoring voegt apparaatgebonden uitvoervertraging toe; het is geen nultijd-monitoring.

## Audiopacks en volledige bibliotheek

- Maximaal **500 geluiden per audiopack**.
- Maximaal **1 GiB (1.073.741.824 bytes) uitgepakte inhoud** voor media, afbeeldingen en manifest. Vanwege de bestaande decoderlimiet blijft een afzonderlijk mediabestand maximaal 250 MiB.
- Op de bibliotheekpagina opent **Bibliotheek exporteren** eerst een inhoudsoverzicht met alle geluiden en mappen, inclusief lege mappen. Je kunt vervolgens een volledig ZIP-pakket downloaden.
- De importcontrole berekent SHA256 van mediabestanden. Byte-identieke bestanden worden herkend ongeacht hun bestandsnaam. Ook dubbele bestanden binnen hetzelfde pakket worden gemarkeerd.
- Nieuwe geluiden zijn standaard aangevinkt. Al aanwezige of dubbele geluiden zijn standaard niet aangevinkt. Met **Ook al aanwezige geluiden opnieuw toevoegen** mag de gebruiker expliciet extra exemplaren selecteren.
- Als een geluid dezelfde naam heeft maar andere inhoud, wordt dat apart vermeld en niet automatisch genegeerd.
- Een ZIP wordt vooraf gevalideerd. Paden binnen ZIP-bestanden worden niet direct op schijf uitgepakt; de app maakt veilige bestandsnamen aan.
- De volledige export omvat mediabestanden, namen, fragmentinformatie, ingestelde volumes, afbeeldingen, groepen en lege mappen. Dit is **geen volledige back-up van alle appinstellingen**: apparaatinstellingen, steminstellingen, gebruikshistorie en globale sneltoetsen worden niet meegenomen.

## Installatie en compatibiliteit

Deze update verandert geen bestaande audiobestanden of favorieten en vervangt geen SQLite-database. Updater 1.2 maakt een back-up van de gewijzigde projectbestanden, voert de regressietests uit en verifieert de nieuwe versie. Installeer buiten een actief gesprek; de virtuele microfoon stopt tijdelijk.

Een Windows-installer voor deze specifieke patch is nog niet gebouwd. Voordat je deze versie met anderen deelt, moet een nieuwe Setup.exe op Windows gebouwd en praktisch getest worden.
