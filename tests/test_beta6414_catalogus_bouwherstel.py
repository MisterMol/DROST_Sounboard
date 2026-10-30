"""Catalogusregressies voor 18 zichtbare effecten en interne compatibiliteit en werkelijk aanwezige unieke pictogrammen.

Deze controles gebruiken de echte appcatalogus en het echte dashboardbestand.
Ze openen geen audiodevice en laden geen native stemmotor.
"""
from pathlib import Path
import re
import unittest

from app.audio.stemvervorming import PROFIELEN, profiel_catalogus_voor_api, VERVALLEN_STEMPROFIELEN
from app.audio.stemparameters import standaard_parameters, controleer_parameters

VERWACHTE_PROFIELEN = {
    'normaal', 'radio', 'robot', 'diep', 'heel_diep', 'hoog', 'heel_hoog',
    'alien', 'telefoon', 'monster', 'echo', 'megafoon', 'jongen', 'meisje',
    'oudeman', 'oudevrouw', 'xbox2010', 'autotune',
    'monsterkoor', 'ruimtepak', 'spook', 'retrocomputer',
}
NIEUWE_PROFIELEN = {'monsterkoor', 'ruimtepak', 'spook', 'retrocomputer'}


def lees_pictogrampaden() -> dict[str, str]:
    path = Path(__file__).resolve().parents[1] / 'app/webinterface/statisch/dashboard.js'
    text = path.read_text(encoding='utf-8-sig')
    marker = 'const STEM_ICON_PADEN = Object.freeze({'
    if text.count(marker) != 1:
        raise AssertionError('De centrale pictogramtabel ontbreekt of is dubbel.')
    block = text.split(marker, 1)[1].split('\n});', 1)[0]
    pattern = r"^\s*(?:'([\w-]+)'|([A-Za-z_]\w*)):\s*'([^']*)',?\s*$"
    result = {}
    for line in block.splitlines():
        if not line.strip():
            continue
        found = re.fullmatch(pattern, line)
        if not found:
            raise AssertionError('Onherkenbare regel in de pictogramtabel: ' + line)
        name, path = found.group(1) or found.group(2), found.group(3)
        if name in result:
            raise AssertionError('Dubbele pictogramnaam in het dashboard: ' + name)
        result[name] = path
    return result


class TestCatalogusBouwherstel414(unittest.TestCase):
    def test_exact_22_bedoelde_profielen(self):
        self.assertEqual(len(PROFIELEN), 22)
        self.assertEqual(set(PROFIELEN), VERWACHTE_PROFIELEN)

    def test_ids_zijn_uniek(self):
        self.assertEqual(len(PROFIELEN), len(set(PROFIELEN)))

    def test_api_bevat_alleen_de_18_kiesbare_profielen(self):
        info = profiel_catalogus_voor_api()
        self.assertEqual(len(info), 18)
        self.assertEqual([p['id'] for p in info], [p for p in PROFIELEN if p not in VERVALLEN_STEMPROFIELEN])

    def test_alle_pictogramnamen_zijn_uniek(self):
        info = profiel_catalogus_voor_api()
        self.assertEqual(len({p['icoon'] for p in info}), len(info))

    def test_elk_pictogram_heeft_een_tekening(self):
        paths = lees_pictogrampaden()
        for profile in profiel_catalogus_voor_api():
            with self.subTest(profiel=profile['id']):
                self.assertIn(profile['icoon'], paths)
                self.assertTrue(paths[profile['icoon']].startswith('M'))
                self.assertGreater(len(paths[profile['icoon']]), 10)

    def test_tekeningen_zijn_ook_onderling_verschillend(self):
        paths = lees_pictogrampaden()
        selected = [paths[p['icoon']] for p in profiel_catalogus_voor_api()]
        self.assertEqual(len(set(selected)), 18)

    def test_nieuwe_profielen_gebruiken_eigen_pictogram(self):
        info = {p['id']: p for p in profiel_catalogus_voor_api()}
        for identity in NIEUWE_PROFIELEN:
            with self.subTest(profiel=identity):
                self.assertEqual(info[identity]['icoon'], identity)

    def test_twee_geldige_regelaars_per_nieuw_profiel(self):
        defaults = standaard_parameters()
        for identity in NIEUWE_PROFIELEN:
            with self.subTest(profiel=identity):
                self.assertEqual(len(defaults[identity]), 2)
                self.assertEqual(controleer_parameters(identity, defaults[identity]), defaults[identity])


if __name__ == '__main__':
    unittest.main()
