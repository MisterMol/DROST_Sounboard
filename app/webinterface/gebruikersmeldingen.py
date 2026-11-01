"""Zakelijke Nederlandse meldingen, los van de technische diagnose.

De router logt de oorspronkelijke uitzondering en behoudt codes en referenties.
Deze module verandert geen HTTP-status, toestemming of afspeelopdracht.
"""
from __future__ import annotations
import re

MELDINGEN = {
    'WEB-001': 'Kies een microfoon uit de lijst.',
    'WEB-002': 'De gekozen microfoon is niet meer beschikbaar. Vernieuw de apparatenlijst.',
    'WEB-004': 'Kies eerst een geluid.',
    'WEB-005': 'Dit geluid staat niet meer in de bibliotheek. Vernieuw de lijst.',
    'WEB-006': 'Klik eerst op Verbinden en zet Soundboard aan.',
    'WEB-007': 'Dit geluid kan niet worden afgespeeld. Controleer het bestand of importeer het opnieuw.',
    'WEB-020': 'Dit bestand is geen geldige afbeelding. Kies een PNG, JPG, WEBP of GIF.',
    'WEB-021': 'Open het dashboard op de computer waarop DrostSoundboard draait.',
    'WEB-022': 'Deze pagina hoort bij een eerdere sessie. Vernieuw de pagina en probeer het opnieuw.',
    'WEB-023': 'Deze actie is alleen toegestaan vanuit het lokale dashboard.',
    'WEB-024': 'Deze aanvraag kon niet worden verwerkt. Vernieuw de pagina en probeer het opnieuw.',
    'WEB-025': 'Deze aanvraag kon niet worden verwerkt. Vernieuw de pagina en probeer het opnieuw.',
    'WEB-026': 'Deze aanvraag kon niet worden verwerkt. Vernieuw de pagina en probeer het opnieuw.',
    'WEB-028': 'De aanvraag is leeg of te groot. Controleer het bestand of de invoer.',
    'WEB-031': 'Deze afbeelding is niet meer beschikbaar. Voeg de afbeelding opnieuw toe.',
    'WEB-033': 'Geef een naam van 1 tot 100 tekens op.',
    'WEB-036': 'Kies een MP3, WAV of MP4.',
    'WEB-037': 'Kies een PNG, JPG, WEBP of GIF.',
    'WEB-041': 'Kies een headset of luidspreker uit de lijst.',
    'WEB-053': 'Het bronbestand is tijdens het afspelen gewijzigd. Start het geluid opnieuw.',
    'WEB-054': 'Deze GIF kan niet worden geopend. Kies een ander bestand.',
    'WEB-060': 'Dit fragment kan niet worden gelezen. Controleer het beginpunt en het bestand.',
    'WEB-061': 'De golfvorm kan niet worden geladen. Controleer de fragmentselectie.',
    'WEB-062': 'Kies een fragment van maximaal twee minuten.',
    'WEB-065': 'Bevestig eerst dat je dit geluid wilt verwijderen.',
    'WEB-080': 'De vorige verbinding wordt nog afgesloten. Probeer het zo opnieuw.',
    'WEB-081': 'DrostSoundboard wordt afgesloten. Start de app opnieuw om verder te gaan.',
    'SPELER-001': 'Dit fragment speelt niet meer. Start het geluid opnieuw.',
    'SPELER-003': 'Kies een positie binnen het fragment.',
    'VOLUME-001': 'Kies een totaalvolume van 0 tot 200%.',
    'VOLUME-002': 'Kies een totaalvolume van 0 tot 200%.',
    'VOLUME-003': 'Het volume kon niet worden aangepast. Vernieuw de pagina en probeer het opnieuw.',
    'VOLUME-005': 'Kies een basisvolume van 0 tot 200%.',
    'VOLUME-006': 'Start dit fragment opnieuw om het basisvolume aan te passen.',
    'EDITOR-021': 'Controleer het beginpunt, de duur en het volume van het fragment.',
    'FAV-001': 'Kies een favorietenplek van 1 tot 15.',
    'FAV-003': 'Het beginpunt ligt buiten het toegestane bereik.',
    'FAV-004': 'Kies een basisvolume van 0 tot 200%.',
    'FAV-005': 'Kies een fragment van maximaal twee minuten.',
    'NORM-004': 'Het bronbestand ontbreekt. Importeer het geluid opnieuw.',
    'NORM-005': 'Een andere preview wordt nog voorbereid. Probeer het zo opnieuw.',
    'LIVE-001': 'Kies een microfoon uit de lijst.',
    'LIVE-002': 'Kies je echte microfoon, niet CABLE Output.',
    'LIVE-003': 'De microfoon accepteert de geteste audioformaten niet. Controleer het opnameformaat in Windows of kies een andere microfoon.',
    'LIVE-015': 'De microfoonverbinding is onverwacht gestopt. Controleer de USB- of headsetverbinding en probeer opnieuw.',
    'LIVE-018': 'De microfoonverbinding start, maar Windows levert geen audio aan DrostSoundboard. Controleer microfoonrechten en de gekozen ingang.',
    'LIVE-024': 'Windows kan de microfoon en VB-CABLE niet openen. Sluit andere audioprogramma’s en controleer de Windows-geluidsinstellingen.',
    'LIVE-025': 'De Windows-audioverbinding kon niet worden geopend. Dit kan ook door een ongeschikt opnameformaat komen. Controleer de audioapparaten en hun standaardformaten.',
    'LIVE-026': 'Windows kan de fysieke microfoon niet openen. Controleer de opname-ingang, microfoonrechten en of een ander programma de microfoon bezet houdt.',
    'LIVE-027': 'Windows kan CABLE Input (VB-CABLE) niet openen. Controleer bij Afspelen of CABLE Input ingeschakeld is en op stereo 48 kHz staat.',
    'KABEL-002': 'VB-CABLE is niet correct gevonden. Installeer de gewone VB-CABLE-driver en herstart Windows. Controleer daarna de audioapparaten.',
    'LIVE-010': 'Klik eerst op Verbinden.',
    'LIVE-012': 'Klik eerst op Verbinden.',
    'LIVE-013': 'Zet Soundboard aan om een geluid uit te zenden.',
    'LIVE-014': 'Dit geluid kan niet worden afgespeeld. Controleer het bestand of importeer het opnieuw.',
    'MON-011': 'Meeluisteren kan niet starten. Controleer je headset en de gekozen uitvoer.',
    'STEM-021': 'DrostSoundboard wordt afgesloten. Start de app opnieuw om verder te gaan.',
    'STEM-022': 'Verbreek eerst de microfoonverbinding om lokaal je stem te testen.',
    'STEM-023': 'Er speelt al een stemvoorbeeld. Stop dat voorbeeld eerst.',
    'STEM-024': 'De microfoon is niet gevonden. Vernieuw de apparatenlijst.',
    'STEM-025': 'Kies een headset of luidspreker om je stem te beluisteren.',
    'STEM-026': 'Stop eerst het lokale stemvoorbeeld.',
    'STEM-058': 'Het stemvoorbeeld wordt al voorbereid. Probeer het zo opnieuw.',
    'EXP-015': 'Er wordt al een bestand klaargemaakt. Probeer het opnieuw zodra dat klaar is.',
    'ARCH-023': 'Selecteer de geluiden die je wilt importeren.',
    'BIB-080': 'Typ BEVESTIG om de bibliotheek leeg te maken.',
    'BIB-084': 'Er wordt nog een geluid voorbereid. Probeer het zo opnieuw.',
    'HOTKEY-030': 'Start de desktopapp om sneltoetsen buiten de browser te gebruiken.',
    'GELUID-004': 'Het bronbestand ontbreekt. Importeer het geluid opnieuw.',
    'GELUID-005': 'Dit geluidsbestand is leeg. Kies een ander bestand.',
    'GELUID-021': 'Kies eerst een bestand.',
    'GELUID-022': 'Kies een MP3, WAV of MP4.',
    'GELUID-023': 'Het bronbestand ontbreekt. Importeer het geluid opnieuw.',
    'GELUID-024': 'Dit geluidsbestand is leeg. Kies een ander bestand.',
    'GELUID-025': 'Dit bestand is groter dan 250 MiB. Kies een kleiner bestand.',
    'GELUID-029': 'Kies een basisvolume van 0 tot 200%.',
    'GELUID-037': 'Kies een fragment van maximaal twee minuten.',
}

_CODE = re.compile(r'^([A-Z][A-Z0-9_-]*-\d{3}):\s*')
_TECHNISCH = re.compile(
    r'Traceback|invalid literal|could not convert|Expecting value|is not defined|\b(?:JSON|HTTP|None|True|False|true|false|NaN|float32|callback|PortAudio|WASAPI)\b'
    r'|[A-Za-z]:[\\/]|/(?:home|tmp|Users|mnt)/|\b\w+(?:Error|Exception)\b', re.I)


def gebruikersmelding(fout: Exception | str | None, *, code: str | None = None,
                       http_status: int = 400, standaard: str | None = None) -> str:
    """Houd bruikbare Nederlandse invoerfeedback; stuur geen interne details terug."""
    tekst = str(fout or '').strip()
    match = _CODE.match(tekst)
    code = code or (match.group(1) if match else None)
    if code in MELDINGEN:
        return MELDINGEN[code]
    if http_status >= 500:
        return standaard or 'Deze actie is niet gelukt. Probeer het opnieuw. Blijft dit gebeuren, bekijk dan het logboek.'
    if isinstance(fout, FileNotFoundError):
        return 'Het bestand is niet meer beschikbaar. Controleer het bestand of voeg het opnieuw toe.'
    if isinstance(fout, PermissionError):
        return 'DrostSoundboard heeft geen toegang tot dit bestand. Controleer de bestandsrechten.'
    inhoud = _CODE.sub('', tekst)
    # Alleen voorzienbare invoerfouten mogen eigen tekst behouden. Onbekende
    # driver- en Pythonfouten krijgen een korte melding; logs houden de details.
    veilig = isinstance(fout, ValueError) and not _TECHNISCH.search(inhoud)
    if veilig and inhoud and len(inhoud) <= 240:
        return inhoud[0].upper() + inhoud[1:]
    return standaard or 'Deze actie is niet gelukt. Controleer je invoer en probeer het opnieuw.'
