# DrostSoundboard 6.0.0-beta.4: lichte geluidsnormalisatie

Deze patch is gemaakt op basis van de volledige broncode van **6.0.0-beta.3**.
Automatische GitHub-releaseupdates blijven buiten deze fase. Er wordt geen
nieuwe afhankelijkheid geïnstalleerd.

## Wat verandert er?

In **Audioverbinding** staat een nieuwe instelling **Geluidsnormalisatie**:

| Stand | Effect |
| --- | --- |
| Uit (standaard bij een bestaande installatie) | Speelt identiek af aan Beta 3 |
| Subtiel | Corrigeert zacht, maximale versterking 1,4 maal |
| Normaal | Corrigeert merkbaar, maximale versterking 2 maal |
| Sterk | Corrigeert stevig, maximale versterking 3 maal |

Deze standen werken alleen op *soundboardfragmenten die via de virtuele
microfoon worden uitgezonden*. De microfoon, Windows-apparaten en browserpreview
worden niet bewerkt. Dat staat expliciet bij de instelling vermeld.

De instelling wordt in de bestaande SQLite-bibliotheek opgeslagen en is dus na
herstart nog actief. Verandering geldt vanaf het **volgende** fragment; een
reeds lopend fragment wordt nooit halverwege aangepast.

## Hoe werkt de normalisatie?

De speler leest zoals voorheen alleen het geselecteerde deel, met maximaal
twee minuten audio, in een aparte decodewerkdraad.

Daarna meet `app/audio/geluidsnormalisatie.py` de RMS-sterkte in vensters van
100 milliseconden. Stille vensters worden uitgesloten. De 70e percentielwaarde
van actieve vensters bepaalt een enkele versterkingsfactor voor het hele fragment.
De benodigde hoeveelheid extra geheugen blijft klein. De factor wordt
begrensd om versterking van ruis en overschrijding van digitale samplepieken
te voorkomen. De handmatig ingestelde volumes (0 tot 200%) blijven bestaan
en worden **na** de normalisatie toegepast.

Hierdoor blijft de oorspronkelijke dynamiek binnen een clip intact. Dit is
een eenvoudige RMS-gebaseerde normalisatie en **geen** gegarandeerd gelijke
waargenomen luidheid volgens EBU R128/LUFS. Een zwaar gecomprimeerd nummer en
een fragment met hoge pieken kunnen nog verschillen. Een echte limiter volgt
in de volgende patch.

## Wat blijft behouden?

- De originele MP3-, WAV- en MP4-bestanden worden nooit overschreven.
- Bestaande individuele geluidsvolumes, trimposities, groepen en favorieten
  blijven ongemoeid.
- Het uitlezen en aanpassen van de stand verloopt via een lokale HTTP-API met
  de bestaande beveiligingstoken voor schrijfacties.
- De realtime audiocallback wordt niet gewijzigd en rekent geen RMS meer uit.
- Het wijzigen van de stand start of stopt geen microfoon- of VB-CABLE-stream.

## Grenzen en gebruik

Deze normalisatie beïnvloedt **uitzenden via de virtuele microfoon**, niet
`Preview` in de browser of losse media-export. Voor die twee blijft de bron
ongewijzigd, zodat er geen misverstand ontstaat over het originele bestand.

De standen hebben bewust versterkingsgrenzen; een zeer stil bronbestand met
hoge losse pieken kan dus niet altijd tot dezelfde RMS worden opgetrokken.
Dit is normaal en veiliger dan sterke vervorming introduceren.

## Geautomatiseerde tests

Nieuwe regressies dekken stille, zachte en harde fragmenten, piekbescherming,
onjuiste invoer, MP3/WAV, behouden bronbestanden, volumeknop op nul, SQLite-
opslaan, het doorgeven van de keuze aan de decodewerkdraad, de HTTP-API en
bescherming tegen ongeautoriseerd opslaan. Het volledige testcommando is:

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -q
```

De oorspronkelijke Windows-hardwaretest en de Windows-Setup-test moeten nog
op een echte computer worden uitgevoerd. Voer de ontwikkelpatch niet uit
terwijl je in een gesprek zit: Updater 1.2 stopt de microfoon tijdelijk.
