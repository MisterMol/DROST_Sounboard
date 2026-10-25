"""Controleer de procesherkenning ook binnen de bestaande unittest-suite.

Op Windows draait dit een apart PowerShell-script met alleen nagebootste
processen. Buiten Windows is die test niet zinvol.
"""
from __future__ import annotations

import os
from pathlib import Path
import subprocess
import unittest


@unittest.skipUnless(os.name == 'nt', 'Windows PowerShell-procescontrole is alleen op Windows beschikbaar')
class TestPowerShellProcesbeheer(unittest.TestCase):
    def test_venv_launcher_en_echte_server_worden_veilig_herkend(self):
        script = Path(__file__).with_name('Controleer_Updater_Procesbeheer.ps1')
        uitslag = subprocess.run(
            ['powershell.exe', '-NoProfile', '-ExecutionPolicy', 'RemoteSigned',
             '-File', str(script)],
            cwd=str(script.parents[1]),
            text=True,
            capture_output=True,
            encoding='utf-8',
            errors='replace',
            timeout=30,
            check=False,
        )
        self.assertEqual(uitslag.returncode, 0,
                         f'PowerShell-regressietests mislukten:\n{uitslag.stdout}\n{uitslag.stderr}')
        self.assertIn('Alle 11 procesherkenningstests zijn geslaagd.', uitslag.stdout)
