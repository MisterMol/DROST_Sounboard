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
