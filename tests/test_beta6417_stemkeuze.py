"""Gerichte tests: echte keuze/nabewerkingcode, vervangende audioapparaten/native DLL."""
import io,json,logging,tempfile,threading,unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock,patch
import numpy as np
from app.audio.natuurlijke_stem.varianten import VARIANTEN, catalogus, controleer_variant, Klankbewerking
from app.audio.natuurlijke_stem.dienst import NatuurlijkeStemDienst
from app.webinterface.stemkeuze import StemKeuzeBediening

class TestVarianten417(unittest.TestCase):
    def test_vier_unieke_keuzes(self): self.assertEqual(len({p['id'] for p in catalogus()}),4)
    def test_zelfde_model_eerlijk_gelabeld(self):
        self.assertEqual({p['model_id'] for p in catalogus()},{'koeai-llvc-proef-1'})
        self.assertTrue(all(p['soort']=='klankvariant' for p in catalogus()))
    def test_vier_eigen_pictogrammen(self):self.assertEqual(len({p.icoon for p in VARIANTEN}),4)
    def test_invaliden(self):
        for x in ('oudeman','../model',[],None,42):
            with self.subTest(x=x),self.assertRaises(ValueError):controleer_variant(x)
    def test_basis_gebruikt_geen_dll(self):
        factory=Mock(side_effect=AssertionError('Geen DLL'))
        with Klankbewerking('llvc_basis',motor_factory=factory) as k:
            x=np.ones(200,np.float32)*.12;y=k.verwerk(x)
            np.testing.assert_array_equal(x,y);self.assertIsNot(x,y);self.assertEqual(k.vertraging_ms,0)
        factory.assert_not_called()
    def test_helder_stuurt_andere_parameters_dan_warm(self):
        calls=[]
        for id in ('llvc_helder','llvc_warm'):
            motor=Mock(vertraging_samples=3072);motor.verwerk_blok.side_effect=lambda x,**k:x
            with Klankbewerking(id,motor_factory=lambda sr:motor) as effect:
                effect.verwerk(np.ones(2500,np.float32)*.1);effect.verwerk(np.ones(20,np.float32)*.2)
                self.assertEqual(effect.vertraging_ms,64);self.assertEqual(motor.verwerk_blok.call_count,2)
                calls.append(motor.verwerk_blok.call_args.kwargs)
            motor.sluiten.assert_called_once()
        self.assertGreater(calls[0]['toonhoogte'],0);self.assertLess(calls[1]['toonhoogte'],0)
        self.assertNotEqual(calls[0]['klankkleur'],calls[1]['klankkleur'])
    def test_radio_gebruikt_effect_twee(self):
        motor=Mock(vertraging_samples=3072);motor.verwerk_blok.side_effect=lambda x,**k:x
        with Klankbewerking('llvc_radio',motor_factory=lambda sr:motor) as k:
            k.verwerk(np.zeros(10,np.float32));self.assertEqual(k.vertraging_ms,0)
        self.assertEqual(motor.verwerk_blok.call_args.kwargs['effect'],2)
    def test_geen_nan_aan_nabewerking(self):
        with Klankbewerking('llvc_basis') as k:
            with self.assertRaises(ValueError):k.verwerk(np.array([float('nan')],np.float32))
    def test_pieken_begrensd(self):
        m=Mock(vertraging_samples=0);m.verwerk_blok.side_effect=lambda x,**k:10*x
        with Klankbewerking('llvc_warm',motor_factory=lambda sr:m) as k:
            self.assertLessEqual(float(k.verwerk(np.ones(10,np.float32)).max()),.95001)

class TestOpslag417(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.pad=Path(self.tmp.name)/'stem2_keuze.json'
        self.d=NatuurlijkeStemDienst(self.pad,logging.getLogger('test417'),autostart=False)
    def tearDown(self):self.d.sluiten();self.tmp.cleanup()
    def test_selecteren_zonder_start(self):
        with patch.object(self.d,'_run') as run:self.d.kies_variant('llvc_warm',aan=False)
        run.assert_not_called();self.assertFalse(self.d.aan);self.assertTrue(self.d.gekozen)
        self.assertEqual(json.loads(self.pad.read_text())['variant'],'llvc_warm')
    def test_selectie_blijft_na_herstart(self):
        self.d.kies_variant('llvc_helder',aan=False)
        s=NatuurlijkeStemDienst(self.pad,logging.getLogger('test417'))
        try:self.assertEqual(s.variant,'llvc_helder');self.assertTrue(s.gekozen);self.assertFalse(s.aan)
        finally:s.sluiten()
    def test_oude_aan_keuze_wordt_basis(self):
        self.pad.write_text(json.dumps({'schema':1,'aan':True,'bufferprofiel':'direct'}))
        with patch.object(NatuurlijkeStemDienst,'stel_in') as start:
            s=NatuurlijkeStemDienst(self.pad,logging.getLogger('test417'))
        start.assert_called_once_with(True,bewaren=False)
        self.assertEqual(s.variant,'llvc_basis');self.assertTrue(s.gekozen);self.assertEqual(s.bufferprofiel,'direct');s.sluiten()
    def test_oude_uit_keuze_blijft_effect(self):
        self.pad.write_text('{"schema":1,"aan":false}')
        s=NatuurlijkeStemDienst(self.pad,logging.getLogger('test417'));self.assertFalse(s.gekozen);s.sluiten()
    def test_ongeldige_variant_verandert_niets(self):
        with self.assertRaises(ValueError):self.d.kies_variant('onbekend')
        self.assertFalse(self.pad.exists());self.assertFalse(self.d.gekozen)
    def test_opslaan_mislukt_herstelt_selectie(self):
        with patch.object(self.d,'_save',side_effect=OSError('test')),self.assertRaises(OSError):self.d.kies_variant('llvc_warm',aan=False)
        self.assertEqual(self.d.variant,'llvc_basis');self.assertFalse(self.d.gekozen)
    def test_terug_naar_effect_wist_oude_audio(self):
        self.d.kies_variant('llvc_basis',aan=False);self.d._out=np.ones(20,np.float32)
        self.d.kies_gewone_effecten();self.assertFalse(self.d.gekozen);self.assertEqual(len(self.d._out),0)
    def test_selectie_tijdens_test_geweigerd(self):
        self.d._test_only=True
        with self.assertRaises(ValueError):self.d.kies_variant('llvc_warm')
        self.assertFalse(self.pad.exists());self.d._test_only=False
    def test_rapport_benoemt_hetzelfde_model_en_variant(self):
        self.d.kies_variant('llvc_radio',aan=False);r=self.d.geef_rapport()
        self.assertEqual(r['stemnaam'],'Omroeper');self.assertEqual(r['aantal_modellen'],1)
        self.assertEqual(r['aantal_klankvarianten'],4);self.assertIsNone(r['totale_audiovertraging_ms'])
    def test_geen_stem_uit_foutieve_bestanden(self):
        self.pad.write_text('{"aan":true,"variant":"onbekend"}')
        d=NatuurlijkeStemDienst(self.pad,logging.getLogger('test417'))
        try:self.assertEqual(d.status()['toestand'],'fout');self.assertTrue(d.aan);self.assertTrue(d.gekozen)
        finally:d.sluiten()

class TestKeuzeController417(unittest.TestCase):
    def setUp(self):
        self.c=StemKeuzeBediening();self.c._wordt_afgesloten=False;self.c._bescherm_toestand=threading.RLock()
        self.c._stemkeuze_generatie=0;self.c.stemkeuze_voorbeelden=Mock()
        self.c.favorieten=Mock();self.c.favorieten.geef_stemvervormer_aan.return_value=False
        self.c.favorieten.geef_stemprofiel.return_value='robot'
        self.c.stemvoorbeeld=Mock(actief=False);self.c.mixer=Mock();self.c.stop_stemvoorbeeld=Mock()
        self.c.natuurlijke_stem=Mock(aan=True,gekozen=True,variant='llvc_basis')
        self.c.natuurlijke_stem.status.return_value={'test_bezig':False,'toestand':'actief'}
        self.c.geef_steminstellingen=Mock(return_value={'ok':True})
        self.c.stel_stemvervormer_aan_in=Mock()
    def test_gewone_kaart_kan_llvc_verlaten(self):
        self.c.kies_stem('robot')
        self.c.natuurlijke_stem.kies_gewone_effecten.assert_called_once()
        self.c.mixer.stel_stemprofiel_in.assert_called_once_with('robot')
        self.c.mixer.stel_stemvervormer_aan_in.assert_called_once_with(True)
    def test_wisselen_naar_normaal_is_bewuste_keuze(self):
        self.c.kies_stem('normaal');self.c.mixer.stel_stemprofiel_in.assert_called_once_with('normaal')
    def test_effect_klaar_voordat_llvc_uitgaat(self):
        calls=[]
        self.c.mixer.stel_stemprofiel_in.side_effect=lambda p:calls.append('profiel')
        self.c.mixer.stel_stemvervormer_aan_in.side_effect=lambda x:calls.append('actief')
        self.c.natuurlijke_stem.kies_gewone_effecten.side_effect=lambda:calls.append('llvc_uit')
        self.c.kies_stem('robot');self.assertEqual(calls,['profiel','actief','llvc_uit'])
    def test_bij_mislukte_effectwissel_blijft_llvc_eigenaar(self):
        self.c.mixer.stel_stemprofiel_in.side_effect=RuntimeError('test')
        with self.assertRaises(RuntimeError):self.c.kies_stem('robot')
        self.c.natuurlijke_stem.kies_gewone_effecten.assert_not_called()
    def test_nieuwe_variant_blijft_aan(self):
        self.c.kies_stem('llvc_warm');self.c.natuurlijke_stem.kies_variant.assert_called_once_with('llvc_warm',aan=True)
    def test_uitgeschakelde_keuze_blijft_uit(self):
        self.c.natuurlijke_stem.aan=False;self.c.kies_stem('llvc_helder')
        self.c.natuurlijke_stem.kies_variant.assert_called_once_with('llvc_helder',aan=False)
    def test_actief_effect_neemt_aanstand_mee(self):
        self.c.natuurlijke_stem.gekozen=False;self.c.favorieten.geef_stemvervormer_aan.return_value=True
        self.c.kies_stem('llvc_basis');self.c.natuurlijke_stem.kies_variant.assert_called_once_with('llvc_basis',aan=True)
    def test_invaliden_schakelen_niets_uit(self):
        for x in ('onbekend',[],None,'../../worker'):
            with self.subTest(x=x),self.assertRaises(ValueError):self.c.kies_stem(x)
        self.c.natuurlijke_stem.kies_gewone_effecten.assert_not_called();self.c.stemkeuze_voorbeelden.annuleer.assert_not_called()
    def test_geselecteerde_llvc_kan_uit(self):
        self.c.schakel_stemkeuze(False);self.c.natuurlijke_stem.stel_in.assert_called_once_with(False)
        self.c.mixer.stel_stemvervormer_aan_in.assert_called_once_with(False)
    def test_geen_per_ongeluk_oude_effecten_bij_uitzetten(self):
        calls=[];self.c.mixer.stel_stemvervormer_aan_in.side_effect=lambda x:calls.append('effect_uit')
        self.c.natuurlijke_stem.stel_in.side_effect=lambda x:calls.append('llvc_uit')
        self.c.schakel_stemkeuze(False);self.assertEqual(calls,['effect_uit','llvc_uit'])
    def test_niet_tijdens_computertest(self):
        self.c.natuurlijke_stem.status.return_value={'test_bezig':True}
        with self.assertRaises(ValueError):self.c.kies_stem('robot')
    def test_niet_tijdens_afsluiten(self):
        self.c._wordt_afgesloten=True
        with self.assertRaises(ValueError):self.c.kies_stem('robot')
    def test_wisselen_annuleert_voorbeeld(self):
        self.c.kies_stem('robot');self.c.stemkeuze_voorbeelden.annuleer.assert_called_once();self.assertEqual(self.c._stemkeuze_generatie,1)
    def test_gewone_schakelaar_blijft_beschikbaar(self):
        self.c.natuurlijke_stem.gekozen=False;self.c.schakel_stemkeuze(True)
        self.c.stel_stemvervormer_aan_in.assert_called_once_with(True)
    def test_uit_variant_stopt_bestaande_eigen_preview(self):
        self.c.natuurlijke_stem.aan=False;self.c.stemvoorbeeld.actief=True
        self.c.kies_stem('llvc_warm');self.c.stop_stemvoorbeeld.assert_called_once()


class TestVoorbeeldKeuze417(unittest.TestCase):
    def setUp(self):
        self.c=StemKeuzeBediening();self.c._wordt_afgesloten=False
        self.c._bescherm_toestand=threading.RLock();self.c._stemkeuze_generatie=3
        self.c._stemvoorbeeld_render_slot=threading.Lock()
        self.c.favorieten=Mock();self.params={'robot':{'metaal':50}}
        self.c.favorieten.geef_stemparameters.return_value=self.params
        self.c.favorieten.geef_stemprofiel.return_value='robot'
        self.c.stemvoorbeeld=Mock(actief=False)
        self.c.natuurlijke_stem=Mock(aan=True,gekozen=True,variant='llvc_warm')
        self.c.natuurlijke_stem.status.return_value={'test_bezig':False,'toestand':'actief'}
        self.c.stemkeuze_voorbeelden=Mock()
        self.c.maak_voorbeeldstem_wav=Mock(return_value=b'gewone-wav')
        self.bron=Mock(return_value=b'ingebouwde-wav')
        import sys
        naam='app.audio.ingebouwde_stemvoorbeelden'
        vorige=sys.modules.get(naam)
        sys.modules[naam]=SimpleNamespace(render_voorbeeld=self.bron)
        def herstel():
            if vorige is None:sys.modules.pop(naam,None)
            else:sys.modules[naam]=vorige
        self.addCleanup(herstel)
    def test_llvc_krijgt_het_onbewerkte_voorbeeld_en_volledige_parameterstructuur(self):
        def render(maak_bron,variant,verzoek,**kw):
            self.assertEqual(maak_bron(),b'ingebouwde-wav')
            self.assertEqual((variant,verzoek),('llvc_warm','verzoek_001'))
            return b'model-wav'
        self.c.stemkeuze_voorbeelden.render.side_effect=render
        self.assertEqual(self.c.maak_stemkeuze_voorbeeld('bob','llvc_warm','verzoek_001'),b'model-wav')
        self.bron.assert_called_once_with('bob','normaal',100,self.params)
        self.c.maak_voorbeeldstem_wav.assert_not_called()
        self.assertTrue(self.c._stemvoorbeeld_render_slot.acquire(blocking=False))
        self.c._stemvoorbeeld_render_slot.release()
    def test_nieuwe_keuze_maakt_pending_voorbeeld_ongeldig(self):
        self.c.maak_stemkeuze_voorbeeld('elise','llvc_warm','verzoek_002')
        geldig=self.c.stemkeuze_voorbeelden.render.call_args.kwargs['nog_geldig']
        self.assertTrue(geldig());self.c._stemkeuze_generatie+=1;self.assertFalse(geldig())
    def test_afsluiten_maakt_pending_voorbeeld_ongeldig(self):
        self.c.maak_stemkeuze_voorbeeld('bob','llvc_warm','verzoek_003')
        geldig=self.c.stemkeuze_voorbeelden.render.call_args.kwargs['nog_geldig']
        self.c._wordt_afgesloten=True;self.assertFalse(geldig())
    def test_onbekende_spreker_start_geen_verwerking(self):
        with self.assertRaises(ValueError):self.c.maak_stemkeuze_voorbeeld('vreemd','llvc_warm','verzoek_004')
        self.c.stemkeuze_voorbeelden.render.assert_not_called()
    def test_achterhaalde_stem_start_geen_verwerking(self):
        with self.assertRaises(ValueError):self.c.maak_stemkeuze_voorbeeld('bob','llvc_basis','verzoek_005')
        self.c.stemkeuze_voorbeelden.render.assert_not_called()
    def test_eigen_microfoontest_wordt_niet_met_demo_gemengd(self):
        self.c.stemvoorbeeld.actief=True
        with self.assertRaises(ValueError):self.c.maak_stemkeuze_voorbeeld('bob','llvc_warm','verzoek_006')
        self.c.stemkeuze_voorbeelden.render.assert_not_called()
    def test_gewone_stem_gebruikt_bestaande_rendering(self):
        self.c.natuurlijke_stem.gekozen=False
        self.assertEqual(self.c.maak_stemkeuze_voorbeeld('elise','robot','verzoek_007'),b'gewone-wav')
        self.c.maak_voorbeeldstem_wav.assert_called_once_with('elise')
        self.c.stemkeuze_voorbeelden.render.assert_not_called()
    def test_ladende_motor_krijgt_geen_tweede_start(self):
        self.c.natuurlijke_stem.status.return_value={'test_bezig':False,'toestand':'laden'}
        with self.assertRaises(ValueError):self.c.maak_stemkeuze_voorbeeld('bob','llvc_warm','verzoek_008')
        self.c.stemkeuze_voorbeelden.render.assert_not_called()

if __name__=='__main__':unittest.main()
