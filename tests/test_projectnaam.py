"""Voorkom dat de oude projectnaam in gebruikersmappen en loggers terugkomt."""

import os
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from app.diagnostiek.logboek import (
    bepaal_logmap_voor_deze_computer,
    maak_logboeken_klaar,
    sluit_logboeken_netjes_af,
)


class TestVasteProjectnaam(unittest.TestCase):
    def test_logmap_heeft_de_juiste_naam_op_iedere_windows_computer(self):
        with patch.dict(os.environ, {"LOCALAPPDATA": str(Path("testgegevens") / "Lokaal")}):
            gekozen_pad = bepaal_logmap_voor_deze_computer()

        self.assertEqual(gekozen_pad.name, "logboeken")
        self.assertEqual(gekozen_pad.parent.name, "DrostSoundboard")

    def test_beide_logboeken_krijgen_de_juiste_loggernaam(self):
        with TemporaryDirectory() as tijdelijke_map:
            logboeken = maak_logboeken_klaar(Path(tijdelijke_map))
            try:
                self.assertEqual(logboeken.softwarelogboek.name, "drostsoundboard.software")
                self.assertEqual(logboeken.auditlogboek.name, "drostsoundboard.audit")
            finally:
                sluit_logboeken_netjes_af(logboeken)


if __name__ == "__main__":
    unittest.main()
