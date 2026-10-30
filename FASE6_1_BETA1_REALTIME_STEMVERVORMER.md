# DrostSoundboard 6.1.0-beta.1: realtime stemvervormer

## Wat is toegevoegd?

Een lichte, direct schakelbare bewerking van **uitsluitend de microfoon** in de bestaande live audiomixer. Geluidseffecten, clips, browserpreviews en de VB-CABLE-koppeling blijven onafhankelijk.

### Profielen

| Profiel | Wat het doet |
| --- | --- |
| Normaal | Exact hetzelfde microfoonsignaal als voorheen, zonder extra DSP |
| Radio | Hoog- en laagafsnijding, lichte verzadiging voor radioklank |
| Robot | Ringmodulatie met 48 Hz voor een elektronisch timbre |
| Diepe stem (bèta) | Overlappende korte vertragingen; verlaagt de toonhoogte circa vier halve tonen; circa 19–54 ms extra stemvertraging |

Onder **Instellingen > Geluid** staat de profielkeuze en de knop **Mijn stem beluisteren**. Wisselen tijdens een lopende preview of actieve live verbinding werkt zonder opnieuw verbinding te maken.

## Privacy en veilig vooraf beluisteren

- De preview wordt door dezelfde Python-`Stemvervormer` gemaakt als de live uitzending. Er wordt geen browsermicrofoon of externe website gebruikt.
- Voor preview moet de liveverbinding eerst zijn verbroken. Er worden nooit twee microfoonstreams geopend en preview wordt niet naar de virtuele microfoon gestuurd.
- De preview opent de geselecteerde fysieke microfoon en het geselecteerde fysieke luisterapparaat, of de Windows-standaarduitvoer. Een virtuele kabel wordt geweigerd.
- Preview stopt bij handmatig stoppen, het teruggaan naar het dashboard of bij sluiten van de pagina. Een eigen limiet van maximaal 90 seconden voorkomt eindeloos doorlopend luisteren als de browser onverwacht sluit.
- Gebruik een koptelefoon. Luidsprekers kunnen een feedbacklus veroorzaken. De preview begrenst het audioniveau conservatief.
- Er worden nooit spraakopnamen, samples of een previewbestand opgeslagen.

## Technische indeling

- `app/audio/stemvervorming.py`: zuivere DSP; status tussen blokken; validatie.
- `app/audio/stemvoorbeeld.py`: lokale WASAPI-preview op fysieke input/output, één stream per previewsessie.
- `app/audio/live_audiomixer.py`: verwerkt de stem vóór het mengen; bij DSP-fout gaat de originele microfoon door; de fout wordt buiten callback gelogd.
- `app/webinterface/favorieten_en_instellingen.py`: SQLite-profielstand, default `normaal`.
- `app/webinterface/bediening_van_de_audiomotor.py`: uitsluitend gecontroleerde apparaatkeuze, start/stop preview en instellingen.
- `app/webinterface/lokale_webserver.py`: lokale beveiligde HTTP-acties.
- `app/webinterface/statisch/`: instellingenscherm, profielen en previewbediening.

Er zijn **geen nieuwe pakketafhankelijkheden**. De profiler gebruikt NumPy en de reeds aanwezige audioapparatenbibliotheek. De diepe stem is een eenvoudige bèta-pitchshifter, geen professionele formantbewarende studiovervorming. Het kan artificiële artefacten geven bij muziek, zachte klanken of erg complexe stemmen. De normale en radio/robot-profielen hebben geen extra DSP-lookahead-buffer.

## Nieuwe routes

- `GET /api/instellingen/stemprofiel`
- `POST /api/instellingen/stemprofiel` met `{ "profiel": "robot" }`
- `POST /api/stemvoorbeeld/start` met `{ "microfoonnummer": 2, "uitvoernummer": null }`
- `POST /api/stemvoorbeeld/stop` met `{}`

Alle muterende routes vereisen de bestaande per-start CSRF-token. Het dashboard is uitsluitend beschikbaar op de lokale loopback-interface. Er worden geen ruwe microfoonsamples via HTTP verstuurd.

## Acceptatietests op Windows

1. Verbreek de microfoonverbinding, ga naar Instellingen, kies Robot en klik op Mijn stem beluisteren. Luister via een fysieke headset. Het geluid mag niet als virtuele microfoon uitgezonden worden.
2. Wissel tijdens de preview tussen Normaal, Radio, Robot en Diepe stem; het effect moet meteen veranderen. De diepe stem kan hoorbaar vertraagd en minder natuurlijk zijn.
3. Stop de preview. Controleer dat je headset daarna geen vertraagde stem meer ontvangt. Start daarna de gewone VB-CABLE-verbinding.
4. Wissel tijdens die liveverbinding van profiel. Geluidseffecten mogen daardoor niet veranderen en de microfoon mag niet verbreken.
5. Stop een geluidseffect en controleer of je stem blijft doorgaan.
6. Sluit de applicatie af en herstart haar. De profielinstelling moet behouden blijven.
7. Probeer de preview te starten terwijl de liveverbinding actief is. De app moet een duidelijke foutmelding tonen en geen extra stream starten.
8. Test verschillende fysieke Windows-microfoons en headsets. Er staat nergens een fabrikant ingebouwd.

## Verspreiding

Deze patch is voor **ontwikkelupdater 1.2** op de originele broncodeversie `6.0.0-beta.5.1`. De publieke Windows-installer is nog niet automatisch gebouwd of hardware-getest. De GitHub auto-updateproef blijft uitgesteld; deel voorlopig alleen na lokale installatieproeven een nieuwe Setup.exe.
