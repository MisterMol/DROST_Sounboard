# Bijdragen aan DrostSoundboard

DrostSoundboard is een open-source Python-app met een lokale HTML-, CSS- en JavaScript-interface. Lees eerst [`ARCHITECTUUR.md`](ARCHITECTUUR.md); je hoeft de hele audiomixer niet te kennen om één scherm te verbeteren.

## Code die je na vijf jaar nog begrijpt

- Gebruik **beschrijvende Nederlandstalige** namen: `geef_huidige_webstatus()` is duidelijker dan `get()`.
- Houd één verantwoordelijkheid per module. De browser bedient; de webserver valideert; de audiomixer verwerkt samples.
- Schrijf een commentaar bij belangrijke keuzes dat uitlegt **waarom**, niet alleen wat de code letterlijk doet.
- Gebruik `None`, ontbrekende sleutels en verkeerde types als aparte, herkenbare foutgevallen.
- Voeg geen extra audiostream toe voor een interfacefunctie.

Voorbeeld:

```python
# De browser mag niet zelf de fysieke microfoon opnemen. Daarom geven we
# alleen een startopdracht aan de audiomixer, die al met VB-CABLE verbonden is.
def start_een_geluid_vanuit_het_dashboard(geluid_id: str) -> None:
    ...
```

## Fouten en audit

Maak API-antwoorden via `app/webinterface/api_foutantwoorden.py`. De gebruiker ziet een korte melding met een logreferentie. Bewaar de echte fout en originele Python-traceback in `software.jsonl`; audit hoort in `audit.jsonl`. Registreer geen gesprekken, tokens of ruwe microfoondata. Vermijd `except: pass` op plekken waar een fout verloren gaat.

## Realtime audio

Houd audiocallbacks zo kort mogelijk. Geen disk-I/O, netwerk, GIF/MP4-decodering of uitgebreide logging binnen een callback. Bij video volgt de browser de Python-audioklok, maar mag niet bij iedere poll opnieuw zoeken. Verander deze afspraken alleen met meetbare tests.

## Tests en pull requests

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -q
```

- Voeg voor ieder nieuw gedrag een succes- en fouttest toe.
- Probeer ontbrekende bestanden, ongeldige parameters en snel klikken.
- Controleer behoud van SQLite-bibliotheek, favorieten, groepindeling en geluidskwaliteit.
- Meld welke tests je hebt uitgevoerd en welke **niet** op echte Windows-hardware zijn gecontroleerd.
- Houd wijzigingen klein, zodat iemand ze kan reviewen en eventueel terugdraaien.

## Veilig publiceren

Commit geen `.venv`, audiobestanden van gebruikers, database, privélogs of credentials. Check `git diff --cached --stat` en `git diff --cached --check` vóór iedere push. Bundel VB-CABLE niet; verwijs naar de maker. Controleer de licenties van FFmpeg en andere binaries vóór een publieke installer.

Bij een beveiligingsprobleem gebruik je bij voorkeur een private GitHub Security Advisory, zoals beschreven in [`SECURITY.md`](SECURITY.md).
