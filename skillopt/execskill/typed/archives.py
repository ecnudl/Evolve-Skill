"""typed-v3 archive packages (CHAIN-DECISIONS T9): the program packages an earlier chain accepted at its own practice
gate, kept in this tree and offered to the bench's step as candidate 0 of ``programs`` (``chain``, 'repair' only).

The records are byte copies of the SkillOpt ``skill-archive`` procedure records (built 2026-11-09 16:57; its
``manifest.json`` lists every file sha256), stored as ``archive/<bench>/<package>/<id>.procedure.json`` beside this
module. ``archive/index.json`` names, per chain and bench, the package, its procedures in package order and for each
the file, the sha256 of the file's bytes and the record's own ``record_sha256``; the index's bytes are pinned here
(``INDEX_SHA256``), so a changed byte anywhere is refused before anything runs. Only the five records of ``PACKAGES``
exist: chain G ZebraLogic ``main-v6-G-s3-p-zebralogic-3-5``, chain D ZebraLogic ``main-v6-D-s3-p-zebralogic-3-3``,
both chains ALFWorld ``alfworld-v11-accepted`` (three procedures). Never a hand-picked package, never
``oracle-reference`` (T9): the loader refuses every package not in ``PACKAGES``.

A run seals what it may use at prepare (the manifest field ``archive``, ``sealed``: per chain, per bench, the package
name and every procedure's id, record hash and file) and reads it back only from the manifest; ``load_package``
verifies the sealed entry against the index, the index against its pin, every file against its sha256 and every
record against its own hash (``Procedure.from_json``) and returns the records. Nothing here screens a program: the
typed static screen is the chain's (``writers.screen_record``). Files are read as bytes and parsed, never executed.

    index  = {'version', 'source', 'rule', 'chains': {chain: {bench: {'package', 'procedures': [row, ...]}}}}
    row    = {'id', 'file', 'sha256', 'record_sha256', 'source_file'}
    sealed = {chain: {bench: {'package', 'procedures': [{'id', 'record_sha256', 'file'}, ...]}}}   # manifest
"""
from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path

from skillopt.continual_eval.core import require

from . import CHAINS, ORDER

ARCHIVE_DIR = Path(__file__).resolve().parent / 'archive'
INDEX = 'index.json'
INDEX_VERSION = 'typed-v3-archive-1'
INDEX_SHA256 = '7a3bd676899de243715b286de11217408c9a087c0b8902884a8ad8a46403476b'
# T9: the only packages (per chain and bench) a typed-v3 run may take from the archive
PACKAGES = {('G', 'zebralogic'): 'main-v6-G-s3-p-zebralogic-3-5', ('D', 'zebralogic'): 'main-v6-D-s3-p-zebralogic-3-3',
            ('G', 'alfworld'): 'alfworld-v11-accepted', ('D', 'alfworld'): 'alfworld-v11-accepted'}
REFUSED_NAMES = ('oracle-reference', 'zebra-pc-', 'main-v5-')  # never, whatever an index says (T9; the brief)
ROW_KEYS = ('id', 'file', 'sha256', 'record_sha256', 'source_file')
SEALED_KEYS = ('id', 'record_sha256', 'file')
HEX64 = re.compile(r'[0-9a-f]{64}')
FILE_NAME = re.compile(r'(?P<bench>[a-z]+)/(?P<package>[A-Za-z0-9][A-Za-z0-9._-]{0,99})/(?P<id>p-[a-z]+-\d{1,3}-\d{1,3})'
                       r'\.procedure\.json')


def _sha256(data):
    return hashlib.sha256(data).hexdigest()


def _root(root):
    return Path(ARCHIVE_DIR if root is None else root)


def load_index(root=None):
    """The verified index: its bytes hash to ``INDEX_SHA256``; it names exactly the packages of ``PACKAGES``, each
    procedure row with its file under ``<bench>/<package>/<id>.procedure.json`` and two hex hashes. Refused
    (``ValueError``) otherwise; a refusal names keys and paths, never contents."""
    path = _root(root) / INDEX
    try:
        raw = path.read_bytes()
    except OSError as error:
        raise ValueError('The archive index %s cannot be read (%s)' % (path, type(error).__name__)) from None
    require(_sha256(raw) == INDEX_SHA256, 'The archive index %s differs from the pinned one (INDEX_SHA256)' % path)
    index = json.loads(raw.decode('utf-8'))
    require(isinstance(index, dict) and index.get('version') == INDEX_VERSION and isinstance(index.get('chains'), dict),
            'An archive index of version ' + INDEX_VERSION)
    named = {(chain, bench): entry.get('package') for chain, benches in index['chains'].items()
             for bench, entry in (benches or {}).items() if isinstance(entry, dict)}
    require(named == PACKAGES, 'The archive index names exactly the packages of T9 (PACKAGES)')
    for (chain, bench), package in named.items():
        rows = index['chains'][chain][bench].get('procedures')
        require(isinstance(rows, list) and rows, 'An archive package holds at least one procedure: ' + package)
        for row in rows:
            require(isinstance(row, dict) and set(row) == set(ROW_KEYS), 'An archive index row has %s' % (ROW_KEYS,))
            found = FILE_NAME.fullmatch(str(row['file']))
            require(found is not None and found.group('bench') == bench and found.group('package') == package
                    and found.group('id') == row['id'], 'An archive file is <bench>/<package>/<id>.procedure.json')
            require(all(HEX64.fullmatch(str(row[key])) for key in ('sha256', 'record_sha256')),
                    'An archive row carries the file and record sha256')
        require(len({row['id'] for row in rows}) == len(rows), 'Procedure ids are distinct within a package')
        require(not any(word in package for word in REFUSED_NAMES), 'A refused archive package: ' + package)
    return index


def sealed(choice, root=None):
    """The manifest field ``archive`` of a prepare: ``{}`` for no archive (None, 'none', ``{}``), else (``'index'``)
    every package of the verified index per chain and bench with each procedure's id, record hash and file. A dict
    is checked with ``check_sealed`` and returned as is (tests and explicit preparations)."""
    if choice in (None, 'none') or choice == {}:
        return {}
    if isinstance(choice, dict):
        return check_sealed(choice, root=root)
    require(choice == 'index', "An archive choice is 'none' or 'index'")
    index = load_index(root)
    return {chain: {bench: {'package': entry['package'],
                            'procedures': [{key: row[key] for key in SEALED_KEYS} for row in entry['procedures']]}
                    for bench, entry in sorted(index['chains'][chain].items())}
            for chain in CHAINS if chain in index['chains']}


def check_sealed(value, root=None):
    """A manifest's ``archive`` value: ``{}``, or per chain (of ``CHAINS``) per bench (of ``ORDER``) exactly the index's
    package with exactly its procedures (id, record hash, file, in index order). Returns the value."""
    require(isinstance(value, dict), 'The manifest field archive is a mapping')
    if not value:
        return value
    index = load_index(root)
    for chain, benches in value.items():
        require(chain in CHAINS and isinstance(benches, dict) and benches, 'An archive entry per registered chain')
        for bench, entry in benches.items():
            require(bench in ORDER and (chain, bench) in PACKAGES, 'An archive package for this chain and bench (T9)')
            expected = index['chains'][chain][bench]
            require(isinstance(entry, dict) and set(entry) == {'package', 'procedures'}
                    and entry['package'] == expected['package']
                    and entry['procedures'] == [{key: row[key] for key in SEALED_KEYS} for row in expected['procedures']],
                    'The sealed archive entry of %s %s is the index entry' % (chain, bench))
    return value


def entry_for(value, chain, bench):
    """The sealed entry of ``chain`` and ``bench`` (None when the manifest's archive names none)."""
    return ((value or {}).get(chain) or {}).get(bench)


def load_package(value, chain, bench, root=None):
    """The procedure records of the sealed package of ``chain`` on ``bench``, verified (module docstring): the sealed
    entry is the index entry, each file's bytes hash to the index's sha256, each record's ``record_sha256`` is the
    index's and the sealed one, and ``Procedure.from_json`` rebuilds the record with that hash. Returns
    ``{'package', 'procedures': [record, ...]}`` in package order; ValueError on any difference."""
    from .mount import procedure_from_record  # lazily: the manifest checks need no solver import
    check_sealed(value, root=root)
    entry = entry_for(value, chain, bench)
    require(entry is not None, 'The manifest seals no archive package for %s %s' % (chain, bench))
    index_rows = load_index(root)['chains'][chain][bench]['procedures']
    base, records = _root(root).resolve(), []
    for row, sealed_row in zip(index_rows, entry['procedures']):
        path = (base / row['file']).resolve()
        require(base in path.parents, 'An archive file inside the archive directory: ' + row['file'])
        try:
            raw = path.read_bytes()
        except OSError as error:
            raise ValueError('The archive file %s cannot be read (%s)' % (row['file'], type(error).__name__)) from None
        require(_sha256(raw) == row['sha256'], 'The archive file %s differs from the index (sha256)' % row['file'])
        record = json.loads(raw.decode('utf-8'))
        require(isinstance(record, dict) and record.get('id') == row['id'] and record.get('origin') == bench
                and record.get('record_sha256') == row['record_sha256'] == sealed_row['record_sha256'],
                'The archive record %s is the indexed and sealed one' % row['id'])
        procedure = procedure_from_record(record)  # PackageInvalid unless the record verifies and hashes to itself
        require(procedure.sha256 == row['record_sha256'], 'The archive record %s hashes to itself' % row['id'])
        records.append(record)
    return {'package': entry['package'], 'procedures': records}
