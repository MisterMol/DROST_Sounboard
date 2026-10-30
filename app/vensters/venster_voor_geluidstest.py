"""Klein tijdelijk Windows-venster om echte WAV-fragmenten te testen.

Het uiteindelijke dashboard wordt HTML/CSS/JavaScript. Dit testvenster is
bewust los van de audiomotor gehouden zodat die code later gewoon blijft.
"""

from __future__ import annotations

import logging
from pathlib import Path
from queue import Empty, Queue
import threading
from typing import Any
from uuid import uuid4

from app.audio.apparatenbeheer import controleer_werkelijk_aangesloten_audioapparaten
from app.audio.geluid_afspelen import speel_voorbereid_geluid_naar_de_virtuele_kabel
from app.audio.geluidsbestanden import lees_en_bereid_wav_geluid_voor
from app.audio.kabelcontrole import selecteer_de_twee_uiteinden_van_vb_cable
from app.diagnostiek.logboek import BeschikbareLogboeken, schrijf_auditgebeurtenis


class VensterVoorWavGeluidstest:
    """Beheer knoppen en status zonder de GUI tijdens audio te blokkeren."""

    def __init__(self, venster: Any, tkinterbibliotheek: Any, logboeken: BeschikbareLogboeken):
        self.venster = venster
        self.tkinterbibliotheek = tkinterbibliotheek
        self.logboeken = logboeken
        self.bericht_uit_achtergrond: Queue[tuple[str, Any]] = Queue()
        self.gevraagd_om_te_stoppen = threading.Event()
        self.huidige_afspeeldraad: threading.Thread | None = None
        self.venster_wordt_gesloten = False

        voorbeeldpad = Path(__file__).resolve().parents[2] / "voorbeelden" / "voorbeeld_ping.wav"
        self.geselecteerd_bestand: Path | None = voorbeeldpad if voorbeeldpad.exists() else None

        self.venster.title("DrostSoundboard | WAV-test")
        self.venster.geometry("580x285")
        self.venster.minsize(540, 270)
        self.venster.resizable(True, False)
        self.venster.protocol("WM_DELETE_WINDOW", self.verzoek_om_het_venster_te_sluiten)

        self.naam_van_bestand_als_tekst = tkinterbibliotheek.StringVar(
            value=(self.geselecteerd_bestand.name if self.geselecteerd_bestand else "Nog geen WAV gekozen")
        )
        self.status_als_tekst = tkinterbibliotheek.StringVar(value="Klaar om een geluid te testen")

        inhoud = tkinterbibliotheek.Frame(venster, padx=24, pady=18)
        inhoud.pack(fill="both", expand=True)
        tkinterbibliotheek.Label(
            inhoud, text="WAV naar VB-CABLE", font=("Segoe UI", 18, "bold"), anchor="w"
        ).pack(fill="x")
        tkinterbibliotheek.Label(
            inhoud,
            text="Tijdelijk testvenster. De gewone microfoon wordt niet gebruikt.",
            anchor="w",
        ).pack(fill="x", pady=(4, 12))
        tkinterbibliotheek.Label(
            inhoud, textvariable=self.naam_van_bestand_als_tekst, anchor="w", font=("Segoe UI", 11)
        ).pack(fill="x", pady=(0, 8))

        rij_met_knoppen = tkinterbibliotheek.Frame(inhoud)
        rij_met_knoppen.pack(fill="x", pady=(4, 8))
        self.knop_voor_bestand = tkinterbibliotheek.Button(
            rij_met_knoppen, text="Kies WAV", width=14, command=self.kies_een_geluidsbestand
        )
        self.knop_voor_bestand.pack(side="left", padx=(0, 8))
        self.knop_voor_afspelen = tkinterbibliotheek.Button(
            rij_met_knoppen, text="Afspelen", width=14, command=self.start_afspelen_naar_kabel
        )
        self.knop_voor_afspelen.pack(side="left", padx=(0, 8))
        self.knop_voor_stoppen = tkinterbibliotheek.Button(
            rij_met_knoppen, text="Stop", width=10, command=self.stop_het_huidige_geluid,
            state="disabled",
        )
        self.knop_voor_stoppen.pack(side="left", padx=(0, 8))
        tkinterbibliotheek.Button(
            rij_met_knoppen, text="Sluiten", width=10, command=self.verzoek_om_het_venster_te_sluiten
        ).pack(side="left")

        tkinterbibliotheek.Label(
            inhoud, textvariable=self.status_als_tekst, anchor="w", wraplength=525,
            fg="#135b39",
        ).pack(fill="x", pady=(8, 6))
        tkinterbibliotheek.Label(
            inhoud,
            text=(
                "Uitvoer: CABLE Input (VB-Audio). Alleen WAV, maximaal 120 seconden. "
                "Standaardvolume: 35%."
            ),
            anchor="w", wraplength=525, fg="#565656", justify="left",
        ).pack(fill="x", pady=(4, 0))
        self.venster.after(100, self.verwerk_berichten_van_de_afspeeldraad)

    def kies_een_geluidsbestand(self) -> None:
        """Gebruik de Windows-bestandskiezer om paden overtypen te voorkomen."""
        from tkinter import filedialog

        startmap = self.geselecteerd_bestand.parent if self.geselecteerd_bestand else Path.home()
        gekozen_bestand = filedialog.askopenfilename(
            parent=self.venster,
            title="Kies een kort WAV-geluidsbestand",
            initialdir=str(startmap),
            filetypes=[("WAV-bestanden", "*.wav"), ("Alle bestanden", "*.*")],
        )
        if not gekozen_bestand:
            return
        self.geselecteerd_bestand = Path(gekozen_bestand)
        self.naam_van_bestand_als_tekst.set(self.geselecteerd_bestand.name)
        self.status_als_tekst.set("Bestand gekozen. Klik op Afspelen om via VB-CABLE te testen.")

    def start_afspelen_naar_kabel(self) -> None:
        """Start een achtergronddraad, zodat de Stop-knop bereikbaar blijft."""
        if self.huidige_afspeeldraad is not None and self.huidige_afspeeldraad.is_alive():
            return
        if self.geselecteerd_bestand is None:
            self.status_als_tekst.set("Kies eerst een WAV-bestand.")
            return

        self.gevraagd_om_te_stoppen = threading.Event()
        self.knop_voor_bestand.config(state="disabled")
        self.knop_voor_afspelen.config(state="disabled")
        self.knop_voor_stoppen.config(state="normal")
        self.status_als_tekst.set("Bestand wordt gecontroleerd en klaargemaakt...")
        bestand_voor_deze_afspeelbeurt = self.geselecteerd_bestand
        afspeelbeurt_id = str(uuid4())
        self.huidige_afspeeldraad = threading.Thread(
            target=self.voer_de_afspeelactie_uit_zonder_het_venster_te_blokkeren,
            args=(bestand_voor_deze_afspeelbeurt, afspeelbeurt_id, self.gevraagd_om_te_stoppen),
            name="WAV-afspeeldraad",
            daemon=True,
        )
        self.huidige_afspeeldraad.start()

    def voer_de_afspeelactie_uit_zonder_het_venster_te_blokkeren(
        self, gekozen_bestand: Path, afspeelbeurt_id: str, stopsignaal: threading.Event
    ) -> None:
        """Registreer ook mislukte voorbereidingen, niet alleen gespeelde geluiden."""
        huidige_actie = "bestand voorbereiden"
        schrijf_auditgebeurtenis(
            self.logboeken.auditlogboek,
            "afspeelverzoek_ontvangen",
            {"afspeelbeurt_id": afspeelbeurt_id, "bestandsnaam": gekozen_bestand.name},
        )
        try:
            voorbereid_geluid = lees_en_bereid_wav_geluid_voor(gekozen_bestand)
            if stopsignaal.is_set():
                schrijf_auditgebeurtenis(
                    self.logboeken.auditlogboek,
                    "afspeelverzoek_geannuleerd",
                    {"afspeelbeurt_id": afspeelbeurt_id, "reden": "gestopt_voor_audio"},
                )
                self.bericht_uit_achtergrond.put(("klaar", "Gestopt voordat audio is gestart."))
                return

            huidige_actie = "virtueel uitvoerapparaat opnieuw opzoeken"
            apparaatcontrole = controleer_werkelijk_aangesloten_audioapparaten(
                self.logboeken.softwarelogboek
            )
            geselecteerde_kabel = selecteer_de_twee_uiteinden_van_vb_cable(apparaatcontrole.apparaten)
            huidige_actie = "audio uitvoeren via VB-CABLE"
            import sounddevice as geluidsapparatenbibliotheek

            resultaat = speel_voorbereid_geluid_naar_de_virtuele_kabel(
                audiobibliotheek=geluidsapparatenbibliotheek,
                uitvoerapparaat=geselecteerde_kabel.afspeelkant,
                voorbereid_geluid=voorbereid_geluid,
                softwarelogboek=self.logboeken.softwarelogboek,
                auditlogboek=self.logboeken.auditlogboek,
                signaal_om_te_stoppen=stopsignaal,
                afspeelbeurt_id=afspeelbeurt_id,
                meld_dat_audio_echt_gestart_is=lambda: self.bericht_uit_achtergrond.put(
                    ("gestart", f"Afspelen via VB-CABLE: {voorbereid_geluid.naam_van_het_geluid}")
                ),
            )
            schrijf_auditgebeurtenis(
                self.logboeken.auditlogboek,
                "afspeelverzoek_afgerond",
                {"afspeelbeurt_id": afspeelbeurt_id, "resultaat": resultaat.resultaat},
            )
            if resultaat.resultaat == "volledig_aangeleverd":
                leesbare_uitkomst = (
                    f"Afgerond: {resultaat.aangeleverde_audio_in_seconden:.2f} sec "
                    f"doorgestuurd, {resultaat.aantal_bufferproblemen} bufferproblemen."
                )
            elif resultaat.resultaat in ("handmatig_gestopt", "voor_start_geannuleerd"):
                leesbare_uitkomst = "Afspelen gestopt. De rest van het geluid is niet verstuurd."
            else:
                leesbare_uitkomst = f"Afspeelbeurt beëindigd: {resultaat.resultaat}."
            self.bericht_uit_achtergrond.put(("klaar", leesbare_uitkomst))
        except Exception as oorspronkelijke_fout:
            # Log precies één volledige traceback aan de buitenrand. De lage
            # audiolagen bewaren hun oorspronkelijke oorzaak met 'raise from'.
            fouttekst = str(oorspronkelijke_fout)
            herkenbare_foutcode = fouttekst.split(":", 1)[0]
            if not (
                herkenbare_foutcode.startswith(("GELUID-", "AFSPELEN-", "KABEL-", "APPARAAT-"))
                and herkenbare_foutcode.split("-")[-1].isdigit()
            ):
                herkenbare_foutcode = "WAV-999"
            self.logboeken.softwarelogboek.exception(
                "Het afspeelverzoek is mislukt",
                extra={
                    "gebeurtenis": "afspeelverzoek_mislukt",
                    "gegevens": {
                        "foutcode": herkenbare_foutcode,
                        "afspeelbeurt_id": afspeelbeurt_id,
                        "bestand": gekozen_bestand.name,
                        "actie_bij_fout": huidige_actie,
                        "type_van_fout": type(oorspronkelijke_fout).__name__,
                        "hersteladvies": "Open software.jsonl en bekijk de volledige traceback",
                    },
                },
            )
            schrijf_auditgebeurtenis(
                self.logboeken.auditlogboek,
                "afspeelverzoek_mislukt",
                {
                    "afspeelbeurt_id": afspeelbeurt_id,
                    "bestandsnaam": gekozen_bestand.name,
                    "actie_bij_fout": huidige_actie,
                    "fouttype": type(oorspronkelijke_fout).__name__,
                },
            )
            self.bericht_uit_achtergrond.put(("fout", f"Niet gelukt: {oorspronkelijke_fout}"))

    def stop_het_huidige_geluid(self) -> None:
        """Een stopverzoek is veilig, ook als het bestand nog voorbereid wordt."""
        if self.huidige_afspeeldraad is not None and self.huidige_afspeeldraad.is_alive():
            self.gevraagd_om_te_stoppen.set()
            self.status_als_tekst.set("Stoppen is aangevraagd...")
            self.knop_voor_stoppen.config(state="disabled")

    def verwerk_berichten_van_de_afspeeldraad(self) -> None:
        """Alleen de GUI-draad wijzigt widgets; Tk is niet veilig vanuit audiodraden."""
        try:
            while True:
                berichtsoort, inhoud_van_bericht = self.bericht_uit_achtergrond.get_nowait()
                if not self.venster_wordt_gesloten:
                    self.status_als_tekst.set(str(inhoud_van_bericht))
                if berichtsoort in ("klaar", "fout"):
                    if not self.venster_wordt_gesloten:
                        self.knop_voor_bestand.config(state="normal")
                        self.knop_voor_afspelen.config(state="normal")
                        self.knop_voor_stoppen.config(state="disabled")
        except Empty:
            pass

        if self.venster_wordt_gesloten and (
            self.huidige_afspeeldraad is None or not self.huidige_afspeeldraad.is_alive()
        ):
            self.venster.destroy()
            return
        self.venster.after(100, self.verwerk_berichten_van_de_afspeeldraad)

    def verzoek_om_het_venster_te_sluiten(self) -> None:
        """Stop eerst de stream, want logboeken sluiten terwijl audio loopt is riskant."""
        self.venster_wordt_gesloten = True
        self.gevraagd_om_te_stoppen.set()
        self.status_als_tekst.set("Audiostream wordt gestopt. Venster sluit daarna.")
        self.knop_voor_bestand.config(state="disabled")
        self.knop_voor_afspelen.config(state="disabled")
        self.knop_voor_stoppen.config(state="disabled")
        if self.huidige_afspeeldraad is None or not self.huidige_afspeeldraad.is_alive():
            self.venster.destroy()
