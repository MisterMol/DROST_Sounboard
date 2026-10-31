# DrostSoundboard

Een soundboard voor Windows, gemaakt als hobbyproject. Speel geluiden af, gebruik 15 favorieten, zoek in je bibliotheek en verzend geluiden via een virtuele microfoon.

**Versie 6.1.0 RC5 (testversie)**

## Installeren

**Zonder Git (aanbevolen):** [Download de Windows Setup](https://github.com/MisterMol/DROST_Sounboard/releases) en open `DrostSoundboard.Desktop-beta-Setup.exe`. Python is niet nodig.

**Na git clone:**

```powershell
git clone https://github.com/MisterMol/DROST_Sounboard.git
cd DROST_Sounboard
.\Installeer_DrostSoundboard.cmd
```

De starter haalt de Setup op uit een gepubliceerde GitHub Release en laat je de installatie starten. Je hebt dus wel internet nodig. Staat er nog geen `Setup.exe` bij een Release, dan kan de starter niets installeren.

## VB-CABLE voor Uitzenden

**VB-CABLE is een aparte afhankelijkheid** die je moet installeren om geluiden via de virtuele microfoon te verzenden. Download het via de [officiële VB-Audio-website](https://vb-audio.com/Cable/). Pak het Windows-driverpakket uit, voer de installatie uit als administrator en herstart Windows.

Zonder VB-CABLE kun je wel geluiden toevoegen, beheren en lokaal beluisteren via Preview.

## Functies

15 favorieten, drie dashboardindelingen, zoekfilters en mappen, een speler met tijdlijn, stemvervorming, persoonlijke thema's en een aparte beheerbibliotheek.

De broncode, tests en ontwikkelbestanden staan in deze repository. Voor normaal gebruik is de Windows Setup bedoeld. De broncodeclone bevat niet de complete stemruntime en modellen; de Setup bevat de benodigde gebundelde onderdelen.

DrostSoundboard valt onder de [MIT-licentie](LICENSE). Externe onderdelen hebben hun eigen voorwaarden in [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md). De Setup is nog niet digitaal ondertekend en updates verschijnen voorlopig handmatig.

## Gemakkelijk installeren met zichtbare voortgang

Bij [GitHub Releases](https://github.com/MisterMol/DROST_Sounboard/releases) kun je de normale Windows Setup downloaden. Er is nu ook een **kleine installerstarter** in ontwikkeling: `DrostSoundboard-Installeren.exe`. Zodra deze EXE als Release-asset is toegevoegd, kunnen gebruikers hem starten zonder Git of Python. De starter toont direct een venster met de voortgang voor de officiële Windows Setup en optioneel het startersoundpack.

Het [startersoundpack](https://github.com/MisterMol/DROST_Sounboard/releases/download/v6.1.0-rc.5/DrostSoundboard_startersoundpack.zip) is een **aparte** ZIP van ongeveer 310 MiB met 141 geluiden en 11 mappen. In DrostSoundboard kies je **Bibliotheek > Audiopack importeren**. Uitpakken is niet nodig.

De installerstarter wordt via **GitHub Actions > Installerstarter bouwen** als Windows-EXE gebouwd. Na testen moet de beheerder de EXE nog handmatig bij de GitHub Release uploaden. De bestaande Setup wordt niet vervangen. Windows kan een niet-ondertekende EXE vóór de eerste zichtbare start nog controleren.

Een normale herinstallatie verwijdert geen favorieten of bibliotheek. Voor volledig opnieuw beginnen kun je na het verwijderen van de app **zelf** `%LOCALAPPDATA%\DrostSoundboard` wissen. Exporteer eerst je eigen bibliotheek; verwijdering is definitief.
