"""Regressies voor consoleflitsen en veel snelle opdrachten vanuit de browser.

Geen fysiek audioapparaat nodig. Windows-specifieke procesvlaggen worden
nagebootst, zodat CI ook buiten Windows het gewenste gedrag kan controleren.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from tempfile import TemporaryDirectory
import threading
import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

from app.diagnostiek.vensterloze_windowsprocessen import geef_opstartopties_zonder_console
from app.diagnostiek.logboek import maak_logboeken_klaar, sluit_logboeken_netjes_af
from app.webinterface.bediening_van_de_audiomotor import WebbedieningVanDrostSoundboard


class TestZonderZwarteVensters(unittest.TestCase):
    def test_bij_windows_wordt_nooit_een_nieuw_ffmpeg_consolevenster_gemaakt(self):
        # Simuleer de Windows-specifieke STARTUPINFO zonder echte Windows-pc.
        # Beide opties zijn nodig omdat consoleprocessen en GUI-processen
        # verschillend omgaan met de eerste zichtbare vensteractie.
        from types import SimpleNamespace
        from contextlib import ExitStack
        namespace = 'app.diagnostiek.vensterloze_windowsprocessen'
        with ExitStack() as stapel:
            stapel.enter_context(patch(f'{namespace}.sys.platform', 'win32'))
            stapel.enter_context(patch(f'{namespace}.subprocess.CREATE_NO_WINDOW', 0x08000000, create=True))
            stapel.enter_context(patch(f'{namespace}.subprocess.STARTF_USESHOWWINDOW', 0x00000001, create=True))
            stapel.enter_context(patch(f'{namespace}.subprocess.SW_HIDE', 0, create=True))
            stapel.enter_context(patch(f'{namespace}.subprocess.STARTUPINFO',
                                       lambda: SimpleNamespace(dwFlags=0, wShowWindow=9), create=True))
            opties = geef_opstartopties_zonder_console()
            self.assertEqual(opties['creationflags'], 0x08000000)
            self.assertEqual(opties['startupinfo'].dwFlags, 1)
            self.assertEqual(opties['startupinfo'].wShowWindow, 0)
            self.assertIsNot(opties['startupinfo'], geef_opstartopties_zonder_console()['startupinfo'])

    def test_op_andere_systemen_blijft_normale_processtart_gelijk(self):
        with patch('app.diagnostiek.vensterloze_windowsprocessen.sys.platform', 'linux'):
            self.assertEqual(geef_opstartopties_zonder_console(), {})

    def test_mp4_probe_geeft_geen_console_maar_vangt_stderr_wel_af(self):
        from app.audio.mp4_verwerken import controleer_of_mp4_audio_en_video_bevat
        with TemporaryDirectory() as mapnaam:
            bron = Path(mapnaam) / 'test.mp4'
            bron.write_bytes(b'nep.mp4')
            verwacht = SimpleNamespace(stderr='Duration: 00:00:07.00\nVideo: h264\nAudio: aac', returncode=1)
            with patch('app.audio.mp4_verwerken.geef_meegeleverde_ffmpeg', return_value='ffmpeg'):
                with patch('app.audio.mp4_verwerken.geef_opstartopties_zonder_console',
                           return_value={'creationflags': 0x08000000}):
                    with patch('app.audio.mp4_verwerken.subprocess.run', return_value=verwacht) as start:
                        self.assertEqual(controleer_of_mp4_audio_en_video_bevat(bron), 7.0)
            self.assertEqual(start.call_args.kwargs['creationflags'], 0x08000000)
            self.assertTrue(start.call_args.kwargs['capture_output'])

    def test_alle_productie_ffmpeg_aanroepen_gebruiken_stille_optie(self):
        import ast
        from app.audio import mp4_verwerken, bronduur_en_golfvorm
        from app.webinterface import losse_media_exporteren
        for module in (mp4_verwerken, bronduur_en_golfvorm, losse_media_exporteren):
            with self.subTest(module=module.__name__):
                structuur = ast.parse(Path(module.__file__).read_text(encoding='utf-8'))
                gevonden = [knoop for knoop in ast.walk(structuur)
                            if isinstance(knoop, ast.Call) and isinstance(knoop.func, ast.Attribute)
                            and isinstance(knoop.func.value, ast.Name)
                            and knoop.func.value.id == 'subprocess' and knoop.func.attr == 'run']
                self.assertTrue(gevonden)
                for aanroep in gevonden:
                    self.assertTrue(any(keyword.arg is None and
                                        isinstance(keyword.value, ast.Call) and
                                        isinstance(keyword.value.func, ast.Name) and
                                        keyword.value.func.id == 'geef_opstartopties_zonder_console'
                                        for keyword in aanroep.keywords),
                                    f'Vensteroptie ontbreekt bij {module.__name__}:{aanroep.lineno}')


@dataclass(frozen=True)
class _NepAudio:
    naam_van_het_geluid: str = 'nep-geluid'
    ingesteld_volume: float = 1.0
    normalisatiestand: str = 'uit'
    normalisatiefactor: float = 1.0


class TestSnelAchterElkaarKlikken(unittest.TestCase):
    def setUp(self):
        self.map = TemporaryDirectory()
        self.basis = Path(self.map.name)
        self.logs = maak_logboeken_klaar(self.basis / 'logs')
        self.bediening = WebbedieningVanDrostSoundboard(object(), self.logs, self.basis / 'geluiden.sqlite')
        bron = self.basis / 'geluid.wav'
        bron.write_bytes(b'nep')
        self.geluid = self.bediening.geluidenbibliotheek.voeg_geluidsbestanden_toe([bron])[0]
        self.bediening.mixer.geef_huidige_status = Mock(return_value=SimpleNamespace(
            toestand='verbonden', geluidseffecten_aan=True,
        ))
        self.bediening.mixer.speel_een_voorbereid_geluid = Mock(return_value='beurt-123')
        self.bediening.mixer.stop_het_huidige_geluid = Mock()
        self.bediening.mixer.verbreek_de_verbinding = Mock()

    def tearDown(self):
        self.bediening._werkdraad_voor_decoderen.shutdown(wait=True, cancel_futures=True)
        sluit_logboeken_netjes_af(self.logs)
        self.map.cleanup()

    def test_twaalf_snelle_afspeelverzoeken_leveren_geen_twaalf_decodes_op(self):
        gestart, afronden = threading.Event(), threading.Event()
        decodeerbeurten = []

        def decoder(*args, **kwargs):
            decodeerbeurten.append(1)
            if len(decodeerbeurten) == 1:
                gestart.set()
                if not afronden.wait(timeout=3):
                    raise TimeoutError('De testsynchronisatie is niet vrijgegeven')
            return _NepAudio()

        with patch('app.webinterface.bediening_van_de_audiomotor.lees_en_bereid_mp3_of_wav_voor', decoder):
            self.bediening.speel_geluid_uit_de_bibliotheek(self.geluid.geluid_id)
            self.assertTrue(gestart.wait(timeout=2))
            for _ in range(11):
                self.bediening.speel_geluid_uit_de_bibliotheek(self.geluid.geluid_id)
            afronden.set()
            self.bediening._werkdraad_voor_decoderen.shutdown(wait=True)

        # De eerste decode was al bezig en wordt na voltooiing afgewezen.
        # Alleen de allerlaatste aanvraag mag uiteindelijk geluid starten.
        self.assertLessEqual(len(decodeerbeurten), 2)
        self.bediening.mixer.speel_een_voorbereid_geluid.assert_called_once()

    def test_stop_annuleert_ook_de_laatste_wachtende_opdracht(self):
        gestart, afronden = threading.Event(), threading.Event()

        def decoder(*args, **kwargs):
            gestart.set()
            afronden.wait(timeout=3)
            return _NepAudio()

        with patch('app.webinterface.bediening_van_de_audiomotor.lees_en_bereid_mp3_of_wav_voor', decoder):
            self.bediening.speel_geluid_uit_de_bibliotheek(self.geluid.geluid_id)
            self.assertTrue(gestart.wait(timeout=2))
            self.bediening.speel_geluid_uit_de_bibliotheek(self.geluid.geluid_id)
            self.bediening.stop_het_huidige_geluid()
            afronden.set()
            self.bediening._werkdraad_voor_decoderen.shutdown(wait=True)
        self.bediening.mixer.speel_een_voorbereid_geluid.assert_not_called()

    def test_al_bezig_met_verbinden_geeft_geen_tweede_driveraanroep(self):
        self.bediening.mixer.geef_huidige_status = Mock(return_value=SimpleNamespace(
            toestand='wordt_verbonden', geluidseffecten_aan=False,
        ))
        self.bediening.verbind_met_microfoon(24)
        self.bediening.verbind_met_microfoon(24)
        self.bediening.mixer.verbind_de_microfoon_met_vb_cable = Mock()
        self.bediening.mixer.verbind_de_microfoon_met_vb_cable.assert_not_called()


if __name__ == '__main__':
    unittest.main()

class TestGestopteMediaOverdracht(unittest.TestCase):
    def test_browser_die_zelf_video_stopt_is_geen_http_500(self):
        from app.webinterface.lokale_webserver import DrostVerzoekAfhandeling
        afhandeling = object.__new__(DrostVerzoekAfhandeling)
        logger = Mock()
        afhandeling.server = SimpleNamespace(
            bediening=SimpleNamespace(logboeken=SimpleNamespace(softwarelogboek=logger)))
        afhandeling.path = '/media/00000000-0000-0000-0000-000000000001'
        afhandeling.close_connection = False
        afhandeling._stuur_json = Mock()
        fout = ConnectionResetError('De browser heeft tijdens zoeken de verbinding verbroken')
        afhandeling._verwerk_fout(fout, 'GET '+afhandeling.path)
        self.assertTrue(afhandeling.close_connection)
        afhandeling._stuur_json.assert_not_called()
        logger.error.assert_not_called()
        logger.info.assert_called_once()

    def test_echte_mediafout_blijft_volledig_worden_gelogd(self):
        from app.webinterface.lokale_webserver import DrostVerzoekAfhandeling
        afhandeling = object.__new__(DrostVerzoekAfhandeling)
        logger = Mock()
        afhandeling.server = SimpleNamespace(
            bediening=SimpleNamespace(logboeken=SimpleNamespace(softwarelogboek=logger)))
        afhandeling.path = '/media/00000000-0000-0000-0000-000000000001'
        afhandeling.close_connection = False
        afhandeling._stuur_json = Mock()
        afhandeling._verwerk_fout(OSError('werkelijk stuk'), 'GET '+afhandeling.path)
        logger.error.assert_called_once()
        self.assertEqual(afhandeling._stuur_json.call_args.args[0], 500)
