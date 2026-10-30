"""Gerichte tests met echte methodes, SQLite en audiosamples.

Niet meegeleverde platformmodules blijven testdubbels. Dit is geen volledige
Windows- of audiostroomtest. De gebruikte productiecode wordt niet herschreven.
"""
from __future__ import annotations
import ast, dataclasses, importlib.util, math, re, sqlite3, sys, tempfile, threading
from pathlib import Path
from contextlib import closing
from types import SimpleNamespace, ModuleType
from queue import SimpleQueue, Empty
from unittest.mock import Mock
import unittest
import numpy as np
from test_beta6410_bediening import method, SERVICE, MIXER, SERVER, ROOT

FAVORITES = ROOT/'app/webinterface/favorieten_en_instellingen.py'
MESSAGES = ROOT/'app/webinterface/gebruikersmeldingen.py'
RUN='11111111-1111-4111-8111-111111111111'


def standalone(path, name):
    spec=importlib.util.spec_from_file_location(name,path)
    module=importlib.util.module_from_spec(spec);sys.modules[name]=module
    spec.loader.exec_module(module)
    return module
messages=standalone(MESSAGES,'test_messages411')


def load_favorites():
    tree=ast.parse(FAVORITES.read_text())
    tree.body=[n for n in tree.body if not isinstance(n,ast.ImportFrom) or not (n.module or '').startswith('app.')]
    mod=ModuleType('test_favorites411');sys.modules[mod.__name__]=mod
    mod.__dict__['bepaal_standaardlocatie_van_de_bibliotheek']=lambda:Path('unused.sqlite')
    exec(compile(tree,str(FAVORITES),'exec'),mod.__dict__)
    return mod
favorites=load_favorites()


class TestOpslag(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.path=Path(self.tmp.name)/'bibliotheek.db'
        with closing(sqlite3.connect(self.path)) as db, db:
            db.execute('CREATE TABLE geluiden(geluid_id TEXT PRIMARY KEY, naam TEXT)')
            db.execute("INSERT INTO geluiden VALUES ('a', 'Eigen geluid')")
    def tearDown(self):self.tmp.cleanup()
    def oud(self, value=63):
        with closing(sqlite3.connect(self.path)) as db, db:
            db.execute('CREATE TABLE algemeen_effectvolume(sleutel INTEGER PRIMARY KEY CHECK(sleutel=1), percentage INTEGER NOT NULL CHECK(percentage BETWEEN 0 AND 100))')
            db.execute('INSERT INTO algemeen_effectvolume VALUES(1, ?)',(value,))
    def test_nieuwe_database_begint_op_75_niet_200(self):
        app=favorites.VasteFavorietenEnInstellingen(self.path)
        self.assertEqual(app.geef_algemeen_effectvolume(),75)
    def test_oude_waarde_en_bibliotheek_blijven_behouden(self):
        self.oud();app=favorites.VasteFavorietenEnInstellingen(self.path)
        self.assertEqual(app.geef_algemeen_effectvolume(),63)
        with closing(sqlite3.connect(self.path)) as db, db:
            self.assertEqual(db.execute('SELECT * FROM geluiden').fetchall(),[('a','Eigen geluid')])
            self.assertEqual(db.execute('SELECT percentage FROM algemeen_effectvolume_voor_beta411').fetchone(),(63,))
    def test_200_wordt_opgeslagen_en_na_herstart_gelezen(self):
        self.oud();app=favorites.VasteFavorietenEnInstellingen(self.path)
        self.assertEqual(app.bewaar_algemeen_effectvolume(200),200)
        app=favorites.VasteFavorietenEnInstellingen(self.path)
        self.assertEqual(app.geef_algemeen_effectvolume(),200)
    def test_stil_blijft_stil_na_migratie(self):
        self.oud(0);app=favorites.VasteFavorietenEnInstellingen(self.path)
        self.assertEqual(app.geef_algemeen_effectvolume(),0)
    def test_migratie_fout_is_atomair(self):
        self.oud()
        with closing(sqlite3.connect(self.path)) as db, db:
            db.execute('BEGIN IMMEDIATE')
            favorites.VasteFavorietenEnInstellingen._maak_volume_tot_200_beschikbaar(db)
            db.rollback()
            schema=db.execute("SELECT sql FROM sqlite_master WHERE name='algemeen_effectvolume'").fetchone()[0]
            self.assertIn('AND 100',schema)
            self.assertIsNone(db.execute("SELECT name FROM sqlite_master WHERE name='algemeen_effectvolume_voor_beta411'").fetchone())
    def test_waarden_buiten_bereik_geweigerd_zonder_schrijven(self):
        app=favorites.VasteFavorietenEnInstellingen(self.path)
        for value in (-1,201,True,2.5,'120',None,float('nan')):
            with self.subTest(value=value),self.assertRaises(ValueError):app.bewaar_algemeen_effectvolume(value)
        self.assertEqual(app.geef_algemeen_effectvolume(),75)
    def test_database_constraint_weigert_201(self):
        app=favorites.VasteFavorietenEnInstellingen(self.path)
        with closing(sqlite3.connect(self.path)) as db, db:
            with self.assertRaises(sqlite3.IntegrityError):db.execute('INSERT INTO algemeen_effectvolume VALUES(1,201)')
    def test_individueel_volume_wordt_niet_door_master_gewijzigd(self):
        app=favorites.VasteFavorietenEnInstellingen(self.path)
        with closing(sqlite3.connect(self.path)) as db, db:
            db.execute("INSERT INTO geluidsinstellingen(geluid_id, volume) VALUES('a', 1.6)")
        app.bewaar_algemeen_effectvolume(180)
        self.assertAlmostEqual(app.geef_instellingen_van_geluid('a').volume,1.6)


class TestLiveBasisvolume(unittest.TestCase):
    def fixture(self, volume=1, master=100):
        fragment=SimpleNamespace(voorbereide_samples=np.full((8192,2),.1,np.float32),
            huidige_framepositie=0,herhalen=False,fade_in_frames=0,basisvolume=volume,
            vorige_basisvolume_factor=volume,afspeelbeurt_id=RUN)
        mixer=SimpleNamespace(_huidige_geluid=fragment,_algemeen_effectvolume_percentage=master,
            _vorige_effectvolume_factor=master/100,_stuur_effect_naar_eigen_headset=None,
            _eigen_stem_monitor_aan=False,_sluit_lopend_geluid_af=Mock(),_audio_opdrachten=SimpleQueue())
        render=method(MIXER,'_verwerk_het_lopende_geluid_in_het_audioblok',np=np,
            _meet_effect_rms_zonder_audio_te_onderbreken=lambda b:float(np.sqrt(np.mean(b*b))))
        process=method(MIXER,'_voer_wachtende_opdrachten_uit',Empty=Empty,MAXIMALE_AANTAL_OPDRACHTEN_PER_AUDIOBLOK=8)
        setbase=method(MIXER,'stel_lopend_basisvolume_in',np=np,LiveVerbindingFout=ValueError,
            _AudioOpdracht=lambda kind,data:SimpleNamespace(soort=kind,gegevens=data))
        return fragment,mixer,render,process,setbase
    def test_master_200_verdubbelt_samples(self):
        f,m,r,_,_=self.fixture(master=200);out=np.zeros((128,2),np.float32);r(m,out)
        self.assertAlmostEqual(float(out.mean()),.2,places=5)
    def test_basis_en_master_werken_samen(self):
        f,m,r,_,_=self.fixture(volume=1.5,master=120);out=np.zeros((128,2),np.float32);r(m,out)
        self.assertAlmostEqual(float(out.mean()),.18,places=5)
    def test_live_slepen_verandert_samples_zonder_positiesprong(self):
        f,m,r,p,setbase=self.fixture();out=np.zeros((128,2),np.float32);r(m,out)
        setbase(m,RUN,1.8);p(m);r(m,np.zeros_like(out));out[:]=0;r(m,out)
        self.assertAlmostEqual(float(out.mean()),.18,places=5)
        self.assertEqual(f.huidige_framepositie,384)
        self.assertIs(m._huidige_geluid,f)
        self.assertTrue(np.all(f.voorbereide_samples==np.float32(.1)))
    def test_volume_nul_kan_live_weer_hoorbaar_worden(self):
        f,m,r,p,setbase=self.fixture(volume=0);out=np.zeros((128,2),np.float32);r(m,out)
        self.assertEqual(float(out.max()),0)
        setbase(m,RUN,1.5);p(m);r(m,np.zeros_like(out));out[:]=0;r(m,out)
        self.assertAlmostEqual(float(out.mean()),.15,places=5)
    def test_oude_afspeelbeurt_verandert_niets(self):
        f,m,r,p,setbase=self.fixture();setbase(m,'22222222-2222-4222-8222-222222222222',0);p(m)
        self.assertEqual(f.basisvolume,1)
    def test_legacy_voorbereid_fragment_krijgt_geen_dubbele_gain(self):
        f,m,r,p,setbase=self.fixture();f.basisvolume=None
        setbase(m,RUN,2);p(m);out=np.zeros((128,2),np.float32);r(m,out)
        self.assertAlmostEqual(float(out.mean()),.1,places=5)
    def test_ongeldige_basiswaarden_worden_geweigerd(self):
        f,m,r,p,setbase=self.fixture()
        for value in (-1,2.01,True,float('inf'),float('nan'),'1'):
            with self.subTest(value=value),self.assertRaises(ValueError):setbase(m,RUN,value)
        self.assertTrue(m._audio_opdrachten.empty())
    def test_volume_ramp_is_geleidelijk(self):
        f,m,r,p,setbase=self.fixture(volume=0);setbase(m,RUN,2);p(m)
        out=np.zeros((128,2),np.float32);r(m,out)
        self.assertLess(float(out[0,0]),.005)
        self.assertAlmostEqual(float(out[-1,0]),.2,places=5)
        self.assertTrue(np.all(np.diff(out[:,0])>0))
    def test_webservice_wijzigt_alleen_geselecteerde_lopende_clip(self):
        service=SimpleNamespace(mixer=Mock(),favorieten=Mock())
        service.mixer.geef_huidige_status.return_value=SimpleNamespace(toestand='verbonden',afspeelbeurt_id=RUN,huidig_geluid_id='a',live_basisvolume=1.)
        action=method(SERVICE,'stel_lopend_basisvolume_in')
        self.assertEqual(action(service,RUN,'a',170),170)
        service.mixer.stel_lopend_basisvolume_in.assert_called_once_with(RUN,1.7)
        self.assertFalse(service.favorieten.mock_calls)
    def test_verkeerd_geluidid_en_oude_beurt_geweigerd(self):
        service=SimpleNamespace(mixer=Mock())
        service.mixer.geef_huidige_status.return_value=SimpleNamespace(toestand='verbonden',afspeelbeurt_id=RUN,huidig_geluid_id='a',live_basisvolume=1.)
        action=method(SERVICE,'stel_lopend_basisvolume_in')
        for run,id in [(RUN,'b'),('oud','a'),(None,'a')]:
            with self.subTest(run=run,id=id),self.assertRaises(ValueError):action(service,run,id,150)
        service.mixer.stel_lopend_basisvolume_in.assert_not_called()
    def handler(self,data):
        service=Mock();service.stel_lopend_basisvolume_in.return_value=150
        h=SimpleNamespace(path='/api/speler/basisvolume',server=SimpleNamespace(bediening=service),
            _controleer_herkomst=Mock(),_lees_invoer_json=Mock(return_value=data),_stuur_json=Mock(),_verwerk_fout=Mock())
        return h,service
    def test_endpoint_bewaakt_token_en_herkomst(self):
        h,s=self.handler({'afspeelbeurt_id':RUN,'geluid_id':'a','percentage':150});method(SERVER,'do_POST')(h)
        h._controleer_herkomst.assert_called_once_with(True)
        s.stel_lopend_basisvolume_in.assert_called_once_with(RUN,'a',150)
        h._stuur_json.assert_called_once_with(200,{'percentage':150,'afspeelbeurt_id':RUN})
    def test_geweigerde_herkomst_wijzigt_geen_audio(self):
        h,s=self.handler({'afspeelbeurt_id':RUN,'geluid_id':'a','percentage':150})
        h._controleer_herkomst.side_effect=ValueError('token');method(SERVER,'do_POST')(h)
        s.stel_lopend_basisvolume_in.assert_not_called();h._verwerk_fout.assert_called_once()
    def test_endpoint_weigert_extra_en_ontbrekende_velden(self):
        for data in ({'percentage':150},{'afspeelbeurt_id':RUN,'geluid_id':'a','percentage':150,'bewaren':True}):
            h,s=self.handler(data);method(SERVER,'do_POST')(h)
            s.stel_lopend_basisvolume_in.assert_not_called();h._verwerk_fout.assert_called_once()
    def test_decoder_bereidt_op_100_voor_mixer_ontvangt_basisvolume(self):
        @dataclasses.dataclass
        class Prepared:
            naam_van_het_geluid:str='old';ingesteld_volume:float=1.;normalisatiestand:str='uit';normalisatiefactor:float=1.
        decoder=Mock(return_value=Prepared())
        mixer=Mock();mixer.geef_huidige_status.return_value=SimpleNamespace(toestand='verbonden',geluidseffecten_aan=True)
        mixer.speel_een_voorbereid_geluid.return_value=RUN
        obj=SimpleNamespace(_bescherm_toestand=threading.Lock(),_volgnummer_van_voorbereiden=1,mixer=mixer,
            recent_en_weergave=Mock(),logboeken=SimpleNamespace(softwarelogboek=Mock(),auditlogboek=Mock()))
        clip=SimpleNamespace(bestandspad=Path('test.wav'),eigen_naam='Test',geluid_id='a')
        settings=SimpleNamespace(begint_bij_seconden=2,maximale_duur_seconden=3,volume=0.)
        action=method(SERVICE,'_bereid_geluid_voor_en_start_als_het_nog_mag',
            lees_en_bereid_mp3_of_wav_voor=decoder,replace=dataclasses.replace,schrijf_auditgebeurtenis=Mock())
        action(obj,1,clip,settings)
        self.assertEqual(decoder.call_args.kwargs['ingesteld_volume'],1.)
        self.assertEqual(mixer.speel_een_voorbereid_geluid.call_args.kwargs['basisvolume'],0.)
        obj.logboeken.softwarelogboek.exception.assert_not_called()


class TestMeldingen(unittest.TestCase):
    def test_verouderde_sessie_legt_herladen_uit(self):
        self.assertIn('eerdere sessie',messages.gebruikersmelding(ValueError('WEB-022: bad token')))
    def test_routinefout_behoudt_herstelactie(self):
        self.assertEqual(messages.gebruikersmelding(ValueError('WEB-002: x')),
            'De gekozen microfoon is niet meer beschikbaar. Vernieuw de apparatenlijst.')
    def test_500_toont_geen_python_pad(self):
        text=messages.gebruikersmelding(RuntimeError(r'Traceback C:\Users\jelle\secret.py'),http_status=500)
        for unwanted in ('Traceback','jelle','secret','Python'):self.assertNotIn(unwanted,text)
    def test_geen_technische_types_in_generieke_invoerfout(self):
        text=messages.gebruikersmelding(ValueError('FAV-002: float32 NaN True'))
        self.assertIn('Controleer je invoer',text)
    def test_gebruikersnaam_nooit_als_technische_fout_teruggestuurd(self):
        text=messages.gebruikersmelding(r'failure at C:\Users\jelle\sound.mp3')
        self.assertNotIn('jelle',text)
    def test_bruikbare_nederlandse_invoerfout_blijft_specifiek(self):
        self.assertEqual(messages.gebruikersmelding(ValueError('TEST-001: kies een kortere mapnaam.')),'Kies een kortere mapnaam.')
    def test_foutstatus_en_logreferentie_blijven_intact(self):
        data={'fout':'raw','foutcode':'WEB-400','oorzaakcode':'WEB-022'}
        answer=SimpleNamespace(http_status=400,inhoud=data,logreferentie='abc123')
        logger=Mock();h=SimpleNamespace(path='/api/test',server=SimpleNamespace(bediening=SimpleNamespace(logboeken=SimpleNamespace(softwarelogboek=logger))),_stuur_json=Mock())
        action=method(SERVER,'_verwerk_fout',maak_webfoutantwoord=lambda *_:answer,gebruikersmelding=messages.gebruikersmelding)
        err=ValueError('WEB-022: token incorrect');action(h,err,'POST /api/test')
        self.assertEqual(h._stuur_json.call_args.args[0],400)
        self.assertEqual(data['oorzaakcode'],'WEB-022')
        self.assertIn('eerdere sessie',data['fout'])
        self.assertIs(logger.error.call_args.kwargs['exc_info'][1],err)
        self.assertEqual(logger.error.call_args.kwargs['extra']['gegevens']['referentie'],'abc123')

if __name__=='__main__':unittest.main()
