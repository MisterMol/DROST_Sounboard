# Fase 6.1 Beta 4.7: één afspeelbediening

## Waarom

In Beta 4.6 werkte de lokale Preview met een zoekbare tijdlijn, herhalen en volume, maar bij uitzending bleef de tijdlijn alleen-lezen. Bovendien stopte een lokale Preview een al naar VB-CABLE afgespeeld geluid niet. Snelle klikken konden hierdoor voor de gebruiker een onvoorspelbare volgorde veroorzaken.

## Veranderingen

* Het dashboard neemt het Windows-standaardopnameapparaat als dat beschikbaar en bruikbaar is. Als die ontbreekt en precies één fysieke microfoon gevonden wordt, wordt deze gekozen. Bij meerdere microfoons zonder bruikbare standaard blijft de selectie leeg. Handmatige keuzes blijven binnen de sessie behouden.
* Er is één exclusieve afspeelbediening in de browser. De laatst aangevraagde preview of live-uitzending heeft voorrang. Voordat de browser lokaal een preview laat horen, stopt de server het lopende of nog te decoderen soundboardgeluid. De virtuele microfoonverbinding zelf blijft bestaan. Als een globale sneltoets een uitzending start tijdens de preview, sluit die preview.
* De live-tijdlijn krijgt 30 Hz-servermetingen uit de bestaande `EventSource` voor audiometers. Tussen metingen toont `requestAnimationFrame` de positie vloeiend. De oudere statuspolling blijft als terugval bestaan.
* De tijdlijn is tijdens een uitzending zoekbaar. De nieuwe `/api/speler/live`-route geeft opdrachten aan dezelfde Python-audiocallback door en controleert het unieke afspeelbeurt-ID. Een verouderde knopopdracht kan niet het volgende geluid beïnvloeden.
* Herhalen geldt alleen voor het huidige uitgezonden fragment. De audiocallback vult alle audioblokken en begrenst sprongovergangen licht om hoorbare tikken te verminderen. Bij een nieuwe clip staat live-herhalen weer uit.
* De algemene soundboardvolumeschuif werkt nu ook op de live-speler. Dit verandert geen microfoonvolume of individuele volume-instellingen.
* Bij een bewuste sprong of loopgrens past ook een gedempte MP4-video zijn positie aan. Bij normale weergave blijft de bestaande rustige videosynchronisatie in werking. De videoweergave houdt `object-fit: cover` aan vanaf het eerste frame.

## Veiligheid en beperkingen

* De zoek- en herhaal-API is lokaal en vereist het bestaande schrijftoken. Voor een actie moet het opgegeven afspeelbeurt-ID overeenkomen met de actieve audioclip.
* Er wordt geen tweede microfoon- of audiostream gestart. Bestanddecodering blijft buiten de audiocallback.
* De werkelijke seek-precisie wordt begrensd door de sliderresolutie, de audioframerate en bij MP4 door de decodeereigenschappen. De visuele tijdlijn beweegt vloeiend, maar niet elke audio-/videozoekactie kan tot op één milliseconde hoorbaar exact worden gegarandeerd.
* Dit pakket werkt alleen het ontwikkelproject bij. Een reeds geïnstalleerde Windows-app wordt pas bijgewerkt na een nieuwe installerbuild.

## Testen

1. Verbind een microfoon, schakel het soundboard in en start een clip met een duidelijk ritme. Klik halverwege de live-tijdlijn en sleep naar een ander punt. Controleer dat VB-CABLE de juiste positie laat horen.
2. Schakel Herhalen in tijdens uitzenden; het fragment moet doorgaan zonder de microfoonverbinding te verbreken. Schakel Herhalen uit en laat het natuurlijk eindigen.
3. Start fragment A via uitzenden en klik daarna op Preview van B. A moet stoppen voordat B lokaal hoorbaar wordt. Doe ook B naar live C en probeer snelle opeenvolgende klikken.
4. Test live MP4 en controleer of beeld en geluid na een bewuste sprong meebewegen. Test ook normaal MP4-afspelen zonder handmatig zoeken.
5. Verander Soundboardvolume tijdens live, controleer dat je microfoon ongemoeid blijft.
6. Verwijder de Windows-standaardmicrofoon alleen in een veilige testomgeving. Test de situatie met precies één microfoon versus meerdere microfoons.

De volledige Python- en JavaScript-tests zijn geautomatiseerd; de fysieke Windows-luistertest blijft noodzakelijk.
