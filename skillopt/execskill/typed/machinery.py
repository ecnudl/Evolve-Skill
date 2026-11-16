"""typed-v2 machinery guard (DESIGN 3.5 and 5; addendum F2, F11): the frozen main-v10 machinery this tree runs with.

The real run imports every ``skillopt`` module outside ``skillopt.execskill.typed`` from the main-v10 code snapshot
(``scripts/run_typed.py --machinery-snapshot``, DESIGN 2 F1) and only ``typed`` from this tree. An edited copy of a
machinery file in this tree would silently not exist in the real run, and a module that exists only in this tree's
``skillopt/execskill`` would silently become importable there. The guard pins the two lists of the frozen files
(``LIST``: the 564 ``.py`` files outside ``typed``; ``DATA_LIST``: the 64 other files, made from the snapshot on dl)
and ``check`` refuses, before any model call, when one of six checks fails:

1. each list file has its pinned sha256 and row count (``listed``);
2. real only: the bound snapshot is the expected one and holds exactly the listed files with their listed sha256,
   the pinned ``scripts`` files (``SCRIPTS``) and no ``typed`` package;
3. this tree holds exactly the listed files outside ``typed``: none missing, none changed, no unlisted file of any
   kind (``.py`` or other); and the pinned ``scripts`` files;
4. real only: every loaded ``skillopt`` module outside ``typed`` has its file under the snapshot, every ``typed``
   module under this tree (``misplaced``), every loaded ``scripts`` module is a pinned file of the snapshot
   (``misplaced_scripts``);
5. every frozen name that ``typed`` uses exists (``REQUIRED``, ``require_symbols``);
6. the pinned texts of ``typed`` (``check_pins``, ``TEXT_PINS``).

``__pycache__`` directories are not compared (caches of listed sources); a symbolic link inside the compared area
is a problem of its own and is never followed. The guard itself uses the standard library only, so that it does not
depend on the machinery it checks; files are read as bytes, never executed. Only checks 5 and 6 import anything: the
modules named in ``REQUIRED`` and the ``typed`` modules that hold pinned texts. ``frozen_uses`` and
``import_closure`` (a static scan, read by the tests and the bound driver, never by ``check``) show that ``REQUIRED``
and ``SCRIPTS`` cover what ``typed`` uses.
"""
from __future__ import annotations

import ast
import hashlib
import importlib
import json
import os
import re
import sys
from pathlib import Path

from . import MACHINERY_SNAPSHOT

LIST = 'docs/handoff/typed-v2/machinery-main-v10.sha256'
LIST_SHA256 = '3c37fdd90de0e6b51013af7fd4f166f3fa9a1fead5836b335111a4775202599f'
LIST_FILES = 564
DATA_LIST = 'docs/handoff/typed-v2/machinery-main-v10-data.sha256'
DATA_LIST_SHA256 = '75ad90d48b644a1dddb43fc5e83edb855418229bd9930eed4e3c6f073b337a48'
DATA_LIST_FILES = 64
PACKAGE = 'skillopt'
TYPED = 'skillopt/execskill/typed'
TYPED_MODULE = 'skillopt.execskill.typed'
CACHE = '__pycache__'
ROW =re.compile(r'([0-9a-f]{64})  (skillopt/[^\n]+)')
SHOWN = 10
TREE = Path(__file__).resolve().parents[3]

# Every frozen name that ``typed`` uses, as {module: (names, ...)}; check 5 imports each module and requires each
# name. Exactly the ``skillopt`` part of the static scan ``frozen_uses()`` of the final ``T/`` (Step 7; a test holds the
# two equal): every name ``typed`` imports from a frozen module or reads on one, function-level imports, lazy imports
# and the private helpers of the copies (``cards``: DESIGN 3.1) included. The ``scripts`` part is pinned by file
# (``SCRIPTS``), a stronger pin than a name.
REQUIRED = {
    'skillopt.coevo5.cells': ('Pause',),
    'skillopt.coevo5.data': ('TestAccess', 'ranked', 'test_panel'),
    'skillopt.coevo5.leakage': ('LEAK_MIN_SIGNIFICANT_DIGITS', 'LEAK_MIN_SINGLE_WORD', '_grams', '_numbers',
                                '_numeric', '_significant', '_value', 'normalize'),
    'skillopt.coevo5.ledger': ('_usage', 'request_bytes', 'settle'),
    'skillopt.coevo5.protocol': ('CLIENT_ATTEMPTS', 'RESERVATION_OVERHEAD'),
    'skillopt.coevo5.roles': ('fit',),
    'skillopt.coevo5.texts': ('instruction_text',),
    'skillopt.continual_eval.backends': ('readiness', 'score'),
    'skillopt.continual_eval.core': ('require',),
    'skillopt.execskill.chain': ('heavy',),
    'skillopt.execskill.client': ('NORTHGATE_ENV', 'NORTHGATE_RESPONSE_MODEL_IDS', 'unpooled'),
    'skillopt.execskill.corpus': ('Corpus',),
    'skillopt.execskill.engineer': ('EDIT_KINDS', 'OPTIONAL', 'PROCEDURE_KEYS', 'absent_findings'),
    'skillopt.execskill.engineer_payload': ('trim', 'view_excerpt'),
    'skillopt.execskill.engineer_reader': ('FENCE', 'MAX_JSON_DEPTH', 'MAX_REPLY_BYTES', 'Unusable', 'defined_hooks',
                                           'normalize', 'schema', 'tolerant_json'),
    'skillopt.execskill.errors': ('PackageInvalid', 'STOP_KINDS', 'stop_kind'),
    'skillopt.execskill.evaluation': ('_registry', '_sheet_qualification', '_with_views', 'alfworld_reset'),
    'skillopt.execskill.judge': ('judge',),
    'skillopt.execskill.manifest': ('_items', '_slot_sizes', 'check_clients', 'limits_of', 'make_solver',
                                    'role_settings', 'solver_block'),
    'skillopt.execskill.notes': ('FIELD_TYPES',),
    'skillopt.execskill.package': ('MAX_STATE_BYTES', 'NOTE_HOOKS', 'Package', 'Procedure', 'SECOND_CALL_HOOKS',
                                   'empty'),
    'skillopt.execskill.policy': ('FORBIDDEN_ATTRIBUTES', 'FORBIDDEN_MODULES', 'FORBIDDEN_NAMES', 'FROM_ONLY',
                                  'IMPORTABLE', 'MAX_CONSTANT_CHARS', 'ORDINARY_ATTRIBUTES', 'RECEPTACLES', 'RULES',
                                  'check', 'source_limit'),
    'skillopt.execskill.prelaunch': ('SNAPSHOT_DIRS', 'env_files', 'sha256_list'),
    'skillopt.execskill.profiles': ('CONSENT_FIELDS', 'ENGINEER_SHOWN', 'LIVE_SANDBOX_UNIT_CAP', 'MAX_CHANGES',
                                    'MAX_DESCRIPTION_CHARS', 'MAX_HEADER_CHARS', 'MAX_NOTE_CHARS', 'NEVER_WRITTEN',
                                    'POLICY_VERSIONS', 'ROLE_INPUT_BYTES', 'RUN_ROOTS', 'SANDBOX_TIMEOUTS',
                                    'ZEBRA_PC_V15', 'cleanup_grace_seconds', 'ready_timeout_seconds'),
    'skillopt.execskill.protocol': ('CHAINS', 'FIRST_CALL_SYSTEM', 'FIRST_CALL_USER'),
    'skillopt.execskill.routes': ('BRANCH', 'S1B_CEILING', 'pin'),
    'skillopt.execskill.sandbox.client': ('Docker', 'Worker', 'drain_unit', 'unit_tag'),
    'skillopt.execskill.slots': ('CALL', 'EPISODE', 'LIVE', 'NATIVE', 'pools'),
    'skillopt.execskill.solver': ('_user', 'routing_view', 'solve'),
    'skillopt.execskill.step': ('_sheet_reference',),
    'skillopt.execskill.v218_lock': ('call',),
    'skillopt.execskill.v222_cards': ('format_text', 'historical_text'),
    'skillopt.execskill.v225_cards': ('CARD_JOIN', 'CARD_RETRY', 'CARD_REVISE_SYSTEM', 'CARD_WRITER_INPUT_CHARS',
                                      'CARD_WRITE_SYSTEM', 'MAX_CARD_BULLETS', 'MAX_CARD_CHARS', 'PATH_LIKE',
                                      'RETRY_REASONS', '_reference_values', 'card_violation'),
    'skillopt.execskill.v225_writer': ('FORBIDDEN', 'REFERENCE_CHARS', 'REPLY_HEAD', 'REPLY_TAIL', 'VIEW_CHARS',
                                       'task_card', 'truncate'),
    'skillopt.execskill.zebralogic': ('BENCH', 'CARD_TEXT', 'EXCLUDED_IDS', 'EXCLUDED_IDS_SHA256', 'POOL_PATH',
                                      'POOL_SHA256', 'load_pool', 'test_panel'),
    'skillopt.validator_pilot.api': ('digest',),
}

# The ``scripts`` modules a bound run can import (addendum RP12 / Q19, spec/read-plan.md 5.3: ``weak_solver_probe``
# sets chain G's thinking, effort and max tokens and the request body of both chains), on neither list: the bound run
# takes them from the snapshot (``bind_machinery`` puts it first on ``sys.path``). The set is the static import
# closure of ``typed`` through the frozen modules (``import_closure``; a test holds the two equal), an
# over-approximation of what the run can import, each file pinned by its sha256 as this tree holds it (history: none
# changed after 2026-10-21, before main-v10). Checks 2 and 3 compare the files, check 4 the loaded modules.
SCRIPTS_PACKAGE = 'scripts'
SCRIPTS = {
    'scripts/__init__.py': 'e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855',
    'scripts/continue_fivebench_baselines.py': '8b7cccb6c45c7e27116abd38e89191b74f36e9d2f962700e167c7d1f2cbb8c57',
    'scripts/generate_zero_shot_skill.py': '393b57031fc5464dcf77ea8fe062d294ad9974e336030720d97499f27198e734',
    'scripts/make_extension_study.py': '56b70ba62918bb15bfb8a9afbb6ee0eb4475c85f517b6a04435f3207e039c048',
    'scripts/make_searchqa_fresh_sample.py': '8966294e3b4645d8feb10de39da7fe973ba202b8af83fed8f04bd1b482277919',
    'scripts/pilot_livemath_headroom.py': 'bb6a428daeba5477147ab4b687f0c0168f8ba7fcccd93ae6fe2ab0ab400a00ff',
    'scripts/pilot_officeqa_headroom.py': 'c1fb57307430ab416a8349718ac18f1582107e30d860dd59aaab916ccc4861cc',
    'scripts/replay_sheet_v6.py': 'bd71af36ab0876f2b8407338e8e5c8d4b42929ac1ebd0c66085b582aea12792f',
    'scripts/run_active_evidence_panel_eval.py': '04bb5f7fac83a12667b9a42cdbfa00f9b45e1776ef41916e886f11d163146845',
    'scripts/run_fivebench_g_stage.py': '29b096a150987c06d55bb4628f34e3395314b63f84c91ddbe25f1c464b29ae99',
    'scripts/weak_solver_probe.py': 'd62a002ef5d44fcd194d195bfd11486c8cdd418d251b9423398cf13a20ee00d6',
}
# The one ``scripts`` module that is typed code (``prepare.TYPED_CODE``): when a process imports it as a module (the
# local tests do; the bound run runs it as ``__main__``), it comes from this tree.
TYPED_SCRIPTS = ('scripts.run_typed',)

# Check 6 (DESIGN 3.5, 4.3; addendum RP14), the one rule for all pinned texts of ``typed``: the sha256 of every pinned
# text as ``pinned_texts()`` gives it. The ten engineer system texts and the reply texts keep their own pin tables
# and self-checks (``engineer_prompt.PINS`` / ``verify()``, ``replies.PINS`` / ``verify()``); this table pins those
# tables too, with the card retry texts, the bound source the card screen copies (``COPIED_SOURCE_SHA256``) and the
# D16 member and D17 base card sentences of both writers, so no pinned text of ``typed`` changes without this table.
TEXT_PINS = {
    'cards.LIMITS_RECORD': 'c0a20e320ca755148371fc3045e8f00c4525c8644bf952dee08e30c968c53b87',
    'cards.REASON_JOIN': '6bb1887ca389ae20a4085444a78b43b80d8aeb2bbb0cfa58bbd24be4594c689f',
    'cards.REASON_NO_TEXT': 'caec84d5a55b8db16ecdff0edeaf5f534fe68f9f571cd86ed1a1dfe3e0fcc8d8',
    'cards.REASON_TOO_LONG': '925519843bc0100344c9533c754e235d42dfc062706fb97241b3f96b5817db76',
    'cards.REASON_TOO_MANY_BULLETS': '2bd6be5f73452ebf6588905a9158343eb0d71c0f4be2c8ac9270648ac1c4a8e5',
    'cards.RETRY_FRAME': '9579bac5bda833ae6bb0a3bd0427256a78d1867e2963024d9a6e08d1e85a2a4c',
    'cards.RETRY_SHORT': '2f6a91ca68525530391f1fc35632fa20432ba77d0afc8d0d23bc68fd7d24169a',
    'cards.copied_source': '796aa276975b2f449d97e329c37a20848536352fb95492157b3dae458f56ea2c',  # = COPIED_SOURCE_SHA256
    'engineer_prompt.BASE_CARD_MEANING': '70ec3771041bc5e269c7d52b525b77195d75cfe996f6bbc19e2f30def3a21d2c',
    'engineer_prompt.MEMBERS_MEANING': '13a5a9326ac9c7856c0812c0087feb47564be3865d4a34dacbd1d22c4977ac9a',
    'engineer_prompt.MEMBER_BASE_MEANING': '819540410008d05c7df3ea7f497746858183d8dae3f5b39143dd62bbc97f3c2a',
    'engineer_prompt.PINS': '4a06b375a85af14f120c16af71bdcd8bbb5bde7de0959adbee7ba906bc17ba13',  # + REPAIR_PINS (T8)
    'engineer_prompt.PROMPT_VERSION': '8e09b1f203af8dee949b2e228ce74cb619e74b04d0e1cac9623618524891bac4',
    'replies.PINS': 'e4b417e7bd8306f62690bfbe5ac022db6ab9dc37a363e79314628824c30f0990',
    'replies.READER': '172c26e08e8d8967a188dc5a02d164e9d3bbaf20697d3d38000dc6075caa74f2',
    'writers.BASE_CARD_MEANING': 'bb1f0f034e0ef263e5b3dbaf328229343d4a670d0d2620fc4229bda8eaee1e1f',
    'writers.MEMBERS_MEANING': 'ed38a8dacee55c254e8ff49adac5132c03e0e2c2e9459e2ba2023c5cf3e8cc9e',
    'writers.MEMBER_BASE_MEANING': 'ad353a944831667a7b185e35b84f99c1a17ca74d929646a69fd9988b89141a23',
    'writers.MEMBER_RULE': '709a5087f38890573821c98110923019123df8c686799f002f51d62865cbe4ae',
}


def _shown(entries):
    """At most ``SHOWN`` entries, then the count of the others: refusal messages name paths, never contents."""
    entries = list(entries)
    more = len(entries) - SHOWN
    return ', '.join(entries[:SHOWN]) + (' and %d more' % more if more > 0 else '')


def _sha256(path):
    try:
        return hashlib.sha256(path.read_bytes()).hexdigest()
    except OSError:
        return None


def _rows(relative, pinned, count):
    path = TREE / relative
    try:
        data = path.read_bytes()
    except OSError as error:
        raise ValueError('Machinery check 1 refused: the list %s cannot be read (%s)'
                         % (path, type(error).__name__)) from None
    digest = hashlib.sha256(data).hexdigest()
    if digest != pinned:
        raise ValueError('Machinery check 1 refused: the list %s has sha256 %s, pinned %s' % (path, digest, pinned))
    rows = {}
    for number, line in enumerate(data.decode('utf-8').splitlines(), 1):
        match = ROW.fullmatch(line)
        if not match:
            raise ValueError('Machinery check 1 refused: row %d of the list %s is not "<sha256>  <path>"'
                             % (number, path))
        rows[match.group(2)] = match.group(1)
    if len(rows) != count:
        raise ValueError('Machinery check 1 refused: the list %s has %d distinct paths, pinned %d'
                         % (path, len(rows), count))
    return rows


def listed():
    """Check 1. ``{path: sha256}`` of the frozen files outside ``typed`` (both lists, 564 + 64 rows, sorted by path),
    read from this tree; refused unless each list file has its pinned sha256 and row count."""
    rows = _rows(LIST, LIST_SHA256, LIST_FILES)
    rows.update(_rows(DATA_LIST, DATA_LIST_SHA256, DATA_LIST_FILES))
    return dict(sorted(rows.items()))


def compare(root):
    """``[(path, problem), ...]`` sorted by path, empty when ``<root>/skillopt`` outside ``typed`` equals the lists.

    Every file under ``<root>/skillopt`` except ``skillopt/execskill/typed`` and ``__pycache__`` directories is
    compared with ``listed()``. Problems: ``missing`` (listed, absent), ``differs`` (listed, other bytes or not a
    regular file), ``unlisted`` (present, not listed: an extra module or data file), ``symlink`` (a symbolic link to a
    file or directory; never followed)."""
    root = Path(root).resolve()
    expected = listed()
    problems, seen = [], set()
    for directory, dirs, files in os.walk(root / PACKAGE):
        here = Path(directory)
        keep = []
        for name in dirs:
            relative = (here / name).relative_to(root).as_posix()
            if name == CACHE or relative == TYPED:
                continue
            if (here / name).is_symlink():
                problems.append((relative, 'symlink'))
            else:
                keep.append(name)
        dirs[:] = keep
        for name in files:
            path = here / name
            relative = path.relative_to(root).as_posix()
            seen.add(relative)
            if path.is_symlink():
                problems.append((relative, 'symlink'))
            elif relative not in expected:
                problems.append((relative, 'unlisted'))
            elif not path.is_file() or _sha256(path) != expected[relative]:
                problems.append((relative, 'differs'))
    problems.extend((relative, 'missing') for relative in expected if relative not in seen)
    return sorted(problems)


def loaded():
    """Where the code of this process comes from: ``snapshot`` = the root ``skillopt`` was imported from,
    ``typed_from`` = the tree of this module, ``bound`` = the two differ (``run_typed.py --machinery-snapshot``)."""
    import skillopt
    snapshot = Path(skillopt.__file__).resolve().parents[1]
    own = Path(__file__).resolve().parents[3]
    return {'snapshot': str(snapshot), 'bound': snapshot != own, 'typed_from': str(own)}


def _inside(place, base):
    path = Path(place).resolve()
    return path == base or base in path.parents


def misplaced(binding):
    """Check 4. The names of the loaded ``skillopt`` modules whose file is not where ``binding`` (``loaded()``) says:
    ``<snapshot>/skillopt`` for the machinery, ``<typed_from>/skillopt/execskill/typed`` for ``typed``. A module
    without a file (a namespace package) is judged by every entry of its ``__path__``; one with neither is
    misplaced."""
    machinery_root = (Path(binding['snapshot']) / PACKAGE).resolve()
    typed_root = (Path(binding['typed_from']) / TYPED).resolve()
    wrong = []
    for name, module in sorted(list(sys.modules.items()), key=lambda pair: pair[0]):
        if module is None or not (name == PACKAGE or name.startswith(PACKAGE + '.')):
            continue
        typed = name == TYPED_MODULE or name.startswith(TYPED_MODULE + '.')
        base = typed_root if typed else machinery_root
        file = getattr(module, '__file__', None)
        places = [file] if file else list(getattr(module, '__path__', None) or ())
        if not places or not all(_inside(place, base) for place in places):
            wrong.append(name)
    return wrong


def compare_scripts(root):
    """``[(path, problem), ...]`` sorted by path, empty when ``<root>`` holds every ``SCRIPTS`` file with its pinned
    sha256 (``missing``, ``differs``, ``symlink``: a linked file or a linked ``scripts`` directory, never followed).
    Other files under ``<root>/scripts`` are not compared: the bound run can import none of them (``import_closure``),
    and ``scripts/run_typed.py`` is typed code, sealed by ``provenance.typed_code``."""
    root = Path(root).resolve()
    if (root / SCRIPTS_PACKAGE).is_symlink():
        return [(SCRIPTS_PACKAGE, 'symlink')]
    problems = []
    for relative, digest in sorted(SCRIPTS.items()):
        path = root / relative
        if path.is_symlink():
            problems.append((relative, 'symlink'))
        elif not path.exists():
            problems.append((relative, 'missing'))
        elif not path.is_file() or _sha256(path) != digest:
            problems.append((relative, 'differs'))
    return problems


def misplaced_scripts(binding):
    """Check 4 for ``scripts``, in a bound process only (unbound, this tree serves everything): the names of the
    loaded ``scripts`` modules that are not a ``SCRIPTS`` file under ``<snapshot>/scripts`` (with check 2: the pinned
    bytes), or, for ``TYPED_SCRIPTS``, not under ``<typed_from>/scripts``."""
    if not binding.get('bound'):
        return []
    snapshot, typed_from = Path(binding['snapshot']).resolve(), Path(binding['typed_from']).resolve()
    wrong = []
    for name, module in sorted(list(sys.modules.items()), key=lambda pair: pair[0]):
        if module is None or not (name == SCRIPTS_PACKAGE or name.startswith(SCRIPTS_PACKAGE + '.')):
            continue
        base = typed_from if name in TYPED_SCRIPTS else snapshot
        file = getattr(module, '__file__', None)
        path = Path(file).resolve() if file else None
        if path is None or not _inside(path, base / SCRIPTS_PACKAGE):
            wrong.append(name)
        elif name not in TYPED_SCRIPTS and path.relative_to(base).as_posix() not in SCRIPTS:
            wrong.append(name)
    return wrong


def require_symbols():
    """Check 5. Import every module of ``REQUIRED`` and require each of its names; returns the number of names.
    Refused with the missing names; a module that cannot be imported counts as missing."""
    missing, count = [], 0
    for module_name in sorted(REQUIRED):
        names = REQUIRED[module_name]
        count += len(names)
        try:
            module = importlib.import_module(module_name)
        except Exception as error:  # any import failure of a frozen module is a refusal, reported by type and module
            missing.append('%s (import failed: %s)' % (module_name, type(error).__name__))
            continue
        missing.extend(module_name + '.' + name for name in names if not hasattr(module, name))
    if missing:
        raise ValueError('Machinery check 5 refused: %d frozen names missing: %s' % (len(missing), _shown(missing)))
    return count


# ---- the static scan of ``typed`` (Step 7) -------------------------------------------------------------------------
# Read by the tests and the bound driver (``tests/typed2_bound_driver.py``), never by ``check``: which frozen names
# ``typed`` uses is a property of the code, sealed with it (``provenance.typed_code``). The scan follows the two
# top-level packages a bound run takes from the snapshot: ``skillopt`` (outside ``typed``) and ``scripts``.
SCAN_PACKAGES = ('skillopt', 'scripts')
_NESTED = (ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda, ast.ClassDef, ast.ListComp, ast.SetComp, ast.DictComp,
           ast.GeneratorExp)


def _frozen_module(name):
    """True for a module of the frozen machinery (``skillopt`` outside ``typed``) or of the ``scripts`` package."""
    return (name.split('.')[0] in SCAN_PACKAGES
            and not (name == TYPED_MODULE or name.startswith(TYPED_MODULE + '.')))


def module_file(name, root=None):
    """The source file of module ``name`` under ``root`` (default this tree; a package's ``__init__.py``), else None."""
    base = Path(TREE if root is None else root, *name.split('.'))
    for path in (base.parent / (base.name + '.py'), base / '__init__.py'):
        if path.is_file():
            return path
    return None


def _absolute(node, package):
    """The absolute module of an ``ImportFrom`` inside ``package``."""
    if not node.level:
        return node.module
    parts = package.split('.')
    parts = parts[:len(parts) - node.level + 1]
    return '.'.join(parts + ([node.module] if node.module else []))


def _shallow(nodes):
    """Every node of ``nodes`` without the inside of a nested scope (the nested node itself is yielded)."""
    stack = list(nodes)[::-1]
    while stack:
        node = stack.pop()
        yield node
        if not isinstance(node, _NESTED):
            stack.extend(reversed(list(ast.iter_child_nodes(node))))


class _Scan:
    """One pass over one module of ``typed``: the frozen modules it imports, the names it imports from them or reads
    on them (``uses``), and the names it would assign or delete on them (``writes``). A module alias is followed
    through Python's scopes: a name bound in a function by anything but an import is local there, so a local
    variable that happens to share an alias's name (``client``) is never taken for the module."""

    def __init__(self, root, package):
        self.root, self.package = root, package
        self.modules, self.uses, self.writes = set(), set(), set()

    def binding_of_import(self, node):
        """[(bound name, binding)] of one import statement: ('module', M) or ('name', M, n) for a frozen module,
        None (local) otherwise; records the imported frozen modules and names."""
        found = []
        if isinstance(node, ast.Import):
            for alias in node.names:
                if _frozen_module(alias.name):
                    self.modules.add(alias.name)
                target = alias.name if alias.asname else alias.name.split('.')[0]
                found.append((alias.asname or alias.name.split('.')[0],
                              ('module', target) if _frozen_module(target) else None))
            return found
        module = _absolute(node, self.package)
        for alias in node.names:
            bound = alias.asname or alias.name
            if not module or not _frozen_module(module) or alias.name == '*':
                found.append((bound, None))
            elif module_file(module + '.' + alias.name, self.root):
                self.modules.add(module + '.' + alias.name)
                found.append((bound, ('module', module + '.' + alias.name)))
            else:
                self.modules.add(module)
                self.uses.add((module, alias.name))
                found.append((bound, ('name', module, alias.name)))
        return found

    def bindings(self, nodes, params=()):
        """{name: binding} of one scope. A name bound by an import keeps that binding only when nothing else binds
        it in the same scope; a ``global`` name is left to the module scope."""
        imported, local, declared = {}, set(params), set()
        for node in _shallow(nodes):
            if isinstance(node, (ast.Import, ast.ImportFrom)):
                for name, binding in self.binding_of_import(node):
                    imported.setdefault(name, []).append(binding)
            elif isinstance(node, ast.Name) and not isinstance(node.ctx, ast.Load):
                local.add(node.id)
            elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                local.add(node.name)
            elif isinstance(node, ast.ExceptHandler) and node.name:
                local.add(node.name)
            elif isinstance(node, (ast.Global, ast.Nonlocal)):
                declared.update(node.names)
            elif isinstance(node, (ast.MatchAs, ast.MatchStar)) and node.name:
                local.add(node.name)
            elif isinstance(node, ast.MatchMapping) and node.rest:
                local.add(node.rest)
        scope = {name: None for name in local}
        for name, found in imported.items():
            unique = {repr(binding) for binding in found}
            scope[name] = found[0] if name not in local and len(unique) == 1 else None
        for name in declared:
            scope.pop(name, None)
        return scope

    @staticmethod
    def lookup(name, scopes):
        innermost = len(scopes) - 1
        for index in range(innermost, -1, -1):
            kind, names = scopes[index]
            if kind == 'class' and index != innermost:
                continue   # a class body's names are not visible inside its methods
            if name in names:
                return names[name]
        return None

    def attribute(self, node, scopes):
        chain, base = [], node
        while isinstance(base, ast.Attribute):
            chain.append(base.attr)
            base = base.value
        if not isinstance(base, ast.Name):
            self.walk(base, scopes)
            return
        binding = self.lookup(base.id, scopes)
        if not binding or binding[0] != 'module':
            return
        module, names = binding[1], chain[::-1]
        for index, name in enumerate(names):
            if name.startswith('__') and name.endswith('__'):
                return     # a module's own dunder (``skillopt.__file__``): every module has it, no machinery name
            if module_file(module + '.' + name, self.root):
                module = module + '.' + name
                continue
            stored = index == len(names) - 1 and not isinstance(node.ctx, ast.Load)
            (self.writes if stored else self.uses).add((module, name))
            return

    def walk(self, node, scopes):
        if isinstance(node, ast.Attribute):
            self.attribute(node, scopes)
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda)):
            arguments = node.args
            for sub in list(getattr(node, 'decorator_list', ())) + arguments.defaults + [
                    default for default in arguments.kw_defaults if default is not None]:
                self.walk(sub, scopes)
            params = [a.arg for a in arguments.posonlyargs + arguments.args + arguments.kwonlyargs]
            params += [a.arg for a in (arguments.vararg, arguments.kwarg) if a is not None]
            body = node.body if isinstance(node.body, list) else [node.body]
            inner = scopes + [('function', self.bindings(body, params))]
            for sub in body:
                self.walk(sub, inner)
        elif isinstance(node, ast.ClassDef):
            for sub in node.decorator_list + node.bases + [keyword.value for keyword in node.keywords]:
                self.walk(sub, scopes)
            inner = scopes + [('class', self.bindings(node.body))]
            for sub in node.body:
                self.walk(sub, inner)
        elif isinstance(node, (ast.ListComp, ast.SetComp, ast.DictComp, ast.GeneratorExp)):
            targets = {sub.id for generator in node.generators for sub in ast.walk(generator.target)
                       if isinstance(sub, ast.Name)}
            inner = scopes + [('function', {name: None for name in targets})]
            for sub in ast.iter_child_nodes(node):
                self.walk(sub, inner)
        elif isinstance(node, ast.AnnAssign):  # annotations are never evaluated (``from __future__ import annotations``)
            for sub in (node.target, node.value):
                if sub is not None:
                    self.walk(sub, scopes)
        elif not isinstance(node, ast.arg):    # parameter annotations: never evaluated either
            for sub in ast.iter_child_nodes(node):
                self.walk(sub, scopes)

    def scan(self, tree):
        scopes = [('module', self.bindings(tree.body))]
        for node in tree.body:
            self.walk(node, scopes)
        return self


def frozen_uses(tree=None):
    """The static scan of every module of ``typed`` in ``tree`` (default this tree): ``{'uses': {module: [names]},
    'writes': {module: [names]}, 'modules': [frozen modules imported]}``. ``uses`` holds every name ``typed`` imports
    from a frozen module or reads on one (function-level imports included, annotations excluded: they are never
    evaluated); ``writes`` every name it would assign or delete on one (none is allowed). Files are parsed, never
    run."""
    root = Path(TREE if tree is None else tree)
    modules, uses, writes = set(), set(), set()
    for path in sorted((root / TYPED).glob('*.py')):
        scan = _Scan(root, TYPED_MODULE).scan(ast.parse(path.read_bytes(), filename=str(path)))
        modules |= scan.modules
        uses |= scan.uses
        writes |= scan.writes

    def grouped(pairs):
        return {module: sorted({name for owner, name in pairs if owner == module})
                for module in sorted({owner for owner, _ in pairs})}
    return {'uses': grouped(uses), 'writes': grouped(writes), 'modules': sorted(modules)}


def _imports_of(path, name, root):
    """Every module (absolute) one source file imports anywhere, function level included, with its packages."""
    package = name if path.name == '__init__.py' else name.rpartition('.')[0]
    found = set()
    for node in ast.walk(ast.parse(path.read_bytes(), filename=str(path))):
        if isinstance(node, ast.Import):
            found.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            module = _absolute(node, package)
            if not module:
                continue
            found.add(module)
            found.update(module + '.' + alias.name for alias in node.names
                         if module_file(module + '.' + alias.name, root))
    return {'.'.join(parts[:end]) for parts in (module.split('.') for module in found)
            for end in range(1, len(parts) + 1)}


def import_closure(roots, tree=None):
    """The frozen modules (with a source file in ``tree``) reachable from ``roots`` through static imports, function
    level included: an over-approximation of what a bound run can import from the snapshot."""
    root = Path(TREE if tree is None else tree)
    seen = set()
    todo = sorted({'.'.join(parts[:end]) for parts in (name.split('.') for name in roots)   # with their packages
                   for end in range(1, len(parts) + 1)})
    while todo:
        name = todo.pop()
        if name in seen or not _frozen_module(name) or module_file(name, root) is None:
            continue
        seen.add(name)
        todo.extend(sorted(_imports_of(module_file(name, root), name, root) - seen))
    return sorted(seen)


# ---- check 6: the pinned texts -------------------------------------------------------------------------------------
def _canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True)


def _text_sha256(text):
    return hashlib.sha256(text.encode('utf-8')).hexdigest()


def pinned_texts():
    """``{name: text}`` of every text ``TEXT_PINS`` pins, read from the modules of this process (a mapping as canonical
    JSON). ``cards.copied_source`` is the source the card screen copies as the BOUND ``v225_cards.card_violation``
    holds it, so its pin (``cards.COPIED_SOURCE_SHA256``) also holds the snapshot's frozen function."""
    from . import cards, engineer_prompt, replies, writers
    return {
        'cards.LIMITS_RECORD': _canonical(cards.LIMITS_RECORD),
        'cards.REASON_JOIN': cards.REASON_JOIN,
        'cards.REASON_NO_TEXT': cards.REASON_NO_TEXT,
        'cards.REASON_TOO_LONG': cards.REASON_TOO_LONG,
        'cards.REASON_TOO_MANY_BULLETS': cards.REASON_TOO_MANY_BULLETS,
        'cards.RETRY_FRAME': cards.RETRY_FRAME,
        'cards.RETRY_SHORT': _canonical(cards.RETRY_SHORT),
        'cards.copied_source': cards.copied_source(),
        'engineer_prompt.BASE_CARD_MEANING': engineer_prompt.BASE_CARD_MEANING,
        'engineer_prompt.MEMBERS_MEANING': engineer_prompt.MEMBERS_MEANING,
        'engineer_prompt.MEMBER_BASE_MEANING': engineer_prompt.MEMBER_BASE_MEANING,
        # typed-v3 (T8): the five repair texts' pins with the ten (one table pin; the count of check 6 is unchanged)
        'engineer_prompt.PINS': _canonical({'%s.%s' % key: pin for key, pin in
                                            {**engineer_prompt.PINS, **engineer_prompt.REPAIR_PINS}.items()}),
        'engineer_prompt.PROMPT_VERSION': engineer_prompt.PROMPT_VERSION,
        'replies.PINS': _canonical(replies.PINS),
        'replies.READER': replies.READER,
        'writers.BASE_CARD_MEANING': writers.BASE_CARD_MEANING,
        'writers.MEMBERS_MEANING': writers.MEMBERS_MEANING,
        'writers.MEMBER_BASE_MEANING': writers.MEMBER_BASE_MEANING,
        'writers.MEMBER_RULE': writers.MEMBER_RULE,
    }


def check_pins():
    """Check 6 (DESIGN 3.5, 4.3), the one rule for all pinned texts of ``T/``; refused, naming keys only, unless
    (a) ``engineer_prompt.verify()`` holds: the ten system texts, rendered again from the bound screen modules, equal
    ``PINS``, and every legal / illegal example of its rule table passes / fails the bound ``policy.check``;
    (b) ``replies.verify()`` is empty: the two reply formats, the format-retry text and ``PROBLEM_SENTENCES``;
    (c) the card screen's copy still matches the bound function (``cards.COPIED_SOURCE_SHA256``) and the two retry
    texts it shares with typed-v1 equal the bound ``v225_cards.CARD_RETRY`` / ``RETRY_REASONS``;
    (d) every text of ``pinned_texts()`` has its ``TEXT_PINS`` sha256 (the two tables have the same names).
    Returns the number of pins verified."""
    from skillopt.execskill import v225_cards
    from . import cards, engineer_prompt, replies
    try:
        engineer_prompt.verify()
    except RuntimeError as error:
        raise ValueError('Machinery check 6 refused: %s' % error) from None
    changed = replies.verify()
    if changed:
        raise ValueError('Machinery check 6 refused: the pinned reply texts %s differ from replies.PINS'
                         % ', '.join(changed))
    texts = pinned_texts()
    if _text_sha256(texts['cards.copied_source']) != cards.COPIED_SOURCE_SHA256:
        raise ValueError('Machinery check 6 refused: the bound v225_cards.card_violation no longer holds the lines '
                         'the card screen copies (cards.COPIED_SOURCE_SHA256)')
    if cards.RETRY_FRAME != v225_cards.CARD_RETRY or cards.RETRY_SHORT != v225_cards.RETRY_REASONS:
        raise ValueError('Machinery check 6 refused: the card retry texts shared with typed-v1 (RETRY_FRAME, '
                         'RETRY_SHORT) differ from the bound v225_cards texts')
    changed = sorted(name for name in set(texts) | set(TEXT_PINS)
                     if name not in texts or _text_sha256(texts[name]) != TEXT_PINS.get(name))
    if changed:
        raise ValueError('Machinery check 6 refused: %d pinned texts differ from TEXT_PINS: %s'
                         % (len(changed), _shown(changed)))
    return len(engineer_prompt.PINS) + len(replies.PINS) + len(TEXT_PINS)


def _refuse(number, where, problems):
    if problems:
        raise ValueError('Machinery check %d refused: %s differs from the machinery lists in %d paths: %s'
                         % (number, where, len(problems), _shown('%s (%s)' % pair for pair in problems)))


def check(*, real, snapshot=None):
    """The machinery record of this process after checks 1 to 6 (module docstring); ValueError on the first failure.

    ``real=True`` (every real start: run, resume, smoke on dl) runs all six and requires a bound process whose
    snapshot is ``snapshot`` (default ``MACHINERY_SNAPSHOT``; another path only for the bound-interpreter test of
    Step 7, which binds a stand-in copy). ``real=False`` (``prepare``, local tests, unbound starts) runs 1, 3, 5 and 6
    and ignores ``snapshot``. Check 4 runs last, so it also judges every module that checks 5 and 6 imported. The
    record does not depend on ``real``: the one sealed at ``prepare`` is compared with the one of every real start
    (``chain.start_checks``)."""
    listed()                                                                                    # 1
    binding = loaded()
    if real:
        expected = Path(MACHINERY_SNAPSHOT if snapshot is None else snapshot).resolve()
        if not binding['bound']:
            raise ValueError('Machinery check 2 refused: a real start imports skillopt from the snapshot %s, but this '
                             'process imports it from this tree %s' % (expected, binding['typed_from']))
        if Path(binding['snapshot']) != expected:
            raise ValueError('Machinery check 2 refused: skillopt is imported from %s, expected the snapshot %s'
                             % (binding['snapshot'], expected))
        _refuse(2, 'the snapshot ' + binding['snapshot'],                                       # 2
                sorted(compare(binding['snapshot']) + compare_scripts(binding['snapshot'])))
        if os.path.lexists(os.path.join(binding['snapshot'], TYPED)):
            raise ValueError('Machinery check 2 refused: the snapshot %s holds %s, which would shadow this tree\'s '
                             'typed package' % (binding['snapshot'], TYPED))
    _refuse(3, 'this tree ' + str(TREE), sorted(compare(TREE) + compare_scripts(TREE)))         # 3
    symbols = require_symbols()                                                                 # 5
    check_pins()                                                                                # 6
    if real:
        wrong = misplaced(binding)                                                              # 4
        if wrong:
            raise ValueError('Machinery check 4 refused: %d skillopt modules are loaded from outside %s (machinery) '
                             'or %s (typed): %s' % (len(wrong), os.path.join(binding['snapshot'], PACKAGE),
                                                    os.path.join(binding['typed_from'], TYPED), _shown(wrong)))
        wrong = misplaced_scripts(binding)
        if wrong:
            raise ValueError('Machinery check 4 refused: %d scripts modules are not the pinned files under %s: %s'
                             % (len(wrong), os.path.join(binding['snapshot'], SCRIPTS_PACKAGE), _shown(wrong)))
    return {'snapshot': binding['snapshot'], 'bound': binding['bound'], 'typed_from': binding['typed_from'],
            'list': LIST, 'list_sha256': LIST_SHA256, 'files': LIST_FILES, 'data_list_sha256': DATA_LIST_SHA256,
            'symbols': symbols}
