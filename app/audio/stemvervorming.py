"""Lichte, instelbare stemprofielen voor live-audio en lokale preview.

Er wordt niets opgenomen, opgeslagen of naar een extern netwerk gestuurd.
Stateful filters en vertragingsbuffers leven uitsluitend in de audiocallback.
"""
from __future__ import annotations

import math
import numpy as np
from app.audio.stemparameters import standaard_parameters, controleer_parameters
from app.audio.signalsmith_motor import SignalsmithMotor

SAMPLEFREQUENTIE = 48000

# Eén catalogus voor DSP, API en interface. Bestaande profielen starten op hun
# eerdere, hoorbaar bekende sterkte. Elk profiel heeft zijn eigen standaardwaarde.
PROFIEL_CATALOGUS = (
    ('normaal', 'Normaal', 'Onbewerkte microfoon', 'mic', 100),
    ('monsterkoor', 'Monsterkoor', 'Lage klank met zwevende stemlagen', 'monsterkoor', 85),
    ('ruimtepak', 'Ruimtepak', 'Communicatiestem met een metalen rand', 'ruimtepak', 80),
    ('spook', 'Spook', 'Lichtere klank, zweving en korte echo', 'spook', 75),
    ('retrocomputer', 'Retrocomputer', 'Digitale korrel met een robotachtige klank', 'retrocomputer', 80),
    ('radio', 'Radio', 'Radioklank met beperkt frequentiebereik', 'radio', 100),
    ('robot', 'Robot', 'Elektronisch en ritmisch', 'bot', 100),
    ('diep', 'Diepe stem', 'Een paar tonen lager', 'arrow-down', 100),
    ('heel_diep', 'Heel lage stem', 'Extra zwaar en laag', 'chevrons-down', 90),
    ('hoog', 'Hoge stem', 'Lichter en hoger', 'arrow-up', 80),
    ('heel_hoog', 'Heel hoge stem', 'Heliumachtige hoge stem', 'chevrons-up', 90),
    ('alien', 'Alien', 'Buitenaardse, trillende klank', 'orbit', 75),
    ('telefoon', 'Telefoon', 'Smalle, ouderwetse telefoonklank', 'phone', 80),
    ('monster', 'Monster', 'Laag en vervormd', 'skull', 80),
    ('echo', 'Echo', 'Korte echo achter je stem', 'waves', 60),
    ('megafoon', 'Megafoon', 'Scherp en krachtig', 'megaphone', 65),
    ('jongen', 'Jongensstem', 'Hoger stijleffect, geen natuurlijke kinderstem', 'smile', 85),
    ('meisje', 'Meisjesstem', 'Lichter stijleffect, geen natuurlijke kinderstem', 'sparkles', 85),
    ('oudeman', 'Oudere man', 'Laag karaktereffect, geen getrainde ouderdomsstem', 'user-round', 80),
    ('oudevrouw', 'Oudere vrouw', 'Ruw karaktereffect, geen getrainde ouderdomsstem', 'flower', 80),
    ('xbox2010', 'Xbox-lobby 2010', 'Goedkope headset met smal geluid en digitale korrel', 'gamepad', 85),
    ('autotune', 'Stoorzender', 'Haperend digitaal radiosignaal met ruis en vervorming', 'radio-tower', 100),
)
# De vier oude DSP-profielen blijven alleen intern leesbaar voor bestaande
# instellingen en terugzetten. Ze worden niet meer als stemkeuze aangeboden.
VERVALLEN_STEMPROFIELEN = frozenset(('jongen', 'meisje', 'oudeman', 'oudevrouw'))
PROFIELEN = tuple(item[0] for item in PROFIEL_CATALOGUS)
STANDAARD_INTENSITEITEN = {item[0]: item[4] for item in PROFIEL_CATALOGUS}


def controleer_stemprofiel(profiel: str) -> str:
    if type(profiel) is not str or profiel not in PROFIELEN:
        raise ValueError('STEM-001: onbekend stemprofiel; kies een beschikbaar profiel.')
    return profiel


def controleer_kiesbaar_stemprofiel(profiel: str) -> str:
    """Valideer een nieuwe keuze; oude opgeslagen profielen worden apart gemigreerd."""
    profiel = controleer_stemprofiel(profiel)
    if profiel in VERVALLEN_STEMPROFIELEN:
        raise ValueError('Dit leeftijdseffect is verwijderd. Kies een beschikbare stem.')
    return profiel


def controleer_stemintensiteit(intensiteit: int) -> int:
    """Intensiteit is een geheel getal tussen 0 en 100, geen bool of float."""
    if type(intensiteit) is not int or not 0 <= intensiteit <= 100:
        raise ValueError('STEM-030: intensiteit moet een geheel getal van 0 tot 100 zijn.')
    return intensiteit


def profiel_catalogus_voor_api() -> list[dict[str, object]]:
    return [dict(id=identiteit, naam=naam, beschrijving=beschrijving,
                 icoon=icoon, standaard_intensiteit=intensiteit)
            for identiteit, naam, beschrijving, icoon, intensiteit in PROFIEL_CATALOGUS
            if identiteit not in VERVALLEN_STEMPROFIELEN]


class Stemvervormer:
    """Draagt filter-, modulatie- en toonhoogtetoestand tussen audioblokken.

    Toonhoogte en resonantie gebruiken een blijvende Signalsmith-motor.
    De leeftijdsprofielen blijven stijleffecten, geen neurale stemconversie.
    Alle updates van profiel/intensiteit gebeuren in dezelfde audiothread.
    """

    def __init__(self, profiel: str = 'normaal', samplefrequentie: int = SAMPLEFREQUENTIE,
                 intensiteit: int | None = None, parameters: dict | None = None):
        if type(samplefrequentie) is not int or samplefrequentie < 16000:
            raise ValueError('STEM-002: ongeldige samplefrequentie.')
        controleer_stemprofiel(profiel)
        self.samplefrequentie = samplefrequentie
        self._native = None
        self._native_fout = None
        self._werd_verwerkt = False
        try:
            self._native = SignalsmithMotor(samplefrequentie)
        except Exception as fout:
            # Normale microfoon en soundboard blijven bruikbaar. Een effect dat
            # de nieuwe motor nodig heeft wordt niet stilletjes oud uitgevoerd.
            self._native_fout = fout
        self._hp_vorige_in = np.zeros(2, dtype=np.float64)
        self._hp_vorige_uit = np.zeros(2, dtype=np.float64)
        self._lp_vorige_uit = np.zeros(2, dtype=np.float64)
        self._modulatie_frames = 0
        self._pitch_buf = np.zeros((16384, 2), dtype=np.float32)
        self._pitch_frames = 0
        self._pitch_fase = 0.0
        self._pitch_huidige_factor = 1.0
        self._pitch_overgang = 0
        self._kleur_laag = np.zeros(2, dtype=np.float64)
        self._echo_buf = np.zeros((131072, 2), dtype=np.float32)
        self._echo_frames = 0
        self._stoorzender_frames = 0
        self._stoorzender_laatste = np.zeros(2, dtype=np.float32)
        self._effect_parameters = standaard_parameters()
        self._bron_parameters_ref = None
        if parameters:
            self.stel_effectparameters_in(parameters)
        self.profiel = 'normaal'
        self.intensiteit = 100
        self.kies_profiel(profiel)
        self.stel_intensiteit_in(STANDAARD_INTENSITEITEN[profiel] if intensiteit is None else intensiteit)

    def kies_profiel(self, profiel: str) -> None:
        profiel = controleer_stemprofiel(profiel)
        if profiel == self.profiel:
            return
        self.profiel = profiel
        self.herstel_audiobuffers()
        self.intensiteit = STANDAARD_INTENSITEITEN[profiel]

    def herstel_audiobuffers(self) -> None:
        """Wis oude stemaudio bij wisselen, uitschakelen of opnieuw inschakelen."""
        self._hp_vorige_in.fill(0)
        self._hp_vorige_uit.fill(0)
        self._lp_vorige_uit.fill(0)
        self._modulatie_frames = 0
        self._pitch_buf.fill(0)
        self._pitch_frames = 0
        self._pitch_fase = 0.0
        self._pitch_huidige_factor = 1.0
        self._pitch_overgang = 0
        self._kleur_laag.fill(0)
        self._echo_buf.fill(0)
        self._echo_frames = 0
        self._stoorzender_frames = 0
        self._stoorzender_laatste.fill(0)
        if self._native is not None:
            self._native.reset()
        self._werd_verwerkt = False

    def _nieuwe_motor(self):
        if self._native is None:
            raise RuntimeError('STEM-090: De stemmotor is niet beschikbaar. Installeer de stempatch opnieuw.') from self._native_fout
        return self._native

    def stel_intensiteit_in(self, intensiteit: int) -> None:
        self.intensiteit = controleer_stemintensiteit(intensiteit)

    def stel_effectparameters_in(self, instellingen: dict[str, dict]) -> None:
        # Nieuwe snapshots worden buiten de audiocallback gevalideerd.
        if type(instellingen) is not dict or set(instellingen) != set(self._effect_parameters):
            raise ValueError('STEM-053: onvolledige effectinstellingen.')
        nieuw = {p: controleer_parameters(p, params) for p, params in instellingen.items()}
        self._effect_parameters = nieuw
        self._bron_parameters_ref = instellingen

    def neem_gecontroleerde_parameters_over(self, snapshot: dict[str, dict]) -> None:
        """Neem een eerder gevalideerde, onveranderlijk gebruikte snapshot over.

        Wordt uitsluitend vanuit de audiocallback gebruikt. Validatie en opslag
        gebeuren in de bedieningsdraad, niet in het realtime gedeelte.
        """
        self._effect_parameters = snapshot
        self._bron_parameters_ref = snapshot

    def verwerk(self, invoer: np.ndarray) -> np.ndarray:
        """Verwerk mono/stereo float32, zonder de originele samples te veranderen."""
        if (not isinstance(invoer, np.ndarray) or invoer.ndim != 2
                or invoer.shape[1] not in (1, 2) or invoer.dtype != np.float32):
            raise ValueError('STEM-003: verwacht mono/stereo float32-microfoonframes.')
        if not np.isfinite(invoer).all():
            raise ValueError('STEM-004: ongeldige microfoonsamples.')
        if len(invoer) == 0:
            return invoer
        if self.profiel == 'normaal' or self.intensiteit == 0:
            if self._werd_verwerkt:
                self.herstel_audiobuffers()
            return invoer
        self._werd_verwerkt = True
        sterkte = self.intensiteit / 100.0
        profiel = self.profiel
        if profiel in ('monsterkoor', 'ruimtepak', 'spook', 'retrocomputer'):
            return self._nieuw_effect(invoer, sterkte)
        if profiel in ('radio', 'telefoon', 'xbox2010'):
            verwerkt = self._bandfilter(invoer, telefoon=profiel != 'radio')
            if profiel == 'xbox2010':
                # Smalle headset, lage digitale resolutie en licht vervormde pieken.
                korrel = np.round(verwerkt * 13.0) / 13.0
                verwerkt = (np.tanh(korrel * 2.7) * .68).astype(np.float32)
            return np.asarray(invoer * (1.0 - sterkte) + verwerkt * sterkte, dtype=np.float32)
        if profiel in ('robot', 'alien'):
            n = len(invoer)
            hz = 48.0 if profiel == 'robot' else 73.0
            fase = (self._modulatie_frames + np.arange(n, dtype=np.float64)) * (2.0 * math.pi * hz / self.samplefrequentie)
            self._modulatie_frames = (self._modulatie_frames + n) % self.samplefrequentie
            modulatie = (0.15 + 0.78 * np.sin(fase)) if profiel == 'robot' else (0.53 + 0.42 * np.sin(fase + 0.7 * np.sin(fase * 0.16)))
            return np.asarray(invoer * (1.0 - sterkte + sterkte * modulatie[:, None]), dtype=np.float32)
        if profiel in ('diep', 'heel_diep', 'hoog', 'heel_hoog', 'monster',
                      'jongen', 'meisje', 'oudeman', 'oudevrouw'):
            # Merkbare toonhoogte én klankkleur voor karakterstemmen. Deze
            # benaderingen zijn geen realistische leeftijds-/genderconversie.
            doel = {'diep': .79, 'heel_diep': .52, 'hoog': 1.42,
                    'heel_hoog': 1.90, 'monster': .65, 'jongen': 1.30,
                    'meisje': 1.56, 'oudeman': .73, 'oudevrouw': .86}[profiel]
            verhouding = 1.0 + (doel - 1.0) * sterkte
            if profiel in ('oudeman', 'oudevrouw'):
                tijd = self._modulatie_frames / self.samplefrequentie
                verhouding *= 1.0 + .012 * sterkte * math.sin(2 * math.pi * 5.2 * tijd)
                self._modulatie_frames = (self._modulatie_frames + len(invoer)) % self.samplefrequentie
            verwerkt = self._verschuif_toonhoogte(invoer, verhouding)
            if profiel in ('jongen', 'meisje', 'oudeman', 'oudevrouw'):
                verwerkt = self._karakterklank(verwerkt, profiel, sterkte)
            if profiel == 'monster':
                verwerkt = np.tanh(verwerkt * (1.0 + sterkte * 2.4)).astype(np.float32) * 0.76
            return verwerkt
        if profiel == 'echo':
            return self._echo(invoer, sterkte)
        if profiel == 'autotune':  # Bestaande profiel-ID behouden voor opgeslagen intensiteiten.
            return self._stoorzender(invoer, sterkte)
        if profiel == 'megafoon':
            verwerkt = np.tanh(invoer * (1.0 + 7.0 * sterkte)).astype(np.float32) * .72
            return np.asarray(invoer * (1 - sterkte) + verwerkt * sterkte, dtype=np.float32)
        return invoer

    def _bandfilter(self, invoer: np.ndarray, telefoon: bool) -> np.ndarray:
        hp = 500 if telefoon else 360
        lp = 2300 if telefoon else 3000
        hp_alpha = 1.0 / (1.0 + 2.0 * math.pi * hp / self.samplefrequentie)
        lp_alpha = (2.0 * math.pi * lp / self.samplefrequentie) / (1.0 + 2.0 * math.pi * lp / self.samplefrequentie)
        uitgang = np.empty_like(invoer)
        for kanaal in range(invoer.shape[1]):
            vorige_in = float(self._hp_vorige_in[kanaal])
            vorige_hp = float(self._hp_vorige_uit[kanaal])
            vorige_lp = float(self._lp_vorige_uit[kanaal])
            for i, waarde in enumerate(invoer[:, kanaal]):
                x = float(waarde)
                hoog = hp_alpha * (vorige_hp + x - vorige_in)
                laag = vorige_lp + lp_alpha * (hoog - vorige_lp)
                uitgang[i, kanaal] = math.tanh(laag * (3.0 if telefoon else 2.5)) * .73
                vorige_in, vorige_hp, vorige_lp = x, hoog, laag
            self._hp_vorige_in[kanaal] = vorige_in
            self._hp_vorige_uit[kanaal] = vorige_hp
            self._lp_vorige_uit[kanaal] = vorige_lp
        return uitgang

    def _karakterklank(self, invoer: np.ndarray, profiel: str, sterkte: float) -> np.ndarray:
        """Licht stateful laag/hoog-EQ voor herkenbare karakterklank zonder DSP-dependency.

        Eén filtertoestand per kanaal voorkomt klikken op audioblokgrenzen.
        De originele stem wordt niet opgeslagen of gewijzigd.
        """
        bass, treble = {
            'jongen': (.72, 1.17), 'meisje': (.52, 1.27),
            'oudeman': (1.24, .66), 'oudevrouw': (.99, .77),
        }[profiel]
        bass = 1.0 + (bass - 1.0) * sterkte
        treble = 1.0 + (treble - 1.0) * sterkte
        alpha = 1.0 - math.exp(-2 * math.pi * 650.0 / self.samplefrequentie)
        result = np.empty_like(invoer)
        for kanaal in range(invoer.shape[1]):
            vorige = float(self._kleur_laag[kanaal])
            for i, x in enumerate(invoer[:, kanaal]):
                vorige += alpha * (float(x) - vorige)
                result[i, kanaal] = bass * vorige + treble * (float(x) - vorige)
            self._kleur_laag[kanaal] = vorige
        if profiel in ('oudeman', 'oudevrouw'):
            # Milde korreligheid. Clip pas boven de veilige amplitude.
            result = (np.tanh(result * (1.0 + .75 * sterkte)) /
                      math.tanh(1.0 + .75 * sterkte)).astype(np.float32)
        # Zachte afvlakking boven 90% in plaats van harde clipping.
        amplitude = np.abs(result)
        verzacht = .90 + .10 * np.tanh((amplitude - .90) * 10.0)
        return np.where(amplitude > .90, np.sign(result) * verzacht, result).astype(np.float32)

    def _verschuif_toonhoogte(self, invoer: np.ndarray, factor: float) -> np.ndarray:
        """Pitch en formanten los aanpassen, met doorlopende native audiobuffers."""
        kleur = {'diep': -1.4, 'heel_diep': -3.0, 'hoog': 1.1,
                 'heel_hoog': 2.8, 'monster': -3.2, 'jongen': 1.8,
                 'meisje': 2.8, 'oudeman': -1.4, 'oudevrouw': -.5}[self.profiel]
        return self._nieuwe_motor().verwerk_blok(
            invoer, toonhoogte=12 * math.log2(float(np.clip(factor, .5, 2))),
            klankkleur=kleur*self.intensiteit/100)

    def _nieuw_effect(self, invoer: np.ndarray, sterkte: float) -> np.ndarray:
        waarden = self._effect_parameters[self.profiel]
        if self.profiel == 'monsterkoor':
            toon, kleur, code = -float(waarden['diepte']), -3.0, 1
            a, b = waarden['diepte']/12, waarden['dubbel_pct']/100
        elif self.profiel == 'ruimtepak':
            toon, kleur, code = 0, 0, 2
            a, b = waarden['metaal_pct']/100, waarden['helder_pct']/100
        elif self.profiel == 'spook':
            toon, kleur, code = 3.0, 1.7, 3
            a, b = waarden['zweving_pct']/100, waarden['echo_pct']/100
        else:
            toon, kleur, code = 0, 0, 4
            a, b = waarden['korrel_pct']/100, waarden['robot_pct']/100
        return self._nieuwe_motor().verwerk_blok(
            invoer, toonhoogte=toon*sterkte, klankkleur=kleur*sterkte,
            effect=code, sterkte=sterkte, instelling1=a, instelling2=b)

    def _stoorzender(self, invoer: np.ndarray, sterkte: float) -> np.ndarray:
        """Digitale storing met korrel, signaalhaperingen en stemafhankelijke ruis.

        Dit is een *audio-effect*, geen echte radiozender. De tijdsbasis loopt
        door over opeenvolgende audioblokken. Korte haperingen zijn bewust
        onderdeel van de klank; de randen worden afgerond om harde klikken
        bij de audioblokgrenzen te voorkomen.
        """
        params = self._effect_parameters['autotune']
        ruis = params['ruis_pct'] / 100.0
        hap = params['haperingen_pct'] / 100.0
        korrel = params['korrel_pct'] / 100.0
        n = len(invoer)
        if not (ruis or hap or korrel):
            self._stoorzender_frames += n
            return invoer.copy()

        tijd = self._stoorzender_frames + np.arange(n, dtype=np.int64)
        self._stoorzender_frames += n
        kanalen = invoer.shape[1]
        # Sample-and-hold + grove quantisatie leveren hoorbaar digitaal gekraak.
        stap = max(1, round(1 + 12 * korrel))
        waar = (tijd % stap) == 0
        index = np.maximum.accumulate(np.where(waar, np.arange(n), -1))
        bron = invoer[np.maximum(index, 0)].copy()
        eerder = index < 0
        if np.any(eerder):
            bron[eerder] = self._stoorzender_laatste[:kanalen]
        self._stoorzender_laatste[:kanalen] = bron[-1]
        niveau = max(8, round(90 - 78 * korrel))
        vervormd = np.round(bron * niveau) / niveau
        vervormd = np.tanh(vervormd * (1.2 + 2.8 * korrel)) * .87

        # Deterministische digitale ruis, alleen wanneer spraak binnenkomt.
        # Daardoor geen permanente ruis wanneer de microfoon stil is.
        hashwaarde = ((tijd * 1664525 + 1013904223) & 0xffff).astype(np.float32)
        digitale_ruis = hashwaarde / 32767.5 - 1.0
        spraak = np.minimum(1.0, np.mean(np.abs(invoer), axis=1) * 12.0)
        vervormd += (digitale_ruis * spraak * (.23 * ruis))[:, None]

        # Korte signaaluitval ongeveer twee keer per seconde, met zachte rand.
        fase = (tijd % max(1, round(.63 * self.samplefrequentie))) / self.samplefrequentie
        begin, eind, rand = .19, .275, .005
        inval = np.clip((fase - begin) / rand, 0, 1)
        uitval = np.clip((eind - fase) / rand, 0, 1)
        dip = inval * uitval
        vervormd *= (1.0 - .93 * hap * dip)[:, None]

        # Soepele droge/natte mix. Intensiteit 0 wordt bovenin `verwerk`
        # helemaal overgeslagen, zodat de oorspronkelijke samples exact blijven.
        resultaat = invoer * (1.0 - sterkte) + vervormd * sterkte
        return np.asarray(np.clip(resultaat, -.98, .98), dtype=np.float32)

    def _echo(self, invoer: np.ndarray, sterkte: float) -> np.ndarray:
        """Variabele echo met begrensde feedback en instelbare wet/dry-verhouding."""
        n = len(invoer)
        if n > 480:
            return np.concatenate([self._echo(invoer[i:i+480], sterkte)
                                   for i in range(0, n, 480)], axis=0)
        params = self._effect_parameters['echo']
        delay = max(480, int(self.samplefrequentie * params['vertraging_ms'] / 1000))
        m = len(self._echo_buf)
        kanalen = invoer.shape[1]
        posities = self._echo_frames + np.arange(n, dtype=np.int64)
        vorige = self._echo_buf[(posities - delay) % m, :kanalen].copy()
        feedback = params['feedback_pct'] / 100.0
        mix = params['mix_pct'] / 100.0 * sterkte
        uit = invoer + vorige * mix
        self._echo_buf[posities % m, :kanalen] = invoer + vorige * feedback
        self._echo_frames += n
        return np.asarray(uit, dtype=np.float32)
