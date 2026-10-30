# Installeren en eerste keer starten

Dit is de korte handleiding voor DrostSoundboard 6.1.0 RC4. Het is een hobbyproject voor Windows. De Setup-installer wordt met Velopack gemaakt en hoort Python, Git en de ontwikkelomgeving niet nodig te hebben.

## 1. DrostSoundboard installeren

1. Ga naar [GitHub Releases](https://github.com/MisterMol/DROST_Sounboard/releases).
2. Download de nieuwste **geteste** Windowsversie met `Setup.exe` in de bestandsnaam, als die er al staat.
3. Start de Setup. Velopack installeert de app voor je Windowsgebruikersaccount en maakt een snelkoppeling.
4. Open DrostSoundboard. De bediening verschijnt in je standaardbrowser. De app zelf blijft in het Windows-systeemvak actief.

**Verschijnt er een SmartScreen-waarschuwing?** De installer is mogelijk niet digitaal ondertekend. Controleer of je het bestand van de echte GitHub Release hebt gedownload en vergelijk eventueel de SHA256. Schakel Windows-beveiliging niet uit.

## 2. VB-CABLE installeren voor Discord

Wil je soundboardgeluiden via je microfoon delen, dan heb je VB-CABLE nodig. De app controleert bij het starten of de kabel bruikbaar is en toont anders een melding met deze officiële link:

**[VB-CABLE downloaden bij VB-Audio](https://vb-audio.com/Cable/)**

1. Download op die website het actuele Windows-driverpakket.
2. Pak het ZIP-bestand volledig uit. Open het installatieprogramma **vanuit de uitgepakte map**, niet vanuit het ZIP-bestand.
3. Kies op Windows 64-bit `VBCABLE_Setup_x64.exe` en voer dit uit als administrator.
4. Volg de installatie en **herstart Windows**.
5. Open DrostSoundboard opnieuw en klik op **Opnieuw controleren**. Als de app VB-CABLE nog niet ziet, controleer of beide kabelapparaten in Windows ingeschakeld zijn.
6. Open Discord en kies bij de invoerapparaten **CABLE Output (VB-Audio Virtual Cable)**.

VB-CABLE is externe donationware van VB-Audio. DrostSoundboard downloadt of installeert de driver niet zelf en vraagt daarvoor geen administratorrechten. Je kunt zonder VB-CABLE wel lokaal een Preview beluisteren.

| Waarvoor | Kies dit apparaat |
| --- | --- |
| Je eigen stem in DrostSoundboard | Je echte microfoon of Windows-standaardmicrofoon |
| Audio van DrostSoundboard naar de kabel | CABLE Input, wordt door de app gebruikt |
| Microfoon in Discord of een andere app | CABLE Output |
| Zelf luisteren via de headset | Je eigen koptelefoon of Windows-standaarduitvoer |

Een browser sluiten stopt DrostSoundboard niet. Kies **App afsluiten** of **Afsluiten** in het systeemvak als je volledig wilt stoppen. Daarna kan de virtuele microfoon stil zijn; stel dan eventueel je echte microfoon weer in bij Discord.

## 3. Eerste geluid afspelen

1. Kies je microfoon en controleer de audioverbinding.
2. Open het dashboard en zoek een geluid in de bibliotheek rechts of onderaan, afhankelijk van je indeling.
3. **Preview** betekent alleen lokaal luisteren. **Uitzenden** stuurt het geluid naar de virtuele microfoon.
4. Met **Stop**, de tijdlijn en **Blijven herhalen** bedien je het huidige fragment.
5. Via **Instellingen > Dashboardindeling** kies je Klassiek, Bibliotheek centraal of Favorieten eerst. Die keuze wordt onthouden.
6. Met **Weergave** kun je thema's, accentkleuren en persoonlijke thema's instellen.

De knop **Bibliotheek** in de navigatie opent de aparte beheerpagina voor mappen, verplaatsen, bewerken en importeren.

## 4. Je eigen geluiden meenemen

Exporteer op de oude computer je bibliotheek als audiopack. Importeer die op de nieuwe computer via de beheerbibliotheek. De Setup bevat **niet** je persoonlijke geluidsbestanden, database of opnames. Bewaar vóór grote wijzigingen zelf een back-up.

## 5. Git clone voor ontwikkelaars

Heb je Git en Python 3.13 op Windows, dan kun je de broncode klonen:

```powershell
git clone https://github.com/MisterMol/DROST_Sounboard.git
cd DROST_Sounboard
.\Start_Na_Git_Clone.cmd
```

De clone bevat de twee korte ingebouwde MP3-stemvoorbeelden van Bob en Elise, mits die daadwerkelijk naar GitHub zijn gepusht. De clone bevat geen volledige stemruntime, proefmodel of privébestanden. Als die ontbreken, verwijst de starter naar de complete Setup onder Releases. Voor alleen broncode en tests kun je `Installeer_ontwikkelomgeving.bat` uitvoeren en daarna `\.venv\Scripts\python.exe -m unittest discover -s tests -q` gebruiken. Sommige tests vragen extra stemonderdelen of een Windowsomgeving.

## Problemen oplossen

- Geen geluid in Discord: controleer VB-CABLE, de verbinding en de invoerinstelling **CABLE Output**.
- Wel Preview maar geen uitzending: controleer VB-CABLE en of DrostSoundboard verbonden is.
- Geen microfoon gevonden: controleer Windows-invoerrechten en druk op **Vernieuwen**.
- App lijkt nog actief: kijk in het systeemvak en gebruik **App afsluiten**.
- Voice model laadt niet: kijk onder **Instellingen > Probleemoplossing > Stemdiagnose**.

Meld bugs bij GitHub Issues, maar verwijder persoonlijke paden, tokens en audiobestanden uit logs.
