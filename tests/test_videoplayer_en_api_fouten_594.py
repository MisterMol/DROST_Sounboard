"""Regressies voor soepele MP4-beelden en een consequent foutcontract.

De hoofdtests draaien zonder Node of een browser op een schone Windows-pc.
Geavanceerde JavaScript-tests draaien aanvullend wanneer Node bij een
ontwikkelaar beschikbaar is. Eindgebruikers hoeven Node niet te installeren.
"""

from __future__ import annotations

import json
from pathlib import Path
import shutil
import subprocess
import unittest
from unittest.mock import Mock

from app.webinterface.api_foutantwoorden import (
    maak_webantwoord_voor_onbekende_route,
    maak_webfoutantwoord,
)

BASISMAP = Path(__file__).resolve().parents[1]


class TestStandaardApiAntwoord(unittest.TestCase):
    def test_verkeerde_parameter_krijgt_400_en_onderliggende_foutcode(self):
        fout = maak_webfoutantwoord(ValueError('WEB-026: verwacht een JSON-object.'), 'POST /api/test')
        self.assertEqual(fout.http_status, 400)
        self.assertEqual(fout.inhoud['foutcode'], 'WEB-400')
        self.assertEqual(fout.inhoud['oorzaakcode'], 'WEB-026')
        self.assertEqual(fout.inhoud['actie'], 'POST /api/test')
        self.assertEqual(fout.inhoud['referentie'], fout.logreferentie)
        self.assertEqual(len(fout.logreferentie), 12)

    def test_onverwachte_fout_lekt_geen_systeempad_of_traceback(self):
        fout = maak_webfoutantwoord(RuntimeError('C:\\Geheim\\bestand.txt'), 'GET /api/status')
        self.assertEqual(fout.http_status, 500)
        self.assertNotIn('Geheim', json.dumps(fout.inhoud))
        self.assertIn('software.jsonl', fout.inhoud['fout'])
        self.assertEqual(fout.inhoud['foutcode'], 'WEB-999')

    def test_onbekende_route_gebruikt_dezelfde_basisvelden(self):
        antwoord = maak_webantwoord_voor_onbekende_route('WEB-032', 'onbekende pagina of actie.')
        self.assertEqual(antwoord['foutcode'], 'WEB-032')
        self.assertEqual(antwoord['fouttype'], 'OngeldigWebverzoek')
        self.assertIn('WEB-032', antwoord['fout'])


class TestModulaireVideoWeergave(unittest.TestCase):
    def test_browser_script_wordt_voor_dashboard_geladen(self):
        html = (BASISMAP / 'app/webinterface/statisch/dashboard.html').read_text(encoding='utf-8')
        self.assertLess(html.index('/video_synchronisatie.js'), html.index('/dashboard.js'))

    def test_dashboard_herstart_mp4_niet_tijdens_voorbereiden(self):
        bron = (BASISMAP / 'app/webinterface/statisch/dashboard.js').read_text(encoding='utf-8')
        self.assertIn('toonVoorbereidingZonderVideo(geluid)', bron)
        self.assertNotIn('Math.abs(video.currentTime - gewensteTijd) > .45', bron)
        self.assertIn('videobediening?.synchroniseerMetAudio(status)', bron)
        self.assertIn('videobediening?.stop()', bron)

    def test_video_controller_is_op_zichzelf_getest_met_node_indien_beschikbaar(self):
        node = shutil.which('node')
        if node is None:
            self.skipTest('Node is optioneel voor ontwikkelaars; geen Windows-runtime-afhankelijkheid.')
        script = BASISMAP / 'tests/hulpmiddelen/test_video_synchronisatie.js'
        resultaat = subprocess.run([node, str(script)], capture_output=True, text=True,
                                   timeout=15, check=False)
        self.assertEqual(resultaat.returncode, 0, resultaat.stdout + resultaat.stderr)
        self.assertIn('Video controller OK', resultaat.stdout)
