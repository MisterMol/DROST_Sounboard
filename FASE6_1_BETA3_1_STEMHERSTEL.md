# DrostSoundboard 6.1.0-beta.3.1: stemherstel en microfoontest

Deze herstelpatch is uitsluitend bedoeld voor een ongewijzigde 6.1.0-beta.3-broncode.
De audiomixer, soundboardgeluiden, SQLite-instellingen, bestaande voorbeeld-MP3's,
Velopack-opzet en gebruikersbibliotheek blijven behouden.

## Wijzigingen

* Toonhoogte van jongens- en meisjesstem en oudere stemmen duidelijker en warmer/helderder gemaakt. Dat zijn speelse DSP-bewerkingen, geen realistische conversie van leeftijd of identiteit.
* De pitch-shifter houdt zijn leesfase voortaan doorlopend bij, ook wanneer de gevraagde toonhoogte verandert. Dit verkleint het risico op periodiek gekraak of tikken door abrupte fasesprongen.
* Autotune detecteert stemtonen met een genormaliseerde autocorrelatie, corrigeert aangehouden klinkers naar muzikale noten en gebruikt standaard C majeur met snelle correctie voor nieuwe of geresette instellingen. Reeds persoonlijk opgeslagen toonladders blijven behouden.
* De voorbeeldopnames Bob en Elise blijven apart van de knop Mijn eigen stem testen; een profielwissel tijdens de microfoontest mag de voorbeeldstemmen niet starten.
* Mijn eigen stem testen staat prominent boven de voorbeeldsteminstellingen; hierbij staan ook de inkomende en bewerkte microfoonmeters.
* De knoppen voor het terugzetten van profielinstellingen heten Reset en Reset alles.
* Gemelde PortAudio-bufferonderbrekingen worden bij de stemmeters zichtbaar; dit helpt de oorzaak van gekraak te onderscheiden van DSP-artefacten.
* Het Windows-releasebouwscript accepteert herstelversies van het type 6.1.0-beta.3.1.

## Verwacht gedrag

Bij een eigen microfoontest hoor je alleen de fysieke microfoon, lokaal via het eigen luisterapparaat. Via Voorbeeld afspelen kun je afzonderlijk Bob of Elise horen. De twee standen werken niet tegelijk. Alle effectinstellingen en de bestaande audiobibliotheek blijven bewaard.

## Praktijktesten

1. Verbreek de live microfoonverbinding. Gebruik een fysieke koptelefoon, geen VB-CABLE als luisterapparaat.
2. Start Mijn eigen stem testen. Spreek en wissel meerdere malen tussen Jongensstem, Meisjesstem, Oudere man, Oudere vrouw en Autotune. Bob en Elise mogen niet automatisch starten.
3. Gebruik bij Autotune: toonladder majeur, toonsoort C, correctiesnelheid hoog, intensiteit 100%. Houd klinkers langer aan. Autotune is niet bedoeld als realistische realtime studioplugin en is veel subtieler op gewone spraak dan op gezongen noten.
4. Kijk of er tijdens gekraak ook audioonderbrekingen worden gerapporteerd. Zo ja, controleer dan de Windows-audiostuurprogramma's, USB en de uitgaande audio-apparaten.
5. Stop de microfoontest. Klik op Voorbeeld afspelen om Bob of Elise te testen.
6. Gebruik Reset en Reset alles, herstart en controleer dat instellingen bewaard blijven.
7. Verbind de virtuele microfoon en controleer de nieuwe stemfilters in je eigen opname of testgesprek.

## Beperkingen

De tests zijn uitgevoerd in een Linux-container zonder de fysieke Windows-audioapparaten. Periodieke onderbrekingen door USB/WASAPI, bufferunderruns en de werkelijke klank zijn pas op een echte Windows-computer te beoordelen. De karakterprofielen gebruiken eenvoudige toonhoogte- en EQ-bewerkingen. Voor hoogwaardige formantbehoudende stemconversie of studiowaardige Autotune is een zwaardere architectuur nodig, die bewust buiten deze lichtgewicht patch blijft.
