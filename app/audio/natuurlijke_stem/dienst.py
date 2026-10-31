"""Eén CPU-stemmotor voor live microfoon en lokale preview.

De callback wisselt alleen begrensde audioblokken uit. Laden, inferentie,
bestandstoegang en procesbeheer gebeuren elders. Bij achterstand blijft de
microfoon gedempt, zonder terugval naar de onbewerkte stem.
"""
from __future__ import annotations
import copy
import hashlib
import json
import os
from pathlib import Path
from queue import Empty, Full, Queue
import struct
import subprocess
import threading
import time
import uuid
import numpy as np
from .varianten import Klankbewerking, catalogus, controleer_variant
from .proces import EigenProcesgroep, start_eigen_worker
from .prestatie import BUFFERPROFIELEN, Meetvenster, beoordeel, controleer_profiel
from .runtimecontrole import valideer_runtime, file_sha
from app.desktop.bouwprofiel import ai_stemmen_ingeschakeld

FRAMES=2496
HEADER=struct.Struct('<4sIII')
MAGIC=b'DS15'
MODEL_SHA='cceb7ab9621f84d62d283725ae3281cacb04f762d6a088fe3e97c1a29d4b8c0e'


def runtime_map():
    return Path(__file__).resolve().parents[3] / 'stem-runtime'


def controleer_runtime(root=None):
    root=Path(root) if root else runtime_map()
    valideer_runtime(root)
    return root/'DrostStemWorker.exe',root/'G_500000.pth'


def _read_exact(stream,size):
    out=bytearray()
    while len(out)<size:
        part=stream.read(size-len(out))
        if not part: raise EOFError('Stemmotor heeft de pijp gesloten.')
        out.extend(part)
    return bytes(out)


def _write_exact(stream,data):
    view=memoryview(data)
    while len(view):
        count=stream.write(view)
        if not count: raise EOFError('Stemmotor neemt geen audio aan.')
        view=view[count:]


class NatuurlijkeStemDienst:
    def __init__(self, instellingpad, logger, *, root=None, autostart=True):
        self.instellingpad=Path(instellingpad)
        self.logger=logger
        self.root=Path(root) if root else runtime_map()
        self._command=threading.RLock()
        self._lock=threading.Lock()
        self._thread=None; self._watch_thread=None; self._process=None; self._job=None
        self._stop=threading.Event()
        self._inputs=Queue(maxsize=18); self._outputs=Queue(maxsize=4)
        self._out=np.zeros(0,np.float32)
        self._out_gen=0; self._generation=0
        self._route=None; self._last_callback=0.0
        self._started_output=False; self._underflows=0
        self.aan=False; self._state='uit'; self._message='Proefstem uit.'
        self._ms=0.0; self._slow=0; self._closing=False
        self._deadline=0.0
        self.bufferprofiel='gebalanceerd'
        self.variant='llvc_basis'; self.gekozen=False; self._variantvertraging_ms=0.0
        self._test_only=False; self._test_voortgang=0
        self._pc_test=None; self._pakketcontrole='niet_gecontroleerd'
        self._metingen=Meetvenster(); self._onderbrekingen=0
        self._rapport_bewaard=False
        if autostart and self.instellingpad.is_file():
            try:
                keuze=json.loads(self.instellingpad.read_text(encoding='utf-8'))
                if not isinstance(keuze,dict) or type(keuze.get('aan',False)) is not bool:
                    raise ValueError('Ongeldige stemkeuze.')
                self.bufferprofiel=controleer_profiel(keuze.get('bufferprofiel','gebalanceerd'))
                self.variant=controleer_variant(keuze.get('variant','llvc_basis')).id
                self.gekozen=keuze.get('gekozen',keuze.get('aan',False))
                if type(self.gekozen) is not bool:raise ValueError('Ongeldige stemkeuze.')
                if keuze.get('aan') and not self.gekozen:raise ValueError('Actieve modelstem is niet geselecteerd.')
                if not ai_stemmen_ingeschakeld():
                    # Een oude modelselectie mag niet actief blijven in de compacte editie,
                    # ook niet wanneer de gebruiker deze eerder had uitgeschakeld.
                    # Laat het instellingenbestand ongemoeid voor een eventuele rollback.
                    self.aan = False
                    self.gekozen = False
                    self._state = 'uit'
                    self._message = 'AI-stemmen zijn niet meegeleverd. Gewone effecten blijven beschikbaar.'
                elif keuze.get('aan') is True:
                    self.stel_in(True,bewaren=False)
            except Exception:
                self.aan=True; self.gekozen=True; self._state='fout'
                self._message='De proefstem kon niet starten. Je microfoon blijft gedempt. Schakel de proefstem uit om de gewone effecten te gebruiken.'

    def _save(self,aan):
        self.instellingpad.parent.mkdir(parents=True,exist_ok=True)
        temp=self.instellingpad.with_name(self.instellingpad.name+'.'+uuid.uuid4().hex+'.tmp')
        try:
            temp.write_text(json.dumps({'schema':2,'aan':aan,'bufferprofiel':self.bufferprofiel,'variant':self.variant,'gekozen':self.gekozen}),encoding='utf-8')
            os.replace(temp,self.instellingpad)
        finally:
            temp.unlink(missing_ok=True)

    def _clear_locked(self):
        self._generation+=1
        for q in (self._inputs,self._outputs):
            while True:
                try:q.get_nowait()
                except Empty:break
        self._out=np.zeros(0,np.float32)
        self._out_gen=self._generation
        self._started_output=False; self._underflows=0
        self._route=None; self._last_callback=0.0

    def wis_audio(self):
        with self._lock:self._clear_locked()

    def stel_in(self,aan,bewaren=True,*,herladen=False):
        if type(aan) is not bool:raise ValueError('Kies aan of uit voor de proefstem.')
        if aan and not ai_stemmen_ingeschakeld():
            raise ValueError('AI-stemmen zijn niet inbegrepen in deze compacte installatie.')
        with self._command:
            if self._closing:raise RuntimeError('De app wordt afgesloten.')
            if self._test_only:
                raise ValueError('Stop eerst de computertest.')
            if self.aan==aan and self._state!='fout' and not herladen:return self.status()
            # Eerst muten. Een lopende callback mag tijdens stoppen nooit droog doorschakelen.
            if aan:self.aan=True; self.gekozen=True
            try:
                self._stop_worker()
                if bewaren:self._save(aan)
            except Exception:
                self._fault('De stemkeuze kon niet worden toegepast. Je microfoon is gedempt. Probeer opnieuw.')
                raise
            with self._lock:
                self._clear_locked(); self.aan=aan
                self._metingen.wis(); self._onderbrekingen=0; self._slow=0
                self._state='laden' if aan else 'uit'
                self._message='Proefstem laden. Je microfoon blijft intussen gedempt.' if aan else 'Proefstem uit. De gewone steminstellingen gelden weer.'
            if aan:
                self._test_voortgang=0; self._pc_test=None; self._rapport_bewaard=False
                self._stop=threading.Event(); self._deadline=time.monotonic()+45
                self._thread=threading.Thread(target=self._run,name='DrostStem-beheer',daemon=True)
                self._thread.start()
                self._watch_thread=threading.Thread(target=self._watchdog,args=(self._stop,),name='DrostStem-bewaking',daemon=True)
                self._watch_thread.start()
            return self.status()

    def kies_variant(self, variant, *, aan=None):
        if not ai_stemmen_ingeschakeld():
            raise ValueError('AI-stemmen zijn niet inbegrepen in deze compacte installatie.')
        variant=controleer_variant(variant).id
        if aan is not None and type(aan) is not bool:
            raise ValueError('Kies aan of uit voor de stemvervormer.')
        with self._command:
            if self._closing:raise RuntimeError('De app wordt afgesloten.')
            if self._test_only:raise ValueError('Stop eerst de computertest.')
            oud=(self.variant,self.gekozen)
            herladen=variant!=self.variant or not self.gekozen
            self.variant=variant; self.gekozen=True
            doel=self.aan if aan is None else aan
            try:
                # Bij een wissel worden model- en effectbuffers volledig opnieuw gestart.
                # Daardoor kan de oude stem niet na de nieuwe keuze terugkomen.
                if doel or self.aan:
                    return self.stel_in(doel,herladen=herladen)
                self._save(False)
                self.wis_audio()
                self._state='uit'; self._message='Karaktervariant gekozen. Zet de stemvervormer aan of beluister een voorbeeld.'
            except Exception:
                self.variant,self.gekozen=oud
                raise
            return self.status()

    def kies_gewone_effecten(self):
        with self._command:
            if self._closing:raise RuntimeError('De app wordt afgesloten.')
            if self._test_only:raise ValueError('Stop eerst de computertest.')
            oud=self.gekozen
            self.gekozen=False
            try:
                return self.stel_in(False,herladen=True)
            except Exception:
                self.gekozen=oud
                raise

    def stel_bufferprofiel_in(self, profiel):
        profiel=controleer_profiel(profiel)
        with self._command:
            if self._closing:raise RuntimeError('De app wordt afgesloten.')
            if self.aan or self._test_only:
                raise ValueError('Zet de proefstem uit en stop de computertest voordat je de buffer aanpast.')
            oud=self.bufferprofiel
            self.bufferprofiel=profiel
            try:self._save(False)
            except Exception:
                self.bufferprofiel=oud
                raise
            with self._lock:self._clear_locked()
        return self.status()

    def test_computer(self):
        """Start een eigen synthetische proef; de bestaande aan-keuze blijft gelijk."""
        if not ai_stemmen_ingeschakeld():
            raise ValueError('De AI-stemtest is niet beschikbaar in deze compacte installatie.')
        with self._command:
            if self._closing:raise RuntimeError('De app wordt afgesloten.')
            if self.aan:raise ValueError('Zet de proefstem eerst uit voordat je de computer test.')
            if self._test_only:return self.status()
            self._stop_worker()
            self._test_only=True; self._pc_test=None; self._rapport_bewaard=False
            self._test_voortgang=0; self._state='testen'
            self._message='Computer testen met kunstmatige audio. Je microfoon wordt niet geopend.'
            self._stop=threading.Event(); self._deadline=time.monotonic()+45
            self._thread=threading.Thread(target=self._run,name='DrostStem-computertest',daemon=True)
            self._thread.start()
            self._watch_thread=threading.Thread(target=self._watchdog,args=(self._stop,),name='DrostStem-bewaking',daemon=True)
            self._watch_thread.start()
        return self.status()

    def annuleer_test(self):
        with self._command:
            if self._test_only:
                self._stop_worker()
                self._test_only=False; self._state='uit'
                self._message='Computertest gestopt. De proefstem staat uit.'
                with self._lock:self._clear_locked()
        return self.status()

    def geef_rapport(self):
        # Geen paden, gebruikersnaam, microfoonaudio of logboeken exporteren.
        from app.diagnostiek.logboek import VERSIE_VAN_DE_APP
        return {'schema':1, 'appversie':VERSIE_VAN_DE_APP,
                'model':'LLVC-proefmodel', 'uitvoering':'processor',
                'variant':self.variant,'stemnaam':controleer_variant(self.variant).naam,
                'aantal_modellen':1, 'aantal_klankvarianten':len(catalogus()),
                'nabewerking_vertraging_ms':self._variantvertraging_ms,
                'toestand':self._state, 'melding':self._message, 'pakketcontrole':self._pakketcontrole,
                'bufferprofiel':self.bufferprofiel,
                'opstartreserve_ms':BUFFERPROFIELEN[self.bufferprofiel]['buffer_ms'],
                'computertest':copy.deepcopy(self._pc_test),
                'recente_verwerking':self._metingen.status(),
                'onderbrekingen':self._onderbrekingen,
                'totale_audiovertraging_ms':None,
                'geen_microfoonopname':True, 'geen_luistertest':True}

    def _wissel_blok(self, process, gen, block):
        """Volledige aanvraag meten, inclusief heen- en teruggaande procescommunicatie."""
        self._deadline=time.monotonic()+2.0
        started=time.perf_counter()
        _write_exact(process.stdin,HEADER.pack(MAGIC,gen,FRAMES,0)+block.astype('<f4').tobytes())
        process.stdin.flush()
        magic,returned,count,micros=HEADER.unpack(_read_exact(process.stdout,HEADER.size))
        if magic!=MAGIC or returned!=gen or count!=FRAMES:
            raise ValueError('Onjuist audioblok uit de stemmotor.')
        output=np.frombuffer(_read_exact(process.stdout,4*FRAMES),dtype='<f4').copy()
        elapsed=(time.perf_counter()-started)*1000
        self._deadline=0
        if not np.isfinite(output).all():raise ValueError('Ongeldige samples uit de stemmotor.')
        # Een gemelde modeltijd mag niet door een snellere pijpmeting worden verborgen.
        return output, max(elapsed,micros/1000), micros/1000

    def _meet_computer(self, process, nabewerking=None):
        rng=np.random.default_rng(416)
        audio=(rng.normal(0,.025,FRAMES)+.08*np.sin(2*np.pi*185*np.arange(FRAMES)/48000)).astype(np.float32)
        tijden=[]; modeltijden=[]; niet_stil=False
        self._pc_test=None; self._rapport_bewaard=False
        if not self._test_only:
            self._message='Proefstem laden en snelheid controleren. Je microfoon blijft gedempt.'
        # Deze speciale generatie bevat geen microfoonaudio. De echte route heeft een
        # andere generatie en wist daardoor de modelbuffers voor de eerste gesproken zin.
        for nr in range(36):
            if self._stop.is_set():return False
            uitvoer,elapsed,model_ms=self._wissel_blok(process,0xFFFFFFFE,audio)
            if nabewerking is not None:
                begin=time.perf_counter(); uitvoer=nabewerking.verwerk(uitvoer)
                elapsed+=(time.perf_counter()-begin)*1000
            if nr>=4:
                tijden.append(elapsed); modeltijden.append(model_ms)
                niet_stil=bool(niet_stil or np.max(np.abs(uitvoer))>1e-7)
            self._test_voortgang=round((nr+1)*100/36)
        rapport=beoordeel(tijden,modeltijden,niet_stil=niet_stil,model_sha=MODEL_SHA)
        if self._stop.is_set():return False
        rapport['variant']=self.variant
        rapport['inclusief_nabewerking']=nabewerking is not None
        self._pc_test=rapport
        path=self.instellingpad.with_name('stem3_laatste_controle.json')
        temp=path.with_name(path.name+'.'+uuid.uuid4().hex+'.tmp')
        try:
            vast_rapport=self.geef_rapport()
            vast_rapport.update(toestand='test_afgerond',melding='Lokale snelheidscontrole afgerond. Dit is geen luistertest.')
            temp.write_text(json.dumps(vast_rapport,ensure_ascii=False,indent=2),encoding='utf-8')
            os.replace(temp,path); self._rapport_bewaard=True
        except OSError:
            # Opslag is niet nodig om de meting in de huidige sessie te bekijken.
            self.logger.warning('Stemmeting kon niet lokaal worden opgeslagen.')
        finally:temp.unlink(missing_ok=True)
        return rapport['geslaagd']

    def _fault(self,message):
        self._state='fout'; self._message=message; self._stop.set()
        # Geen log-I/O vanuit de callback. Details gaan op de beheerdraad naar het log.

    def _watchdog(self,stop):
        while True:
            stopped=stop.wait(.2)
            if stop is not self._stop:return
            if stopped:
                if self._state == 'fout':
                    # Een callbackfout mag niet een vastgelopen eigen proces achterlaten.
                    p=self._process
                    if p is not None and p.poll() is None:
                        try:p.kill()
                        except OSError:pass
                return
            if self._deadline and time.monotonic()>self._deadline:
                self._fault('De proefstem reageert niet op tijd. Je microfoon is gedempt. Zet de proefstem uit en opnieuw aan.')
                p=self._process
                if p is not None and p.poll() is None:
                    try:p.kill()
                    except OSError:pass
                return

    def _run(self):
        error_stream=None; process=None; job=None; nabewerking=None
        try:
            self._pakketcontrole='bezig'
            exe,model=controleer_runtime(self.root)
            self._pakketcontrole='gecontroleerd'
            if self._stop.is_set():return
            self.instellingpad.parent.mkdir(parents=True,exist_ok=True)
            error_path=self.instellingpad.parent/'stem2_technisch.log'
            error_stream=error_path.open('w',encoding='utf-8')
            process=start_eigen_worker(exe,model,error_stream)
            self._process=process
            if self._stop.is_set():return
            job=EigenProcesgroep(process); self._job=job
            hello=process.stdout.readline(2048)
            if json.loads(hello)!=dict(ready=True,protocol=1,frames=FRAMES):
                raise ValueError('Stemmotor gaf geen geldige gereedmelding.')
            if self._stop.is_set():return
            self._deadline=0
            nabewerking=Klankbewerking(self.variant)
            self._variantvertraging_ms=nabewerking.vertraging_ms
            geslaagd=self._meet_computer(process,nabewerking)
            # De synthetische proef mag geen voorgeschiedenis in live spraak achterlaten.
            nabewerking.sluiten(); nabewerking=Klankbewerking(self.variant)
            if self._stop.is_set():return
            if self._test_only:
                self._state='uit'
                self._message=('Computertest afgerond. De verwerking heeft voldoende ruimte. Test de stem ook met een koptelefoon.'
                    if geslaagd else "Deze computer houdt de proefstem nu niet bij, of het model gaf geen audio. Sluit zware programma's en test opnieuw. De gewone effecten blijven beschikbaar.")
                return
            if not geslaagd:
                self._fault('De processor houdt de proefstem nu niet bij, of het model gaf geen audio. Je microfoon is gedempt. Zet de proefstem uit en gebruik een gewone effectstem.')
                return
            with self._lock:self._clear_locked()
            self._state='gereed'; self._message='Proefstem gereed. Test met een koptelefoon of verbind de microfoon.'
            pending=np.zeros(0,np.float32); epoch=None
            while not self._stop.is_set():
                try:gen,audio,stamp=self._inputs.get(timeout=.1)
                except Empty:continue
                if gen!=self._generation:continue
                if time.monotonic()-stamp>.25:
                    self._fault('De processor houdt de proefstem niet bij. Je microfoon is gedempt. Gebruik een gewone effectstem.')
                    break
                if epoch!=gen:
                    pending=np.zeros(0,np.float32); epoch=gen
                    nabewerking.sluiten(); nabewerking=Klankbewerking(self.variant)
                pending=np.concatenate((pending,audio))
                while len(pending)>=FRAMES and not self._stop.is_set():
                    block=pending[:FRAMES].copy(); pending=pending[FRAMES:]
                    output,elapsed,model_ms=self._wissel_blok(process,gen,block)
                    begin=time.perf_counter(); output=nabewerking.verwerk(output)
                    elapsed+=(time.perf_counter()-begin)*1000
                    if gen!=self._generation:break
                    self._ms=elapsed
                    self._metingen.voeg_toe(elapsed)
                    self._slow=self._slow+1 if self._ms>52 else max(0,self._slow-1)
                    if self._slow>=6:
                        self._fault('De processor houdt de proefstem niet bij. Je microfoon is gedempt. Gebruik een gewone effectstem.'); break
                    try:self._outputs.put_nowait((gen,np.clip(output,-.95,.95),time.monotonic()))
                    except Full:
                        # Geen microfoon meer afgenomen of route gewisseld: oude spraak nooit bewaren.
                        with self._lock:self._clear_locked()
                        break
        except Exception:
            if not self._stop.is_set():
                if self._pakketcontrole=='bezig':self._pakketcontrole='beschadigd'
                self._fault('De proefstem werkt niet. Je microfoon is gedempt; soundboardgeluiden blijven werken. Zet de proefstem uit en opnieuw aan.')
                self.logger.exception('LLVC-proefmotor gestopt')
        finally:
            if nabewerking is not None:
                try:nabewerking.sluiten()
                except Exception:self.logger.exception('Klankbewerking afsluiten mislukt')
            self._deadline=0
            if process is not None:
                try:
                    if process.stdin:process.stdin.close()
                    process.wait(timeout=1)
                except Exception:
                    if process.poll() is None:process.kill()
                    try:process.wait(timeout=2)
                    except Exception:pass
                for stream in (process.stdout,process.stderr):
                    if stream:
                        try:stream.close()
                        except Exception:pass
            if job is not None:job.close()
            if error_stream is not None:error_stream.close()
            self._process=None; self._job=None
            if self._test_only:
                self._stop.set(); self._test_only=False

    def verwerk(self,invoer,bron):
        """Nooit wachten op de motor. Nooduitvoer is stilte, geen originele stem."""
        result=np.zeros_like(invoer)
        if not self.aan:return result
        if self._state not in ('gereed','actief') or self._stop.is_set():return result
        if (not isinstance(invoer,np.ndarray) or invoer.dtype!=np.float32 or invoer.ndim!=2
                or invoer.shape[1] not in (1,2) or not 0<len(invoer)<=4096 or not np.isfinite(invoer).all()):
            self._fault('Ongeldige microfoonaudio. Je microfoon is gedempt.');return result
        if not self._lock.acquire(blocking=False):return result
        try:
            now=time.monotonic()
            if bron!=self._route or now-self._last_callback>.25:
                self._clear_locked(); self._route=bron
            self._last_callback=now; gen=self._generation
            mono=np.mean(invoer,axis=1,dtype=np.float32)
            try:self._inputs.put_nowait((gen,mono.copy(),now))
            except Full:
                self._fault('De processor houdt de proefstem niet bij. Je microfoon is gedempt. Gebruik een gewone effectstem.');return result
            # Twee blokken opstartreserve voor onregelmatige Windowsplanning.
            if not self._started_output and self._outputs.qsize()<BUFFERPROFIELEN[self.bufferprofiel]['blokken']:return result
            self._started_output=True
            while len(self._out)<len(invoer):
                try:item=self._outputs.get_nowait()
                except Empty:break
                out_gen,audio=item[:2]
                stamp=item[2] if len(item)==3 else now
                if now-stamp>.30:
                    self._onderbrekingen+=1
                    self._clear_locked()
                    return result
                if out_gen==gen:self._out=np.concatenate((self._out,audio))
            if len(self._out)<len(invoer):
                self._underflows+=1; self._onderbrekingen+=1
                if self._underflows>15:
                    self._fault('De proefstem hapert te veel. Je microfoon is gedempt. Gebruik een gewone effectstem.')
                return result
            self._underflows=max(0,self._underflows-1)
            result[:]=self._out[:len(invoer),None]
            self._out=self._out[len(invoer):]
            self._state='actief'; self._message=controleer_variant(self.variant).naam+' actief op de processor.'
            return result
        finally:self._lock.release()

    def status(self):
        return dict(aan=self.aan,toestand=self._state,melding=self._message,
                    beschikbaar=ai_stemmen_ingeschakeld() and (self.root/'runtime.json').is_file(),
                    model='LLVC-proefmodel',processor=True,
                    variant=self.variant, stemnaam=controleer_variant(self.variant).naam,
                    gekozen=self.gekozen, varianten=catalogus(),
                    nabewerking_vertraging_ms=self._variantvertraging_ms,
                    verwerking_ms=round(self._ms,1),experimenteel=True,
                    bufferprofiel=self.bufferprofiel, bufferprofielen=copy.deepcopy(BUFFERPROFIELEN),
                    opstartreserve_ms=BUFFERPROFIELEN[self.bufferprofiel]['buffer_ms'],
                    test_bezig=self._test_only, test_voortgang=self._test_voortgang,
                    pakketcontrole=self._pakketcontrole, computertest=copy.deepcopy(self._pc_test),
                    recente_verwerking=self._metingen.status(), onderbrekingen=self._onderbrekingen,
                    model_id='koeai-llvc-proef-1', aantal_modellen=1,
                    rapport_bewaard=self._rapport_bewaard, totale_audiovertraging_ms=None)

    def _stop_worker(self):
        self._stop.set()
        thread=self._thread
        if thread is not None and thread is not threading.current_thread():thread.join(timeout=.4)
        process=self._process
        if process is not None and process.poll() is None:
            try:process.terminate()
            except OSError:pass
        if thread is not None and thread is not threading.current_thread():
            thread.join(timeout=3)
            if thread.is_alive():
                process=self._process
                if process is not None and process.poll() is None:
                    try:process.kill()
                    except OSError:pass
                thread.join(timeout=2)
                if thread.is_alive():raise RuntimeError('De stemmotor kon niet volledig afsluiten.')
        self._thread=None
        watcher=self._watch_thread
        if watcher is not None and watcher is not threading.current_thread():
            watcher.join(timeout=1)
            if watcher.is_alive():raise RuntimeError('De stembewaking is nog niet afgesloten.')
        self._watch_thread=None

    def sluiten(self):
        with self._command:
            self._closing=True
            self._stop_worker()
            self._test_only=False
            with self._lock:
                self._clear_locked(); self._state='uit'
                # AAN blijft tijdens het afsluiten muten totdat ook de audiostream stopt.
            # Bewaarde keuze blijft behouden voor een volgende appstart.
            return True
