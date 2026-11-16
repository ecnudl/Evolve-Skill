"""typed-v3 item stage (build brief P2b): the guarantees Codex's review of P2b found untested (finding 5), on fakes only
(no network, no paid call, no /data).

1. A corrupted seal is refused on resume. A step dies right after its ``items.json`` was sealed; its sealed lists are
   then edited without a new ``record_sha256``, or the stored file of a judging item gets another reference. The
   resumed step refuses at the seal check (``itemstage._read_sealed``, ``itemstage._item_of``) before any unit or
   call runs on the edited list; an untouched seal resumes into the uninterrupted run's records.
2. The default flow equals the base commit's. ``git archive`` exports bd421da (the base of P2b; it already carries P1's
   version switch, so its version and evidence labels are typed-v3's and the label mapping P1 needed for its typed-v2
   base is the identity here: the test checks that) and ``tests/typed3_base_runner.py`` runs the same five-bench fake
   chains in both trees (``tests/test_typed2_shared.py``'s ``SINGLE`` scenarios through its ``real_run``, the REAL
   mount, writers and reads, frozen clock), with the synthetic manifest as it is and with the explicit default fields
   a prepare now seals (decision B6 (c)). Every file of the run root, every request and the end state must be equal,
   record hashes included, apart from what differs between two runs of ONE tree (the send counter ``logical_call`` and
   the ledger snapshots of ``done.json`` / ``decisions.json``, which depend on thread timing; time keys are stripped as
   in P1's comparison); a default prepare seals the base's manifest plus ``item_stage`` 'none' and ``item_quotas``
   null.
3. One uniform scan of every request of a full 'planned' step (SearchQA; one item round, two rounds, an accepted
   archive package; program learning 'repair'): the card writer, the engineer, its repairs, the describers, the
   analyst, the selector, the first call and the solver are each held to one rule table (B6 (a), (b); T4, T6).
"""
import json
import re
import shutil
import subprocess
import sys
import tarfile
import tempfile
from pathlib import Path

import pytest

from skillopt.execskill.typed import chain, itemstage
from tests.test_typed3_item_stage import (NEUTRAL, NOW, Script, build, index, lenient, planned_archive, read, records,
                                          run, sq_id, strict, tmp_path)  # noqa: F401 -- tmp_path: the neutral fixture
from tests.test_typed_chain import recovery

TREE = Path(__file__).resolve().parents[1]
RUNNER = Path(__file__).resolve().with_name('typed3_base_runner.py')
BASE_COMMIT = 'bd421da'
LEARN, GATE = set(range(12)), set(range(12, 20))
CANDIDATES = set(range(20, 80))     # neither learn nor gate: what the selector may read (B6 (a))


# ==== 1: a corrupted seal is refused on resume ===========================================================================
def kill_after_the_seal(monkeypatch):
    """The step dies (a process death, no pause) right after its items.json was sealed and its list activated: the
    first gate unit (noise) never starts."""
    original, hit = chain._Run.noise, []

    def noise(self, k, bench):
        if not hit:
            hit.append(k)
            raise RuntimeError('killed after the seal')
        return original(self, k, bench)
    monkeypatch.setattr(chain._Run, 'noise', noise)
    return hit


def move_a_judging_item_to_the_shown_list(root):
    """items.json edited in place, its record_sha256 kept: judging attack item 20 listed as a shown attack item (a
    writer would see it, J would lose it)."""
    path = root / 'G' / 's1' / 'items.json'
    sealed = json.loads(path.read_text())
    entry = sealed['lists']['judging']['attack'].pop(0)
    assert entry['record']['item'] == sq_id(20)
    sealed['lists']['shown']['attack'].append(entry)
    path.write_text(json.dumps(sealed, indent=1, sort_keys=True))
    return path, ('_read_sealed', 'The items.json of s1 is the one sealed')


def change_a_judging_items_reference(root):
    """The stored file of judging attack item 20 (``<unit>/items/<slot>.json``) gets another reference: the judge would
    read it. items.json itself is untouched."""
    entry = json.loads((root / 'G' / 's1' / 'items.json').read_text())['lists']['judging']['attack'][0]
    path = root / 'G' / entry['unit'] / 'items' / (entry['slot'] + '.json')
    item = json.loads(path.read_text())
    assert item['task_id'] == sq_id(20) and item['private']['answers'] == ['REF20']
    item['private']['answers'] = ['REF21']
    path.write_text(json.dumps(item, indent=1, sort_keys=True))
    return path, ('_item_of', 'The item of %s/%s is the one its record names' % (entry['unit'], entry['slot']))


CORRUPTIONS = {'intact': None, 'items_json': move_a_judging_item_to_the_shown_list,
               'item_file': change_a_judging_items_reference}


def refusals(monkeypatch):
    """Every ValueError of the two seal checks as it passes: [(function, message)]."""
    found = []
    for name in ('_read_sealed', '_item_of'):
        original = getattr(itemstage, name)

        def spy(*args, _original=original, _name=name, **kw):
            try:
                return _original(*args, **kw)
            except ValueError as error:
                found.append((_name, str(error)))
                raise
        monkeypatch.setattr(itemstage, name, spy)
    return found


@pytest.mark.parametrize('corruption', sorted(CORRUPTIONS))
def test_a_resumed_step_refuses_a_corrupted_seal_before_anything_runs_on_it(tmp_path, monkeypatch, corruption):
    """SearchQA, one item round (strict). The run dies right after s1/items.json; then (items_json) the sealed lists
    are edited and the old record_sha256 kept, or (item_file) the stored file of judging attack item 20 gets another
    reference, or (intact) nothing changes. On resume the edited seal is refused by its own check (the hash of
    items.json, the hash of the item file against its record), the chain pauses, no request is sent, no gate unit
    starts and the edited file stays as it is; the intact seal resumes into the uninterrupted run's records."""
    monkeypatch.setattr(chain, '_now', lambda: NOW)
    state, _ = run(tmp_path / 'a', Script())
    assert state['complete'], state['paused']
    root, script = tmp_path / 'b', Script()
    services = build(root, script)
    with monkeypatch.context() as patched:
        hit = kill_after_the_seal(patched)
        state = chain.run(root, 'G', services=services, sleep=lambda s: None)
    assert hit == [1] and state['paused']['reason'] == 'exception:RuntimeError', state['paused']
    assert (root / 'G' / 's1' / 'items.json').exists() and not (root / 'G' / 's1' / 'noise').exists()
    corrupt = CORRUPTIONS[corruption]
    path, expected = corrupt(root) if corrupt is not None else (None, None)
    edited = path.read_bytes() if path is not None else None
    found = refusals(monkeypatch)
    recovery(root)
    before = len(script.requests)
    state = chain.run(root, 'G', services=services, resume=True, sleep=lambda s: None)
    if corrupt is None:
        assert state['complete'], state['paused']
        assert found == [] and records(root) == records(tmp_path / 'a')
        return
    assert (state['paused'] or {}).get('reason') == 'exception:ValueError', (state['complete'], state['paused'])
    assert found == [expected]
    assert len(script.requests) == before                                  # nothing sent on the edited list
    assert not (root / 'G' / 's1' / 'noise').exists()                       # no gate unit started
    assert path.read_bytes() == edited                                      # the stage rewrote nothing
    # a second resume refuses the same way
    recovery(root)
    state = chain.run(root, 'G', services=services, resume=True, sleep=lambda s: None)
    assert state['paused']['reason'] == 'exception:ValueError' and found == [expected, expected]
    assert len(script.requests) == before


# ==== 2: the default flow equals the base commit's ======================================================================
@pytest.fixture(scope='module')
def base_tree():
    """A ``git archive`` export of the base commit in a new, empty directory; skipped when the checkout lacks git or
    the commit (a copy without history)."""
    try:
        known = subprocess.run(['git', '-C', str(TREE), 'cat-file', '-e', BASE_COMMIT + '^{commit}'],
                               capture_output=True)
    except FileNotFoundError:
        pytest.skip('git is not installed')
    if known.returncode != 0:
        pytest.skip('the base commit %s is not in this checkout' % BASE_COMMIT)
    NEUTRAL.mkdir(parents=True, exist_ok=True)
    where = Path(tempfile.mkdtemp(prefix='base-', dir=NEUTRAL))
    try:
        export = subprocess.Popen(['git', '-C', str(TREE), 'archive', '--format=tar', BASE_COMMIT],
                                  stdout=subprocess.PIPE)
        with tarfile.open(fileobj=export.stdout, mode='r|') as tar:
            tar.extractall(where, **({'filter': 'data'} if hasattr(tarfile, 'data_filter') else {}))
        assert export.wait() == 0
        yield where
    finally:
        shutil.rmtree(where, ignore_errors=True)


def dump(tree, mode, where, *args):
    """One run of ``tests/typed3_base_runner.py`` in ``tree`` (its own process); its JSON dump."""
    out = where.parent / (where.name + '.json')
    done = subprocess.run([sys.executable, str(RUNNER), str(tree), mode, str(where), str(out), *args], cwd=str(tree),
                          capture_output=True, text=True, timeout=900)
    assert done.returncode == 0, done.stderr[-4000:]
    return json.loads(out.read_text())


TIME_KEYS = {'at', 'accepted_at', 'updated', 'started', 'saved_at', 'frozen_at', 'created_at', 'seconds', 'applied_at',
             'bound_at', 'finished'}
SNAPSHOTS = ('done.json', 'decisions.json')   # their 'ledger' is a snapshot of the shared ledger at that moment


def strip(value):
    if isinstance(value, dict):
        return {k: strip(v) for k, v in value.items() if k not in TIME_KEYS and k != 'logical_call'}
    if isinstance(value, list):
        return [strip(v) for v in value]
    return value


def comparable(found):
    """A runner dump without what differs between two runs of one tree: time keys (the clock is frozen, so the hashes
    over them are equal), the send counters and the ledger snapshots of done.json / decisions.json (thread timing),
    the order of the requests (concurrent sends). The final ledger.json and state.json stay."""
    files = {}
    for rel, entry in found['files'].items():
        value = strip(entry['json']) if 'json' in entry else entry
        if rel.rsplit('/', 1)[-1] in SNAPSHOTS and isinstance(value, dict):
            value.pop('ledger', None)
        files[rel] = value
    return {'complete': found['complete'], 'paused': found['paused'], 'files': files,
            'requests': sorted(json.dumps(request) for request in found['requests'])}


def differences(a, b, path=''):
    """The differing leaves of two JSON values: [(path, a, b)]."""
    if isinstance(a, dict) and isinstance(b, dict):
        return [row for k in sorted(set(a) | set(b)) for row in (
            differences(a[k], b[k], '%s/%s' % (path, k)) if k in a and k in b
            else [('%s/%s' % (path, k), a.get(k, '<absent>'), b.get(k, '<absent>'))])]
    if isinstance(a, list) and isinstance(b, list) and len(a) == len(b):
        return [row for i, (u, v) in enumerate(zip(a, b)) for row in differences(u, v, '%s[%d]' % (path, i))]
    return [] if a == b else [(path, a, b)]


def shown(rows, limit=12):
    return '\n'.join('%s: %s -> %s' % (p, repr(u)[:160], repr(v)[:160]) for p, u, v in rows[:limit])


@pytest.mark.parametrize('variant', ['absent', 'explicit'])
@pytest.mark.parametrize('scenario', ['smoke', 'default'])
def test_the_default_flow_writes_the_base_commits_records(base_tree, tmp_path, scenario, variant):
    """Codex P2b finding 5 (and 4, decided by B6 (c)): with the item stage 'none' and every other option at its
    default, the five-bench fake chain of ``tests/test_typed2_shared.py`` (scenario ``smoke`` or ``default``) writes in
    this tree exactly what bd421da (P2b's base, exported by ``git archive``) writes: the same files (state.json,
    ledger.json, every calls file, cell, done record, decision, library and read aggregate, compared as parsed JSON
    with every record hash), the same multiset of requests and the same end state, after taking out only what two runs
    of one tree differ in. ``absent``: the synthetic manifest names no typed-v3 option (an old manifest);
    ``explicit``: each tree's manifest carries the option fields its default prepare seals (here also item_stage
    'none' and item_quotas null). The version and evidence labels of both trees are equal (typed-v3), so no label is
    mapped back."""
    base = dump(base_tree, 'chain', tmp_path / 'base', scenario, variant)
    new = dump(TREE, 'chain', tmp_path / 'new', scenario, variant)
    assert base['labels'] == new['labels'] == {'version': 'typed-v3', 'evidence': {
        'run': 'typed_v3_real_run', 'smoke': 'typed_v3_smoke', 'test': 'engineering_fixture'}}
    assert base['complete'] and new['complete'], (base['paused'], new['paused'])
    a, b = comparable(base), comparable(new)
    assert sorted(a['files']) == sorted(b['files']), (sorted(set(a['files']) ^ set(b['files']))[:20])
    assert len(a['files']) > 700 and any(rel.endswith('/decisions.json') for rel in a['files'])
    rows = differences(a['files'], b['files'])
    assert rows == [], 'records differ from %s:\n%s' % (BASE_COMMIT, shown(rows))
    assert a['requests'] == b['requests'] and len(a['requests']) > 250
    assert (a['complete'], a['paused']) == (b['complete'], b['paused'])
    # nothing of the item stage in this tree's run: no stage unit, no items.json, no items block or class gains
    text = json.dumps(new['files'])
    assert not [rel for rel in new['files'] if rel.split('/')[-1] == 'items.json' or '/diagnose/' in rel]
    assert '"by_class"' not in text and '"items_sha256"' not in text and '"item_stage"' not in text


def test_a_default_prepare_seals_the_base_commits_manifest_plus_the_two_item_fields(base_tree, tmp_path):
    """Decision B6 (c): a default smoke prepare (the fixture inputs of ``tests/test_typed_reads.py``, frozen clock, the
    same parent directory) seals in this tree bd421da's manifest plus ``item_stage`` 'none' and ``item_quotas`` null,
    nothing else (the code-identity fields name the tree a run comes from: mapped to one placeholder)."""
    parent = tmp_path / 'prepared'
    base = dump(base_tree, 'prepare', parent)
    shutil.rmtree(parent)
    new = dump(TREE, 'prepare', parent)

    def fields(found, tree):
        manifest = {key: value for key, value in found['manifest'].items() if key != 'record_sha256'}
        return json.loads(json.dumps(manifest).replace(json.dumps(str(tree))[1:-1], '<tree>'))
    old, now = fields(base, base_tree), fields(new, TREE)
    assert 'item_stage' not in old and 'item_quotas' not in old
    assert now == {**old, 'item_stage': 'none', 'item_quotas': None}, shown(differences(
        {**old, 'item_stage': 'none', 'item_quotas': None}, now))
    assert old['machinery_code']['snapshot'] == '<tree>' and old['program_learning'] == 'single'


# ==== 3: one uniform scan of every request of a full planned step ======================================================
# Every request of the step is classified by its purpose; an unknown purpose fails the scan. What a request may hold of
# an item (its public text: question or snippet; its reference: the judge's answer), by kind:
#   every kind              no reference of a gate item or a judging-side item (final, replaced or unused), the
#                           selector and the solver included (B6 (b))
#   writer (card writer,    no public text of such an item; public text and references of learn items and of the
#   engineer, repairs)      FINAL shown items only (T6; B6 (b): a failed learn or shown item's reference is training
#                           material)
#   describer               no public text of such an item
#   analyst                 learn items only (T4: the learn rows)
#   selector                candidates only (neither learn nor gate: P2 brief D), judging-side candidates included
#                           (B6 (a)); no learn or gate item
#   first call              no item at all
#   solver                  the measurement: any public text; no gate or judging reference (above)
KINDS = {'card_writer': 'writer', 'program_writer': 'writer', 'describer': 'describer', 'item_analyst': 'analyst',
         'item_selector': 'selector', 'first_call': 'fixture', 'solver': 'solver'}
PUBLIC = [re.compile(pattern) for pattern in (r'Q(\d\d) ', r'CTX(\d\d)', r'did event (\d+) happen', r'wrote book (\d+)\?',
                                              r'is landmark (\d+)\?', r'has machine (\d+)\?', r'snippet on item (\d+)\.')]
REFERENCE = re.compile(r'REF(\d\d)')


def held(text):
    """The SearchQA fixture items whose public text, and whose reference, a request holds (by their markers)."""
    return {int(m) for pattern in PUBLIC for m in pattern.findall(text)}, {int(m) for m in REFERENCE.findall(text)}


def sides(sealed):
    """(judging-side items of the step: final, replaced and unused; the final shown items) by index."""
    judging = {index(e['record']['item']) for e in itemstage.entries_of(sealed) if e['record']['side'] == 'judging'}
    final = {index(e['record']['item']) for cls in ('attack', 'guard') for e in sealed['lists']['shown'][cls]}
    return judging, final


def violations(requests, sealed):
    """Every breach of the rule table by any request: [(purpose, unit, rule, items)]."""
    judging, final = sides(sealed)
    private, writable = GATE | judging, LEARN | final
    out = []
    for purpose, unit, system, user in requests:
        kind = KINDS[purpose]
        public, references = held(system + '\n' + user)
        rules = [('reference_of_gate_or_judging_item', references & private)]
        if kind not in ('selector', 'solver'):
            rules.append(('public_text_of_gate_or_judging_item', public & private))
        if kind == 'writer':
            rules.append(('neither_learn_nor_final_shown', (public | references) - writable))
        elif kind == 'analyst':
            rules.append(('not_a_learn_item', (public | references) - LEARN))
        elif kind == 'selector':
            rules.append(('not_a_candidate', public - CANDIDATES))
        elif kind == 'fixture':
            rules.append(('any_item', public | references))
        out += [(purpose, unit, rule, sorted(items)) for rule, items in rules if items]
    return out


SCAN_UNITS = {
    'one_round': {('first_call', 'confirm'), ('item_analyst', 's1/items-plan'), ('item_selector', 's1/items'),
                  ('card_writer', 's1/card-r1'), ('describer', 's1/card-r1'), ('program_writer', 's1/programs'),
                  ('program_writer', 's1/program-1-repair-1')},
    'two_rounds': {('first_call', 'confirm'), ('item_analyst', 's1/items-plan'), ('item_analyst', 's1/items-plan-2'),
                   ('item_selector', 's1/items'), ('item_selector', 's1/items-2'), ('card_writer', 's1/card-r1'),
                   ('card_writer', 's1/card-r2'), ('program_writer', 's1/programs'),
                   ('program_writer', 's1/program-1-repair-1')},
    'archive': {('first_call', 'confirm'), ('item_analyst', 's1/items-plan'), ('item_selector', 's1/items'),
                ('card_writer', 's1/card-r1'), ('describer', 's1/program-0'), ('program_writer', 's1/programs'),
                ('program_writer', 's1/program-1-repair-1')},
}


def scan_run(tmp_path, monkeypatch, scenario):
    """The full step of a scan scenario under 'repair' (one free repair round, the paid round): one item round
    (strict: the card is accepted and described), two item rounds (lenient: the check fails, round 2 replaces the
    attack items, both card rounds are rejected), an accepted archive package (its skill is described)."""
    monkeypatch.setattr(chain, '_now', lambda: NOW)
    if scenario == 'archive':
        _, _, kw = planned_archive(monkeypatch, tmp_path / 'package')
    else:
        kw = dict(rule=strict if scenario == 'one_round' else lenient, program_learning='repair',
                  limits={'program_repair_rounds': 1, 'program_paid_feedback': 1, 'card_rounds': 2})
    script = Script()
    state, _ = run(tmp_path / 'run', script, **kw)
    assert state['complete'], state['paused']
    return script, read(tmp_path / 'run', 's1', 'items.json')


@pytest.mark.parametrize('scenario', sorted(SCAN_UNITS))
def test_every_request_of_a_planned_step_keeps_to_the_rule_table(tmp_path, monkeypatch, scenario):
    """Codex P2b finding 5 (with B6 (a), (b)): every request of the step -- card writer, engineer, its repair, the
    describers, the analyst, the selector, the first call, every solver request -- is scanned for the public text
    (question, snippet) and the reference of every SearchQA item, and held to the rule table above; the role calls of
    the step are the expected ones (none escapes the scan). The scan is not empty: the analyst holds the 12 learn
    items, the writers the final shown items, the selector every judging-side item (it read them as candidates), and
    the card writer the references of the failed shown attack items and of failed learn items (one item round)."""
    script, sealed = scan_run(tmp_path, monkeypatch, scenario)
    roles = [(p, u, s, x) for p, u, s, x in script.requests if p != 'solver']
    assert {(p, u) for p, u, _, _ in roles} == SCAN_UNITS[scenario]
    assert len(script.requests) > len(roles)
    assert violations(script.requests, sealed) == []
    judging, final = sides(sealed)
    by_unit, by_kind = {}, {}   # what the requests of one unit, of one kind hold together: (public, references)
    for purpose, unit, system, user in roles:
        public, references = held(system + '\n' + user)
        for found in (by_unit.setdefault((purpose, unit), (set(), set())),
                      by_kind.setdefault(KINDS[purpose], (set(), set()))):
            found[0].update(public)
            found[1].update(references)
    assert by_unit[('item_analyst', 's1/items-plan')][0] == LEARN
    assert final <= by_kind['writer'][0] and judging <= by_kind['selector'][0]
    assert by_kind['selector'][1] == set() and by_kind['analyst'][1] == set()
    if scenario == 'one_round':
        public, references = by_unit[('card_writer', 's1/card-r1')]
        assert {28, 29, 30} <= references and references & LEARN   # failed shown attack and learn items (strict)


def test_the_scan_catches_a_judging_item_handed_to_the_writers(tmp_path, monkeypatch):
    """The scan's control: the one-round step with judging attack item 20 slipped into the shown items after the seal
    (its outcome and its reference then reach the writers). The scan reports item 20's public text and reference in
    the writers' requests -- and nothing else."""
    original = itemstage._activate

    def leaky(run_, k, bench, record):
        original(run_, k, bench, record)
        run_.step_items['shown'][0] = run_.step_items['shown'][0] + run_.step_items['judging'][:1]
    monkeypatch.setattr(itemstage, '_activate', leaky)
    script, sealed = scan_run(tmp_path, monkeypatch, 'one_round')
    found = violations(script.requests, sealed)
    assert found and {(rule, tuple(items)) for _, _, rule, items in found} <= {
        ('reference_of_gate_or_judging_item', (20,)), ('public_text_of_gate_or_judging_item', (20,)),
        ('neither_learn_nor_final_shown', (20,))}
    assert {purpose for purpose, _, _, _ in found} <= {'card_writer', 'program_writer'}
    assert ('card_writer', 's1/card-r1', 'reference_of_gate_or_judging_item', [20]) in found
