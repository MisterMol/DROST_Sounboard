# DrostSoundboard RC6 Compact: één EXE voor gebruikers

Gebruikers installeren DrostSoundboard uitsluitend via een Windows EXE.
Zij hoeven geen Git, Python, .NET SDK, PowerShell of `winget` te openen.
De kleine installer downloadt de echte Setup en voert die uit. Het startersoundpack
is een **optionele** keuze van circa 310 MiB. Wanneer gekozen probeert de
installer de geluiden na de appinstallatie automatisch toe te voegen.
Dubbele geluiden worden overgeslagen, en een bestaand geluidenarchief
wordt niet verwijderd. Als automatische import mislukt, staat de ZIP nog in Downloads.

## Windows Setup en echte éénklikinstallatie automatisch bouwen op GitHub

De nieuwe workflow levert twee artefacten op. De technische
`DrostSoundboard-RC6-Compact-Setup` is alleen bedoeld om de verpakte app
afzonderlijk te controleren. Dit is een vrijwel stille Velopack Setup.

De **gebruikersgerichte testinstaller** heet
`DrostSoundboard-RC6-Een-EXE-Met-Geluidskeuze`. Deze bevat één
`DrostSoundboard-Installeren-RC6-Test.exe`, met de compacte
RC6 Setup al inbegrepen. Die toont een echt Windows-venster met uitleg,
een optioneel vinkje voor 141 startergeluiden, voortgang en de knop om
DrostSoundboard te openen. Dit bestand is circa 73 MiB plus een klein
installatievenster. Voor alleen de app is geen internet nodig tijdens de
testinstallatie. Als iemand het soundpack aanvinkt, wordt dit afzonderlijk
vanaf de bestaande officiële Release gedownload en in de app geïmporteerd.

De losse kleine internetstarter blijft voor latere publieke releases bestaan,
maar hoort niet bij deze zelfstandige RC6-test. Publiceer de nieuwe versie
pas nadat het volledige gebruikerspad op Windows is gecontroleerd.

## Technische RC6-bouw op GitHub

Gebruik de workflow **RC6 automatisch compacte Windows Setup bouwen** onder
GitHub Actions. Deze workflow voert de volledige test- en releasebouw uit
op een tijdelijke Windows-computer in GitHub Actions.

De GitHub-runner haalt één specifieke, via SHA256 vastgepinde officiële RC5
Setup op, pakt die in een geïsoleerde map uit en controleert
`drost_stem.dll` op de verwachte SHA256.
De kleine native DSP-motor is nodig voor de gewone stemfilters.
De zware LLVC AI-stemruntime blijft **buiten** de compacte RC6.

Na geslaagde bouw verschijnt het artefact
**DrostSoundboard-RC6-Compact-Setup**, dat één
`DrostSoundboard.Desktop-beta-Setup.exe` bevat.
GitHub downloadt dit bouwartefact als ZIP; pak de ZIP uit om de EXE te testen.
De workflow publiceert de nieuwe Setup **niet automatisch** als GitHub Release.
Daarvoor moeten de werkelijke Windows-installatie en het geluid nog worden getest.
De grootte van de RC6 Setup verschijnt in het Actions-runoverzicht.

De kleine **DrostSoundboard-Installeren.exe** wordt apart automatisch gebouwd
via de workflow **Installerstarter bouwen**. Hij kiest pas de nieuwe RC6 Setup
nadat een geteste RC6-release daadwerkelijk is gepubliceerd.
Tot dat moment verwijst de huidige openbare installer nog naar RC5.
Verander de bestaande RC5-downloads niet.

## Testen vóór publieke release

Test een verse Windows-installatie, bestaande favorieten, diep en hoog,
lokale preview, microfoon en VB-CABLE, bibliotheekimport, app-afsluiten en
herstarten. Controleer dat Nova/Ruben/Linde/Omroeper ontbreken. De scripts
verifiëren bestanden en gedrag, maar vervangen deze praktijktest niet.

VB-CABLE is een aparte Windows-driver en vereist zo nodig gebruikersgoedkeuring
en een herstart. De app kan hem niet ongemerkt als onderdeel van een gewone
gebruikersinstallatie toevoegen.

## Alleen voor ontwikkelaars

De bestaande PowerShell-bouwer blijft beschikbaar voor wie de Windows-build
liever lokaal uitvoert, maar gewone gebruikers hoeven deze route niet te kennen.
