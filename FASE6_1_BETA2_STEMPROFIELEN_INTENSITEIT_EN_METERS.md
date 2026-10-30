# DrostSoundboard 6.1.0 Beta 2: stemprofielen en live meters

Deze bèta breidt de stemvervormer uit, zonder de microfoon, bestaande geluidseffecten of VB-CABLE te vervangen.

## Stemprofielen

Onder **Instellingen > Geluid > Stemvervormer** staan nu twaalf profielen met herkenbare, lokaal getekende pictogrammen:

Normaal, Radio, Robot, Diepe stem, Heel lage stem, Hoge stem, Heel hoge stem, Alien, Telefoon, Monster, Echo en Megafoon.

Dit zijn lichte DSP-effecten. Hoge en lage tonen gebruiken een eenvoudige delay-gebaseerde toonhoogteverandering. Ze veranderen ook het stemkarakter en kunnen bij hoge sterkte kunstmatig klinken. Dit is geen formant-correcte studio-pitchshifter. Het effect **Echo** kan bij luid spreken nagalm en oversturing geven. De bestaande pieklimiter op de eindmix blijft van toepassing.

## Intensiteit per profiel

- De schuif gebruikt waarden van **0% tot 100%**. 0% betekent onverwerkt geluid.
- Elk profiel heeft een eigen standaardwaarde. Bestaande Radio-, Robot- en Diepe-stemgeluiden starten op hun oorspronkelijke intensiteit.
- Aanpassingen worden opgeslagen in de bestaande lokale SQLite-database. Originele audio wordt nooit opgeslagen.
- **Herstel dit profiel** verwijdert alleen de override van het gekozen profiel.
- **Herstel alle profielen** zet alle intensiteiten terug, met bevestiging. De profielkeuze zelf blijft bestaan.
- Een oudere database met de oorspronkelijke vier toegestane profielen wordt niet vervangen. Een nieuwe versie-2-tabel bewaart de uitgebreide keuze.

## Live microfoonmeter

De microfoontest toont twee meters: inkomend signaal en de bewerkte stem. Beide waarden zijn dBFS, waarbij 0 dBFS het digitale maximum is. Dit zijn **geen** geluidsdrukniveaus in dB SPL. De meters lezen uitsluitend reeds berekende RMS-niveaus, niet de stem zelf.

- **Mijn stem beluisteren:** start de lokale preview op de eigen koptelefoon, zonder VB-CABLE. Hiervoor moet de liveverbinding uit staan.
- **Liveverbinding:** meters zijn te gebruiken terwijl DrostSoundboard als virtuele microfoon actief is.
- **Niet verbonden:** geen meterwaarde. Start eerst een preview of verbind de microfoon.
- De preview duurt maximaal 90 seconden en wordt beëindigd bij het sluiten of verlaten van de instellingenpagina.

## Veiligheid en prestaties

De audiocallback leest alleen een atomair in geheugen gewisselde snapshot van de intensiteiten. Alle database-, web- en schijf-I/O blijft buiten de audiocallback. De bestaande terugval bij een stem-DSP-fout blijft behouden; geluidseffecten worden pas na de bewerkte microfoon gemengd. Extra dependencies zijn niet toegevoegd.

De eerdere broncode-updater blijft bedoeld voor ontwikkelaars. Voor officiële distributie kan één Velopack-installer worden gebouwd. Automatische publicatie via GitHub blijft uitgesteld.

## Testen

De testset controleert twaalf DSP-profielen, toonhoogteverschuivingen, sterkte nul, database-upgrade, herstelknoppen, CSRF op de API, meters, audiomixer en JavaScript-syntaxis. Het effect op echt Windows/WASAPI en de hoorbare kwaliteit moeten op fysieke hardware worden getest.
