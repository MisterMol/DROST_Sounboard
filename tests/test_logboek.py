"""Controleer dat auditlogs en tracebacks later terug te lezen zijn."""

import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from app.diagnostiek.logboek import (
    maak_logboeken_klaar,
    schrijf_auditgebeurtenis,
    sluit_logboeken_netjes_af,
)


class TestNederlandseLogboeken(unittest.TestCase):
    def test_softwarelog_bevat_uitzondering_en_traceback(self):
        with TemporaryDirectory() as mapnaam:
            logboeken = maak_logboeken_klaar(Path(mapnaam))
            try:
                raise ValueError("De microfoonwaarde mag niet leeg zijn")
            except ValueError:
                logboeken.softwarelogboek.exception(
                    "Controle van microfoonwaarde mislukt",
                    extra={
                        "gebeurtenis": "microfoonwaarde_afgewezen",
                        "gegevens": {"foutcode": "INVOER-001", "ontvangen_type": "NoneType"},
                    },
                )

            inhoud = (Path(mapnaam) / "software.jsonl").read_text(encoding="utf-8")
            bericht = json.loads(inhoud.splitlines()[-1])
            self.assertEqual(bericht["fouttype"], "ValueError")
            self.assertEqual(bericht["foutcode"], "INVOER-001")
            self.assertIn("Traceback", bericht["traceback"])
            self.assertIn("microfoonwaarde mag niet leeg zijn", bericht["traceback"])
            self.assertTrue(bericht["sessie_id"])
            sluit_logboeken_netjes_af(logboeken)

    def test_auditgebeurtenis_staat_in_eigen_bestand(self):
        with TemporaryDirectory() as mapnaam:
            logboeken = maak_logboeken_klaar(Path(mapnaam))
            schrijf_auditgebeurtenis(
                logboeken.auditlogboek,
                "apparaatcontrole_gestart",
                {"fase": 0},
            )
            inhoud = (Path(mapnaam) / "audit.jsonl").read_text(encoding="utf-8")
            bericht = json.loads(inhoud.splitlines()[-1])
            self.assertEqual(bericht["gebeurtenis"], "apparaatcontrole_gestart")
            self.assertEqual(bericht["gegevens"]["fase"], 0)
            sluit_logboeken_netjes_af(logboeken)


if __name__ == "__main__":
    unittest.main()
