"""typed-v2 step 5b (addendum D17, with RP12 / Q23): the learning starts from the historical card C.

The sealed manifest field ``base_card`` ('format', the code default, or 'historical') is the base every learned mount
composes on: ``mount.system_card(bench, T, base_card=)`` is ``T + CARD_JOIN + base`` for a learned text T and the
base alone without one (also for an unknown item and a typed item whose type has no card). The learning side has its
own base arm B (the base alone); the read arms C0 (format lines) and C (historical card) never depend on the base.
Under 'historical' both writers are shown the base card. Under 'format', with one bench per type, every request is
one that commit cdf85b6 sent, apart from two documented changes (``CDF85B6_FORMAT_IDENTITY``, below).

Golden values (``GOLDEN_RUNS``): the fake chain through the REAL mount, writers and reads, scripted replies and an
exact axis embedder (every routing number exact, so the digests do not depend on the interpreter's float sums), in
two scenarios: the smoke limits, and the default limits with every searchqa card failing (round 2 revises). Per run
the digest of every request (purpose, unit, sha256 of system NUL user; sorted) and of every cell (unit, label, item,
its request hashes, its selection request hashes; sorted). History of the pins: step 5b computed them with the
untouched tree at cdf85b6 (``GOLDEN_RUNS_CDF85B6``); steps 5w and 5x changed the requests on purpose and pinned their
own trees' output (``GOLDEN_RUNS_5W``, ``GOLDEN_RUNS``), so ``GOLDEN_RUNS`` ties the requests to the 5x tree only. In
both scenarios OfficeQA joins SearchQA's type, so D16 changes requests against cdf85b6 by design.

The tie to the OLD code (fix-b, review finding rb-requests F1): ``CDF85B6_FORMAT_IDENTITY`` holds the distinct
request contents of the scenarios with one bench per type (``tests/typed2_format_driver.py``), as the cdf85b6 typed
package sends them; this tree must send the same set, and the live test re-derives the pins from that commit wherever
the checkout holds it. The pins of this file are never re-pinned from the output of the tree under test. Since fix-b,
coord-1, the [import] row of the ten program-writer system texts is reworded (typed-engineer-prompt-2); every
golden of this file and of ``tests/test_typed2_shared.py`` compares the requests with that one wording mapped back
(``undo_coord1``), and checks that the mapping touched only the program-writer requests.
"""
import hashlib
import io
import json
import os
import re
import shutil
import subprocess
import sys
import tarfile
import tempfile
from pathlib import Path

import pytest

from scripts import run_typed
from skillopt.execskill import typed, zebralogic
from skillopt.execskill.package import Procedure
from skillopt.execskill.v225_cards import CARD_JOIN
from skillopt.execskill.typed import (BASE_CARD_DEFAULT, BASE_CARDS, ORDER, cards, chain, engineer_prompt, gates,
                                      library as lib, mount, prepare, smoke, tasktypes as typing_, units, writers)
from tests import typed2_format_driver as format_driver  # the scenario code both trees run (fix-b, F1)
from tests.fixtures.execskill.items import searchqa_items
from tests.test_typed_reads import sealed_code, write_machinery, write_pools, write_tree, zebra_rows

NEUTRAL = Path('/tmp/typed2-neutral').resolve()  # pytest's tmp_path carries "test", which the sealed-path guard refuses
FAMILY_AXES = 16
RELABEL = {'Ba': 'C0a', 'Bb': 'C0b', 'B': 'C0'}  # 5b's label map against cdf85b6 (history; no 5w label is in it)
# Step 5b's pins: the requests and cells of cdf85b6 (before the gate wiring), reproduced by 5b under 'format'. Kept as
# history: step 5w changes them on purpose (DESIGN 4.2 (8): each gate cell's request is sent R = 3 times, the no-harm
# baseline is the noise unit, a shared arm runs no cell), so the test pins GOLDEN_RUNS below instead.
GOLDEN_RUNS_CDF85B6 = {
    'smoke': {'requests': 'ba7144ae5c3457371fb14c7f85a576001839a7261229d477c4d175a01f8b1849', 'n_requests': 235,
              'cells': '96fdb9abad13d7f7284b57766dbdf636e45380a4b80232d8ea68e04c0417fcc5', 'n_cells': 191},
    'default': {'requests': '25beaaf94cf9432dc1f83b6156a29e23712876f0513f37c49c74428c52cfcf37', 'n_requests': 264,
                'cells': '95012d67c3474cd946494dd2deb88f84c7d9e3a1829e3917e889c550af838a71', 'n_cells': 196},
}
# Step 5w's pins (computed with the 5w tree under 'format', Python 3.13 and 3.10 equal): every request and cell of the
# same two scenarios after the gate wiring. Kept as history: in both scenarios OfficeQA joins SearchQA's type at step
# 2, so step 5x (addendum D16) changes them on purpose (member units s2/member-searchqa-*, member arms of the
# candidates that passed the home rule, the member block in the step-2 writer requests); the test pins GOLDEN_RUNS.
# A type of one bench changes nothing: tests/test_typed2_shared.py pins two such scenarios to the 5w tree.
GOLDEN_RUNS_5W = {
    'smoke': {'requests': 'ab1b85846264f0d41e972e94b5fe9dbdcc0ffcc3f36c386c2c400d986b0fef58', 'n_requests': 277,
              'cells': '9c2729b6b7c0303d67bbe130710ac4e539c433199f000a78a437a057226a7aa5', 'n_cells': 233},
    'default': {'requests': '647e43deae296dc0514c3d0286218782c5e709126228df69b374248043a3de35', 'n_requests': 324,
                'cells': '55bbc4ee208a54c44fee3d63632854f2e15c7a3878f612b5fe23b5ba9d0e9dcd', 'n_cells': 244},
}
# Step 5x's pins (the 5x tree under 'format', Python 3.13 and 3.10 equal): 20 more cells in each scenario (smoke:
# member outcomes 2, member base 9, program-1 member arm 9; default: member outcomes 2, member base 9, card-r1 member
# arm 9, card-r2's member arm shared with round 1's). The requests are compared with the coord-1 wording mapped back.
GOLDEN_RUNS = {
    'smoke': {'requests': '358c625ad77737d8b33db4b8703e589b61e093a575522396591a4a327f06868c', 'n_requests': 297,
              'cells': '78d6740464810830cbfef4c942b942c14d2f9572a0afe2daaf0503454f320c63', 'n_cells': 253},
    'default': {'requests': '66a3fe2208c58925578792681067c7ab5abc1a251a3a6fdc1e752a1df62fb6ab', 'n_requests': 364,
                'cells': '9b87a88169fc07b20ebe28699f7833ad09d421114def9158c3a585f9f7bf912b', 'n_cells': 264},
}
LABEL_SHA256 = {  # the two base card labels, pinned (a change is a visible change of the writer requests)
    'writers': 'bb1f0f034e0ef263e5b3dbaf328229343d4a670d0d2620fc4229bda8eaee1e1f',
    'engineer': '70ec3771041bc5e269c7d52b525b77195d75cfe996f6bbc19e2f30def3a21d2c',
}
# fix-b (rb-requests F1): the requests under 'format' tied to the code of commit cdf85b6 (batch 1, before the wiring of
# 5b, 5w and 5x). Measure (``format_identity``): the DISTINCT request contents of a run, sorted [purpose,
# sha256(system NUL user)] (R repeats, unit names and the order of sends do not change it), on the two scenarios of
# ``tests/typed2_format_driver.py`` (one bench per type), after two normalizations, each a documented change made on
# purpose since cdf85b6: (1) ``undo_coord1``: the [import] row of typed-engineer-prompt-2 (fix-b, coord-1) mapped back
# to its DESIGN 3.2 wording, in the ten program-writer system texts and in the screen evidence of a fix request; (2)
# ``card_points``: the gain numbers of a round-2 card request's ``result`` at 9 decimals (DESIGN 4.2 (2): item means;
# -66.66666666666667 where cdf85b6 wrote -66.66666666666666). Raw, the two sets differ only in those requests. The
# values are what the cdf85b6 typed package sends, extracted by ``git archive`` and run by the driver (2026-11-12,
# Python 3.13; the smoke value equals the review's own cdf85b6 measurement); ``test_..._live`` re-derives them
# wherever the checkout holds the commit. Never re-pin them from the output of this tree.
CDF85B6 = 'cdf85b6a10470bd4939df601dd643e8ba821c306'
CDF85B6_PATHS = ('skillopt', 'scripts', 'docs/handoff/v29-20261026', 'tests/fixtures/execskill/v222_cards')
CDF85B6_FORMAT_IDENTITY = {
    'smoke-single': {'n': 97, 'digest': '323f1e33f2e11b04d8b57185b5ac3ae72e5580fde35a138d562472bd837f9569'},
    'default-single': {'n': 104, 'digest': '0c076c11d5b77ddc974c9d2df552e796d2b8e1bde2226c7d4a9687a178a7fa25'},
}
# the coord-1 change of the [import] row: (text of typed-engineer-prompt-2, text of DESIGN 3.2 / -1), literal here
COORD1_PAIRS = (
    ('In "from M import name" the name must not be one that the [name] or [attribute] rules below ban, nor a blocked '
     'module name (random and time included): "from datetime import time", "from pandas import read_csv" and "from '
     'numpy import random" are rejected. ', ''),
    ('leave type hints out or use the built-in names (list, dict); for a banned member import the module and write the '
     'member after a dot where the [attribute] rule allows it (import datetime, then datetime.time).',
     'leave type hints out or use the built-in names (list, dict).'),
)
CARD_POINTS = re.compile(r'("(?:required_)?mean_gain_points": )(-?\d+(?:\.\d+)?(?:[eE][-+]?\d+)?)')


@pytest.fixture
def tmp_path():
    NEUTRAL.mkdir(parents=True, exist_ok=True)
    made = Path(tempfile.mkdtemp(prefix='base-', dir=NEUTRAL))
    try:
        yield made
    finally:
        shutil.rmtree(made, ignore_errors=True)


@pytest.fixture
def inputs(tmp_path, monkeypatch):
    monkeypatch.setattr(zebralogic, 'load_pool', lambda *a, **k: zebra_rows())
    machinery = tmp_path / 'machinery.json'
    return {'pools': write_pools(tmp_path), 'machinery': machinery, 'value': write_machinery(machinery),
            'tree': write_tree(tmp_path), 'parent': tmp_path}


def sha256(text):
    return hashlib.sha256(text.encode('utf-8')).hexdigest()


# ---- the fake chain (golden scenario) ------------------------------------------------------------------------
def exact_embedder(texts):
    """One exact unit vector per text family (the smoke's family prefix): every distance is 0 or sqrt 2."""
    rows = []
    for text in texts:
        axis = int(sha256(text[:smoke.FAMILY_CHARS]), 16) % FAMILY_AXES
        rows.append([1.0 if i == axis else 0.0 for i in range(FAMILY_AXES)])
    return rows


class Capture(smoke.Script):
    """The smoke's scripted clients, keeping every request (purpose, unit, system, user)."""

    def __init__(self, scripted=None):
        super().__init__(scripted)
        self.requests = []

    def send(self, purpose, system, user, *, model, unit=None):
        with self.lock:
            self.requests.append((purpose, unit, system, user))
        return super().send(purpose, system, user, model=model, unit=unit)


def searchqa_cards_fail(bench, item_id, mounted):
    if bench == 'searchqa' and (mounted.get('card_text') or '').strip() and mounted.get('arm') != 'C':
        return 'fail'
    return smoke.default_outcome(bench, item_id, mounted)


SCENARIOS = {'smoke': (smoke.SMOKE_LIMITS, None), 'default': (chain.DEFAULT_LIMITS, searchqa_cards_fail)}


def run_scenario(root, name, base_card=None):
    limits, outcomes = SCENARIOS[name]
    manifest = smoke.synthetic_manifest() if base_card is None else smoke.synthetic_manifest(base_card=base_card)
    script = Capture({'outcomes': outcomes} if outcomes else None)
    services = smoke.fake_services(root, 'G', manifest, scripted=script)
    services.embed = exact_embedder
    services.slices = smoke.smoke_slices(services.items, services.slices)
    services.limits = dict(limits)
    state = chain.run(root, 'G', services=services, sleep=lambda s: None)
    return state, script


def digest(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True).encode('utf-8')).hexdigest()


def undo_coord1(text):
    """A request text (a system text, or a user message: raw, or inside JSON as its escaped form) with the coord-1
    wording of the [import] row mapped back to DESIGN 3.2's (``COORD1_PAIRS``)."""
    for new, old in COORD1_PAIRS:
        escaped_new, escaped_old = (json.dumps(value, ensure_ascii=False)[1:-1] for value in (new, old))
        text = text.replace(new, old).replace(escaped_new, escaped_old)
    return text


def coord1_touched(requests):
    """The purposes of the requests ``undo_coord1`` changes, and whether it changed every request whose system text is
    one of the ten program-writer texts of this tree (each holds the [import] row; a format retry has its own text)."""
    texts = {engineer_prompt.system(bench, purpose) for bench in ORDER for purpose in engineer_prompt.PURPOSES}
    touched = [(purpose, system, undo_coord1(system) != system or undo_coord1(user) != user)
               for purpose, _, system, user in requests]
    return ({purpose for purpose, _, changed in touched if changed},
            all(changed for _, system, changed in touched if system in texts))


def coord1_hashes(requests):
    """{hash of a request of this tree: hash of the same request with the coord-1 wording mapped back}, in both forms a
    record names a request by (``sha256(system NUL user)``, ``writers.request_sha256``), for the records (decisions,
    program lineage) that hold the hash of a program-writer request."""
    mapping = {}
    for _, _, system, user in requests:
        old_system, old_user = undo_coord1(system), undo_coord1(user)
        if (old_system, old_user) != (system, user):
            mapping[sha256(system + '\x00' + user)] = sha256(old_system + '\x00' + old_user)
            mapping[writers.request_sha256(system, user)] = writers.request_sha256(old_system, old_user)
    return mapping


def remap(value, mapping):
    """``value`` (JSON data) with every string that is a key of ``mapping`` replaced by its value."""
    if isinstance(value, dict):
        return {key: remap(inner, mapping) for key, inner in value.items()}
    if isinstance(value, list):
        return [remap(inner, mapping) for inner in value]
    return mapping.get(value, value) if isinstance(value, str) else value


def request_rows(script, *, coord1=False):
    """[purpose, unit, sha256(system NUL user)] of every request, sorted; ``coord1``: with the coord-1 wording mapped
    back (``undo_coord1``), the form in which the goldens computed before fix-b hold."""
    undo = undo_coord1 if coord1 else (lambda text: text)
    return sorted([purpose, unit, sha256(undo(system) + '\x00' + undo(user))]
                  for purpose, unit, system, user in script.requests)


def card_points(purpose, user):
    """A card writer request with the gain numbers of its round-2 ``result`` at 9 decimals (DESIGN 4.2 (2))."""
    if purpose != 'card_writer':
        return user
    return CARD_POINTS.sub(lambda found: found.group(1) + '%.9f' % float(found.group(2)), user)


def format_identity(requests):
    """The distinct request contents of a run (module docstring, ``CDF85B6_FORMAT_IDENTITY``): {'n', 'digest'} of the
    sorted unique [purpose, sha256(system NUL user)] after ``undo_coord1`` and ``card_points``."""
    rows = {(purpose, sha256(undo_coord1(system) + '\x00' + card_points(purpose, undo_coord1(user))))
            for purpose, _, system, user in requests}
    return {'n': len(rows), 'digest': digest(sorted([list(row) for row in rows]))}


def cell_files(root):
    base = Path(root) / 'G'
    for path in sorted(base.rglob('cells/*.json')):
        yield str(path.parent.parent.relative_to(base)), json.loads(path.read_text())


def cell_rows(root, *, relabel=True):
    rows = []
    for unit, cell in cell_files(root):
        label = cell['arm']
        if relabel and not unit.startswith('practice-read-'):
            label = RELABEL.get(label, label)
        rows.append([unit, label, cell['item_id'], list(cell.get('request_sha256') or []),
                     list(cell.get('selection_request_sha256') or [])])
    return sorted(rows)


def bench_of(unit):
    """The bench of a learning unit (s<k>/...), a practice read unit (practice-read-<event>-<bench>) or, typed-v2 step
    5x (addendum D16), a member unit of a shared type, which names its member bench after 'member-'
    (s<k>/member-<b>-outcomes, s<k>/member-<b>-base, s<k>/card-r<j>-member-<b>, s<k>/program-<i>-member-<b>)."""
    if unit.startswith('practice-read-'):
        return unit.rsplit('-', 1)[1]
    name = unit.split('/', 1)[1]
    if 'member-' in name:
        rest = name.split('member-', 1)[1]
        return next(bench for bench in ORDER if rest == bench or rest.startswith(bench + '-'))
    return ORDER[int(unit.split('/')[0][1:]) - 1]


@pytest.mark.parametrize('name', sorted(GOLDEN_RUNS))
def test_format_base_sends_every_request_and_cell_of_the_5x_tree(tmp_path, name):
    """The shared-type scenarios under 'format': every request and cell of the 5x tree (``GOLDEN_RUNS``), apart from
    the coord-1 wording of the [import] row (mapped back; it touches the program-writer requests and nothing else).
    The tie to the old code is ``test_format_base_one_bench_requests_are_cdf85b6s`` (fix-b, rb-requests F1)."""
    state, script = run_scenario(tmp_path / ('golden-%s-smoke' % name), name)
    assert state['complete'] and state['paused'] is None and state['base_card'] == 'format'
    requests, cells = request_rows(script, coord1=True), cell_rows(tmp_path / ('golden-%s-smoke' % name))
    assert coord1_touched(script.requests) == ({'program_writer'}, True)
    golden = GOLDEN_RUNS[name]
    assert (len(requests), len(cells)) == (golden['n_requests'], golden['n_cells'])
    assert digest(requests) == golden['requests']  # every solver, selection, writer, engineer and describer request
    assert digest(cells) == golden['cells']        # every cell (unit, label, item, request and selection hashes)
    # step 5w: the learning base B runs as B#1..3 in the noise unit; a gate arm's R cells of one item send identical
    # requests (fresh, DESIGN 4.2 (8)); the read side keeps its single-run C0 / C / F labels; no C0a / C0b / Ba / Bb
    labels, repeats = {}, {}
    for unit, cell in cell_files(tmp_path / ('golden-%s-smoke' % name)):
        labels.setdefault('read' if unit.startswith('practice-read-') else unit.split('/')[1].split('-')[0], set()).add(
            cell['arm'])
        if gates.repeat_of_label(cell['arm']) is not None:
            repeats.setdefault((unit, cell['item_id'], gates.arm_of_label(cell['arm'])), []).append(
                (cell['request_sha256'], cell['repeat'] if 'repeat' in cell else gates.repeat_of_label(cell['arm'])))
        if gates.arm_of_label(cell['arm']) == 'B':
            assert cell['mount']['arm'] == 'B' and cell['mount']['system_card_sha256'] == sha256(
                mount.format_block(bench_of(unit)))
    assert labels['noise'] == {'B#1', 'B#2', 'B#3'} and labels['read'] <= {'C0', 'C', 'F'} and 'C0' in labels['read']
    assert all(len(found) == 3 and len({tuple(h) for h, _ in found}) == 1 for found in repeats.values()) and repeats
    assert not any(label in {'C0a', 'C0b', 'Ba', 'Bb', 'B'} for found in labels.values() for label in found)
    assert not any('base_card' in user for purpose, _, _, user in script.requests if purpose != 'solver')


# ---- the tie of the 'format' requests to commit cdf85b6 (fix-b, rb-requests F1) -------------------------------------
def one_bench_types(root):
    return [json.loads((Path(root) / 'G' / ('s%d' % k) / 'typing' / 'typing.json').read_text())['type']
            for k in range(1, 6)]


@pytest.mark.parametrize('name', format_driver.SCENARIOS)
def test_format_base_one_bench_requests_are_cdf85b6s(tmp_path, name):
    """Addendum D16 (d) and D17 ('format' = the behaviour without D17): with one bench per type, this tree sends
    exactly the distinct request contents (solver, selection, describer, card writer, program writer) that the
    cdf85b6 code sends on the same scenario (``CDF85B6_FORMAT_IDENTITY``), up to the two documented changes the
    measure maps back; raw, it differs in exactly those requests (program writer: coord-1; card writer: one round-2
    result number in the default scenario)."""
    root = tmp_path / (name + '-smoke')
    state, requests = format_driver.run_requests(name, root, chain=chain, smoke=smoke)
    assert state['complete'] and state['paused'] is None and state['base_card'] == 'format'
    assert one_bench_types(root) == ['t01', 't02', 't03', 't04', 't05']   # every type holds one bench
    assert format_identity(requests) == CDF85B6_FORMAT_IDENTITY[name]
    assert coord1_touched(requests) == ({'program_writer'}, True)
    rounded = {purpose for purpose, _, _, user in requests if card_points(purpose, user) != user}
    # the gain numbers normalized: a round-2 card request's only (the smoke limits run one card round)
    assert rounded == ({'card_writer'} if name == 'default-single' else set())


def test_format_identity_sees_one_changed_request(tmp_path, monkeypatch):
    """The measure is not blind: one describer request changed by one character moves it off the cdf85b6 pin (the
    kind of change a re-pinned golden absorbed, review rb-requests F1); the count of distinct requests stays."""
    from skillopt.execskill.typed import library as library_module
    real = library_module.description_request

    def changed(skill, examples):
        request = real(skill, examples)
        return {**request, 'user': request['user'] + ' '}
    monkeypatch.setattr(library_module, 'description_request', changed)
    state, requests = format_driver.run_requests('smoke-single', tmp_path / 'changed-smoke', chain=chain, smoke=smoke)
    assert state['complete'] and any(purpose == 'describer' for purpose, _, _, _ in requests)
    found, pinned = format_identity(requests), CDF85B6_FORMAT_IDENTITY['smoke-single']
    assert found['n'] == pinned['n'] and found['digest'] != pinned['digest']


def cdf85b6_tree(parent):
    """The paths ``CDF85B6_PATHS`` of commit cdf85b6, extracted by ``git archive`` under ``parent`` (the typed package
    and the frozen machinery it imports, and the data files the fake chain reads); skips where the checkout has no git
    or not that commit (the pins still run)."""
    here = Path(__file__).resolve().parents[1]
    try:
        found = subprocess.run(['git', 'rev-parse', '--verify', '--quiet', CDF85B6 + '^{commit}'], cwd=here,
                               capture_output=True, text=True, timeout=60)
        if found.returncode != 0 or found.stdout.strip() != CDF85B6:
            pytest.skip('commit cdf85b6 is not in this checkout')
        archive = subprocess.run(['git', 'archive', '--format=tar', CDF85B6] + list(CDF85B6_PATHS), cwd=here,
                                 capture_output=True, check=True, timeout=120).stdout
    except (OSError, subprocess.SubprocessError):
        pytest.skip('git is not available in this checkout')
    tree = Path(parent) / 'cdf85b6'
    tree.mkdir()
    with tarfile.open(fileobj=io.BytesIO(archive)) as bundle:
        if hasattr(tarfile, 'data_filter'):
            bundle.extractall(tree, filter='data')
        else:  # Python 3.11 before 3.11.4
            bundle.extractall(tree)
    return tree


@pytest.mark.parametrize('name', format_driver.SCENARIOS)
def test_format_base_cdf85b6_pins_are_rederived_from_the_commit_live(tmp_path, name):
    """The pins of ``CDF85B6_FORMAT_IDENTITY`` are the cdf85b6 code's: its typed package (``git archive``) runs the
    same scenario code in a fresh interpreter (``-I``: nothing of this tree on its path) and gives these values."""
    tree = cdf85b6_tree(tmp_path)
    out, root = tmp_path / 'requests.json', tmp_path / (name + '-smoke')
    env = {key: value for key, value in os.environ.items() if key != 'PYTHONPATH'}
    done = subprocess.run([sys.executable, '-I', format_driver.__file__, str(tree), name, str(root), str(out)],
                          cwd=str(tree), env=env, capture_output=True, text=True, timeout=600)
    assert done.returncode == 0, done.stderr[-2000:]
    found = json.loads(out.read_text(encoding='utf-8'))
    assert found['complete'] is True and found['paused'] is None
    assert one_bench_types(root) == ['t01', 't02', 't03', 't04', 't05']
    requests = [tuple(row) for row in found['requests']]
    assert format_identity(requests) == CDF85B6_FORMAT_IDENTITY[name]
    assert coord1_touched(requests)[0] == set()  # the old texts: the mapping of coord-1 changes nothing there


def systems_ok(system, base):
    """A learned-side system text: the base alone, or a learned text + CARD_JOIN + the base."""
    return system == base or (system.endswith(CARD_JOIN + base) and len(system) > len(base) + len(CARD_JOIN))


def test_historical_base_every_learned_mount_and_both_writers_carry_C(tmp_path):
    hist_root, fmt_root = tmp_path / 'hist-smoke', tmp_path / 'fmt-smoke'
    state, script = run_scenario(hist_root, 'default', base_card='historical')
    assert state['complete'] and state['base_card'] == 'historical'
    seen = {'B': 0, 'learned_no_card': 0, 'learned_card': 0, 'read': 0}
    for unit, cell in cell_files(hist_root):
        bench = bench_of(unit)
        system, C = cell['sends'][0]['system'], mount.historical_card(bench)
        assert cell['mount']['system_card_sha256'] == sha256(system)
        if unit.startswith('practice-read-'):
            event = unit[len('practice-read-'):].rsplit('-', 1)[0]
            seen['read'] += 1
            if event == 'C0':
                assert system == mount.format_block(bench)  # the no-skill row: the format lines only, whatever the base
            elif event == 'C':
                assert system == C
            else:  # S<k>: the library composes on C; an unknown or card-less item reads exactly C
                assert systems_ok(system, C) and (cell['mount']['card_skill'] is not None or system == C)
            continue
        if cell['mount']['arm'] == 'B':
            assert system == C and cell['arm'] in ('B#1', 'B#2', 'B#3')  # step 5w: the noise repeats B#1..3
            seen['B'] += 1
            continue
        assert systems_ok(system, C), (unit, cell['arm'])
        candidate = cell['mount'].get('candidate') or {}
        carded = cell['mount']['card_skill'] is not None or (candidate.get('kind') == 'card' and candidate.get('applied'))
        seen['learned_card' if carded else 'learned_no_card'] += 1
        if not carded:
            assert system == C, (unit, cell['arm'])
        elif bench != 'zebralogic':
            assert system != C
    assert all(seen.values()), seen
    # the same run under 'format': the same cells (unit, label, item), only the system texts of the learned side differ;
    # ZebraLogic (C = its format block) and the read arms C0 / C send exactly the same requests
    run_scenario(fmt_root, 'default')
    hist, fmt = cell_rows(hist_root, relabel=False), cell_rows(fmt_root, relabel=False)
    assert [row[:3] for row in hist] == [row[:3] for row in fmt]
    for h, f in zip(hist, fmt):
        unit = h[0]
        same = bench_of(unit) == 'zebralogic' or unit.startswith(('practice-read-C0-', 'practice-read-C-'))
        assert (h[3:] == f[3:]) == same, (unit, h[1])
    # the writers: the card writer and the engineer see C, labelled, on every bench where it adds to the format block
    blocks = {'card_writer': {}, 'program_writer': {}}
    for purpose, unit, system, user in script.requests:
        if purpose not in blocks:
            continue
        request = json.loads(user)
        if purpose == 'program_writer' and request.get('request') != 'propose':
            assert 'base_card' not in request  # fix and format-retry requests are about the reply, not the card
            continue
        blocks[purpose].setdefault(bench_of(unit), []).append(request.get('base_card'))
    labels = {'card_writer': writers.BASE_CARD_MEANING, 'program_writer': engineer_prompt.BASE_CARD_MEANING}
    for purpose, by_bench in blocks.items():
        assert set(by_bench) == set(ORDER), purpose
        for bench, found in by_bench.items():
            expected = None if bench == 'zebralogic' else {'meaning': labels[purpose], 'text': mount.historical_card(bench)}
            assert found and all(block == expected for block in found), (purpose, bench)
    assert len(blocks['card_writer']['searchqa']) == 2  # round 1 and the revision round


# ---- the mount -------------------------------------------------------------------------------------------------
CARD_TEXT, NEW_CARD = '- read every snippet before answering', '- a new card'
QA_TEXTS = ['Which fixture town keeps the bell number %d?' % i for i in range(40)]
ZEBRA_ITEM = {'benchmark': 'zebralogic', 'task_id': 'fx-zebra-1',
              'public': {'question': 'There are 2 houses, numbered 1 to 2 from left to right, as seen from across the '
                                     'street. Each house is occupied by a different person. Eric drinks milk.',
                         'columns': ['Name', 'Drink']}, 'private': {}}
SOURCE = ('"""A fixture program."""\n\n\ndef applies(view):\n    return True\n\n\n'
          'def before_call(view, state):\n    return None\n')


def axis(texts):
    return [[1.0 if i == (3 if 'treasury' in text else 4) else 0.0 for i in range(8)] for text in texts]


def program_record(pid):
    return Procedure(id=pid, origin='searchqa', description='A fixture program.', hooks=('applies', 'before_call'),
                     source=SOURCE, evidence='engineering_fixture', max_note_chars=600).to_json()


def world(*, card=True, programs=0, signature='question/context', texts=QA_TEXTS, card_text=CARD_TEXT):
    tm = typing_.TypeMap()
    sid = tm.add_source({'path': '/x/pool.json', 'sha256': 'a' * 64}, signature, axis(texts), step=1)
    tid = tm.new_type(sid, step=1)
    library = lib.Library()
    if card:
        library.add(lib.make_skill(skill_id='card-%s-s1' % tid, name='fixture-card', kind='card', home_type=tid,
                                   body={'text': card_text}, origin={'chain': 'G', 'step': 1, 'bench': 'searchqa'},
                                   description='For the fixture tasks.'))
        tm.set_card(tid, 'card-%s-s1' % tid, step=1)
    for letter in 'ab'[:programs]:
        skill = lib.make_skill(skill_id='prog-%s-s1-%s' % (tid, letter), name='fixture-program-' + letter,
                               kind='program', home_type=tid, body={'procedure': program_record('fx-typed-' + letter)},
                               origin={'chain': 'G', 'step': 1, 'bench': 'searchqa'}, description='Scans the input.')
        library.add(skill)
        tm.add_program(tid, skill['skill_id'], step=1)
    return tm, library, tid, tm.data['sources'][sid]['centroid']


class Selector:
    def __init__(self):
        self.sends = 0

    def __call__(self, system, user):
        self.sends += 1
        return {'ok': True, 'response': '{"use": [], "why": "none"}', 'finish_reason': 'stop', 'usage': {}}


def plain_case(bench):
    """An item of each bench with what ``mount`` needs to derive (QA, ZebraLogic) or receive (the others) its view."""
    if bench == 'searchqa':
        return searchqa_items(1)[0], {}
    if bench == 'zebralogic':
        return ZEBRA_ITEM, {'runtime': {'zebralogic': {}}}
    views = {'officeqa': {'question': 'What is the 2020 excise total?', 'context': 'Year | Excise\n2020 | 305'},
             'spreadsheetbench': {'instruction': 'Put the sum of A1:A3 in B1.', 'workbook_preview': 'A1=1 A2=2 A3=3'},
             'alfworld': {'task': 'put a clean mug in the coffee machine', 'admissible_commands': ['go to sink 1']}}
    item = {'benchmark': bench, 'task_id': 'fx-%s-1' % bench, 'public': dict(views[bench]), 'private': {}}
    return item, {'view': views[bench]}


def both(bench, item, **kw):
    """mount and mount_identity of one case under each base: {base: (record, identity)}, the identity checked."""
    out = {}
    for base in BASE_CARDS:
        selector = Selector() if kw.get('arm') in mount.ROUTED_ARMS else None
        record = mount.mount(bench, item, selector=selector, base_card=base, **kw)
        identity = mount.mount_identity(bench, item, base_card=base, **kw)
        assert identity['system_card_sha256'] == record['system_card_sha256'] == sha256(record['system_card'])
        out[base] = record
    return out


@pytest.mark.parametrize('bench', ORDER)
def test_read_arms_keep_their_mounts_and_B_is_the_base_alone(bench):
    item, extra = plain_case(bench)
    plain = dict(typemap=None, library=None, vector=None, **extra)
    c0, c, b = both(bench, item, arm='C0', **plain), both(bench, item, arm='C', **plain), both(bench, item, arm='B', **plain)
    default = mount.mount(bench, item, arm='C0', **plain)  # the read arms never depend on the base
    assert c0['format'] == c0['historical'] == default and c0['format']['system_card'] == mount.format_block(bench)
    assert c['format'] == c['historical'] == mount.mount(bench, item, arm='C', **plain)
    assert c['format']['system_card'] == mount.historical_card(bench)
    assert {**b['format'], 'arm': 'C0'} == default  # 'format': B mounts what C0 mounts (requests unchanged)
    assert {**b['historical'], 'arm': 'C', 'card_text': c['format']['card_text']} == c['format']  # 'historical': C's text
    for base in BASE_CARDS:
        assert b[base]['system_card'] == mount.system_card(bench, '', base_card=base) == mount.base_text(bench, base)
        assert b[base]['card_text'] == '' and not b[base]['routed'] and b[base]['enabled'] == []
    assert mount.base_text(bench, 'format') == mount.format_block(bench)
    assert mount.base_text(bench, 'historical') == mount.historical_card(bench)
    if bench == 'zebralogic':  # ZebraLogic's C is its format block: nothing changes with the base
        assert b['format'] == b['historical'] and mount.historical_card(bench) == zebralogic.CARD_TEXT
    else:
        assert b['historical']['system_card'] != b['format']['system_card']


def test_learned_mounts_compose_on_the_base_and_unknown_or_card_less_items_read_C():
    qa, C, block = searchqa_items(1)[0], mount.historical_card('searchqa'), mount.format_block('searchqa')
    base = {'format': block, 'historical': C}
    carded, bare, programs_only = world(), world(card=False), world(card=False, programs=1)
    far = axis(['treasury table z'])[0]

    def routed(state, arm='F', vector=None, candidate=None, item=qa, bench='searchqa', **extra):
        tm, library, _, centroid = state
        return both(bench, item, arm=arm, typemap=tm, library=library, candidate=candidate,
                    vector=centroid if vector is None else vector, **extra)
    tid = carded[2]
    cases = {
        'F with a card': (routed(carded), CARD_TEXT + CARD_JOIN),
        'F, type without skills': (routed(bare), ''),
        'F, typed without a card, programs offered': (routed(programs_only), ''),
        'F, distance above p95': (routed(carded, vector=far), ''),
        'F, unseen signature': (both('searchqa', qa, arm='F', typemap=typing_.TypeMap(), library=lib.Library(),
                                     vector=None), ''),
        'cand_card applied': (routed(carded, 'cand_card', candidate={'text': NEW_CARD, 'home_type': tid}),
                              NEW_CARD + CARD_JOIN),
        'cand_card on an unknown item': (routed(carded, 'cand_card', vector=far,
                                                candidate={'text': NEW_CARD, 'home_type': tid}), ''),
        'cand_program with a card': (routed(carded, 'cand_program',
                                            candidate={'procedure': program_record('fx-cand'), 'home_type': tid}),
                                     CARD_TEXT + CARD_JOIN),
        'cand_program without a card': (routed(bare, 'cand_program', candidate={'procedure': program_record('fx-cand'),
                                                                                'home_type': bare[2]}), ''),
    }
    for name, (records, head) in cases.items():
        for kind, text in base.items():
            assert records[kind]['system_card'] == head + text, (name, kind)
            assert records[kind]['card_text'] == (head[:-len(CARD_JOIN)] if head else ''), (name, kind)
        # everything but the system card is the same under both bases (routing, offers, selection, candidate)
        strip = lambda r: {k: v for k, v in r.items() if k not in ('system_card', 'system_card_sha256')}
        assert strip(records['format']) == strip(records['historical']), name
    assert cases['F, typed without a card, programs offered'][0]['historical']['programs_offered'] == ['prog-t01-s1-a']
    assert cases['F, unseen signature'][0]['historical']['unknown_reason'] == 'unseen_signature'
    assert cases['F, distance above p95'][0]['historical']['unknown_reason'] == 'distance_above_p95'
    # an unknown or card-less item mounts byte-equal system text: arm C's under 'historical', arm C0's under 'format'
    c_arm = mount.mount('searchqa', qa, arm='C', typemap=None, library=None, vector=None)
    c0_arm = mount.mount('searchqa', qa, arm='C0', typemap=None, library=None, vector=None)
    for name in ('F, type without skills', 'F, typed without a card, programs offered', 'F, distance above p95',
                 'F, unseen signature', 'cand_card on an unknown item', 'cand_program without a card'):
        assert cases[name][0]['historical']['system_card'] == c_arm['system_card'], name
        assert cases[name][0]['format']['system_card'] == c0_arm['system_card'], name
    # ZebraLogic: a learned card composes on its format block under both bases
    zebra = world(signature='puzzle_template', texts=['There are %d houses.' % i for i in range(2, 42)],
                  card_text='- fill the grid')
    found = routed(zebra, item=ZEBRA_ITEM, bench='zebralogic', runtime={'zebralogic': {}})
    assert found['format'] == found['historical']
    assert found['historical']['system_card'] == '- fill the grid' + CARD_JOIN + zebralogic.CARD_TEXT


def test_an_unknown_base_card_is_refused_everywhere():
    qa = searchqa_items(1)[0]
    tm, library, _, centroid = world()
    for bad in ('Historical', 'C', '', None, 'format '):
        with pytest.raises(ValueError, match='base card'):
            mount.base_text('searchqa', bad)
        with pytest.raises(ValueError, match='base card'):
            mount.system_card('searchqa', CARD_TEXT, base_card=bad)
        for arm in ('B', 'F', 'C0'):
            with pytest.raises(ValueError, match='base card'):
                mount.mount('searchqa', qa, arm=arm, typemap=tm, library=library, vector=centroid, selector=Selector(),
                            base_card=bad)
            with pytest.raises(ValueError, match='base card'):
                mount.mount_identity('searchqa', qa, arm=arm, typemap=tm, library=library, vector=centroid, base_card=bad)
        with pytest.raises(ValueError):
            prepare.base_card_of({'base_card': bad})
        with pytest.raises(ValueError):
            smoke.synthetic_manifest(base_card=bad)
    assert (typed.BASE_CARDS, typed.BASE_CARD_DEFAULT) == (('format', 'historical'), 'format')
    assert 'B' in mount.ARMS and 'B' not in mount.ROUTED_ARMS and mount.BASE_ARM == 'B' and 'B' not in typed.READ_ARMS


# ---- the writers ---------------------------------------------------------------------------------------------------
EXAMPLES = [{'task_id': 'fx-searchqa-00', 'view': 'Q: who? C: snippets', 'reply': 'Ada', 'outcome': 'fail',
             'reference': 'Ada Lovelace', 'request_user': '{"question": "who?"}'},
            {'task_id': 'fx-searchqa-01', 'view': 'Q: when? C: snippets', 'reply': '1843', 'outcome': 'pass',
             'request_user': '{"question": "when?"}'}]


def test_card_request_and_proposal_payload_hold_the_base_block_only_where_it_adds():
    assert sha256(writers.BASE_CARD_MEANING) == LABEL_SHA256['writers']
    assert sha256(engineer_prompt.BASE_CARD_MEANING) == LABEL_SHA256['engineer']
    for bench in ORDER:
        kw = dict(bench=bench, runtime={}, current_text='- current card', examples=EXAMPLES[1:], round=1)
        before, dropped = writers.card_request(**kw)  # the code default: the request without D17
        fmt, _ = writers.card_request(base_card='format', **kw)
        hist, hist_dropped = writers.card_request(base_card='historical', **kw)
        assert fmt == before and 'base_card' not in before and dropped == hist_dropped
        payload = dict(bench=bench, runtime={}, skill_index=[{'name': 'fixture-card', 'kind': 'card', 'description': 'x'}],
                       examples=EXAMPLES if bench == 'searchqa' else [], hook_view={'routing_view': {}})
        proposal = writers.program_payload(**payload)
        assert writers.program_payload(base_card='format', **payload) == proposal and 'base_card' not in proposal
        hist_proposal = writers.program_payload(base_card='historical', **payload)
        if bench == 'zebralogic':
            assert hist == before and hist_proposal == proposal
            continue
        C = mount.historical_card(bench)
        assert hist == {**before, 'base_card': {'meaning': writers.BASE_CARD_MEANING, 'text': C}}
        assert hist_proposal == {**proposal, 'base_card': {'meaning': engineer_prompt.BASE_CARD_MEANING, 'text': C}}
        assert C == mount.system_card(bench, '', base_card='historical')  # exactly what the solver receives
    revised, _ = writers.card_request(bench='officeqa', runtime={}, current_text='', examples=[], round=2,
                                      previous='- old card', result={'kind': 'other', 'n': 3}, base_card='historical')
    assert revised['base_card']['text'] == mount.historical_card('officeqa') and revised['previous_card'] == '- old card'


class Call:
    """A recorded writer call with scripted replies."""

    def __init__(self, replies):
        self.replies, self.sends = list(replies), []

    def __call__(self, system, user):
        self.sends.append({'system': system, 'user': user})
        return {'ok': True, 'response': self.replies.pop(0), 'finish_reason': 'stop', 'usage': {}}


def test_write_card_shows_C_counts_the_learned_text_only_and_never_flags_C_as_a_copy():
    C, block = mount.historical_card('searchqa'), mount.format_block('searchqa')
    line = next(row for row in C.splitlines() if row not in block.splitlines() and len(row.split()) > 12)
    shown = [{'task_id': 'fx-searchqa-00', 'view': 'Q: who wrote it?', 'reply': 'I checked: ' + line, 'outcome': 'pass',
              'request_user': '{"question": "who wrote it?"}'}]
    corpus = writers.corpus_for('searchqa', searchqa_items(2))
    kw = dict(bench='searchqa', runtime={}, current_text='', examples=shown, corpus=corpus, practice_ids=['fx-x'],
              round=1)
    # a card repeating a line of C that an example's reply also holds: a copy of an example under 'format' (the
    # line is not public there), public text the solver already receives under 'historical'
    fmt = writers.write_card(call=Call([line, line]), base_card='format', **kw)
    assert [a['violation'] for a in fmt['attempts']] == ['copied_examples', 'copied_examples'] and fmt['text'] is None
    call = Call([line])
    hist = writers.write_card(call=call, base_card='historical', **kw)
    assert hist['text'] == line + '\n' and hist['attempts'][0]['violation'] is None
    request = json.loads(call.sends[0]['user'])
    assert request['base_card'] == {'meaning': writers.BASE_CARD_MEANING, 'text': C} and request['format_block'] == block
    # D2's length rules count the learned text only: 4,400 content characters pass with C beside them
    long_card = '\n'.join('- ' + 'keep the reasoning short and check every snippet before you answer, ' * 6
                          for _ in range(11))[:4400].rstrip()
    assert cards.content_chars(long_card) <= cards.CARD_HARD_CHARS < cards.content_chars(long_card) + len(C)
    found = writers.write_card(call=Call([long_card]), base_card='historical', **{**kw, 'examples': []})
    assert found['attempts'][0]['violation'] is None and found['attempts'][0]['chars'] == cards.content_chars(long_card)


# ---- manifest, chain state, smoke, command line --------------------------------------------------------------
def test_prepare_seals_the_base_card_and_load_manifest_refuses_another(inputs):
    parent = inputs['parent']
    common = dict(machinery_manifest=inputs['machinery'], roles_repo='/root/roles', pools_root=inputs['pools'],
                  smoke=True, typed_tree=inputs['tree'], root_parent=str(parent))
    made = prepare.prepare(parent / 'execskill-20261112-typed-v3-smoke', base_card='historical', **common)
    assert made['base_card'] == 'historical' and prepare.load_manifest(made['root']) == made
    default = prepare.prepare(parent / 'execskill-20261113-typed-v3-smoke', **common)
    assert default['base_card'] == BASE_CARD_DEFAULT == 'format'
    assert made['record_sha256'] != prepare.seal({k: v for k, v in made.items() if k != 'record_sha256'} | {
        'base_card': 'format'})['record_sha256']  # the field is inside the sealed record
    fields = {key: value for key, value in made.items() if key != 'record_sha256'}
    root = Path(made['root'])
    for bad in ('other', None, ['historical']):
        units.write_json(root / 'manifest.json', prepare.seal({**fields, 'base_card': bad}))
        with pytest.raises(ValueError, match='base card'):
            prepare.load_manifest(root)
    units.write_json(root / 'manifest.json', prepare.seal({k: v for k, v in fields.items() if k != 'base_card'}))
    with pytest.raises(ValueError, match='base card'):
        prepare.load_manifest(root)
    raw = dict(made)
    raw['base_card'] = 'format'  # edited without re-sealing: the record hash no longer verifies
    units.write_json(root / 'manifest.json', raw)
    with pytest.raises(ValueError, match='hash'):
        prepare.load_manifest(root)
    bogus = parent / 'execskill-20261114-typed-v3-smoke'
    with pytest.raises(ValueError, match='base card'):
        prepare.prepare(bogus, base_card='hist', **common)
    assert not bogus.exists()  # refused before anything is written


def test_the_chain_refuses_a_manifest_without_a_base_and_a_resume_with_another(tmp_path):
    services = smoke.fake_services(tmp_path / 'a', 'G', {**smoke.synthetic_manifest(), 'base_card': None})
    services.order = ('searchqa',)
    with pytest.raises(ValueError, match='base card'):
        chain.run(tmp_path / 'a', 'G', services=services)
    assert not (tmp_path / 'a').exists()  # refused before anything is written
    fresh = chain._open_state(tmp_path / 'b' / 'G', 'G', 'smoke', False, base_card='historical')
    assert fresh['base_card'] == 'historical'
    units.write_json(tmp_path / 'b' / 'G' / 'state.json', fresh)
    assert chain._open_state(tmp_path / 'b' / 'G', 'G', 'smoke', True, base_card='historical')['base_card'] == 'historical'
    with pytest.raises(ValueError, match='started with another base_card'):
        chain._open_state(tmp_path / 'b' / 'G', 'G', 'smoke', True, base_card='format')


def test_the_smoke_runs_on_either_base(tmp_path):
    root = tmp_path / 'execskill-20261112-typed-v3'
    state = smoke.run(root, 'G', fake=True, base_card='historical', sleep=lambda s: None)
    assert state['complete'] and state['base_card'] == 'historical'
    noise = json.loads((smoke.smoke_root(root) / 'G' / 's1' / 'noise' / 'noise.json').read_text())
    assert noise['mount_arm'] == 'B' and noise['arms'] == ['B#1', 'B#2', 'B#3']  # step 5w: R = 3 runs (DESIGN 3.4)
    cell = json.loads(next((smoke.smoke_root(root) / 'G' / 's1' / 'noise' / 'cells').glob('*.json')).read_text())
    assert cell['sends'][0]['system'] == mount.historical_card('searchqa')
    units.write_json(smoke.smoke_root(root) / 'G' / 'recovery.json', {'by': 'owner', 'date': '2026-11-12', 'decision': 'x'})
    with pytest.raises(ValueError, match='started with another base_card'):
        smoke.run(root, 'G', fake=True, resume=True, sleep=lambda s: None)  # the synthetic default is 'format'
    assert smoke.synthetic_manifest()['base_card'] == 'format'
    assert smoke.synthetic_manifest(base_card='historical')['base_card'] == 'historical'
    # a prepared smoke root: the base it seals, and a different --base-card is refused
    prepared = tmp_path / 'execskill-20261113-typed-v3-smoke'
    units.write_json(prepared / 'manifest.json', prepare.seal({
        'version': 'typed-v3', 'configuration': 'typed-v3', 'root': str(prepared), **prepare.sealed_constants(),
        **sealed_code(), 'base_card': 'historical',
        'schedule': 'interleaved', 'memory_lock': 'per_cell_plain',  # step 6s: a loadable manifest seals both
        'read_plan': 'full'}))  # step rp-int: and its read plan (read-plan R3)
    assert smoke.smoke_manifest(prepared, fake=False)['base_card'] == 'historical'
    assert smoke.smoke_manifest(prepared, fake=False, base_card='historical')['base_card'] == 'historical'
    with pytest.raises(ValueError, match='prepared with base_card'):
        smoke.smoke_manifest(prepared, fake=False, base_card='format')


def test_the_command_line_takes_the_base_card_on_prepare_and_smoke(tmp_path, monkeypatch, capsys):
    assert run_typed.BASE_CARDS == typed.BASE_CARDS
    parse = run_typed.parser().parse_args
    assert parse(['prepare', '--root', '/r', '--base-card', 'historical']).base_card == 'historical'
    assert parse(['smoke', '--root', '/r', '--chain', 'G', '--fake', '--base-card', 'format']).base_card == 'format'
    assert parse(['prepare', '--root', '/r']).base_card is None
    for bad in (['prepare', '--root', '/r', '--base-card', 'C'], ['run', '--root', '/r', '--chain', 'G', '--base-card',
                                                                  'historical']):
        with pytest.raises(SystemExit):
            parse(bad)
    calls = []
    monkeypatch.setattr(run_typed, 'clean_environment', lambda: None)
    monkeypatch.setattr(run_typed, '_prepare', lambda root, **kw: calls.append(('prepare', kw)) or
                        {'configuration': 'typed-v2', 'base_card': kw.get('base_card', 'format')})
    monkeypatch.setattr(run_typed, '_smoke_run', lambda root, chain, **kw: calls.append(('smoke', kw)) or {'status': 'complete'})
    root = tmp_path / 'run'
    root.mkdir()
    machinery = tmp_path / 'machinery.json'
    machinery.write_text(json.dumps({'runtime': {}}))
    assert run_typed.main(['prepare', '--root', str(root), '--machinery-manifest', str(machinery),
                           '--base-card', 'historical']) == 0
    assert calls[-1][1]['base_card'] == 'historical'
    assert json.loads(capsys.readouterr().out)['manifest']['base_card'] == 'historical'  # the sealed base is printed
    assert run_typed.main(['smoke', '--root', str(root), '--chain', 'G', '--fake', '--base-card', 'historical']) == 0
    assert calls[-1] == ('smoke', {'fake': True, 'base_card': 'historical'})
    assert run_typed.main(['smoke', '--root', str(root), '--chain', 'G', '--fake']) == 0
    assert calls[-1] == ('smoke', {'fake': True})  # no option: nothing passed, the manifest decides
