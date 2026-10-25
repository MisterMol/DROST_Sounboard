# Architectuur van DrostSoundboard

Dit is de korte wegwijzer voor iemand die de code voor het eerst opent.

## Wat gebeurt er als je op een geluid klikt?

1. `app/webinterface/statisch/dashboard.js` leest de klik en roept via **`vraagAanPython()`** de lokale API aan.
2. `app/webinterface/lokale_webserver.py` controleert herkomst, tokens en parameters en geeft de opdracht door.
3. `app/webinterface/bediening_van_de_audiomotor.py` zorgt dat het juiste geluid wordt opgezocht en voorbereid.
4. `app/audio/live_audiomixer.py` mixt het gekozen effect met de microfoon en stuurt dat naar VB-CABLE.
5. `app/webinterface/statisch/video_synchronisatie.js` toont alleen het gedempte MP4-beeld. Python blijft de audioklok.
6. `app/diagnostiek/logboek.py` bewaart de relevante auditgebeurtenis en eventuele technische fout.

Preview gebruikt de browser en **niet** de virtuele microfoon. De live-mixer opent alleen de echte audioapparaten; browser en editor mogen geen extra microfoonstream starten.

## Waar hoort een wijziging thuis?

| Verandering | Begin hier | Waarom? |
| --- | --- | --- |
| Video blijft hangen of springt | `statisch/video_synchronisatie.js` | Video- en audioklok blijven gescheiden |
| Knoppen, favorieten of editor | `statisch/dashboard.js` | Presentatie kent geen echte audiodriver |
| HTTP-route of upload | `lokale_webserver.py` | Controle en autorisatie zitten hier |
| Structuur van fouten | `api_foutantwoorden.py` | API-antwoorden blijven consequent |
| Geluid wordt uitgezonden | `bediening_van_de_audiomotor.py` | Coördineert zonder zelf te mixen |
| Realtime samples | `audio/live_audiomixer.py` | Audiocallback blijft kort en voorspelbaar |
| MP4 decode, uitvoer of GIF | `audio/mp4_verwerken.py` en `webinterface/losse_media_exporteren.py` | Media en export staan los van realtime audio |
| Systeemvak en globale sneltoetsen | `desktop/` en `start_desktop.py` | Browser mag dicht zonder dat audio stopt |
| Technische logs of audit | `diagnostiek/logboek.py` | Fouten blijven ook zonder browser zichtbaar |

## Afspraak voor Python-fouten

Alle API-fouten behouden minimaal `fout`, `fouttype` en `foutcode`. De standaardvorm wordt gemaakt in `app/webinterface/api_foutantwoorden.py`. Een onverwachte fout geeft een veilige melding met `referentie`; het volledige pad, type en traceback komen alleen in `software.jsonl` met diezelfde referentie.

We bewaren bestaande velden omdat oudere webclients nog dezelfde routes kunnen aanroepen. Voeg velden toe zonder eerdere sleutels ongemerkt te verwijderen. Nieuwe foutcodes hebben een beschrijvende prefix, bijvoorbeeld `VIDEO-003`.

## Audioklok en MP4

**Nooit bij ieder statusbericht `video.currentTime` instellen.** Dat veroorzaakt zichtbaar zoeken en haperingen. De videomodule start na `loadedmetadata` en `seeked`, en maakt het beeld pas zichtbaar na het eerste gedecodeerde frame. Daarna corrigeert hij kleine verschillen met een minimale verandering van de afspeelsnelheid. Alleen langdurige, grote verschillen rechtvaardigen opnieuw zoeken.

De voorbereidingsstatus toont een statisch beeld; pas zodra Python echt speelt, wordt één nieuwe videospeler aangemaakt. Bij Stop ruimen we deze op, maar **niet** de microfoonverbinding.

## Beveiliging en opslag

- Alleen `127.0.0.1`, een per-start-token en gecontroleerde HTTP-routes.
- Geen microfoonopnames, geheimen, `.venv` of persoonlijke logs naar GitHub.
- Gebruikersbestanden onder `%LOCALAPPDATA%\DrostSoundboard`, nooit in de broncodemap.
- Onverwachte crashes worden met traceback gelogd, zonder de fouten uit de audiocallback direct naar schijf te schrijven.

## Testen

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -q
```

Een optional JavaScript-regressietest draait met Node als die op de ontwikkelcomputer staat; Windows-eindgebruikers hebben Node niet nodig. Test MP4 daarnaast altijd op een Windows-pc met korte en lange clips, een niet-nul-knipbegin, Preview, Stop en snel wisselen. Test ook dat de gesprekspartner alleen de via VB-CABLE gestuurde audio ontvangt.

## Bekende vervolgstappen

De hoofdfile `dashboard.js` en de HTTP-router zijn nog groot. Splits ze later functie voor functie uit met regressietests. Begin niet met een grote herschrijving van de audiomixer terwijl de Windows-verbinding stabiel is. **Volgende fase: 6.0, Windows-installer en schone build**, na verificatie van versie 5.9.4 op echte hardware.
