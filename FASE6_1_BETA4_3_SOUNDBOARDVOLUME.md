# DrostSoundboard 6.1.0 Beta 4.3: Soundboardvolume

## Wat is nieuw?

Onder **Instellingen > Geluid** staat nu één algemene schuif **Soundboardvolume** van 0 tot 100 procent en een knop **Reset**. De stand wordt automatisch opgeslagen zodra je de schuif loslaat. 100% is het bestaande niveau; bij 0% blijven de geluidsfragmenten stil terwijl de gewone microfoon doorgaat. Voor een eerste test bij een harde bibliotheek kun je bijvoorbeeld 70 tot 75% proberen.

De schuif verandert de individuele volumenummers en originele bestanden niet. Je hoeft je bibliotheek niet opnieuw te importeren. Soundboardvolume heeft geen invloed op de microfoon, stemvervormer of het ingestelde eigen-stem-monitorvolume.

## Technische plaats in de audioketen

1. Een bestand wordt buiten de audiocallback gedecodeerd. Fragmentvolume en eventuele normalisatie zijn op dat moment al verwerkt.
2. De audiocallback leest alleen een vaste procentwaarde uit het geheugen. Het effectfragment wordt geschaald en pas daarna aan de microfoon toegevoegd.
3. Bij het aanpassen van het volume wordt één audioblok gebruikt voor een kleine overgang. De al voorbereide samples worden **niet** overschreven.
4. De bestaande limiter en veiligheidsgrens blijven op de uiteindelijke mix werken. De koptelefoonmonitor voor geluidseffecten krijgt dezelfde nieuwe volumestand.
5. De browserpreview gebruikt dezelfde extra algemene procentfactor in zijn Web Audio GainNode. Hij blijft een lokale preview, zonder microfoonmix of limiter.

De instelling heeft een eigen SQLite-tabel `algemeen_effectvolume`, zodat een oudere versie bij een rollback geen bestaande tabel hoeft te begrijpen. De standaard is 100 als nog niets is opgeslagen. Er komen geen nieuwe Python-bibliotheken bij.

## Veiligheid en testen

- De lokale API `GET /api/instellingen/effectvolume` leest de waarde.
- De beveiligde API `POST /api/instellingen/effectvolume` accepteert alleen gehele getallen van 0 tot 100, inclusief 0.
- Waarden buiten het bereik, tekst en booleans worden geweigerd.
- De bestaande schrijftoken- en oorsprongscontrole blijven verplicht.
- De microfoon blijft actief op 0% effectvolume. Eventuele limiterreductie kan wel veranderen doordat de **mix** zachter wordt.

Een algemene vermenigvuldiger maakt alle clips zachter maar **maakt onderlinge verschillen niet automatisch gelijk**. Gebruik daarvoor normalisatie; beoordeel een bewust geboost geluidsbestand afzonderlijk als dat nog te hard klinkt.

## Handmatige acceptatietest op Windows

1. Open Instellingen > Geluid en controleer dat de nieuwe regelaar op 100% begint wanneer je hem nooit eerder hebt ingesteld.
2. Verbind de microfoon en speel een vast fragment af. Zet Soundboardvolume op 75%, 40% en 0% en laat een tweede persoon naar het ontvangen geluid luisteren.
3. Spreek op 0% in de microfoon: je stem moet gewoon doorkomen.
4. Zet het effectvolume weer op 75%, gebruik normalisatie en de limiter, en luister ook via de eigen headsetmonitor.
5. Probeer een lokale Preview op twee standen; hij moet eveneens zachter worden, zonder het bronbestand te wijzigen.
6. Sluit de app volledig af en start opnieuw. De stand moet terugkomen.
7. Klik Reset. De stand wordt 100%, zonder alle individuele soundvolumes te veranderen.

Werk niet bij tijdens een gesprek, de ontwikkelupdater onderbreekt tijdelijk de microfoon. Updater 1.2 maakt een reservekopie en voert tests uit.
