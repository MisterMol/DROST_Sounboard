"""Effectparameters voor de stemvervormer; één validatie voor web, opslag en DSP.

Alle instellingen worden per stemprofiel bewaard. Onbekende sleutels worden
geweigerd om stilzwijgende fouten bij updates te voorkomen.
"""
from __future__ import annotations

PARAMETERS = {
    'monsterkoor': {
        'diepte': (7, 0, 12, 'Diepte', 'halve tonen'),
        'dubbel_pct': (65, 0, 100, 'Dubbele stem', '%'),
    },
    'ruimtepak': {
        'metaal_pct': (45, 0, 100, 'Metalen klank', '%'),
        'helder_pct': (40, 0, 100, 'Helderheid', '%'),
    },
    'spook': {
        'zweving_pct': (65, 0, 100, 'Zweving', '%'),
        'echo_pct': (35, 0, 100, 'Echo', '%'),
    },
    'retrocomputer': {
        'korrel_pct': (65, 0, 100, 'Digitale korrel', '%'),
        'robot_pct': (60, 0, 100, 'Robotklank', '%'),
    },
    'echo': {
        'vertraging_ms': (190, 100, 1800, 'Echovertraging', 'ms'),
        'feedback_pct': (28, 0, 75, 'Herhalingen', '%'),
        'mix_pct': (50, 0, 100, 'Echo in de mix', '%'),
    },
    'autotune': {  # Legacy-ID blijft bestaan; zichtbaar heet dit profiel Stoorzender.
        'ruis_pct': (60, 0, 100, 'Digitale ruis', '%'),
        'haperingen_pct': (50, 0, 100, 'Signaalhaperingen', '%'),
        'korrel_pct': (70, 0, 100, 'Digitale vervorming', '%'),
    },
}

def standaard_parameters() -> dict[str,dict[str,object]]:
    return {profiel: {sleutel: beschrijving[0] for sleutel,beschrijving in velden.items()}
            for profiel, velden in PARAMETERS.items()}

def controleer_parameters(profiel: str, waarden: dict) -> dict:
    if profiel not in PARAMETERS or type(waarden) is not dict or set(waarden) != set(PARAMETERS[profiel]):
        raise ValueError('STEM-050: ongeldige effectparameters.')
    gecontroleerd = {}
    for sleutel, waarde in waarden.items():
        veld = PARAMETERS[profiel][sleutel]
        if len(veld) == 5:
            if type(waarde) is not int or not veld[1] <= waarde <= veld[2]:
                raise ValueError('STEM-051: effectinstelling buiten toegestaan bereik.')
        else:
            if type(waarde) is not str or waarde not in veld[1]:
                raise ValueError('STEM-052: ongeldige keuze voor deze effectinstelling.')
        gecontroleerd[sleutel] = waarde
    return gecontroleerd

def parameters_voor_api() -> dict:
    resultaat = {}
    for profiel, velden in PARAMETERS.items():
        resultaat[profiel] = []
        for sleutel, gegevens in velden.items():
            if len(gegevens)==5:
                resultaat[profiel].append(dict(id=sleutel, standaard=gegevens[0], min=gegevens[1],
                                              max=gegevens[2], label=gegevens[3], eenheid=gegevens[4], type='range'))
            else:
                resultaat[profiel].append(dict(id=sleutel, standaard=gegevens[0], keuzes=list(gegevens[1]),
                                              label=gegevens[2], type='select'))
    return resultaat
