# DrostSoundboard 5.2: correcte geluidsmeters

Deze kleine update corrigeert **alleen de weergave van de twee audiometers**. De audiomixer, microfoon, virtuele kabel, bibliotheek en bestandsformaten veranderen niet.

## Wat klopte er niet?

De getallen boven de meters gaven **RMS** (gemiddelde signaalsterkte) weer. De witte lijn toonde een **samplepiek** (de grootste recente samplewaarde). Die kunnen met spraak gemakkelijk 10 tot 15 dB uiteenlopen. Omdat de witte lijn niet als piek was benoemd, leek hij op de verkeerde plaats te staan.

Daarnaast stonden de labels min 60, min 30, min 12 en 0 dBFS op vier gelijkmatig verdeelde plekken. Bij een lineaire schaal van min 60 tot 0 moet min 30 echter precies in het midden staan en min 12 op 80 procent van de breedte. Ook werd het volledige kleurverloop samengedrukt als de RMS-balk korter werd. Daardoor verschenen waarschuwingskleuren op te lage niveaus.

## Nieuwe werking

- De gekleurde balk en de dunne witte markering staan **op dezelfde, uit RMS berekende plaats**.
- De echte hoogste samplepiek verschijnt apart als `Piek: -17.0 dBFS`, met zijn eigen naam. Dit is een echte meting uit de Python-audiomotor en geen geschatte waarde.
- De markeringen min 60, min 30, min 12 en 0 liggen op 0, 50, 80 en 100 procent van de schaal.
- De kleuren blijven op hun vaste dBFS-plaats, ook wanneer het geluidsniveau daalt.
- Geluiden onder de ondergrens van de schaal houden de meter stil. De numerieke RMS-waarde wordt nog steeds getoond, ook als die lager is dan min 60 dBFS.
- De browser gebruikt een korte vertraging voor de visuele beweging. De Python-metingen en de daadwerkelijke audio zijn niet aangepast.

## Bijwerken vanuit Windows PowerShell

1. Sluit de webserver en de browserpagina van DrostSoundboard volledig.
2. Download `DrostSoundboard_Fase5_2_Meters_Correctie.zip` naar `Downloads`.
3. Voer uit:

```powershell
cd "$env:USERPROFILE\Desktop\pythonProjects"

Compress-Archive -Path .\DrostSoundboard\app\webinterface\statisch, .\DrostSoundboard\tests -DestinationPath .\DrostSoundboard_backup_voor_meters52.zip -Force

Expand-Archive -LiteralPath "$env:USERPROFILE\Downloads\DrostSoundboard_Fase5_2_Meters_Correctie.zip" -DestinationPath . -Force

cd .\DrostSoundboard

.\.venv\Scripts\python.exe -m unittest discover -s tests -q
```

Verwachte uitslag bij de bestaande versie 5.1 plus deze update: `Ran 191 tests`, gevolgd door `OK`.

4. Start de applicatie met `Start_DrostSoundboard.bat`.
5. Druk in de browser op `Ctrl + Shift + R`, zodat je geen oude JavaScript of CSS uit de browsercache ziet.

## Wat moet je testen?

Praat op normaal volume. Als RMS rond min 30 dBFS zit, moet de witte markering ongeveer in het midden van de meter staan. De piekwaarde daarnaast kan hoger zijn: dat is normaal en wordt nu expliciet benoemd. Als je stil bent en de microfoon alleen achtergrondruis van ongeveer min 74 dBFS ontvangt, moet de balk leeg zijn, zonder zwervend wit streepje.

Als Defender een detectie meldt, schakel de beveiliging niet uit. Controleer de bedreigingsnaam voordat je opnieuw probeert uit te pakken.
