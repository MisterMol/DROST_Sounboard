# DrostSoundboard installeren

Deze handleiding hoort bij DrostSoundboard 6.1.0 RC4 (testversie) voor Windows.

## De app installeren

1. Ga naar [GitHub Releases](https://github.com/MisterMol/DROST_Sounboard/releases).
2. Download `DrostSoundboard.Desktop-beta-Setup.exe` bij de nieuwste release.
3. Open de Setup en start DrostSoundboard vanuit het Startmenu of via de snelkoppeling.

Voor een bestaande installatie kan de Setup vragen of je wilt bijwerken. Dat is normaal. De app draait op de achtergrond via het Windows-systeemvak en opent de bediening in je browser. Python en Git zijn niet nodig.

De Setup is nog niet digitaal ondertekend. Controleer bij een Windows-waarschuwing de herkomst van het bestand. Zet je beveiligingssoftware niet uit.

## Vereiste voor geluiden uitzenden: VB-CABLE

**VB-CABLE is een aparte afhankelijkheid voor Uitzenden.** De driver is niet opgenomen in de DrostSoundboard Setup. Zonder deze driver kun je je bibliotheek beheren en geluiden lokaal beluisteren met Preview.

1. Download VB-CABLE via de [officiële VB-Audio-website](https://vb-audio.com/Cable/).
2. Pak de download volledig uit. Voer de passende Windows-driverinstallatie uit als administrator.
3. Herstart Windows na de installatie.
4. Start DrostSoundboard en kies je microfoon. Controleer of de virtuele audioverbinding werkt.
5. Selecteer in het programma dat de geluiden moet ontvangen **CABLE Output (VB-Audio Virtual Cable)** als microfoon of opnamebron.

DrostSoundboard geeft een melding en een officiële link wanneer VB-CABLE niet gevonden wordt. De driver wordt nooit stilzwijgend geïnstalleerd.

## Gebruik

**Preview** speelt lokaal af. **Uitzenden** stuurt het geluid naar de virtuele microfoon. In de bibliotheek kun je zelf geluiden toevoegen, aanpassen en ordenen. Met Stop onderbreek je een fragment.

De Setup bevat geen persoonlijke geluiden of mappen. Die kun je meenemen door op de oude computer een audiopack te exporteren en op de nieuwe computer te importeren.

## Problemen?

Controleer de gekozen microfoon, VB-CABLE en het invoerapparaat van het ontvangende programma. Sluit DrostSoundboard volledig af via **App afsluiten** of het systeemvak, niet alleen door de browsertab te sluiten.

De broncodecloneroute bevat geen volledige stemruntime. Gebruik de Windows Setup voor de volledige app. Problemen kun je melden via [GitHub Issues](https://github.com/MisterMol/DROST_Sounboard/issues).
