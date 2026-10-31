"""Controleer onafhankelijk de gebundelde RC6 Setup inclusief de PE-overlay."""
from __future__ import annotations
import hashlib
from pathlib import Path
import struct
import sys

SIGNATURE = b"DROSTPKGv000001!"
TRAILER_SIZE = 56

def controleer(wizard: Path, setup: Path) -> None:
    setup_size = setup.stat().st_size
    original_sha = hashlib.file_digest(setup.open("rb"), "sha256").digest()
    total = wizard.stat().st_size
    if total < setup_size + TRAILER_SIZE + 16384:
        raise ValueError("Gebundelde installer is onvolledig")
    with wizard.open("rb") as stream:
        stream.seek(-TRAILER_SIZE, 2)
        trailer = stream.read(TRAILER_SIZE)
        sha = trailer[:32]
        embedded_size = struct.unpack("<Q", trailer[32:40])[0]
        signature = trailer[40:]
        if signature != SIGNATURE:
            raise ValueError("Verkeerde installerhandtekening")
        if embedded_size != setup_size or sha != original_sha:
            raise ValueError("Ingesloten Setup komt niet overeen met de originele Setup")
        offset = total - TRAILER_SIZE - embedded_size
        stream.seek(offset)
        if stream.read(2) != b"MZ":
            raise ValueError("Ingesloten Setup is geen Windows EXE")
        stream.seek(offset)
        digest = hashlib.sha256()
        remain = embedded_size
        while remain:
            block = stream.read(min(remain, 1024 * 1024))
            if not block:
                raise ValueError("Ingesloten Setup is afgebroken")
            digest.update(block)
            remain -= len(block)
        if digest.digest() != original_sha:
            raise ValueError("SHA256 van de ingesloten Setup klopt niet")
    print(f"RC6 Setup volledig en correct gebundeld: {setup_size / 1048576:.1f} MiB")
    print(f"Gebruikers-EXE: {total / 1048576:.1f} MiB")
    print(f"Setup SHA256: {digest.hexdigest()}")

if __name__ == "__main__":
    if len(sys.argv) != 3:
        raise SystemExit("Gebruik: python Controleer_RC6_Bundel.py TEST_EXE SETUP_EXE")
    controleer(Path(sys.argv[1]), Path(sys.argv[2]))
