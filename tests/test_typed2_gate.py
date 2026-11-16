"""typed-v2 step 5w: the gate wiring (DESIGN 3.4, 4.1, section 5; addendum O1, O5, O6, O11, O12, D17).

The chain runs every gate arm R = 3 times per gate item inside one unit (labels ``<arm>#<r>``), shares an arm whose
zero-call identity equals an earlier arm's on every gate item (``plan.json``), decides on item sums with the exact
rules of ``gates`` (re-exported from ``gatestats``) and stores records that ``gates.recompute`` reproduces. Fakes only:
the fake chain of ``tests/test_typed_chain.py`` and the smoke's scripted services (no network, no Docker, no /data).
"""
import json
import shutil
import tempfile
import threading
from collections import Counter
from pathlib import Path

import pytest

from skillopt.execskill.typed import (GATE_REPEATS, chain, gates, gatestats, smoke, tasktypes as typing_, units)
from tests.test_typed_chain import FakeWriters, build, recovery
from tests.test_typed_units import GuardedLedger

R = GATE_REPEATS


@pytest.fixture
def tmp_path():
    root = Path('/tmp/typed2-neutral')
    root.mkdir(parents=True, exist_ok=True)
    made = Path(tempfile.mkdtemp(prefix='gate-', dir=root))
    try:
        yield made
    finally:
        shutil.rmtree(made, ignore_errors=True)


def counting(services):
    """Wrap the solve: every invocation (one solver request in the fake solve) by (unit, item, mount arm, tag)."""
    seen, real = Counter(), services.solve_fn

    def solve(bench, item, mounted, **kwargs):
        seen[(kwargs['unit'], item['task_id'], mounted['arm'], kwargs['tag'])] += 1
        return real(bench, item, mounted, **kwargs)
    services.solve_fn = solve
    return seen


def decision_records(chain_dir):
    """Every stored gate record of the chain: noise, no-harm checks, card rounds and programs with a gate."""
    found = []
    for path in sorted(Path(chain_dir).glob('s[0-9]*/decisions.json')):
        doc = json.loads(path.read_text())
        found.append(doc['noise'])
        found += [check for check in doc['typing']['no_harm']]
        found += [row for row in doc['cards'] + doc['programs'] if 'per_item' in row]
    return found


def plans(chain_dir):
    return {str(p.relative_to(chain_dir)): p.read_bytes() for p in sorted(Path(chain_dir).rglob('plan.json'))}


# ---- module placement and the exact forms ---------------------------------------------------------------------
def test_gates_reexports_the_repeat_statistics_and_keeps_the_read_side_functions():
    for name in ('REPEAT_SEP', 'repeat_labels', 'arm_of_label', 'repeat_of_label', 'arm_runs', 'repeat_statistics',
                 'calibration', 'card_decision', 'program_decision', 'no_harm_decision', 'recompute', 'UndecidableRuns'):
        assert getattr(gates, name) is getattr(gatestats, name), name
    assert callable(gates.paired_statistics) and callable(gates.split_pairs) and callable(gates.noise_threshold)
    assert not hasattr(gates, '_summary')  # the typed-v1 decision helpers are gone


def test_integer_forms_through_gates_equal_the_D5_formulas():
    """A compact property check through the re-exported names (the full one is tests/test_typed_gate_stats.py)."""
    import random
    from fractions import Fraction
    rng = random.Random(512)
    for _ in range(300):
        n, items = rng.randint(1, 12), None
        items = ['i%d' % i for i in range(n)]
        sb = {i: rng.randint(0, R) for i in items}
        sk = {i: rng.randint(0, R) for i in items}
        base = {'sums': sb, 'squares': dict(sb), 'unknown': 0}
        cand = {'sums': sk, 'squares': dict(sk), 'unknown': 0}
        stats = gates.repeat_statistics(base, cand, items=items, repeats=R, minimum_points=3.0, multiplier=2.0)
        mean = sum(Fraction(sk[i] - sb[i], R) for i in items) / n * 100
        s2 = sum(Fraction(R * sb[i] - sb[i] ** 2, R * (R - 1)) for i in items)
        se2 = 2 * s2 / (R * n * n) * 10000  # (100 * se)^2 of D5
        reaches = mean >= 3 and (mean >= 0) and mean * mean >= 4 * se2
        no_regress = mean >= -3 or mean >= 0 or mean * mean <= 4 * se2
        assert stats['reaches'] == reaches and stats['no_regress'] == no_regress
        card = gates.card_decision(stats)
        assert card['accepted'] == (reaches and stats['better'] > stats['worse']) and gates.recompute(card) == card


# ---- the chain ---------------------------------------------------------------------------------------------------
def test_every_stored_decision_is_reproduced_by_recompute_and_runs_stay_within_R(tmp_path):
    """The fake chain through two benches with a merge, an accepted card, a revision round and programs: every
    noise, no-harm, card and program record equals its ``gates.recompute``; every gate unit sends exactly R requests
    per gate item for its arm (no re-run here); a shared arm's unit runs no gate cell; read units run once per item."""
    services, modules, script = build(tmp_path, order=('searchqa', 'officeqa'), proposals={'searchqa': ['p-sq-1']})
    seen = counting(services)
    state = chain.run(tmp_path, 'G', services=services, sleep=lambda s: None)
    assert state['complete'], state['paused']
    chain_dir = tmp_path / 'G'
    records = decision_records(chain_dir)
    assert {r['kind'] for r in records} == {'noise', 'no_harm', 'card', 'program'}
    for record in records:
        assert chain.recompute_decision(record) == record
        assert record['excluded_unknown' if record['kind'] != 'noise' else 'unknown_final'] == 0
    for path in chain_dir.rglob('decision.json'):  # the unit copies too
        stored = json.loads(path.read_text())
        if 'per_item' in stored:
            assert gates.recompute(stored) == stored
    per_arm = Counter()
    for (unit, item, arm, tag), count in seen.items():
        assert count == 1  # every cell ran once: no re-run in this scenario
        per_arm[(unit, arm)] += 1
    for plan_path in chain_dir.rglob('plan.json'):
        plan = json.loads(plan_path.read_text())
        ran = per_arm.get((plan['unit'], plan['arm']), 0)
        if plan['shared_from'] is None:
            assert ran >= len(plan['items']) * R  # outcomes units add their single-run learn cells under the same arm
            gate_cells = [c for c in (chain_dir / plan['unit'] / 'cells').glob('*.json')
                          if '#' in json.loads(c.read_text())['arm']]
            assert len(gate_cells) == len(plan['items']) * R
        else:
            labels = {json.loads(c.read_text())['arm'] for c in (chain_dir / plan['unit'] / 'cells').glob('*.json')} \
                if (chain_dir / plan['unit'] / 'cells').is_dir() else set()
            assert not any('#' in label for label in labels)  # a shared arm runs no gate cell
    # reads: one cell per panel item, bare labels, never a repeat
    for unit, item, arm, tag in seen:
        if unit.startswith('read-') or 'read-' in unit:
            raise AssertionError('the fake reads of this file never solve')
    d1 = json.loads((chain_dir / 's1' / 'decisions.json').read_text())
    assert [a['unit'] for a in d1['gate']['arms']][:2] == ['s1/noise', 's1/outcomes'] and d1['gate']['repeats'] == R
    assert d1['gate']['arms'][1]['shared_from'] == {'unit': 's1/noise', 'arm': 'B'}  # case (b): a new type, F = B
    d2 = json.loads((chain_dir / 's2' / 'decisions.json').read_text())
    check = d2['typing']['no_harm'][0]
    assert check['baseline'] == {'unit': 's2/noise', 'arm': 'B', 'shared_from': None}  # case (a): B@noise
    outcomes_arm = [a for a in d2['gate']['arms'] if a['unit'] == 's2/outcomes'][0]
    assert outcomes_arm['shared_from'] == {'unit': 's2/noharm-t01', 'arm': 'F'}  # case (c): the merged source's F


def test_read_units_still_run_once_per_item_with_bare_labels(tmp_path):
    state = smoke.run(tmp_path / 'run', 'G', fake=True, sleep=lambda s: None)
    assert state['complete'], state['paused']
    chain_dir = tmp_path / 'run-smoke' / 'G'
    reads = [p for p in chain_dir.iterdir() if p.name.startswith('practice-read-')]
    assert len(reads) == 35
    for unit in reads:
        cells = [json.loads(p.read_text()) for p in (unit / 'cells').glob('*.json')]
        assert len(cells) == 2 and len({c['item_id'] for c in cells}) == 2  # the smoke panel: 2 items, one cell each
        assert all('#' not in c['arm'] and c.get('repeat') is None for c in cells)
    # every learning-side gate cell of the smoke carries its repeat through the label
    noise = [json.loads(p.read_text()) for p in (chain_dir / 's1' / 'noise' / 'cells').glob('*.json')]
    assert sorted(gates.repeat_of_label(c['arm']) for c in noise) == [1, 1, 1, 2, 2, 2, 3, 3, 3]


def test_a_model_side_unknown_run_scores_zero_and_is_never_run_again(tmp_path):
    """Addendum O1: one card-round repeat answers with an unscorable token (a final model-side verdict): the gate
    decides with it scored 0 and counted in unknown_final; the cell is never re-run, also not after a later pause and
    the owner's recovery."""
    def outcome(bench, item_id, mounted):
        if mounted.get('arm') == 'cand_card' and item_id == 'searchqa-g1' and mounted.get('repeat') == 2:
            return 'unknown_artifact'
        return 'pass' if mounted.get('card_text') else 'fail'
    crash = {'on': True}
    writers = FakeWriters(proposals={'searchqa': ['p-1']})
    real_propose = writers.propose_programs

    def propose(**kw):  # a pause after the card gate: the programs writer fails once
        if crash['on']:
            raise RuntimeError('writer down')
        return real_propose(**kw)
    writers.propose_programs = propose
    services, modules, script = build(tmp_path, order=('searchqa',), writers=writers, scripted={'outcomes': outcome})
    seen = counting(services)
    state = chain.run(tmp_path, 'G', services=services, sleep=lambda s: None)
    assert state['paused']['reason'] == 'exception:RuntimeError' and state['paused']['unit'] == 's1/programs'
    decision = json.loads((tmp_path / 'G' / 's1' / 'card-r1' / 'decision.json').read_text())
    assert decision['accepted'] and decision['unknown_final'] == {'baseline': 0, 'candidate': 1}
    assert decision['per_item'][1] == ['searchqa-g1', 0, 2] and decision['excluded_unknown'] == 0
    key = [k for k in seen if k[0] == 's1/card-r1' and k[1] == 'searchqa-g1']
    assert len(key) == R and all(seen[k] == 1 for k in key)
    before = dict(seen)
    crash['on'] = False
    recovery(tmp_path)
    state = chain.run(tmp_path, 'G', services=services, resume=True, sleep=lambda s: None)
    assert state['complete'], state['paused']
    assert all(seen[k] == before[k] for k in before if k[0] == 's1/card-r1')  # nothing of the gate ran again
    assert not (tmp_path / 'G' / 's1' / 'card-r1' / 'rerun').exists()


def test_an_infrastructure_unknown_gate_cell_pauses_is_rerun_once_archived_and_counted(tmp_path):
    """DESIGN 3.4 "Cells": a transport failure of one card-round repeat leaves the arm undecidable: the done marker is
    archived and the chain pauses ``gate_cells_unknown``; the recovery re-runs exactly that cell (archived under
    rerun/), the decision counts it per arm, and every other unit keeps its cells."""
    broken = {'on': True}

    def solver(system, user):
        return 'The answer is 42.'
    services, modules, script = build(tmp_path, order=('searchqa',), scripted={'replies': {'solver': solver}})
    real = services.solve_fn

    def solve(bench, item, mounted, **kwargs):
        row = real(bench, item, mounted, **kwargs)
        if broken['on'] and kwargs['unit'] == 's1/card-r1' and item['task_id'] == 'searchqa-g0' \
                and kwargs['tag'] == units.cell_tag(bench, 'searchqa-g0', 'cand_card#3'):
            row.update(correct=None, infrastructure_unknown=True, token='unknown_transport')
        return row
    services.solve_fn = solve
    seen = counting(services)
    state = chain.run(tmp_path, 'G', services=services, sleep=lambda s: None)
    assert state['paused']['reason'] == 'gate_cells_unknown' and state['paused']['unit'] == 's1/card-r1'
    unit = tmp_path / 'G' / 's1' / 'card-r1'
    assert not (unit / 'done.json').exists() and (unit / 'done-stopped-1.json').exists()
    assert not (unit / 'decision.json').exists()
    broken['on'] = False
    recovery(tmp_path)
    state = chain.run(tmp_path, 'G', services=services, resume=True, sleep=lambda s: None)
    assert state['complete'], state['paused']
    tag = units.cell_tag('searchqa', 'searchqa-g0', 'cand_card#3')
    assert [p.name for p in (unit / 'rerun').glob('*.json')] == [tag + '-1.json']
    assert seen[('s1/card-r1', 'searchqa-g0', 'cand_card', tag)] == 2  # the one archived infrastructure re-run
    assert all(count == 1 for key, count in seen.items() if key[3] != tag)
    decision = json.loads((unit / 'decision.json').read_text())
    assert decision['reruns'] == {'baseline': 0, 'candidate': 1} and gates.recompute(decision) == decision


def interrupt_once(services, unit_name):
    """Raise KeyboardInterrupt (SIGINT) inside the first solver call of ``unit_name``: the unit's first cell runs
    serially in the calling thread, the main thread, where SIGINT lands. Returns the record of the fired call."""
    fired, real = {}, services.solver_call

    def solver_call(bench, unit, tag, *, transform=None, purpose='solve'):
        recorder = real(bench, unit, tag, transform=transform, purpose=purpose)
        inner = recorder.client_call

        def call(system, user):
            if not fired and unit == unit_name and purpose == 'solve':
                fired.update(tag=tag, main=threading.current_thread() is threading.main_thread())
                raise KeyboardInterrupt()
            return inner(system, user)
        recorder.client_call = call
        return recorder
    services.solver_call = solver_call
    return fired


@pytest.mark.parametrize('unit', ['s1/card-r1', 's1/noise'])
def test_a_sigint_inside_a_gate_cell_is_sent_again_and_counted_as_a_rerun(tmp_path, unit):
    """fix-b (review rb-resume 1): SIGINT, the documented way to stop a chain (F7), lands in the main thread while it
    is inside a unit's first (serial) cell. The interrupted call stays pending in the ledger, the owner's recovery
    resumes, the cell is sent again (R + 1 requests for that item and label), and the decision or noise record counts
    that re-run (it said 0 before the fix)."""
    services, modules, script = build(tmp_path, order=('searchqa',), proposals={'searchqa': ['p-sq-1']})
    fired = interrupt_once(services, unit)
    seen = counting(services)
    with pytest.raises(KeyboardInterrupt):
        chain.run(tmp_path, 'G', services=services, sleep=lambda s: None)
    assert fired['main']
    ledger = json.loads((tmp_path / 'G' / 'ledger.json').read_text())
    assert [(e['unit'], e['cell']) for e in ledger['pending'].values()] == [(unit, fired['tag'])]
    assert ledger['stop_reason'] == 'interrupted'
    recovery(tmp_path)
    state = chain.run(tmp_path, 'G', services=services, resume=True, sleep=lambda s: None)
    assert state['complete'], state['paused']
    assert [count for key, count in seen.items() if key[0] == unit and key[3] == fired['tag']] == [2]
    assert all(count == 1 for key, count in seen.items() if key[3] != fired['tag'])
    decisions = json.loads((tmp_path / 'G' / 's1' / 'decisions.json').read_text())
    if unit == 's1/noise':
        assert decisions['noise']['reruns'] == 1
        assert json.loads((tmp_path / 'G' / 's1' / 'noise' / 'noise.json').read_text())['reruns'] == 1
    else:
        card = decisions['cards'][0]
        assert card['reruns'] == {'baseline': 0, 'candidate': 1} and gates.recompute(card) == card
    recovered = json.loads((tmp_path / 'G' / 'ledger.json').read_text())['recovered']
    assert [(row['unit'], row['cell']) for row in recovered] == [(unit, fired['tag'])]


@pytest.mark.parametrize('purpose, calls_file', [
    ('card_writer', 'writer-card_writer.json'), ('describer', 'describe-card-t01-s1-describer.json')])
def test_a_resumed_card_writer_or_describer_keeps_every_earlier_send_in_its_calls_file(tmp_path, purpose, calls_file):
    """fix-b (review rb-resume 2), DESIGN 3.3: the card writer and the describer of a unit that paused inside their
    call start again with a new recorder on the same calls file; every send of every attempt stays in that file (the
    interrupted one first), as for the program writer (``_keep_earlier_sends``), and as the ledger counted them."""
    services, modules, script = build(tmp_path, order=('searchqa',), proposals={'searchqa': ['p-sq-1']})
    broken, real = {'on': True}, services.role_call

    def role_call(role, unit, tag, max_tokens):
        recorder = real(role, unit, tag, max_tokens)
        inner = recorder.client_call

        def call(system, user):
            if broken['on'] and role == purpose and unit == 's1/card-r1':
                broken['on'] = False
                raise RuntimeError('role connection lost')
            return inner(system, user)
        recorder.client_call = call
        return recorder
    services.role_call = role_call
    state = chain.run(tmp_path, 'G', services=services, sleep=lambda s: None)
    assert state['paused']['reason'] == 'exception:RuntimeError' and state['paused']['unit'] == 's1/card-r1'
    path = tmp_path / 'G' / 's1' / 'card-r1' / 'calls' / calls_file
    first = json.loads(path.read_text())
    assert len(first) == 1 and first[0]['receipt'] is None and first[0]['exception'] == 'RuntimeError'
    recovery(tmp_path)
    state = chain.run(tmp_path, 'G', services=services, resume=True, sleep=lambda s: None)
    assert state['complete'], state['paused']
    every = json.loads(path.read_text())
    assert len(every) == 2 and every[0] == first[0] and every[1]['receipt']['ok'] is True
    assert every[1]['request_sha256'] == first[0]['request_sha256']    # the same request, sent again
    assert len({send['logical_call'] for send in every}) == 2
    calls = json.loads((tmp_path / 'G' / 'ledger.json').read_text())['by_unit']['s1/card-r1']['calls']
    cells = len(list((tmp_path / 'G' / 's1' / 'card-r1' / 'cells').glob('*.json')))
    assert calls == cells + 3   # one send per gate cell, then 2 + 1 sends of the writer and the describer


def test_parallel_read_units_and_learning_units_touch_rerun_entries_only_under_the_lock(tmp_path, monkeypatch):
    """fix-b (review rb-resume 3): a whole fake chain with the REAL read units (five panels of an event side by side
    in the read pool; two benches here) and learning units, on a guarded ledger whose rerun set refuses any access
    without the ledger's lock (``tests/test_typed_units.py``): the chain completes, so no unit marks, reads or consumes
    a rerun entry unlocked (before the fix the read units' and the learning units' consumption did)."""
    monkeypatch.setattr(units, 'Ledger', GuardedLedger)
    services = smoke.fake_services(tmp_path, 'G', smoke.synthetic_manifest())
    services.order = ('searchqa', 'zebralogic')
    services.slices = smoke.smoke_slices(services.items, services.slices)
    services.limits = dict(smoke.SMOKE_LIMITS)
    state = chain.run(tmp_path, 'G', services=services, sleep=lambda s: None)
    assert state['complete'], state['paused']
    assert isinstance(services.ledger, GuardedLedger) and 'read-S2-zebralogic' in state['done_units']


def test_shared_arms_run_no_cell_and_plan_json_is_identical_after_a_resume(tmp_path):
    """Case (e): after an accepted card, outcomes-card's F is the accepted round's cand_card (no gate cell, the
    program baseline is those runs: baseline_selected, O5); the resumed step recomputes every plan and finds it
    byte-identical; a changed plan pauses ``gate_plan_changed``."""
    crash = {'on': True}
    writers = FakeWriters(proposals={'searchqa': ['p-sq-1']})
    real_propose = writers.propose_programs

    def propose(**kw):
        if crash['on']:
            raise RuntimeError('writer down')
        return real_propose(**kw)
    writers.propose_programs = propose
    services, modules, script = build(tmp_path, order=('searchqa',), writers=writers)
    state = chain.run(tmp_path, 'G', services=services, sleep=lambda s: None)
    assert state['paused']['unit'] == 's1/programs'
    chain_dir = tmp_path / 'G'
    before = plans(chain_dir)
    assert sorted(before) == ['s1/card-r1/plan.json', 's1/noise/plan.json', 's1/outcomes-card/plan.json',
                              's1/outcomes/plan.json']
    card_plan = json.loads(before['s1/outcomes-card/plan.json'])
    assert card_plan['shared_from'] == {'unit': 's1/card-r1', 'arm': 'cand_card'} and card_plan['repeats'] == R
    assert [c['equal'] for c in card_plan['compared']] == [False, False, True]
    labels = {json.loads(p.read_text())['arm'] for p in (chain_dir / 's1' / 'outcomes-card' / 'cells').glob('*.json')}
    assert labels == {'F'}  # learn cells only
    crash['on'] = False
    recovery(tmp_path)
    state = chain.run(tmp_path, 'G', services=services, resume=True, sleep=lambda s: None)
    assert state['complete'], state['paused']
    after = plans(chain_dir)
    assert {k: v for k, v in after.items() if k in before} == before  # byte-identical after the resume
    program = json.loads((chain_dir / 's1' / 'decisions.json').read_text())['programs'][0]
    assert program['baseline'] == {'unit': 's1/outcomes-card', 'arm': 'F',
                                   'shared_from': {'unit': 's1/card-r1', 'arm': 'cand_card'}}
    assert program['baseline_selected'] is True
    # a changed plan pauses before any cell
    other = tmp_path / 'other'
    crash['on'] = True
    services2, _, _ = build(other, order=('searchqa',), writers=writers)
    assert chain.run(other, 'G', services=services2, sleep=lambda s: None)['paused']['unit'] == 's1/programs'
    path = other / 'G' / 's1' / 'outcomes-card' / 'plan.json'
    units.write_json(path, {**json.loads(path.read_text()), 'repeats': 2})
    crash['on'] = False
    recovery(other)
    state = chain.run(other, 'G', services=services2, resume=True, sleep=lambda s: None)
    assert state['paused']['reason'] == 'gate_plan_changed' and state['paused']['unit'] == 's1/outcomes-card'


def test_a_round_two_text_equal_to_round_one_is_the_earlier_arm(tmp_path):
    """Case (f): a revision that writes round 1's text again is the same arm: no gate cell, the same statistics,
    rejected again."""
    writers = FakeWriters(card_text=lambda bench, r: '- the same card\n')
    services, modules, script = build(tmp_path, order=('searchqa',), writers=writers,
                                      scripted={'outcomes': lambda bench, item_id, mounted: 'fail'})
    services.limits = dict(chain.DEFAULT_LIMITS)
    state = chain.run(tmp_path, 'G', services=services, sleep=lambda s: None)
    assert state['complete'], state['paused']
    rounds = json.loads((tmp_path / 'G' / 's1' / 'decisions.json').read_text())['cards']
    assert [(r['round'], r['accepted'], r['reason']) for r in rounds] == [(1, False, 'gain_below_tau'),
                                                                        (2, False, 'gain_below_tau')]
    assert rounds[1]['candidate_arm']['shared_from'] == {'unit': 's1/card-r1', 'arm': 'cand_card'}
    assert rounds[1]['cells'] == 0 and rounds[1]['per_item'] == rounds[0]['per_item']
    assert not (tmp_path / 'G' / 's1' / 'card-r2' / 'cells').exists()


def test_shared_arm_mismatch_pauses(tmp_path):
    """An identity that claims two arms are equal while the earlier arm's rows recorded another system card is a
    defect, never a silent reuse: the chain pauses ``shared_arm_mismatch``."""
    services, modules, script = build(tmp_path, order=('searchqa',))
    real = services.identity_fn
    services.identity_fn = lambda bench, item, **kw: {**real(bench, item, **kw), 'system_card_sha256': 'x' * 64}
    state = chain.run(tmp_path, 'G', services=services, sleep=lambda s: None)
    assert state['paused']['reason'] == 'shared_arm_mismatch' and state['paused']['unit'] == 's1/outcomes'


def test_no_harm_returns_the_stored_record_on_resume(tmp_path):
    """A resumed typing unit reads each no-harm decision it stored (never a recomputation); its gate arm and plan
    are found again."""
    services, modules, script = build(tmp_path, order=('searchqa', 'officeqa'))
    real_freeze, fail = typing_.TypeMap.freeze, {'on': True}

    def freeze(self, path, *, step):
        if fail['on'] and str(path).endswith('s2/typing/typemap.json'):
            fail['on'] = False
            raise RuntimeError('disk full')
        return real_freeze(self, path, step=step)
    typing_.TypeMap.freeze = freeze
    try:
        state = chain.run(tmp_path, 'G', services=services, sleep=lambda s: None)
        assert state['paused']['reason'] == 'exception:RuntimeError' and state['paused']['unit'] == 's2/noharm-t01'
        path = tmp_path / 'G' / 's2' / 'noharm-t01' / 'decision.json'
        stored = json.loads(path.read_text())
        units.write_json(path, {**stored, 'stored_marker': 'kept'})
        plan = (tmp_path / 'G' / 's2' / 'noharm-t01' / 'plan.json').read_bytes()
        recovery(tmp_path)
        state = chain.run(tmp_path, 'G', services=services, resume=True, sleep=lambda s: None)
    finally:
        typing_.TypeMap.freeze = real_freeze
    assert state['complete'], state['paused']
    typing = json.loads((tmp_path / 'G' / 's2' / 'typing' / 'typing.json').read_text())
    assert typing['no_harm'][0]['stored_marker'] == 'kept' and typing['no_harm'][0]['merge']
    assert (tmp_path / 'G' / 's2' / 'noharm-t01' / 'plan.json').read_bytes() == plan


# ---- rerun entries per (unit, tag) --------------------------------------------------------------------------------
def build_ok(bench, item, arm, tag):
    return {'bench': bench, 'item_id': item['task_id'], 'arm': arm, 'correct': True, 'failure': None,
            'configuration_error': False, 'infrastructure_unknown': False, 'tokens': 1,
            'sends': [{'receipt': {'ok': True, 'response': 'x'}}]}


def test_a_recovered_call_reruns_its_own_unit_cell_once_and_never_a_cell_of_another_unit(tmp_path):
    """DESIGN 3.4: a label such as F#2 recurs in several units of a step and a cell tag does not name its unit. The
    ledger's recovered entry (unit A, tag) re-runs that cell in unit A once (the entry is consumed), and never the
    finished cell with the same tag of unit B (the double fault of DESIGN section 5)."""
    ledger = units.Ledger(tmp_path / 'ledger.json', 10 ** 9)
    item = {'task_id': 'searchqa-0', 'public': {}}
    tag = units.cell_tag('searchqa', 'searchqa-0', 'F#2')
    for name in ('a', 'b'):  # both units hold a finished F#2 cell of the item (unit directories without done.json)
        units.write_json(tmp_path / name / 'cells' / (tag + '.json'), build_ok('searchqa', item, 'F#2', tag))
    key, _ = ledger.before_send('s', 'u', 10, cell=tag, unit='s1/a')  # an interrupted call of unit a
    resumed = units.Ledger(tmp_path / 'ledger.json', 10 ** 9, resume=True)
    assert resumed.rerun_cells == {('s1/a', tag)}
    ran = []

    def build_cell(bench, it, arm, t):
        ran.append(arm)
        return build_ok(bench, it, arm, t)
    jobs = [('searchqa', item, ('F#1', 'F#2', 'F#3'))]
    units.run_unit(tmp_path / 'b', jobs, unit='s1/b', widths={'searchqa': 1}, build_cell=build_cell, ledger=resumed,
                   resume=True)
    assert sorted(ran) == ['F#1', 'F#3'] and resumed.rerun_cells == {('s1/a', tag)}  # b's finished F#2 kept
    ran.clear()
    units.run_unit(tmp_path / 'a', jobs, unit='s1/a', widths={'searchqa': 1}, build_cell=build_cell, ledger=resumed,
                   resume=True)
    assert sorted(ran) == ['F#1', 'F#2', 'F#3'] and resumed.rerun_cells == set()  # consumed on re-run
    (tmp_path / 'a' / 'done.json').unlink()  # a later re-entry of unit a (e.g. after another pause)
    ran.clear()
    units.run_unit(tmp_path / 'a', jobs, unit='s1/a', widths={'searchqa': 1}, build_cell=build_cell, ledger=resumed,
                   resume=True)
    assert ran == []  # the entry was consumed: the finished cell is never drawn again
    with pytest.raises(ValueError):
        units.run_unit(tmp_path / 'c', jobs, unit='', widths={}, build_cell=build_cell, ledger=resumed)


def test_a_model_side_unknown_cell_is_never_marked_for_rerun(tmp_path):
    ledger = units.Ledger(tmp_path / 'ledger.json', 10 ** 9)
    item = {'task_id': 'searchqa-0'}
    model_side = {**build_ok('searchqa', item, 'F#1', 't1'), 'correct': None, 'token': 'unknown_artifact'}
    infra = {**build_ok('searchqa', item, 'F#2', 't2'), 'correct': None, 'infrastructure_unknown': True}
    units.write_json(tmp_path / 'u' / 'cells' / 't1.json', model_side)
    units.write_json(tmp_path / 'u' / 'cells' / 't2.json', infra)
    assert units.mark_infrastructure_reruns(tmp_path / 'u', ledger, unit='s1/u') == ['t2']
    assert ledger.rerun_cells == {('s1/u', 't2')} and (tmp_path / 'u' / 'cells' / 't1.json').exists()
    assert units.reruns_of(tmp_path / 'u', ['t1', 't2']) == 1
