"""Lees bij het openen van het dashboard of de gewone VB-CABLE bruikbaar is.

Alleen apparaatnamen, WASAPI en kanaalaantallen worden gelezen. We starten
geen audiostream, wijzigen geen Windows-instellingen en downloaden geen driver.
De audiomixer en deze controle delen exact dezelfde herkenningsregels.
"""
from __future__ import annotations

from app.audio.apparatenbeheer import GevondenAudioapparaat
from app.audio.kabelcontrole import vind_vb_cable_uiteinden

# Alleen de officiële website. Geen ingebouwde driver-EXE of stille UAC-prompt.
OFFICIELE_VB_CABLE_SITE = 'https://vb-audio.com/Cable/'


def beoordeel_vb_cable(
    apparaten: list[GevondenAudioapparaat],
) -> dict[str, object]:
    """Vertaal de beschikbare Windows-audioapparaten naar een leesbare status.

    'ontbreekt' betekent niet bewezen dat de driver nooit is geïnstalleerd:
    een uitgeschakelde driver kan evenmin in WASAPI worden aangeboden.
    """
    afspeel, opname = vind_vb_cable_uiteinden(apparaten)
    aantal_afspeel, aantal_opname = len(afspeel), len(opname)

    if aantal_afspeel == 1 and aantal_opname == 1:
        status = 'gereed'
        melding = 'VB-CABLE is beschikbaar. De virtuele microfoon kan worden ingesteld.'
    elif aantal_afspeel == 0 and aantal_opname == 0:
        status = 'ontbreekt'
        melding = ('VB-CABLE is niet gevonden bij de beschikbare Windows-audioapparaten. '
                   'Installeer de driver of schakel de apparaten in via Windows.')
    elif aantal_afspeel > 1 or aantal_opname > 1:
        status = 'meerdere'
        melding = ('Er zijn meerdere bijpassende VB-CABLE-apparaten gevonden. '
                   'Controleer welke virtuele kabels in Windows actief zijn.')
    else:
        status = 'onvolledig'
        melding = ('VB-CABLE is niet volledig beschikbaar. De invoer- en opnamekant '
                   'moeten allebei ingeschakeld zijn in Windows.')

    return {
        'status': status,
        'bruikbaar': status == 'gereed',
        'melding': melding,
        'aantal_afspeelpunten': aantal_afspeel,
        'aantal_opnamepunten': aantal_opname,
        'officiele_website': OFFICIELE_VB_CABLE_SITE,
    }


def resultaat_voor_mislukte_controle() -> dict[str, object]:
    """Claim nooit 'niet geïnstalleerd' als uitlezen zelf is mislukt."""
    return {
        'status': 'controle_mislukt',
        'bruikbaar': False,
        'melding': ('De audioapparaten konden niet gecontroleerd worden. '
                   'Probeer opnieuw of bekijk de logboeken.'),
        'aantal_afspeelpunten': 0,
        'aantal_opnamepunten': 0,
        'officiele_website': OFFICIELE_VB_CABLE_SITE,
    }
