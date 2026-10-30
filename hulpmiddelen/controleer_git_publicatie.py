"""Controleer wat er klaarstaat voor GitHub. Verstuur nooit bestanden.

Alleen staged (geprepareerde) bestanden worden bekeken; niet het hele project.
Dit script is een veiligheidsnet, geen garantie tegen verborgen privédata.
"""
from __future__ import annotations
import re
from pathlib import Path, PurePosixPath
import subprocess
import sys

GEHEIMEN = re.compile(r'(?i)(?:github_pat_[A-Za-z0-9_]{15,}|ghp_[A-Za-z0-9]{20,}|sk-[A-Za-z0-9]{25,}|-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----)')
VERBODEN_EXTENSIES = {'.db', '.sqlite', '.sqlite3', '.exe', '.dll', '.pth', '.pt', '.onnx',
                       '.safetensors', '.nupkg', '.msi', '.pfx', '.pem', '.key', '.zip',
                       '.mp3', '.wav', '.mp4', '.gif', '.webp'}
VERBODEN_MAPPEN = {'.venv', 'venv', 'stem-runtime', 'release-velopack', 'dist', 'build',
                   '__pycache__', 'node_modules'}
MAX_BYTES = 20 * 1024 * 1024
# Deze twee vaste, ingebouwde stemvoorbeelden moeten in de GitHub-clone zitten.
# Alle andere mediabestanden blijven uitgesloten.
VEREISTE_STEMVOORBEELDEN = (
    'app/audio/stemvoorbeelden/hello_my_name_is_bob.mp3',
    'app/audio/stemvoorbeelden/hello_my_name_is_elise.mp3',
)


def is_stemvoorbeeld(pad: str) -> bool:
    """Sta alleen MP3's direct in de vaste stemvoorbeeldmap toe."""
    delen = PurePosixPath(pad.replace('\\', '/')).parts
    return (len(delen) == 4 and delen[:3] == ('app', 'audio', 'stemvoorbeelden')
            and delen[3].lower().endswith('.mp3') and not delen[3].startswith('.'))


def beoordeel_pad(pad: str) -> str | None:
    """Geef een fout terug voor lokale data of uitvoerbestanden."""
    pad = pad.replace('\\', '/')
    delen = PurePosixPath(pad).parts
    naam = delen[-1].lower() if delen else ''
    if any(item.lower() in VERBODEN_MAPPEN for item in delen):
        return 'lokale runtime- of bouwmap'
    if naam.startswith('.env') or 'token' in naam or 'secret' in naam or 'wachtwoord' in naam:
        return 'mogelijk geheim bestand'
    if is_stemvoorbeeld(pad):
        return None
    if PurePosixPath(pad).suffix.lower() in VERBODEN_EXTENSIES:
        return 'binary, mediabestand of persoonlijke data'
    if naam.endswith(('.log', '.jsonl')) or naam == '.drost-release.lock':
        return 'lokale status of logboek'
    return None


def controleer_project(project: Path) -> tuple[list[str], list[str]]:
    """Lees uitsluitend de git-index en controleer alle gestagede inhoud."""
    p = subprocess.run(['git', 'rev-parse', '--show-toplevel'], cwd=project,
                       capture_output=True, text=True)
    if p.returncode:
        return [], ['Geen Git-repository gevonden. Zie GITHUB_PUBLICEREN.md.']
    root = Path(p.stdout.strip()).resolve()
    if root != project.resolve():
        return [], ['Git-root is niet de projectmap; voer de controle vanuit de clone uit.']
    staged = subprocess.run(['git', 'diff', '--cached', '--name-only', '--diff-filter=ACMR', '-z'],
                            cwd=root, capture_output=True)
    if staged.returncode:
        return [], ['Git kon de voorbereide bestanden niet lezen.']
    namen = [n.decode('utf-8', errors='replace') for n in staged.stdout.split(b'\0') if n]
    fouten: list[str] = []
    # 'Niet genegeerd' betekent nog niet 'daadwerkelijk mee in een clone'.
    # Controleer dus ook de index, inclusief al eerder gecommitte bestanden.
    stem_index = subprocess.run(
        ['git', 'ls-files', '--cached', '-z', '--', 'app/audio/stemvoorbeelden/'],
        cwd=root, capture_output=True)
    if stem_index.returncode:
        fouten.append('Git kon de opgenomen stemvoorbeelden niet controleren.')
    else:
        opgenomen = {naam.decode('utf-8', errors='replace')
                    for naam in stem_index.stdout.split(b'\0') if naam}
        for verplicht in VEREISTE_STEMVOORBEELDEN:
            if verplicht not in opgenomen:
                fouten.append(f'{verplicht}: ontbreekt in Git. Gebruik git add voor dit bestand.')
    for naam in namen:
        reden = beoordeel_pad(naam)
        if reden:
            fouten.append(f'{naam}: {reden}')
            continue
        locatie = root / naam
        if locatie.is_symlink():
            fouten.append(f'{naam}: symbolische link; eerst handmatig controleren')
            continue
        if not locatie.is_file():
            continue
        if locatie.stat().st_size > MAX_BYTES:
            fouten.append(f'{naam}: groter dan 20 MB')
            continue
        # Controleer de INDEX, niet de latere working-tree-versie.
        blob = subprocess.run(['git', 'show', f':{naam}'], cwd=root, capture_output=True)
        if blob.returncode:
            fouten.append(f'{naam}: indexinhoud niet leesbaar')
            continue
        if GEHEIMEN.search(blob.stdout.decode('utf-8', errors='replace')):
            fouten.append(f'{naam}: mogelijk toegangstoken of privésleutel')
    verschil = subprocess.run(['git', 'diff', '--cached', '--check'], cwd=root,
                              capture_output=True, text=True)
    if verschil.returncode:
        fouten.append('Git diff --cached --check meldt fouten: ' + verschil.stdout.strip())
    return namen, fouten


def main() -> int:
    try:
        namen, fouten = controleer_project(Path.cwd())
    except FileNotFoundError:
        print('Git is niet geïnstalleerd. Zie GITHUB_PUBLICEREN.md.')
        return 1
    print('Bestanden klaar voor GitHub:', len(namen))
    for naam in namen[:100]:
        print(' ', naam)
    if len(namen) > 100:
        print(' ... en', len(namen) - 100, 'meer')
    if fouten:
        print('LET OP. GitHub-controle afgekeurd:')
        for fout in fouten:
            print(' ', fout)
        return 1
    if not namen:
        print('Er staat nog niets klaar voor een commit. Zie GITHUB_PUBLICEREN.md.')
        return 1
    print('Geen herkenbare verboden bestanden gevonden. Controleer de inhoud nog zelf.')
    print('Dit script heeft niets geüpload, gecommit of gepusht.')
    return 0


if __name__ == '__main__':
    sys.exit(main())
