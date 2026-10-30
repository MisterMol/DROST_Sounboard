# DrostSoundboard

Een soundboard voor Windows, gemaakt als hobbyproject. Speel geluiden af via je headset of stuur ze samen met je microfoon naar Discord of een game.

**Versie: 6.1.0 RC4 (testversie).**

## Downloaden

**[DrostSoundboard voor Windows downloaden](https://github.com/MisterMol/DROST_Sounboard/releases)**

1. Open de nieuwste geteste release en download het bestand dat eindigt op `Setup.exe`.
2. Open de Setup en start DrostSoundboard via het Startmenu of de snelkoppeling.
3. Kies in de app je microfoon. Je kunt direct geluiden toevoegen en lokaal beluisteren.

Je hebt geen Python of Git nodig. **Staat er nog geen Setup onder Releases? Dan is er nog geen publieke download.**

### Geluiden via Discord versturen

Daarvoor moet je eenmalig **[VB-CABLE installeren via de officiële VB-Audio-site](https://vb-audio.com/Cable/)**. Pak het driverpakket uit, voer `VBCABLE_Setup_x64.exe` uit als administrator en herstart Windows. Kies daarna in Discord bij de microfoon **CABLE Output (VB-Audio Virtual Cable)**. DrostSoundboard geeft ook zelf een melding als VB-CABLE ontbreekt.

**[Korte installatiehandleiding](INSTALLEREN.md)**

## Functies

15 favorieten, zoeken en filteren op mappen, drie dashboardindelingen, eigen thema's, Preview, Uitzenden, een speler met tijdlijn en herhalen, en stemvervorming. De aparte bibliotheekpagina gebruik je om je geluiden te beheren.

## Broncode

De broncode staat hier voor wie wil meekijken of ontwikkelen:

```powershell
git clone https://github.com/MisterMol/DROST_Sounboard.git
cd DROST_Sounboard
.\Start_Na_Git_Clone.cmd
```

Een clone bevat de Bob- en Elise-stemvoorbeelden, maar **niet de volledige stemruntime en modelgewichten**. Voor normaal gebruik is de Windows Setup bedoeld.

Dit project gebruikt de [MIT-licentie](LICENSE). Externe onderdelen hebben hun eigen voorwaarden, zie [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md). De Setup is momenteel niet digitaal ondertekend en updates worden handmatig gedeeld.
