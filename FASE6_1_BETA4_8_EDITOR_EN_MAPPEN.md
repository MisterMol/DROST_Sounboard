# DrostSoundboard 6.1.0-beta.4.8: fragmenteditor en mapbeheer

## Waarom deze update?

Bij het bewerken van een geluid moest je eerder eerst opslaan of het bewerkvenster verlaten om het fragment via de virtuele microfoon te testen. Een grote bibliotheek bevat bovendien zoveel mappen dat de oude reeks selectievakjes onoverzichtelijk werd. En een verkeerd gekozen map kon alleen per geluid worden gecorrigeerd.

## Gewijzigd

1. De fragmenteditor heeft naast **Preview** nu **Uitzenden** en **Stop**. De huidige niet-opgeslagen beginpositie, duur en individuele volume worden voor die ene afspeelbeurt toegepast. De opgeslagen brongegevens wijzigen pas na **Wijzigingen opslaan**.
2. **Effectvolume** heet nu **Volume van dit geluid**. Het is nog steeds de bestaande individuele 0 tot 200%-regeling, geen nieuwe versterker. Het **Soundboardvolume** onder Instellingen blijft onafhankelijk.
3. De mapkeuze in de editor is een doorzoekbare, scrollbare boom. De zoekfunctie doorzoekt ook bovenliggende mappaden. Een selectie verdwijnt niet wanneer een map buiten de zoekresultaten valt.
4. Bij **Bibliotheek > Selectie beheren** is **Uit map halen** toegevoegd. Selecteer meerdere geluiden, kies de map en bevestig. Alleen die ene mapkoppeling wordt verwijderd, niet het bestand, de favoriet of koppelingen naar andere mappen.
5. Algemene voorbeeldteksten en het titelveld van het oudere Windows-venster zijn merkonafhankelijk gemaakt. Eigen namen die gebruikers eerder in de bibliotheek hebben gezet blijven natuurlijk bewaard.

## Veiligheid en beperkingen

* Uitzenden vereist een verbonden microfoon en ingeschakeld Soundboard.
* Het beginpunt en de duur van de editor worden gevalideerd tegen bestaande fragmentgrenzen; de bewerkte selectie is maximaal twee minuten.
* Gelijktijdige preview en uitzending worden via de bestaande exclusieve afspeelwachtrij verwerkt. Het gewone microfoonsignaal blijft verbonden.
* De groepsverwijdering werkt in een database-transactie en controleert alle IDs voordat iets wordt losgemaakt.
* De huidige ontwikkelupdater maakt vóór overschrijven een back-up en voert regressietests uit. Deze patch is alleen voor bronversie **6.1.0-beta.4.7**.
* De geïnstalleerde zelfstandige Windows-app wordt door de ontwikkelpatch niet bijgewerkt. Daarvoor is een nieuwe Setup.exe nodig.

## Praktijktest

- Open een geluid, pas de knipselectie en het individuele volume tijdelijk aan. Klik **Preview** en **Uitzenden** en controleer beide resultaten. Sluit zonder op te slaan en heropen: de oorspronkelijke beginpositie en het oorspronkelijke volume moeten er nog staan.
- Zoek in de editor naar een diep gelegen map, selecteer die, zoek een andere en vink deze ook aan. Beide keuzes moeten behouden blijven bij opslaan.
- Zet twee tijdelijke geluiden in bijvoorbeeld een map **Muziek** en een map **Voorbeelden**. Selecteer ze en gebruik **Uit map halen** voor Muziek. Beide geluiden blijven in Voorbeelden en in Alle geluiden staan.
- Controleer de preview, live audio en de virtuele microfoon op een echte Windows-pc. De automatische tests zijn geen fysieke WASAPI-luistertest.

## Teststatus

In de ontwikkelomgeving: 523 automatische Python-tests uitgevoerd, één overgeslagen, geen fouten. De JavaScript-hulptests voor de editor met 120 mappen en tijdelijke uitzending slaagden ook. Visuele Windows-browserbediening en de ontwikkelupdater zijn hier niet fysiek uitgevoerd.
