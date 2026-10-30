"""Gerichte tests met echte functiecode en vervangende Windows-/appafhankelijkheden.

Deze tests zijn geen complete appintegratietest. HTTP gaat wel over een echte
lokale socket. Er wordt geen Windows-audio of externe stemmotor gestart.
"""
from __future__ import annotations
import ast
import http.client
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import importlib.util
import io
import json
import logging
from pathlib import Path
import re
import secrets
import sys
import tempfile
import threading
import time
from types import ModuleType, SimpleNamespace
import unittest
from unittest.mock import Mock, patch
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parents[1]
SERVICE = ROOT/'app/webinterface/bediening_van_de_audiomotor.py'
SERVER = ROOT/'app/webinterface/lokale_webserver.py'
MIXER = ROOT/'app/audio/live_audiomixer.py'

def load(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod

cleanup = load(ROOT/'app/desktop/afsluitbeheer.py', 'drost413_cleanup')

def function(path, name, **deps):
    tree = ast.parse(path.read_text(encoding='utf-8-sig'))
    nodes = [n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef) and n.name == name]
    if len(nodes) != 1: raise AssertionError(name)
    tree = ast.Module(body=[ast.ImportFrom(module='__future__', names=[ast.alias(name='annotations')],level=0), nodes[0]],type_ignores=[])
    scope = dict(OngeldigeWebactie=ValueError, OngeldigWebverzoek=ValueError, **deps)
    exec(compile(ast.fix_missing_locations(tree),str(path),'exec'),scope)
    return scope[name]

class TestOpruimen(unittest.TestCase):
    def test_stappen_in_volgorde(self):
        seen=[]
        self.assertTrue(cleanup.sluit_onderdelen_af(None,[(str(i), lambda i=i:seen.append(i)) for i in range(5)]))
        self.assertEqual(seen,list(range(5)))
    def test_exception_blokkeert_volgende_stap_niet(self):
        last=Mock();logger=Mock()
        self.assertFalse(cleanup.sluit_onderdelen_af(logger,[('kapot',Mock(side_effect=OSError('test'))),('audio',last)]))
        last.assert_called_once();logger.exception.assert_called_once()
    def test_false_is_geen_succes(self):
        last=Mock(return_value=None)
        self.assertFalse(cleanup.sluit_onderdelen_af(None,[('driver',lambda:False),('overig',last)]))
        last.assert_called_once()
    def test_kapotte_loghandler_blokkeert_audio_niet(self):
        logger=Mock();logger.exception.side_effect=OSError('logboek');last=Mock()
        self.assertFalse(cleanup.sluit_onderdelen_af(logger,[('kapot',lambda:False),('audio',last)]))
        last.assert_called_once()
    def test_webserver_socket_gaat_dicht_bij_fout(self):
        server=Mock();server.shutdown.side_effect=RuntimeError('test')
        with self.assertRaises(RuntimeError):cleanup.sluit_webserver_af(server,Mock(),True)
        server.server_close.assert_called_once()
    def test_nooit_gestarte_server_krijgt_geen_shutdown(self):
        server=Mock()
        self.assertTrue(cleanup.sluit_webserver_af(server,None,False));server.shutdown.assert_not_called()
        server.server_close.assert_called_once()
    def test_levende_serverdraad_wordt_niet_als_succes_gemeld(self):
        server=Mock();thread=Mock();thread.is_alive.return_value=True
        self.assertFalse(cleanup.sluit_webserver_af(server,thread,True));server.server_close.assert_called_once()
    def test_afwezige_server_is_veilig(self):self.assertTrue(cleanup.sluit_webserver_af(None,None,False))

class TestAudioAfsluiten(unittest.TestCase):
    def setUp(self):
        self.service=SimpleNamespace(_bescherm_toestand=threading.RLock(),_wordt_afgesloten=False,
            _volgnummer_van_voorbereiden=3,_wordt_voorbereid='test',logboeken=Mock(),
            _sluit_natuurlijke_stem=Mock(return_value=True),
            stop_stemvoorbeeld=Mock(return_value=None),stop_het_huidige_geluid=Mock(return_value=None),
            mixer=Mock(), monitor=Mock(),_werkdraad_voor_decoderen=Mock())
        self.service.mixer.wacht_tot_verbinding_echt_weg_is.return_value=True
        self.close=function(SERVICE,'sluit_alle_audio_af',sluit_onderdelen_af=cleanup.sluit_onderdelen_af)
    def test_normale_afsluiting(self):
        self.assertTrue(self.close(self.service));self.assertTrue(self.service._wordt_afgesloten)
        self.assertEqual(self.service._volgnummer_van_voorbereiden,4)
        self.assertIsNone(self.service._wordt_voorbereid)
        self.service._werkdraad_voor_decoderen.shutdown.assert_called_once_with(wait=True,cancel_futures=True)
    def test_foute_preview_stopt_nog_steeds_microfoon(self):
        self.service.stop_stemvoorbeeld.side_effect=RuntimeError('test')
        self.assertFalse(self.close(self.service))
        self.service.mixer.verbreek_de_verbinding.assert_called_once()
        self.service.monitor.sluit_monitor.assert_called_once()
        self.service._werkdraad_voor_decoderen.shutdown.assert_called_once()
    def test_foute_soundboardstop_stopt_nog_steeds_microfoon(self):
        self.service.stop_het_huidige_geluid.side_effect=RuntimeError('test')
        self.assertFalse(self.close(self.service));self.service.mixer.verbreek_de_verbinding.assert_called_once()
    def test_foute_driver_stopt_nog_steeds_decoder(self):
        self.service.mixer.wacht_tot_verbinding_echt_weg_is.return_value=False
        self.assertFalse(self.close(self.service));self.service._werkdraad_voor_decoderen.shutdown.assert_called_once()
    def test_geen_nieuwe_verbinding_tijdens_afsluiten(self):
        self.service._wordt_afgesloten=True
        connect=function(SERVICE,'verbind_met_microfoon')
        with self.assertRaisesRegex(ValueError,'WEB-081'):connect(self.service,3)
        self.service.mixer.verbind_de_microfoon_met_vb_cable.assert_not_called()

class TestHTTPAfsluiten(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        tree=ast.parse(SERVER.read_text())
        wanted={'OngeldigWebverzoek','LokaleWebserverVanDrostSoundboard','DrostVerzoekAfhandeling'}
        nodes=[n for n in tree.body if isinstance(n,ast.ClassDef) and n.name in wanted]
        nodes.insert(0,ast.ImportFrom(module='__future__',names=[ast.alias(name='annotations')],level=0))
        scope=dict(BaseHTTPRequestHandler=BaseHTTPRequestHandler,ThreadingHTTPServer=ThreadingHTTPServer,
                   threading=threading,secrets=secrets,json=json,urlsplit=urlsplit,
                   geef_map_voor_beheerde_bestanden=lambda:Path(self.tmp.name),GROOTSTE_JSON_IN_BYTES=100000,
                   time=time,re=re)
        def foutantwoord(error,action):
            code=str(error).split(':')[0]
            return SimpleNamespace(http_status=400,inhoud={'fout':str(error),'foutcode':code,'oorzaakcode':code},logreferentie='test')
        scope.update(maak_webfoutantwoord=foutantwoord,gebruikersmelding=lambda e,**kw:str(e),
                     maak_webantwoord_voor_onbekende_route=lambda code,msg:{'fout':msg,'foutcode':code})
        exec(compile(ast.fix_missing_locations(ast.Module(body=nodes,type_ignores=[])),str(SERVER),'exec'),scope)
        self.server=scope['LokaleWebserverVanDrostSoundboard'](('127.0.0.1',0),Mock())
        self.server.afsluitverzoek=threading.Event()
        self.thread=threading.Thread(target=self.server.serve_forever,kwargs={'poll_interval':.01},daemon=True);self.thread.start()
    def tearDown(self):
        self.server.shutdown();self.server.server_close();self.thread.join(2);self.tmp.cleanup()
    def request(self, method='POST', path='/api/app/afsluiten', data=None, headers=None):
        defaults={'Content-Type':'application/json','X-Drost-Token':self.server.schrijf_token,
                  'Origin':f'http://127.0.0.1:{self.server.server_port}'}
        defaults.update(headers or {})
        c=http.client.HTTPConnection('127.0.0.1',self.server.server_port,timeout=2)
        try:
            # Alleen een schrijfverzoek krijgt JSON. GET dient uitsluitend om
            # de status te lezen en mag geen ongebruikte body achterlaten.
            body = None if method == 'GET' else json.dumps(data if data is not None else {'bevestiging':'AFSLUITEN'})
            c.request(method, path, body=body, headers=defaults)
            r=c.getresponse();return r.status,json.loads(r.read())
        finally:c.close()
    def test_post_met_token_en_bevestiging(self):
        code,data=self.request();self.assertEqual(code,202)
        self.assertTrue(self.server.afsluitverzoek.wait(1));self.assertTrue(self.server.wordt_afgesloten.is_set())
    def test_geen_token_geen_stop(self):
        self.assertEqual(self.request(headers={'X-Drost-Token':''})[0],400)
        self.assertFalse(self.server.afsluitverzoek.is_set())
    def test_verkeerde_origin_geen_stop(self):
        self.assertEqual(self.request(headers={'Origin':'https://andere-website.example'})[0],400)
        self.assertFalse(self.server.afsluitverzoek.is_set())
    def test_verkeerde_host_geen_stop(self):
        self.assertEqual(self.request(headers={'Host':'anders.example'})[0],400)
        self.assertFalse(self.server.afsluitverzoek.is_set())
    def test_geen_bevestiging_geen_stop(self):
        self.assertEqual(self.request(data={})[0],400);self.assertFalse(self.server.afsluitverzoek.is_set())
    def test_extra_gegevens_geweigerd(self):
        self.assertEqual(self.request(data={'bevestiging':'AFSLUITEN','andere':True})[0],400)
    def test_get_sluit_niets(self):
        self.assertEqual(self.request(method='GET')[0],404);self.assertFalse(self.server.afsluitverzoek.is_set())
    def test_herhaald_afsluiten_is_veilig(self):
        self.assertEqual(self.request()[0],202);self.assertEqual(self.request()[0],202)
    def test_unsupported_startwijze_geeft_geen_succes(self):
        self.server.afsluitverzoek=None
        self.assertEqual(self.request()[0],409);self.assertFalse(self.server.wordt_afgesloten.is_set())
    def test_acties_geweigerd_na_afsluitverzoek(self):
        self.request();code,_=self.request(path='/api/verbinden',data={'microfoonnummer':1})
        self.assertEqual(code,400);self.server.bediening.verbind_met_microfoon.assert_not_called()
    def test_status_ondersteuning_komt_uit_server(self):
        module=ModuleType('app.diagnostiek.logboek');module.VERSIE_VAN_DE_APP='test'
        with patch.dict(sys.modules,{'app.diagnostiek.logboek':module}):
            code,data=self.request(method='GET',path='/api/app')
        self.assertEqual(code,200);self.assertTrue(data['afsluiten_ondersteund']);self.assertFalse(data['wordt_afgesloten'])

class TestDesktopAfsluiten(unittest.TestCase):
    def scenario(self, failure=None):
        server=Mock();server.server_port=8765;server.wordt_afgesloten=threading.Event()
        icon=Mock();hotkeys=Mock();audio=Mock();audio.sluit_alle_audio_af.return_value=True
        updater=Mock();updater.pas_toe_voor_audio_start.return_value=False
        lock=Mock();lock.probeer_eigenaarschap_te_krijgen.return_value=True
        logs=Mock();thread=Mock();thread.is_alive.return_value=False
        def run(*,setup):
            server.afsluitverzoek.set();setup(icon)
        icon.run.side_effect=run
        if failure=='hotkeys':hotkeys.stop.side_effect=RuntimeError('hotkey test')
        if failure=='updates':updater.stop.side_effect=RuntimeError('update test')
        if failure=='driver':audio.sluit_alle_audio_af.return_value=False
        if failure=='startup':icon.run.side_effect=RuntimeError('startup test')
        modules={name:ModuleType(name) for name in ('sounddevice','soundfile','soxr','pystray',
            'app.webinterface.bediening_van_de_audiomotor','app.webinterface.lokale_webserver',
            'app.desktop.bediening_van_sneltoetsen','app.desktop.sneltoetsinstellingen','app.desktop.systeemvak')}
        modules['app.webinterface.bediening_van_de_audiomotor'].WebbedieningVanDrostSoundboard=lambda *a:audio
        modules['app.webinterface.lokale_webserver'].LokaleWebserverVanDrostSoundboard=lambda *a:server
        modules['app.desktop.bediening_van_sneltoetsen'].BedieningVanGlobaleSneltoetsen=lambda *a:hotkeys
        modules['app.desktop.sneltoetsinstellingen'].OpslagVanSneltoetsinstellingen=Mock()
        modules['app.desktop.systeemvak'].maak_systeemvakicoon=lambda *a,**kw:icon
        action=function(ROOT/'start_desktop.py','start_drostsoundboard_als_desktopprogramma',
            sys=SimpleNamespace(platform='win32'),EenActieveInstantie=lambda:lock,
            threading=SimpleNamespace(Event=threading.Event,Thread=lambda **kw:thread),
            ReleaseUpdateService=lambda:updater,maak_logboeken_klaar=lambda:logs,
            zet_uitgebreide_foutafhandeling_aan=Mock(),platform=Mock(),os=Mock(),VERSIE_VAN_DE_APP='test',
            schrijf_auditgebeurtenis=Mock(),sluit_logboeken_netjes_af=Mock(),webbrowser=Mock(),
            sluit_onderdelen_af=cleanup.sluit_onderdelen_af,sluit_webserver_af=cleanup.sluit_webserver_af)
        with patch.dict(sys.modules,modules):result=action()
        return SimpleNamespace(result=result,server=server,icon=icon,hotkeys=hotkeys,audio=audio,updater=updater,lock=lock)
    def test_normale_start_en_afsluiten(self):
        r=self.scenario();self.assertEqual(r.result,0);r.audio.sluit_alle_audio_af.assert_called_once()
        r.server.shutdown.assert_called_once();r.lock.laat_vergrendeling_los.assert_called_once()
        r.updater.pas_toe_na_audio_stop.assert_called_once()
    def test_sneltoetsfout_slaat_audio_niet_over(self):
        r=self.scenario('hotkeys');r.audio.sluit_alle_audio_af.assert_called_once();r.server.server_close.assert_called_once()
        r.updater.pas_toe_na_audio_stop.assert_not_called()
    def test_updatefout_slaat_audio_niet_over(self):
        r=self.scenario('updates');r.audio.sluit_alle_audio_af.assert_called_once();r.lock.laat_vergrendeling_los.assert_called_once()
    def test_driver_false_blokkeert_update(self):
        r=self.scenario('driver');self.assertEqual(r.result,1);r.updater.pas_toe_na_audio_stop.assert_not_called()
    def test_opstartfout_ruimt_ook_op(self):
        r=self.scenario('startup');self.assertEqual(r.result,1);r.audio.sluit_alle_audio_af.assert_called_once()
    def test_webstarter_gebruikt_windows_desktopinstantie(self):
        start=Mock(return_value=9);module=ModuleType('start_desktop');module.start_drostsoundboard_als_desktopprogramma=start
        action=function(ROOT/'start_webdashboard.py','start_het_lokale_webdashboard',sys=SimpleNamespace(platform='win32'))
        with patch.dict(sys.modules,{'start_desktop':module}):self.assertEqual(action(),9)
        start.assert_called_once_with(open_browser=True)

if __name__=='__main__':unittest.main()
