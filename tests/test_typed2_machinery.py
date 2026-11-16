"""typed-v2 machinery guard, step 1m (DESIGN 3.5 and 5, spec/identity.md 4, addendum F11): the two lists are pinned,
this tree equals them, and an altered file, an extra module under this tree's skillopt/execskill and a missing frozen
name are each refused.

Altered copies are built under /tmp/typed2-neutral (a plain name: the sealed-path guard refuses a path with 'test'),
never in the tree. The start_checks test belongs to step 1b. Here the real-only checks 2 and 4 run in this process
with ``machinery.loaded`` replaced by a stand-in binding.

Step 7g adds: ``REQUIRED`` equals the static scan of the typed package; the pinned ``scripts`` files (addendum RP12 /
Q19) are its import closure and are compared on the tree, the snapshot and the loaded modules; check 6 pins every
pinned text; and the ONE bound harness (DESIGN 5): a fresh interpreter runs ``tests/typed2_bound_driver.py`` bound by
``bind_machinery`` to a stand-in snapshot made of the 564 + 64 listed files (plus the pinned scripts files and the data
the frozen ``v222_cards`` reads beside ``skillopt/``), and the guard cases of DESIGN 5 are each refused in that child.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import types
from pathlib import Path

import pytest

from skillopt.execskill.typed import MACHINERY_SNAPSHOT, machinery

TREE = Path(machinery.__file__).resolve().parents[3]
NEUTRAL = Path('/tmp/typed2-neutral')
# The pins as the coordinator recorded them (addendum F11: both recomputed on dl inside the main-v10 snapshot).
PINNED_LIST_SHA256 = '3c37fdd90de0e6b51013af7fd4f166f3fa9a1fead5836b335111a4775202599f'
PINNED_DATA_LIST_SHA256 = '75ad90d48b644a1dddb43fc5e83edb855418229bd9930eed4e3c6f073b337a48'
RECORD_KEYS = {'snapshot', 'bound', 'typed_from', 'list', 'list_sha256', 'files', 'data_list_sha256', 'symbols'}


@pytest.fixture
def scratch():
    """A neutral scratch directory: pytest's own tmp_path carries the word 'test', which the sealed-path guard refuses."""
    NEUTRAL.mkdir(parents=True, exist_ok=True)
    made = Path(tempfile.mkdtemp(prefix='machinery-', dir=NEUTRAL))
    try:
        yield made
    finally:
        shutil.rmtree(made, ignore_errors=True)


def stand_in(target, *, lists=True):
    """A copy of exactly the 628 listed files of this tree and the pinned ``scripts`` files (step 7g: checks 2 and 3
    compare them too; the main-v10 snapshot holds ``scripts/``); with ``lists`` also the two list files, so that the
    copy can stand in for this tree (``machinery.TREE``) as well as for the snapshot."""
    names = (list(machinery.listed()) + sorted(machinery.SCRIPTS)
             + ([machinery.LIST, machinery.DATA_LIST] if lists else []))
    for relative in names:
        destination = target / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(TREE / relative, destination)
    return target.resolve()


def rows(relative):
    return [tuple(line.split('  ', 1)) for line in (TREE / relative).read_text(encoding='utf-8').splitlines()]


def flip(path):
    data = bytearray(path.read_bytes())
    data[len(data) // 2] ^= 0x01
    path.write_bytes(bytes(data))


def required_count():
    return sum(len(names) for names in machinery.REQUIRED.values())


# ---- check 1: the lists ------------------------------------------------------------------------------------------
def test_list_is_pinned():
    assert machinery.LIST == 'docs/handoff/typed-v2/machinery-main-v10.sha256'
    assert machinery.DATA_LIST == 'docs/handoff/typed-v2/machinery-main-v10-data.sha256'
    assert (machinery.LIST_SHA256, machinery.DATA_LIST_SHA256) == (PINNED_LIST_SHA256, PINNED_DATA_LIST_SHA256)
    assert (machinery.LIST_FILES, machinery.DATA_LIST_FILES) == (564, 64)
    merged = {}
    for relative, pinned, count, python in ((machinery.LIST, PINNED_LIST_SHA256, 564, True),
                                            (machinery.DATA_LIST, PINNED_DATA_LIST_SHA256, 64, False)):
        assert hashlib.sha256((TREE / relative).read_bytes()).hexdigest() == pinned
        found = rows(relative)
        paths = [path for _, path in found]
        assert len(found) == count and paths == sorted(paths) and len(set(paths)) == count  # sorted as LC_ALL=C
        assert all(re.fullmatch(r'[0-9a-f]{64}', digest) and path.startswith('skillopt/') for digest, path in found)
        assert not any(path.startswith('skillopt/execskill/typed/') or '__pycache__' in path for path in paths)
        assert all(path.endswith('.py') is python for path in paths)
        assert not set(paths) & set(merged)
        merged.update((path, digest) for digest, path in found)
    assert machinery.listed() == dict(sorted(merged.items())) and len(merged) == 628


def test_altered_list_is_refused(scratch, monkeypatch):
    for relative in (machinery.LIST, machinery.DATA_LIST):
        (scratch / relative).parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(TREE / relative, scratch / relative)
    monkeypatch.setattr(machinery, 'TREE', scratch)
    assert len(machinery.listed()) == 628
    text = (scratch / machinery.LIST).read_text(encoding='utf-8')
    (scratch / machinery.LIST).write_text(''.join(text.splitlines(keepends=True)[1:]), encoding='utf-8')  # a row less
    with pytest.raises(ValueError, match=r'check 1 refused: the list \S+machinery-main-v10\.sha256 has sha256'):
        machinery.listed()
    with pytest.raises(ValueError, match='check 1 refused'):
        machinery.check(real=False)
    (scratch / machinery.LIST).write_text(text, encoding='utf-8')
    (scratch / machinery.DATA_LIST).unlink()
    with pytest.raises(ValueError, match=r'check 1 refused: the list \S+machinery-main-v10-data\.sha256 cannot be read'):
        machinery.check(real=False)


# ---- checks 1, 3, 5 on this tree -----------------------------------------------------------------------------------
def test_tree_equals_list():
    assert machinery.compare(TREE) == []
    assert machinery.loaded() == {'snapshot': str(TREE), 'bound': False, 'typed_from': str(TREE)}
    record = machinery.check(real=False)
    assert set(record) == RECORD_KEYS
    assert record == {'snapshot': str(TREE), 'bound': False, 'typed_from': str(TREE), 'list': machinery.LIST,
                      'list_sha256': PINNED_LIST_SHA256, 'files': 564, 'data_list_sha256': PINNED_DATA_LIST_SHA256,
                      'symbols': required_count()}
    assert json.loads(json.dumps(record)) == record  # sealed into the manifest by prepare (step 1b)
    assert machinery.check(real=False) == record


def test_compare_skips_typed_and_caches(scratch):
    root = stand_in(scratch / 'tree', lists=False)
    assert machinery.compare(root) == []
    (root / 'skillopt/execskill/typed').mkdir()
    (root / 'skillopt/execskill/typed/anything.py').write_text('VALUE = 1\n')
    (root / 'skillopt/execskill/__pycache__').mkdir(exist_ok=True)
    (root / 'skillopt/execskill/__pycache__/policy.cpython-313.pyc').write_bytes(b'cache')
    assert machinery.compare(root) == []
    assert len(machinery.compare(scratch / 'nowhere')) == 628  # everything missing
    assert {problem for _, problem in machinery.compare(scratch / 'nowhere')} == {'missing'}


# ---- check 3: an altered or extra file in this tree -----------------------------------------------------------------
@pytest.mark.parametrize('relative, alter, problem', [
    ('skillopt/execskill/policy.py', 'flip', 'differs'),
    ('skillopt/execskill/sandbox/policy.json', 'flip', 'differs'),     # a data file
    ('skillopt/coevo5/leakage.py', 'remove', 'missing'),
    ('skillopt/execskill/v225_cards.py', 'symlink', 'symlink'),        # same bytes, but a link
])
def test_altered_file_is_refused(scratch, monkeypatch, relative, alter, problem):
    root = stand_in(scratch / 'tree')
    target = root / relative
    if alter == 'flip':
        flip(target)
    else:
        target.unlink()
        if alter == 'symlink':
            os.symlink(TREE / relative, target)
    assert machinery.compare(root) == [(relative, problem)]
    monkeypatch.setattr(machinery, 'TREE', root)
    with pytest.raises(ValueError, match=r'check 3 refused: this tree \S+ differs from the machinery lists in 1 paths: '
                       + re.escape('%s (%s)' % (relative, problem)) + '$'):
        machinery.check(real=False)


@pytest.mark.parametrize('relative', [
    'skillopt/execskill/v226_extra.py',                 # a module that exists only in this tree's X/
    'skillopt/execskill/extra/__init__.py',             # a new subpackage
    'skillopt/execskill/sneaky.pyc',                    # a sourceless module outside __pycache__
    'skillopt/execskill/sandbox/policy-v2-99.json',     # an unlisted data file
    'skillopt/typed_helper.py',
])
def test_extra_module_under_x_is_refused(scratch, monkeypatch, relative):
    root = stand_in(scratch / 'tree')
    (root / relative).parent.mkdir(parents=True, exist_ok=True)
    (root / relative).write_bytes(b'VALUE = 1\n')
    assert machinery.compare(root) == [(relative, 'unlisted')]
    monkeypatch.setattr(machinery, 'TREE', root)
    with pytest.raises(ValueError, match=r'check 3 refused: .* in 1 paths: ' + re.escape(relative + ' (unlisted)')):
        machinery.check(real=False)


def test_symlinked_directory_is_refused(scratch, monkeypatch):
    root = stand_in(scratch / 'tree')
    elsewhere = scratch / 'elsewhere'
    elsewhere.mkdir()
    (elsewhere / 'hidden.py').write_text('VALUE = 1\n')
    os.symlink(elsewhere, root / 'skillopt/execskill/linked')
    assert machinery.compare(root) == [('skillopt/execskill/linked', 'symlink')]
    monkeypatch.setattr(machinery, 'TREE', root)
    with pytest.raises(ValueError, match=re.escape('skillopt/execskill/linked (symlink)')):
        machinery.check(real=False)


# ---- check 5: the frozen names -------------------------------------------------------------------------------------
def test_required_names_are_frozen_machinery():
    files = machinery.listed()
    for module, names in machinery.REQUIRED.items():
        path = module.replace('.', '/')
        assert path + '.py' in files or path + '/__init__.py' in files, module  # listed, so never a typed module
        assert names and len(set(names)) == len(names) and all(name.isidentifier() for name in names), module
    required = {(module, name) for module, names in machinery.REQUIRED.items() for name in names}
    assert {  # DESIGN 3.1 (private helpers of the copied content_violation and the retry texts), 3.2, 3.3, 3.5
        ('skillopt.execskill.v225_cards', '_reference_values'), ('skillopt.execskill.v225_cards', 'PATH_LIKE'),
        ('skillopt.execskill.v225_cards', 'CARD_RETRY'), ('skillopt.execskill.v225_cards', 'RETRY_REASONS'),
        ('skillopt.execskill.v225_cards', 'CARD_WRITER_INPUT_CHARS'), ('skillopt.coevo5.leakage', '_numbers'),
        ('skillopt.coevo5.leakage', '_numeric'), ('skillopt.coevo5.leakage', '_significant'),
        ('skillopt.coevo5.leakage', '_value'), ('skillopt.coevo5.leakage', '_grams'),
        ('skillopt.execskill.engineer', 'absent_findings'), ('skillopt.execskill.policy', 'check'),
        ('skillopt.execskill.policy', 'source_limit'), ('skillopt.execskill.engineer_reader', 'tolerant_json'),
        ('skillopt.execskill.sandbox.client', 'unit_tag'), ('skillopt.execskill.sandbox.client', 'drain_unit'),
    } <= required
    assert machinery.require_symbols() == len(required) == required_count()


def test_missing_required_name_is_refused(monkeypatch):
    policy = 'skillopt.execskill.policy'
    monkeypatch.setitem(machinery.REQUIRED, policy, machinery.REQUIRED[policy] + ('_no_such_private_name',))
    with pytest.raises(ValueError, match=r'check 5 refused: 1 frozen names missing: '
                                         r'skillopt\.execskill\.policy\._no_such_private_name$'):
        machinery.require_symbols()
    with pytest.raises(ValueError, match='check 5 refused'):
        machinery.check(real=False)
    monkeypatch.setitem(machinery.REQUIRED, 'skillopt.execskill.no_such_module', ('anything',))
    with pytest.raises(ValueError, match=r'check 5 refused: 2 frozen names missing: skillopt\.execskill\.no_such_module '
                                         r'\(import failed: ModuleNotFoundError\), skillopt\.execskill\.policy\.'):
        machinery.require_symbols()


# ---- checks 2 and 4: real starts -----------------------------------------------------------------------------------
def test_real_check_refuses_unbound_wrong_and_altered_snapshots(scratch, monkeypatch):
    with pytest.raises(ValueError, match='check 2 refused: a real start imports skillopt from the snapshot'):
        machinery.check(real=True)  # this process imports skillopt from this tree
    assert machinery.misplaced(machinery.loaded()) == []  # check 4 itself holds for the binding this process has
    snapshot = stand_in(scratch / 'snap', lists=False)
    binding = {'snapshot': str(snapshot), 'bound': True, 'typed_from': str(TREE)}
    monkeypatch.setattr(machinery, 'loaded', lambda: dict(binding))
    with pytest.raises(ValueError, match='expected the snapshot ' + re.escape(str(Path(MACHINERY_SNAPSHOT).resolve()))):
        machinery.check(real=True)
    # every file equal, so checks 1, 2, 3 and 5 pass; check 4 refuses: this process loaded the machinery from the tree
    loaded = sorted(name for name, module in sys.modules.items()
                    if module is not None and (name == 'skillopt' or name.startswith('skillopt.')))
    wrong = machinery.misplaced(binding)
    assert wrong and wrong == [name for name in loaded if not (name == 'skillopt.execskill.typed'
                                                               or name.startswith('skillopt.execskill.typed.'))]
    with pytest.raises(ValueError, match=r'check 4 refused: \d+ skillopt modules are loaded from outside'):
        machinery.check(real=True, snapshot=snapshot)
    for relative in ('skillopt/execskill/package.py', 'skillopt/execskill/sandbox/policy.json'):
        flip(snapshot / relative)
        with pytest.raises(ValueError, match=r'check 2 refused: the snapshot \S+ differs from the machinery lists in '
                                             r'1 paths: ' + re.escape(relative + ' (differs)') + '$'):
            machinery.check(real=True, snapshot=snapshot)
        shutil.copyfile(TREE / relative, snapshot / relative)
    (snapshot / 'skillopt/execskill/extra.py').write_text('VALUE = 1\n')
    with pytest.raises(ValueError, match=re.escape('skillopt/execskill/extra.py (unlisted)')):
        machinery.check(real=True, snapshot=snapshot)
    (snapshot / 'skillopt/execskill/extra.py').unlink()
    (snapshot / 'skillopt/execskill/typed').mkdir()
    (snapshot / 'skillopt/execskill/typed/__init__.py').write_text("VERSION = 'typed-v1'\n")
    with pytest.raises(ValueError, match=r'check 2 refused: the snapshot \S+ holds skillopt/execskill/typed'):
        machinery.check(real=True, snapshot=snapshot)


# ---- step 7g: REQUIRED is the static scan of typed ------------------------------------------------------------------
def test_required_equals_the_static_scan_of_typed():
    scan = machinery.frozen_uses()
    assert scan['writes'] == {}  # typed assigns or deletes no attribute of a frozen module
    machinery_uses = {module: names for module, names in scan['uses'].items() if module.split('.')[0] == 'skillopt'}
    assert machinery_uses == {module: list(names) for module, names in machinery.REQUIRED.items()}
    assert all(list(names) == sorted(set(names)) for names in machinery.REQUIRED.values())
    # names first used after step 1m (6s, rp-int, D16 / D17) are among them; the stale typed-v1 names are gone
    required = {(module, name) for module, names in machinery.REQUIRED.items() for name in names}
    assert {('skillopt.execskill.v218_lock', 'call'), ('skillopt.coevo5.cells', 'Pause'),
            ('skillopt.execskill.errors', 'stop_kind'), ('skillopt.validator_pilot.api', 'digest'),
            ('skillopt.execskill.profiles', 'cleanup_grace_seconds'), ('skillopt.execskill.notes', 'FIELD_TYPES'),
            ('skillopt.execskill.policy', 'RULES')} <= required
    assert not {('skillopt.execskill.engineer_v295', 'system'), ('skillopt.execskill.engineer_reader', 'read')} & required
    # every name engineer_prompt declares it reads is required too
    assert {(m, n) for m, names in __import__('skillopt.execskill.typed.engineer_prompt', fromlist=['x'])
            .MACHINERY_SYMBOLS.items() for n in names} <= required
    assert [module for module in scan['uses'] if module.split('.')[0] == 'scripts'] == ['scripts.weak_solver_probe']


SCAN_SOURCE = '''
from skillopt.execskill import policy, sandbox
from skillopt.execskill.sandbox import client as box
import skillopt.execskill.policy as unused
from . import cards


def solve(client, view):
    client.call(view)                   # a parameter that shares a name with no alias: never the module
    return policy.check, box.unit_tag, sandbox.client.Docker, cards.anything


def local():
    from skillopt.execskill.policy import RULES
    policy = RULES
    return policy.real                  # a local variable named like the alias: not the module


label: policy.Annotation = 1            # an annotation is never evaluated
policy.PATCHED = 1                      # a write on a frozen module
lazy = lambda: policy.IN_LAMBDA


class Holder:
    policy = None

    def method(self):
        return policy.inside            # a class body's names are not visible in its methods
'''


def test_the_scan_follows_imports_and_scopes(scratch):
    for relative in ('skillopt/__init__.py', 'skillopt/execskill/__init__.py', 'skillopt/execskill/policy.py',
                     'skillopt/execskill/sandbox/__init__.py', 'skillopt/execskill/sandbox/client.py',
                     'skillopt/execskill/typed/__init__.py', 'skillopt/execskill/typed/cards.py'):
        (scratch / relative).parent.mkdir(parents=True, exist_ok=True)
        (scratch / relative).write_text('')
    (scratch / 'skillopt/execskill/typed/user.py').write_text(SCAN_SOURCE)
    found = machinery.frozen_uses(scratch)
    assert found['uses'] == {'skillopt.execskill.policy': ['IN_LAMBDA', 'RULES', 'check', 'inside'],
                             'skillopt.execskill.sandbox.client': ['Docker', 'unit_tag']}
    assert found['writes'] == {'skillopt.execskill.policy': ['PATCHED']}
    assert found['modules'] == ['skillopt.execskill.policy', 'skillopt.execskill.sandbox',
                                'skillopt.execskill.sandbox.client']
    assert machinery.import_closure(found['modules'], scratch) == [
        'skillopt', 'skillopt.execskill', 'skillopt.execskill.policy', 'skillopt.execskill.sandbox',
        'skillopt.execskill.sandbox.client']


# ---- step 7g: the scripts modules of a bound run --------------------------------------------------------------------
def test_scripts_pins_are_the_import_closure_of_typed():
    closure = machinery.import_closure(machinery.frozen_uses()['modules'])
    scripts = sorted(machinery.module_file(m).relative_to(TREE).as_posix() for m in closure if m.split('.')[0] == 'scripts')
    assert scripts == sorted(machinery.SCRIPTS) and 'scripts/weak_solver_probe.py' in scripts  # RP12 / Q19
    assert {relative: hashlib.sha256((TREE / relative).read_bytes()).hexdigest() for relative in scripts} == machinery.SCRIPTS
    assert machinery.compare_scripts(TREE) == [] and 'scripts/run_typed.py' not in machinery.SCRIPTS
    assert machinery.TYPED_SCRIPTS == ('scripts.run_typed',)


@pytest.mark.parametrize('alter, problem', [('flip', 'differs'), ('remove', 'missing'), ('symlink', 'symlink')])
def test_an_altered_scripts_file_is_refused(scratch, monkeypatch, alter, problem):
    root = stand_in(scratch / 'tree')
    relative = 'scripts/weak_solver_probe.py'
    if alter == 'flip':
        flip(root / relative)
    else:
        (root / relative).unlink()
        if alter == 'symlink':
            os.symlink(TREE / relative, root / relative)
    assert machinery.compare_scripts(root) == [(relative, problem)] and machinery.compare(root) == []
    monkeypatch.setattr(machinery, 'TREE', root)
    with pytest.raises(ValueError, match=r'check 3 refused: this tree \S+ differs from the machinery lists in 1 paths: '
                       + re.escape('%s (%s)' % (relative, problem)) + '$'):
        machinery.check(real=False)
    shutil.rmtree(root / 'scripts')
    os.symlink(TREE / 'scripts', root / 'scripts')
    assert machinery.compare_scripts(root) == [('scripts', 'symlink')]


def test_loaded_scripts_modules_must_be_pinned_files_of_the_snapshot(scratch, monkeypatch):
    snapshot = stand_in(scratch / 'snap', lists=False)
    unbound = {'snapshot': str(TREE), 'bound': False, 'typed_from': str(TREE)}
    bound = {'snapshot': str(snapshot), 'bound': True, 'typed_from': str(TREE)}
    for name, file in (('scripts', snapshot / 'scripts/__init__.py'),
                       ('scripts.weak_solver_probe', snapshot / 'scripts/weak_solver_probe.py'),
                       ('scripts.run_typed', TREE / 'scripts/run_typed.py')):
        module = types.ModuleType(name)
        module.__file__ = str(file)
        monkeypatch.setitem(sys.modules, name, module)
    for name in [n for n in sys.modules if n.startswith('scripts.') and n not in
                 ('scripts.weak_solver_probe', 'scripts.run_typed')]:
        monkeypatch.delitem(sys.modules, name)
    assert machinery.misplaced_scripts(bound) == [] and machinery.misplaced_scripts(unbound) == []
    for name, file in (('scripts.weak_solver_probe', TREE / 'scripts/weak_solver_probe.py'),   # from the tree
                       ('scripts.make_kor_probes', snapshot / 'scripts/make_kor_probes.py'),     # not pinned
                       ('scripts.run_typed', snapshot / 'scripts/run_typed.py')):                # typed code elsewhere
        module = types.ModuleType(name)
        module.__file__ = str(file)
        monkeypatch.setitem(sys.modules, name, module)
        assert machinery.misplaced_scripts(bound) != [] and name in machinery.misplaced_scripts(bound)
        assert machinery.misplaced_scripts(unbound) == []


# ---- step 7g: check 6, the pinned texts ------------------------------------------------------------------------------
def test_check_6_pins_every_pinned_text():
    from skillopt.execskill.typed import cards, engineer_prompt, replies
    texts = machinery.pinned_texts()
    assert set(texts) == set(machinery.TEXT_PINS)
    assert {name: hashlib.sha256(text.encode('utf-8')).hexdigest() for name, text in texts.items()} == machinery.TEXT_PINS
    assert machinery.TEXT_PINS['cards.copied_source'] == cards.COPIED_SOURCE_SHA256
    assert machinery.check_pins() == len(engineer_prompt.PINS) + len(replies.PINS) + len(machinery.TEXT_PINS) == 33
    # the D16 member and D17 base card sentences carry the same pins as their own tests (one value, two places)
    from tests import test_typed2_base, test_typed2_shared
    for name, pin in test_typed2_shared.SENTENCE_SHA256.items():
        assert machinery.TEXT_PINS[name] == pin
    assert machinery.TEXT_PINS['writers.BASE_CARD_MEANING'] == test_typed2_base.LABEL_SHA256['writers']
    assert machinery.TEXT_PINS['engineer_prompt.BASE_CARD_MEANING'] == test_typed2_base.LABEL_SHA256['engineer']


@pytest.mark.parametrize('module_name, name, change, message', [
    ('writers', 'MEMBER_RULE', lambda v: v + ' ', r'1 pinned texts differ from TEXT_PINS: writers\.MEMBER_RULE$'),
    ('writers', 'MEMBERS_MEANING', lambda v: v.replace('no worse', 'not worse'), r'writers\.MEMBERS_MEANING$'),
    ('engineer_prompt', 'BASE_CARD_MEANING', lambda v: v + ' ', r'engineer_prompt\.BASE_CARD_MEANING$'),
    ('cards', 'REASON_TOO_LONG', lambda v: v.replace('cut', 'remove'), r'cards\.REASON_TOO_LONG$'),
    ('cards', 'RETRY_SHORT', lambda v: dict(v, length='too long'), r'retry texts shared with typed-v1'),
    ('cards', 'COPIED_SOURCE_SHA256', lambda v: '0' * 64, r'no longer holds the lines the card screen copies'),
    ('replies', 'READER', lambda v: v + '-x', r'replies\.READER$'),
    ('replies', 'FORMAT_RETRY_SYSTEM', lambda v: v + ' ', r'the pinned reply texts format_retry_system differ'),
    ('engineer_prompt', 'PROMPT_VERSION', lambda v: v + '-x', r'engineer_prompt\.PROMPT_VERSION$'),
])
def test_check_6_refuses_a_changed_pinned_text(monkeypatch, module_name, name, change, message):
    module = __import__('skillopt.execskill.typed.' + module_name, fromlist=['x'])
    monkeypatch.setattr(module, name, change(getattr(module, name)))
    with pytest.raises(ValueError, match='check 6 refused: .*' + message):
        machinery.check_pins()
    with pytest.raises(ValueError, match='check 6 refused'):
        machinery.check(real=False)


def test_check_6_refuses_changed_engineer_pins_and_bound_retry_text(monkeypatch):
    from skillopt.execskill import v225_cards
    from skillopt.execskill.typed import engineer_prompt
    key = ('searchqa', 'propose')
    monkeypatch.setitem(engineer_prompt.PINS, key, '0' * 64)
    with pytest.raises(ValueError, match=r'check 6 refused: engineer_prompt: the sha256 of the searchqa\.propose text'):
        machinery.check_pins()
    monkeypatch.undo()
    monkeypatch.setattr(v225_cards, 'CARD_RETRY', v225_cards.CARD_RETRY + ' ')  # the bound text, as another snapshot
    with pytest.raises(ValueError, match='retry texts shared with typed-v1 .* differ from the bound v225_cards'):
        machinery.check_pins()


# ---- step 7g: the ONE bound harness (DESIGN 5), a fresh interpreter per case -------------------------------------------
DRIVER = TREE / 'tests' / 'typed2_bound_driver.py'
# what the frozen v222_cards reads beside skillopt/ (FIXTURE and instruction_start.FIXTURE); the real snapshot holds it
BESIDE = ('tests/fixtures/execskill/v222_cards', 'docs/handoff/v29-20261026/v210-instructions-coevo5-v1.json')


def bound_snapshot(target):
    """The stand-in machinery snapshot: the 564 listed .py files and the 64 data files, the pinned scripts files and
    the data read beside skillopt/; no typed package, nothing else of this tree."""
    root = stand_in(target, lists=False)
    for relative in BESIDE:
        if (TREE / relative).is_dir():
            shutil.copytree(TREE / relative, root / relative, ignore=shutil.ignore_patterns('__pycache__'))
        else:
            (root / relative).parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(TREE / relative, root / relative)
    return root


def bound_tree(target):
    """A stand-in of this tree for the tree-side guard cases: the listed files, the lists, the pinned scripts files,
    the typed package and its launcher (this tree is never edited)."""
    root = stand_in(target)
    shutil.copytree(TREE / machinery.TYPED, root / machinery.TYPED, ignore=shutil.ignore_patterns('__pycache__'))
    shutil.copyfile(TREE / 'scripts/run_typed.py', root / 'scripts/run_typed.py')
    return root


def run_driver(snapshot, tree, scratch, *extra):
    env = {key: value for key, value in os.environ.items() if key != 'PYTHONPATH'}
    env['TMPDIR'] = str(NEUTRAL)
    done = subprocess.run([sys.executable, '-I', str(DRIVER), str(snapshot), str(tree), str(scratch / 'work'), *extra],
                          cwd=str(scratch), env=env, capture_output=True, text=True, timeout=300)
    assert done.returncode == 0, done.stderr[-4000:]
    return json.loads(done.stdout.strip().splitlines()[-1])


def test_bound_interpreter_runs_every_area_on_the_snapshot(scratch):
    snapshot = bound_snapshot(scratch / 'snap')
    found = run_driver(snapshot, TREE, scratch)
    assert found['stage'] == 'done' and 'refused' not in found and found['preloaded'] == []
    assert found['binding']['sys_path_0'] == str(snapshot) and found['binding']['execskill_file'].startswith(str(snapshot))
    assert found['record'] == {'snapshot': str(snapshot), 'bound': True, 'typed_from': str(TREE),
                               'list': machinery.LIST, 'list_sha256': PINNED_LIST_SHA256, 'files': 564,
                               'data_list_sha256': PINNED_DATA_LIST_SHA256, 'symbols': required_count()}
    assert found['final_check'] is True
    stems = sorted(path.stem for path in (TREE / machinery.TYPED).glob('*.py'))
    assert found['typed_modules'] == stems and 'readplan' in stems and 'machinery' in stems
    cases = found['cases']
    assert cases['scan'] == {'required_equal': True, 'scripts_uses': ['scripts.weak_solver_probe'],
                             'scripts_uses_pinned': True, 'closure_equal': True, 'writes': {},
                             'symbols': required_count()}
    assert cases['prompts'] == {'rendered': 10, 'pinned': 10, 'reply_format_inside': 10, 'verify': True}
    assert cases['card'] == {'passed': {'violation': None, 'chars': 4500, 'bullets': 0},
                             'failed': {'violation': 'length', 'chars': 4501, 'bullets': 0},
                             'content': ['format_markers', 'format_markers']}
    assert cases['reply'] == {'read': [True, True], 'screen': []}
    mount = cases['mount']
    assert mount['all_equal'] and mount['historical_base_is_c'] and mount['format_base_is_c0']
    assert mount['searchqa_card_differs_from_format'] and len(mount['rows']) == 16
    assert all(row['offered'] == [] and row['forced'] is None for row in mount['rows'])
    capture = cases['capture']
    assert capture['stable'] and capture['arms_differ'] and capture['scratch_untouched']
    # read plan T7 (R14; fix-c, review F1): the unit label reaches no hook input and no request, only the load
    # request's package_sha256; the program is enabled and fires, and its note is in the first request
    label = cases['label']
    assert label['enabled'] == [['prog-t01-s1-a']] * 2 and label['fired'] == [['fx-label']] * 2
    assert label['hook_calls'] == [['fx-label', 'applies'], ['fx-label', 'before_call']]
    assert label['note_in_first_request'] == [[True], [True]] and label['sends'][0] == label['sends'][1] >= 1
    assert label['selections_equal'] and label['hooks_equal'] and label['sends_equal']
    assert label['loads'] == [1, 1] and label['loads_equal_but_package'] and label['load_packages'] == [True, True]
    assert label['packages_differ'] and label['scratch_untouched']
    origins = found['origins']
    assert origins['outside'] == [] and origins['misplaced'] == [] and origins['misplaced_scripts'] == []
    assert origins['counts']['typed'] == len(stems) and origins['counts']['machinery'] > 50
    assert origins['counts']['scripts'] >= 2  # scripts and scripts.weak_solver_probe, from the snapshot
    assert origins['binding'] == {'snapshot': str(snapshot), 'bound': True, 'typed_from': str(TREE)}


def _append(path, data):
    with open(path, 'ab') as handle:
        handle.write(data)


GUARD_CASES = {
    # case: (where, relative path, how, stage, message pattern)
    'altered listed file': ('snapshot', 'skillopt/execskill/policy.py', b'\n# altered\n', 'check',
                            r'check 2 refused: the snapshot \S+ differs from the machinery lists in 1 paths: '
                            r'skillopt/execskill/policy\.py \(differs\)$'),
    'altered data file': ('snapshot', 'skillopt/execskill/sandbox/policy.json', b'\n', 'check',
                          r'check 2 refused: .* in 1 paths: skillopt/execskill/sandbox/policy\.json \(differs\)$'),
    'altered scripts file': ('snapshot', 'scripts/weak_solver_probe.py', b'\n# altered\n', 'check',
                             r'check 2 refused: .* in 1 paths: scripts/weak_solver_probe\.py \(differs\)$'),
    'snapshot with a typed package': ('snapshot', 'skillopt/execskill/typed/__init__.py', b"VERSION = 'typed-v1'\n",
                                      'bind', r'holds its own skillopt/execskill/typed'),
    'extra module under the tree X': ('tree', 'skillopt/execskill/v226_extra.py', b'VALUE = 1\n', 'check',
                                      r'check 3 refused: this tree \S+ differs from the machinery lists in 1 paths: '
                                      r'skillopt/execskill/v226_extra\.py \(unlisted\)$'),
    'altered pinned text': ('tree', 'skillopt/execskill/typed/writers.py', b"\nMEMBER_RULE = MEMBER_RULE + ' '\n",
                            'check', r'check 6 refused: 1 pinned texts differ from TEXT_PINS: writers\.MEMBER_RULE$'),
    'missing private name': ('snapshot', None, None, 'check',
                             r'check 5 refused: 1 frozen names missing: '
                             r'skillopt\.execskill\.v225_cards\._no_such_private_helper$'),
}


@pytest.mark.parametrize('case', sorted(GUARD_CASES))
def test_the_bound_guard_refuses_each_altered_case(scratch, case):
    where, relative, data, stage, pattern = GUARD_CASES[case]
    snapshot = bound_snapshot(scratch / 'snap')
    tree = bound_tree(scratch / 'tree') if where == 'tree' else TREE
    extra = ('--missing', 'skillopt.execskill.v225_cards:_no_such_private_helper') if relative is None else ()
    if relative is not None:
        target = (snapshot if where == 'snapshot' else tree) / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        _append(target, data)
    found = run_driver(snapshot, tree, scratch, *extra)
    assert found['stage'] == stage and 'cases' not in found, found
    assert re.search(pattern, found['refused']), found['refused']
    assert found['preloaded'] == []


def test_the_bound_launcher_runs_the_configured_smoke_plan_replay_status_and_readout(scratch):
    """spec/identity.md 4 (vii), impl/rp-int.md: the launcher itself, bound by ``--machinery-snapshot`` to the stand-in
    snapshot: a fake smoke with the typed-v2 smoke's sealed values (``--configured``: learn_first, unit_shared,
    historical base, economy reads with the probe) completes with every pair settled, ``plan-replay`` of its bound plan
    is equal, and ``status`` and ``readout`` run on its root."""
    snapshot = bound_snapshot(scratch / 'snap')
    root = scratch / 'runs' / 'run'
    root.parent.mkdir()
    env = {key: value for key, value in os.environ.items() if key != 'PYTHONPATH'}
    env['TMPDIR'] = str(NEUTRAL)

    def launcher(*argv):
        done = subprocess.run([sys.executable, '-I', str(TREE / 'scripts' / 'run_typed.py'), '--machinery-snapshot',
                               str(snapshot), *argv], cwd=str(scratch), env=env, capture_output=True, text=True,
                              timeout=600)
        assert done.returncode == 0, (argv, done.stderr[-3000:])
        return json.loads(done.stdout)

    smoked = launcher('smoke', '--root', str(root), '--chain', 'G', '--fake', '--configured')
    assert smoked['status'] == 'complete' and smoked['exit_code'] == 0
    assert smoked['read_plan']['mode'] == 'economy' and smoked['read_plan']['reads']['settled'] == 35
    smoke_root = root.with_name(root.name + '-smoke')
    replayed = launcher('plan-replay', '--root', str(smoke_root), '--chain', 'G', '--smoke', '--fake')
    assert replayed['verdict'] == 'equal' and replayed['different'] == 0 and replayed['files'] == replayed['equal']
    assert launcher('status', '--root', str(smoke_root))['chains']['G']['ledger']['sends'] > 0
    assert launcher('readout', '--root', str(smoke_root))['command'] == 'readout'
