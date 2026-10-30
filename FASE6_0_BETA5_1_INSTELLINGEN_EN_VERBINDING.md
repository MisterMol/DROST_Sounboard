# DrostSoundboard 6.0.0 Beta 5.1: instellingen en verbindingsbediening

Deze kleine onderhoudsrelease verplaatst geavanceerde audioregelingen naar een aparte pagina. De audiomixer en opgeslagen geluidsvoorkeuren veranderen niet.

## Werking

Het dashboard toont nog steeds de actieve audiometers, microfoonkeuze, geluidseffecten, meeluisteren en de speler. Via **Instellingen** rechtsboven open je een aparte pagina met de sectie **Geluid**. Hier staan nu **Geluidsnormalisatie** en **Piekbeveiliging**, inclusief de gemeten correctie in dB. De knop rechtsboven heet op die pagina **Dashboard**, waarmee je teruggaat. Ook de Terug- en Vooruit-knoppen van de browser werken dankzij de hash-navigatie.

De microfoon heeft één bedieningsknop. Deze heet **Verbinden** als er geen audiostream is en **Verbreken** als de stream actief is. Tijdens een verbindingswisseling is de knop tijdelijk uitgeschakeld. Bij een klik wordt eerst opnieuw de status van de Python-server opgehaald. Gelijktijdige klikken sturen geen dubbele aanvragen. Alle bestaande VB-CABLE-controles blijven van kracht.

De preview kan tijdens het spelen blijven lopen wanneer je naar Instellingen gaat. Als je daar de normalisatie wijzigt, wordt die rechtstreeks op de preview toegepast, zoals in Beta 4.1. De limiter blijft een instelling voor de gecombineerde uitvoermix en is niet van toepassing op alleen browserpreview.

## Geen wijzigingen aan de audiotechniek

- Het Python-algoritme voor normalisatie en de pieklimiter blijft ongewijzigd.
- SQL-opslag en API-endpoints blijven ongewijzigd.
- Er worden geen nieuwe afhankelijkheden geïnstalleerd.
- De Windows-installer, de releaseworkflow en de ontwikkelupdater blijven ongewijzigd.

## Acceptatie op Windows

1. Installeer de patch alleen over de exacte bronbestanden van Beta 5.
2. Open het dashboard opnieuw met Ctrl+F5. Controleer dat de twee geavanceerde audioregelingen verdwenen zijn.
3. Open Instellingen en controleer de sectie Geluid. Alle instellingen en de dB-metingen moeten daar staan en bedienbaar zijn.
4. Verbind de microfoon met de knop Verbinden. De knop moet daarna Verbreken tonen.
5. Druk opnieuw op dezelfde knop. Het geluid wordt losgekoppeld, zonder een tweede knop.
6. Controleer dat het stoppen van een fragment de microfoonverbinding niet verbreekt.
7. Laat Preview lopen en wijzig normalisatie onder Instellingen. Het verschil is direct hoorbaar wanneer er normalisatie wordt toegepast.
8. Herlaad het scherm en gebruik browser Terug/Vooruit. De gekozen instellingen blijven behouden.
9. Controleer dat de VB-CABLE-waarschuwing en de sneltoetsen nog werken.

De automatische ontwikkeltests testen de DOM-indeling, daadwerkelijke JavaScript-logica met nagebootste serverstatus en het oude audiogedrag. Een echte Windows-luistertest blijft nodig.
