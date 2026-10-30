"""6.1 Beta 4: veiligheid en compatibiliteit van mappen, audiopacks en populariteit."""
from __future__ import annotations
from contextlib import closing
from io import BytesIO
import json
from pathlib import Path
import sqlite3
from tempfile import TemporaryDirectory
import os
import threading
from urllib.error import HTTPError
from urllib.request import Request, urlopen
from unittest import TestCase
from unittest.mock import Mock
import unittest
from zipfile import ZipFile
import wave

from app.audio.geluidenbibliotheek import PersoonlijkeGeluidenbibliotheek
from app.webinterface.geluidsgroepen import PersoonlijkeGeluidsgroepen, GroepsinstellingOngeldig
from app.webinterface.recente_geluiden_en_weergave import RecenteGeluidenEnWeergave
from app.webinterface.bibliotheek_archieven import (
    bekijk_inhoud_audiopack, importeer_draagbaar_bibliotheekarchief,
    maak_draagbaar_bibliotheekarchief, OngeldigBibliotheekarchief
)
from app.diagnostiek.logboek import maak_logboeken_klaar, sluit_logboeken_netjes_af
from app.webinterface.bediening_van_de_audiomotor import WebbedieningVanDrostSoundboard
from app.webinterface.lokale_webserver import LokaleWebserverVanDrostSoundboard


def maak_wav(pad: Path):
    pad.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(pad), 'wb') as uitvoer:
        uitvoer.setnchannels(1)
        uitvoer.setsampwidth(2)
        uitvoer.setframerate(16000)
        uitvoer.writeframes(b'\x00\x00' * 16000)


class TestGenesteMappenEnPopulariteit(TestCase):
    def setUp(self):
        self.tijdelijk = TemporaryDirectory()
        self.addCleanup(self.tijdelijk.cleanup)
        self.root = Path(self.tijdelijk.name)
        self.db = self.root / 'bibliotheek.sqlite3'
        self.bibliotheek = PersoonlijkeGeluidenbibliotheek(self.db)
        self.groepen = PersoonlijkeGeluidsgroepen(self.db)
        self.history = RecenteGeluidenEnWeergave(self.db)
        bron = self.root / 'geluid.wav'
        maak_wav(bron)
        self.item = self.bibliotheek.voeg_geluidsbestanden_toe([bron])[0]

    def test_migratie_oud_gaat_niet_ten_koste_van_bestaande_regels(self):
        # Nieuw aangemaakte database simuleert de oude globale naamstructuur.
        with closing(sqlite3.connect(self.db)) as db:
            met = db.execute('PRAGMA table_info(geluidsgroepen)').fetchall()
        self.assertNotIn('ouder_id', {r[1] for r in met})
        with closing(sqlite3.connect(self.db)) as db:
            db.execute("INSERT INTO geluidsgroepen VALUES ('ouderwetse-groep', 'Oude groep', '2026')")
            db.commit()
        # Oude code met drie kolommen moet na een rollback nog schrijven.
        self.assertIn('Oude groep', [g['naam'] for g in self.groepen.geef_alle_groepen()])
        movies = self.groepen.maak_groep('Movies')
        sub = self.groepen.maak_groep('Star Wars', movies)
        heropen = PersoonlijkeGeluidsgroepen(self.db)
        self.assertEqual({g['id']: g['ouder_id'] for g in heropen.geef_alle_groepen()}[sub], movies)
        heropen.verander_lidmaatschap(sub, self.item.geluid_id, True)
        self.assertEqual(heropen.geef_groepsnummers_per_geluid()[self.item.geluid_id], [sub])

    def test_verplaatsen_weigert_cyclus_en_verdwijnende_map(self):
        hoofd = self.groepen.maak_groep('Films')
        child = self.groepen.maak_groep('Actie', hoofd)
        with self.assertRaisesRegex(GroepsinstellingOngeldig,'GROEP-010'):
            self.groepen.verplaats_groep(hoofd, child)
        with self.assertRaisesRegex(GroepsinstellingOngeldig,'GROEP-011'):
            self.groepen.verplaats_groep(child, 'aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa')
        self.assertEqual({g['id']: g['ouder_id'] for g in self.groepen.geef_alle_groepen()}[child], hoofd)
        self.groepen.verplaats_groep(child, None)
        self.assertIsNone({g['id']: g['ouder_id'] for g in self.groepen.geef_alle_groepen()}[child])

    def test_verwijder_bovenmap_behoudt_submap_en_geluid(self):
        a = self.groepen.maak_groep('Media')
        b = self.groepen.maak_groep('Games', a)
        self.groepen.verander_lidmaatschap(b, self.item.geluid_id, True)
        self.groepen.verwijder_groep(a)
        self.assertIsNone({g['id']: g['ouder_id'] for g in self.groepen.geef_alle_groepen()}[b])
        self.assertTrue(self.item.bestandspad.exists())
        self.assertIn(b, self.groepen.geef_groepsnummers_per_geluid()[self.item.geluid_id])

    def test_populariteit_telt_alleen_uitzenden_en_niet_dubbel(self):
        self.history.registreer_afspelen(self.item.geluid_id,'Ping','preview','p-1')
        self.assertEqual(self.history.geef_afspeelaantallen().get(self.item.geluid_id,0),0)
        self.history.registreer_afspelen(self.item.geluid_id,'Ping','gesprek','g-1')
        self.history.registreer_afspelen(self.item.geluid_id,'Ping','gesprek','g-1')
        self.history.registreer_afspelen(self.item.geluid_id,'Ping','gesprek','g-2')
        self.assertEqual(RecenteGeluidenEnWeergave(self.db).geef_afspeelaantallen()[self.item.geluid_id],2)


class TestAudiopackSelectie(TestCase):
    def setUp(self):
        self.tijdelijk = TemporaryDirectory()
        self.addCleanup(self.tijdelijk.cleanup)
        self.root = Path(self.tijdelijk.name)
        self.logs = maak_logboeken_klaar(self.root/'logs')
        self.addCleanup(sluit_logboeken_netjes_af,self.logs)
        self.bediening = WebbedieningVanDrostSoundboard(Mock(), self.logs, self.root/'db.sqlite3')
        self.addCleanup(self.bediening.sluit_alle_audio_af)
        self.media = self.root/'media'
        self.media.mkdir()
        self.wav = self.root/'bron.wav'
        maak_wav(self.wav)
        self.item = self.bediening.geluidenbibliotheek.voeg_geluidsbestanden_toe([self.wav])[0]

    def test_export_behoudt_geneste_mappen_en_selectieve_import(self):
        film=self.bediening.groepen.maak_groep('Movies')
        star=self.bediening.groepen.maak_groep('Star Wars',film)
        self.bediening.groepen.verander_lidmaatschap(star,self.item.geluid_id,True)
        self.bediening.geluidenbibliotheek.verander_de_naam_van_een_geluid(self.item.geluid_id,'Soundtrack')
        pad=maak_draagbaar_bibliotheekarchief(self.bediening,self.media,[self.item.geluid_id])
        self.addCleanup(pad.unlink,missing_ok=True)
        toon=bekijk_inhoud_audiopack(pad)
        self.assertEqual(toon['geluiden'][0]['groepspaden'],[['Movies','Star Wars']])
        self.assertEqual(toon['geluiden'][0]['naam'],'Soundtrack')
        leeg=importeer_draagbaar_bibliotheekarchief(self.bediening,self.media,pad,selectie=[])
        self.assertEqual(leeg['aantal'],0)
        resultaat=importeer_draagbaar_bibliotheekarchief(self.bediening,self.media,pad,selectie=[0])
        self.assertEqual(resultaat['aantal'],1)
        self.assertEqual(len(self.bediening.geluidenbibliotheek.geef_alle_geluiden()),2)
        self.assertEqual(len(self.bediening.groepen.geef_alle_groepen()),2)

    def test_zip_met_normale_submappen_werkt_en_met_selectie(self):
        pakket=self.root/'pakket.zip'
        with ZipFile(pakket,'w') as z:
            z.write(self.wav,'Films/Actie/Film_A.wav')
            z.write(self.wav,'Films/Actie/Film_B.wav')
        resultaat=bekijk_inhoud_audiopack(pakket)
        self.assertEqual(resultaat['aantal'],2)
        self.assertEqual(resultaat['geluiden'][0]['groepspaden'],[['Films','Actie']])
        self.assertEqual(importeer_draagbaar_bibliotheekarchief(self.bediening,self.media,pakket,selectie=[1])['aantal'],1)
        self.assertEqual(len(self.bediening.geluidenbibliotheek.geef_alle_geluiden()),2)

    def test_onveilige_zip_paden_of_selecties_worden_geweigerd(self):
        pakket=self.root/'onveilig.zip'
        with ZipFile(pakket,'w') as z:
            z.write(self.wav,'../slecht.wav')
        with self.assertRaisesRegex(OngeldigBibliotheekarchief,'ARCH-021'):
            bekijk_inhoud_audiopack(pakket)
        pakket=self.root/'gewoon.zip'
        with ZipFile(pakket,'w') as z:
            z.write(self.wav,'schoon.wav')
        with self.assertRaisesRegex(OngeldigBibliotheekarchief,'ARCH-023'):
            importeer_draagbaar_bibliotheekarchief(self.bediening,self.media,pakket,selectie=[23])
        self.assertEqual(len(self.bediening.geluidenbibliotheek.geef_alle_geluiden()),1)


class TestDashboardNieuweIndeling(TestCase):
    def test_apparte_bibliotheekpagina_en_compacte_stem(self):
        root=Path(__file__).resolve().parents[1]/'app/webinterface/statisch'
        html=(root/'dashboard.html').read_text(encoding='utf-8')
        js=(root/'dashboard.js').read_text(encoding='utf-8')
        css=(root/'stijl.css').read_text(encoding='utf-8')
        self.assertIn('id="bibliotheek-pagina"',html)
        self.assertNotIn('id="dialoog-bibliotheek"',html)
        self.assertIn('id="snel-stem-keuze"',html)
        self.assertIn('href="#instellingen-stem"', html)
        self.assertIn("pagina === '#instellingen-stem'", js)
        self.assertIn('id="audiopack-boom"',html)
        self.assertIn('id="dialoog-map-beheer"',html)
        self.assertIn('id="formulier-map-beheer"',html)
        self.assertIn("'populair'",js)
        self.assertIn('max-height:min(58vh,620px)',css)
        self.assertIn('audiopackSelectie',js)
        self.assertIn("window.location.hash='#bibliotheek'",js)


class TestAudiopackHttpApi(TestCase):
    def setUp(self):
        self.tijdelijk=TemporaryDirectory()
        self.addCleanup(self.tijdelijk.cleanup)
        self.map=Path(self.tijdelijk.name)
        self.oudedata=os.environ.get('LOCALAPPDATA')
        os.environ['LOCALAPPDATA']=str(self.map)
        self.addCleanup(self.herstel_env)
        self.logs=maak_logboeken_klaar(self.map/'logs')
        self.addCleanup(sluit_logboeken_netjes_af,self.logs)
        self.bediening=WebbedieningVanDrostSoundboard(Mock(),self.logs,self.map/'database.sqlite3')
        self.addCleanup(self.bediening.sluit_alle_audio_af)
        self.server=LokaleWebserverVanDrostSoundboard(('127.0.0.1',0),self.bediening)
        self.draad=threading.Thread(target=self.server.serve_forever,daemon=True)
        self.draad.start()
        self.addCleanup(self.stop_server)
        self.url=f'http://127.0.0.1:{self.server.server_port}'

    def herstel_env(self):
        if self.oudedata is None: os.environ.pop('LOCALAPPDATA',None)
        else: os.environ['LOCALAPPDATA']=self.oudedata

    def stop_server(self):
        self.server.shutdown();self.server.server_close();self.draad.join(timeout=3)

    def vraag(self,route,body,token=True):
        headers={'Content-Type':'application/octet-stream'}
        if token: headers['X-Drost-Token']=self.server.schrijf_token
        req=Request(self.url+route,data=body,headers=headers,method='POST')
        with urlopen(req,timeout=5) as antwoord:
            return antwoord.status,json.loads(antwoord.read())

    def test_api_herkent_dubbel_via_hash_en_slaat_standaard_over(self):
        wav=self.map/'bestaand.wav';maak_wav(wav)
        self.bediening.geluidenbibliotheek.voeg_geluidsbestanden_toe([wav])
        with BytesIO() as tijdelijk:
            with ZipFile(tijdelijk,'w') as archief:
                archief.write(wav,'Herbenoemd.wav')
            zipbytes=tijdelijk.getvalue()
        status,voorbeeld=self.vraag('/api/bibliotheek/audiopack-bekijk',zipbytes)
        self.assertEqual(status,200)
        self.assertTrue(voorbeeld['geluiden'][0]['al_aanwezig'])
        status,resultaat=self.vraag('/api/bibliotheek/importeer?selectie=0',zipbytes)
        self.assertEqual(status,201)
        self.assertEqual(resultaat['aantal'],0)
        self.assertEqual(resultaat['overgeslagen'],1)
        self.assertEqual(len(self.bediening.geluidenbibliotheek.geef_alle_geluiden()),1)
        status,resultaat=self.vraag('/api/bibliotheek/importeer?selectie=0&dubbelen=toestaan',zipbytes)
        self.assertEqual(resultaat['aantal'],1)

    def test_stemmonitor_api_bewaart_instelling_en_weigert_foute_requests(self):
        def vraag_stemmonitor(payload, token=True):
            headers = {'Content-Type': 'application/json'}
            if token:
                headers['X-Drost-Token'] = self.server.schrijf_token
            verzoek = Request(self.url + '/api/monitor-stem', data=payload,
                              headers=headers, method='POST')
            with urlopen(verzoek, timeout=5) as antwoord:
                return antwoord.status, json.loads(antwoord.read())

        body=json.dumps({'aan':True,'volume':35}).encode('utf-8')
        with self.assertRaises(HTTPError) as fout:
            vraag_stemmonitor(body,token=False)
        self.assertEqual(fout.exception.code,400)
        with self.assertRaises(HTTPError) as fout:
            vraag_stemmonitor(json.dumps({'aan':True,'volume':0}).encode())
        self.assertEqual(fout.exception.code,400)
        status,antwoord=vraag_stemmonitor(body)
        self.assertEqual(status,200)
        self.assertTrue(antwoord['aan'])
        self.assertEqual(antwoord['volume'],35)
        with urlopen(self.url+'/api/status',timeout=5) as antwoord:
            toestand=json.loads(antwoord.read())
        self.assertTrue(toestand['eigen_stem_horen_aan'])
        self.assertEqual(toestand['eigen_stem_horen_volume'],35)

    def test_volledige_export_toont_eerst_een_overzicht(self):
        wav=self.map/'voorbeeld.wav';maak_wav(wav)
        self.bediening.geluidenbibliotheek.voeg_geluidsbestanden_toe([wav])
        with urlopen(self.url+'/api/bibliotheek/exportoverzicht',timeout=5) as antwoord:
            gegevens=json.loads(antwoord.read())
        self.assertEqual(gegevens['aantal'],1)
        self.assertEqual(gegevens['max_geluiden'],500)
        self.assertTrue(gegevens['kan_exporteren'])

    def test_beveiligde_zip_preview_en_gerichte_import(self):
        wav=self.map/'sample.wav';maak_wav(wav)
        with BytesIO() as tijdelijk:
            with ZipFile(tijdelijk,'w') as archief:
                archief.write(wav,'Movies/Star Wars/sound_one.wav')
                archief.write(wav,'Movies/Star Wars/sound_two.wav')
            gegevens=tijdelijk.getvalue()
        with self.assertRaises(HTTPError) as fout:
            self.vraag('/api/bibliotheek/audiopack-bekijk',gegevens,token=False)
        self.assertEqual(fout.exception.code,400)
        status,voorbeeld=self.vraag('/api/bibliotheek/audiopack-bekijk',gegevens)
        self.assertEqual(status,200)
        self.assertEqual(voorbeeld['aantal'],2)
        self.assertEqual(voorbeeld['geluiden'][0]['groepspaden'],[['Movies','Star Wars']])
        status,ingevoerd=self.vraag('/api/bibliotheek/importeer?selectie=1&dubbelen=toestaan',gegevens)
        self.assertEqual(status,201)
        self.assertEqual(ingevoerd['aantal'],1)
        self.assertEqual(len(self.bediening.geluidenbibliotheek.geef_alle_geluiden()),1)
        groepen=self.bediening.groepen.geef_alle_groepen()
        self.assertEqual({g['naam'] for g in groepen},{'Movies','Star Wars'})
        self.assertEqual(next(g['ouder_id'] for g in groepen if g['naam']=='Star Wars'),
                         next(g['id'] for g in groepen if g['naam']=='Movies'))

if __name__=='__main__':unittest.main()
