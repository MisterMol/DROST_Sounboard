"""Vertaal eenvoudige webknoppen naar de bestaande veilige Python-audiomixer.

De webserver mag nooit in een PortAudio-callback werken. Lange MP3-bestanden
worden daarom in een losse werkdraad gedecodeerd. Een stopknop verhoogt het
opdrachtnummer: een verouderde decode kan daarna niets meer laten afspelen.
"""

from __future__ import annotations

from concurrent.futures import Future, ThreadPoolExecutor
from dataclasses import replace
import math
import logging
from pathlib import Path
import time
import threading
from typing import Any

from app.desktop.afsluitbeheer import sluit_onderdelen_af
from app.audio.apparatenbeheer import controleer_werkelijk_aangesloten_audioapparaten
from app.audio.vb_cable_vereisten import beoordeel_vb_cable, resultaat_voor_mislukte_controle
from app.audio.bronduur_en_golfvorm import (bepaal_werkelijke_bronduur, bepaal_werkelijke_fragmentduur,
                                             maak_gedetailleerde_golfvorm_voor_tijdsvenster, BronbestandNietLeesbaar)
from app.audio.geluidenbibliotheek import PersoonlijkeGeluidenbibliotheek
from app.audio.kabelcontrole import selecteer_de_twee_uiteinden_van_vb_cable
from app.audio.live_audiomixer import LiveAudiomixer
from app.audio.natuurlijke_stem.dienst import NatuurlijkeStemDienst
from app.audio.stemvoorbeeld import LokaalStemvoorbeeld, StemvoorbeeldFout
from app.audio.stemvervorming import controleer_kiesbaar_stemprofiel, profiel_catalogus_voor_api
from app.audio.stemparameters import parameters_voor_api
from app.audio.monitor_voor_eigen_headset import MonitorVoorEigenHeadset
from app.audio.windows_standaardapparaten import vind_wasapi_standaardapparaat
from app.audio.mp3_en_wav_fragmenten import lees_en_bereid_mp3_of_wav_voor
from app.audio.preview_normalisatie import bereken_browser_preview_versterkingen
from app.diagnostiek.logboek import BeschikbareLogboeken, schrijf_auditgebeurtenis
from app.webinterface.favorieten_en_instellingen import VasteFavorietenEnInstellingen, controleer_afspeelinstellingen
from app.webinterface.geluidsgroepen import PersoonlijkeGeluidsgroepen
from app.webinterface.extra_geluidsinformatie import BeheerVanExtraGeluidsinformatie
from app.webinterface.recente_geluiden_en_weergave import RecenteGeluidenEnWeergave
from app.webinterface.gebruikersmeldingen import gebruikersmelding


class OngeldigeWebactie(ValueError):
    """Foutcode voor webacties waarvoor geen geldige invoer is gevonden."""


from app.webinterface.stemkeuze import StemKeuzeBediening
from app.audio.natuurlijke_stem.voorbeeld import StemVoorbeeldRenderer


class WebbedieningVanDrostSoundboard(StemKeuzeBediening):
    """Eén instantie voor alle HTTP-verzoeken van een lokale gebruiker."""

    def __init__(self, audiobibliotheek: Any, logboeken: BeschikbareLogboeken,
                 databasepad: Path | None = None):
        self.logboeken = logboeken
        self.audioapparaten = audiobibliotheek
        self.geluidenbibliotheek = PersoonlijkeGeluidenbibliotheek(databasepad)
        self.favorieten = VasteFavorietenEnInstellingen(self.geluidenbibliotheek.databasepad)
        self.groepen = PersoonlijkeGeluidsgroepen(self.geluidenbibliotheek.databasepad)
        self.extra_informatie = BeheerVanExtraGeluidsinformatie(self.geluidenbibliotheek.databasepad)
        self.recent_en_weergave = RecenteGeluidenEnWeergave(self.geluidenbibliotheek.databasepad)
        self._bronduur_cache: dict[str, tuple[int, int, float | None]] = {}
        # Een kleine cache voorkomt dat wisselen tussen standen telkens MP3/MP4
        # opnieuw decodeert. Beperk de gelijktijdige analyses tot één aanvraag.
        self._preview_analyse_cache: dict[tuple, dict] = {}
        self._preview_analyse_slot = threading.BoundedSemaphore(1)
        self._stemvoorbeeld_render_slot = threading.BoundedSemaphore(1)
        self._preview_analyse_lock = threading.Lock()
        self.mixer = LiveAudiomixer(
            audiobibliotheek, logboeken.softwarelogboek, logboeken.auditlogboek
        )
        self.mixer.stel_limiter_in(self.favorieten.geef_limiterstand())
        self.mixer.stel_algemeen_effectvolume_in(self.favorieten.geef_algemeen_effectvolume())
        self.mixer.stel_stemprofiel_in(self.favorieten.geef_stemprofiel())
        self.mixer.stel_stemvervormer_aan_in(self.favorieten.geef_stemvervormer_aan())
        self.mixer.stel_stemintensiteiten_in(self.favorieten.geef_stemintensiteiten())
        self.mixer.stel_stemparameters_in(self.favorieten.geef_stemparameters())
        self.stemvoorbeeld = LokaalStemvoorbeeld(audiobibliotheek, logboeken.softwarelogboek)
        self.stemvoorbeeld.stel_stemintensiteiten_in(self.favorieten.geef_stemintensiteiten())
        self.stemvoorbeeld.stel_stemparameters_in(self.favorieten.geef_stemparameters())
        self.monitor = MonitorVoorEigenHeadset(audiobibliotheek, logboeken.softwarelogboek)
        zelfmonitor = self.favorieten.geef_eigen_stem_monitor()
        self.monitor.stel_eigen_stem_in(zelfmonitor['aan'], zelfmonitor['volume'])
        self.mixer.stel_eigen_stem_monitor_in(zelfmonitor['aan'])
        self.mixer.koppel_monitor_voor_effecten(
            self.monitor.ontvang_alleen_effectsamples, self.monitor.maak_monitorbuffer_leeg,
            self.monitor.ontvang_live_mix,
        )
        self._bescherm_toestand = threading.RLock()
        self._volgnummer_van_voorbereiden = 0
        self._wordt_voorbereid: str | None = None
        self._laatste_afspeelfout: str | None = None
        self._werkdraad_voor_decoderen = ThreadPoolExecutor(
            max_workers=1, thread_name_prefix='MP3-voorbereiden'
        )
        # Een reeks snelle klikken mag geen eindeloze rij decodeertaken maken.
        # Bewaar alleen de laatste nog niet gestarte opdracht; de actieve
        # decode kan zichzelf bij afronden al op een verouderd nummer afwijzen.
        self._laatste_ingediende_decode: Future | None = None
        self._wordt_afgesloten = False
        self.natuurlijke_stem = NatuurlijkeStemDienst(
            self.geluidenbibliotheek.databasepad.parent / 'stem2_keuze.json',
            logboeken.softwarelogboek)
        self._stemkeuze_generatie = 0
        self.stemkeuze_voorbeelden = StemVoorbeeldRenderer(self.natuurlijke_stem.root)
        self.mixer.natuurlijke_stem = self.natuurlijke_stem
        self.stemvoorbeeld.natuurlijke_stem = self.natuurlijke_stem
        try:
            self.migreer_vervallen_stemkeuze()
        except Exception:
            # De webserver en de microfoon zijn nog niet gestart. Ruim wel een
            # eventueel al ladende modelworker op voordat opstarten afbreekt.
            try:
                self._sluit_natuurlijke_stem()
            finally:
                self._werkdraad_voor_decoderen.shutdown(wait=False, cancel_futures=True)
            raise

    def geef_natuurlijke_stem_status(self) -> dict:
        dienst = getattr(self, 'natuurlijke_stem', None)
        return dienst.status() if dienst is not None else {'aan': False, 'toestand': 'uit', 'beschikbaar': False}

    def stel_natuurlijke_stem_in(self, aan: bool) -> dict:
        if type(aan) is not bool:
            raise OngeldigeWebactie('Kies aan of uit voor de proefstem.')
        with self._bescherm_toestand:
            if self._wordt_afgesloten:
                raise OngeldigeWebactie('De app wordt afgesloten.')
            return self.natuurlijke_stem.stel_in(aan)

    def beheer_natuurlijke_stem(self, actie: str, bufferprofiel=None) -> dict:
        """Eén beheerverzoek tegelijk; nooit tijdens een lopend gesprek testen."""
        with self._bescherm_toestand:
            if self._wordt_afgesloten:
                raise OngeldigeWebactie('De app wordt afgesloten.')
            if actie == 'stop_test':
                return self.natuurlijke_stem.annuleer_test()
            if actie not in ('test', 'buffer'):
                raise OngeldigeWebactie('Onbekende actie voor de proefstem.')
            if self.mixer.geef_huidige_status().toestand != 'verbroken' or self.stemvoorbeeld.actief:
                raise OngeldigeWebactie('Verbreek eerst de microfoonverbinding en stop de stempreview.')
            try:
                if actie == 'test':
                    return self.natuurlijke_stem.test_computer()
                return self.natuurlijke_stem.stel_bufferprofiel_in(bufferprofiel)
            except ValueError as fout:
                raise OngeldigeWebactie(str(fout)) from fout

    def geef_natuurlijke_stem_rapport(self) -> dict:
        return self.natuurlijke_stem.geef_rapport()

    def _controleer_computertest(self) -> None:
        dienst = getattr(self, 'natuurlijke_stem', None)
        if dienst is not None and dienst.status().get('test_bezig') is True:
            raise OngeldigeWebactie('Stop eerst de computertest voordat je de microfoon verbindt.')

    def _controleer_gewone_stemkeuze(self) -> None:
        dienst = getattr(self, 'natuurlijke_stem', None)
        if dienst is not None and dienst.aan:
            raise OngeldigeWebactie('Zet de proefstem eerst uit om gewone stemprofielen te wijzigen.')

    def _wis_natuurlijke_stemaudio(self) -> None:
        dienst = getattr(self, 'natuurlijke_stem', None)
        if dienst is not None:
            dienst.wis_audio()

    def _sluit_natuurlijke_stem(self) -> bool:
        voorbeelden = getattr(self, 'stemkeuze_voorbeelden', None)
        resultaat = True
        if voorbeelden is not None:
            try: resultaat = voorbeelden.sluiten()
            except Exception:
                resultaat = False
                self.logboeken.softwarelogboek.exception('Stemvoorbeelden afsluiten mislukt')
        dienst = getattr(self, 'natuurlijke_stem', None)
        return (dienst.sluiten() if dienst is not None else True) and resultaat

    def geef_apparaten_voor_de_webpagina(self) -> list[dict[str, Any]]:
        overzicht = controleer_werkelijk_aangesloten_audioapparaten(self.logboeken.softwarelogboek)
        return [
            {'nummer': a.huidig_apparaatnummer, 'naam': a.naam}
            for a in overzicht.apparaten
            if a.api_naam.casefold() == 'windows wasapi'
            and a.aantal_invoerkanalen > 0
            and 'cable' not in a.naam.casefold()
            and 'vb-audio' not in a.naam.casefold()
        ]

    def geef_standaard_microfoonnummer_voor_de_webpagina(
        self, zichtbare_microfoons: list[dict[str, Any]],
    ) -> int | None:
        """Kies de Windows-standaardinvoer, nooit een fabrikant op naam.

        Ontbreekt die en is er precies één bruikbare microfoon, kies die.
        Bij meerdere zonder geldige standaard moet de gebruiker zelf kiezen.
        Apparaatnummers zijn tijdelijk en worden opnieuw opgevraagd bij
        het vernieuwen van de lijst.
        """
        try:
            standaard = vind_wasapi_standaardapparaat(
                self.audioapparaten.query_devices(),
                self.audioapparaten.query_hostapis(),
                'invoer',
            )
        except Exception:
            self.logboeken.softwarelogboek.exception(
                'Het standaardmicrofoonapparaat kon niet worden bepaald',
                extra={'gebeurtenis': 'standaard_microfoon_onbekend'},
            )
            return None
        if standaard is None:
            return zichtbare_microfoons[0]['nummer'] if len(zichtbare_microfoons) == 1 else None
        nummer, naam = standaard
        # Tussen twee WASAPI-vragen kan een USB-apparaat worden losgekoppeld.
        # Een gelijk nummer met een andere naam is geen veilige automatische keuze.
        if any(item['nummer'] == nummer and item['naam'] == naam for item in zichtbare_microfoons):
            return nummer
        return zichtbare_microfoons[0]['nummer'] if len(zichtbare_microfoons) == 1 else None

    def geef_uitvoerapparaten_voor_de_webpagina(self) -> list[dict[str, Any]]:
        """Laat alleen echte WASAPI-uitgangen zien, nooit de virtuele kabel."""
        overzicht = controleer_werkelijk_aangesloten_audioapparaten(self.logboeken.softwarelogboek)
        return [
            {'nummer': apparaat.huidig_apparaatnummer, 'naam': apparaat.naam}
            for apparaat in overzicht.apparaten
            if apparaat.api_naam.casefold() == 'windows wasapi'
            and apparaat.aantal_uitvoerkanalen >= 2
            and 'cable' not in apparaat.naam.casefold()
            and 'vb-audio' not in apparaat.naam.casefold()
        ]

    def geef_vb_cable_status(self) -> dict[str, object]:
        """Doe alleen op verzoek een apparaatcontrole, buiten de audiocallback.

        De UI krijgt bij een Windows-/PortAudio-fout een onbekende status, geen
        onterecht advies dat de driver ontbreekt. De echte fout staat in het log.
        """
        try:
            overzicht = controleer_werkelijk_aangesloten_audioapparaten(
                self.logboeken.softwarelogboek)
            return beoordeel_vb_cable(overzicht.apparaten)
        except Exception:
            self.logboeken.softwarelogboek.exception(
                'VB-CABLE kon niet op beschikbaarheid worden gecontroleerd',
                extra={
                    'gebeurtenis': 'vb_cable_controle_mislukt',
                    'gegevens': {'foutcode': 'VB-CABLE-001'},
                },
            )
            return resultaat_voor_mislukte_controle()

    def stel_meeluisteren_in(self, aan: bool, apparaatnummer: int | None = None) -> None:
        """Een kapotte headsetmonitor mag de virtuele microfoon niet verbreken."""
        if type(aan) is not bool:
            raise OngeldigeWebactie('WEB-040: meeluisteren moet true of false zijn.')
        if apparaatnummer is not None:
            geldige = {a['nummer'] for a in self.geef_uitvoerapparaten_voor_de_webpagina()}
            if type(apparaatnummer) is not int or apparaatnummer not in geldige:
                raise OngeldigeWebactie('WEB-041: kies een geldig headset-uitvoerapparaat.')
        self.monitor.kies_uitvoerapparaat(apparaatnummer)
        if self.monitor.ingeschakeld != aan:
            self.monitor.maak_monitorbuffer_leeg()
        self.monitor.ingeschakeld = aan
        if not aan and not self.monitor.eigen_stem_ingeschakeld:
            self.monitor.sluit_monitor()
        schrijf_auditgebeurtenis(self.logboeken.auditlogboek, 'meeluisteren_ingesteld', {
            'ingeschakeld': aan, 'uitvoerapparaatnummer': apparaatnummer,
        })

    def stel_eigen_stem_monitor_in(self, aan: bool, volume: int) -> dict:
        """De slider geldt alleen voor de eigen headset, nooit voor VB-CABLE."""
        if type(aan) is not bool or type(volume) is not int or not 1 <= volume <= 100:
            raise OngeldigeWebactie('MON-010: kies aan of uit en volume 1 tot 100%.')
        vorige = self.favorieten.geef_eigen_stem_monitor()
        if vorige['aan'] != aan:
            self.monitor.maak_monitorbuffer_leeg()
        self.monitor.stel_eigen_stem_in(aan, volume)
        self.mixer.stel_eigen_stem_monitor_in(aan)
        if aan and self.mixer.geef_huidige_status().toestand == 'verbonden':
            try:
                if not self.monitor.zorg_dat_monitor_kan_afspelen():
                    raise OngeldigeWebactie('MON-011: luisterapparaat kan niet starten.')
            except Exception as fout:
                # Geen schijnbare succesvolle wijziging als de uitvoer faalt.
                self.monitor.stel_eigen_stem_in(vorige['aan'], vorige['volume'])
                self.mixer.stel_eigen_stem_monitor_in(vorige['aan'])
                raise OngeldigeWebactie('MON-011: luisterapparaat kan niet starten. Controleer je headset.') from fout
        instelling = self.favorieten.bewaar_eigen_stem_monitor(aan, volume)
        if not aan and not self.monitor.ingeschakeld:
            self.monitor.sluit_monitor()
        return instelling

    def registreer_preview(
        self, geluid_id: str, actie: str, verstreken_seconden: float = 0.0, reden: str = 'niet_opgegeven',
        afspeelbeurt: str | None = None,
    ) -> None:
        """Een browserpreview is lokaal en mag nooit de VB-CABLE-mixer activeren."""
        item = self.zoek_geluid_met_id(geluid_id)
        if actie not in ('gestart', 'gestopt', 'verplaatst'):
            raise OngeldigeWebactie('WEB-042: previewactie moet gestart of gestopt zijn.')
        if (isinstance(verstreken_seconden, bool) or not isinstance(verstreken_seconden, (int, float))
                or not 0 <= verstreken_seconden <= 120):
            raise OngeldigeWebactie('WEB-043: previewduur moet tussen nul en 120 seconden liggen.')
        if not isinstance(reden, str) or len(reden) > 80:
            raise OngeldigeWebactie('WEB-044: geef een korte reden voor het stoppen op.')
        # Alleen echt gestarte previews komen in de recente geschiedenis.
        # Verplaatsen van de afspeelcursor is geen nieuwe afspeelbeurt.
        if actie == 'gestart':
            self.recent_en_weergave.registreer_afspelen(
                geluid_id, item.eigen_naam, 'preview', afspeelbeurt
            )
        elif actie == 'gestopt':
            self.recent_en_weergave.registreer_afspeel_einde(
                geluid_id, 'preview', reden, verstreken_seconden, afspeelbeurt
            )
        schrijf_auditgebeurtenis(self.logboeken.auditlogboek, f'preview_{actie}', {
            'geluid_id': geluid_id, 'naam': item.eigen_naam,
            'verstreken_tijd_seconden': round(float(verstreken_seconden), 3),
            'geen_audio_naar_vb_cable': True, 'reden': reden,
        })

    def stel_stemprofiel_in(self, profiel: str) -> str:
        """Bewaar de keuze, wissel live en in preview zonder stream-herstart."""
        self._controleer_gewone_stemkeuze()
        profiel = controleer_kiesbaar_stemprofiel(profiel)
        gekozen = self.favorieten.bewaar_stemprofiel(profiel)
        self.mixer.stel_stemprofiel_in(gekozen)
        self.stemvoorbeeld.stel_stemprofiel_in(gekozen)
        schrijf_auditgebeurtenis(self.logboeken.auditlogboek, 'stemprofiel_ingesteld',
                                 {'profiel': gekozen})
        return gekozen

    def stel_stemvervormer_aan_in(self, aan: bool) -> bool:
        # De geselecteerde stem en de preview blijven onveranderd.
        self._controleer_gewone_stemkeuze()
        gekozen = self.favorieten.bewaar_stemvervormer_aan(aan)
        self.mixer.stel_stemvervormer_aan_in(gekozen)
        schrijf_auditgebeurtenis(self.logboeken.auditlogboek, 'stemvervormer_geschakeld',
                                 {'ingeschakeld': gekozen})
        return gekozen

    def maak_bibliotheek_leeg(self, bevestiging: str) -> dict:
        """Eerst een DB-kopie, dan alleen de bibliotheektabellen wissen."""
        from app.webinterface.bibliotheek_opnieuw_beginnen import begin_met_lege_bibliotheek
        # Stop eventuele geluidsfragmenten, nooit de doorlopende microfoon.
        self.stop_het_huidige_geluid()
        if self._wordt_voorbereid is not None:
            raise OngeldigeWebactie('BIB-084: een geluid wordt nog voorbereid. Probeer opnieuw.')
        resultaat = begin_met_lege_bibliotheek(self.geluidenbibliotheek.databasepad, bevestiging)
        self._bronduur_cache.clear()
        with self._preview_analyse_lock:
            self._preview_analyse_cache.clear()
        schrijf_auditgebeurtenis(self.logboeken.auditlogboek, 'bibliotheek_leeggemaakt', {
            'geluiden': resultaat['geluiden_verwijderd'], 'mappen': resultaat['mappen_verwijderd'],
            'backup': resultaat['reservekopie'], 'bronbestanden_verwijderd': False,
        })
        return resultaat

    def geef_steminstellingen(self) -> dict:
        return {'natuurlijke_stem': self.geef_natuurlijke_stem_status(),
                'migratiemelding': getattr(self, '_stemkeuze_migratiemelding', ''),
                'profiel': self.favorieten.geef_stemprofiel(),
                'actief': self.favorieten.geef_stemvervormer_aan(),
                'preview': self.stemvoorbeeld.status(),
                'profielen': profiel_catalogus_voor_api(),
                'intensiteiten': self.favorieten.geef_stemintensiteiten(),
                'effectparameters': self.favorieten.geef_stemparameters(),
                'parameters_catalogus': parameters_voor_api(),
                'voorbeeldspreker': self.favorieten.geef_voorbeeldspreker()}

    def stel_stemintensiteit_in(self, profiel: str, intensiteit: int) -> dict:
        # Geen streamstop; voor opslag draaien we buiten de audiocallback.
        controleer_kiesbaar_stemprofiel(profiel)
        gekozen = self.favorieten.bewaar_stemintensiteit(profiel, intensiteit)
        waarden = self.favorieten.geef_stemintensiteiten()
        self.mixer.stel_stemintensiteiten_in(waarden)
        self.stemvoorbeeld.stel_stemintensiteiten_in(waarden)
        return {'profiel': profiel, 'intensiteit': gekozen, 'intensiteiten': waarden}

    def herstel_stemintensiteit(self, profiel: str | None) -> dict:
        if profiel is not None:
            controleer_kiesbaar_stemprofiel(profiel)
        waarden = self.favorieten.herstel_stemintensiteit(profiel)
        self.mixer.stel_stemintensiteiten_in(waarden)
        self.stemvoorbeeld.stel_stemintensiteiten_in(waarden)
        return {'intensiteiten': waarden}

    def stel_stemparameters_in(self, profiel: str, waarden: dict) -> dict:
        nieuw = self.favorieten.bewaar_stemparameters(profiel, waarden)
        alles = self.favorieten.geef_stemparameters()
        self.mixer.stel_stemparameters_in(alles)
        self.stemvoorbeeld.stel_stemparameters_in(alles)
        return {'profiel': profiel, 'parameters': nieuw, 'effectparameters': alles}

    def herstel_stemparameters(self, profiel: str | None) -> dict:
        alles = self.favorieten.herstel_stemparameters(profiel)
        self.mixer.stel_stemparameters_in(alles)
        self.stemvoorbeeld.stel_stemparameters_in(alles)
        return {'effectparameters': alles}

    def bewaar_voorbeeldspreker(self, spreker: str) -> dict:
        return {'voorbeeldspreker': self.favorieten.bewaar_voorbeeldspreker(spreker)}

    def maak_voorbeeldstem_wav(self, spreker: str) -> bytes:
        # Alleen één CPU-intensieve rendering tegelijk; geen audioverbinding nodig.
        self._controleer_gewone_stemkeuze()
        from app.audio.ingebouwde_stemvoorbeelden import render_voorbeeld
        if not self._stemvoorbeeld_render_slot.acquire(timeout=1):
            raise OngeldigeWebactie('STEM-058: voorbeeld wordt al voorbereid.')
        try:
            profiel = self.favorieten.geef_stemprofiel()
            return render_voorbeeld(spreker, profiel,
                                   self.favorieten.geef_stemintensiteiten()[profiel],
                                   self.favorieten.geef_stemparameters())
        finally:
            self._stemvoorbeeld_render_slot.release()

    def begin_stemvoorbeeld(self, microfoonnummer: int, uitvoernummer: int | None = None) -> dict:
        """Alleen lokaal afluisteren, zonder VB-CABLE en zonder stemopslag.

        Preview en liveverbinding delen nooit een tweede microfoonstream.
        """
        if type(microfoonnummer) is not int or (uitvoernummer is not None and type(uitvoernummer) is not int):
            raise OngeldigeWebactie('STEM-020: kies een geldige microfoon en luisteruitvoer.')
        with self._bescherm_toestand:
            if self._wordt_afgesloten:
                raise OngeldigeWebactie('STEM-021: DrostSoundboard wordt afgesloten.')
            self._controleer_computertest()
            dienst = getattr(self, 'natuurlijke_stem', None)
            if dienst is not None and getattr(dienst, 'gekozen', False) is True and not dienst.aan:
                raise OngeldigeWebactie('Zet de gekozen karakterstem eerst aan om je eigen microfoon te testen. Bob en Elise kun je ook zonder inschakelen beluisteren.')
            if self.mixer.geef_huidige_status().toestand != 'verbroken':
                raise OngeldigeWebactie('STEM-022: verbreek eerst de liveverbinding om lokaal je stem te testen.')
            if self.stemvoorbeeld.actief:
                raise OngeldigeWebactie('STEM-023: er draait al een stempreview.')
            overzicht = controleer_werkelijk_aangesloten_audioapparaten(self.logboeken.softwarelogboek)
            invoer = next((a for a in overzicht.apparaten
                           if a.huidig_apparaatnummer == microfoonnummer
                           and a.api_naam.casefold() == 'windows wasapi'
                           and a.aantal_invoerkanalen > 0
                           and 'cable' not in a.naam.casefold()
                           and 'vb-audio' not in a.naam.casefold()), None)
            if invoer is None:
                raise OngeldigeWebactie('STEM-024: microfoon niet gevonden. Vernieuw de apparatenlijst.')
            # Expliciete keuze wint; anders de Windows-standaarduitvoer.
            nummer = uitvoernummer
            if nummer is None:
                nummer = self.monitor.gekozen_apparaatnummer
            if nummer is None:
                standaard = vind_wasapi_standaardapparaat(
                    self.audioapparaten.query_devices(), self.audioapparaten.query_hostapis(), 'uitvoer')
                nummer = standaard[0] if standaard else None
            uitvoer = next((a for a in overzicht.apparaten
                            if a.huidig_apparaatnummer == nummer
                            and a.api_naam.casefold() == 'windows wasapi'
                            and a.aantal_uitvoerkanalen >= 2
                            and 'cable' not in a.naam.casefold()
                            and 'vb-audio' not in a.naam.casefold()), None)
            if uitvoer is None:
                raise OngeldigeWebactie('STEM-025: kies een bruikbaar fysiek luisterapparaat.')
            try:
                self.stemvoorbeeld.start(invoer, uitvoer, self.favorieten.geef_stemprofiel())
            except StemvoorbeeldFout as fout:
                raise OngeldigeWebactie(str(fout)) from fout
        return self.stemvoorbeeld.status()

    def stop_stemvoorbeeld(self) -> dict:
        with self._bescherm_toestand:
            try:
                self.stemvoorbeeld.stop()
                self._wis_natuurlijke_stemaudio()
            except StemvoorbeeldFout as fout:
                raise OngeldigeWebactie(str(fout)) from fout
        return self.stemvoorbeeld.status()

    def verbind_met_microfoon(self, gekozen_nummer: int) -> None:
        """Herken steeds opnieuw, want een USB-herverbinding wijzigt apparaatnummers."""
        if type(gekozen_nummer) is not int:
            raise OngeldigeWebactie('WEB-001: kies een geldig microfoonnummer.')
        # Snelle dubbele klikken mogen geen tweede WASAPI-stream starten.
        # Het slot beschermt deze check én de opdracht aan de mixer.
        with self._bescherm_toestand:
            if self._wordt_afgesloten:
                raise OngeldigeWebactie('WEB-081: DrostSoundboard wordt afgesloten.')
            self._controleer_computertest()
            if self.stemvoorbeeld.actief:
                raise OngeldigeWebactie('STEM-026: stop eerst de lokale stempreview.')
            huidige_status = self.mixer.geef_huidige_status()
            if huidige_status.toestand in ('wordt_verbonden', 'verbonden'):
                return
            if huidige_status.toestand == 'wordt_verbroken':
                raise OngeldigeWebactie('WEB-080: wacht totdat de vorige verbinding is verbroken.')
        overzicht = controleer_werkelijk_aangesloten_audioapparaten(self.logboeken.softwarelogboek)
        kandidaten = [a for a in overzicht.apparaten
                      if a.huidig_apparaatnummer == gekozen_nummer
                      and a.api_naam.casefold() == 'windows wasapi'
                      and a.aantal_invoerkanalen > 0]
        if len(kandidaten) != 1:
            raise OngeldigeWebactie('WEB-002: de geselecteerde microfoon is niet meer aanwezig. Vernieuw de lijst.')
        kabel = selecteer_de_twee_uiteinden_van_vb_cable(overzicht.apparaten).afspeelkant
        with self._bescherm_toestand:
            # Tussen apparaatdetectie en aanroepen kan een ander verzoek
            # binnenkomen. Daarom controleren we de toestand opnieuw.
            if self._wordt_afgesloten:
                raise OngeldigeWebactie('WEB-081: DrostSoundboard wordt afgesloten.')
            self._controleer_computertest()
            huidige_status = self.mixer.geef_huidige_status()
            if huidige_status.toestand in ('wordt_verbonden', 'verbonden'):
                return
            if huidige_status.toestand == 'wordt_verbroken':
                raise OngeldigeWebactie('WEB-080: wacht totdat de vorige verbinding is verbroken.')
            self.mixer.verbind_de_microfoon_met_vb_cable(kandidaten[0], kabel)
            if self.monitor.eigen_stem_ingeschakeld:
                try:
                    self.monitor.zorg_dat_monitor_kan_afspelen()
                except Exception:
                    # Een defecte headset mag de virtuele microfoon niet verbreken.
                    self.logboeken.softwarelogboek.exception('Stemmonitor kan niet starten')

    def verbreek_de_verbinding(self) -> None:
        self.stop_het_huidige_geluid()
        self.mixer.verbreek_de_verbinding()
        self._wis_natuurlijke_stemaudio()
        self.monitor.sluit_monitor()

    def zet_soundboard_aan_of_uit(self, aan: bool) -> None:
        if type(aan) is not bool:
            raise OngeldigeWebactie('WEB-003: soundboardstand moet true of false zijn.')
        if not aan:
            # Een lopende decode mag de geluidsknop niet alsnog activeren.
            with self._bescherm_toestand:
                self._volgnummer_van_voorbereiden += 1
                self._wordt_voorbereid = None
        self.mixer.zet_geluidseffecten_aan_of_uit(aan)
        if not aan:
            self.monitor.maak_monitorbuffer_leeg()

    def stel_tijdelijk_effectvolume_in(self, percentage: int) -> int:
        """Pas de schuif live toe; bewaar pas bij loslaten op schijf."""
        if type(percentage) is not int or not 0 <= percentage <= 200:
            raise OngeldigeWebactie('VOLUME-002: verwacht een geheel percentage van 0 tot 200.')
        self.mixer.stel_algemeen_effectvolume_in(percentage)
        return percentage

    def stel_algemeen_effectvolume_in(self, percentage: int) -> int:
        """Bewaar en pas een mastervolume toe zonder de microfoon te beïnvloeden."""
        percentage = self.favorieten.bewaar_algemeen_effectvolume(percentage)
        self.mixer.stel_algemeen_effectvolume_in(percentage)
        schrijf_auditgebeurtenis(self.logboeken.auditlogboek,
                                 'algemeen_effectvolume_ingesteld', {'percentage': percentage})
        return percentage

    def stel_pieklimiter_in(self, ingeschakeld: bool) -> bool:
        """Bewaar veilig buiten de callback en pas meteen op de eindmix toe."""
        meting = self.favorieten.bewaar_limiterstand(ingeschakeld)
        self.mixer.stel_limiter_in(meting)
        schrijf_auditgebeurtenis(self.logboeken.auditlogboek, 'pieklimiter_ingesteld',
                                 {'ingeschakeld': meting})
        return meting

    def geef_huidige_webstatus(self) -> dict[str, Any]:
        status = self.mixer.geef_huidige_status()
        with self._bescherm_toestand:
            bezig = self._wordt_voorbereid
            afspeelfout = self._laatste_afspeelfout
        return {
            'natuurlijke_stem': self.geef_natuurlijke_stem_status(),
            'toestand': status.toestand,
            'microfoon': status.microfoon,
            'uitvoer': status.uitvoer,
            'effecten_aan': status.geluidseffecten_aan,
            'microfoon_rms': status.laatst_gemeten_microfoon_rms,
            'kabel_rms': status.laatst_gemeten_kabel_rms,
            'microfoon_piek': status.laatst_gemeten_microfoon_piek,
            'kabel_piek': status.laatst_gemeten_kabel_piek,
            'is_signaal_gemeten': status.is_signaal_gemeten,
            'bufferproblemen': status.aantal_bufferproblemen,
            'effectvolume_percentage': self.mixer.geef_algemeen_effectvolume(),
            'effect_actief': status.effect_actief,
            'effect_rms_voor': status.effect_rms_voor,
            'effect_rms_na': status.effect_rms_na,
            'limiter_aan': status.limiter_aan,
            'limiter_reductie_db': status.limiter_reductie_db,
            'limiter_terugvallen': status.limiter_terugvallen,
            'stemprofiel': status.stemprofiel,
            'stemvervormer_aan': self.mixer.is_stemvervormer_ingeschakeld(),
            'stem_rms': status.stem_rms,
            'stem_piek': status.stem_piek,
            'stemvervorming_terugvallen': status.stemvervorming_terugvallen,
            'stemvervorming_geblokkeerd': getattr(status, 'stemvervorming_geblokkeerd', False),
            'stemvoorbeeld': self.stemvoorbeeld.status(),
            'callbacks': status.aantal_audio_callbacks,
            'fout': gebruikersmelding(status.laatst_bekende_fout) if status.laatst_bekende_fout else None,
            'geluid_voorbereiden': bezig,
            'laatste_afspeelfout': gebruikersmelding(afspeelfout, standaard='Dit geluid kan niet worden afgespeeld. Controleer het bestand of importeer het opnieuw.') if afspeelfout else None,
            'huidig_geluid': getattr(status, 'huidig_geluid', None),
            'huidig_geluid_id': getattr(status, 'huidig_geluid_id', None),
            'afspeelbeurt_id': getattr(status, 'afspeelbeurt_id', None),
            'afgespeelde_seconden': getattr(status, 'afgespeelde_seconden', 0.0),
            'beginpositie_seconden': getattr(status, 'beginpositie_seconden', 0.0),
            'live_herhalen': getattr(status, 'live_herhalen', False),
            'live_basisvolume': getattr(status, 'live_basisvolume', None),
            'positie_wijzigingsnummer': getattr(status, 'positie_wijzigingsnummer', 0),
            'meeluisteren_aan': self.monitor.ingeschakeld,
            'eigen_stem_horen_aan': self.monitor.eigen_stem_ingeschakeld,
            'eigen_stem_horen_volume': self.monitor.eigen_stem_volume,
            'meeluisteruitvoer': self.monitor.huidige_apparaatnaam,
            'meeluisterfout': gebruikersmelding(self.monitor.laatste_fout, standaard='Meeluisteren is niet beschikbaar. Controleer je headset en de gekozen uitvoer.') if self.monitor.laatste_fout else None,
            'meeluisterbufferproblemen': self.monitor.aantal_overgelopen_blokken,

            'startpoging': status.huidige_startpoging,
            'maximale_startpogingen': status.maximale_startpogingen,
        }

    def geef_directe_audioniveaus(self) -> dict[str, Any]:
        """Lever alléén live meetwaarden, zonder database of media-bestanden.

        Dit endpoint mag circa 30 keer per seconde worden gelezen. De rest
        van het dashboard blijft de gewone, rustige statusroute gebruiken.
        Bij een stilgevallen audiocallback tonen we geen verouderde niveaus.
        """
        status = self.mixer.geef_huidige_status()
        actief = (
            status.toestand == 'verbonden'
            and status.is_signaal_gemeten
            and status.seconden_sinds_laatste_callback is not None
            and status.seconden_sinds_laatste_callback <= 0.2
        )
        # De lokale stempreview gebruikt al dezelfde meetcallback. Lever
        # deze kleine meetwaarden over de bestaande 30 Hz-niveaustroom;
        # een tweede HTTP-poller of audiostream is niet nodig.
        voorbeeld = getattr(self, 'stemvoorbeeld', None)
        preview = voorbeeld.status() if voorbeeld is not None else {'actief': False, 'gemeten': False}
        return {
            'gemeten': actief,
            'toestand': status.toestand,
            'huidig_geluid_id': getattr(status, 'huidig_geluid_id', None),
            'afspeelbeurt_id': getattr(status, 'afspeelbeurt_id', None),
            'afgespeelde_seconden': getattr(status, 'afgespeelde_seconden', 0.0),
            'beginpositie_seconden': getattr(status, 'beginpositie_seconden', 0.0),
            'live_herhalen': getattr(status, 'live_herhalen', False),
            'live_basisvolume': getattr(status, 'live_basisvolume', None),
            'positie_wijzigingsnummer': getattr(status, 'positie_wijzigingsnummer', 0),
            'is_signaal_gemeten': actief,
            'stemvoorbeeld': preview,
            'bufferproblemen': status.aantal_bufferproblemen if actief else 0,
            'stem_rms': status.stem_rms if actief else 0.0,
            'stem_piek': status.stem_piek if actief else 0.0,
            'microfoon_rms': status.laatst_gemeten_microfoon_rms if actief else 0.0,
            'kabel_rms': status.laatst_gemeten_kabel_rms if actief else 0.0,
            'microfoon_piek': status.laatst_gemeten_microfoon_piek if actief else 0.0,
            'kabel_piek': status.laatst_gemeten_kabel_piek if actief else 0.0,
            'limiter_reductie_db': status.limiter_reductie_db if actief else 0.0,
            'effect_actief': actief and status.effect_actief,
            'effect_rms_voor': status.effect_rms_voor if actief else 0.0,
            'effect_rms_na': status.effect_rms_na if actief else 0.0,
            'laatste_audio_ms_geleden': (
                round(status.seconden_sinds_laatste_callback * 1000)
                if status.seconden_sinds_laatste_callback is not None else None
            ),
            'verzonden_op_ms': time.time_ns() // 1_000_000,
        }

    def geef_echte_duur_van_geluid(self, item: Any) -> float | None:
        """Lees de werkelijke lengte eenmalig, niet bij ieder browserverzoek.

        We gebruiken bestandsgrootte en wijzigingsdatum als cachesleutel. De
        audiomixer mag hiervan geen hinder ondervinden en hoeft nooit een
        MP3- of MP4-header te openen binnen de realtime audiocallback.
        """
        try:
            informatie = item.bestandspad.stat()
        except OSError:
            return None
        in_cache = self._bronduur_cache.get(item.geluid_id)
        sleutel = (informatie.st_size, informatie.st_mtime_ns)
        if in_cache and in_cache[:2] == sleutel:
            return in_cache[2]
        try:
            duur = bepaal_werkelijke_bronduur(item.bestandspad)
        except BronbestandNietLeesbaar as fout:
            # Een oud, ongeldig of intussen veranderd bestand mag niet het
            # gehele dashboard breken. De editor toont dan 'onbekend'.
            self.logboeken.softwarelogboek.warning(
                'Lengte van een geluid kon niet worden bepaald',
                exc_info=True,
                extra={'gebeurtenis': 'bronduur_onbekend', 'gegevens': {
                    'geluid_id': item.geluid_id, 'fouttype': type(fout).__name__,
                }},
            )
            duur = None
        self._bronduur_cache[item.geluid_id] = (*sleutel, duur)
        return duur

    def geef_golfvorm_van_geluid(
        self, geluid_id: str, begin: float, duur: float, resolutie: int = 160,
    ) -> dict[str, Any]:
        """Laat de editor een klein golfvormvenster ophalen, zonder audiomix."""
        item = self.zoek_geluid_met_id(geluid_id)
        bronduur = self.geef_echte_duur_van_geluid(item)
        if bronduur is None or begin >= bronduur:
            raise OngeldigeWebactie('WEB-060: geen bruikbaar audiobestand of begin voorbij de bron.')
        werkelijk_venster = min(float(duur), 120.0, bronduur - float(begin))
        gegevens = maak_gedetailleerde_golfvorm_voor_tijdsvenster(
            item.bestandspad, begin, werkelijk_venster, resolutie,
        )
        return {**gegevens, 'begin': begin, 'vensterduur': werkelijk_venster,
                'bronduur': bronduur, 'resolutie': resolutie}

    def geef_geluidsbibliotheek(self) -> dict[str, Any]:
        from app.webinterface.losse_media_exporteren import geef_mogelijke_exportformaten
        # Zelfde beheerde map als de HTTP-server; nooit media uit willekeurige
        # paden in de downloadlijst aanbieden.
        import os
        mediamap = Path(os.environ.get('LOCALAPPDATA') or (Path.home() / '.drostsoundboard')) / 'DrostSoundboard' / 'media'
        alle_geluiden = self.geluidenbibliotheek.geef_alle_geluiden()
        favorieten = self.favorieten.geef_alle_favorietplekken()
        groepen_per_geluid = self.groepen.geef_groepsnummers_per_geluid()
        aanvullende_informatie = self.extra_informatie.geef_alle_informatie()
        resultaat = []
        afspeelaantallen = self.recent_en_weergave.geef_afspeelaantallen()
        for item in alle_geluiden:
            instellingen = self.favorieten.geef_instellingen_van_geluid(item.geluid_id)
            bronduur = self.geef_echte_duur_van_geluid(item)
            fragmentduur = bepaal_werkelijke_fragmentduur(
                bronduur, instellingen.begint_bij_seconden, instellingen.maximale_duur_seconden
            )
            resultaat.append({
                'id': item.geluid_id,
                'naam': item.eigen_naam,
                'aantal_afgespeeld': afspeelaantallen.get(item.geluid_id, 0),
                'bestandsnaam': item.bestandspad.name,
                'formaat': item.bestandspad.suffix.lower().lstrip('.'),
                'bestand_gevonden': item.bestandspad.is_file(),
                'beginpositie': instellingen.begint_bij_seconden,
                'volume': instellingen.volume,
                'exportformaten': geef_mogelijke_exportformaten(
                    self, mediamap, item.geluid_id, bron=item.bestandspad, instellingen=instellingen
                ),
                'maximale_duur': instellingen.maximale_duur_seconden,
                'bronduur': bronduur,
                'fragmentduur': fragmentduur,
                'groep_ids': groepen_per_geluid.get(item.geluid_id, []),
                'beschrijving': aanvullende_informatie[item.geluid_id].beschrijving if item.geluid_id in aanvullende_informatie else '',
                'gesproken_tekst': aanvullende_informatie[item.geluid_id].gesproken_tekst if item.geluid_id in aanvullende_informatie else '',
                'zoekwoorden': aanvullende_informatie[item.geluid_id].zoekwoorden if item.geluid_id in aanvullende_informatie else '',
                'mediabron': f'/media/{item.geluid_id}' if item.bestandspad.is_file() else None,
                'is_video': item.bestandspad.suffix.casefold() == '.mp4',
                'beeldvoorkeur': instellingen.beeldvoorkeur,
                'afbeelding': ('/afbeeldingen/' + instellingen.afbeelding_bestandsnaam)
                              if instellingen.afbeelding_bestandsnaam else None,
                'miniatuur': ('/afbeeldingen/' + instellingen.afbeelding_bestandsnaam.rsplit('.', 1)[0] + '.png')
                              if (instellingen.afbeelding_bestandsnaam
                                  and instellingen.afbeelding_bestandsnaam.lower().endswith('.gif')
                                  and (self._geef_beheerde_afbeeldingenmap() /
                                       (instellingen.afbeelding_bestandsnaam.rsplit('.', 1)[0] + '.png')).is_file())
                              else (('/afbeeldingen/' + instellingen.afbeelding_bestandsnaam)
                                    if instellingen.afbeelding_bestandsnaam
                                    and not instellingen.afbeelding_bestandsnaam.lower().endswith('.gif') else None),
            })
        return {'geluiden': resultaat, 'favorieten': favorieten,
                'groepen': self.groepen.geef_alle_groepen()}

    def _geef_beheerde_afbeeldingenmap(self) -> Path:
        """Voorkom een cirkelimport met de webserver bij het opzoeken van GIF-miniaturen."""
        import os
        basis = Path(os.environ.get('LOCALAPPDATA') or (Path.home() / '.drostsoundboard'))
        return basis / 'DrostSoundboard' / 'media' / 'afbeeldingen'

    def zoek_geluid_met_id(self, geluid_id: str):
        if not isinstance(geluid_id, str) or not geluid_id:
            raise OngeldigeWebactie('WEB-004: een geluidsnummer ontbreekt.')
        geluid = next((item for item in self.geluidenbibliotheek.geef_alle_geluiden()
                       if item.geluid_id == geluid_id), None)
        if geluid is None:
            raise OngeldigeWebactie('WEB-005: dit geluid bestaat niet meer in je bibliotheek.')
        return geluid

    def geef_preview_normalisatie(self, geluid_id: str, begin: float | None = None,
                                 duur: float | None = None, volume: float | None = None) -> dict[str, Any]:
        """Geef de browser de werkelijke versterking, zonder audio uit te zenden.

        We analyseren dezelfde audiokopie die de mixer ook zou voorbereiden.
        Alleen geselecteerde bibliotheekmedia, maximaal 120 s, nooit de mic.
        """
        item = self.zoek_geluid_met_id(geluid_id)
        instellingen = self.favorieten.geef_instellingen_van_geluid(geluid_id)
        begin = instellingen.begint_bij_seconden if begin is None else begin
        duur = instellingen.maximale_duur_seconden if duur is None else duur
        volume = instellingen.volume if volume is None else volume
        gekozen = controleer_afspeelinstellingen(begin, volume, duur)
        if not item.bestandspad.is_file():
            raise OngeldigeWebactie('NORM-004: het geselecteerde geluidsbestand ontbreekt.')
        informatie = item.bestandspad.stat()
        sleutel = (item.geluid_id, informatie.st_size, informatie.st_mtime_ns,
                  gekozen.begint_bij_seconden, gekozen.maximale_duur_seconden, gekozen.volume)
        with self._preview_analyse_lock:
            gevonden = self._preview_analyse_cache.get(sleutel)
        if gevonden is not None:
            return gevonden
        if not self._preview_analyse_slot.acquire(blocking=False):
            raise OngeldigeWebactie('NORM-005: een andere preview wordt voorbereid. Probeer het opnieuw.')
        try:
            with self._preview_analyse_lock:
                gevonden = self._preview_analyse_cache.get(sleutel)
            if gevonden is not None:
                return gevonden
            resultaat = bereken_browser_preview_versterkingen(
                item.bestandspad, begin=gekozen.begint_bij_seconden,
                duur=gekozen.maximale_duur_seconden, volume=gekozen.volume,
            )
            with self._preview_analyse_lock:
                if len(self._preview_analyse_cache) >= 8:
                    self._preview_analyse_cache.clear()
                self._preview_analyse_cache[sleutel] = resultaat
            return resultaat
        finally:
            self._preview_analyse_slot.release()

    def speel_geluid_uit_de_bibliotheek(self, geluid_id: str,
                                       tijdelijke_instellingen: dict | None = None) -> None:
        """Zend opgeslagen instellingen uit, of een tijdelijke editorselectie zonder opslag."""
        item = self.zoek_geluid_met_id(geluid_id)
        instellingen = self.favorieten.geef_instellingen_van_geluid(geluid_id)
        tijdelijk = tijdelijke_instellingen if tijdelijke_instellingen is not None else {}
        if not isinstance(tijdelijk, dict):
            raise OngeldigeWebactie('EDITOR-021: ongeldige tijdelijke fragmentinstellingen.')
        herhalen = tijdelijk.get('herhalen', False)
        if type(herhalen) is not bool:
            raise OngeldigeWebactie('SPELER-010: herhalen moet true of false zijn.')
        fragmentkeuze = {sleutel: waarde for sleutel, waarde in tijdelijk.items() if sleutel != 'herhalen'}
        if fragmentkeuze and set(fragmentkeuze) != {'beginpositie', 'maximale_duur', 'volume'}:
            raise OngeldigeWebactie('EDITOR-021: ongeldige tijdelijke fragmentinstellingen.')
        if fragmentkeuze:
            gekozen = controleer_afspeelinstellingen(fragmentkeuze['beginpositie'],
                        fragmentkeuze['volume'], fragmentkeuze['maximale_duur'])
            instellingen = replace(instellingen,
                begint_bij_seconden=gekozen.begint_bij_seconden,
                volume=gekozen.volume,
                maximale_duur_seconden=gekozen.maximale_duur_seconden)
        status = self.mixer.geef_huidige_status()
        if status.toestand != 'verbonden' or not status.geluidseffecten_aan:
            raise OngeldigeWebactie('WEB-006: maak verbinding en zet Soundboard aan.')
        normalisatiestand = self.favorieten.geef_normalisatiestand()
        if self.monitor.ingeschakeld:
            # De monitor is optioneel: bij headsetproblemen blijft de audio
            # voor de virtuele microfoon gewoon via VB-CABLE lopen.
            try:
                self.monitor.zorg_dat_monitor_kan_afspelen()
            except Exception:
                self.logboeken.softwarelogboek.exception('Meeluisteruitvoer kon niet worden gekozen', extra={
                    'gebeurtenis': 'monitor_kiezen_mislukt', 'gegevens': {'geluid_id': geluid_id}
                })
        with self._bescherm_toestand:
            if self._wordt_afgesloten:
                raise OngeldigeWebactie('WEB-081: DrostSoundboard wordt afgesloten.')
            self._controleer_computertest()
            self._volgnummer_van_voorbereiden += 1
            opdracht = self._volgnummer_van_voorbereiden
            self._wordt_voorbereid = item.eigen_naam
            self._laatste_afspeelfout = None
        schrijf_auditgebeurtenis(self.logboeken.auditlogboek, 'geluid_voorbereiden_aangevraagd', {
            'geluid_id': item.geluid_id,
            'naam': item.eigen_naam,
            'bestandsnaam': item.bestandspad.name,
            'startpositie': instellingen.begint_bij_seconden,
            'fragmentduur': instellingen.maximale_duur_seconden,
            'volume': instellingen.volume,
            'tijdelijke_editorselectie': bool(fragmentkeuze),
            'herhalen': herhalen,
            'normalisatiestand': normalisatiestand,
        })
        with self._bescherm_toestand:
            if opdracht != self._volgnummer_van_voorbereiden or self._wordt_afgesloten:
                # Een recentere klik of Stop heeft deze aanvraag vervangen.
                # Een vertraagde webdraad mag de nieuwste taak niet annuleren.
                return
            # De executor heeft bewust slechts één actieve werkdraad.
            # Annuleer een wachtende decode zodat spammen geen onbegrensde
            # wachtrij, geheugendruk of vertraagde geluiden veroorzaakt.
            if self._laatste_ingediende_decode is not None:
                self._laatste_ingediende_decode.cancel()
            self._laatste_ingediende_decode = self._werkdraad_voor_decoderen.submit(
                self._bereid_geluid_voor_en_start_als_het_nog_mag,
                opdracht, item, instellingen, normalisatiestand,
                **({'herhalen': True} if herhalen else {}),
            )

    def _bereid_geluid_voor_en_start_als_het_nog_mag(self, opdracht: int, item: Any, instellingen: Any,
                                                       normalisatiestand: str = 'uit', herhalen: bool = False) -> None:
        try:
            with self._bescherm_toestand:
                if opdracht != self._volgnummer_van_voorbereiden:
                    return
            voorbereid = lees_en_bereid_mp3_of_wav_voor(
                item.bestandspad,
                beginpositie_seconden=instellingen.begint_bij_seconden,
                ingesteld_volume=1.0,
                maximale_duur_seconden=instellingen.maximale_duur_seconden,
                normalisatiestand=normalisatiestand,
            )
            voorbereid = replace(voorbereid, naam_van_het_geluid=item.eigen_naam,
                                 ingesteld_volume=instellingen.volume)
            with self._bescherm_toestand:
                if opdracht != self._volgnummer_van_voorbereiden:
                    # Stop of de volgende kaart heeft deze opdracht ongeldig gemaakt.
                    schrijf_auditgebeurtenis(self.logboeken.auditlogboek, 'geluid_voorbereiden_geannuleerd', {
                        'naam': item.eigen_naam,
                        'reden': 'verouderde_of_gestopte_opdracht',
                    })
                    return
                status = self.mixer.geef_huidige_status()
                if status.toestand != 'verbonden' or not status.geluidseffecten_aan:
                    self._wordt_voorbereid = None
                    schrijf_auditgebeurtenis(self.logboeken.auditlogboek, 'geluid_geweigerd', {
                        'naam': item.eigen_naam,
                        'reden': 'audio_niet_meer_verbonden',
                    })
                    return
                afspeelbeurt_id = self.mixer.speel_een_voorbereid_geluid(
                    voorbereid, geluid_id=item.geluid_id, basisvolume=instellingen.volume,
                    **({'herhalen': True} if herhalen else {}))
                self._wordt_voorbereid = None
            # De gebruiker vroeg om afspelen. We registreren pas 'naar gesprek'
            # nadat de mixer de fragmentstart ook werkelijk heeft aanvaard.
            try:
                self.recent_en_weergave.registreer_afspelen(
                    item.geluid_id, item.eigen_naam, 'gesprek',
                    str(afspeelbeurt_id) if afspeelbeurt_id else None
                )
            except Exception:
                # Historie is nooit belangrijker dan hoorbaar geluid.
                self.logboeken.softwarelogboek.exception(
                    'Afspeelhistorie kon niet worden bewaard',
                    extra={'gebeurtenis': 'recente_afspeelbeurt_opslag_mislukt',
                           'gegevens': {'geluid_id': item.geluid_id}}
                )
            self.logboeken.softwarelogboek.info(
                'Geluid is aan de live-mixer aangeboden',
                extra={'gebeurtenis': 'web_geluid_aangeboden', 'gegevens': {
                    'naam': item.eigen_naam,
                    'afspeelbeurt_id': afspeelbeurt_id,
                    'gevraagde_duur': instellingen.maximale_duur_seconden,
                    'normalisatiestand': voorbereid.normalisatiestand,
                    'normalisatiefactor': round(voorbereid.normalisatiefactor, 4),
                }},
            )
        except Exception as fout:
            # De originele Python-traceback inclusief decoderfouten blijft bewaard.
            with self._bescherm_toestand:
                if opdracht == self._volgnummer_van_voorbereiden:
                    self._wordt_voorbereid = None
                    self._laatste_afspeelfout = str(fout)
            self.logboeken.softwarelogboek.exception(
                'Geluid voorbereiden of starten is mislukt',
                extra={'gebeurtenis': 'web_geluid_mislukt', 'gegevens': {
                    'foutcode': 'WEB-007', 'geluid_id': item.geluid_id,
                    'bestandsnaam': item.bestandspad.name,
                    'parameter_begint_bij_seconden': instellingen.begint_bij_seconden,
                    'parameter_volume': instellingen.volume,
                    'parameter_maximale_duur': instellingen.maximale_duur_seconden,
                }},
            )
            schrijf_auditgebeurtenis(self.logboeken.auditlogboek, 'geluid_voorbereiden_mislukt', {
                'geluid_id': item.geluid_id, 'fouttype': type(fout).__name__,
                'foutmelding': str(fout),
            })

    def stel_lopend_basisvolume_in(self, afspeelbeurt_id: str, geluid_id: str,
                                  percentage: int) -> int:
        """Een tijdelijke wijziging; opslaan blijft een afzonderlijke editoractie."""
        if type(percentage) is not int or not 0 <= percentage <= 200:
            raise OngeldigeWebactie('VOLUME-005: kies een basisvolume van 0 tot 200%.')
        if not isinstance(afspeelbeurt_id, str) or not isinstance(geluid_id, str):
            raise OngeldigeWebactie('SPELER-001: dit fragment speelt niet meer.')
        status = self.mixer.geef_huidige_status()
        if (status.toestand != 'verbonden' or status.afspeelbeurt_id != afspeelbeurt_id
                or status.huidig_geluid_id != geluid_id):
            raise OngeldigeWebactie('SPELER-001: dit fragment speelt niet meer.')
        if getattr(status, 'live_basisvolume', None) is None:
            raise OngeldigeWebactie('VOLUME-006: start dit fragment opnieuw om het volume aan te passen.')
        self.mixer.stel_lopend_basisvolume_in(afspeelbeurt_id, percentage / 100.0)
        return percentage

    def bedien_lopend_geluid(self, afspeelbeurt_id: str, *, fractie: float | None = None,
                             herhalen: bool | None = None) -> None:
        """Seek of loop het huidige fragment; een oude afspeelbeurt heeft geen invloed.

        De werkelijke wijziging gebeurt in de audio-callback, niet in HTTP.
        """
        status = self.mixer.geef_huidige_status()
        if status.toestand != 'verbonden' or status.afspeelbeurt_id != afspeelbeurt_id:
            raise OngeldigeWebactie('SPELER-001: dit fragment speelt niet meer.')
        if (fractie is None) == (herhalen is None):
            raise OngeldigeWebactie('SPELER-002: kies precies één speleractie.')
        if fractie is not None:
            if type(fractie) not in (int, float) or not math.isfinite(fractie) or not 0 <= fractie <= 1:
                raise OngeldigeWebactie('SPELER-003: kies een positie tussen 0 en 100%.')
            self.mixer.zoek_in_lopend_geluid(afspeelbeurt_id, fractie)
        else:
            if type(herhalen) is not bool:
                raise OngeldigeWebactie('SPELER-004: herhalen moet true of false zijn.')
            self.mixer.stel_lopend_geluid_herhalen_in(afspeelbeurt_id, herhalen)

    def stop_het_huidige_geluid(self) -> None:
        # Status vóór het stoppen ophalen. Na stoppen is het afspeelnummer weg,
        # en zou de geschiedenis niet meer kunnen vastleggen wat werd gestopt.
        status_voor_stop = self.mixer.geef_huidige_status()
        with self._bescherm_toestand:
            self._volgnummer_van_voorbereiden += 1
            of_bezig = self._wordt_voorbereid
            self._wordt_voorbereid = None
            if self._laatste_ingediende_decode is not None:
                self._laatste_ingediende_decode.cancel()
        if of_bezig:
            schrijf_auditgebeurtenis(self.logboeken.auditlogboek, 'geluid_voorbereiden_geannuleerd', {
                'naam': of_bezig, 'reden': 'handmatig_gestopt',
            })
        self.mixer.stop_het_huidige_geluid()
        if getattr(status_voor_stop, 'huidig_geluid_id', None):
            try:
                self.recent_en_weergave.registreer_afspeel_einde(
                    status_voor_stop.huidig_geluid_id, 'gesprek', 'handmatig',
                    min(120, max(0, status_voor_stop.afgespeelde_seconden or 0)),
                    str(status_voor_stop.afspeelbeurt_id) if status_voor_stop.afspeelbeurt_id else None,
                )
            except Exception:
                self.logboeken.softwarelogboek.exception(
                    'Stopreden kon niet in de geschiedenis worden opgeslagen',
                    extra={'gebeurtenis': 'recente_stop_opslag_mislukt'}
                )
        self.monitor.maak_monitorbuffer_leeg()
        schrijf_auditgebeurtenis(self.logboeken.auditlogboek, 'stop_geluid_aangevraagd')

    def sluit_alle_audio_af(self) -> bool:
        """Stop alle eigen audio, ook als een onderdeel bij opruimen een fout geeft."""
        with self._bescherm_toestand:
            self._wordt_afgesloten = True
            self._volgnummer_van_voorbereiden += 1
            self._wordt_voorbereid = None
        # Stop de mixer direct, niet pas nadat een eventuele previewfout is opgelost.
        # De monitor gaat dicht vóór het wachten op een lopende decoder.
        return sluit_onderdelen_af(self.logboeken.softwarelogboek, [
            ('natuurlijke stemmotor', self._sluit_natuurlijke_stem),
            ('stemvoorbeeld', self.stop_stemvoorbeeld),
            ('lopend soundboardgeluid', self.stop_het_huidige_geluid),
            ('microfoonverbinding', self.mixer.verbreek_de_verbinding),
            ('headsetmonitor', self.monitor.sluit_monitor),
            ('audiodriver', lambda: self.mixer.wacht_tot_verbinding_echt_weg_is(maximaal_seconden=6)),
            ('geluidsdecoder', lambda: self._werkdraad_voor_decoderen.shutdown(wait=True, cancel_futures=True)),
        ])
