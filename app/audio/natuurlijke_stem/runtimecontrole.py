"""Controleer de bestaande vaste LLVC-runtime zonder code uit modellen te laden."""
from __future__ import annotations
import hashlib
import json
from pathlib import Path
import re

MODEL_SHA = 'cceb7ab9621f84d62d283725ae3281cacb04f762d6a088fe3e97c1a29d4b8c0e'


def file_sha(path):
    digest=hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda:stream.read(1024*1024),b''):
            digest.update(block)
    return digest.hexdigest()


def _geen_link(path):
    st=path.lstat()
    if path.is_symlink() or getattr(st,'st_file_attributes',0)&0x400:
        raise ValueError('Het stempakket bevat een link of junction.')


def _json_pairs(pairs):
    result={}
    for key,value in pairs:
        if key in result:raise ValueError('Dubbele sleutel in het stempakket.')
        result[key]=value
    return result


def valideer_runtime(root):
    root=Path(root)
    _geen_link(root)
    manifestpad=root/'runtime.json'
    _geen_link(manifestpad)
    if manifestpad.stat().st_size>8*1024*1024:
        raise ValueError('Het stempakketmanifest is te groot.')
    info=json.loads(manifestpad.read_text(encoding='utf-8'),object_pairs_hook=_json_pairs)
    if not isinstance(info,dict) or info.get('schema')!=1 or info.get('model_sha256')!=MODEL_SHA:
        raise ValueError('Het stempakket heeft niet de verwachte versie.')
    files=info.get('files')
    if not isinstance(files,dict) or not 2<=len(files)<=20000:
        raise ValueError('Ongeldige bestandslijst voor de stemmotor.')
    if not {'DrostStemWorker.exe','G_500000.pth'}<=files.keys() or files['G_500000.pth']!=MODEL_SHA:
        raise ValueError('Het gecontroleerde proefmodel of de stemmotor ontbreekt.')
    seen=set()
    for name,expected in files.items():
        parts=name.split('/') if isinstance(name,str) else []
        if (not parts or any(part in ('','.','..') for part in parts)
                or any(re.search(r'[<>:"|?*\\\x00-\x1f]',part) or part.endswith((' ','.')) for part in parts)
                or name.casefold() in seen or name.casefold()=='runtime.json'
                or not isinstance(expected,str) or not re.fullmatch(r'[0-9a-f]{64}',expected)):
            raise ValueError('Ongeldige of dubbele bestandsnaam in het stempakket.')
        seen.add(name.casefold())
        path=root
        for part in parts:
            if re.match(r'(?i)^(CON|PRN|AUX|NUL|COM[1-9]|LPT[1-9])(?:\.|$)',part):
                raise ValueError('Gereserveerde bestandsnaam in het stempakket.')
            path=path/part
            _geen_link(path)
        if not path.is_file() or file_sha(path)!=expected:
            raise ValueError('Een stembestand ontbreekt of is beschadigd: '+name)
    actual=set()
    for path in root.rglob('*'):
        _geen_link(path)
        if path.is_file():actual.add(path.relative_to(root).as_posix())
    if actual!=set(files)|{'runtime.json'}:
        raise ValueError('Er staan onverwachte bestanden in het stempakket. Bewaar het pakket en herstel de oorspronkelijke runtime.')
    return info
