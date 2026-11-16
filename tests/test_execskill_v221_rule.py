"""Authored counts and fake-worker request identities; no benchmark file or model."""
from contextlib import contextmanager
from copy import deepcopy
from fractions import Fraction
import functools
from types import SimpleNamespace

import pytest

from skillopt.execskill import acceptance as a, audit, engineer, engineer_v221, profiles as p, reuse, stats_ext, v221_rule as rule, zebralogic
from skillopt.execskill.package import empty, with_
from tests.execskill_fakes_env import FakeSandbox, procedure
from tests.execskill_v293_fakes import tmp_path  # noqa: F401
from tests.test_execskill_acceptance import make_cells
from tests.test_execskill_zpc_pipeline import offline  # noqa: F401


@pytest.fixture(autouse=True)
def authored_statistics(monkeypatch):
    monkeypatch.setattr(stats_ext, 'bootstrap_ci', functools.partial(stats_ext.bootstrap_ci, resamples=40))
    monkeypatch.setattr(stats_ext, 'signflip', functools.partial(stats_ext.signflip, n=128))


def paired(fixed, broken, tied=0, runs=1):
    ids = ['authored-%03d' % i for i in range(fixed + broken + tied)]
    cells = {}
    for i, key in enumerate(ids):
        cells[("S'", key)] = [{'judge': {'v2': {'token': 'pass' if i < fixed else 'fail'}}}] * runs
        cells[('S', key)] = [{'judge': {'v2': {'token': 'pass' if fixed <= i < fixed + broken else 'fail'}}}] * runs
    return ids, cells


@pytest.mark.parametrize('touched,fixed,broken,batch,decision,floor', [
    (38, 17, 21, 951, 'reject', 4), (32, 21, 11, 1000, 'accept', 4),
    (2, 2, 0, 100, 'reject', 3), (100, 40, 5, 100, 'accept', 10),
    (17, 10, 7, 100, 'reject', 3), (5, 4, 1, 100, 'accept', 3),
    (0, 0, 0, 100, 'reject', 3)])
def test_worked_counts_and_exact_harm_ratio(touched, fixed, broken, batch, decision, floor):
    got = rule.counts(touched=touched, fixed=fixed, broken=broken, batch=batch)
    assert got['decision'] == decision and got['gain_floor'] == floor
    assert got['net'] == fixed - broken and got['harm_cap'] == float(Fraction(2, 3) * fixed)
    assert got['constants'] == {'GAIN_MIN_ITEMS': 3, 'GAIN_MIN_SHARE': .1,
                               'HARM_RATIO': '2/3', 'WHOLE_BATCH_FLOOR': -.01}
    assert rule.rule_ok(got)


@pytest.mark.parametrize('whole,decision', [(Fraction(-1, 100), 'accept'), (Fraction(-11, 1000), 'reject')])
def test_whole_batch_floor_is_inclusive_and_recorded(whole, decision):
    assert rule.counts(touched=10, fixed=8, broken=2, batch=100, whole_batch=whole)['decision'] == decision


def test_the_same_record_at_training_confirmation_and_acceptance_and_untouched_zero():
    ids, cells = paired(21, 11, 968)
    touched = ids[:32]
    # Same-text solver noise on untouched items cannot change any of the counts.
    cells[("S'", ids[-1])][0]['judge']['v2']['token'] = 'pass'
    records = [rule.decide(cells, ids, touched=touched) for _ in ('training', 'confirmation', 'acceptance')]
    assert records[0] == records[1] == records[2] == rule.counts(touched=32, fixed=21, broken=11, batch=1000)
    changes = rule.item_changes(cells, ids, touched=touched)
    assert len(changes['untouched']) == 968 and changes['deltas'][ids[-1]] == 0


def test_repeated_runs_count_items_and_keep_whole_batch_guard():
    cells = {("S'", 'a'): ['pass', 'fail'], ('S', 'a'): ['fail', 'fail'],
             ("S'", 'b'): ['pass', 'pass'], ('S', 'b'): ['pass', 'fail']}
    got = rule.decide(cells, ['a', 'b'], touched=['a', 'b'])
    assert got['fixed'] == 2 and got['net'] == 2 and got['whole_batch'] == .5
    assert got['decision'] == 'reject'  # Two items cannot meet the minimum three.


@pytest.mark.parametrize('bench', ['searchqa', 'officeqa', 'zebralogic', 'spreadsheetbench'])
def test_request_bytes_and_post_call_identity_define_touched_not_predicates_or_faults(bench):
    base = {'request_sha256': 'a' * 64, 'post_call': [], 'faults': [], 'enabled': []}
    pairs = {'same': {'S': base, "S'": dict(base, enabled=['p'])},
             'changed': {'S': base, "S'": dict(base, request_sha256='b' * 64)},
             'post': {'S': base, "S'": dict(base, post_call=[{'hook': 'second'}])},
             'fault': {'S': base, "S'": dict(base, faults=[{'kind': 'authored'}])}}
    assert rule.identity_touched(pairs, bench=bench) == ['changed', 'post']
    assert not reuse.interchangeable(pairs['fault']['S'], pairs['fault']["S'"], bench=bench)


def test_incomplete_identity_cannot_silently_become_untouched():
    with pytest.raises(ValueError, match='complete request identities'):
        rule.identity_touched({'x': {'S': {}, "S'": {}}}, bench='searchqa')


@pytest.mark.parametrize('fields,repair,expected_note,expected_touch', [
    ({}, False, False, False), ({'facts': ['The public execution report was inspected.']}, False, False, False),
    ({}, True, False, True), ({'facts': ['The public execution report was inspected.']}, True, True, True)])
def test_actual_sheet_cell_records_silent_callback_separately_from_request_effects(
        tmp_path, monkeypatch, fields, repair, expected_note, expected_touch):
    from dataclasses import replace
    from skillopt.execskill import cells, instruction_start, policy, solver
    from tests.test_execskill_cells import (_Client, _context, _reply, _cell, _sheet, PROGRAM, REPAIRED,
                                          DELIVERED, PASSED, package)
    from tests.fixtures.execskill.items import spreadsheetbench_items
    proc = procedure('fx-callback', ('applies', 'sheet_feedback'), origin='spreadsheetbench',
                     requests_second_call=True, policy_version=policy.POLICY_VERSION_V29)
    candidate = package(proc)
    hooks = {proc.id: {'applies': lambda view: True,
                      'sheet_feedback': lambda *args: {'fields': fields, 'request_repair': repair}}}
    _sheet(monkeypatch, [DELIVERED], [PASSED])
    client = _Client(*[_reply(text) for text in ([PROGRAM, REPAIRED] if repair else [PROGRAM])])
    ctx = replace(_context(tmp_path, client, worker=lambda bench: FakeSandbox(hooks)), configuration=p.MAIN_V7,
                  cards={bench: row['text'] for bench, row in instruction_start.pins().items()})
    item = spreadsheetbench_items(tmp_path / 'authored', 1)[0]
    record = cells.run_cell(ctx, _cell(item), item, cells.Arm('candidate', candidate),
                            store=cells.TrainingStore(ctx.attempt))
    effect = record['post_call_effects'][proc.id]
    assert effect == {'procedure_sha256': proc.sha256, 'note_emitted': expected_note, 'repair_requested': repair}
    view = solver.routing_view('spreadsheetbench', item['public'], runtime=ctx.runtime['spreadsheetbench'])
    worker = FakeSandbox(hooks).start(candidate, kind='cell')
    first = reuse.signature('spreadsheetbench', candidate, view, worker, configuration=p.MAIN_V7,
                            card_text=ctx.cards['spreadsheetbench'], runtime=ctx.runtime['spreadsheetbench'])
    worker.close()
    second = reuse.signature('spreadsheetbench', package(), view, None, configuration=p.MAIN_V7,
                             card_text=ctx.cards['spreadsheetbench'], runtime=ctx.runtime['spreadsheetbench'])
    assert first['request_sha256'] == second['request_sha256']
    assert first['post_call'] and not second['post_call']
    key = record['task_id']
    pair = {key: {"S'": first, 'S': second}}
    observed = rule.identity_report(pair, bench='spreadsheetbench', trajectories=[record])
    assert observed['callback_active'][key] == {'S': [], "S'": [proc.id]}
    assert observed['request_changed'] == []
    assert observed['touched'] == ([key] if expected_touch else [])
    assert observed['untouched'] == ([] if expected_touch else [key])
    if not expected_touch:
        coverage = rule.coverage(1, observed['touched'], {proc.id: []})
        assert coverage['candidate']['touched'] == coverage['procedures'][proc.id]['touched'] == 0
        # Independent pass/fail variation cannot enter the decision through a silent callback.
        decision = rule.decide({("S'", key): ['pass'], ('S', key): ['fail']}, [key], touched=observed['touched'])
        assert decision['reason'] == 'no_touched_items' and decision['net'] == decision['whole_batch'] == 0
        assert rule.rule_ok(decision)


def test_sheet_callback_presence_without_actual_evidence_is_not_a_touch():
    parent = {'request_sha256': 'a' * 64, 'post_call': []}
    callback = {'hook': 'sheet_feedback', 'procedure': 'p', 'version': 'b' * 64, 'sham': None}
    candidate = dict(parent, post_call=[callback])
    pair = {'authored': {'S': parent, "S'": candidate}}
    assert rule.same_request(candidate, parent)
    assert not rule.identity_touched(pair, bench='spreadsheetbench')
    silent = {'task_id': 'authored', 'arm': "S'", 'post_call_effects': {
        'p': {'procedure_sha256': 'b' * 64, 'note_emitted': False, 'repair_requested': False}}}
    assert not rule.identity_touched(pair, bench='spreadsheetbench', trajectories=[silent])
    active = deepcopy(silent); active['post_call_effects']['p']['repair_requested'] = True
    assert rule.identity_touched(pair, bench='spreadsheetbench', trajectories=[active]) == ['authored']
    stale = deepcopy(active); stale['post_call_effects']['p']['procedure_sha256'] = 'c' * 64
    assert not rule.identity_touched(pair, bench='spreadsheetbench', trajectories=[stale])
    unchanged = {'authored': {'S': candidate, "S'": candidate}}
    assert not rule.identity_touched(unchanged, bench='spreadsheetbench', trajectories=[active])


@pytest.mark.parametrize('note,repair,expected', [(False, False, 'reject'), (True, False, 'accept'),
                                                (False, True, 'accept')])
def test_sheet_acceptance_counts_actual_effects_and_rejects_silent_callback_noise(tmp_path, note, repair, expected):
    from skillopt.execskill import policy
    from tests.test_execskill_replay import SHEET_VIEW
    parent = empty(step='D/s0', evidence='engineering_fixture')
    proc = procedure('fx-callback', ('applies', 'sheet_feedback'), origin='spreadsheetbench',
                     requests_second_call=True, policy_version=policy.POLICY_VERSION_V29)
    candidate = with_(parent, step='D/s1-spreadsheetbench', add=[proc])
    @contextmanager
    def workers(package, item):
        worker = FakeSandbox({proc.id: {'applies': lambda view: True,
            'sheet_feedback': lambda *args: {'fields': {}, 'request_repair': False}}}).start(package, kind='cell')
        try:
            yield worker
        finally:
            worker.close()
    views = {'authored-%d' % i: dict(SHEET_VIEW, instruction='Authored instruction %d.' % i) for i in range(3)}
    sealed = a.prepare(tmp_path, chain='D', bench='spreadsheetbench', step='D/s1-spreadsheetbench',
        unit='D/s1-spreadsheetbench/accept-r1', candidate=candidate, parent=parent, views=views,
        blocks={key: 'b1' for key in views}, workers=workers, trajectories=[], configuration=p.MAIN_V7,
        rule=p.acceptance_rule(p.MAIN_V7, 'spreadsheetbench'), reuse={'card_text': 'Authored card.', 'runtime': {}})
    cells = make_cells(sealed, token=lambda job: 'pass' if job['arm'] == "S'" else 'fail')
    for cell in cells:
        cell['post_call_effects'] = ({proc.id: {'procedure_sha256': proc.sha256,
            'note_emitted': note, 'repair_requested': repair}} if cell['arm'] == "S'" else {})
    found = a.decide(cells, sealed)
    assert found['decision'] == expected
    common = found['gain_and_no_harm']
    assert common['touched'] == common['fixed'] == (0 if expected == 'reject' else 3)
    assert found['touch_evidence']['request_changed'] == []
    assert all(row["S'"] == [proc.id] for row in found['touch_evidence']['callback_active'].values())
    if expected == 'reject':
        assert common['reason'] == 'no_touched_items' and found['untouched_items'] == list(views)


@pytest.mark.parametrize('status,touched', [('exception', 4), ('ok', 0)])
def test_engineer_sheet_coverage_uses_existing_practice_reports_not_callback_registration(status, touched):
    from dataclasses import replace
    from tests.test_execskill_v211_routing import engineer_context
    ctx = replace(engineer_context('spreadsheetbench', n=4), configuration=p.MAIN_V7)
    histories = []
    for trace in ctx.trajectories:
        fields = deepcopy({key: value for key, value in trace.items() if key not in (p.RECORD_HASH, 'version', 'evidence')})
        fields['shell']['precheck']['status'] = status
        histories.append(p.record('trajectory', ctx.evidence, fields))
    ctx = replace(ctx, trajectories=histories, current=histories)
    source = ('def sheet_feedback(view, report, state):\n'
              '    return {"fields": {}, "request_repair": report["status"] == "exception"}\n')
    change = engineer.Change(1, 'new', {'kind': 'new', 'description': 'Inspect public execution reports.',
        'hooks': ['sheet_feedback'], 'requests_second_call': True, 'max_note_chars': 1000,
        'excluded_benches': [bench for bench in p.BENCHES if bench != 'spreadsheetbench'], 'replay_tests': []},
        source, 'a' * 64)
    checked = engineer.check(change, ctx)
    assert checked['coverage']['candidate']['touched'] == touched
    assert checked['coverage']['procedures'][change.procedure.id]['touched'] == touched
    assert checked['inert'] == (touched < 3)


def test_alfworld_touched_requires_changed_procedure_emitted_note_in_either_arm():
    def trace(key, pid, text, arm="S'"):
        return {'bench': 'alfworld', 'arm': arm, 'task_id': key,
                'shell': {'notes': [{'id': pid, 'delivered_text': text}]}}
    traces = [trace('a', 'new', 'Public observation.'), trace('a', 'new', 'Again.'),
              trace('b', 'new', ''), trace('c', 'unchanged', 'Public observation.'),
              trace('d', 'old', 'Removed helper note.', arm='S')]
    assert rule.alfworld_touched(traces, {'new', 'old'}) == ['a', 'd']


def seal(root, *, size=100, touching=None, configuration=None):
    configuration = configuration or p.MAIN_V7
    parent = empty(step='D/s0', evidence='engineering_fixture')
    proc = procedure('p-searchqa-1-1', ('applies', 'before_call'), origin='searchqa')
    candidate = with_(parent, step='D/s1-searchqa', add=[proc])
    table = {proc.id: {'applies': lambda view: True,
             'before_call': lambda view, state: {'facts': ['The public input was inspected.']}
                if touching is None or int(view['question']) in touching else None}}
    @contextmanager
    def workers(package, item):
        worker = FakeSandbox(table).start(package, kind='cell')
        try:
            yield worker
        finally:
            worker.close()
    views = {'authored-%03d' % i: {'question': str(i), 'context': ['A public value.']} for i in range(size)}
    return a.prepare(root, chain='D', bench='searchqa', step='D/s1-searchqa', unit='D/s1-searchqa/accept-r1',
        candidate=candidate, parent=parent, views=views, blocks={key: 'b1' for key in views},
        workers=workers, trajectories=[], configuration=configuration,
        rule=p.acceptance_rule(configuration, 'searchqa'), reuse={'card_text': 'Authored card.', 'runtime': {}})


@pytest.mark.parametrize('touching,fixed,broken,decision', [(38, 17, 21, 'reject'), (32, 21, 11, 'accept'),
    (2, 2, 0, 'reject'), (100, 40, 5, 'accept')])
def test_real_acceptance_uses_common_rule_without_minimum_astar_or_pooled_baseline(tmp_path, touching, fixed, broken, decision):
    sealed = seal(tmp_path, touching=set(range(touching)))
    def token(job):
        i = int(job['item'].rsplit('-', 1)[1])
        good = i < fixed if job['arm'] == "S'" else fixed <= i < fixed + broken if job['arm'] == 'S' else False
        return 'pass' if good else 'fail'
    found = a.decide(make_cells(sealed, token=token), sealed)
    assert found['decision'] == decision
    assert found['gain_and_no_harm'] == rule.counts(touched=touching, fixed=fixed, broken=broken, batch=100)
    assert found['guards']['J1']['rule'] == rule.NAME and found['guards']['J2'] == {'removed': True}
    assert found['guards']['J7_meta'] == {'not_applicable': True}
    assert found['untouched_contribution'] == 0 and len(found['untouched_items']) == 100 - touching
    assert not any(job['arm'].startswith(('withhold', 'restore', 'P_')) for jobs in a.schedule(sealed).values() for job in jobs)


@pytest.mark.parametrize('guard', ['J3', 'J4', 'J5', 'J6'])
def test_registered_guards_are_computed_stored_and_never_decide_or_pause(tmp_path, guard):
    sealed = seal(tmp_path, size=12)
    cells = make_cells(sealed, token=lambda job: 'pass' if job['arm'] == "S'" or guard == 'J6' and job['arm'] == 'C' else 'fail',
        violation=lambda job: guard == 'J4' and job['arm'] == "S'",
        faults=lambda job: [{'procedure': 'p-searchqa-1-1', 'hook': 'before_call', 'kind': 'output_shape'}]
            if guard == 'J3' and job['arm'] == "S'" else [],
        flags=lambda job: ['reasoning_mismatch'] if guard == 'J5' else [])
    found = a.decide(cells, sealed)
    key = {'J4': 'J4_items', 'J6': 'J6_dup'}.get(guard, guard)
    assert found['decision'] == 'accept' and not found['guards'][key]['ok']
    assert found['guards'][key]['informational'] and guard in found['diagnostic_warnings']
    assert found['guards']['J5']['pause'] is False


def test_one_item_acceptance_rejects_by_gain_floor_without_statistics_pause(tmp_path):
    sealed = seal(tmp_path, size=1)
    found = a.decide(make_cells(sealed, token=lambda job: 'pass' if job['arm'] == "S'" else 'fail'), sealed)
    assert found['decision'] == 'reject' and found['gain_and_no_harm']['touched'] == 1
    assert found['contrasts']["S'-S"]['unavailable'] == 'too_few_answered_units_for_descriptive_t_test'
    assert found['guards']['J5']['pause'] is False


def finding(*, g='false', d='false', policy=None):
    return {'kind': 'note', 'procedure': 'p', 'verdict': policy or 'P1',
            'judges': {'G': {'truth': g, 'policy': policy or 'ok'},
                       'D': {'truth': d, 'policy': policy or 'ok'}}}


@pytest.mark.parametrize('g,d,fixed,broken,removed', [('false', 'false', 3, 1, []),
    ('false', 'false', 2, 2, []), ('false', 'false', 1, 2, ['p']),
    ('false', 'unverifiable', 1, 2, []), ('unverifiable', 'unverifiable', 0, 4, [])])
def test_audit_drop_requires_both_untrue_and_own_confirmation_net_harm(g, d, fixed, broken, removed):
    result = {'confirmed': [finding(g=g, d=d)]}
    own = {'p': {'fixed': fixed, 'broken': broken}}
    assert audit.removed_procedures(result, ['p'], configuration=p.MAIN_V7, confirmation=own) == removed
    assert audit.v221_decisions(result, ['p'], own)[0]['decision'] == ('drop' if removed else 'keep')
    assert audit.removed_procedures(result, ['p'], configuration=p.MAIN_V6) == ['p']


def test_audit_without_own_confirmation_cannot_drop_on_other_procedure_harm():
    assert audit.removed_procedures({'confirmed': [finding()]}, ['p'], configuration=p.MAIN_V7,
                                   confirmation={'q': {'fixed': 0, 'broken': 10}}) == []


def test_final_audit_retains_deferred_note_truth_only_for_matching_surviving_source():
    proc = procedure('p-searchqa-1-1', ('applies', 'before_call'), origin='searchqa')
    parent = empty(step='D/s0', evidence='engineering_fixture')
    candidate = with_(parent, step='D/s1-searchqa', add=[proc])
    claim = dict(finding(), procedure=proc.id)
    earlier = {'truth_confirmed': [claim], 'procedure_sources': {proc.id: audit.text_sha256(proc.source)},
               '_source_unit': 'D/s1-searchqa/engineer-r1'}
    final = audit.v221_prior_truth({'confirmed': []}, [earlier], candidate)
    retained = final['truth_confirmed'][0]
    assert retained['reused_from_unit'] == earlier['_source_unit']
    assert retained['source_sha256'] == audit.text_sha256(proc.source)
    assert audit.removed_procedures(final, candidate.order, configuration=p.MAIN_V7,
                                   confirmation={proc.id: {'fixed': 0, 'broken': 1}}) == [proc.id]
    changed = dict(earlier, procedure_sources={proc.id: 'a' * 64})
    assert not audit.v221_prior_truth({'confirmed': []}, [changed], candidate)['truth_confirmed']


@pytest.mark.parametrize('code', ['P2', 'P3', 'P4', 'P5', 'P6'])
def test_policy_checks_remain_hard_even_when_the_procedure_has_gain(code):
    result = {'confirmed': [finding(g='true', d='true', policy=code)]}
    assert audit.removed_procedures(result, ['p'], configuration=p.MAIN_V7,
                                   confirmation={'p': {'fixed': 10, 'broken': 0}}) == ['p']


def test_coverage_feedback_is_count_only_and_small_candidates_name_existing_repair():
    got = rule.coverage(20, ['a', 'b'], {'p': ['a'], 'q': ['b']})
    assert got['candidate'] == {'touched': 2, 'batch': 20, 'share': .1}
    assert got['procedures']['p']['touched'] == 1 and '30%' in got['instruction'] and 'sub-type' in got['instruction']
    assert got['repair'] == 'fires on almost nothing: 2 / 20 items touched' and rule.coverage_ok(got)
    damaged = deepcopy(got); damaged['candidate']['share'] = .5
    assert not rule.coverage_ok(damaged)


@pytest.mark.parametrize('bench', engineer_v221.BENCHES)
@pytest.mark.parametrize('mode', ['single', 'train'])
@pytest.mark.parametrize('purpose', ['propose', 'inert_repair', 'audit_fix'])
def test_prompt_additions_belong_only_to_main_v7_with_exact_parent_prefix(bench, mode, purpose):
    from skillopt.execskill import engineer_v211
    old = SimpleNamespace(configuration=p.MAIN_V6, bench=bench, mode=mode, sheet={})
    new = SimpleNamespace(configuration=p.MAIN_V7, bench=bench, mode=mode, sheet={})
    user = {'request': purpose, 'evidence': {}}
    parent = engineer_v211.dispatch(old, user) if p.uses_v211(p.MAIN_V6, bench) else engineer._legacy_system(old, user)
    child = engineer_v221.dispatch(new, user)
    assert child == parent + engineer_v221.DECISION_PARAGRAPH + engineer_v221.COVERAGE_PARAGRAPH
    assert 'First propose procedures that act on every item' in child and '30%' in child
    assert engineer_v221.COVERAGE_PARAGRAPH not in parent


def test_actual_engineer_repairs_fewer_than_three_touched_items_and_defers_truth_drop():
    from dataclasses import replace
    from tests.execskill_fakes import engineer_reply
    from tests.test_execskill_v24_engineer import context
    from tests.test_execskill_v24_feedback_isolation import WireRoles
    from tests.test_execskill_v29_audit import Judge
    from tests.test_execskill_v291_engineer import encoded, views
    limited = ('def before_call(view, state):\n'
               '    index = int(view["question"].splitlines()[-1].split()[-1])\n'
               '    return {"facts": ["The public question was read."]} if index < 2 else None\n')
    broad = 'def before_call(view, state):\n    return {"facts": ["The public question was read."]}\n'
    ctx, _ = context(configuration=p.ZEBRA_PC_V15, views=views(6))
    ctx = replace(ctx, configuration=p.MAIN_V7, current=list(ctx.trajectories), card=zebralogic.CARD_TEXT)
    ctx.audit_judges = {key: Judge(truth='false') for key in ('G', 'D')}
    ctx.roles = WireRoles([engineer_reply({'findings': []}, []), encoded(ctx, limited), encoded(ctx, broad)])
    package, result = engineer.run_train(ctx)
    assert package is not None and package.procedures[0].source.strip() == broad.strip()
    row = result['changes'][0]
    assert row['attempts'][0]['coverage']['candidate'] == {'touched': 2, 'batch': 6, 'share': 1/3}
    assert row['repair_cycle']['inert_repairs'] == 1 and row['repair_cycle']['audit_fixes'] == 0
    assert row['audits'][0]['truth_confirmed'] and not row['audits'][0]['confirmed']
    assert row['audits'][0]['truth_gate'] == 'deferred_until_own_confirmation_net_harm'
    request = row['inert_repair']['calls'][0]['request']
    assert request['evidence']['coverage']['repair'] == 'fires on almost nothing: 2 / 6 items touched'


def test_parent_engineer_keeps_two_item_helper_without_new_repair_or_coverage():
    from dataclasses import replace
    from tests.execskill_fakes import engineer_reply
    from tests.test_execskill_v24_engineer import context
    from tests.test_execskill_v24_feedback_isolation import WireRoles
    from tests.test_execskill_v29_audit import Judge
    from tests.test_execskill_v291_engineer import encoded, views
    source = ('def before_call(view, state):\n'
              '    index = int(view["question"].splitlines()[-1].split()[-1])\n'
              '    return {"facts": ["The public question was read."]} if index < 2 else None\n')
    ctx, _ = context(configuration=p.ZEBRA_PC_V15, views=views(6))
    ctx = replace(ctx, configuration=p.MAIN_V6, current=list(ctx.trajectories), card=zebralogic.CARD_TEXT)
    ctx.audit_judges = {key: Judge() for key in ('G', 'D')}
    ctx.roles = WireRoles([engineer_reply({'findings': []}, []), encoded(ctx, source)])
    package, result = engineer.run_train(ctx)
    assert package is not None and result['changes'][0]['repair_cycle']['inert_repairs'] == 0
    assert all('coverage' not in attempt for attempt in result['changes'][0]['attempts'])


def test_production_feedback_and_history_enter_next_context_with_merged_training_ownership(monkeypatch):
    from dataclasses import replace
    from skillopt.execskill import step
    from tests.test_execskill_v24_engineer import context
    from tests.test_execskill_v291_engineer import views
    ctx, _ = context(configuration=p.ZEBRA_PC_V15, views=views(3))
    ctx = replace(ctx, configuration=p.MAIN_V7, current=list(ctx.trajectories), card=zebralogic.CARD_TEXT)
    keys = [trace['task_id'] for trace in ctx.trajectories]
    cells = {(arm, key): [{'cell': {'id': '%s-%s' % (arm, key), 'run': 1},
                          'judge': {'v2': {'token': 'pass' if arm == "S'" else 'fail'},
                                    'format': {'violation': arm == "S'"}}}]
             for arm in ('S', "S'") for key in keys}
    verdict = step.train_verdict(cells, keys, [], [], predicate_faults=0, routed=3, runs=1,
                                identical=[], touched=keys, configuration=p.MAIN_V7)
    assert verdict['adopted'] and not verdict['guards']['format']
    st = SimpleNamespace(bench='zebralogic', setting=SimpleNamespace(extra={'configuration': p.MAIN_V7}),
                         label=lambda unit: 'D/s1-zebralogic/' + unit, runtime=lambda: {})
    cut = {'run': [{'task_id': key.split('/', 1)[1], 'public': view} for key, view in ctx.routing_items]}
    monkeypatch.setattr(step, '_references', lambda *args, **kwargs: {})
    feedback = step._feedback(st, cut, 'train-r1', verdict, {}, ctx.parent, ctx.parent, cells, {})
    rejected = rule.counts(touched=2, fixed=2, broken=0, batch=3)
    coverage = rule.coverage(3, keys, {})
    feedback.update(rule=verdict['rule'], coverage=coverage, early_acceptance=rejected)
    feedback.update(adopted=False, reason='immediate_acceptance_rejected')
    verdict.update(adopted=False, reason='immediate_acceptance_rejected')
    evaluated = {'verdict': verdict, 'coverage': coverage, 'early_acceptance': rejected}
    line = step._line(1, {'candidate_sha256': ctx.parent.sha256, 'engineer': {'changes': []}},
                      evaluated, configuration=p.MAIN_V7)
    line['patience_counted'] = line['candidate']  # The training controller's unchanged history addition.
    fields = {key: value for key, value in ctx.trajectories[0].items()
              if key not in (p.RECORD_HASH, 'version', 'evidence')}
    merged = p.record('trajectory', ctx.evidence, {**fields, 'cell': 'merged-cell', 'arm': "S'",
        'arm_kind': 'candidate', 'unit': 'D/s1-zebralogic/train-r1-split-merge'})
    next_ctx = replace(ctx, round=2, current=[merged], evaluated=[merged], training=feedback, history=[line])
    assert next_ctx.training['informational_guards'] == ['own_faults', 'predicate_faults', 'format']
    assert next_ctx.history[0]['early_acceptance']['decision'] == 'reject'
    assert 'merged-cell' in engineer._verified_run_cells(next_ctx)
    with pytest.raises(ValueError, match='Training trajectories'):
        replace(next_ctx, configuration=p.MAIN_V6, training=None, history=[])


def test_combined_candidate_low_coverage_uses_same_latest_change_repair_cycle(monkeypatch):
    from dataclasses import replace
    from tests.execskill_fakes import engineer_reply
    from tests.test_execskill_v24_engineer import change, context
    from tests.test_execskill_v24_feedback_isolation import WireRoles
    from tests.test_execskill_v29_audit import Judge
    from tests.test_execskill_v291_engineer import encoded, views
    ctx, _ = context(configuration=p.ZEBRA_PC_V15, views=views(6))
    ctx = replace(ctx, configuration=p.MAIN_V7, current=list(ctx.trajectories), card=zebralogic.CARD_TEXT)
    ctx.audit_judges = {key: Judge() for key in ('G', 'D')}
    first = change(ctx, 'def before_call(view, state):\n    return {"facts": ["Public first."]}\n')
    second = change(ctx, 'def before_call(view, state):\n    return {"facts": ["Public second."]}\n')
    repaired = 'def before_call(view, state):\n    return {"facts": ["Public repaired."]}\n'
    original_signature = reuse.signature
    seen_combined = []
    def signature(bench, package, view, worker, **kwargs):
        result = original_signature(bench, package, view, worker, **kwargs)
        index = int(view['question'].splitlines()[-1].split()[-1])
        if len(package.procedures) == 2:
            seen_combined.append(package.order)
            if not any('repaired' in procedure.source for procedure in package.procedures) and index >= 2:
                result = dict(result, request_sha256='0' * 64, post_call=[])
        elif not package.procedures:
            result = dict(result, request_sha256='0' * 64, post_call=[])
        return result
    monkeypatch.setattr(reuse, 'signature', signature)
    ctx.roles = WireRoles([engineer_reply({'findings': []}, []),
        engineer_reply({'changes': [first.entry, second.entry]}, [first.source, second.source]),
        encoded(ctx, repaired)])
    package, result = engineer.run_train(ctx)
    assert seen_combined and len(package.procedures) == 2
    row = result['changes'][1]
    assert row['attempts'][0]['coverage']['candidate']['touched'] == 2
    assert row['repair_cycle']['inert_repairs'] == 1
    assert row['inert_repair']['calls'][0]['request']['evidence']['coverage']['candidate']['touched'] == 2


@pytest.mark.parametrize('bench', engineer_v221.BENCHES)
@pytest.mark.parametrize('mode', ['single', 'train'])
@pytest.mark.parametrize('configuration', [p.MAIN_V6, p.MAIN_V7])
def test_engineer_record_hash_matches_actual_proposal_prompt_on_all_learning_benches(bench, mode, configuration):
    from dataclasses import replace
    from tests.execskill_fakes import engineer_reply
    from tests.test_execskill_v24_engineer import context
    from tests.test_execskill_v24_feedback_isolation import WireRoles
    from tests.test_execskill_v211_routing import engineer_context
    if bench == 'zebralogic':
        ctx, _ = context(configuration=p.ZEBRA_PC_V15, mode=mode)
        ctx = replace(ctx, configuration=configuration, card=zebralogic.CARD_TEXT,
                      current=list(ctx.trajectories) if mode == 'train' else [])
    else:
        ctx = replace(engineer_context(bench, mode=mode), configuration=configuration)
    ctx.roles = WireRoles(([engineer_reply({'findings': []}, [])] if mode == 'train' else [])
                         + [engineer_reply({'changes': []}, [])])
    _, record = engineer.run_train(ctx) if mode == 'train' else engineer.run(ctx)
    proposal = next(wire for wire in ctx.roles.wire if wire['label'].endswith('/propose'))
    expected = audit.text_sha256(proposal['system'])
    assert record['prompt_sha256'] == expected
    assert record['prompt_sha256'] == audit.text_sha256(p.engineer_prompt(configuration, bench, mode))
    if p.uses_v211(configuration, bench):
        assert record['prompt_requests'][0]['system_sha256'] == expected
    assert (engineer_v221.COVERAGE_PARAGRAPH in proposal['system']) == p.is_v221(configuration)
