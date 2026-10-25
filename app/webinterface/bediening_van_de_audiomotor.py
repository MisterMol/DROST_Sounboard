"""Vertaal eenvoudige webknoppen naar de bestaande veilige Python-audiomixer.

De webserver mag nooit in een PortAudio-callback werken. Lange MP3-bestanden
worden daarom in een losse werkdraad gedecodeerd. Een stopknop verhoogt het
opdrachtnummer: een verouderde decode kan daarna niets meer laten afspelen.
"""

from __future__ import annotations

from concurrent.futures import Future, ThreadPoolExecutor
from dataclasses import replace
import logging
from pathlib import Path
import time
import threading
from typing import Any

from app.audio.apparatenbeheer import controleer_werkelijk_aangesloten_audioapparaten
from app.audio.bronduur_en_golfvorm import (bepaal_werkelijke_bronduur, bepaal_werkelijke_fragmentduur,
                                             maak_gedetailleerde_golfvorm_voor_tijdsvenster, BronbestandNietLeesbaar)
from app.audio.geluidenbibliotheek import PersoonlijkeGeluidenbibliotheek
from app.audio.kabelcontrole import selecteer_de_twee_uiteinden_van_vb_cable
from app.audio.live_audiomixer import LiveAudiomixer
from app.audio.monitor_voor_eigen_headset import MonitorVoorEigenHeadset
from app.audio.mp3_en_wav_fragmenten import lees_en_bereid_mp3_of_wav_voor
from app.diagnostiek.logboek import BeschikbareLogboeken, schrijf_auditgebeurtenis
from app.webinterface.favorieten_en_instellingen import VasteFavorietenEnInstellingen
from app.webinterface.geluidsgroepen import PersoonlijkeGeluidsgroepen
from app.webinterface.extra_geluidsinformatie import BeheerVanExtraGeluidsinformatie
from app.webinterface.recente_geluiden_en_weergave import RecenteGeluidenEnWeergave


class OngeldigeWebactie(ValueError):
    """Foutcode voor webacties waarvoor geen geldige invoer is gevonden."""


class WebbedieningVanDrostSoundboard:
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
        self.mixer = LiveAudiomixer(
            audiobibliotheek, logboeken.softwarelogboek, logboeken.auditlogboek
        )
        self.monitor = MonitorVoorEigenHeadset(audiobibliotheek, logboeken.softwarelogboek)
        self.mixer.koppel_monitor_voor_effecten(
            self.monitor.ontvang_alleen_effectsamples, self.monitor.maak_monitorbuffer_leeg,
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

    def stel_meeluisteren_in(self, aan: bool, apparaatnummer: int | None = None) -> None:
        """Een kapotte headsetmonitor mag de verbinding met Discord niet verbreken."""
        if type(aan) is not bool:
            raise OngeldigeWebactie('WEB-040: meeluisteren moet true of false zijn.')
        if apparaatnummer is not None:
            geldige = {a['nummer'] for a in self.geef_uitvoerapparaten_voor_de_webpagina()}
            if type(apparaatnummer) is not int or apparaatnummer not in geldige:
                raise OngeldigeWebactie('WEB-041: kies een geldig headset-uitvoerapparaat.')
        self.monitor.kies_uitvoerapparaat(apparaatnummer)
        self.monitor.ingeschakeld = aan
        if not aan:
            self.monitor.sluit_monitor()
        schrijf_auditgebeurtenis(self.logboeken.auditlogboek, 'meeluisteren_ingesteld', {
            'ingeschakeld': aan, 'uitvoerapparaatnummer': apparaatnummer,
        })

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

    def verbind_met_microfoon(self, gekozen_nummer: int) -> None:
        """Herken steeds opnieuw, want een USB-herverbinding wijzigt apparaatnummers."""
        if type(gekozen_nummer) is not int:
            raise OngeldigeWebactie('WEB-001: kies een geldig microfoonnummer.')
        # Snelle dubbele klikken mogen geen tweede WASAPI-stream starten.
        # Het slot beschermt deze check én de opdracht aan de mixer.
        with self._bescherm_toestand:
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
            huidige_status = self.mixer.geef_huidige_status()
            if huidige_status.toestand in ('wordt_verbonden', 'verbonden'):
                return
            if huidige_status.toestand == 'wordt_verbroken':
                raise OngeldigeWebactie('WEB-080: wacht totdat de vorige verbinding is verbroken.')
            self.mixer.verbind_de_microfoon_met_vb_cable(kandidaten[0], kabel)

    def verbreek_de_verbinding(self) -> None:
        self.stop_het_huidige_geluid()
        self.mixer.verbreek_de_verbinding()
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

    def geef_huidige_webstatus(self) -> dict[str, Any]:
        status = self.mixer.geef_huidige_status()
        with self._bescherm_toestand:
            bezig = self._wordt_voorbereid
            afspeelfout = self._laatste_afspeelfout
        return {
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
            'callbacks': status.aantal_audio_callbacks,
            'fout': status.laatst_bekende_fout,
            'geluid_voorbereiden': bezig,
            'laatste_afspeelfout': afspeelfout,
            'huidig_geluid': getattr(status, 'huidig_geluid', None),
            'huidig_geluid_id': getattr(status, 'huidig_geluid_id', None),
            'afspeelbeurt_id': getattr(status, 'afspeelbeurt_id', None),
            'afgespeelde_seconden': getattr(status, 'afgespeelde_seconden', 0.0),
            'beginpositie_seconden': getattr(status, 'beginpositie_seconden', 0.0),
            'meeluisteren_aan': self.monitor.ingeschakeld,
            'meeluisteruitvoer': self.monitor.huidige_apparaatnaam,
            'meeluisterfout': self.monitor.laatste_fout,
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
        return {
            'gemeten': actief,
            'microfoon_rms': status.laatst_gemeten_microfoon_rms if actief else 0.0,
            'kabel_rms': status.laatst_gemeten_kabel_rms if actief else 0.0,
            'microfoon_piek': status.laatst_gemeten_microfoon_piek if actief else 0.0,
            'kabel_piek': status.laatst_gemeten_kabel_piek if actief else 0.0,
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
        for item in alle_geluiden:
            instellingen = self.favorieten.geef_instellingen_van_geluid(item.geluid_id)
            bronduur = self.geef_echte_duur_van_geluid(item)
            fragmentduur = bepaal_werkelijke_fragmentduur(
                bronduur, instellingen.begint_bij_seconden, instellingen.maximale_duur_seconden
            )
            resultaat.append({
                'id': item.geluid_id,
                'naam': item.eigen_naam,
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

    def speel_geluid_uit_de_bibliotheek(self, geluid_id: str) -> None:
        item = self.zoek_geluid_met_id(geluid_id)
        status = self.mixer.geef_huidige_status()
        if status.toestand != 'verbonden' or not status.geluidseffecten_aan:
            raise OngeldigeWebactie('WEB-006: maak verbinding en zet Soundboard aan.')
        instellingen = self.favorieten.geef_instellingen_van_geluid(geluid_id)
        if self.monitor.ingeschakeld:
            # De monitor is optioneel: bij headsetproblemen blijft de audio
            # voor de andere gespreksdeelnemers gewoon via VB-CABLE lopen.
            try:
                self.monitor.zorg_dat_monitor_kan_afspelen()
            except Exception:
                self.logboeken.softwarelogboek.exception('Meeluisteruitvoer kon niet worden gekozen', extra={
                    'gebeurtenis': 'monitor_kiezen_mislukt', 'gegevens': {'geluid_id': geluid_id}
                })
        with self._bescherm_toestand:
            if self._wordt_afgesloten:
                raise OngeldigeWebactie('WEB-081: DrostSoundboard wordt afgesloten.')
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
                opdracht, item, instellingen,
            )

    def _bereid_geluid_voor_en_start_als_het_nog_mag(self, opdracht: int, item: Any, instellingen: Any) -> None:
        try:
            with self._bescherm_toestand:
                if opdracht != self._volgnummer_van_voorbereiden:
                    return
            voorbereid = lees_en_bereid_mp3_of_wav_voor(
                item.bestandspad,
                beginpositie_seconden=instellingen.begint_bij_seconden,
                ingesteld_volume=instellingen.volume,
                maximale_duur_seconden=instellingen.maximale_duur_seconden,
            )
            voorbereid = replace(voorbereid, naam_van_het_geluid=item.eigen_naam)
            with self._bescherm_toestand:
                if opdracht != self._volgnummer_van_voorbereiden:
                    # Stop of de volgende kaart heeft deze opdracht ongeldig gemaakt.
                    schrijf_auditgebeurtenis(self.logboeken.auditlogboek, 'geluid_voorbereiden_geannuleerd', {
                        'naam': item.eigen_naam, 'reden': 'verouderde_of_gestopte_opdracht',
                    })
                    return
                status = self.mixer.geef_huidige_status()
                if status.toestand != 'verbonden' or not status.geluidseffecten_aan:
                    self._wordt_voorbereid = None
                    schrijf_auditgebeurtenis(self.logboeken.auditlogboek, 'geluid_geweigerd', {
                        'naam': item.eigen_naam, 'reden': 'audio_niet_meer_verbonden',
                    })
                    return
                afspeelbeurt_id = self.mixer.speel_een_voorbereid_geluid(voorbereid, geluid_id=item.geluid_id)
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
                    'naam': item.eigen_naam, 'afspeelbeurt_id': afspeelbeurt_id,
                    'gevraagde_duur': instellingen.maximale_duur_seconden,
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
        """Stop bij programma-afsluiting eerst geluid en geef PortAudio tijd om te sluiten."""
        with self._bescherm_toestand:
            self._wordt_afgesloten = True
        self.verbreek_de_verbinding()
        driver_afgesloten = self.mixer.wacht_tot_verbinding_echt_weg_is(maximaal_seconden=6)
        # Bij normaal sluiten kort lopende decode laten afronden zodat de
        # auditlogs niet na het afsluiten van de logbestanden geschreven worden.
        self._werkdraad_voor_decoderen.shutdown(wait=True, cancel_futures=True)
        self.monitor.sluit_monitor()
        return driver_afgesloten
