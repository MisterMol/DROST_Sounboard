# DrostSoundboard 6.0.0 Beta 5: pieklimiter

## Waarom?

De bestaande `np.clip` hield de eindmix wel onder de digitale grens, maar vlakte pieken hard af. Dat kan hoorbare vervorming geven als microfoonspraak en een geluidseffect tegelijk hard zijn.

## Wat is veranderd?

- De nieuwe `app/audio/pieklimiter.py` verwerkt de **uiteindelijke stereomix** in de PortAudio-callback, dus *na* de individuele geluidsvolumes en normalisatie.
- De limiter berekent één gezamenlijke gain voor links en rechts. Hierdoor verschuift het stereobeeld niet.
- Bij een naderende piek binnen het beschikbare audioblok wordt de gain geleidelijk teruggebracht. De gain herstelt daarna geleidelijk gedurende ongeveer 120 ms.
- Er wordt geen extra audio vastgehouden. De berekening veroorzaakt **geen extra bufferlatentie** en gebruikt alleen NumPy. Er loopt geen Python-loop over de afzonderlijke audioframes.
- Het samplepiekplafond is 0,95. De bestaande `np.clip` blijft als laatste veiligheidsnet, ook als de gebruiker de limiter uitschakelt.
- Onder **Audioverbinding** staat nu een schakelaar *Piekbeveiliging*, standaard aan. Hij werkt direct en wordt opgeslagen in de bestaande SQLite-bibliotheek.
- De browser toont de daadwerkelijk gemeten piekreductie in decibel. Bij een lichte mix staat deze op 0,0 dB. Alleen meetwaarden verlaten de callback, geen opnames.
- Bij een onverwachte limiterfout blijft de bestaande veiligheidsbegrenzing actief. De microfoonstream wordt dan **niet vanwege de limiter** onderbroken. De volledige traceback wordt buiten de realtime callback gelogd.

## Wat is het niet?

Deze limiter is een lichte **sample-pieklimiter**, geen true-peak limiter met oversampling. Hij kan ook geen al vervormd bronbestand herstellen. Binnen een realtime callback is alleen de huidige audiobuffer bekend. De vooruitblik beperkt zich daarom tot dit buffer en kan niet voorspellen wat in het volgende buffer zit. Er is geen garantie op onhoorbare vervorming bij elk denkbaar geluid.

De browserpreview speelt alleen het geselecteerde fragment af, zonder microfoonmix. Daarom verwerkt de *eindmixlimiter* alleen het signaal naar de virtuele uitvoer. De bestaande previewnormalisatie van Beta 4.1 werkt wel gewoon.

## Technische opbouw

- `PiekLimiter`: houdt de actuele gain bij; `verwerk_in_place()` stuurt één stereobuffer bij en geeft de reductie in dB terug.
- `LiveAudiomixer`: roept de limiter aan na de effectenmix, vóór de RMS- en piekmetingen. Een fout geeft een veilige terugval.
- `VasteFavorietenEnInstellingen`: voegt de tabel `pieklimiter_instellingen` toe met standaardstand aan. De bestaande bibliotheek en mediabestanden blijven intact.
- Lokale API: `GET/POST /api/instellingen/pieklimiter` met dezelfde CSRF-controles als bestaande instellingen; `/api/status` en `/api/niveaus/live` leveren reductiemetingen.
- Dashboard: aan/uit-schakelaar en rustige reductiemeter onder de normalisatie-instelling.

## Bepalen of de patch geslaagd is

1. Zet een duidelijk hard fragment klaar. Zet eerst de normalisatie zoals gewenst.
2. Maak een verbinding met de virtuele microfoon en schakel geluidseffecten in.
3. Speel het harde fragment af. De meter **Piekreductie** hoort tijdens harde pieken meer dan 0,0 dB te tonen.
4. Schakel Piekbeveiliging uit en in. Vergelijk via de **echte uitvoermix** met een opname of luistertest, niet alleen de preview.
5. Stop het geluidseffect en blijf in de microfoon praten. De microfoon moet aangesloten en hoorbaar blijven.
6. Sluit DrostSoundboard af, start opnieuw en controleer dat de gekozen limiterstand behouden bleef.
7. Verifieer op echte Windows-hardware het ontbreken van hoorbaar pompen, gekraak of onaanvaardbare CPU-belasting.

## Afbakening

Deze patch wijzigt geen VB-CABLE-driver, microfoonselectie, sneltoetsen, hotkeys, bibliotheekbestanden, installatieprocedure of online updatebeleid.
