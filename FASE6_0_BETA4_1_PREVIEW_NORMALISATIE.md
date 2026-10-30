# DrostSoundboard 6.0.0-beta.4.1: herstel normalisatie en hoorbare preview

De eerste Beta 4 normaliseerde het af te spelen geluid vóór de persoonlijke
volumeregeling. Als het bronfragment bijvoorbeeld op 200% stond, kon die
volumeregeling de correctie weer ongedaan maken. Bovendien gebruikte Preview
het originele bestand zonder normalisatie. Daardoor veranderde de hoorbare
browserpreview nooit wanneer je Uit, Subtiel of Sterk koos.

## Herstel

* Persoonlijk volume wordt eerst toegepast met de bestaande digitale
  piekbescherming. Daarna wordt de normalisatiefactor berekend en toegepast.
  Dit gebeurt **buiten** de realtime audiocallback.
* Een browserpreview vraagt per geselecteerd fragment alle vier
  normalisatieversterkingen aan de lokale, beveiligde API op. De eigenlijke
  geluidsweergave loopt via de Web Audio API met een GainNode. Ook MP4-video
  blijft daardoor intact en hoeft niet opnieuw te worden gerenderd.
* Tijdens een lopende Preview kun je schakelen tussen Uit, Subtiel, Normaal
  en Sterk. Je hoort de nieuwe versterking meteen, zonder het fragment opnieuw
  te starten. Onder Geluidsnormalisatie zie je de correctie in dB.
* De fragmenteditor gebruikt dezelfde berekening op de gekozen selectie.
* Originele mediabestanden, bibliotheek, microfoonstream, favoriete geluiden
  en triminstellingen worden niet gewijzigd.
* Eerder opgeslagen normalisatiestanden blijven bestaan.

De beschikbare standen blijven bewust begrensd. Als een fragment al op het
doelniveau zit of hoge pieken verdere versterking blokkeren, kan een
correctie `0,0 dB` bedragen. Dat is geen meetfout. Dit is RMS-normalisatie,
geen LUFS-loudnessmatching, equalizer of limiter. Dat kan later worden
verfijnd op basis van praktijktests.

## API en systeemlast

`GET /api/geluiden/{id}/preview-normalisatie` vereist het bestaande lokale
beveiligingstoken. Er wordt alleen een bibliotheekbestand onder de beheerde
mediamap onderzocht. Maximumduur is 120 seconden. Er wordt nooit een
microfoonstream geopend. Er vindt maximaal één parallelle previewanalyse
plaats, en de laatste acht resultaten worden in een kleine cache bewaard.
Een eerste preview moet soms kort worden voorbereid, vooral bij MP4.

## Testen op een echte Windows-pc

1. Start DrostSoundboard en open de webpagina opnieuw met Ctrl+F5.
2. Kies een hard fragment met bijvoorbeeld volume 200% en klik Preview.
3. Zet Geluidsnormalisatie van Uit naar Sterk **terwijl de preview speelt**.
   De preview moet hoorbaar zachter worden en onder Geluidsnormalisatie moet
   een negatieve correctie in decibel staan.
4. Kies een zacht fragment en test Normaal en Sterk. Een positieve correctie
   kan worden getoond, zolang dat zonder digitale oversturing mogelijk is.
5. Test apart `Uitzenden` via VB-CABLE. De microfoon mag bij het stoppen van
   effecten niet wegvallen.
6. Herstart de app en controleer dat de instelling bewaard is gebleven.
7. Test desgewenst ook de preview in de fragmenteditor, inclusief MP4-video.

## Beperkingen

De automatische tests bewijzen de gainberekening, HTTP-tokencontrole en
JavaScript-gainroutering. Een browseraudit met echte audio-apparaten en de
Windows-installer moeten op Windows zelf gebeuren. Automatische GitHub-updates
worden in deze patch niet aangepast.
