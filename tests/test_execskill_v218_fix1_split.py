"""Real split feedback over authored source trajectories, without providers or datasets."""
from copy import deepcopy
from types import SimpleNamespace

import pytest

from skillopt.coevo5.calls import _request_hash
from skillopt.continual_eval.core import write_json
from skillopt.execskill import confirm, profiles as p, solver, step, trajectories, v218_split as split
from skillopt.execskill.package import FIXTURE, empty, with_
from tests.execskill_fakes_env import Script, procedure
from tests.execskill_v293_fakes import tmp_path  # noqa: F401
from tests.test_execskill_v218_split import FixtureStep, cell
from tests.test_execskill_zpc_pipeline import SourceWorker, workers


def scenario(tmp_path, monkeypatch):
    incumbent = empty(step='G/s2-officeqa', evidence=FIXTURE)
    a = procedure('fx-v218-note-a', ('applies', 'before_call'), origin='zebralogic', source='''
def applies(view):
    return True
def before_call(view, state):
    return {"facts": ["Clue 6 compares positions."], "diagnostics": ["A compared clue positions."]}
''')
    b = procedure('fx-v218-note-b', ('applies', 'before_call'), origin='zebralogic', source='''
def applies(view):
    return True
def before_call(view, state):
    if "Confirmation" in view["question"]:
        return {"facts": ["Recheck the relative ordering."]}
    return None
''')
    full = with_(incumbent, step='G/s3-zebralogic', add=(a, b))
    st = FixtureStep(tmp_path, incumbent)
    st.setting.cards = {'zebralogic': 'Use the public clues.'}
    st.services = SimpleNamespace(item_workers=None, workers=workers)
    cut = {kind: [{'task_id': 'authored-' + kind, 'public': {
        'question': 'There are 2 houses, numbered 1 to 2 from left to right, as seen from across the street. '
                    'Clue 6 compares positions. ' + ('Confirmation' if kind == 'confirm' else 'Training'),
        'columns': ['Name']}, 'private': {}}] for kind in ('run', 'confirm')}
    # The regression concerns attribution, not reference disclosure; no reference files/registry are opened.
    monkeypatch.setattr(step, '_references', lambda *args, **kwargs: {})

    def produce(attempt, unit, arm, package, key, public):
        held = 'Confirmation' in public['question']
        token = 'pass' if a.id in package.order and not (held and b.id in package.order) else 'fail'
        script = Script(['{"solution": {}}'])
        prediction = solver.solve(st.bench, public, st.setting.cards[st.bench], package, script,
                                  worker=SourceWorker(), configuration=p.MAIN_V6)
        assert len(script.requests) == 1 and not prediction['shell']['faults']
        found = cell(unit, arm, key, token)
        fields = {k: v for k, v in found.items() if k not in ('version', p.RECORD_HASH, 'evidence')}
        fields['cell'] = {**found['cell'], 'benchmark': st.bench}
        fields['package_sha256'] = package.sha256
        found = p.record('cell-v2-3', FIXTURE, fields)
        calls = [{'purpose': 'first', 'system': system, 'user': user,
                  'request_sha256': _request_hash(system, user), 'receipt': receipt}
                 for (system, user), receipt in zip(script.requests, script.receipts)]
        trace = trajectories.build(found['cell'], evidence=FIXTURE,
            arm_kind='candidate' if arm == "S'" else 'parent', package_sha256=package.sha256,
            calls=calls, prediction=prediction, judge=found['judge'], deciding=0, worst='delivered',
            logical_calls=1, dispatch_ts=0, finish_ts=1, configuration=p.MAIN_V6)
        write_json(attempt / 'cells' / (found['cell']['id'] + '.json'), found)
        trajectories.write(attempt, trace['cell'], trace)
        return found

    dispatched = []

    def dispatch(st, attempt, endpoint, unit, jobs, **kwargs):
        result = []
        for arm, chosen, key, run, task in jobs:
            assert run == 0
            dispatched.append((unit, arm, key))
            result.append(produce(attempt, unit, arm, chosen.package, key, task['public']))
        return result

    monkeypatch.setattr(step, '_cells', dispatch)
    sources = []
    for kind in ('run', 'confirm'):
        unit_name = ('train' if kind == 'run' else 'confirm') + '-r1'
        unit = st.label(unit_name)
        publics = {st.bench + '/' + item['task_id']: item['public'] for item in cut[kind]}
        views = [(key, solver.routing_view(st.bench, public)) for key, public in publics.items()]
        signatures = step._pair_signatures(st, full, incumbent, publics, views)
        attempt = st.chain_root / 's3-zebralogic' / unit_name / 'attempt-1'
        cells = {(arm, key): [produce(attempt, unit, arm, package, key, public)]
                 for key, public in publics.items() for arm, package in (('S', incumbent), ("S'", full))}
        source = {'candidate_sha256': full.sha256, 'request_signatures': signatures,
                  'incumbent_cells': {key: rows for (arm, key), rows in cells.items() if arm == 'S'},
                  'candidate_cells': {key: rows for (arm, key), rows in cells.items() if arm == "S'"}}
        if kind == 'run':
            verdict = step.train_verdict(cells, list(publics), [], set(full.order), predicate_faults=0,
                routed=len(publics), sign=step.TRAIN_SIGN[p.MAIN_V6], configuration=p.MAIN_V6, runs=1)
            source.update(adopted=verdict['adopted'], verdict=verdict, feedback={})
        else:
            source.update(confirm=confirm.verdict(cells, list(publics), items=len(publics)),
                          slice_ids=[item['task_id'] for item in cut[kind]])
        sources.append(source)
    return st, cut, full, sources, dispatched


def test_split_full_candidate_empty_b_note_reuses_real_feedback_and_resumes(tmp_path, monkeypatch):
    st, cut, full, (training, confirmation), dispatched = scenario(tmp_path, monkeypatch)
    assert training['adopted'] and not confirmation['confirm']['passed']
    source_files = sorted((tmp_path / 's3-zebralogic' / 'train-r1').glob('attempt-1/*/*.json'))
    source_before = {path: path.read_bytes() for path in source_files}
    source_snapshot = deepcopy(training)
    key = 'zebralogic/authored-run'
    source_cell = training['candidate_cells'][key][0]
    source_trace = split.source_trajectories(st, {("S'", key): [source_cell]})[source_cell['cell']['id']]
    assert source_cell['package_sha256'] == source_trace['package_sha256'] == full.sha256
    assert [note['id'] for note in source_trace['shell']['notes']] == list(full.order)
    assert source_trace['shell']['notes'][1]['fields'] == {}
    current = list(split.source_trajectories(st,
        {('S', key): training['incumbent_cells'][key]}).values())
    engineered = {'engineer': {'changes': [{'id': pid, 'kind': 'new', 'target': None} for pid in full.order]}}

    selected, result = split.run(st, cut, 1, st.parent, full, engineered, training, confirmation, None,
                                 current=current)
    assert selected.order == (full.order[0],) and result['adopted']
    assert result['split_winner'] == full.order[0]
    train = st.done('train-r1-split-p1')
    assert train['cells'] == 0
    assert train['cell_rules'][key]["S'"]['rule'] == 'identical_to_candidate'
    assert train['candidate_cells'][key] == [source_cell]
    assert train['candidate_sha256'] == selected.sha256 != source_trace['package_sha256']
    rows = train['feedback']['procedures']
    assert [row['id'] for row in rows] == [full.order[0]]
    assert rows[0]['enabled_items'] == rows[0]['fixed'] == 1
    assert rows[0]['notes_coverage']['items'] == rows[0]['notes_coverage']['with_notes'] == 1
    assert rows[0]['notes_coverage']['fields']['facts'] == 1
    assert rows[0]['notes_coverage']['faults'] == 0
    assert rows[0]['examples'][0]['cell'] == source_trace['cell']
    assert rows[0]['examples'][0]['notes'] == step._notes_text(source_trace)
    diagnostics = train['feedback']['engineer_diagnostics']
    assert diagnostics['items_count'] == 1 and diagnostics['items'][0]['records'] == 1
    assert 'A compared clue positions.' in str(diagnostics)
    assert full.order[1] not in str(train['feedback'])
    assert len(dispatched) == 1 and dispatched[0][0] == st.label('confirm-r1-split-p1')

    # A completed retry does no work; a lost completion re-observes the subcandidate and reuses the source again.
    assert split.run(st, cut, 1, st.parent, full, engineered, training, confirmation, None,
                     current=current) == (selected, result)
    st.results.pop('train-r1-split-p1')
    resumed = split.run(st, cut, 1, st.parent, full, engineered, training, confirmation, None, current=current)
    assert resumed == (selected, result) and len(dispatched) == 1
    assert st.attempts['train-r1-split-p1'] == 2
    assert training == source_snapshot
    assert {path: path.read_bytes() for path in source_files} == source_before


def test_reused_source_capture_is_main_v6_only(tmp_path, monkeypatch):
    st, cut, full, (training, _), _ = scenario(tmp_path, monkeypatch)
    candidate = split.subcandidate(st.parent, st.parent, full, full.procedures[0], [])
    key = 'zebralogic/authored-run'
    cells = {("S'", key): training['candidate_cells'][key]}
    made = split.source_trajectories(st, cells)
    captured = {key: {'request_sha256': training['request_signatures'][key]["S'"]['request_sha256'],
        'fields': {candidate.order[0]: {'facts'}}, 'candidate_sha256': candidate.sha256,
        'source_cells': [cells[("S'", key)][0]['cell']['id']]}}
    st.setting.extra['configuration'] = p.MAIN_V5
    with pytest.raises(ValueError, match="source package's first-note hooks"):
        step._notes_coverage(st, candidate.order[0], [key], candidate, cells, made, [], set(), captured)
