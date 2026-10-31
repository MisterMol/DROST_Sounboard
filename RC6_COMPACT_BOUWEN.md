# DrostSoundboard RC6 Compact: een duidelijke Windows-installer

## Voor de gebruiker

Download en open alleen `DrostSoundboard-Installeren-RC6-Test.exe`.
Deze EXE bevat de compacte RC6-app en toont direct het installatiescherm.
Je hoeft geen Git, Python, .NET SDK, PowerShell of `winget` te installeren.

De installer laat je kiezen of je ook het **optionele startersoundpack met
141 geluiden** wilt toevoegen. Dat is ongeveer 310 MiB extra download
en staat standaard uitgevinkt. Na installatie probeert het venster het
soundpack automatisch te importeren. Bij een importprobleem blijft de
gedownloade ZIP in Downloads staan en krijg je handmatige instructies.
Dubbele geluiden worden overgeslagen; de bestaande bibliotheek blijft bewaard.

## Slechts een GitHub Actions-download

Gebruik de workflow **RC6 installatie-EXE met geluidskeuze bouwen**.
Bij een geslaagde build verschijnt **uitsluitend** dit gebruikersartefact:

`DrostSoundboard-RC6-Een-EXE-Met-Geluidskeuze`

Na downloaden en uitpakken bevat dat precies de zelfstandige
`DrostSoundboard-Installeren-RC6-Test.exe` van circa 73 MiB.

De technische `DrostSoundboard.Desktop-beta-Setup.exe` (Velopack) wordt
**wel intern gebouwd en gecontroleerd**, want deze Setup zit in de uiteindelijke
gebruikers-EXE. Hij wordt **niet afzonderlijk als Actions-artefact aangeboden**.
De vroegere dubbele download `DrostSoundboard-RC6-Compact-Setup` vervalt.
Historische workflow-runs die de oude opzet gebruikten kunnen nog oudere
artefacten tonen; nieuwe runs tonen alleen de installer met geluidskeuze.

## Hoe de Windows-bouw werkt

GitHub Actions voert de tests uit op een tijdelijke Windows-computer,
haalt de gewone DSP-motor uit de gecontroleerde officiele RC5 Setup en
valideert die tegen de vastgelegde SHA256. De grote AI-stemmen Nova, Ruben,
Linde en Omroeper worden niet meegenomen. Daarna wordt de compacte app
verpakt als technische Velopack Setup, wordt die Setup ingebed in het
installatievenster en wordt de ingebedde inhoud opnieuw op SHA256
gecontroleerd. Alleen het resultaat voor gebruikers wordt aangeboden.

Er wordt niets automatisch als nieuwe publieke GitHub-release uitgegeven.
De gepubliceerde RC5 blijft ongewijzigd. De kleine online installerstarter
uit de aparte workflow wordt pas voor RC6 gebruikt nadat de juiste
nieuwe release gepubliceerd is.

## Testen voordat je deze versie uitgeeft

Test op een Windows-computer zonder ontwikkelomgeving: het installatievenster,
de keuze voor het startersoundpack, automatische en handmatige bibliotheekimport,
geluid en gewone stemfilters, microfoon, VB-CABLE indien aanwezig, afsluiten,
starten en opnieuw installeren. Controleer dat de verdwenen AI-stemmen niet
aangeboden worden. Een groene GitHub-build is geen praktijktest.

VB-CABLE is een afzonderlijke Windows-driver en kan administratorrechten
en een herstart vereisen. De testinstaller installeert deze niet ongemerkt.
De EXE is nog niet digitaal ondertekend. Schakel Windows-beveiliging niet uit.

## Alleen voor ontwikkelaars

De bestaande lokale PowerShell-bouwer blijft voor ontwikkelaars bestaan,
maar gebruikers hoeven geen bouwcommando's uit te voeren.
