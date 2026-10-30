# DrostSoundboard 6.1 Beta 4: bibliotheek, mappen en audiopacks

## Doel

De bestaande geluidsbibliotheek beheert nog steeds de originele media en gebruikersgegevens; alleen de presentatie en aanvullende indeling veranderen. De dialoog voor bibliotheekbeheer is een **aparte pagina** geworden. De mappenlijst is groter en blijft bij veel mappen scrollbaar. Lange titels mogen tot drie regels gebruiken.

## Nieuwe bediening

- Open **Bibliotheek** vanuit het dashboard. De pagina heeft een zoekveld, een hiërarchische mappenlijst, bestandstypen, sortering en herkenbare beheerknoppen.
- **Nieuwe map** maakt een map op hoofdniveau. Kies een bestaande map en klik **Submap** voor een onderliggende map. Je kunt een map naar een andere map slepen of via het menu `···` de naam en bovenliggende map veranderen.
- Geluiden kun je naar een map slepen. Dit koppelt het geluid aan die map zonder het bronbestand te verplaatsen. De oorspronkelijke bibliotheek blijft behouden en een geluid mag bij meerdere mappen horen.
- Geluiden in een submap zijn ook zichtbaar wanneer je de bovenliggende map selecteert.
- Sorteer geluiden op **Naam A tot Z**, **Naam Z tot A** of **Meest afgespeeld**. Sorteer de mappen op **Naam** of **Meest gebruikt**. Populariteit telt uitzendingen via de soundboarduitvoer, **niet** previewluisterbeurten. Oude recente uitzendingen worden eenmalig meegenomen voor zover die geschiedenis nog beschikbaar is.
- Voor selectieacties gebruik je **Selectie beheren**. Hier vind je bijvoorbeeld groepsgewijze export, aanpassen van volumes en verwijderen. Bij verwijderen blijven de oorspronkelijke bestanden intact.
- Het dashboard biedt nu alleen een kleine stemvervormerregel met een profielkeuze, aan/uitknop en **Instellen**, die rechtstreeks naar het stemgedeelte in Instellingen gaat.

## Audiopacks

**Map delen** exporteert de geluiden van de gekozen map, inclusief submappen, als één DrostSoundboard ZIP met media, namen, instellingen, metadata en groepspaden. Ook **Export selectie** blijft mogelijk.

**Audiopack importeren** accepteert DrostSoundboard ZIP-pakketten en gewone ZIP-bestanden met MP3, WAV of MP4 in submappen. De app toont eerst een boomstructuur met selectievakjes; vink één fragment of een hele map aan. Een gedeeltelijk gekozen bovenliggende map wordt als gedeeltelijk geselecteerd weergegeven. De selectie wordt pas bij **Importeren** uitgevoerd. Er worden nooit bestanden naar paden uit de ZIP uitgepakt. Ongeldige ZIP-paden, te grote bestanden, kapotte audio en onverwachte formaten worden geweigerd. De import wordt bij een fout opgeruimd en de bestaande bibliotheek blijft ongemoeid.

Limiet: maximaal **250 geluiden**, **500 MiB uitgepakte inhoud** per audiopack. De huidige bibliotheek heeft nog een oude SQLite-uniekheidsregel voor mapnamen. Twee mappen met exact dezelfde naam, ook onder verschillende bovenliggende mappen, zijn daarom in deze patch nog niet toegestaan; een conflict wordt duidelijk gemeld in plaats van de geluiden bij een verkeerde map te zetten.

## Veiligheid, onderhoud en rollback

De extra maphiërarchie en afspeelstatistieken worden in **afzonderlijke nieuwe tabellen** in de gebruikersdatabase opgeslagen. De oorspronkelijke `geluidsgroepen`-tabel blijft exact intact. Daardoor kan de oude versie na een rollback groepen blijven aanmaken. Persoonlijke geluidsbestanden, favoriete posities, individuele volumeinstellingen en stemprofielen worden niet aangepast door de update.

De ontwikkelupdater stopt tijdelijk de microfoon, installeert alleen gewijzigde bronbestanden, test de code en herstart de juiste desktopserver. Werk daarom niet bij tijdens een gesprek.

De automatische GitHub-releaseupdater blijft zoals afgesproken uitgeschakeld. Deze patch raakt de audiomixer en de bestaande stem-DSP niet.

## Tests en aandachtspunten

- Migratie van de bestaande bibliotheek, groepskoppelingen en rollbackcompatibiliteit.
- Geneste mappen, het weigeren van mapcycli, het bewaren van submappen na verwijderen en blijven bestaan van originele media.
- Populariteit zonder dubbeltelling.
- ZIP-export en selectieve ZIP-import, inclusief onveilige paden.
- Lokale beveiligde HTTP-API voor bekijken en importeren van ZIP-bestanden.
- HTML-structuur, paginanavigatie en JavaScript-syntaxis.

De werkelijke browserbediening, slepen met de muis en de Windows-ervaring moeten nog op een echte Windows-computer worden getest.
