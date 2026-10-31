# DrostSoundboard 6.1.0 RC6: compact en eenvoudig installeren

**Nog een proefpatch, geen vrijgegeven Windows-installatie.**

RC6 behoudt de microfoonmixer, bibliotheek, favorieten en de gewone DSP-stemeffecten. De grote LLVC AI-stemruntime (Nova, Ruben, Linde en Omroeper) is niet inbegrepen in de compacte Windows-bouw. Er is geen optie meer nodig om de modelruntime bij de standaardinstallatie te downloaden.

## Bouwen op de eigen Windows ontwikkelcomputer

Voor de compacte variant:
```powershell
.\Bouw_Windows_Release.ps1 -Compact -GitHubRepository "https://github.com/MisterMol/DROST_Sounboard"
```

De bouw controleert de EXE, de basisstemmotor en het ontbreken van de grote AI-runtime. De tests die externe binaire bestanden verwachten, werken niet op een kale GitHub-runner en moeten apart worden herzien. De Windows-build moet daarom nog daadwerkelijk op de ontwikkelcomputer worden uitgevoerd.

## Gebruiksgemak

De kleine installerstarter uit PR #1 blijft de aanbevolen ingang. Bied in de volgende release alleen de starter aan als duidelijk aanbevolen download en zet het echte Setup-bestand ernaast als technische directe download. Het soundpack blijft los en optioneel: download het alleen wanneer de gebruiker daarvoor kiest. Laat voortgang en locatie in Downloads zichtbaar zijn. De nieuwe appcode moet een nieuwe release krijgen, niet de bestaande RC5-assets overschrijven.

**Voor publicatie controleren:** echte Windows-installatie, geluidsweergave, gewoon stemfilter, bibliotheekimport, de-installer, systeemvak, herinstallatie en het ontbreken van de AI-stemmen. Meet de werkelijke downloadgrootte na een volledige build. Er is nog geen onderbouwde groottebesparing bekend.
