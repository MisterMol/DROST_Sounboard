"""Native acceptatietest. Werkt zonder microfoon, audiodevice of server."""
from __future__ import annotations
import argparse
import importlib.util
import json
from pathlib import Path
import time
import traceback
import numpy as np


def controleer(motor_module, library):
    factory=lambda: motor_module.SignalsmithMotor(48000, library=library)
    fs=48000; t=np.arange(fs*2,dtype=np.float64)/fs
    x=(.15*np.sin(2*np.pi*220*t)).astype(np.float32)[:,None]
    tests=[]; benchmarks={}
    def ok(name,condition):
        if not condition: raise AssertionError(name)
        tests.append(name)
    motor=factory()
    try:
        y=np.concatenate([motor.verwerk_blok(x[i:i+480],toonhoogte=12) for i in range(0,len(x),480)])
        spectrum=np.abs(np.fft.rfft(y[-fs:,0]*np.hanning(fs)))
        freq=float(np.fft.rfftfreq(fs,1/fs)[np.argmax(spectrum)])
        ok('Toonhoogte daadwerkelijk verdubbeld',430<=freq<=450)
        ok('Geen tijdrek of ongeldige uitvoer',y.shape==x.shape and np.isfinite(y).all())
        ok('Bron blijft ongewijzigd',np.array_equal(x[:,0],(.15*np.sin(2*np.pi*220*t)).astype(np.float32)))
        ok('Bekende interne vertraging',0<motor.vertraging_samples<=9600)
        motor.reset()
        z=motor.verwerk_blok(np.zeros((8192,1),np.float32),toonhoogte=-6)
        ok('Reset verwijdert oude audio',float(np.max(np.abs(z)))<1e-5)
        try: motor.verwerk_blok(np.asarray([[np.nan]],np.float32))
        except ValueError: tests.append('NaN wordt geweigerd')
        else: raise AssertionError('NaN niet geweigerd')
        for effect in range(5):
            motor.reset(); outputs=[]; durations=[]
            for i in range(0,len(x),480):
                start=time.perf_counter()
                out=motor.verwerk_blok(x[i:i+480],effect=effect,toonhoogte=-5 if effect in (0,1) else 3 if effect==3 else 0,
                                      klankkleur=-2 if effect in (0,1) else 0,instelling1=.65,instelling2=.65)
                durations.append(time.perf_counter()-start);outputs.append(out)
            result=np.concatenate(outputs)
            ok(f'Effect {effect}: eindig, hoorbaar en begrensd',np.isfinite(result).all() and
               .005<float(np.sqrt(np.mean(result[-fs:]**2))) and float(np.max(np.abs(result)))<=1.001)
            d=np.asarray(durations[10:])
            benchmarks[str(effect)]={'gemiddeld_ms':float(d.mean()*1000),
                                     'p99_ms':float(np.quantile(d,.99)*1000),
                                     'verwerking_per_audioseconde':float(d.mean()/.01)}
            ok(f'Effect {effect}: geen gemiddelde achterstand',float(d.mean())<.008)
        # Stereo kanaalwisseling mag geen oude stem in een stil kanaal afgeven.
        motor.reset()
        stereo=np.column_stack([x[:,0],np.zeros(len(x),np.float32)])
        ys=np.concatenate([motor.verwerk_blok(stereo[i:i+480],toonhoogte=-3) for i in range(0,len(x),480)])
        ok('Stereo scheiding',float(np.max(np.abs(ys[:,1])))<1e-5)
        # The splitter must preserve state across arbitrary callback block sizes.
        one=factory();two=factory()
        try:
            a=np.concatenate([one.verwerk_blok(x[i:i+480],toonhoogte=-3) for i in range(0,len(x),480)])
            b=np.concatenate([two.verwerk_blok(x[i:i+240],toonhoogte=-3) for i in range(0,len(x),240)])
            ok('Streaming onafhankelijk van callbackgrenzen',np.allclose(a,b,atol=2e-4,rtol=1e-3))
        finally: one.sluiten();two.sluiten()
        return {'geslaagd':True,'controles':tests,'meting':benchmarks,
                'interne_vertraging_samples':motor.vertraging_samples,
                'opmerking':'Synthetische audio. Geen luistertest, totale audiovertraging of gamingmeting.'}
    finally: motor.sluiten()


def main():
    ap=argparse.ArgumentParser();ap.add_argument('--dll',type=Path,required=True)
    ap.add_argument('--motor',type=Path,required=True);ap.add_argument('--rapport',type=Path,required=True)
    args=ap.parse_args()
    try:
        spec=importlib.util.spec_from_file_location('drost_native_probe_module',args.motor)
        module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
        result=controleer(module,module.laad_library(args.dll))
        print(f"Native controles geslaagd: {len(result['controles'])}")
    except Exception as exc:
        traceback.print_exc();result={'geslaagd':False,'fout':str(exc)}
    args.rapport.write_text(json.dumps(result,indent=2),encoding='utf-8')
    return 0 if result['geslaagd'] else 1
if __name__=='__main__':raise SystemExit(main())
