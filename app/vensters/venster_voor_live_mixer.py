"""Tijdelijk eenvoudig scherm voor de echte microfoonmix.

De vensterlaag kiest apparaten en toont knoppen. Alle audio blijft in
app/audio/live_audiomixer.py, zodat later HTML de knoppen kan overnemen.
"""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path
from queue import Empty, SimpleQueue
import threading
import tkinter as tkinterbibliotheek
from tkinter import filedialog, messagebox, simpledialog, ttk
from typing import Any

from app.audio.apparatenbeheer import (
    GevondenAudioapparaat,
    controleer_werkelijk_aangesloten_audioapparaten,
)
from app.audio.geluidenbibliotheek import (
    GeluidInBibliotheek,
    PersoonlijkeGeluidenbibliotheek,
)
from app.audio.mp3_en_wav_fragmenten import lees_en_bereid_mp3_of_wav_voor
from app.audio.kabelcontrole import selecteer_de_twee_uiteinden_van_vb_cable
from app.audio.windows_standaardapparaten import vind_wasapi_standaardapparaat
from app.audio.live_audiomixer import LiveAudiomixer
from app.audio.signaaldiagnose import (
    maak_een_leesbaar_geluidsniveau,
    bereken_meterstand_op_schaal_van_honderd,
)
from app.diagnostiek.logboek import BeschikbareLogboeken, schrijf_auditgebeurtenis


class VensterVoorLiveMixer:
    """Een simpele bediening met twee duidelijke knoppen: verbinden en aan/uit."""

    def __init__(self, venster: Any, logboeken: BeschikbareLogboeken, audiobibliotheek: Any):
        self.venster = venster
        self.logboeken = logboeken
        self.audioapparaten = audiobibliotheek
        self.mixer = LiveAudiomixer(
            audiobibliotheek,
            logboeken.softwarelogboek,
            logboeken.auditlogboek,
        )
        self.venster_is_bezig_met_sluiten = False
        self.geluidenbibliotheek = PersoonlijkeGeluidenbibliotheek()
        self.bibliotheek_geluiden: list[GeluidInBibliotheek] = []
        self.geselecteerde_bibliotheek_geluid: GeluidInBibliotheek | None = None
        self.resultaten_van_audio_voorbereiden: SimpleQueue[tuple[int, object, BaseException | None]] = SimpleQueue()
        self._volgnummer_van_voorbereiden = 0
        self._geluid_wordt_voorbereid = False
        self._aantal_controles_tijdens_sluiten = 0
        self.geselecteerde_microfoons: dict[str, GevondenAudioapparaat] = {}
        self.gekozen_kabel: GevondenAudioapparaat | None = None
        self.gekozen_geluid: Path | None = (
            Path(__file__).resolve().parents[2] / "voorbeelden" / "controletoon_12seconden.wav"
        )

        self.huidige_verbindingstekst = tkinterbibliotheek.StringVar(value="Niet verbonden")
        self.korte_uitleg = tkinterbibliotheek.StringVar(
            value="Klik op Verbinden. Daarna blijft je microfoon via VB-CABLE doorlopen."
        )
        self.geselecteerde_microfoon_tekst = tkinterbibliotheek.StringVar(value="")
        self.geselecteerde_geluid_tekst = tkinterbibliotheek.StringVar(
            value=self.gekozen_geluid.name if self.gekozen_geluid.exists() else "Geen geluid gekozen"
        )
        self.effecten_ingeschakeld = tkinterbibliotheek.BooleanVar(value=False)
        self.startpositie_van_het_geluid = tkinterbibliotheek.StringVar(value="0")
        self.status_onderaan = tkinterbibliotheek.StringVar(value="Klaar om apparaten te zoeken")
        self._laatste_status = ""
        self.tekst_microfoonmeter = tkinterbibliotheek.StringVar(value="nog niet gemeten")
        self.tekst_kabelmeter = tkinterbibliotheek.StringVar(value="nog niet gemeten")
        self.tekst_audioactiviteit = tkinterbibliotheek.StringVar(
            value="Er is nog geen audiostream gestart."
        )

        venster.title("DrostSoundboard | Audiomixer")
        venster.geometry("740x640")
        venster.minsize(650, 480)
        venster.protocol("WM_DELETE_WINDOW", self.vraag_of_de_app_afgesloten_mag_worden)
        stijl = ttk.Style(venster)
        try:
            stijl.theme_use("clam")
        except tkinterbibliotheek.TclError:
            pass

        # Hoge schermschaling kan ervoor zorgen dat de knopstatus of meters
        # buiten het venster vallen. Daarom blijft de volledige diagnose
        # bereikbaar via een verticale schuifbalk op iedere Windows-pc.
        hoofdframe = ttk.Frame(venster)
        hoofdframe.pack(fill="both", expand=True)
        scrolbalk = ttk.Scrollbar(hoofdframe, orient="vertical")
        scrolbalk.pack(side="right", fill="y")
        schuifvenster = tkinterbibliotheek.Canvas(hoofdframe, highlightthickness=0)
        schuifvenster.pack(side="left", fill="both", expand=True)
        schuifvenster.configure(yscrollcommand=scrolbalk.set)
        scrolbalk.configure(command=schuifvenster.yview)
        inhoud = ttk.Frame(schuifvenster, padding=22)
        venster_op_canvas = schuifvenster.create_window((0, 0), window=inhoud, anchor="nw")
        inhoud.bind(
            "<Configure>",
            lambda gebeurtenis: schuifvenster.configure(
                scrollregion=schuifvenster.bbox("all")
            ),
        )
        schuifvenster.bind(
            "<Configure>",
            lambda gebeurtenis: schuifvenster.itemconfigure(
                venster_op_canvas, width=gebeurtenis.width
            ),
        )
        ttk.Label(inhoud, text="DrostSoundboard", font=("Segoe UI", 20, "bold")).pack(anchor="w")
        ttk.Label(inhoud, text="Live microfoon naar VB-CABLE, met optionele geluidseffecten").pack(
            anchor="w", pady=(2, 16)
        )
        ttk.Label(
            inhoud, textvariable=self.huidige_verbindingstekst,
            font=("Segoe UI", 14, "bold"), foreground="#17623c",
        ).pack(anchor="w")
        ttk.Label(inhoud, textvariable=self.korte_uitleg, wraplength=590).pack(
            anchor="w", pady=(4, 18)
        )

        ttk.Label(inhoud, text="Jouw microfoon:").pack(anchor="w")
        apparatenrij = ttk.Frame(inhoud)
        apparatenrij.pack(fill="x", pady=(4, 12))
        self.keuze_voor_microfoon = ttk.Combobox(
            apparatenrij, textvariable=self.geselecteerde_microfoon_tekst,
            state="readonly", width=51,
        )
        self.keuze_voor_microfoon.pack(side="left", fill="x", expand=True, padx=(0, 8))
        self.knop_ververs_apparaten = ttk.Button(
            apparatenrij, text="Vernieuwen", command=self.zoek_microfoons_opnieuw,
        )
        self.knop_ververs_apparaten.pack(side="left")

        verbindingsrij = ttk.Frame(inhoud)
        verbindingsrij.pack(fill="x", pady=(2, 14))
        self.knop_verbinden = ttk.Button(
            verbindingsrij, text="Verbinden", width=19, command=self.verbind_de_microfoon,
        )
        self.knop_verbinden.pack(side="left", padx=(0, 8))
        self.knop_verbreken = ttk.Button(
            verbindingsrij, text="Verbinding verbreken", width=22,
            command=self.verbreek_de_microfoonverbinding,
        )
        self.knop_verbreken.pack(side="left")

        ttk.Separator(inhoud).pack(fill="x", pady=8)
        self.schakelaar_voor_soundboard = ttk.Checkbutton(
            inhoud, text="Soundboard aan (microfoon blijft altijd aan)",
            variable=self.effecten_ingeschakeld,
            command=self.verander_de_stand_van_het_soundboard,
        )
        self.schakelaar_voor_soundboard.pack(anchor="w", pady=(8, 12))

        ttk.Label(inhoud, text="Mijn geluidsbibliotheek", font=("Segoe UI", 11, "bold")).pack(anchor="w")
        bibliotheekrij = ttk.Frame(inhoud)
        bibliotheekrij.pack(fill="x", pady=(4, 4))
        self.lijst_met_geluiden = tkinterbibliotheek.Listbox(
            bibliotheekrij, height=5, exportselection=False,
        )
        self.lijst_met_geluiden.pack(side="left", fill="both", expand=True)
        self.lijst_met_geluiden.bind("<<ListboxSelect>>", self._selecteer_geluid_uit_de_lijst)
        bibliotheekscroll = ttk.Scrollbar(
            bibliotheekrij, orient="vertical", command=self.lijst_met_geluiden.yview,
        )
        bibliotheekscroll.pack(side="right", fill="y")
        self.lijst_met_geluiden.configure(yscrollcommand=bibliotheekscroll.set)
        bibliotheekknoppen = ttk.Frame(inhoud)
        bibliotheekknoppen.pack(fill="x", pady=(0, 8))
        ttk.Button(
            bibliotheekknoppen, text="MP3/WAV toevoegen", command=self.importeer_meerdere_geluiden,
        ).pack(side="left", padx=(0, 8))
        ttk.Button(
            bibliotheekknoppen, text="Naam wijzigen", command=self.verander_de_naam_van_het_gekozen_geluid,
        ).pack(side="left", padx=(0, 8))
        ttk.Button(
            bibliotheekknoppen, text="Uit lijst halen", command=self.haal_het_gekozen_geluid_uit_de_lijst,
        ).pack(side="left")
        ttk.Label(inhoud, textvariable=self.geselecteerde_geluid_tekst).pack(anchor="w")
        startpositierij = ttk.Frame(inhoud)
        startpositierij.pack(fill="x", pady=(4, 6))
        ttk.Label(startpositierij, text="Begin bij seconde:").pack(side="left")
        ttk.Entry(
            startpositierij, width=9, textvariable=self.startpositie_van_het_geluid,
        ).pack(side="left", padx=(8, 12))
        ttk.Label(startpositierij, text="Speelt maximaal 120 seconden per klik.").pack(side="left")
        knoppen_voor_geluid = ttk.Frame(inhoud)
        knoppen_voor_geluid.pack(fill="x", pady=(5, 12))
        self.knop_kies_wav = ttk.Button(
            knoppen_voor_geluid, text="Kies MP3/WAV", command=self.kies_een_geluidsbestand,
        )
        self.knop_kies_wav.pack(side="left", padx=(0, 8))
        self.knop_speel_wav = ttk.Button(
            knoppen_voor_geluid, text="Geluid afspelen", command=self.speel_een_geluid_af,
        )
        self.knop_speel_wav.pack(side="left", padx=(0, 8))
        self.knop_stop_wav = ttk.Button(
            knoppen_voor_geluid, text="Stop geluid", command=self.stop_het_huidige_geluid,
        )
        self.knop_stop_wav.pack(side="left")

        # De oude UI liet alleen 'Verbonden' zien. Dat betekende in de code
        # slechts dat PortAudio startte, niet dat er spraak of WAV binnenkwam.
        # Twee aparte meters maken de plek waar audio wegvalt zichtbaar.
        diagnoseblok = ttk.LabelFrame(inhoud, text="Live signaalcontrole", padding=10)
        diagnoseblok.pack(fill="x", pady=(4, 10))

        ttk.Label(diagnoseblok, text="Geluid dat binnenkomt van je microfoon").pack(anchor="w")
        self.meter_van_microfoon = ttk.Progressbar(
            diagnoseblok, orient="horizontal", maximum=100, mode="determinate"
        )
        self.meter_van_microfoon.pack(fill="x", pady=(3, 1))
        ttk.Label(diagnoseblok, textvariable=self.tekst_microfoonmeter).pack(anchor="w")

        ttk.Label(diagnoseblok, text="Geluid dat Python naar CABLE Input stuurt").pack(
            anchor="w", pady=(9, 0)
        )
        self.meter_naar_kabel = ttk.Progressbar(
            diagnoseblok, orient="horizontal", maximum=100, mode="determinate"
        )
        self.meter_naar_kabel.pack(fill="x", pady=(3, 1))
        ttk.Label(diagnoseblok, textvariable=self.tekst_kabelmeter).pack(anchor="w")
        ttk.Label(diagnoseblok, textvariable=self.tekst_audioactiviteit, wraplength=650).pack(
            anchor="w", pady=(9, 0)
        )

        ttk.Label(
            inhoud,
            text=(
                "Soundboard aan speelt niet vanzelf een geluid. Klik ook op Geluid afspelen. "
                "Geluid gaat naar de virtuele microfoon; lokale weergave regel je apart."
            ),
            wraplength=650,
        ).pack(anchor="w", pady=(5, 5))
        ttk.Label(inhoud, textvariable=self.status_onderaan, wraplength=590).pack(
            anchor="w", pady=(5, 0)
        )
        self.zoek_microfoons_opnieuw()
        self.vernieuw_de_weergave_van_de_bibliotheek()
        self.venster.after(100, self.werk_de_status_van_het_venster_bij)

    def zoek_microfoons_opnieuw(self) -> None:
        """Zoek actuele Windows-apparaten op in plaats van vaste nummers te bewaren."""
        try:
            overzicht = controleer_werkelijk_aangesloten_audioapparaten(
                self.logboeken.softwarelogboek
            )
            self.gekozen_kabel = selecteer_de_twee_uiteinden_van_vb_cable(
                overzicht.apparaten
            ).afspeelkant
            mogelijke_microfoons = [
                apparaat for apparaat in overzicht.apparaten
                if apparaat.api_naam.casefold() == "windows wasapi"
                and apparaat.aantal_invoerkanalen > 0
                and "cable" not in apparaat.naam.casefold()
                and "vb-audio" not in apparaat.naam.casefold()
            ]
            if not mogelijke_microfoons:
                raise RuntimeError("VENSTER-002: geen fysieke WASAPI-microfoon gevonden.")
            self.geselecteerde_microfoons = {
                f"{apparaat.naam} (WASAPI {apparaat.huidig_apparaatnummer})": apparaat
                for apparaat in mogelijke_microfoons
            }
            namen_voor_keuzelijst = list(self.geselecteerde_microfoons)
            self.keuze_voor_microfoon["values"] = namen_voor_keuzelijst
            # Ook in het oude venster géén fabrikantvoorkeur: de Windows-standaard
            # krijgt voorrang, anders alleen automatisch kiezen bij precies één microfoon.
            gekozen = ''
            try:
                standaard = vind_wasapi_standaardapparaat(
                    self.audioapparaten.query_devices(), self.audioapparaten.query_hostapis(), 'invoer')
                if standaard:
                    nummer, naam = standaard
                    gekozen = next((sleutel for sleutel, apparaat in self.geselecteerde_microfoons.items()
                        if apparaat.huidig_apparaatnummer == nummer and apparaat.naam == naam), '')
            except Exception:
                # Een ontbrekende standaard is geen reden voor een willekeurige apparaatkeuze.
                pass
            if not gekozen and len(namen_voor_keuzelijst) == 1:
                gekozen = namen_voor_keuzelijst[0]
            self.geselecteerde_microfoon_tekst.set(gekozen)
            self.status_onderaan.set("Microfoon en virtuele kabel gevonden. Nog niet verbonden.")
            schrijf_auditgebeurtenis(
                self.logboeken.auditlogboek, "apparaten_opnieuw_gezocht",
                {"aantal_echte_microfoons": len(mogelijke_microfoons)},
            )
        except Exception as fout:
            self.logboeken.softwarelogboek.exception(
                "Audioapparaten opnieuw zoeken is mislukt",
                extra={"gebeurtenis": "apparaten_zoeken_mislukt", "gegevens": {"foutcode": "VENSTER-003"}},
            )
            self.status_onderaan.set(f"Apparaatfout: {fout}")
            messagebox.showerror("Audioapparaten", str(fout), parent=self.venster)

    def verbind_de_microfoon(self) -> None:
        """Vraag een stream aan, maar laat de GUI altijd bedienbaar blijven."""
        try:
            gekozen_microfoon = self.geselecteerde_microfoons.get(
                self.geselecteerde_microfoon_tekst.get()
            )
            if gekozen_microfoon is None or self.gekozen_kabel is None:
                raise RuntimeError("VENSTER-004: kies een bestaande microfoon en vernieuw de apparaten.")
            self.mixer.verbind_de_microfoon_met_vb_cable(gekozen_microfoon, self.gekozen_kabel)
            self.status_onderaan.set("Audioverbinding wordt gestart...")
        except Exception as fout:
            self._toon_fout_van_gebruikersactie("Microfoon verbinden", fout)

    def verbreek_de_microfoonverbinding(self) -> None:
        self.mixer.verbreek_de_verbinding()
        self.status_onderaan.set("Audioverbinding wordt afgesloten...")

    def verander_de_stand_van_het_soundboard(self) -> None:
        try:
            nieuwe_stand = self.effecten_ingeschakeld.get()
            self.mixer.zet_geluidseffecten_aan_of_uit(nieuwe_stand)
            self.status_onderaan.set(
                "Effecten worden aangezet." if nieuwe_stand else "Effecten worden uitgezet; stem blijft doorgaan."
            )
        except Exception as fout:
            self.effecten_ingeschakeld.set(False)
            self._toon_fout_van_gebruikersactie("Soundboard omschakelen", fout)

    def vernieuw_de_weergave_van_de_bibliotheek(self, te_selecteren_id: str | None = None) -> None:
        """Lees SQLite bij een gebruikersactie, nooit vanuit de audiocallback."""
        try:
            self.bibliotheek_geluiden = self.geluidenbibliotheek.geef_alle_geluiden()
            self.lijst_met_geluiden.delete(0, "end")
            for geluid in self.bibliotheek_geluiden:
                self.lijst_met_geluiden.insert(
                    "end", f"{geluid.eigen_naam} ({geluid.bestandspad.suffix[1:].upper()})"
                )
            if te_selecteren_id:
                for index, geluid in enumerate(self.bibliotheek_geluiden):
                    if geluid.geluid_id == te_selecteren_id:
                        self.lijst_met_geluiden.selection_set(index)
                        self.lijst_met_geluiden.see(index)
                        self._selecteer_geluid_uit_de_lijst()
                        break
        except Exception as fout:
            self._toon_fout_van_gebruikersactie("Bibliotheek vernieuwen", fout)

    def _selecteer_geluid_uit_de_lijst(self, gebeurtenis: Any = None) -> None:
        selectie = self.lijst_met_geluiden.curselection()
        if not selectie:
            return
        index = selectie[0]
        if index >= len(self.bibliotheek_geluiden):
            return
        item = self.bibliotheek_geluiden[index]
        self.geselecteerde_bibliotheek_geluid = item
        self.gekozen_geluid = item.bestandspad
        self.geselecteerde_geluid_tekst.set(f"Gekozen: {item.eigen_naam} ({item.bestandspad.name})")
        self.status_onderaan.set(f"Geselecteerd: {item.eigen_naam}")

    def importeer_meerdere_geluiden(self) -> None:
        """Bestanden blijven op hun plek, en krijgen een eigen naam in de database."""
        map_met_downloads = Path.home() / "Downloads"
        nieuwe_bestanden = filedialog.askopenfilenames(
            parent=self.venster,
            title="Selecteer één of meerdere MP3- of WAV-geluiden",
            initialdir=str(map_met_downloads if map_met_downloads.is_dir() else Path.home()),
            filetypes=[("Geluidsbestanden", "*.mp3 *.wav"), ("MP3", "*.mp3"), ("WAV", "*.wav")],
        )
        if not nieuwe_bestanden:
            return
        try:
            eerder = {item.geluid_id for item in self.geluidenbibliotheek.geef_alle_geluiden()}
            toegevoegd = self.geluidenbibliotheek.voeg_geluidsbestanden_toe(nieuwe_bestanden)
            echt_nieuw = [item for item in toegevoegd if item.geluid_id not in eerder]
            self.vernieuw_de_weergave_van_de_bibliotheek(toegevoegd[0].geluid_id)
            for item in echt_nieuw:
                schrijf_auditgebeurtenis(
                    self.logboeken.auditlogboek, "geluid_toegevoegd_aan_bibliotheek",
                    {"geluid_id": item.geluid_id, "naam": item.eigen_naam,
                     "bestandsnaam": item.bestandspad.name},
                )
            self.status_onderaan.set(
                f"{len(echt_nieuw)} nieuw(e) geluid(en) toegevoegd. "
                f"{len(toegevoegd) - len(echt_nieuw)} stonden al in je bibliotheek."
            )
        except Exception as fout:
            self._toon_fout_van_gebruikersactie("Geluiden importeren", fout)

    def verander_de_naam_van_het_gekozen_geluid(self) -> None:
        item = self.geselecteerde_bibliotheek_geluid
        if item is None:
            self.status_onderaan.set("Selecteer eerst een geluid in je bibliotheek.")
            return
        nieuwe_naam = simpledialog.askstring(
            "Naam van geluid veranderen", "Welke naam wil je dit geluid geven?",
            initialvalue=item.eigen_naam, parent=self.venster,
        )
        if nieuwe_naam is None:
            return
        try:
            self.geluidenbibliotheek.verander_de_naam_van_een_geluid(item.geluid_id, nieuwe_naam)
            self.vernieuw_de_weergave_van_de_bibliotheek(item.geluid_id)
            schrijf_auditgebeurtenis(
                self.logboeken.auditlogboek, "geluidsnaam_gewijzigd",
                {"geluid_id": item.geluid_id, "oude_naam": item.eigen_naam,
                 "nieuwe_naam": nieuwe_naam.strip()},
            )
        except Exception as fout:
            self._toon_fout_van_gebruikersactie("Geluidsnaam wijzigen", fout)

    def haal_het_gekozen_geluid_uit_de_lijst(self) -> None:
        item = self.geselecteerde_bibliotheek_geluid
        if item is None:
            self.status_onderaan.set("Selecteer eerst een geluid in je bibliotheek.")
            return
        if not messagebox.askyesno(
            "Geluid uit de lijst halen",
            f"'{item.eigen_naam}' uit de lijst halen? Het originele bestand blijft bewaard.",
            parent=self.venster,
        ):
            return
        try:
            self.geluidenbibliotheek.haal_geluid_uit_de_bibliotheek(item.geluid_id)
            schrijf_auditgebeurtenis(
                self.logboeken.auditlogboek, "geluid_uit_bibliotheek_gehaald",
                {"geluid_id": item.geluid_id, "naam": item.eigen_naam},
            )
            self.geselecteerde_bibliotheek_geluid = None
            self.gekozen_geluid = None
            self.geselecteerde_geluid_tekst.set("Kies een geluid uit je bibliotheek")
            self.vernieuw_de_weergave_van_de_bibliotheek()
        except Exception as fout:
            self._toon_fout_van_gebruikersactie("Geluid uit de lijst halen", fout)

    def kies_een_geluidsbestand(self) -> None:
        """Behoud de simpele knop naast de nieuwe bibliotheek voor een enkel bestand."""
        zelfgekozen = filedialog.askopenfilename(
            parent=self.venster,
            title="Kies een MP3- of WAV-geluid",
            initialdir=str(self.gekozen_geluid.parent if self.gekozen_geluid else Path.home()),
            filetypes=[("Geluidsbestanden", "*.mp3 *.wav"), ("MP3", "*.mp3"), ("WAV", "*.wav")],
        )
        if zelfgekozen:
            try:
                toegevoegd = self.geluidenbibliotheek.voeg_geluidsbestanden_toe([zelfgekozen])
                self.vernieuw_de_weergave_van_de_bibliotheek(toegevoegd[0].geluid_id)
            except Exception as fout:
                self._toon_fout_van_gebruikersactie("Geluid kiezen", fout)

    def speel_een_geluid_af(self) -> None:
        """Decodeer in een aparte draad zodat Windows-knoppen niet bevriezen."""
        if self._geluid_wordt_voorbereid:
            return
        try:
            if self.gekozen_geluid is None:
                raise RuntimeError("VENSTER-005: kies eerst een MP3- of WAV-bestand.")
            try:
                startpositie = float(self.startpositie_van_het_geluid.get().strip().replace(",", "."))
            except (ValueError, TypeError) as oorspronkelijke_fout:
                raise ValueError(
                    "VENSTER-006: vul bij Begin bij seconde een geldig getal in, bijvoorbeeld 0 of 25,5."
                ) from oorspronkelijke_fout
            gekozen_pad = self.gekozen_geluid
            gekozen_naam = (
                self.geselecteerde_bibliotheek_geluid.eigen_naam
                if self.geselecteerde_bibliotheek_geluid is not None else gekozen_pad.stem
            )
            self._volgnummer_van_voorbereiden += 1
            nummer = self._volgnummer_van_voorbereiden
            self._geluid_wordt_voorbereid = True
            schrijf_auditgebeurtenis(
                self.logboeken.auditlogboek, "geluid_voorbereiden_aangevraagd",
                {"naam": gekozen_naam, "bestandsnaam": gekozen_pad.name,
                 "startpositie_seconden": startpositie},
            )
            self.status_onderaan.set(f"{gekozen_naam} wordt voorbereid...")
            threading.Thread(
                target=self._bereid_geluid_op_achtergronddraad_voor,
                args=(nummer, gekozen_pad, gekozen_naam, startpositie),
                name="Geluid-voorbereiden", daemon=True,
            ).start()
        except Exception as fout:
            self._toon_fout_van_gebruikersactie("Geluid afspelen", fout)

    def _bereid_geluid_op_achtergronddraad_voor(
        self, nummer: int, pad: Path, naam: str, startpositie: float,
    ) -> None:
        """Alleen audiodata voorbereiden: geen Tk-widgets vanaf een werkdraad aanpassen."""
        try:
            resultaat = lees_en_bereid_mp3_of_wav_voor(pad, beginpositie_seconden=startpositie)
            resultaat = replace(resultaat, naam_van_het_geluid=naam)
            self.resultaten_van_audio_voorbereiden.put((nummer, resultaat, None))
        except Exception as fout:
            self.resultaten_van_audio_voorbereiden.put((nummer, None, fout))

    def _verwerk_voorbereide_geluiden_op_de_vensterdraad(self) -> None:
        """Handleer voltooiing en eventuele tracebacks veilig op de Tk-interfacedraad."""
        while True:
            try:
                nummer, voorbereid, fout = self.resultaten_van_audio_voorbereiden.get_nowait()
            except Empty:
                break
            if nummer != self._volgnummer_van_voorbereiden or self.venster_is_bezig_met_sluiten:
                # Een eerdere decode mag niet alsnog beginnen na een stopactie.
                continue
            self._geluid_wordt_voorbereid = False
            if fout is not None:
                schrijf_auditgebeurtenis(
                    self.logboeken.auditlogboek, "geluid_voorbereiden_mislukt",
                    {"fouttype": type(fout).__name__, "foutmelding": str(fout)},
                )
                self._toon_fout_van_gebruikersactie("Geluid voorbereiden", fout)
                continue
            try:
                afspeelbeurt_id = self.mixer.speel_een_voorbereid_geluid(voorbereid)
                melding = f"Afspeelverzoek verstuurd: {voorbereid.naam_van_het_geluid}, beurt {afspeelbeurt_id[:8]}."
                if voorbereid.fragment_ingekort:
                    melding += " Er wordt maximaal 120 seconden afgespeeld."
                self.status_onderaan.set(melding)
            except Exception as actie_fout:
                self._toon_fout_van_gebruikersactie("Geluid afspelen", actie_fout)

    def stop_het_huidige_geluid(self) -> None:
        if self._geluid_wordt_voorbereid:
            schrijf_auditgebeurtenis(
                self.logboeken.auditlogboek, "geluid_voorbereiden_geannuleerd",
                {"reden": "handmatig_gestopt_voordat_decoderen_klaar_was"},
            )
        self._volgnummer_van_voorbereiden += 1
        self._geluid_wordt_voorbereid = False
        self.mixer.stop_het_huidige_geluid()
        self.status_onderaan.set("Stop aangevraagd. De microfoon blijft doorgaan.")

    def _toon_fout_van_gebruikersactie(self, actie: str, fout: BaseException) -> None:
        """Toon een korte melding, maar bewaar de volledige traceback in de logs."""
        self.logboeken.softwarelogboek.error(
            "%s is mislukt", actie,
            exc_info=(type(fout), fout, fout.__traceback__),
            extra={
                "gebeurtenis": "gebruikersactie_mislukt",
                "gegevens": {"foutcode": "VENSTER-999", "actie_bij_fout": actie},
            },
        )
        self.status_onderaan.set(f"{actie}: {fout}")
        messagebox.showerror(actie, str(fout), parent=self.venster)

    def werk_de_status_van_het_venster_bij(self) -> None:
        """Lees hooguit tien keer per seconde status uit, niet in een audiocallback."""
        if self.venster_is_bezig_met_sluiten:
            self._controleer_of_we_veilig_kunnen_sluiten()
            return
        self._verwerk_voorbereide_geluiden_op_de_vensterdraad()
        status = self.mixer.geef_huidige_status()
        if status.toestand == "verbonden":
            zichtbaar = (
                "Verbonden, geluidseffecten aan" if status.geluidseffecten_aan
                else "Verbonden, alleen microfoon"
            )
            uitleg = "De gekozen microfoon wordt continu naar de virtuele microfoon gestuurd."
        elif status.toestand == "wordt_verbonden":
            zichtbaar = "Verbinding wordt gemaakt..."
            if status.huidige_startpoging > 0:
                uitleg = (
                    f"Windows-audio starten, poging {status.huidige_startpoging} "
                    f"van maximaal {status.maximale_startpogingen}. "
                    "Tijdelijke driverproblemen worden automatisch hersteld."
                )
            else:
                uitleg = "Apparaatinstellingen worden gecontroleerd."
        elif status.toestand == "wordt_verbroken":
            zichtbaar = "Verbinding wordt afgesloten..."
            uitleg = "De virtuele microfoon kan zo meteen stil worden in andere programma’s."
        elif status.toestand == "fout":
            zichtbaar = "Verbindingsfout"
            uitleg = f"{status.laatst_bekende_fout}. Zie software.jsonl voor de traceback."
        else:
            zichtbaar = "Niet verbonden"
            uitleg = "Klik op Verbinden. Het soundboard begint standaard uitgeschakeld."
        self.huidige_verbindingstekst.set(zichtbaar)
        self.korte_uitleg.set(uitleg)
        # Toon echte niveaus uit de audiocallback, niet alleen de verbindingsstatus.
        self.meter_van_microfoon["value"] = bereken_meterstand_op_schaal_van_honderd(
            status.laatst_gemeten_microfoon_rms, status.is_signaal_gemeten
        ) if status.toestand == "verbonden" else 0
        self.meter_naar_kabel["value"] = bereken_meterstand_op_schaal_van_honderd(
            status.laatst_gemeten_kabel_rms, status.is_signaal_gemeten
        ) if status.toestand == "verbonden" else 0
        self.tekst_microfoonmeter.set(
            maak_een_leesbaar_geluidsniveau(
                status.laatst_gemeten_microfoon_rms, status.is_signaal_gemeten
            ) if status.toestand == "verbonden" else "nog niet gemeten"
        )
        self.tekst_kabelmeter.set(
            maak_een_leesbaar_geluidsniveau(
                status.laatst_gemeten_kabel_rms, status.is_signaal_gemeten
            ) if status.toestand == "verbonden" else "nog niet gemeten"
        )
        if status.toestand == "verbonden":
            ouderdom = status.seconden_sinds_laatste_callback
            if status.aantal_audio_callbacks == 0:
                self.tekst_audioactiviteit.set(
                    "Verbonden, maar er zijn nog geen audioblokken ontvangen."
                )
            elif ouderdom is not None and ouderdom > 1.0:
                self.tekst_audioactiviteit.set(
                    f"WAARSCHUWING: laatste audioblok {ouderdom:.1f} s geleden. "
                    "Controleer straks software.jsonl."
                )
            else:
                self.tekst_audioactiviteit.set(
                    f"Callbacks: {status.aantal_audio_callbacks} | "
                    f"Frames: {status.aantal_aangeleverde_frames} | "
                    f"Bufferproblemen: {status.aantal_bufferproblemen}"
                )
        elif status.toestand == "fout":
            self.tekst_audioactiviteit.set(
                "De audiodriver meldt een fout. Zie software.jsonl voor de volledige traceback."
            )
        else:
            self.tekst_audioactiviteit.set("Geen actieve audiometing.")

        if status.toestand != self._laatste_status:
            if status.toestand == "fout":
                self.status_onderaan.set(
                    f"De verbinding werkt niet: {status.laatst_bekende_fout}"
                )
            self._laatste_status = status.toestand
        actief = status.toestand == "verbonden"
        bezet = status.toestand in ("wordt_verbonden", "wordt_verbroken")
        self.knop_verbinden.config(state="disabled" if actief or bezet else "normal")
        self.knop_verbreken.config(state="normal" if actief or bezet else "disabled")
        self.keuze_voor_microfoon.config(state="disabled" if actief or bezet else "readonly")
        self.knop_ververs_apparaten.config(state="disabled" if actief or bezet else "normal")
        self.schakelaar_voor_soundboard.config(state="normal" if actief else "disabled")
        self.knop_speel_wav.config(
            state="normal" if actief and status.geluidseffecten_aan and not self._geluid_wordt_voorbereid else "disabled"
        )
        self.knop_stop_wav.config(state="normal" if actief else "disabled")
        if not actief:
            self.effecten_ingeschakeld.set(False)
        self.venster.after(100, self.werk_de_status_van_het_venster_bij)

    def vraag_of_de_app_afgesloten_mag_worden(self) -> None:
        """Laat expliciet zien dat VB-CABLE na afsluiten geen stem meer krijgt."""
        toestand = self.mixer.geef_huidige_status().toestand
        if toestand in ("verbonden", "wordt_verbonden", "wordt_verbroken"):
            bevestiging = messagebox.askyesno(
                "DrostSoundboard afsluiten",
                "Programma’s die de virtuele microfoon gebruiken ontvangen na het afsluiten "
                "geen geluid meer. Wil je de verbinding verbreken en afsluiten?",
                parent=self.venster,
            )
            if not bevestiging:
                return
        self.venster_is_bezig_met_sluiten = True
        self._volgnummer_van_voorbereiden += 1
        self.mixer.verbreek_de_verbinding()
        self._controleer_of_we_veilig_kunnen_sluiten()

    def _controleer_of_we_veilig_kunnen_sluiten(self) -> None:
        if self.mixer.wacht_tot_verbinding_echt_weg_is(maximaal_seconden=0.0):
            self.venster.destroy()
            return
        self._aantal_controles_tijdens_sluiten += 1
        if self._aantal_controles_tijdens_sluiten >= 100:
            # Niet netjes weggaan terwijl een achtergrondthread nog logregels
            # kan produceren. Een vastgelopen audio-driver moet zichtbaar zijn.
            self.venster_is_bezig_met_sluiten = False
            self._aantal_controles_tijdens_sluiten = 0
            messagebox.showerror(
                "Afsluiten duurt te lang",
                "Windows heeft de audioverbinding nog niet losgelaten. "
                "Open de logmap en probeer Verbinding verbreken opnieuw.",
                parent=self.venster,
            )
            self.venster.after(100, self.werk_de_status_van_het_venster_bij)
            return
        self.venster.after(100, self._controleer_of_we_veilig_kunnen_sluiten)
