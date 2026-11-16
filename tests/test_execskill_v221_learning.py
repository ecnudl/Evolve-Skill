"""Authored main-v7 learning, fresh sampling and ordered split fixtures only."""
from copy import deepcopy
from types import SimpleNamespace

import pytest

from skillopt.execskill import confirm, profiles as p, step, v221_learning as learning, v221_rule as rule, v221_split as split
from skillopt.execskill.package import empty, save, with_
from skillopt.validator_pilot.api import digest
from tests.execskill_fakes_env import procedure
from tests.execskill_v293_fakes import tmp_path  # noqa: F401


def signature(value, faults=()):
    return {'request_sha256': digest(value), 'post_call': [], 'faults': list(faults)}


def pool(n):
    return [{'task_id': 'item-%03d' % i, 'benchmark': 'searchqa',
             'public': {'question': str(i)}, 'private': {'answer': 'private'}} for i in range(n)]


def paired(fixed=3, broken=0, ties=0, prefix='i'):
    keys = [prefix + str(i) for i in range(fixed + broken + ties)]
    cells = {(arm, key): [{'judge': {'v2': {'token': 'pass' if
             ((i < fixed and arm == "S'") or (fixed <= i < fixed + broken and arm == 'S')) else 'fail'}},
             'faults': [], 'final': {'outcome': 'pass', 'kind': 'score'}}]
             for i, key in enumerate(keys) for arm in ('S', "S'")}
    return keys, cells


def training(fixed=3, broken=0, ties=0):
    keys, cells = paired(fixed, broken, ties)
    verdict = step.train_verdict(cells, keys, [], {'authored'}, predicate_faults=0, routed=len(keys),
        sign=False, identical=[], configuration=p.MAIN_V7, touched=keys)
    return {'adopted': verdict['adopted'], 'verdict': verdict, 'feedback': {}, 'cells': len(cells)}


def confirmation(fixed=3, broken=0, ties=0):
    keys, cells = paired(fixed, broken, ties)
    sigs = {key: {'S': signature([key, 'S']), "S'": signature([key, "S'"])} for key in keys}
    return {'confirm': learning.confirmation_verdict(cells, keys, sigs, bench='searchqa', items=len(keys))}


def packages(root=None):
    parent = empty(step='G/s1-searchqa', evidence='engineering_fixture')
    rows = [procedure('fx-authored-' + str(i), ('applies', 'before_call'), origin='searchqa') for i in range(3)]
    candidates = [with_(parent, step='G/s1-searchqa', add=tuple(rows[:i])) for i in (1, 2, 3)]
    if root is not None:
        for candidate in [parent, *candidates]:
            save(root, candidate)
    return parent, candidates


class Registry:
    def __init__(self): self.calls = []
    def register(self, *args, **kw): self.calls.append(('register', args, kw))
    def dispatch(self, *args, **kw): self.calls.append(('dispatch', args, kw))
    def decide(self, *args, **kw): self.calls.append(('decide', args, kw))


class FixtureStep:
    def __init__(self, root, parent):
        self.parent, self.chain_root, self.root = parent, root, root / 's1-searchqa'
        self.root.mkdir(parents=True, exist_ok=True)
        self.setting = SimpleNamespace(extra={'configuration': p.MAIN_V7}, root=root, cards={'searchqa': 'card'})
        self.services = SimpleNamespace(registry=Registry(), item_workers=None)
        self.chain, self.bench, self.k, self.smoke = 'G', 'searchqa', 1, None
        self.namespace, self.evidence = 'G-v7', 'engineering_fixture'
        self.results, self.invocations = {}, []
    def runtime(self): return {}
    def label(self, name): return 'G/s1-searchqa/' + name
    def solver(self, kind, attempt): return None
    def done(self, name): return self.results.get(name)
    def unit(self, name, work, **kwargs):
        if name not in self.results:
            self.invocations.append(name)
            attempt = self.root / name / 'attempt-1'; attempt.mkdir(parents=True, exist_ok=True)
            self.results[name] = work(attempt)
            if kwargs.get('settle'): kwargs['settle'](attempt, self.results[name])
        return self.results[name]


@pytest.mark.parametrize('count,target,maximum,expected,touched', [
    (200, 60, 1000, 119, 60), (40, 60, 1000, 40, 20), (200, 60, 75, 75, 38), (0, 60, 1000, 0, 0)])
def test_sampler_uses_public_routing_only_and_stops(count, target, maximum, expected, touched):
    calls = []
    def route(item):
        assert set(item) == {'task_id', 'benchmark', 'public'}
        calls.append(item['task_id']); n = int(item['public']['question'])
        return {'S': signature('base'), "S'": signature('changed' if n % 2 == 0 else 'base')}
    found = learning.select_acceptance(pool(count), route, maximum=maximum, target=target)
    assert len(found['selected']) == expected and len(found['touched']) == touched
    assert calls == found['examined']


def test_sampler_never_recycles_previous_items_and_refuses_protected_partition():
    rows = pool(9)
    fn = lambda item: {'S': signature('same'), "S'": signature('same')}
    found = learning.select_acceptance(rows, fn, used=[i['task_id'] for i in rows[:4]], maximum=100)
    assert found['examined'] == [i['task_id'] for i in rows[4:]] and found['exhausted']
    rows[0]['partition'] = 'test'
    with pytest.raises(ValueError, match='practice'):
        learning.select_acceptance(rows, fn, maximum=100)


def test_identical_three_stage_records_and_diagnostics_do_not_decide():
    keys, cells = paired(21, 11)
    for records in cells.values():
        records[0]['judge']['format'] = {'violation': True}
        records[0]['faults'] = [{'procedure': 'authored', 'kind': 'output'}]
        records[0]['final'] = {'outcome': 'unknown', 'kind': 'infrastructure'}
    train = step.train_verdict(cells, keys, [], {'authored'}, predicate_faults=32, routed=32,
        sign=False, identical=[], configuration=p.MAIN_V7, touched=keys)
    sigs = {key: {'S': signature('S'), "S'": signature('candidate')} for key in keys}
    held = learning.confirmation_verdict(cells, keys, sigs, bench='searchqa', items=32)
    accepted = rule.decide(cells, keys, touched=keys)
    assert train['rule'] == held['rule'] == accepted
    assert train['adopted'] and held['passed'] and accepted['decision'] == 'accept'
    assert not train['guards']['own_faults'] and not train['guards']['predicate_faults']
    assert held['infrastructure']['warnings'] == ['J5:S', "J5:S'"]


def test_public_request_identity_not_predicate_routing_defines_training_and_confirm(tmp_path, monkeypatch):
    parent, candidates = packages(tmp_path); candidate = candidates[0]
    st = FixtureStep(tmp_path, parent)
    rows = pool(40)
    cut = {'run': rows, 'accept': [], 'confirm-r1': [{**i, 'task_id': 'confirm-' + i['task_id']} for i in rows]}
    monkeypatch.setitem(p.PRUNE_NON_FIRING, p.MAIN_V7, False)
    monkeypatch.setattr(step, '_routes', lambda st, package, views, publics: {
        key: SimpleNamespace(enabled=(), faults=[], to_json=lambda: {}) for key, _ in views})
    monkeypatch.setattr(step.solver, 'routing_view', lambda bench, public, **kw: public)
    def identities(st, candidate, incumbent, publics, views, **kw):
        out = {}
        for key, view in views:
            active = int(view['question']) < 3
            out[key] = {"S'": signature([key, bool(candidate.order) and active]),
                        'S': signature([key, bool(incumbent.order) and active])}
            if 'note_coverage' in kw:
                kw['note_coverage'][key] = {'S': {}, "S'": {}}
        return out
    monkeypatch.setattr(step, '_pair_signatures', identities)
    monkeypatch.setattr(step, '_feedback', lambda *args, **kw: {})
    monkeypatch.setattr(step, '_attempt_trajectories', lambda *args: {})
    dispatched = []
    def run(st, attempt, endpoint, name, jobs, **kw):
        out = []
        for arm, package, key, run, task in jobs:
            cell = {'cell': {'id': digest([name, arm, key, run]), 'arm': arm, 'task_id': key, 'run': run},
                    'judge': {'v2': {'token': 'pass' if arm == "S'" else 'fail'}},
                    'faults': [], 'final': {'outcome': 'pass', 'kind': 'score'}, 'sends': []}
            out.append(cell); dispatched.append((name, arm, key))
        return out
    monkeypatch.setattr(step, '_cells', run)
    train = step._train_eval(st, cut, 1, parent, candidate, None, current=[])
    assert train['adopted'] and train['verdict']['rule']['touched'] == 3
    assert train['coverage']['candidate'] == {'touched': 3, 'batch': 40, 'share': .075}
    assert train['coverage']['procedures'][candidate.order[0]]['touched'] == 3
    # Confirmation IDs differ and stay out of the training feedback.
    held = step._confirm_eval(st, cut, 1, parent, candidate)
    assert held['confirm']['passed'] and held['confirm']['rule'] == train['verdict']['rule']
    assert len(dispatched) == 12
    assert held['procedure_confirmation'][candidate.order[0]]['fixed'] == 3
    assert [kind for kind, _, _ in st.services.registry.calls] == ['register', 'dispatch', 'decide']


def test_immediate_acceptance_pins_selection_and_restarts_without_routing(tmp_path, monkeypatch):
    parent, candidates = packages(tmp_path); st = FixtureStep(tmp_path, parent)
    cut = {'accept': pool(100)}
    calls = []
    monkeypatch.setattr(step.solver, 'routing_view', lambda bench, public, **kw: public)
    monkeypatch.setattr(step, '_pair_signatures', lambda st, candidate, incumbent, publics, views: {
        key: {'S': signature('base'), "S'": signature('candidate')} for key, _ in views})
    accepted = {'decision': 'accept', 'reason': None, 'rule': rule.counts(touched=60, fixed=60, broken=0, batch=60)}
    def accept(st, sliced, candidate, generated, **kw):
        calls.append((kw['unit'], kw['incumbent'].sha256, [i['task_id'] for i in sliced['accept']]))
        assert generated is None and sliced['accept_probe'] == []
        return st.unit(kw['unit'], lambda attempt: accepted)
    monkeypatch.setattr(step, '_accept', accept)
    first = learning.immediate_acceptance(st, cut, 1, parent, candidates[0])
    assert len(first['selection']['examined']) == 60
    monkeypatch.setattr(step, '_pair_signatures', lambda *args: pytest.fail('selection must resume'))
    assert learning.immediate_acceptance(st, cut, 1, parent, candidates[0]) == first
    with pytest.raises(ValueError, match='original packages'):
        learning.immediate_acceptance(st, cut, 1, parent, candidates[1])


def test_exhausted_acceptance_pool_rejects_and_never_calls_accept(tmp_path, monkeypatch):
    parent, candidates = packages(tmp_path); st = FixtureStep(tmp_path, parent)
    monkeypatch.setattr(step, '_accept', lambda *a, **k: pytest.fail('no fresh item'))
    accepted = learning.immediate_acceptance(st, {'accept': []}, 1, parent, candidates[0])
    selected, evaluated = learning.apply_acceptance(parent, candidates[0], training(), accepted)
    assert selected == parent and not evaluated['adopted']
    assert accepted['reason'] == 'acceptance_pool_exhausted'


def test_failed_immediate_acceptance_rolls_back_then_next_round_improves_last_accepted(tmp_path, monkeypatch):
    parent, candidates = packages(tmp_path); st = FixtureStep(tmp_path, parent)
    seen = []
    def engineer(st, cut, r, incumbent, **kw):
        seen.append(incumbent.sha256)
        return {'candidate_sha256': candidates[r-1].sha256, 'engineer': {
            'changes': [], 'analysis': {'items': []}, 'disclosed': [], 'lint': [], 'dropped': []}}
    monkeypatch.setattr(step, '_engineer_train', engineer)
    monkeypatch.setattr(step, '_train_eval', lambda st, cut, r, incumbent, candidate, *a, **kw:
        {**training(), 'candidate_sha256': candidate.sha256})
    monkeypatch.setattr(step, '_confirm_eval', lambda *a, **kw: confirmation())
    monkeypatch.setattr(step, '_current', lambda *a: [])
    monkeypatch.setattr(p, 'train_rounds', lambda configuration: 3)
    def immediate(st, cut, r, incumbent, candidate, generated):
        result = rule.counts(touched=3, fixed=0 if r == 2 else 3, broken=0, batch=3)
        return {'decision': result['decision'], 'reason': None, 'rule': result}
    monkeypatch.setattr(learning, 'immediate_acceptance', immediate)
    final, history, last = step._train(st, {}, None)
    assert seen == [parent.sha256, candidates[0].sha256, candidates[0].sha256]
    assert [r['adopted'] for r in history] == [True, False, True]
    assert history[1]['incumbent_sha256'] == candidates[0].sha256
    assert final == candidates[2] and last == candidates[2]
    assert history[1]['early_acceptance']['decision'] == 'reject'


def test_end_of_step_uses_last_accepted_with_one_final_audit_and_no_accept(tmp_path, monkeypatch):
    from tests.test_execskill_v221_fix1 import accepted
    parent, candidates = packages(tmp_path); st = FixtureStep(tmp_path, parent)
    row, decision = accepted(st, 1, parent, candidates[0])
    rows = [row, {'round': 2, 'adopted': False}]
    monkeypatch.setattr(step, '_train', lambda *a: (candidates[0], rows, candidates[1]))
    audits, checks = [], []
    monkeypatch.setattr(step, '_audit_final', lambda st, candidate, history:
        (audits.append(candidate.sha256) or candidate, {'decision': 'continue', 'audit_final': {}}))
    monkeypatch.setattr(step, '_audit_summary', lambda *a: {})
    monkeypatch.setattr(step, '_selftest', lambda st, unit, candidate, generated:
        checks.append(candidate.sha256) or {'blocked': False})
    monkeypatch.setattr(step, '_accept', lambda *a: pytest.fail('no separate end-of-step acceptance'))
    candidate, outcome, recorded = step._trained(st, {}, None)
    assert candidate == candidates[0] and outcome['decision_sha256'] == decision['decision_sha256']
    assert audits == checks == [candidates[0].sha256]
    assert outcome['accepted_rounds'] == [1]


@pytest.mark.parametrize('merge_passes', [True, False])
def test_split_adopts_all_passing_in_order_and_merged_failure_falls_back(tmp_path, merge_passes):
    parent, candidates = packages(tmp_path); full = candidates[2]
    st = FixtureStep(tmp_path, parent)
    stages = []
    def evaluate(st, cut, r, n, incumbent, sub, original, source, generated, **kw):
        held = kw.get('confirmation', False); stages.append((n, held, sub.order))
        if n == 3: return training(0, 3)
        if n == 'merge' and held and not merge_passes: return confirmation(0, 3)
        return confirmation(4 if n == 2 else 3) if held else training(4 if n == 2 else 3)
    selected, result = split.run(st, {}, 1, parent, full,
        {'engineer': {'changes': [{'id': pid, 'kind': 'new', 'target': None} for pid in full.order]}},
        training(6), confirmation(0, 3), None, current=[], evaluator=evaluate)
    assert selected.order == (full.order[:2] if merge_passes else (full.order[1],))
    assert result['adopted'] and result['split_adopted'] == list(selected.order)
    assert sum(n == 'merge' for n, _, _ in stages) == 2
    assert result['confirmation_unit'].endswith('split-merge' if merge_passes else 'split-p2')


def test_split_does_not_hide_policy_or_data_error_during_merge_evaluation(tmp_path):
    parent, candidates = packages(tmp_path); full = candidates[1]; st = FixtureStep(tmp_path, parent)
    def evaluate(st, cut, r, n, *args, **kw):
        if n == 'merge': raise ValueError('policy data mismatch')
        return confirmation() if kw.get('confirmation') else training()
    with pytest.raises(ValueError, match='policy data mismatch'):
        split.run(st, {}, 1, parent, full, {'engineer': {'changes': []}},
                  training(6), confirmation(0, 3), None, current=[], evaluator=evaluate)


def test_audit_uses_selected_confirmation_once_not_every_split_alternative(tmp_path):
    parent, candidates = packages(); candidate = candidates[0]; pid = candidate.order[0]
    st = FixtureStep(tmp_path, parent)
    def result(fixed, broken):
        return {'candidate_sha256': candidate.sha256, 'incumbent_sha256': parent.sha256,
                'procedure_confirmation': {pid: {'fixed': fixed, 'broken': broken, 'touched': fixed + broken,
                    'comparison': {'candidate_sha256': candidate.sha256, 'incumbent_sha256': parent.sha256,
                        'procedure_sha256': candidate.get(pid).sha256, 'candidate_present': True,
                        'incumbent_present': False, 'direction': 'candidate_present_vs_incumbent_absent'}}}}
    st.results.update({'confirm-r1': result(1, 5), 'confirm-r1-split-merge': result(3, 1),
                       'confirm-r2': result(1, 2)})
    counts = learning.audit_confirmation(st, [{'round': 1, 'confirmation_unit': 'confirm-r1-split-merge'},
                                              {'round': 2}], candidate=candidate)
    assert counts == {pid: {'fixed': 4, 'broken': 3, 'touched': 7}}


def authored_request_pair(st, incumbent, candidate, keys):
    """Run the production renderer with authored hook output and public views."""
    from tests.test_execskill_acceptance import workers
    st.services.item_workers = workers({proc.id: {'applies': lambda view: True,
        'before_call': lambda view, state, pid=proc.id: {'facts': ['Authored note from ' + pid]}}
        for proc in (*incumbent.procedures, *candidate.procedures)})
    publics = {key: {'question': 'Authored question ' + key, 'context': ['Authored passage.']} for key in keys}
    views = [(key, step.solver.routing_view(st.bench, public, runtime=st.runtime()))
             for key, public in publics.items()]
    signatures = step._pair_signatures(st, candidate, incumbent, publics, views)
    return publics, views, signatures


def test_rejected_deletion_keeps_six_fixes_zero_breaks_and_cannot_trigger_audit_drop(tmp_path):
    from skillopt.execskill import audit
    parent, candidates = packages(); candidate = candidates[0]; pid = candidate.order[0]
    deleted = with_(candidate, step=candidate.step, remove=[pid])
    st = FixtureStep(tmp_path, parent)
    for round_, incumbent, proposed, fixed, broken in (
            (1, parent, candidate, 6, 0), (2, candidate, deleted, 0, 7)):
        keys, cells = paired(fixed, broken, prefix='r%d-' % round_)
        publics, views, signatures = authored_request_pair(st, incumbent, proposed, keys)
        rows = learning.confirmation_counts(st, cells, publics, views, signatures, incumbent, proposed)
        verdict = learning.confirmation_verdict(cells, keys, signatures, bench=st.bench, items=len(keys))
        assert verdict['passed'] is (round_ == 1)
        assert rows[pid]['fixed'] == fixed and rows[pid]['broken'] == broken
        comparison = rows[pid]['comparison']
        assert comparison['candidate_sha256'] == proposed.sha256
        assert comparison['incumbent_sha256'] == incumbent.sha256
        assert comparison['candidate_present'] is (round_ == 1)
        st.results['confirm-r%d' % round_] = {'candidate_sha256': proposed.sha256,
            'incumbent_sha256': incumbent.sha256, 'procedure_confirmation': rows}
    counts = learning.audit_confirmation(st, [{'round': 1}, {'round': 2}], candidate=candidate)
    assert counts == {pid: {'fixed': 6, 'broken': 0, 'touched': 6}}
    truth = {'confirmed': [{'procedure': pid, 'judges': {
        'G': {'truth': 'false'}, 'D': {'truth': 'false'}}}]}
    decision = audit.v221_decisions(truth, candidate.order, counts)[0]
    assert decision['both_judges_untrue'] and not decision['own_net_harm']
    assert audit.removed_procedures(truth, candidate.order, configuration=p.MAIN_V7, confirmation=counts) == []


@pytest.mark.parametrize('mismatch', ['package', 'procedure'])
def test_audit_confirmation_ignores_evidence_for_another_package_or_procedure_version(tmp_path, mismatch):
    from dataclasses import replace
    parent, candidates = packages(); candidate = candidates[0]; pid = candidate.order[0]
    st = FixtureStep(tmp_path, parent)
    keys, cells = paired(0, 7)
    publics, views, signatures = authored_request_pair(st, parent, candidate, keys)
    rows = learning.confirmation_counts(st, cells, publics, views, signatures, parent, candidate)
    st.results['confirm-r1'] = {'candidate_sha256': candidate.sha256, 'incumbent_sha256': parent.sha256,
                               'procedure_confirmation': rows}
    if mismatch == 'package':
        st.results['confirm-r1']['candidate_sha256'] = candidates[1].sha256
    else:
        changed = replace(candidate.get(pid), source=candidate.get(pid).source + '\n# Different authored source.\n')
        candidate = replace(candidate, procedures=(changed,))
    assert learning.audit_confirmation(st, [{'round': 1}], candidate=candidate) == {}


@pytest.mark.parametrize('excluded,expected', [('searchqa', 3), ('officeqa', 0)])
def test_narrowing_coverage_compares_previous_scope_and_actual_changed_requests(tmp_path, excluded, expected):
    parent, candidates = packages(); incumbent = candidates[0]; pid = incumbent.order[0]
    candidate = with_(incumbent, step=incumbent.step, narrow={pid: [excluded]},
                      add=[candidates[1].procedures[1]])
    st = FixtureStep(tmp_path, parent)
    keys, cells = paired(0, 3)
    publics, views, signatures = authored_request_pair(st, incumbent, candidate, keys)
    assert rule.identity_touched(signatures, bench=st.bench) == keys
    verdict = learning.confirmation_verdict(cells, keys, signatures, bench=st.bench, items=3)
    result = learning.attach_training(st, {'feedback': {}, 'verdict': verdict}, cells, publics, views,
                                      signatures, incumbent, candidate)
    assert result['coverage']['candidate']['touched'] == 3
    assert result['coverage']['procedures'][pid]['touched'] == expected
    own = learning.confirmation_counts(st, cells, publics, views, signatures, incumbent, candidate)[pid]
    assert (own['touched'], own['fixed'], own['broken']) == (expected, 0, expected)
    assert own['comparison']['direction'] == 'candidate_narrowed_vs_incumbent_previous_scope'
    assert own['comparison']['candidate_sha256'] == candidate.sha256
    assert own['comparison']['incumbent_sha256'] == incumbent.sha256


def test_per_procedure_sheet_coverage_requires_its_own_actual_callback_effect(tmp_path, monkeypatch):
    parent = empty(step='G/s1-spreadsheetbench', evidence='engineering_fixture')
    procedures = [procedure('fx-sheet-' + name, ('applies', 'sheet_feedback'), origin='spreadsheetbench')
                  for name in ('silent', 'emitted')]
    candidate = with_(parent, step=parent.step, add=procedures)
    st = FixtureStep(tmp_path, parent); st.bench = 'spreadsheetbench'
    keys, cells = paired(3)
    publics = {key: {} for key in keys}; views = list(publics.items())
    def identities(st, candidate, incumbent, publics, views):
        def identity(package):
            return {**signature('same first request'), 'post_call': [
                {'hook': 'sheet_feedback', 'procedure': proc.id, 'version': proc.sha256}
                for proc in package.for_bench(st.bench)]}
        return {key: {"S'": identity(candidate), 'S': identity(incumbent)} for key in publics}
    monkeypatch.setattr(step, '_pair_signatures', identities)
    for key in keys:
        cells[("S'", key)][0]['post_call_effects'] = {proc.id: {'procedure_sha256': proc.sha256,
            'note_emitted': proc == procedures[1], 'repair_requested': False} for proc in procedures}
    signatures = identities(st, candidate, parent, publics, views)
    counts = learning.confirmation_counts(st, cells, publics, views, signatures, parent, candidate)
    assert counts[procedures[0].id]['touched'] == 0
    assert counts[procedures[0].id]['reason'] == 'no_touched_items'
    assert counts[procedures[1].id]['touched'] == 3
    held = learning.confirmation_verdict(cells, keys, signatures, bench=st.bench, items=3)
    assert held['passed'] and held['request_effects']['request_changed'] == []
    assert held['request_effects']['callback_active'][keys[0]]["S'"] == list(candidate.order)


@pytest.mark.parametrize('kind', ['deletion', 'narrowing'])
def test_removed_sheet_callback_effect_uses_incumbent_arm_and_previous_scope(tmp_path, monkeypatch, kind):
    parent = empty(step='G/s1-spreadsheetbench', evidence='engineering_fixture')
    proc = procedure('fx-sheet-old', ('applies', 'sheet_feedback'), origin='spreadsheetbench')
    incumbent = with_(parent, step=parent.step, add=[proc])
    candidate = with_(incumbent, step=parent.step, **(
        {'remove': [proc.id]} if kind == 'deletion' else {'narrow': {proc.id: ['spreadsheetbench']}}))
    st = FixtureStep(tmp_path, parent); st.bench = 'spreadsheetbench'
    keys, cells = paired(0, 3)
    publics = {key: {} for key in keys}; views = list(publics.items())
    def identities(st, candidate, incumbent, publics, views):
        def identity(package):
            return {**signature('same first request'), 'post_call': [
                {'hook': 'sheet_feedback', 'procedure': row.id, 'version': row.sha256}
                for row in package.for_bench(st.bench)]}
        return {key: {"S'": identity(candidate), 'S': identity(incumbent)} for key in publics}
    monkeypatch.setattr(step, '_pair_signatures', identities)
    for key in keys:
        cells[('S', key)][0]['post_call_effects'] = {proc.id: {
            'procedure_sha256': proc.sha256, 'note_emitted': False, 'repair_requested': True}}
    signatures = identities(st, candidate, incumbent, publics, views)
    own = learning.confirmation_counts(st, cells, publics, views, signatures, incumbent, candidate)[proc.id]
    assert (own['touched'], own['fixed'], own['broken']) == (3, 0, 3)
    assert own['comparison']['incumbent_present']
    st.results['confirm-r1'] = {'candidate_sha256': candidate.sha256, 'incumbent_sha256': incumbent.sha256,
                               'procedure_confirmation': {proc.id: own}}
    assert learning.audit_confirmation(st, [{'round': 1}], candidate=incumbent) == {}


def test_immediate_acceptance_real_prepare_decide_and_settle(tmp_path, monkeypatch):
    from dataclasses import dataclass
    from skillopt.execskill import acceptance, units
    from tests.test_execskill_acceptance import make_cells, workers
    parent, candidates = packages(tmp_path); candidate = candidates[0]; st = FixtureStep(tmp_path, parent)
    st.name = 'G/s1-searchqa'; st.setting.workers = 1
    st.purpose = lambda name: name
    st.solver = lambda *args, **kwargs: None
    st.services.clock, st.services.sleep = lambda: 100000., lambda seconds: None
    table = {candidate.order[0]: {'applies': lambda view: True,
            'before_call': lambda view, state: {'facts': ['Authored mechanism fixture.']}}}
    factory = workers(table)
    monkeypatch.setattr(step, '_item_workers', lambda st, publics: factory)
    @dataclass
    class Context:
        endpoint: object = None
    monkeypatch.setattr(units, 'cell_context', lambda *args: Context())
    monkeypatch.setattr(acceptance, 'runner', lambda *args, **kwargs: None)
    monkeypatch.setattr(acceptance, 'dispatch', lambda sealed, *args, **kwargs:
        make_cells(sealed, token=lambda job: 'pass' if job['arm'] == "S'" else 'fail'))
    rows = [{**item, 'public': {**item['public'], 'context': ['Authored public passage.']}} for item in pool(10)]
    found = learning.immediate_acceptance(st, {'accept': rows}, 1, parent, candidate)
    assert found['accepted'] and found['rule']['touched'] == found['rule']['fixed'] == 10
    assert found['selection']['exhausted'] and found['rule']['decision'] == 'accept'
    assert st.results['accept-r1']['decision'] == 'accept'
    assert [kind for kind, _, _ in st.services.registry.calls] == ['register', 'decide']


def test_acceptance_selection_tampering_refuses_before_dispatch(tmp_path, monkeypatch):
    import json
    parent, candidates = packages(tmp_path); st = FixtureStep(tmp_path, parent)
    rows = pool(4)
    monkeypatch.setattr(step.solver, 'routing_view', lambda bench, public, **kw: public)
    monkeypatch.setattr(step, '_pair_signatures', lambda st, candidate, incumbent, publics, views: {
        key: {'S': signature('base'), "S'": signature('candidate')} for key, _ in views})
    monkeypatch.setattr(step, '_accept', lambda *args, **kwargs: {'decision': 'reject'})
    learning.immediate_acceptance(st, {'accept': rows}, 1, parent, candidates[0])
    path = st.root / 'accept-selection-r1.json'; value = json.loads(path.read_text())
    value['touched'] = []; path.write_text(json.dumps(value))
    monkeypatch.setattr(step, '_accept', lambda *args, **kwargs: pytest.fail('tamper dispatch'))
    with pytest.raises(ValueError):
        learning.immediate_acceptance(st, {'accept': rows}, 1, parent, candidates[0])


def test_second_acceptance_uses_only_unexamined_remaining_prefix(tmp_path, monkeypatch):
    parent, candidates = packages(tmp_path); st = FixtureStep(tmp_path, parent)
    rows = pool(80)
    monkeypatch.setattr(step.solver, 'routing_view', lambda bench, public, **kw: public)
    monkeypatch.setattr(step, '_pair_signatures', lambda st, candidate, incumbent, publics, views: {
        key: {'S': signature('base'), "S'": signature('candidate')} for key, _ in views})
    monkeypatch.setattr(step, '_accept', lambda *args, **kwargs: {'decision': 'reject'})
    first = learning.immediate_acceptance(st, {'accept': rows}, 1, parent, candidates[0])
    second = learning.immediate_acceptance(st, {'accept': rows}, 2, parent, candidates[1])
    assert len(first['selection']['examined']) == 60 and len(second['selection']['examined']) == 20
    assert not set(first['selection']['examined']) & set(second['selection']['examined'])
    assert second['selection']['previously_examined'] == first['selection']['examined']


def test_zero_model_structural_smoke_uses_actual_three_stage_decisions(tmp_path):
    found = learning.structural_smoke(tmp_path)
    assert found['passed'] and found['model_calls'] == found['sealed_reads'] == 0
    assert found['decisions']['training'] == found['decisions']['confirmation'] == found['decisions']['acceptance']
    assert all(found[key]['passed'] for key in ('early_acceptance', 'split_merge', 'audit_non_drop'))


def test_two_real_immediate_acceptances_bind_current_incumbent_without_rewriting_procedures(tmp_path, monkeypatch):
    from dataclasses import dataclass
    from skillopt.execskill import acceptance, units
    from skillopt.execskill.package import load
    from tests.test_execskill_acceptance import make_cells, workers
    parent, candidates = packages(tmp_path); first, second = candidates[:2]; st = FixtureStep(tmp_path, parent)
    st.name = 'G/s1-searchqa'; st.setting.workers = 1; st.purpose = lambda name: name
    st.solver = lambda *args, **kwargs: None
    st.services.clock, st.services.sleep = lambda: 100000., lambda seconds: None
    hooks = {pid: {'applies': lambda view: True,
        'before_call': lambda view, state, pid=pid: {'facts': ['Authored note ' + pid]}} for pid in second.order}
    factory = workers(hooks)
    monkeypatch.setattr(step, '_item_workers', lambda st, publics: factory)
    @dataclass
    class Context:
        endpoint: object = None
    monkeypatch.setattr(units, 'cell_context', lambda *args: Context())
    monkeypatch.setattr(acceptance, 'runner', lambda *args, **kwargs: None)
    monkeypatch.setattr(acceptance, 'dispatch', lambda sealed, *args, **kwargs:
        make_cells(sealed, token=lambda job: 'pass' if job['arm'] == "S'" else 'fail'))
    rows = [{**item, 'public': {**item['public'], 'context': ['Authored public passage.']}} for item in pool(120)]
    a = learning.immediate_acceptance(st, {'accept': rows}, 1, parent, first)
    b = learning.immediate_acceptance(st, {'accept': rows}, 2, first, second)
    assert a['accepted'] and b['accepted']
    assert len(a['selection']['examined']) == len(b['selection']['examined']) == 60
    assert second.parent_sha256 == parent.sha256
    contrast = load(tmp_path / 'packages' / (b['contrast_candidate_sha256'] + '.json'))
    assert contrast.parent_sha256 == first.sha256
    assert contrast.procedures == second.procedures
    assert contrast.order == second.order and contrast.narrowed == second.narrowed
    assert b['candidate_sha256'] == second.sha256 and b['contrast_candidate_sha256'] != second.sha256
    selected, out = learning.apply_acceptance(first, second, step._confirmed_training(training(), confirmation()), b)
    assert selected == second and out['adopted']


def test_rejected_immediate_acceptance_never_reports_split_proposal_as_adopted():
    trained = training()
    trained.update(split=[split.counts('fx-one', trained, confirmation()),
                          split.counts('fx-two', trained, confirmation())],
                   split_winner='fx-one', split_adopted=['fx-one', 'fx-two'])
    parent, candidates = packages()
    rejected = {'decision': 'reject', 'reason': 'gain_and_no_harm',
                'rule': rule.counts(touched=2, fixed=2, broken=0, batch=2)}
    _, evaluated = learning.apply_acceptance(parent, candidates[1], trained, rejected)
    engineered = {'candidate_sha256': candidates[1].sha256, 'engineer': {'changes': [
        {'id': 'fx-one', 'kind': 'new', 'target': None, 'summary': '', 'n': 0, 'survived': True, 'attempts': []},
        {'id': 'fx-two', 'kind': 'new', 'target': None, 'summary': '', 'n': 1, 'survived': True, 'attempts': []}], 'dropped': []}}
    line = step._line(1, engineered, evaluated, configuration=p.MAIN_V7)
    assert not line['adopted'] and all(row['fate'] != 'adopted_by_split' for row in line['proposals'])


@pytest.mark.parametrize('first_round', [1, 3])
@pytest.mark.parametrize('passes', [True, False])
def test_zebra_confirmation_is_fresh_once_then_rejects_exhaustion_without_calls(tmp_path, monkeypatch, first_round, passes):
    parent, candidates = packages(tmp_path); candidate = candidates[1]; st = FixtureStep(tmp_path, parent)
    st.bench = 'zebralogic'
    rows = [{**i, 'task_id': 'confirm-' + i['task_id'], 'benchmark': st.bench} for i in pool(40)]
    cut = {'run': [], 'accept': [], 'confirm': rows}
    monkeypatch.setattr(step, '_routes', lambda st, package, views, publics: {
        key: SimpleNamespace(enabled=(), faults=[], to_json=lambda: {}) for key, _ in views})
    monkeypatch.setattr(step.solver, 'routing_view', lambda bench, public, **kw: public)
    monkeypatch.setattr(step, '_pair_signatures', lambda st, candidate, incumbent, publics, views, **kw: {
        key: {'S': signature([key, bool(incumbent.order)]), "S'": signature([key, bool(candidate.order)])}
        for key, _ in views})
    monkeypatch.setattr(step, '_confirm_cached', lambda *a, **kw: pytest.fail('main-v7 never caches previous confirmations'))
    calls = []
    def dispatch(st, attempt, endpoint, name, jobs, **kw):
        calls.extend(jobs)
        return [{'cell': {'id': digest([name, arm, key]), 'arm': arm, 'task_id': key, 'run': run},
                 'judge': {'v2': {'token': 'pass' if ((arm == "S'") == passes) else 'fail'}},
                 'faults': [], 'final': {'outcome': 'pass', 'kind': 'score'}, 'sends': []}
                for arm, package, key, run, task in jobs]
    monkeypatch.setattr(step, '_cells', dispatch)
    first = step._confirm_eval(st, cut, first_round, parent, candidate)
    assert first['confirm']['passed'] == passes and len(first['slice_ids']) == 40
    assert not first['cross_round_cache'] and len(calls) == 80
    monkeypatch.setattr(step, '_pair_signatures', lambda *a, **kw: pytest.fail('exhausted confirmation does not route'))
    second = step._confirm_eval(st, cut, first_round + 1, parent, candidate)
    assert not second['confirm']['passed'] and second['confirm']['reason'] == 'confirmation_pool_exhausted'
    assert second['confirm']['rule'] == rule.counts(touched=0, fixed=0, broken=0, batch=0)
    assert not second['slice_ids'] and not second['cells'] and len(calls) == 80
    assert [kind for kind, _, _ in st.services.registry.calls] == ['register', 'dispatch', 'decide']
    _, result = split.run(st, cut, first_round + 1, parent, candidate,
        {'engineer': {'changes': []}}, training(), second, None, current=[],
        evaluator=lambda *a, **kw: pytest.fail('exhausted confirmation cannot split-reuse its pool'))
    assert not result['adopted']


def test_no_candidate_round_marks_coverage_not_applicable_and_enters_next_context():
    from dataclasses import replace
    from skillopt.execskill import zebralogic
    from tests.test_execskill_v24_engineer import context
    from tests.test_execskill_v291_engineer import views
    ctx, _ = context(configuration=p.ZEBRA_PC_V15, views=views(3))
    ctx = replace(ctx, configuration=p.MAIN_V7, current=list(ctx.trajectories), card=zebralogic.CARD_TEXT)
    engineered = {'candidate_sha256': None, 'engineer': {'changes': []}}
    line = step._line(1, engineered, None, configuration=p.MAIN_V7)
    line['patience_counted'] = line['candidate']
    assert line['candidate'] is False and line['coverage'] is None
    assert 'rule' not in line and 'early_acceptance' not in line
    next_ctx = replace(ctx, round=2, history=[line])
    assert next_ctx.history[0]['coverage'] is None and next_ctx.training is ctx.training
    assert 'coverage' not in step._line(1, engineered, None, configuration=p.MAIN_V6)
