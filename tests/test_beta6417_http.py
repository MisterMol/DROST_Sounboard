"""Werkelijke lokale HTTP-sockets. De audio-uitvoer zelf is hier een testvervanger."""
import http.client,json,unittest
from urllib.parse import parse_qs
import test_beta6413_afsluiten as basis

class TestStemKeuzeHTTP417(unittest.TestCase):
    def setUp(self):
        basis.TestHTTPAfsluiten.setUp(self)
        self.server.RequestHandlerClass.do_GET.__globals__['parse_qs']=parse_qs
        self.server.bediening.kies_stem.return_value={'profiel':'robot'}
        self.server.bediening.schakel_stemkeuze.return_value={'actief':True}
        self.server.bediening.geef_stemkeuze.return_value={'profiel':'robot'}
        self.server.bediening.stop_stemkeuze_voorbeeld.return_value={'gestopt':True}
        self.server.bediening.maak_stemkeuze_voorbeeld.return_value=b'RIFFtest'
    tearDown=basis.TestHTTPAfsluiten.tearDown
    def request(self,path='/api/stemkeuze',data=None,headers=None,method='POST'):
        default={'Content-Type':'application/json','X-Drost-Token':self.server.schrijf_token,'Origin':f'http://127.0.0.1:{self.server.server_port}'}
        default.update(headers or {})
        c=http.client.HTTPConnection('127.0.0.1',self.server.server_port,timeout=3)
        try:
            # GET heeft geen JSON-body. Een ongelezen body kan op Windows
            # bij het afwijzen van een verzoek een socket-reset veroorzaken.
            body = None if method == 'GET' else json.dumps({} if data is None else data)
            c.request(method, path, body=body, headers=default)
            r=c.getresponse();return r.status,r.read(),r.getheader('Content-Type')
        finally:c.close()
    def test_selecteren_met_token(self):
        self.assertEqual(self.request(data={'keuze':'llvc_warm'})[0],200)
        self.server.bediening.kies_stem.assert_called_once_with('llvc_warm')
    def test_status_get_selecteert_niets(self):
        self.assertEqual(self.request(method='GET')[0],200);self.server.bediening.kies_stem.assert_not_called()
    def test_selectie_zonder_token_geweigerd(self):self.assertEqual(self.request(data={'keuze':'robot'},headers={'X-Drost-Token':''})[0],400)
    def test_selectie_met_vreemde_origin_geweigerd(self):self.assertEqual(self.request(data={'keuze':'robot'},headers={'Origin':'https://extern.example'})[0],400)
    def test_selectie_met_vreemde_host_geweigerd(self):self.assertEqual(self.request(data={'keuze':'robot'},headers={'Host':'extern.example'})[0],400)
    def test_selectie_extra_velden_geweigerd(self):self.assertEqual(self.request(data={'keuze':'robot','pad':'worker.exe'})[0],400)
    def test_selectie_ongeldig_type(self):self.assertEqual(self.request(data={'keuze':[]})[0],400)
    def test_inschakelen(self):self.assertEqual(self.request('/api/stemkeuze/actief',{'aan':True})[0],200)
    def test_inschakelen_geen_getal(self):self.assertEqual(self.request('/api/stemkeuze/actief',{'aan':1})[0],400)
    def test_voorbeeld_get_met_token(self):
        code,wav,mime=self.request('/api/stemkeuze/voorbeeld?spreker=bob&keuze=llvc_basis&verzoek=demoverzoek_417',method='GET')
        self.assertEqual(code,200);self.assertEqual(wav,b'RIFFtest');self.assertEqual(mime,'audio/wav')
        self.server.bediening.maak_stemkeuze_voorbeeld.assert_called_once_with('bob','llvc_basis','demoverzoek_417')
    def test_voorbeeld_get_vereist_token(self):
        self.assertEqual(self.request('/api/stemkeuze/voorbeeld?spreker=bob&keuze=llvc_basis&verzoek=demoverzoek_417',headers={'X-Drost-Token':''},method='GET')[0],400)
        self.server.bediening.maak_stemkeuze_voorbeeld.assert_not_called()
    def test_voorbeeld_vreemde_origin_geweigerd(self):self.assertEqual(self.request('/api/stemkeuze/voorbeeld?spreker=bob&keuze=llvc_basis&verzoek=demoverzoek_417',headers={'Origin':'https://extern.example'},method='GET')[0],400)
    def test_voorbeeld_extra_query_geweigerd(self):self.assertEqual(self.request('/api/stemkeuze/voorbeeld?spreker=bob&keuze=llvc_basis&verzoek=demoverzoek_417&url=https://extern.example',method='GET')[0],400)
    def test_voorbeeld_dubbele_query_geweigerd(self):self.assertEqual(self.request('/api/stemkeuze/voorbeeld?spreker=bob&spreker=elise&keuze=llvc_basis&verzoek=demoverzoek_417',method='GET')[0],400)
    def test_voorbeeld_verzoek_geen_pad(self):self.assertEqual(self.request('/api/stemkeuze/voorbeeld?spreker=bob&keuze=llvc_basis&verzoek=../worker',method='GET')[0],400)
    def test_voorbeeld_spreker_alleen_ingebouwd(self):self.assertEqual(self.request('/api/stemkeuze/voorbeeld?spreker=upload&keuze=llvc_basis&verzoek=demoverzoek_417',method='GET')[0],400)
    def test_stop_verzoek(self):
        self.assertEqual(self.request('/api/stemkeuze/voorbeeld/stop',{'verzoek':'demoverzoek_417'})[0],200)
        self.server.bediening.stop_stemkeuze_voorbeeld.assert_called_once_with('demoverzoek_417')
    def test_stop_zonder_token(self):self.assertEqual(self.request('/api/stemkeuze/voorbeeld/stop',{'verzoek':'demoverzoek_417'},{'X-Drost-Token':''})[0],400)
    def test_afsluiten_blokkeert_selectie(self):
        self.server.wordt_afgesloten.set();self.assertEqual(self.request(data={'keuze':'robot'})[0],400)
    def test_afsluiten_blokkeert_render(self):
        self.server.wordt_afgesloten.set();self.assertEqual(self.request('/api/stemkeuze/voorbeeld?spreker=bob&keuze=llvc_basis&verzoek=demoverzoek_417',method='GET')[0],400)

if __name__=='__main__':unittest.main()
