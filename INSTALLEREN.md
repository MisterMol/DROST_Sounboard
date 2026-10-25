# DrostSoundboard installeren

DrostSoundboard 6.0.0-beta.3 is een **testversie**. De Windows-installer is voorbereid, maar moet vóór een openbare release nog getest worden op schone Windows-computers.

## Voor gebruikers: Windows-installer

1. Download de officiële Setup.exe uit een geteste GitHub Release van dit project. Een broncode-ZIP is geen installatiebestand.
2. Start de installer, rond de installatie af en open DrostSoundboard vanuit het Startmenu.
3. De app toont het dashboard in de standaardbrowser. De audiomixer blijft op de achtergrond draaien wanneer je de browser sluit.
4. DrostSoundboard gebruikt bij de eerste start de **Windows-standaardmicrofoon**. Wil je een andere microfoon, kies die dan onder **Instellingen**.
5. Bij **Luisterapparaat** betekent **Automatisch** de **Windows-standaarduitvoer**. Je kunt ook handmatig een apparaat kiezen.
6. Klik op **Verbinden** en schakel desgewenst **Geluidseffecten** en **Meeluisteren** in.

## VB-CABLE

Voor afspelen via een virtuele microfoon is [VB-CABLE](https://vb-audio.com/Cable/) nodig. DrostSoundboard controleert dit bij het openen van het dashboard. Ontbreekt de driver of staat die uit, dan toont de app een duidelijke waarschuwing met de officiële downloadlink en een knop **Opnieuw controleren**. Installatie van de driver is een aparte handeling; Windows kan daarvoor administratorrechten en een herstart vragen.

De namen in Windows zijn doorgaans:

| Functie | Apparaat |
| --- | --- |
| Je eigen microfoon | Windows-standaardinvoer of zelfgekozen microfoon |
| Geluid naar de virtuele microfoon | `CABLE Input` |
| Virtuele microfoon die andere apps kunnen gebruiken | `CABLE Output` |
| Lokaal meeluisteren | Windows-standaarduitvoer of zelfgekozen luisterapparaat |

Je kunt `CABLE Output` in een programma naar keuze als opnameapparaat selecteren. De exacte instelling verschilt per programma. Een **Preview** speelt alleen lokaal af. **Uitzenden** stuurt geluid naar de virtuele microfoon, maar garandeert niet dat een andere app het ook ontvangt.

Als de virtuele microfoon niet bruikbaar is, kun je nog steeds lokaal previews afspelen en je bibliotheek beheren.

## Automatisch opstarten en updaten

De ontwikkelversie heeft een aparte ontwikkelupdater. Gebruik die niet als updateprocedure voor je vrienden. De Windows-release gebruikt Velopack. Die kan nieuwe versies op de achtergrond downloaden en bij een veilig afsluitmoment of vóór een volgende start toepassen. Dit updateproces moet nog end-to-end worden getest voor de eerste publieke release. Zet de app nooit uit tijdens een gesprek.

De optie **Start met Windows** staat standaard uit. Aanzetten is een gebruikerskeuze; er wordt bij aanmelding geen browservenster geopend.

## Voor ontwikkelaars

De broncode vereist Python en de afhankelijkheden uit `requirements.txt`. Deze ontwikkelinstallatie staat los van de zelfstandige installer.

1. Clone het project naar een eigen map.
2. Draai `Installeer_ontwikkelomgeving.bat` en start via `Start_DrostSoundboard_Desktop.bat`.
3. Draai vanuit de projectmap `.\.venv\Scripts\python.exe -m unittest discover -s tests -q` in PowerShell met Windows-paden.
4. Voor een Windows-build gebruik je `Bouw_Windows_Release.ps1` met .NET SDK, vpk en PyInstaller volgens `FASE6_0_BETA1_INSTALLER_EN_UPDATES.md`.

De oudere `FASE*.md`-bestanden zijn historische ontwikkel- en testverslagen en kunnen nog oorspronkelijke apparaatnamen en testomgevingen noemen. Voor installatie door nieuwe gebruikers is **dit document leidend**.
