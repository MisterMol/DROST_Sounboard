"""Sluit eigen apponderdelen af zonder volgende stappen bij een fout over te slaan."""
from __future__ import annotations

from collections.abc import Callable, Iterable
import logging


def sluit_onderdelen_af(softwarelogboek: logging.Logger | None,
                       stappen: Iterable[tuple[str, Callable[[], object]]]) -> bool:
    """Voer alle opruimstappen uit. False is een mislukte afsluiting, None is akkoord.

    De aanroeper bepaalt de volgorde. Technische details gaan naar het logboek.
    Deze helper start geen processen, stuurt geen audio en forceert geen stop.
    """
    geslaagd = True
    for naam, handeling in stappen:
        try:
            if handeling() is False:
                raise RuntimeError(f'{naam} meldde dat afsluiten niet is gelukt.')
        except Exception:
            geslaagd = False
            if softwarelogboek is not None:
                try:
                    softwarelogboek.exception('Apponderdeel kon niet volledig afsluiten', extra={
                        'gebeurtenis': 'apponderdeel_afsluiten_mislukt',
                        'gegevens': {'onderdeel': naam, 'foutcode': 'DESKTOP-998'},
                    })
                except Exception:
                    # Ook een defecte loghandler mag de audioafsluiting niet blokkeren.
                    pass
    return geslaagd


def sluit_webserver_af(server, serverdraad, gestart: bool) -> bool:
    """Roep dit buiten de serve_forever-draad aan, ook bij een mislukte appstart."""
    if server is None:
        return True
    try:
        if gestart:
            server.shutdown()
            if serverdraad is not None:
                serverdraad.join(timeout=6)
                return not serverdraad.is_alive()
        return True
    finally:
        server.server_close()
