"""Authored cells exercise the production card controller, supply and resume."""
from copy import deepcopy
from fractions import Fraction
from types import SimpleNamespace

import pytest

from skillopt.continual_eval.core import read_json, write_json
from skillopt.execskill import profiles as p, rounds, step, v222_cards, v225_cards as cards, v225_phase as phase
from skillopt.execskill.package import empty, save
from skillopt.validator_pilot.api import digest
from tests.execskill_v293_fakes import tmp_path  # noqa: F401
from tests.test_execskill_v221_learning import Registry, signature


def authored_pool(bench, count, prefix):
    return [{'task_id': '%s-%03d' % (prefix, i), 'benchmark': bench, 'partition': 'practice',
             'public': {'question': 'Authored item %d?' % i, 'index': i},
             'private': {'answer': 'authored'}} for i in range(count)]


class AuthoredStep:
    """Disk-backed completed-unit receipts, with authored dispatch instead of a model."""
    def __init__(self, root, bench='searchqa', parent=None):
        self.chain, self.bench = 'G', bench
        self.k = p.MAIN_V5_ORDER.index(bench) + 1
        self.chain_root = root / 'G'
        self.root = self.chain_root / ('s%d-%s' % (self.k, bench))
        self.root.mkdir(parents=True, exist_ok=True)
        self.name = 'G/s%d-%s' % (self.k, bench)
        self.parent = parent or empty(step='G/s0', evidence='engineering_fixture')
        self.namespace, self.evidence, self.smoke = 'G-v9', 'engineering_fixture', None
        spec = p.slice_spec(p.MAIN_V9, bench)
        self.cut = {'run': authored_pool(bench, spec['run'][0], 'practice'),
                    'accept': authored_pool(bench, spec['accept'][0], 'decision'),
                    'confirm-r1': authored_pool(bench, 40 if bench == p.ZEBRA else 4, 'slice'),
                    'accept_probe': []}
        self.setting = SimpleNamespace(extra={'configuration': p.MAIN_V9}, root=root,
            runtime={b: {} for b in p.MAIN_V5_ORDER},
            pools={bench: self.cut['run'] + self.cut['accept'] + self.cut['confirm-r1']},
            cards={bench: v222_cards.format_text(bench)})
        self.services = SimpleNamespace(registry=Registry())
        self.invocations, self.dispatches, self.writes, self.trajectories, self.cross = [], [], [], {}, []
        save(self.chain_root, self.parent)

    def runtime(self): return {}
    def label(self, name): return self.name + '/' + name
    def solver(self, kind, attempt): return None
    def roles(self, role): return role
    def purpose(self, kind): return kind
    def done(self, name):
        path = self.root / name / 'unit.json'
        return p.verified(read_json(path), 'unit')['result'] if path.is_file() else None
    def unit(self, name, work, *, benches=(), settle=None):
        assert name in step.training_units(p.MAIN_V9)
        found = self.done(name)
        if found is not None:
            return found
        self.invocations.append(name)
        attempt = self.root / name / 'attempt-1'
        attempt.mkdir(parents=True, exist_ok=True)
        result = work(attempt)
        write_json(attempt.parent / 'unit.json', p.record('unit', self.evidence, {'result': result}))
        if settle:
            settle(attempt, result)
        return result


def wire(monkeypatch, st, decisions=None, static_rounds=()):
    from skillopt.execskill import v225_writer, v222_runtime
    decisions = decisions or {}
    run_rows = [{'task_id': rounds.key(st.bench, row['task_id']), 'bench': st.bench,
                 'unit': st.label('run'), 'arm': 'S', 'token': 'fail', 'run': run,
                 'view': row['public'], 'reply': 'Authored attempt', 'evidence': 'engineering_fixture'}
                for row in st.cut['run'] for run in range(p.slice_spec(p.MAIN_V9, st.bench)['run'][1])]
    monkeypatch.setattr(step, '_run_trajectories', lambda *a, **kw: deepcopy(run_rows))
    monkeypatch.setattr(step, '_unit_trajectories', lambda _st, name: deepcopy(st.trajectories.get(name, [])))
    monkeypatch.setattr(step, '_references', lambda *a, **kw: {})
    monkeypatch.setattr(step, '_corpora', lambda *a: [])
    monkeypatch.setattr(step.solver, 'routing_view', lambda b, public, **kw: public)
    def signatures(_st, candidate, incumbent, publics, views, **kw):
        return {key: {'S': signature([key, cards.compose(st.bench, 'Fixed format.', incumbent)]),
                      "S'": signature([key, cards.compose(st.bench, 'Fixed format.', candidate)])}
                for key in publics}
    monkeypatch.setattr(step, '_pair_signatures', signatures)
    def write(role, **kw):
        st.writes.append(deepcopy({key: value for key,value in kw.items() if key != 'incumbent'}))
        assert role == 'card_writer'
        if kw['c'] > 1:
            assert isinstance(kw['previous_card'], str)
        if kw['c'] in static_rounds:
            text, violation = None, 'length'
        else:
            text, violation = 'Compare the supplied evidence carefully. Revision %d.' % kw['c'], None
        return {'text': text, 'static': violation, 'call_record': p.record('card-writer', st.evidence,
            {'card': text, 'round': kw['c']}), 'writer_sha256': '0'*64}
    monkeypatch.setattr(v225_writer, 'write', write)
    def dispatch(_st, attempt, endpoint, unit, jobs, **kw):
        name = unit.rsplit('/',1)[-1]
        st.dispatches.append((name, [(arm,key,run) for arm,_,key,run,_ in jobs]))
        unique = list(dict.fromkeys(key for _,_,key,_,_ in jobs))
        fixed, broken = decisions.get(name, (max(3, -(-len(unique)//20)), 0))
        found, trajectories = [], []
        for arm, selected, key, run, task in jobs:
            index = unique.index(key)
            passed = (index < fixed and arm == "S'") or (fixed <= index < fixed+broken and arm == 'S')
            token = 'pass' if passed else 'fail'
            cell = {'cell': {'id': digest([unit,arm,key,run]), 'arm': arm, 'task_id': key, 'run': run},
                    'judge': {'v2': {'token': token}}, 'faults': [], 'stop': None,
                    'final': {'outcome': token, 'kind': 'score', 'remedy': None}}
            found.append(cell)
            trajectories.append({'task_id': key, 'bench': st.bench, 'unit': unit, 'arm': arm,
                'token': token, 'run': run, 'cell': cell['cell']['id'], 'view': task['public'],
                'reply': 'Authored outcome', 'evidence': 'engineering_fixture'})
        st.trajectories[name] = trajectories
        return found
    monkeypatch.setattr(step, '_cells', dispatch)
    def cross(_st, attempt, *, unit, phase, parent, candidate):
        st.cross.append((phase, parent.sha256, candidate.sha256))
        # Own acceptance identity is authored; cross transfer rejects by default.
        passed = phase == 'acceptance'
        return (candidate if passed else None), p.record('v222-cross-gate', st.evidence,
            {'configuration': p.MAIN_V9, 'phase': phase, 'passed': passed,
             'parent_sha256': parent.sha256, 'proposed_sha256': candidate.sha256,
             'candidate_sha256': candidate.sha256 if passed else None})
    monkeypatch.setattr(v222_runtime, 'cross_gate', cross)
    return run_rows


@pytest.mark.parametrize('touched,fixed,broken,expected,floor', [
    (300,30,15,'accept',15), (300,29,15,'reject',15),
    (40,5,2,'accept',3), (40,4,2,'reject',3),
    (18,3,0,'accept',3), (18,2,0,'reject',3),
    (32,3,0,'accept',3), (60,3,0,'accept',3),
    (31,3,0,'accept',3), (36,3,0,'accept',3),
    (100,15,10,'accept',5), (100,16,11,'reject',5)])
def test_overlay_five_percent_worked_decisions(touched, fixed, broken, expected, floor):
    result = phase.counts(touched=touched, fixed=fixed, broken=broken, batch=touched)
    assert result['decision'] == expected and result['gain_floor'] == floor


def test_card_floor_whole_batch_and_full_touch_contract():
    assert phase.counts(touched=40,fixed=5,broken=2,batch=40,whole_batch=Fraction(-1,100))['decision'] == 'accept'
    assert phase.counts(touched=40,fixed=5,broken=2,batch=40,whole_batch=Fraction(-11,1000))['clause'] == 'whole_batch'
    with pytest.raises(ValueError,match='full registered batch'):
        phase.counts(touched=39,fixed=5,broken=2,batch=40)
    from skillopt.execskill import v221_rule
    assert v221_rule.counts(touched=300,fixed=30,broken=15,batch=300)['decision'] == 'reject'


@pytest.mark.parametrize('bench,consumed,skip', [('searchqa',100,False), ('officeqa',32,True),
                                                ('zebralogic',40,False), ('spreadsheetbench',36,True)])
def test_first_acceptance_stops_and_registered_supply_is_consumed(tmp_path, monkeypatch, bench, consumed, skip):
    st = AuthoredStep(tmp_path, bench); wire(monkeypatch, st)
    parent, record = phase.card_phase(st, st.cut)
    assert parent.card_for(bench) is not None and len(record['rounds']) == 1
    assert record['rounds'][0]['decision'] == 'accept'
    assert len(record['consumed_acceptance']) == consumed
    assert not set(record['consumed_acceptance']) & {row['task_id'] for row in st.cut['confirm-r1']}
    assert record['procedure_phase'] == ('skipped_pool_exhausted' if skip else 'run')
    assert record['accepted_training_unit'] == 'card-train-c1'
    assert len(st.writes) == 1
    assert all(mode == 'acceptance' or mode == 'cross_card' for mode,_,_ in st.cross)
    if bench != 'searchqa':
        assert record['rounds'][0]['confirmation'] == 'not_applicable_supply'
        assert not any(name.startswith('card-confirm') for name in st.invocations)
    else:
        confirm = read_json(st.root/'card-confirm-selection-c1.json')
        accept = read_json(st.root/'card-accept-selection-c1.json')
        assert confirm['examined'] == [row['task_id'] for row in st.cut['accept'][:40]]
        assert accept['examined'] == [row['task_id'] for row in st.cut['accept'][40:100]]


def test_training_revisions_reuse_only_unchanged_parent_and_every_candidate_is_fresh(tmp_path, monkeypatch):
    st=AuthoredStep(tmp_path); wire(monkeypatch,st, {'card-train-c1':(14,0),'card-train-c2':(14,0)})
    _,record=phase.card_phase(st,st.cut)
    assert len(record['rounds']) == 3 and record['rounds'][-1]['decision'] == 'accept'
    training={name:jobs for name,jobs in st.dispatches if name.startswith('card-train')}
    assert len(training['card-train-c1']) == 600
    assert len(training['card-train-c2']) == len(training['card-train-c3']) == 300
    assert all(arm == "S'" for c in (2,3) for arm,_,_ in training['card-train-c%d'%c])
    assert st.done('card-train-c2')['reused_cells'] == st.done('card-train-c3')['reused_cells'] == 300
    assert {row['unit'] for row in st.writes[1]['rows']} == {st.label('card-train-c1')}
    assert {row['unit'] for row in st.writes[2]['rows']} == {st.label('card-train-c2')}
    assert all(row['arm'] == "S'" for kw in st.writes[1:] for row in kw['rows'])


@pytest.mark.parametrize('stage', ['confirmation','acceptance'])
def test_searchqa_rejects_then_consumes_a_new_acceptance_prefix(tmp_path, monkeypatch, stage):
    st=AuthoredStep(tmp_path)
    name='card-confirm-c1' if stage == 'confirmation' else 'card-accept-c1'
    wire(monkeypatch,st,{name:(2,0)})
    _,record=phase.card_phase(st,st.cut)
    assert len(record['rounds']) == 2 and record['rounds'][0][stage]['decision'] == 'reject'
    assert len(record['consumed_acceptance']) == (140 if stage == 'confirmation' else 200)
    selections=[read_json(path)['examined'] for path in st.root.glob('card-*-selection-c*.json')]
    assert sum(map(len,selections)) == len(set(key for ids in selections for key in ids))


@pytest.mark.parametrize('bench', ['officeqa','zebralogic','spreadsheetbench'])
def test_single_acceptance_failure_ends_card_phase_without_recycling(tmp_path, monkeypatch, bench):
    st=AuthoredStep(tmp_path,bench); wire(monkeypatch,st,{'card-accept-c1':(2,0)})
    package,record=phase.card_phase(st,st.cut)
    assert package.sha256 == st.parent.sha256 and len(record['rounds']) == 1
    assert record['rounds'][0]['decision'] == 'card_supply_exhausted'
    assert len(record['consumed_acceptance']) == phase.CARD_ACCEPT_ITEMS[bench]
    if bench != 'zebralogic':
        monkeypatch.setattr(step,'_engineer_train',lambda *a,**kw:pytest.fail('Exhausted pool must skip procedures'))
        assert step._train(st,st.cut,None) == (package,[],None)


def test_static_rejection_still_counts_a_round_and_revision_has_a_previous_string(tmp_path, monkeypatch):
    st=AuthoredStep(tmp_path);wire(monkeypatch,st,static_rounds=(1,))
    _,record=phase.card_phase(st,st.cut)
    assert len(record['rounds']) == 2
    assert record['rounds'][0]['decision'] == 'card_rejected_static'
    assert st.writes[1]['previous_card'] == ''
    assert st.writes[1]['result']['stage'] == 'static'
    assert 'card-train-c1' not in st.invocations


def test_all_rounds_rejected_keep_parent_and_leave_acceptance_untouched(tmp_path, monkeypatch):
    st=AuthoredStep(tmp_path);wire(monkeypatch,st,{f'card-train-c{c}':(2,0) for c in (1,2,3)})
    package,record=phase.card_phase(st,st.cut)
    assert package.sha256 == st.parent.sha256 and record['final_card'] is None
    assert len(record['rounds']) == 3 and record['consumed_acceptance'] == []


def test_current_procedure_evidence_starts_with_accepted_card_candidate_cells(tmp_path, monkeypatch):
    st=AuthoredStep(tmp_path);wire(monkeypatch,st)
    phase.card_phase(st,st.cut)
    current=step._current(st,[])
    assert len(current) == len(st.cut['run'])
    assert {row['unit'] for row in current} == {st.label('card-train-c1')}
    assert {row['arm'] for row in current} == {"S'"}
    assert p.train_patience(p.MAIN_V9) == p.train_patience(p.MAIN_V8) == 4


@pytest.mark.parametrize('pause_after', ['card-write-c1','card-train-c1','card-confirm-c1','card-accept-c1','card-cross-officeqa'])
def test_every_card_unit_resumes_without_repeating_completed_dispatch(tmp_path, monkeypatch, pause_after):
    st=AuthoredStep(tmp_path);wire(monkeypatch,st)
    original=st.unit
    def interrupted(name,work,**kw):
        result=original(name,work,**kw)
        if name==pause_after:
            raise RuntimeError('authored process stop after committed unit')
        return result
    st.unit=interrupted
    with pytest.raises(RuntimeError,match='authored process stop'):
        phase.card_phase(st,st.cut)
    before=list(st.invocations);dispatched=deepcopy(st.dispatches)
    st.unit=original
    package,record=phase.card_phase(st,st.cut)
    assert package.card_for('searchqa') is not None
    assert len(st.invocations)==len(set(st.invocations))
    assert st.invocations[:len(before)]==before
    assert st.dispatches[:len(dispatched)]==dispatched
    calls=len(st.invocations)
    again,other=phase.card_phase(st,st.cut)
    assert again.sha256==package.sha256 and other==record and len(st.invocations)==calls


def test_selection_resume_refuses_changed_parent_candidate_or_pool(tmp_path, monkeypatch):
    st=AuthoredStep(tmp_path);wire(monkeypatch,st)
    candidate=phase.place_card(st.parent,cards.make_card('searchqa','Carefully compare evidence.'),step=st.name)
    selected,_=phase.select(st,st.cut,1,'confirm',st.parent,candidate)
    assert len(selected)==40
    changed={**st.cut,'accept':list(reversed(st.cut['accept']))}
    with pytest.raises(ValueError,match='original packages and practice pool'):
        phase.select(st,changed,1,'confirm',st.parent,candidate)


def test_trained_keeps_accepted_card_when_pool_exhaustion_skips_all_procedures(tmp_path, monkeypatch):
    st=AuthoredStep(tmp_path,'officeqa');wire(monkeypatch,st)
    monkeypatch.setattr(step,'_engineer_train',lambda *a,**kw:pytest.fail('Exhausted pool ran engineer'))
    checked=[]
    monkeypatch.setattr(step,'_selftest',lambda _st,name,candidate,generated:(
        checked.append(candidate.sha256) or {'blocked':False}))
    candidate,outcome,training=step._trained(st,st.cut,None)
    assert candidate.card_for('officeqa') is not None and checked==[candidate.sha256]
    assert outcome['decision']=='accept' and outcome['accepted_rounds']==[]
    assert training['rounds']==[] and training['acceptance_binding']['action']=='rollback_to_accepted_card'
    assert training['audit_final']['audit_final']['reason']=='no_added_or_revised_procedures'


def test_static_rejection_after_a_training_rejection_restores_only_original_run_examples(tmp_path, monkeypatch):
    from skillopt.execskill import v225_writer
    st = AuthoredStep(tmp_path)
    wire(monkeypatch, st, {'card-train-c1': (2, 0)}, static_rounds=(2,))
    phase.card_phase(st, st.cut)
    third = st.writes[2]
    assert {row['unit'] for row in third['rows']} == {st.label('run')}
    assert all(row['arm'] == 'S' for row in third['rows'])
    # Exercise the real provenance selector, rather than only the mocked writer.
    v225_writer.select_examples(third['rows'], chain=st.chain, bench=st.bench, k=st.k, c=3,
        references={}, allowed_ids=third['allowed_ids'])


@pytest.mark.parametrize('bench', ['searchqa', 'officeqa'])
def test_accepted_cross_cards_rebase_for_real_engineer_context_and_no_procedure_path(tmp_path, monkeypatch, bench):
    from contextlib import nullcontext
    from skillopt.execskill import engineer, engineer_v211, units, v222_gate, v222_runtime
    from skillopt.execskill.package import load, validate
    from tests.test_execskill_v225_cross_card import slices, inspector, paired
    st = AuthoredStep(tmp_path, bench)
    original_rows = wire(monkeypatch, st)
    def cross(_st, attempt, *, unit, phase, parent, candidate):
        return v222_gate.check(home=bench, parent=parent, candidate=candidate, slices=slices(),
            inspector=inspector, run_pairs=lambda b, old, new, items: paired(items, 3, 0),
            phase=phase, configuration=p.MAIN_V9)
    monkeypatch.setattr(v222_runtime, 'cross_gate', cross)
    candidate, record = phase.card_phase(st, st.cut)
    assert candidate.parent_sha256 == st.parent.sha256
    validate(candidate, st.parent)
    handoff = record['handoff']
    gated = load(st.chain_root/'packages'/(handoff['selected_package_sha256']+'.json'))
    assert gated.sha256 != candidate.sha256
    assert [proc.to_json() for proc in candidate.procedures] == [proc.to_json() for proc in gated.procedures]
    assert handoff['package_sha256'] == candidate.sha256
    assert handoff['cross_gate_bindings'][-1]['proposed_sha256'] == gated.sha256
    assert handoff['cross_gate_bindings'][-1]['selected_package_sha256'] == gated.sha256
    assert phase.card_phase(st, st.cut)[0] == candidate
    def sealed(row, *, parent=False):
        return p.record('trajectory', st.evidence, {**{k:v for k,v in row.items() if k != 'evidence'},
            'cell': row.get('cell', digest([row['unit'], row['task_id'], row['run']])),
            'arm_kind': 'parent' if parent else 'candidate'})
    context = engineer.Context(bench=bench, k=st.k, step=st.name, evidence=st.evidence,
        parent=candidate, trajectories=[sealed(row, parent=True) for row in original_rows], corpora={},
        workers=None, roles=None, label=st.label('engineer-r1'), card=st.setting.cards[bench],
        mode=engineer.TRAIN, round=1, base=st.parent,
        current=[sealed(row) for row in step._current(st, [])], configuration=p.MAIN_V9)
    assert context.parent == candidate
    if bench == 'officeqa':
        monkeypatch.setattr(step, '_engineer_train', lambda *a, **kw: pytest.fail('Exhausted pool ran engineer'))
        monkeypatch.setattr(step, '_selftest', lambda *a, **kw: {'blocked': False})
        selected, outcome, training = step._trained(st, st.cut, None)
        assert selected.sha256 == candidate.sha256 and outcome['decision'] == 'accept'
        assert training['rounds'] == [] and training['acceptance_binding']['action'] == 'rollback_to_accepted_card'
        return
    run_rows = [sealed(row, parent=True) for row in original_rows]
    monkeypatch.setattr(step, '_run_trajectories', lambda *a, **kw: run_rows)
    monkeypatch.setattr(step, '_unit_trajectories', lambda _st, name:
        [sealed(row) for row in st.trajectories.get(name, [])])
    monkeypatch.setattr(step, '_earlier', lambda *a, **kw: [])
    monkeypatch.setattr(step, '_inputs_dirs', lambda *a, **kw: nullcontext({}))
    monkeypatch.setattr(step, '_item_workers', lambda *a, **kw: lambda *args: nullcontext())
    monkeypatch.setattr(step, '_previous', lambda *a: None)
    monkeypatch.setattr(step.detectors, 'diagnosis', lambda *a, **kw: {})
    monkeypatch.setattr(step.detectors, 'counts', lambda *a: {})
    monkeypatch.setattr(units, 'audit_judges', lambda *a: {})
    st.services.workers = st.services.item_workers = None
    st.setting.extra['v211_prompt_pins'] = engineer_v211.pins()
    observed = []
    def train(ctx):
        assert isinstance(ctx, engineer.Context)
        assert ctx.base == st.parent and ctx.parent == candidate
        assert len(ctx.current) == len(st.cut['run'])
        assert {row['unit'] for row in ctx.current} == {st.label('card-train-c1')}
        observed.append(ctx)
        return None, {'changes': [], 'analysis': {'items': []}, 'disclosed': [], 'lint': []}
    monkeypatch.setattr(engineer, 'run_train', train)
    result = step._engineer_train(st, st.cut, 1, candidate, done=[], fed=None, history=[], training=None,
        lint=[], reserved=frozenset(), analysed=frozenset(), disclosed=frozenset(), generated=None)
    assert result['candidate_sha256'] is None and len(observed) == 1


@pytest.mark.parametrize('bench', ['officeqa', 'spreadsheetbench'])
def test_identical_inherited_guidance_cannot_win_favorable_noise_or_consume_supply(tmp_path, monkeypatch, bench):
    from skillopt.execskill import v225_writer
    base = empty(step='G/s0', evidence='engineering_fixture')
    text = 'Compare the supplied evidence carefully.'
    inherited = phase.place_card(base, cards.make_card('searchqa', text, route=bench), step='G/s1-searchqa')
    st = AuthoredStep(tmp_path, bench, parent=inherited)
    wire(monkeypatch, st, {f'card-accept-c{c}': (phase.CARD_ACCEPT_ITEMS[bench], 0) for c in (1,2,3)})
    def same_card(role, **kw):
        st.writes.append(kw)
        return {'text': text, 'static': None, 'call_record': p.record('card-writer', st.evidence, {'card': text}),
                'writer_sha256': '0'*64}
    monkeypatch.setattr(v225_writer, 'write', same_card)
    candidate, record = phase.card_phase(st, st.cut)
    assert candidate == inherited and record['final_card'] is None
    assert len(st.writes) == 3 and all(row['decision'] == 'card_unchanged' for row in record['rounds'])
    assert record['consumed_acceptance'] == [] and record['procedure_phase'] == 'run'
    assert st.dispatches == [] and st.services.registry.calls == []
    assert not list(st.root.glob('card-*-selection-c*.json'))


@pytest.mark.parametrize('bench', ['officeqa', 'spreadsheetbench'])
def test_partially_unchanged_acceptance_requests_are_screened_without_consuming_read(tmp_path, monkeypatch, bench):
    st = AuthoredStep(tmp_path, bench); wire(monkeypatch, st)
    original = step._pair_signatures
    def signatures(_st, candidate, incumbent, publics, views, **kw):
        found = original(_st, candidate, incumbent, publics, views, **kw)
        for key, pair in found.items():
            if key.startswith('decision-') and key.endswith('000'):
                pair["S'"] = pair['S']
        return found
    monkeypatch.setattr(step, '_pair_signatures', signatures)
    candidate, record = phase.card_phase(st, st.cut)
    assert candidate == st.parent and record['final_card'] is None
    assert all(row['decision'] == 'card_not_full_touch' for row in record['rounds'])
    assert record['consumed_acceptance'] == [] and record['procedure_phase'] == 'run'
    assert st.services.registry.calls == []
    assert not any(name.startswith('card-accept') for name, _ in st.dispatches)
    for c in (1,2,3):
        row = read_json(st.root/f'card-accept-selection-c{c}.json')
        assert row['examined'] == [] and len(row['screened']) == phase.CARD_ACCEPT_ITEMS[bench]
        assert len(row['touched']) == phase.CARD_ACCEPT_ITEMS[bench]-1


def test_favorable_identical_request_outcomes_never_establish_card_gain():
    from tests.test_execskill_v221_learning import paired
    keys, favorable = paired(fixed=32)
    signatures = {key: {'S': signature(key), "S'": signature(key)} for key in keys}
    result = phase.decide(favorable, keys, signatures=signatures)
    assert result['decision'] == 'reject' and result['fixed'] == result['touched'] == 0
    assert result['reason'] == 'not_full_touch'


def test_rendered_request_identity_blocks_dispatch_even_when_raw_card_text_differs(tmp_path, monkeypatch):
    st = AuthoredStep(tmp_path, 'officeqa'); wire(monkeypatch, st)
    monkeypatch.setattr(step, '_pair_signatures', lambda _st, candidate, incumbent, publics, views, **kw:
        {key: {'S': signature(key), "S'": signature(key)} for key in publics})
    candidate, record = phase.card_phase(st, st.cut)
    assert candidate == st.parent and all(row['decision'] == 'card_not_full_touch' for row in record['rounds'])
    assert st.dispatches == [] and st.services.registry.calls == [] and record['consumed_acceptance'] == []


@pytest.mark.parametrize('bench', ['officeqa', 'spreadsheetbench'])
def test_acceptance_rechecks_full_request_changes_before_registry_dispatch(tmp_path, monkeypatch, bench):
    st = AuthoredStep(tmp_path, bench); wire(monkeypatch, st)
    candidate = phase.place_card(st.parent, cards.make_card(bench, 'Compare the supplied evidence.'), step=st.name)
    monkeypatch.setattr(step, '_pair_signatures', lambda _st, candidate, incumbent, publics, views, **kw:
        {key: {'S': signature(key), "S'": signature(key)} for key in publics})
    result = phase.acceptance(st, st.cut, candidate, unit='card-accept-c1', incumbent=st.parent)
    assert result['decision'] == 'reject' and result['reason'] == 'not_full_touch'
    assert result['cells'] == 0 and st.dispatches == [] and st.services.registry.calls == []


def test_phase_retry_after_second_writer_reply_replays_durable_calls_without_transport(tmp_path, monkeypatch):
    from skillopt.execskill import v225_writer
    from tests.test_execskill_v225_writer import FakeRoles
    real_write = v225_writer.write
    st = AuthoredStep(tmp_path); wire(monkeypatch, st)
    monkeypatch.setattr(v225_writer, 'write', real_write)
    initial = FakeRoles(['<answer>Invalid format</answer>', 'Compare the supplied evidence carefully.'])
    st.roles = lambda role: initial
    persist = phase.write_json
    interrupted = []
    def publish(path, value):
        if path.name == 'card-writer.json' and not interrupted:
            interrupted.append(path)
            raise OSError('Authored failure after the second persisted writer reply')
        return persist(path, value)
    monkeypatch.setattr(phase, 'write_json', publish)
    with pytest.raises(OSError, match='second persisted writer reply'):
        phase.card_phase(st, st.cut)
    assert len(initial.calls) == 2
    assert len(list((st.chain_root/'card-writer'/'dispatches').glob('*.json'))) == 2
    assert len(list((st.chain_root/'card-writer'/'replies').glob('*.json'))) == 2
    resumed = FakeRoles([])
    st.roles = lambda role: resumed
    candidate, record = phase.card_phase(st, st.cut)
    assert candidate.card_for(st.bench) is not None and record['rounds'][0]['decision'] == 'accept'
    assert resumed.calls == [] and len(list((st.chain_root/'card-writer'/'dispatches').glob('*.json'))) == 2
    assert len(st.done('card-write-c1')['call_record']['calls']) == 2
