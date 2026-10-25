"""Controleer de Windows-standaardmicrofoon los van de virtuele kabel.

Deze test is bewust een apart programma. Daardoor weten we bij stilte in de
live mixer of het probleem al bij de fysieke opnamebron ontstaat. Geen
spraakopname wordt op schijf gezet, alleen de gemeten signaalsterkte.
"""

from __future__ import annotations

import time

from app.diagnostiek.logboek import (
    maak_logboeken_klaar, schrijf_auditgebeurtenis,
    sluit_logboeken_netjes_af, zet_uitgebreide_foutafhandeling_aan,
)


def vind_de_microfoon_voor_een_rechtstreekse_test(apparaten, standaardnummer=None):
    """Gebruik de Windows-standaardmicrofoon, of één ondubbelzinnige fysieke microfoon."""
    kandidaten = [
        apparaat for apparaat in apparaten
        if apparaat.api_naam.casefold() == "windows wasapi"
        and apparaat.aantal_invoerkanalen > 0
        and "cable" not in apparaat.naam.casefold()
        and "vb-audio" not in apparaat.naam.casefold()
    ]
    if not kandidaten:
        raise RuntimeError(
            "MIC-001: geen fysieke microfoon gevonden via Windows WASAPI. "
            "Controleer je audioapparaten en microfoonrechten."
        )
    if standaardnummer is not None:
        standaard = next((a for a in kandidaten if a.huidig_apparaatnummer == standaardnummer), None)
        if standaard is not None:
            return standaard
        raise RuntimeError('MIC-004: de Windows-standaardmicrofoon is niet bruikbaar voor deze test.')
    if len(kandidaten) == 1:
        return kandidaten[0]
    raise RuntimeError(
        'MIC-005: meerdere microfoons gevonden, maar geen bruikbare Windows-standaardmicrofoon. '
        'Stel een standaardmicrofoon in via Windows.'
    )


def meet_fysieke_microfoon_zonder_opslag(
    audiobibliotheek, microfoon, softwarelogboek, auditlogboek, duur_in_seconden=5.0
):
    """Meet vijf seconden alleen getallen, zonder geluid op te slaan of terug te spelen."""
    from app.audio.live_audiomixer import kies_het_juiste_aantal_microfoonkanalen
    from app.audio.signaaldiagnose import meet_rms_en_piek_van_een_audioblok

    kanalen = kies_het_juiste_aantal_microfoonkanalen(audiobibliotheek, microfoon)
    hoogste_rms = 0.0
    hoogste_piek = 0.0
    aantal_callbacks = 0
    aantal_frames = 0
    callback_fout = None
    bufferproblemen = 0

    def ontvang_audioblok(inkomend_geluid, aantal_nieuwe_frames, tijdinformatie, driverstatus):
        nonlocal hoogste_rms, hoogste_piek, aantal_callbacks, aantal_frames
        nonlocal callback_fout, bufferproblemen
        try:
            if driverstatus:
                bufferproblemen += 1
            rms, piek = meet_rms_en_piek_van_een_audioblok(inkomend_geluid)
            hoogste_rms = max(hoogste_rms, rms)
            hoogste_piek = max(hoogste_piek, piek)
            aantal_callbacks += 1
            aantal_frames += aantal_nieuwe_frames
        except Exception as fout:
            # Sla de oorspronkelijke fout op. Een callbackfout mag niet stil
            # verdwijnen, want anders lijkt een mislukte meting op mute.
            callback_fout = fout
            raise audiobibliotheek.CallbackAbort from fout

    schrijf_auditgebeurtenis(
        auditlogboek, "rechtstreekse_microfoontest_gestart",
        {"microfoon": microfoon.naam, "kanalen": kanalen, "duur_seconden": duur_in_seconden}
    )
    with audiobibliotheek.InputStream(
        device=microfoon.huidig_apparaatnummer,
        samplerate=48000,
        channels=kanalen,
        dtype="float32",
        latency="high",
        callback=ontvang_audioblok,
    ):
        time.sleep(duur_in_seconden)

    if callback_fout is not None:
        raise RuntimeError("MIC-002: signaalmeting faalde in de audiocallback") from callback_fout
    if aantal_callbacks == 0:
        raise RuntimeError(
            "MIC-003: de driver startte maar leverde geen enkel audioblok."
        )

    gegevens = {
        "microfoon": microfoon.naam,
        "apparaatnummer": microfoon.huidig_apparaatnummer,
        "invoerkanalen": kanalen,
        "aantal_callbacks": aantal_callbacks,
        "aantal_frames": aantal_frames,
        "hoogste_rms": round(hoogste_rms, 7),
        "hoogste_piek": round(hoogste_piek, 7),
        "bufferproblemen": bufferproblemen,
        "spraakbestand_opgeslagen": False,
    }
    schrijf_auditgebeurtenis(auditlogboek, "rechtstreekse_microfoontest_afgerond", gegevens)
    softwarelogboek.info(
        "Fysieke microfoon direct gemeten, zonder VB-CABLE",
        extra={"gebeurtenis": "microfoonniveau_gemeten", "gegevens": gegevens},
    )
    return gegevens


def start_de_rechtstreekse_microfoontest():
    logboeken = maak_logboeken_klaar()
    zet_uitgebreide_foutafhandeling_aan()
    try:
        import sounddevice as geluidsapparatenbibliotheek
        from app.audio.apparatenbeheer import controleer_werkelijk_aangesloten_audioapparaten
        from app.audio.windows_standaardapparaten import vind_wasapi_standaardapparaat
        apparaten = controleer_werkelijk_aangesloten_audioapparaten(
            logboeken.softwarelogboek
        ).apparaten
        standaard = vind_wasapi_standaardapparaat(
            geluidsapparatenbibliotheek.query_devices(),
            geluidsapparatenbibliotheek.query_hostapis(), 'invoer'
        )
        microfoon = vind_de_microfoon_voor_een_rechtstreekse_test(
            apparaten, standaard[0] if standaard else None
        )
        print("DrostSoundboard - fysieke microfoon controleren")
        print("Sluit eerst de actieve audioverbinding zodat de microfoon vrij is.")
        print("Deze test doet niets met VB-CABLE en bewaart geen geluidsopname.")
        print(f"Gevonden microfoon: {microfoon.naam}")
        input("Druk op Enter en PRAAT daarna vijf seconden in de gekozen microfoon: ")
        print("Meten... praat nu duidelijk in de microfoon.")
        gegevens = meet_fysieke_microfoon_zonder_opslag(
            geluidsapparatenbibliotheek,
            microfoon,
            logboeken.softwarelogboek,
            logboeken.auditlogboek,
        )
        print("\nMeetresultaat:")
        print(f"  Audioblokken ontvangen: {gegevens['aantal_callbacks']}")
        print(f"  Hoogste RMS:            {gegevens['hoogste_rms']:.6f}")
        print(f"  Hoogste piek:           {gegevens['hoogste_piek']:.6f}")
        print(f"  Bufferproblemen:       {gegevens['bufferproblemen']}")
        if gegevens["hoogste_rms"] < 0.0001:
            print("\nGEEN MEETBAAR SIGNAAL. Controleer de mute-knop, driverinstellingen,")
            print("Windows microfoonrechten en het invoervolume bij Opnemen.")
            return 2
        if gegevens["hoogste_rms"] < 0.003:
            print("\nEr komt wel audio binnen, maar het niveau is erg laag.")
            print("Controleer het invoervolume in Windows en in de driverinstellingen.")
            return 0
        print("\nGOED: Python ontvangt aantoonbaar geluid van de gekozen microfoon.")
        return 0
    except Exception as fout:
        logboeken.softwarelogboek.exception(
            "Rechtstreekse microfoontest is mislukt",
            extra={"gebeurtenis": "microfoontest_mislukt", "gegevens": {"foutcode": "MIC-999"}},
        )
        print(f"\nFOUT: {type(fout).__name__}: {fout}")
        print(f"Volledige traceback: {logboeken.map_met_logbestanden / 'software.jsonl'}")
        return 1
    finally:
        sluit_logboeken_netjes_af(logboeken)


if __name__ == "__main__":
    raise SystemExit(start_de_rechtstreekse_microfoontest())
