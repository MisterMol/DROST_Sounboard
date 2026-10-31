"""Eén gebruikerskeuze voor bestaande effecten en benoemde LLVC-varianten."""
from __future__ import annotations
from app.audio.natuurlijke_stem.varianten import OP_ID, controleer_variant


class StemKeuzeBediening:
    def migreer_vervallen_stemkeuze(self):
        """Vervang een opgeslagen leeftijdseffect voordat audio kan worden gestart.

        Kies eerst de modelroute. Bij laden of een modelstoring dempt die het
        microfoonsignaal. Schakel nooit alvast naar een onbewerkte microfoon.
        Een al gekozen modelvariant, ook wanneer die uitstaat, blijft behouden.
        """
        from app.audio.stemvervorming import VERVALLEN_STEMPROFIELEN
        with self._bescherm_toestand:
            self._stemkeuze_migratiemelding = ''
            if self.favorieten.geef_stemprofiel() not in VERVALLEN_STEMPROFIELEN:
                return
            dienst = self.natuurlijke_stem
            vervang_keuze = not dienst.gekozen
            if vervang_keuze:
                actief = self.favorieten.geef_stemvervormer_aan()
                # Deze stap slaat de modelkeuze op voordat de oude keuze verdwijnt.
                # Mislukt opslaan, dan blijft de oude opslag intact en stopt opstarten.
                if dienst.status().get('beschikbaar'):
                    dienst.kies_variant('llvc_basis', aan=bool(actief))
                else:
                    dienst.kies_gewone_effecten()
            self.favorieten.bewaar_stemvervormer_aan(False)
            self.mixer.stel_stemvervormer_aan_in(False)
            self.favorieten.bewaar_stemprofiel('normaal')
            self.mixer.stel_stemprofiel_in('normaal')
            self.stemvoorbeeld.stel_stemprofiel_in('normaal')
            if vervang_keuze:
                self._stemkeuze_migratiemelding = (
                    'Je eerder gekozen leeftijdseffect is verwijderd. Normale effecten zijn nu '
                    'geselecteerd. De aan/uitstand is behouden.')

    def _controleer_stemkeuze_actie(self):
        if self._wordt_afgesloten: raise ValueError('De app wordt afgesloten.')
        if self.natuurlijke_stem.status().get('test_bezig'):
            raise ValueError('Stop eerst de computertest voordat je een stem kiest.')

    def geef_stemkeuze(self):
        return self.geef_steminstellingen()

    def kies_stem(self, keuze):
        from app.audio.stemvervorming import controleer_kiesbaar_stemprofiel
        if not isinstance(keuze,str): raise ValueError('Kies een beschikbaar stemprofiel.')
        natuurlijk=keuze in OP_ID
        if natuurlijk:
            controleer_variant(keuze)
            if not self.natuurlijke_stem.status().get('beschikbaar'):
                raise ValueError('AI-stemmen zijn niet beschikbaar in de compacte versie.')
        else:controleer_kiesbaar_stemprofiel(keuze)
        with self._bescherm_toestand:
            self._controleer_stemkeuze_actie()
            self._stemkeuze_generatie += 1
            self.stemkeuze_voorbeelden.annuleer()
            dienst=self.natuurlijke_stem
            actief=dienst.aan if dienst.gekozen else self.favorieten.geef_stemvervormer_aan()
            if natuurlijk:
                if not actief and self.stemvoorbeeld.actief:
                    self.stop_stemvoorbeeld()
                # Eerst de modelroute activeren/muten, dan de oude effecten uitschakelen.
                dienst.kies_variant(keuze,aan=bool(actief))
                self.favorieten.bewaar_stemvervormer_aan(False)
                self.mixer.stel_stemvervormer_aan_in(False)
            else:
                # Bereid het nieuwe effect volledig voor terwijl LLVC nog eigenaar is.
                self.favorieten.bewaar_stemprofiel(keuze)
                self.mixer.stel_stemprofiel_in(keuze)
                self.stemvoorbeeld.stel_stemprofiel_in(keuze)
                self.favorieten.bewaar_stemvervormer_aan(bool(actief))
                self.mixer.stel_stemvervormer_aan_in(bool(actief))
                dienst.kies_gewone_effecten()
            self._stemkeuze_migratiemelding = ''
            return self.geef_steminstellingen()

    def schakel_stemkeuze(self, aan):
        if type(aan) is not bool: raise ValueError('Kies aan of uit voor de stemvervormer.')
        with self._bescherm_toestand:
            self._controleer_stemkeuze_actie()
            if self.natuurlijke_stem.gekozen:
                if aan:self.natuurlijke_stem.stel_in(True)
                self.favorieten.bewaar_stemvervormer_aan(False)
                self.mixer.stel_stemvervormer_aan_in(False)
                if not aan:self.natuurlijke_stem.stel_in(False)
            else:
                self.stel_stemvervormer_aan_in(aan)
            return self.geef_steminstellingen()

    def maak_stemkeuze_voorbeeld(self, spreker, keuze, verzoek):
        from app.audio.ingebouwde_stemvoorbeelden import render_voorbeeld
        from app.audio.natuurlijke_stem.voorbeeld import controleer_verzoek
        controleer_verzoek(verzoek)
        if spreker not in ('bob','elise'): raise ValueError('Kies Bob of Elise.')
        with self._bescherm_toestand:
            self._controleer_stemkeuze_actie()
            if self.stemvoorbeeld.actief:
                raise ValueError('Stop eerst je eigen microfoontest om Bob of Elise te beluisteren.')
            dienst=self.natuurlijke_stem
            huidige=dienst.variant if dienst.gekozen else self.favorieten.geef_stemprofiel()
            if keuze!=huidige: raise ValueError('De stemkeuze is gewijzigd. Start het voorbeeld opnieuw.')
            natuurlijk=dienst.gekozen
            parameters=self.favorieten.geef_stemparameters()
            generatie=self._stemkeuze_generatie
            if natuurlijk and dienst.status().get('toestand')=='laden':
                raise ValueError('De karakterstem wordt nog geladen. Probeer het voorbeeld zodra de stem gereed is.')
        # Geen toestandslot vasthouden tijdens modelwerk: stoppen en wisselen blijven mogelijk.
        if natuurlijk:
            def maak_bron():
                if not self._stemvoorbeeld_render_slot.acquire(timeout=1):
                    raise ValueError('Een voorbeeld wordt nog voorbereid. Probeer opnieuw.')
                try: return render_voorbeeld(spreker,'normaal',100,parameters)
                finally: self._stemvoorbeeld_render_slot.release()
            return self.stemkeuze_voorbeelden.render(
                maak_bron,keuze,verzoek,
                nog_geldig=lambda:not self._wordt_afgesloten and self._stemkeuze_generatie==generatie)
        return self.maak_voorbeeldstem_wav(spreker)

    def maak_stemkeuze_bron(self, spreker, verzoek):
        """Bob/Elise zonder stemvervorming; uitsluitend lokaal beluisteren."""
        from app.audio.ingebouwde_stemvoorbeelden import render_voorbeeld
        from app.audio.natuurlijke_stem.voorbeeld import controleer_verzoek, VoorbeeldGestopt
        from app.audio.natuurlijke_stem.voorbeeldaudio import lees_voorbeeld
        controleer_verzoek(verzoek)
        if spreker not in ('bob', 'elise'):
            raise ValueError('Kies Bob of Elise.')
        with self._bescherm_toestand:
            self._controleer_stemkeuze_actie()
            if self.stemvoorbeeld.actief:
                raise ValueError('Stop eerst je eigen microfoontest om Bob of Elise te beluisteren.')
            parameters = self.favorieten.geef_stemparameters()
            generatie = self._stemkeuze_generatie
        if not self._stemvoorbeeld_render_slot.acquire(timeout=1):
            raise ValueError('Een voorbeeld wordt nog voorbereid. Probeer opnieuw.')
        try:
            wav = render_voorbeeld(spreker, 'normaal', 100, parameters)
            lees_voorbeeld(wav)
            if self._wordt_afgesloten or generatie != self._stemkeuze_generatie:
                raise VoorbeeldGestopt('De stemkeuze is gewijzigd. Start het voorbeeld opnieuw.')
            return wav
        finally:
            self._stemvoorbeeld_render_slot.release()

    def stop_stemkeuze_voorbeeld(self, verzoek):
        self.stemkeuze_voorbeelden.annuleer(verzoek)
        return {'gestopt':True}
