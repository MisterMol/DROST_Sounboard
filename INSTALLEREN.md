# DrostSoundboard installeren

Dit is de korte handleiding voor **DrostSoundboard 6.1.0 RC4** op Windows 10 of 11.

## Installatie

1. Ga naar [GitHub Releases](https://github.com/MisterMol/DROST_Sounboard/releases).
2. Download de nieuwste geteste `Setup.exe` en open het bestand.
3. Start DrostSoundboard via het Startmenu of je bureaublad. De bediening opent in je browser. De app blijft op de achtergrond in het systeemvak actief.

Python, Git en andere ontwikkelprogramma's zijn niet nodig. De installer is niet digitaal ondertekend. Controleer bij een Windows-waarschuwing eerst of het bestand van de officiële GitHub-repository komt. Schakel je beveiliging niet uit.

## VB-CABLE voor Discord

Zonder VB-CABLE kun je Preview gebruiken, maar niet uitzenden via een virtuele microfoon.

1. Download VB-CABLE via **[de officiële VB-Audio-site](https://vb-audio.com/Cable/)**.
2. Pak de ZIP volledig uit en start op een 64-bits Windows-pc `VBCABLE_Setup_x64.exe` als administrator.
3. Volg de driverinstallatie en **herstart Windows**.
4. Start DrostSoundboard en kies je eigen microfoon. Controleer de verbinding.
5. Open Discord > Gebruikersinstellingen > Spraak en video. Kies als invoerapparaat **CABLE Output (VB-Audio Virtual Cable)**.

De app meldt zelf wanneer VB-CABLE ontbreekt en heeft een link naar de download. VB-CABLE is aparte donationware en wordt niet stilzwijgend geïnstalleerd.

## Geluiden afspelen

**Preview** hoor je zelf. **Uitzenden** gaat naar de virtuele microfoon. Gebruik Stop om een geluid te onderbreken. Via Instellingen kies je je dashboardindeling en via Weergave je thema.

Voor je eigen geluiden gebruik je **Bibliotheek > Importeren**. Op een andere computer kun je een eerder geëxporteerd audiopack importeren. De Setup bevat niet je persoonlijke bibliotheek.

## Problemen?

Als je niets hoort in Discord, controleer VB-CABLE, de verbinding in DrostSoundboard en het invoerapparaat in Discord. Sluit de app via **App afsluiten** of het systeemvak; alleen je browsertab sluiten is niet genoeg.

Een `git clone` bevat **geen volledige stemruntime**. Voor de complete applicatie gebruik je de Windows Setup. Bugs kun je melden via GitHub Issues, zonder privébestanden of volledige logboeken te delen.
