# Complete offline installatie, RC5 proefbuild

Dit project bouwt een enkel bestand `DrostSoundboard-Complete-Setup.exe` met de bestaande Windows Setup en `DrostSoundboard_startersoundpack.zip`. Het is een **testbuild** en verandert de bestaande RC5-release niet.

## Bouwen
Open op GitHub **Actions > Complete offline installer RC5 > Run workflow**. Download na een geslaagde build het artefact `DrostSoundboard-Complete-Setup-RC5`. Je kunt ook op Windows `Bouw_Complete_Installer.ps1` gebruiken met Inno Setup 6. De bouw downloadt de officiële RC5-onderdelen en vergelijkt hun SHA256 met de verwachte hashwaarden voordat er een nieuw pakket wordt gemaakt.

## Installeren
De gebruiker opent één grote EXE. De Inno Setup-buitenlaag pakt de originele Velopack-installer en het soundpack tijdelijk uit. Vervolgens installeert de Runner de app, bewaart een kopie van het soundpack in Downloads en probeert de inhoud automatisch aan de bestaande bibliotheek toe te voegen. Reeds aanwezige geluiden worden overgeslagen. Bestaande gebruikersdata wordt niet verwijderd.

Bij een fout in de automatische import staat de ZIP nog in Downloads zodat gebruikers de geluiden handmatig kunnen importeren. VB-CABLE blijft een afzonderlijke optionele driver.

**Publiceer nog niet zonder praktijktest op een schone Windows-pc.** De publieke RC5 blijft voorlopig ongewijzigd. Zet een geteste complete bundel bij voorkeur op een aparte releasepagina met een ondubbelzinnige naam, bijvoorbeeld `v6.1.0-rc.5-complete.1`. Dit pakket bevat de RC5-app; het bevat niet automatisch latere wijzigingen uit PR #1. Gebruik geen misleidend RC6-versielabel.

Zorg ervoor dat je toestemming hebt om alle geluiden in het soundpack te verspreiden. De complete EXE is nog niet digitaal ondertekend.
