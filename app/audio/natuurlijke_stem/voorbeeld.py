"""Verwerk uitsluitend de ingebouwde Bob/Elise-fragmenten, zonder microfoon.

Een eigen, begrensde renderopdracht deelt nooit de streamingbuffers van een gesprek.
De worker gebruikt hetzelfde model en protocol als de live stem. Het WAV-resultaat
blijft in het geheugen en wordt alleen aan het lokale dashboard teruggegeven.
"""
from __future__ import annotations
from collections import OrderedDict
import hashlib
import io
import json
from pathlib import Path
import re
import subprocess
import threading
import time
import numpy as np
import soundfile as sf
from .dienst import FRAMES, HEADER, MAGIC, controleer_runtime, _read_exact, _write_exact
from .proces import EigenProcesgroep, start_eigen_worker
from .varianten import Klankbewerking, controleer_variant
from .voorbeeldaudio import bereid_voorbeeld_voor


def controleer_verzoek(verzoek):
    if not isinstance(verzoek, str) or not re.fullmatch(r'[a-zA-Z0-9_]{8,80}', verzoek):
        raise ValueError('Ongeldig voorbeeldverzoek. Vernieuw de pagina.')
    return verzoek


class VoorbeeldGestopt(ValueError):
    pass


class StemVoorbeeldRenderer:
    def __init__(self, root: Path):
        self.root = Path(root)
        self._slot = threading.Lock()
        self._state = threading.Lock()
        self._request = None
        self._cancel = None
        self._process = None
        self._closing = False
        self._done = threading.Event(); self._done.set()
        self._cache = OrderedDict()

    def annuleer(self, verzoek=None):
        if verzoek is not None: controleer_verzoek(verzoek)
        with self._state:
            if verzoek is not None and verzoek != self._request: return
            if self._cancel is not None: self._cancel.set()
            process = self._process
            if process is not None and process.poll() is None:
                try: process.kill()
                except OSError: pass

    def sluiten(self):
        with self._state: self._closing = True
        self.annuleer()
        klaar = self._done.wait(5)
        if klaar: self._cache.clear()
        return klaar

    def render(self, maak_bron, variant: str, verzoek: str, *, nog_geldig=lambda: True) -> bytes:
        controleer_variant(variant); controleer_verzoek(verzoek)
        if not self._slot.acquire(timeout=1):
            raise ValueError('Een voorbeeld wordt nog voorbereid. Stop dat voorbeeld en probeer opnieuw.')
        process = job = nabewerking = watcher = None
        cancel = threading.Event(); finished = threading.Event()
        start_deadline = time.monotonic()+60
        deadline = [min(time.monotonic()+45, start_deadline)]
        def controle():
            if cancel.is_set() or not nog_geldig(): raise VoorbeeldGestopt('Voorbeeld gestopt.')
        def bewaak():
            while not finished.wait(.05):
                if cancel.is_set() or time.monotonic() > deadline[0]:
                    cancel.set()
                    with self._state:
                        proc = self._process if self._request == verzoek else None
                        if proc is not None and proc.poll() is None:
                            try: proc.kill()
                            except OSError: pass
                    # Nog geen proces? Blijf controleren tot de start klaar is.
        try:
            with self._state:
                if self._closing: raise ValueError('De app wordt afgesloten.')
                self._request = verzoek; self._cancel = cancel; self._done.clear()
            watcher = threading.Thread(target=bewaak, name='DrostStem-voorbeeldbewaking', daemon=True)
            watcher.start()
            bron = maak_bron()
            controle()
            if not isinstance(bron, bytes) or not 44 <= len(bron) <= 12*1024*1024:
                raise ValueError('Het ingebouwde voorbeeld is niet leesbaar.')
            key=("bron418",variant,hashlib.sha256(bron).hexdigest())
            if key in self._cache:
                self._cache.move_to_end(key)
                return self._cache[key]
            mono = bereid_voorbeeld_voor(bron)
            exe,model=controleer_runtime(self.root)
            controle()
            process=start_eigen_worker(exe,model,subprocess.DEVNULL)
            with self._state:self._process=process
            controle()
            job=EigenProcesgroep(process)
            if json.loads(process.stdout.readline(2048))!=dict(ready=True,protocol=1,frames=FRAMES):
                raise ValueError('De stemmotor kon het voorbeeld niet voorbereiden.')
            controle()
            nabewerking=Klankbewerking(variant)
            # Bewaar spraakbegin en staart, inclusief vertraging van de nabewerking.
            padded=np.concatenate((np.zeros(FRAMES*2,np.float32),mono,np.zeros(FRAMES*8,np.float32)))
            padded=np.pad(padded,(0,(-len(padded))%FRAMES))
            blocks=[]
            for begin in range(0,len(padded),FRAMES):
                controle(); deadline[0]=min(time.monotonic()+3, start_deadline)
                data=padded[begin:begin+FRAMES].astype('<f4',copy=False).tobytes()
                _write_exact(process.stdin,HEADER.pack(MAGIC,17,FRAMES,0)+data)
                process.stdin.flush()
                magic,generation,count,_=HEADER.unpack(_read_exact(process.stdout,HEADER.size))
                if (magic,generation,count)!=(MAGIC,17,FRAMES):
                    raise ValueError('De stemmotor gaf geen geldig voorbeeld terug.')
                output=np.frombuffer(_read_exact(process.stdout,4*FRAMES),dtype='<f4').copy()
                if not np.isfinite(output).all():raise ValueError('De stemmotor gaf ongeldige audio terug.')
                blocks.append(np.clip(nabewerking.verwerk(output),-.95,.95))
            controle()
            result=io.BytesIO()
            sf.write(result,np.concatenate(blocks),48000,format='WAV',subtype='PCM_16')
            wav=result.getvalue()
            self._cache[key]=wav
            while len(self._cache)>8 or sum(map(len,self._cache.values()))>8*1024*1024:
                self._cache.popitem(last=False)
            return wav
        except (EOFError, BrokenPipeError, OSError) as exc:
            if cancel.is_set(): raise VoorbeeldGestopt('Voorbeeld gestopt of niet op tijd gereed.') from exc
            raise ValueError('Het stemvoorbeeld kon niet worden gemaakt. Probeer opnieuw.') from exc
        finally:
            finished.set()
            if process is not None:
                try:
                    if process.stdin: process.stdin.close()
                    process.wait(timeout=.5)
                except Exception:
                    if process.poll() is None:
                        try: process.kill()
                        except OSError: pass
                    try: process.wait(timeout=2)
                    except Exception: pass
                for stream in (process.stdout, process.stderr):
                    if stream is not None:
                        try: stream.close()
                        except Exception: pass
            if job is not None:
                try:job.close()
                except Exception:pass
            if nabewerking is not None:
                try:nabewerking.sluiten()
                except Exception:pass
            if watcher is not None: watcher.join(timeout=1)
            with self._state:
                self._process=None; self._cancel=None; self._request=None; self._done.set()
            self._slot.release()
