"""Readout of typed-v2 on synthetic open and sealed unit directories (fakes only; no network, no /data)."""
import builtins
import io
import json
import shutil
import tempfile
from pathlib import Path

import pytest

from skillopt.execskill.typed import ORDER, gates, library, readout, tasktypes, units

CANARY = 'CANARY-REPLY-TEXT-7f3a9c'
ITEMS = ['i%d' % i for i in range(10)]


@pytest.fixture
def tmp_path():
    """A neutral directory: pytest's own tmp_path carries the word 'test', which the sealed-path guard refuses."""
    root = Path('/tmp/typed2-neutral')
    root.mkdir(parents=True, exist_ok=True)
    made = Path(tempfile.mkdtemp(prefix='readout-', dir=root))
    try:
        yield made
    finally:
        shutil.rmtree(made, ignore_errors=True)


# ---- fixture builders ----------------------------------------------------------------------------------------
def mount_record(arm, *, typed=False, card=None, programs=()):
    return {'signature': 'question/context', 'type': 't01' if typed else None, 'source': 'src-aaaaaaaa' if typed else None,
            'distance': 0.5 if typed else None, 'unknown_reason': None if typed else 'unseen_signature',
            'card_skill': card, 'system_card_sha256': 'f' * 64, 'programs_offered': list(programs),
            'selection': {'use': list(programs), 'status': 'ok', 'request_sha256': 'e' * 64, 'tokens': 12} if programs else None,
            'programs_enabled': list(programs), 'arm': arm, 'card_text': CANARY, 'system_card': CANARY}


def make_cell(bench, item, arm, correct, *, request=None, mount=None, token=None):
    token = token or ('pass' if correct else 'fail' if correct is False else 'unknown_fault')
    return {'bench': bench, 'item_id': item, 'arm': arm, 'correct': correct, 'token': token,
            'official': {'status': 'pass' if correct else 'fail', 'reason': None}, 'prediction_status': 'available',
            'output_excerpt': CANARY, 'reply': CANARY + ' ' + item,
            'format': {'answer_tag': True, 'retries': 0, 'note': CANARY}, 'flags': [] if correct else ['short_answer'],
            'fired': list((mount or {}).get('programs_enabled') or []), 'faults': [], 'tokens': 100,
            'sends': [{'request_sha256': 'r' * 64, 'system': CANARY, 'user': CANARY, 'receipt': {'ok': True, 'response': CANARY}}],
            'request_sha256': [request or 'sha-%s-%s-%s' % (bench, arm, item)], 'configuration_error': False,
            'infrastructure_unknown': token == 'unknown', 'failure': None, 'mount': mount or mount_record(arm)}


def write_unit(unit_dir, cells, *, sealed):
    (unit_dir / 'cells').mkdir(parents=True)
    for cell in cells:
        tag = units.cell_tag(cell['bench'], cell['item_id'], cell['arm'])
        units.write_json(unit_dir / 'cells' / (tag + '.json'), {**cell, 'tag': tag}, allow_sealed=sealed)
    units.write_json(unit_dir / 'done.json', {'unit': unit_dir.name, 'started': 't0', 'finished': 't1', 'cells': len(cells),
                     'expected_cells': len(cells), 'missing_cells': 0, 'stop_reason': None, 'ledger': {}}, allow_sealed=sealed)


def write_read(chain_dir, event, bench, outcomes, *, requests=None, mount=None, sealed=True):
    """A read unit (sealed by name) with one cell per item plus its open counts-only mirror."""
    arm = 'F' if event.startswith('S') else event
    cells = [make_cell(bench, item, arm, correct, request=(requests or {}).get(item), mount=mount)
             for item, correct in outcomes.items()]
    name = ('test-read-' if sealed else 'practice-read-') + event + '-' + bench
    write_unit(chain_dir / name, cells, sealed=sealed)
    typed = 1.0 if (mount or {}).get('type') else 0.0
    units.write_json(chain_dir / 'read-status' / ('%s-%s.json' % (event, bench)), {  # reads.mirror's shape
        'kind': 'read-status', 'event': event, 'bench': bench, 'arm': arm, 'unit': name, 'status': 'complete',
        'stop_reason': None, 'items': len(cells), 'cells': len(cells), 'expected_cells': len(cells), 'missing_cells': 0,
        'unknown': sum(c is None for c in outcomes.values()),
        'unknown_by_kind': {'unknown_fault': sum(c is None for c in outcomes.values()), 'failure:ValueError': 0},
        'tokens': {'solver': 100 * len(cells), 'selection': 0, 'total': 100 * len(cells)},
        'mount': {'typed': int(typed * len(cells)), 'typed_fraction': typed, 'with_card': int(typed * len(cells)),
                  'selection_status': {'ok': len(cells)} if (mount or {}).get('selection') else {}},
        'pass_count': 99, 'fail': 1})


def outcomes(correct_count, *, unknown=()):
    return {item: (None if item in unknown else index < correct_count) for index, item in enumerate(ITEMS)}


def repeat_runs(values, repeats=3):
    """typed-v2 step 5w: ``gates.arm_runs`` output of R identical runs per item ({item: bool})."""
    sums = {item: repeats * bool(value) for item, value in values.items()}
    return {'sums': sums, 'squares': dict(sums), 'unknown': 0}


def write_step1(chain_dir):
    """Step 1 records in the typed-v2 shapes of step 5w (DESIGN 3.4: R = 3 runs per item and arm)."""
    step = chain_dir / 's1'
    base, cand = (repeat_runs({item: index < cut for index, item in enumerate(ITEMS)}) for cut in (5, 6))
    kw = {'items': list(ITEMS), 'repeats': 3, 'minimum_points': 3.0, 'multiplier': 2.0}
    stats = gates.repeat_statistics(base, cand, **kw)
    fired = {'i5': 3, 'i6': 1}
    program = gates.program_decision(stats, gates.repeat_statistics(base, cand, subset=list(fired), **kw), fired)
    units.write_json(step / 'noise.json', gates.calibration(base, **kw))
    units.write_json(step / 'decisions.json', {
        'tau_points': 3.0, 'card': {'round1': gates.card_decision(stats)}, 'programs': [program],
        'no_harm': gates.no_harm_decision(stats)})
    lib = library.Library()
    lib.add(library.make_skill(skill_id='card-t01-s1', name='evidence-answer-card', kind='card', home_type='t01',
                               body={'text': '- read every snippet'}, origin={'chain': 'G', 'step': 1, 'bench': 'searchqa'},
                               description='For evidence QA with snippets.'))
    lib.add(library.make_skill(skill_id='prog-t01-s1-a', name='snippet-scanner', kind='program', home_type='t01',
                               body={'procedure': {'id': 'p-x', 'source': 'def applies(view):\n    return True\n'}},
                               origin={'chain': 'G', 'step': 1, 'bench': 'searchqa'}, description='Scans snippets.'))
    lib.save(step / 'library.json', step=1)
    tm = tasktypes.TypeMap()
    sid = tm.add_source({'path': '/pools/searchqa.json', 'sha256': 'a' * 64}, 'question/context',
                        [[1.0, 0.1 * i, 0.0] for i in range(5)], step=1)
    tid = tm.new_type(sid, step=1)
    tm.set_card(tid, 'card-t01-s1', step=1)
    tm.add_program(tid, 'prog-t01-s1-a', step=1)
    tm.freeze(step / 'typemap.json', step=1)
    write_unit(step / 'outcomes', [make_cell('searchqa', item, 'F', index < 6) for index, item in enumerate(ITEMS)]
               + [make_cell('searchqa', 'i9', 'C0', None, token='unknown')], sealed=False)


def make_root(tmp_path):
    root = tmp_path / 'run'
    chain_dir = root / 'G'
    chain_dir.mkdir(parents=True)
    units.write_json(chain_dir / 'state.json', {'status': 'paused', 'step': 2, 'done': ['s1/noise', 's1/outcomes'],
                     'paused': {'reason': 'token_cap', 'unit': 's2/outcomes'}, 'ledger': {'charged': 1}})
    units.write_json(chain_dir / 'confirm.json', {'passed': True, 'model': 'glm-5.3', 'response': 'ready ' + CANARY})
    ledger = units.Ledger(chain_dir / 'ledger.json', 10 ** 7)
    for unit in ('s1/outcomes', 'test-read-S1-searchqa'):
        key, bound = ledger.before_send('s', 'u', 100, cell='c', unit=unit)
        ledger.settle(key, {'ok': True, 'usage': {'prompt_tokens': 50, 'completion_tokens': 10, 'total_tokens': 60}},
                      max_tokens=100, prompt_bound=bound - 100)
    write_step1(chain_dir)
    mounted = mount_record('F', typed=True, card='card-t01-s1', programs=('prog-t01-s1-a',))
    # searchqa (home step 1): C0 .5, C .6, S1 .8, S2 .7, S3 .9, S4 .6, S5 .7 with one unknown item in S5
    for event, count in (('C0', 5), ('C', 6), ('S1', 8), ('S2', 7), ('S3', 9), ('S4', 6)):
        write_read(chain_dir, event, 'searchqa', outcomes(count), mount=mounted if event == 'S1' else None)
    write_read(chain_dir, 'S5', 'searchqa', outcomes(7, unknown=('i9',)))
    # officeqa (home step 2): C0 .4, C .4, S1 .5, S2..S4 .7, S5 .9 (ends above every earlier step: signed forgetting)
    for event, count in (('C0', 4), ('C', 4), ('S1', 5), ('S2', 7), ('S3', 7), ('S4', 7), ('S5', 9)):
        write_read(chain_dir, event, 'officeqa', outcomes(count))
    # zebralogic: C and C0 are identical requests on i0..i8 (C has no card), one item differs; only S1 read so far
    same = {item: 'zebra-' + item for item in ITEMS[:9]}
    write_read(chain_dir, 'C0', 'zebralogic', outcomes(5), requests=same)
    write_read(chain_dir, 'C', 'zebralogic', {item: item in ('i0', 'i1', 'i2', 'i3', 'i5', 'i6') for item in ITEMS}, requests=same)
    write_read(chain_dir, 'S1', 'zebralogic', outcomes(6))
    return root


def sealed_guard(monkeypatch):
    """Any open of a path that carries 'test-read' fails the test: closed mode must never touch a sealed unit."""
    real_open, real_read_text = io.open, Path.read_text

    def guarded_open(file, *args, **kwargs):
        if 'test-read' in str(file):
            raise AssertionError('sealed path opened in closed mode: ' + str(file))
        return real_open(file, *args, **kwargs)

    def guarded_read_text(self, *args, **kwargs):
        if 'test-read' in str(self):
            raise AssertionError('sealed path opened in closed mode: ' + str(self))
        return real_read_text(self, *args, **kwargs)
    monkeypatch.setattr(io, 'open', guarded_open)
    monkeypatch.setattr(builtins, 'open', guarded_open)
    monkeypatch.setattr(Path, 'read_text', guarded_read_text)


# ---- closed mode -----------------------------------------------------------------------------------------------
def test_closed_readout_reads_only_open_files(tmp_path, monkeypatch):
    root = make_root(tmp_path)
    sealed_guard(monkeypatch)
    result = readout.build(root, now=0)
    doc = result['chains']['G']
    assert result['mode'] == doc['mode'] == 'closed' and result['generated_utc'] == '19700101T000000Z'
    assert 'panels' not in doc and 'cl_metrics' not in doc and 'five_by_five' not in doc
    assert doc['state']['paused'] == {'reason': 'token_cap', 'unit': 's2/outcomes'} and doc['ledger']['charged'] == 120
    assert doc['costs']['by_unit']['test-read-S1-searchqa'] == {'calls': 1, 'reported': 60, 'charged': 60}
    assert doc['costs']['read_units'] == {'count': 1, 'charged': 60, 'reported': 60}
    assert 'response' not in doc['confirm'] and doc['confirm']['passed'] is True
    step = doc['steps'][1]
    assert step['bench'] == 'searchqa' and step['noise']['tau_points'] == 3.0 and step['noise']['n'] == 10
    kinds = {(d['label'], d['kind'], d['accepted']) for d in step['decisions']}
    assert kinds == {('card/round1', 'card', True), ('programs[0]', 'program', True), ('no_harm', 'no_harm', True)}
    program = next(d for d in step['decisions'] if d['kind'] == 'program')
    assert program['n'] == 10 and program['fired_n'] == 2 and program['excluded_unknown'] == 0 and program['tau_points'] == 3.0
    assert program['repeats'] == 3 and program['se_points'] == 0.0 and abs(program['mean_points'] - 50.0) < 1e-9
    assert step['noise'] == {'rule': 'baseline_repeats', 'repeats': 3, 'n': 10, 'mixed_items': 0, 'se_points': 0.0,
                             'tau_points': 3.0, 'unknown_final': 0, 'reruns': None}
    assert [(s['name'], s['kind'], s['home_type'], s['description']) for s in step['library']] == [
        ('evidence-answer-card', 'card', 't01', 'For evidence QA with snippets.'), ('snippet-scanner', 'program', 't01', 'Scans snippets.')]
    assert step['typemap']['types'] == {'t01': {'signature': 'question/context', 'sources': [tasktypes.source_id(
        {'path': '/pools/searchqa.json', 'sha256': 'a' * 64})], 'card': 'card-t01-s1', 'programs': ['prog-t01-s1-a']}}
    assert 'centroid' not in json.dumps(step['typemap'])
    unit = step['units']['outcomes']
    assert unit['cells'] == 11 and unit['unknown'] == 1 and unit['infrastructure_unknown'] == 1 and unit['tokens'] == 1100
    assert unit['by_arm']['F'] == {'cells': 10, 'correct': 6, 'wrong': 4, 'unknown': 0}
    # mirrors: counts only, the pass count the fixture planted never reaches the readout
    mirror = doc['read_status']['S1-searchqa']
    assert mirror['cells'] == 10 and mirror['mount']['typed_fraction'] == 1.0 and mirror['tokens']['total'] == 1000
    assert 'pass_count' not in mirror and 'fail' not in mirror and mirror['unknown_by_kind']['failure:ValueError'] == 0
    assert doc['mount_check']['all_present'] and doc['mount_check']['reads']['S1-searchqa']['present']
    written = result['written']['G']
    text = Path(written['markdown']).read_text()
    assert Path(written['json']).exists() and CANARY not in text and CANARY not in Path(written['json']).read_text()
    assert 'Practice-side gates decided every acceptance' in text and 'Closed mode' in text
    assert 'practice-side gates' in text and 'generalization evidence' in text
    assert 'evidence-answer-card' in text and 'snippet-scanner' in text and 'noise tau: 3.0 points' in text
    assert 'mount.typed_fraction=1.0' in text and 'tokens.total=1000' in text and 'pass_count' not in text
    with pytest.raises(ValueError):
        readout.build(root, now=0)  # a readout goes to a new directory


def test_status_is_closed_and_counts_only(tmp_path, monkeypatch):
    root = make_root(tmp_path)
    sealed_guard(monkeypatch)
    found = readout.status(root)
    assert found['mode'] == 'closed' and found['chains']['G']['steps_present'] == [1]
    assert found['chains']['G']['ledger']['sends'] == 2 and found['chains']['G']['state']['status'] == 'paused'
    assert 'pass_count' not in found['chains']['G']['read_status']['C0-searchqa']
    assert CANARY not in json.dumps(found)


# ---- open mode -------------------------------------------------------------------------------------------------
def test_open_readout_tables_and_cl_metrics(tmp_path):
    root = make_root(tmp_path)
    result = readout.build(root, open_sealed=True, now=0)
    doc = result['chains']['G']
    assert doc['mode'] == 'open'
    sq = doc['panels']['searchqa']
    assert sq['events'] == ['C0', 'C', 'S1', 'S2', 'S3', 'S4', 'S5'] and sq['items_common'] == 10
    acc = {event: sq['per_event'][event]['accuracy'] for event in sq['events']}
    assert [round(acc[e]['L'], 6) for e in sq['events']] == [.5, .6, .8, .7, .9, .6, .7]
    assert acc['S5'] == {'L': .7, 'H': .8, 'known': 7 / 9} and sq['per_event']['S5']['unknown'] == 1
    assert sq['per_event']['S5']['unknown_by_token'] == {'unknown_fault': 1}
    # paired contrasts on the complete cases: S1-C0 = +30 points (3 better, 0 worse, 7 tied), S5-C0 excludes i9
    pair = sq['pairs']['S1-C0']
    assert (pair['n'], pair['excluded_unknown'], pair['better'], pair['worse'], pair['tied']) == (10, 0, 3, 0, 7)
    assert abs(pair['mean_points'] - 30.0) < 1e-9 and pair['t_interval95_points'][0] < 30 < pair['t_interval95_points'][1]
    assert len(pair['bootstrap_interval95_points']) == 2 and pair['first_correct'] == 8 and pair['second_correct'] == 5
    late = sq['pairs']['S5-C0']
    assert (late['n'], late['excluded_unknown'], late['better'], late['worse']) == (9, 1, 2, 0)
    assert abs(late['mean_points'] - 200 / 9) < 1e-9
    assert set(sq['pairs']) == {'S%d-C0' % k for k in range(1, 6)} | {'S%d-C' % k for k in range(1, 6)} | {'S%d-S%d' % (k, k - 1) for k in range(2, 6)}
    assert abs(sq['pairs']['S3-S2']['mean_points'] - 20.0) < 1e-9
    # the 5x5: rows = steps, columns = panels, None where the panel was not read
    five = doc['five_by_five']
    assert [row['evolved_bench'] for row in five.values()] == list(ORDER)
    assert abs(five['S1']['diff_points_vs_C0']['searchqa'] - 30.0) < 1e-9 and five['S1']['accuracy_L']['officeqa'] == .5
    assert five['S2']['diff_points_vs_C0']['zebralogic'] is None and five['S5']['accuracy_H']['alfworld'] is None
    assert five['S1']['accuracy_L']['zebralogic'] == .6
    # same-request noise: zebralogic C vs C0 on the nine identical requests, three flips
    noise = doc['panels']['zebralogic']['same_request_noise']
    assert (noise['items_common'], noise['identical_requests'], noise['differing_requests'], noise['missing_request_sha']) == (10, 9, 1, 0)
    assert noise['noise']['n'] == 9 and abs(noise['noise']['flip_rate'] - 3 / 9) < 1e-9 and abs(noise['noise']['mean_points'] - 100 / 9) < 1e-9
    assert doc['panels']['searchqa']['same_request_noise']['identical_requests'] == 0
    # CL metrics on the hand-computed example (side L)
    cl = doc['cl_metrics']['per_bench']
    s = cl['searchqa']
    assert s['home_step'] == 1 and s['final_event'] == 'S5' and s['latest_event'] == 'S5'
    expect = {'final': .7, 'C0': .5, 'C': .6, 'gain_over_C0': .2, 'gain_over_C': .1, 'forgetting': .2,
              'forgetting_after_home': .2, 'backward_transfer': -.1, 'forward_transfer': None, 'plasticity': .3}
    assert {k: None if s['L'][k] is None else round(s['L'][k], 9) for k in expect} == expect
    assert round(s['H']['final'], 9) == .8 and round(s['H']['gain_over_C0'], 9) == .3
    o = cl['officeqa']['L']  # forgetting is signed (the vendored cl_metrics FGT; design §5.9): no 0 floor
    assert {k: None if o[k] is None else round(o[k], 9) for k in expect} == {
        'final': .9, 'C0': .4, 'C': .4, 'gain_over_C0': .5, 'gain_over_C': .5, 'forgetting': -.2,
        'forgetting_after_home': -.2, 'backward_transfer': .2, 'forward_transfer': .1, 'plasticity': .2}
    assert 'no floor' in doc['cl_metrics']['definitions']['forgetting']
    z = cl['zebralogic']
    assert z['final_event'] is None and z['L']['final'] is None and z['latest_event'] == 'S1'
    assert z['latest']['L']['final'] == .6 and round(z['latest']['L']['gain_over_C0'], 9) == .1 and z['latest']['L']['plasticity'] is None
    macro = doc['cl_metrics']['macro']['L']
    assert (round(macro['final']['mean'], 9), macro['final']['n_benches']) == (.8, 2) and round(macro['backward_transfer']['mean'], 9) == .05
    assert (round(macro['forward_transfer']['mean'], 9), macro['forward_transfer']['n_benches']) == (.1, 1)
    assert round(macro['forgetting']['mean'], 9) == 0.0 and round(macro['forgetting_after_home']['mean'], 9) == 0.0
    assert doc['cl_metrics']['macro_latest']['L']['final']['n_benches'] == 3
    # mount check: S1 searchqa mounted the step-1 card and program, both frozen in s1/library.json
    check = doc['mount_check']
    assert check['all_present'] and check['reads']['S1-searchqa']['skills_seen'] == ['card-t01-s1', 'prog-t01-s1-a']
    assert check['reads']['S1-searchqa']['unknown_skill_ids'] == [] and check['reads']['S1-searchqa']['typed_fraction'] == 1.0
    assert check['reads']['C0-searchqa']['typed_fraction'] == 0.0 and check['reads']['C0-searchqa']['present']
    routing = sq['per_event']['S1']['routing']
    assert routing['enabled_fraction'] == 1.0 and routing['selection_status'] == {'ok': 10} and routing['types'] == {'t01': 10}
    assert doc['read_tokens']['S1-searchqa'] == 1000 and doc['read_units']['S1-searchqa']['done']
    # no reply text of a test item leaves the sealed units
    for path in Path(result['out']).iterdir():
        assert CANARY not in path.read_text()
    text = Path(result['written']['G']['markdown']).read_text()
    assert 'Open mode' in text and 'select nothing' in text and '## 5x5' in text and 'Continual-learning metrics' in text
    assert 'Practice-side gates decided every acceptance' in text and 'ZebraLogic reads C as C0 by construction' in text


def test_open_readout_flags_unknown_skill_ids_and_missing_mounts(tmp_path):
    root = tmp_path / 'run'
    chain_dir = root / 'D'
    chain_dir.mkdir(parents=True)
    write_step1(chain_dir)
    stray = mount_record('F', typed=True, card='card-t01-s7')
    write_read(chain_dir, 'C0', 'searchqa', outcomes(5))
    write_read(chain_dir, 'S1', 'searchqa', outcomes(6), mount=stray)
    cells = [make_cell('officeqa', item, 'F', True) for item in ITEMS[:3]]
    for cell in cells:
        del cell['mount']
    write_unit(chain_dir / 'test-read-S1-officeqa', cells, sealed=True)
    doc = readout.build(root, open_sealed=True, now=1)['chains']['D']
    check = doc['mount_check']
    assert not check['all_present'] and check['reads']['S1-searchqa']['unknown_skill_ids'] == ['card-t01-s7']
    assert check['reads']['S1-officeqa'] == {**check['reads']['S1-officeqa'], 'cells': 3, 'mount_records_present': 0, 'present': False}
    assert doc['panels']['officeqa']['pairs'] == {} and doc['panels']['officeqa']['same_request_noise'] is None
    assert readout.chains_of(root) == ['D'] and readout.parse_read_name('test-read-S1-officeqa') == ('S1', 'officeqa')
    assert readout.parse_read_name('practice-read-C0-alfworld') == ('C0', 'alfworld')
    assert readout.parse_read_name('s1') is None and readout.parse_read_name('test-read-S1-unknownbench') is None


def test_build_refuses_an_empty_root(tmp_path):
    with pytest.raises(ValueError):
        readout.build(tmp_path)


# ---- fix-b: the program decision's two informational SEs; the sealed base card (D17) ----------------------------
def table_row(text, first_cell):
    """The cells of the markdown table row whose first cell is ``first_cell``, with the header row of its table."""
    lines = text.split('\n')
    for index, line in enumerate(lines):
        cells = [cell.strip() for cell in line.strip().strip('|').split('|')]
        if line.startswith('| ') and cells[0] == first_cell:
            start = index
            while start > 0 and lines[start - 1].startswith('|'):
                start -= 1
            header = [cell.strip() for cell in lines[start].strip().strip('|').split('|')]
            return dict(zip(header, cells))
    raise AssertionError('no table row ' + first_cell)


def test_the_markdown_step_table_shows_both_informational_SEs_of_a_program(tmp_path):
    """fix-b (review rb-stats 2), addendum "Program gate on the items where the program fired": reports state for
    each accepted program its fired items and how its gain compares with se_points_fired and se_points_scaled; the
    markdown step table carries both beside the fired n and the fired gain (the JSON row already did)."""
    root = make_root(tmp_path)
    result = readout.build(root, now=0)
    program = json.loads((root / 'G' / 's1' / 'decisions.json').read_text())['programs'][0]
    assert program['se_points_fired'] is not None and program['se_points_scaled'] is not None
    row = table_row(Path(result['written']['G']['markdown']).read_text(), 'programs[0]')
    assert row['fired n'] == '2' and row['SE fired pts'] == readout._num(program['se_points_fired'])
    assert row['SE scaled pts'] == readout._num(program['se_points_scaled'])
    card = table_row(Path(result['written']['G']['markdown']).read_text(), 'card/round1')
    assert card['SE fired pts'] == card['SE scaled pts'] == '—'  # a card decision has neither


@pytest.mark.parametrize('base, row', [('historical', 'C'), ('format', 'C0'), (None, None)])
def test_the_readout_shows_the_sealed_base_card_and_the_base_row(tmp_path, base, row):
    """fix-b (review F2), addendum D17 "Reporting": the readout names the run's sealed base card (the chain state
    keeps the manifest's value) in its header with what it means, D17's statement that typed-v2 starts from C while
    the v2.24 baselines started from an empty skill, and marks the base row of every panel (C under 'historical',
    C0 under 'format'), so C's own gain over C0 is never read as learned gain."""
    root = make_root(tmp_path)
    state = json.loads((root / 'G' / 'state.json').read_text())
    if base is not None:
        units.write_json(root / 'G' / 'state.json', {**state, 'base_card': base})
    closed = readout.build(root, now=0)
    assert closed['chains']['G']['base_card'] == base
    text = Path(closed['written']['G']['markdown']).read_text()
    assert ('- base card: %s' % (base or 'not recorded')) in text
    assert ('typed-v2 starts from C' in text) == (base == 'historical')
    assert ('started from an empty skill' in text) == (base == 'historical')
    opened = readout.build(root, open_sealed=True, now=1)
    text = Path(opened['written']['G']['markdown']).read_text()
    labels = [line.split('|')[1].strip() for line in text.split('\n') if line.startswith('| C')]
    if row is None:
        assert not any('base of S' in label for label in labels)
    else:
        panels = len(opened['chains']['G']['panels'])  # one base row per panel
        assert panels == 3 and labels.count('%s (base of S1..S5)' % row) == panels
        assert opened['chains']['G']['base_card'] == base
def test_public_readout_entries_refuse_a_root_of_another_typed_version(tmp_path):
    """Codex review round 1, finding 4: build, status and chain_readout check the version like the CLI does, so a
    typed-v2 readout is never written into (or read from) a typed-v1 root."""
    root = tmp_path / 'execskill-20261110-typed-v1'
    (root / 'G').mkdir(parents=True)
    for call in (lambda: readout.build(root), lambda: readout.status(root), lambda: readout.chain_readout(root, 'G')):
        with pytest.raises(ValueError, match='typed version'):
            call()
    assert not (root / 'readout').exists()


# ---- economy read plan (spec/read-plan.md 1.F R63-R74, R89, R90; T20; addendum D10 d, RP3-RP7) ---------------
import ast
import hashlib
import inspect
import os
import subprocess
import time

from skillopt.execskill.typed import readplan as rp
from skillopt.execskill.typed import tasktypes as tt

H = lambda text: hashlib.sha256(text.encode('utf-8')).hexdigest()  # noqa: E731
EITEMS = ['q0', 'q1', 'q2', 'q3']
T0 = time.mktime((2026, 11, 13, 1, 0, 0, 0, 0, -1))
# Base historical (R91 b, d). Step whose learned card changes a panel's requests (None: never changed):
# searchqa {C0} {C} {S1..S5}>S5; officeqa = the layout example's B1 {C0} {C,S1,S2}>S2 {S3,S4,S5}>S5;
# zebralogic {C0,C,S1,S2,S3}>S3 {S4,S5}>S5; spreadsheetbench {C0} {C,S1..S5}>S5; alfworld as spreadsheetbench but
# S2 is a fallback (identity_exception): {C0} {C,S1,S3,S4,S5}>S5 {S2}>S2.
CHANGES = {'searchqa': 1, 'officeqa': 3, 'zebralogic': 4, 'spreadsheetbench': None, 'alfworld': None}
FALLBACK = ('S2', 'alfworld')
# outcomes of q0..q3 per fresh unit (None = an infrastructure unknown)
OUTCOMES = {('searchqa', 'S5'): [True, True, True, None], ('searchqa', 'C'): [True, True, False, False],
            ('searchqa', 'C0'): [True, False, False, False],
            ('officeqa', 'S5'): [True, True, True, False], ('officeqa', 'S2'): [True, True, False, False],
            ('officeqa', 'C0'): [True, False, False, False],
            ('zebralogic', 'S5'): [True, True, True, False], ('zebralogic', 'S3'): [True, True, False, False],
            ('spreadsheetbench', 'S5'): [True, True, True, False], ('spreadsheetbench', 'S4'): [True, True, False, True],
            ('spreadsheetbench', 'C0'): [True, False, False, False],
            ('alfworld', 'S5'): [True, True, False, False], ('alfworld', 'S2'): [True, False, True, False],
            ('alfworld', 'C0'): [True, False, False, False]}
VOIDED = ('C', 'S1', 'S2', 'S3')   # spreadsheetbench: post-read mismatch of S5 voided its aliases (R42); S4 re-read
STALE = ('S4', 'zebralogic')       # a record written, its state entry not yet (P7): stale, never shown


def clock(epoch):
    return time.strftime('%Y-%m-%dT%H:%M:%S', time.localtime(epoch))


def system_text(bench, event):
    fmt = 'FORMAT ' + bench
    hist = fmt if bench == 'zebralogic' else 'HISTORICAL ' + bench
    if event in ('C0', 'C'):
        return fmt if event == 'C0' else hist
    change = CHANGES[bench]
    return ('LEARNED %s\n\n%s' % (bench, hist)) if change is not None and int(event[1:]) >= change else hist


def public_of(bench, item):
    return {'question': 'Q %s %s' % (bench, item)}


def view_of(bench, item):
    return {'bench': bench, 'item': item}


def first_request(bench, event, item):
    return H(system_text(bench, event) + '\x00' + 'USER %s %s' % (bench, item))


def item_record(bench, event, item):
    system, arm = system_text(bench, event), rp.arm_of(event)
    mounted = {'arm': arm, 'type': None, 'source': None, 'unknown_reason': 'unseen_signature' if arm == 'F' else None,
               'card_skill': None, 'programs_offered': [], 'selection': None, 'system_card_sha256': H(system)}
    components = rp.item_components({'system_card_sha256': H(system), 'programs_offered': [], 'forced': None}, mounted,
                                    arm=arm, public_sha256=rp.public_sha256(public_of(bench, item)),
                                    view_sha256=rp.view_sha256(view_of(bench, item)))
    return rp.item_record(bench, components, first_request=None if bench == 'alfworld'
                          else first_request(bench, event, item))


def build_plan():
    frozen = {e: {'step': rp.step_of(e), **{key: H('%s-%d' % (key, rp.step_of(e))) for key in rp.FROZEN_KEYS
                                            if key != 'step'}} for e in rp.EVENTS}
    benches = {}
    for bench in ORDER:
        entries = {}
        for event in rp.EVENTS:
            mount = {key: frozen[event][key] for key in rp.READ_MOUNT_KEYS}
            if (event, bench) == FALLBACK:
                entries[event] = rp.event_entry(bench, event, EITEMS, None, read_mount=mount, reason='identity_exception')
                continue
            records = [item_record(bench, event, item) for item in EITEMS]
            entries[event] = rp.event_entry(bench, event, EITEMS, records, read_mount=mount,
                                            second=records if event.startswith('S') else None)
        views = [view_of(bench, item) for item in EITEMS]
        inputs = rp.inputs_record('G', bench, EITEMS, [rp.view_sha256(v) for v in views],
                                  alfworld_views=views if bench == 'alfworld' else None,
                                  vectors=[[[0.5, float(n)] for n in range(len(EITEMS))] for _run in range(2)])
        benches[bench] = {'inputs': inputs, 'entries': entries, 'registry_sha256': H('registry ' + bench),
                          'run_constants_sha256': H('constants ' + bench)}
    return rp.plan_files(chain='G', smoke=False, schedule='learn_first', read_plan='economy', base_card='historical',
                         manifest_record_sha256=H('manifest'), solver_settings_sha256=H('settings'), order=list(ORDER),
                         frozen=frozen, benches=benches)[rp.PLAN_FILE]


def econ_cell(bench, event, item, correct, models):
    system, arm = system_text(bench, event), rp.arm_of(event)
    first = first_request(bench, event, item)
    return {'bench': bench, 'item_id': item, 'arm': arm, 'correct': correct,
            'token': 'pass' if correct else 'fail' if correct is False else 'unknown',
            'reply': CANARY, 'output_excerpt': CANARY, 'prediction': CANARY,
            'sends': [{'request_sha256': first, 'system': CANARY, 'user': CANARY,
                       'receipt': {'ok': True, 'response': CANARY, 'returned_model': model}} for model in models],
            'selection_sends': [], 'request_sha256': [first], 'public_hash': rp.public_sha256(public_of(bench, item)),
            'system_card_sha256': H(system), 'tokens': 100, 'configuration_error': False,
            'infrastructure_unknown': correct is None, 'failure': None, 'format': {}, 'flags': [], 'fired': [],
            'faults': [], 'mount': {'arm': arm, 'type': None, 'source': None, 'card_skill': None, 'programs_enabled': [],
                                    'unknown_reason': 'unseen_signature' if arm == 'F' else None,
                                    'system_card_sha256': H(system), 'programs_offered': [], 'selection': None,
                                    'card_text': CANARY, 'system_card': CANARY}}


def write_fresh(chain_dir, bench, event, outcomes, *, start, models=('model-a',), done=True):
    """A fresh read unit (sealed) whose cell and done files carry the times of R90, and its open mirror."""
    name = 'test-read-%s-%s' % (event, bench)
    unit = chain_dir / name
    for item, correct in zip(EITEMS, outcomes):
        cell = econ_cell(bench, event, item, correct, models)
        tag = units.cell_tag(bench, item, cell['arm'])
        path = unit / 'cells' / (tag + '.json')
        units.write_json(path, {**cell, 'tag': tag}, allow_sealed=True)
        os.utime(path, (start + 60, start + 60))
    if done:
        units.write_json(unit / 'done.json', {'unit': name, 'started': clock(start), 'finished': clock(start + 300),
                                              'cells': 4, 'expected_cells': 4, 'missing_cells': 0,
                                              'stop_reason': None}, allow_sealed=True)
        os.utime(unit / 'done.json', (start + 300, start + 300))
    unknown = sum(c is None for c in outcomes)
    mirror = {'version': 'typed-v2', 'kind': 'read-status', 'chain': 'G', 'event': event, 'bench': bench,
              'arm': rp.arm_of(event), 'unit': name, 'smoke': False, 'status': 'complete', 'stop_reason': None,
              'items': 4, 'cells': 4, 'expected_cells': 4, 'missing_cells': 0, 'unsubmitted': 0, 'unknown': unknown,
              'unknown_by_kind': {'unknown': unknown}, 'infrastructure_unknown': unknown, 'configuration_errors': 0,
              'tokens': {'solver': 400, 'selection': 0, 'total': 400},
              'mount': {'typed': 0, 'typed_fraction': 0.0, 'with_card': 0}, 'aggregate_sha256': H(name),
              'finished': clock(start + 300)}
    units.write_json(chain_dir / 'read-status' / ('%s-%s.json' % (event, bench)), mirror)
    return mirror


def write_typemaps(chain_dir):
    """s1..s5 type maps: searchqa and officeqa share t01 (officeqa merged at step 2), the others own a type."""
    tm = tasktypes.TypeMap()
    signature = {'searchqa': 'question/context', 'officeqa': 'question/context', 'zebralogic': 'puzzle_template',
                 'spreadsheetbench': 'workbook_preview', 'alfworld': 'admissible_commands'}
    for k, bench in enumerate(ORDER, 1):
        sid = tm.add_source(pool_pin(bench), signature[bench], [[1.0, 0.1 * i, 0.0] for i in range(3)], step=k)
        if bench == 'officeqa':
            tm.merge_source(sid, 't01', step=k, evidence={})
        else:
            tm.new_type(sid, step=k)
        tm.freeze(chain_dir / ('s%d' % k) / 'typemap.json', step=k)
        units.write_json(chain_dir / ('s%d' % k) / 'noise.json', {'rule': 'baseline_repeats', 'repeats': 3, 'n': 4,
                                                                   'se_points': 1.5, 'tau_points': 3.0 + k})


def pool_pin(bench):
    return {'path': '/pools/%s.json' % bench, 'sha256': H('pool ' + bench)}


def economy_root(tmp_path, *, recoveries=(), models=None):
    """A G chain read under economy: fresh, alias, void-alias, fallback and stale pairs (T20 fixture)."""
    root = tmp_path / 'run'
    chain_dir = root / 'G'
    chain_dir.mkdir(parents=True)
    units.write_json(root / 'manifest.json', {'pools': {bench: pool_pin(bench) for bench in ORDER}})
    write_typemaps(chain_dir)
    plan = build_plan()
    file_sha = rp.write_once(rp.plan_path(root, 'G'), plan)
    reads, done, mirrors = {}, ['read-plan'], {}
    fresh = [(e, b) for (b, e) in OUTCOMES]
    order = sorted(fresh, key=lambda pair: (-rp.EVENTS.index(pair[0]), ORDER.index(pair[1])))   # S5 first (D10 e)
    for index, (event, bench) in enumerate(order):
        mirrors[(event, bench)] = write_fresh(chain_dir, bench, event, OUTCOMES[(bench, event)], start=T0 + 600 * index,
                                              models=(models or {}).get((event, bench), ('model-a',)))
        reads.setdefault(event, {})[bench] = {k: v for k, v in mirrors[(event, bench)].items()
                                              if k not in ('unknown_by_kind',)}
        done.append('read-%s-%s' % (event, bench))
    for event, bench in rp.alias_pairs(plan):
        representative = rp.class_of(plan, event, bench)['representative']
        if bench == 'spreadsheetbench':
            if event in VOIDED:
                reads.setdefault(event, {})[bench] = {'kind': 'void_alias', 'alias_of': representative}
            continue
        mirror = mirrors[(representative, bench)]
        record = rp.build_alias(plan, event, bench, check={'items': 4, 'equal': 4, 'unequal': 0},
                                representative_aggregate_sha256=mirror['aggregate_sha256'],
                                representative_counts={key: mirror[key] for key in rp.COUNT_KEYS})
        rp.write_once(rp.alias_path(root, 'G', event, bench), record)
        if (event, bench) != STALE:
            reads.setdefault(event, {})[bench] = rp.alias_state_entry(record)
            done.append('alias-%s-%s' % (event, bench))
    for path in [rp.plan_path(root, 'G')] + sorted((chain_dir / rp.ALIAS_DIR).glob('*.json')):
        os.utime(path, (T0 - 3600, T0 - 3600))
    state = {'status': 'complete', 'step': 5, 'schedule': 'learn_first', 'phase': 'read', 'base_card': 'historical',
             'done_units': done, 'reads': reads, 'recoveries': list(recoveries), 'paused': None,
             'read_plan': {'mode': 'economy', 'plan_sha256': plan['plan_sha256'], 'file_sha256': file_sha,
                           'bound_at': clock(T0 - 3600), 'replay': {'verdict': 'equal'},
                           'fallbacks': {'spreadsheetbench': {'event': 'S5', 'reason': 'post_read_mismatch',
                                                              'unequal': 1}},
                           'failures': [], 'void': False, 'void_reason': None, 'recoveries': []}}
    units.write_json(chain_dir / 'state.json', state)
    return root, plan, order


def by_source(doc):
    found = {}
    for key, pair in doc['resolver']['pairs'].items():
        found.setdefault(pair['source'], set()).add(key)
    return found


def test_resolver_marks_every_pair_from_the_state_checked_against_plan_and_records(tmp_path):
    """R63, R64: sources from the state; aliases verified (R44 a); independent only when fresh; a record without an
    alias state entry is stale and never shown; a full state resolves every pair fresh (R6)."""
    root, plan, order = economy_root(tmp_path)
    resolved = readout._resolve(root, 'G')
    pairs = resolved['pairs']
    assert resolved['mode'] == 'economy' and resolved['error'] is None and plan['counts']['fallback'] == 1
    assert {key for key, p in pairs.items() if p['source'] == 'fresh'} == set(order)
    assert {key for key, p in pairs.items() if p['source'] == 'void_alias'} == {(e, 'spreadsheetbench') for e in VOIDED}
    assert {key for key, p in pairs.items() if p['source'] == 'pending'} == {STALE}
    assert not [key for key, p in pairs.items() if p['source'] == 'invalid']
    aliases = {key for key, p in pairs.items() if p['source'] == 'alias'}
    assert len(aliases) == 35 - len(order) - len(VOIDED) - 1 == 16
    assert pairs[('S3', 'officeqa')]['of'] == 'S5' and pairs[('C', 'officeqa')]['of'] == 'S2'
    assert pairs[('C0', 'zebralogic')]['of'] == 'S3' and pairs[('S1', 'searchqa')]['counts'] == {
        'unknown': 1, 'infrastructure_unknown': 1, 'configuration_errors': 0}
    assert all(p['independent'] == (p['source'] == 'fresh') for p in pairs.values())
    assert resolved['stale_alias_records'] == ['S4-zebralogic']
    assert pairs[('S2', 'alfworld')]['source'] == 'fresh' and pairs[('S3', 'alfworld')]['of'] == 'S5'
    counts = readout.read_counts(resolved, json.loads((root / 'G' / 'state.json').read_text()))
    assert counts == {'settled': 30, 'of': 35, 'fresh_done': 14, 'fresh_planned': 13 + 5, 'alias': 16,
                      'fallbacks': 2, 'void_aliases': 5, 'pending': 1, 'invalid': 0}
    full = readout._resolve_chain(root / 'G', {'read_plan': {'mode': 'full'}})
    assert {p['source'] for p in full['pairs'].values()} == {'fresh'} and len(full['pairs']) == 35


def test_unpatched_typed_v1_open_shows_no_number_for_a_same_class_pair(tmp_path):
    """T20 (CB14), the ACCEPT case: the typed-v1 consumers, unchanged (see the next test), on an economy root. Alias
    pairs have no unit directory (R38), so no consumer can print a number for them: one case per consumer."""
    root, plan, order = economy_root(tmp_path)
    chain_dir = root / 'G'
    steps = {k: readout._step(path, k, ORDER) for k, path in readout._step_dirs(chain_dir).items()}
    old = readout._open(chain_dir, steps, ORDER)
    fresh = set(order)
    for bench, panel in old['panels'].items():                               # _panel
        assert {(e, bench) for e in panel['per_event']} <= fresh
        for name in panel['pairs']:                                          # _pairs: no by-construction 0.0
            first, second = name.split('-')                                  # (two fresh units are measured)
            assert {(first, bench), (second, bench)} <= fresh
    assert 'S5-S4' not in old['panels']['officeqa']['pairs'] and 'S5-C' not in old['panels']['officeqa']['pairs']
    assert old['panels']['zebralogic']['same_request_noise'] is None          # _same_request_noise: no zero flips
    assert old['panels']['officeqa']['same_request_noise'] is None
    for event, row in old['five_by_five'].items():                           # _five_by_five
        for bench in ORDER:
            if (event, bench) not in fresh:
                assert row['diff_points_vs_C0'][bench] is None and row['accuracy_L'][bench] is None
    metrics = old['cl_metrics']['per_bench']                                  # _formulas / _cl_metrics
    assert metrics['officeqa']['L']['gain_over_C'] is None and metrics['zebralogic']['L']['gain_over_C0'] is None
    assert metrics['spreadsheetbench']['L']['gain_over_C'] is None
    macro = old['cl_metrics']['macro']['L']                                   # _macro: means over defined only
    assert macro['gain_over_C']['n_benches'] == 1                            # only searchqa has a fresh C
    check = old['mount_check']                                                # _open_mount_check
    assert {tuple(name.split('-')) for name in check['reads']} == fresh and check['all_present']
    assert all(not row['unknown_skill_ids'] for row in check['reads'].values())
    assert set(old['read_tokens']) == {'%s-%s' % pair for pair in fresh}     # read_tokens
    assert CANARY not in json.dumps(old)


TYPED_V1_CONSUMERS = ('_project', 'read_units_of', '_load_read_unit', '_routing', '_accuracy', '_event_summary',
                      '_paired', '_pairs', '_same_request_noise', '_panel', '_five_by_five', '_formulas',
                      '_bench_metrics', '_macro', '_cl_metrics', '_open_mount_check', '_open', '_closed_mount_check',
                      '_mirrors', '_costs')


def test_the_typed_v1_consumers_are_unpatched():
    """The functions the previous test runs are byte-equal to typed-v1's (commit 8375ecb), so it tests the
    UNPATCHED behaviour; skipped only where the history is not available (a shallow clone)."""
    tree = Path(__file__).resolve().parents[1]
    try:
        old = subprocess.run(['git', 'show', '8375ecb:skillopt/execskill/typed/readout.py'], cwd=tree,
                             capture_output=True, text=True, check=True, timeout=30).stdout
    except (OSError, subprocess.SubprocessError):
        pytest.skip('typed-v1 history (commit 8375ecb) not available')
    found = {node.name: ast.get_source_segment(old, node) for node in ast.parse(old).body
             if isinstance(node, ast.FunctionDef)}
    for name in TYPED_V1_CONSUMERS:
        assert inspect.getsource(getattr(readout, name)).rstrip() == found[name].rstrip(), name


def test_open_economy_readout_marks_aliases_and_never_measures_inside_a_class(tmp_path):
    """T20 patched: marks in every table and export, the dash rule, the alias objects, RP4, both macro columns,
    in-run replicates beside every contrast, u/i/c beside every alias, fresh-only tokens, no text."""
    root, plan, order = economy_root(tmp_path)
    result = readout.build(root, open_sealed=True, now=0)
    doc = result['chains']['G']
    assert set(doc['read_units']) == {'%s-%s' % pair for pair in order}
    assert doc['not_loaded'] == [] and set(doc['read_tokens']) == {'%s-%s' % pair for pair in order}
    officeqa = doc['panels']['officeqa']
    assert officeqa['events'] == ['C0', 'S2', 'S5']                             # fresh units under their own event
    assert officeqa['marks']['S3'] == {'source': 'alias', 'of': 'S5', 'independent': False, 'kind': 'alias',
                                       'counts': {'unknown': 0, 'infrastructure_unknown': 0, 'configuration_errors': 0},
                                       'class': 3, 'reason': None}
    inside = officeqa['contrasts']['S5-S4']                                     # dash rule: null, never 0.0
    assert inside['status'] == 'same_class' and inside['same_class'] and inside['delta'] is None
    assert officeqa['contrasts']['S3-S2']['status'] == 'measured' and officeqa['contrasts']['S3-S2']['of'] == ['S5', 'S2']
    assert officeqa['contrasts']['S3-S2']['requests']['text'] == 'different (4 of 4 items)'
    assert abs(officeqa['contrasts']['S3-S2']['delta']['mean_points'] - 25.0) < 1e-9
    assert officeqa['contrasts']['S5-C']['of'] == ['S5', 'S2']                  # R68: C's class representative
    # in-run replicates: two fresh units of one planned class (a fallback, a voided alias re-read) are noise samples
    assert doc['in_run_replicates'] == {'searchqa': 0, 'officeqa': 0, 'zebralogic': 0, 'spreadsheetbench': 1,
                                        'alfworld': 1, 'total': 2}
    assert doc['panels']['spreadsheetbench']['contrasts']['S5-S4']['requests']['label'] == 'identical'
    assert doc['panels']['alfworld']['contrasts']['S3-S2']['noise_sample'] is True
    five = doc['five_by_five']                                                  # R66 objects
    assert five['S3']['accuracy_L']['officeqa'] == {'value': None, 'source': 'alias', 'of': 'S5', 'independent': False,
                                                    'kind': 'alias', 'counts': {'unknown': 0, 'infrastructure_unknown': 0,
                                                                                'configuration_errors': 0}}
    assert five['S5']['accuracy_L']['officeqa'] == {'value': .75, 'source': 'fresh', 'of': 'S5', 'independent': True,
                                                    'kind': 'measured'}
    assert five['S5']['diff_points_vs_C']['spreadsheetbench']['kind'] == 'none'   # C is a void alias: no value
    assert five['S3']['diff_points_vs_C0']['zebralogic']['kind'] == 'same_class'
    assert five['S3']['diff_points_vs_C0']['zebralogic']['value'] is None
    assert five['S5']['diff_points_vs_C0']['zebralogic']['of'] == ['S5', 'S3']   # C0 read through its class
    for row in five.values():
        for key in ('diff_points_vs_C0', 'diff_points_vs_C', 'accuracy_L', 'accuracy_H'):
            for cell in row[key].values():
                assert set(cell) >= {'value', 'source', 'of', 'independent', 'kind'}
                assert cell['kind'] != 'alias' or cell['value'] is None
    cl = doc['cl_metrics']
    office = cl['per_bench']['officeqa']['L']                                   # RP4: layout example B1
    assert office['forgetting']['kind'] == 'structural' and office['forgetting']['value'] == 0.0
    assert office['forgetting']['structural_terms'] == 2 and abs(office['forgetting']['other_max'] + .25) < 1e-9
    assert office['gain_over_C']['of'] == ['S5', 'S2'] and abs(office['gain_over_C']['value'] - .25) < 1e-9
    search = cl['per_bench']['searchqa']['L']
    assert search['forgetting']['kind'] == 'structural' and search['forgetting']['structural_terms'] == 4
    assert search['backward_transfer']['kind'] == 'structural'                  # S5 and S1 share a class
    zebra = cl['per_bench']['zebralogic']['L']
    assert zebra['gain_over_C0']['of'] == ['S5', 'S3'] and zebra['gain_over_C']['of'] == ['S5', 'S3']
    assert cl['per_bench']['spreadsheetbench']['L']['gain_over_C']['kind'] == 'none'
    macro = cl['macro']['L']['gain_over_C']                                      # (a) structural 0s as 0, (b) measured
    assert macro['a']['kind'] == 'macro_a' and macro['a']['structural'] == 1 and macro['a']['benches'] == 4
    assert macro['b']['n'] == 3 and macro['a']['pending'] == 1
    values = {b: cl['per_bench'][b]['L']['gain_over_C'] for b in ORDER}
    measured = [v['value'] for v in values.values() if v['kind'] == 'measured']
    assert abs(macro['b']['value'] - sum(measured) / 3) < 1e-9 and abs(macro['a']['value'] - sum(measured) / 4) < 1e-9
    assert doc['reference'] == [] and doc['gate_noise'][3] == {'se_points': 1.5, 'tau_points': 6.0}
    # markdown: marks, dashes, u/i/c, replicates, gate noise, legend, classes block; no text of a cell
    text = Path(result['written']['G']['markdown']).read_text()
    assert CANARY not in text and CANARY not in Path(result['written']['G']['json']).read_text()
    assert '=S5 75.0 u/i/c 1/1/0' in text and '=S2 50.0 u/i/c 0/0/0' in text and '=S3 50.0 u/i/c 0/0/0' in text
    grid = table_row(text, 'S1')
    assert grid['searchqa'] == '=S5 75.0 u/i/c 1/1/0' and grid['spreadsheetbench'] == 'void_alias'
    assert grid['zebralogic'] == '=S3 50.0 u/i/c 0/0/0' and grid['alfworld'] == '=S5 50.0 u/i/c 0/0/0'
    assert '- (2 by-construction terms; other classes max -25.0, not above 0)' in text
    assert 'same requests, not measured' in text and 'noise sample, not an effect' in text
    assert text.count('in-run replicates') >= 5 and 'practice-side gate noise per step' in text
    assert 's3 tau 6.0 / SE 1.5' in text and '## Read classes' in text and '## Generalization view' in text
    assert 'post-read mismatch (defect signal, R42)' in text and 'stale alias records' in text
    inside_rows = [line for line in text.split('\n') if 'same requests, not measured |' in line]
    assert len(inside_rows) >= 10 and all('0.0' not in line and '/' not in line.split('|', 4)[4] for line in inside_rows)
    assert any(line.startswith('| S5-S4 | S5-S5 | same requests, not measured |') for line in inside_rows)
    grid_text = text.split('## Event grid')[1].split('##')[0]                    # every alias pair once, marked
    for (event, bench), pair in readout._resolve(root, 'G')['pairs'].items():
        cell = table_row(grid_text, event)[bench]
        assert cell.startswith('=%s ' % pair['of']) == (pair['source'] == 'alias'), (event, bench, cell)
        assert grid_text.count('| %s |' % event) == 1


def test_closed_economy_readout_lists_aliases_apart_from_fresh_mirrors(tmp_path, monkeypatch):
    """R65: closed mode reads no sealed file, lists every verified alias pair once with the representative's u/i/c
    (zeros included), keeps the mount check over fresh mirrors (all present) with the aliases' planned counts,
    reports the stale record and the economy counts (R71)."""
    root, plan, order = economy_root(tmp_path)
    sealed_guard(monkeypatch)
    result = readout.build(root, now=0)
    doc = result['chains']['G']
    assert doc['mode'] == 'closed' and 'panels' not in doc
    assert set(doc['read_status']) == {'%s-%s' % pair for pair in order}          # mirrors: fresh units only
    assert set(doc['aliases']) == {'%s-%s' % key for key, p in readout._resolve(root, 'G')['pairs'].items()
                                   if p['source'] == 'alias'}
    assert all(row['valid'] for row in doc['aliases'].values())
    assert doc['stale_alias_records'] == [{'pair': 'S4-zebralogic', 'reason': 'stale_alias_record'}]
    assert doc['mount_check']['all_present'] and set(doc['mount_check']['planned']) == set(doc['aliases'])
    assert doc['mount_check']['planned']['S1-searchqa']['source'] == 'planned'
    assert doc['economy']['alias'] == 16 and doc['read_plan']['counts'] == plan['counts']
    text = Path(result['written']['G']['markdown']).read_text()
    for stem in doc['aliases']:
        assert sum(1 for line in text.split('\n') if line.startswith('| %s | same requests as' % stem)) == 1
    assert '| S1-searchqa | same requests as S5 | 1/1/0 | 4/0 of 4 | verified |' in text
    assert '| C0-zebralogic | same requests as S3 | 0/0/0 | 4/0 of 4 | verified |' in text
    assert '- economy: 16 pairs aliased, 2 fallbacks, 5 voided aliases' in text and 'tokens saved' not in text
    assert 'S4-zebralogic' in text.split('stale alias records')[1].split('\n')[0]
    assert '- read plan: economy; plan %s' % plan['plan_sha256'][:12] in text
    status = readout.status(root)['chains']['G']
    assert status['read_plan'] == {'mode': 'economy', 'plan_sha256': plan['plan_sha256'][:12], 'error': None,
                                   'void': False}
    assert status['reads']['settled'] == 30 and status['reads']['of'] == 35


def test_alias_records_are_verified_and_a_tampered_plan_renders_no_read_table(tmp_path):
    """R44 a in the readout: an edited record or a rebuilt representative mirror makes the pair invalid (no value);
    R74: a plan that fails its hash renders no read table, only the error, in both modes."""
    root, plan, order = economy_root(tmp_path)
    chain_dir = root / 'G'
    path = rp.alias_path(root, 'G', 'S1', 'officeqa')
    record = json.loads(path.read_text())
    path.chmod(0o644)
    path.write_bytes(rp.canonical_bytes({**record, 'items': 5}))
    mirror = json.loads((chain_dir / 'read-status' / 'S5-searchqa.json').read_text())
    units.write_json(chain_dir / 'read-status' / 'S5-searchqa.json', {**mirror, 'aggregate_sha256': H('rebuilt')})
    pairs = readout._resolve(root, 'G')['pairs']
    assert pairs[('S1', 'officeqa')]['source'] == 'invalid' and pairs[('C', 'officeqa')]['source'] == 'alias'
    assert all(pairs[(e, 'searchqa')]['source'] == 'invalid' for e in ('S1', 'S2', 'S3', 'S4'))
    doc = readout.build(root, open_sealed=True, now=0)['chains']['G']
    assert doc['five_by_five']['S1']['accuracy_L']['officeqa']['kind'] == 'none'
    assert doc['five_by_five']['S1']['accuracy_L']['officeqa']['source'] == 'invalid'
    plan_path = rp.plan_path(root, 'G')
    plan_path.chmod(0o644)
    plan_path.write_bytes(plan_path.read_bytes().replace(b'"items": 4', b'"items": 5', 1))
    for opened in (False, True):
        result = readout.build(root, open_sealed=opened, now=1 + opened)
        doc = result['chains']['G']
        assert doc['read_plan']['error'] == 'plan_file_mismatch'
        assert 'panels' not in doc and 'five_by_five' not in doc
        text = Path(result['written']['G']['markdown']).read_text()
        assert 'no read table is rendered' in text and '| C0 |' not in text and 'same requests as' not in text


def test_split_phase_contrasts_go_to_the_reference_block_and_macros_print_mixed(tmp_path):
    """R67, R70, R89: a recovery between two units that splits (no same_phase in its owner record) makes their
    contrast a reference value with both time ranges and the recovery number; such a term enters no mean and no
    maximum, and its macro prints 'mixed'. Model ids that differ split as well."""
    order_hint = sorted([(e, b) for (b, e) in OUTCOMES], key=lambda p: (-rp.EVENTS.index(p[0]), ORDER.index(p[1])))
    position = {pair: index for index, pair in enumerate(order_hint)}
    at = T0 + 600 * position[('S2', 'officeqa')] - 100   # after officeqa S5, before officeqa S2 starts
    recovery = {'n': 1, 'decision': 'resume', 'paused': {'reason': 'provider_stop', 'at': clock(at - 7200)},
                'at': clock(at)}
    root, plan, order = economy_root(tmp_path, recoveries=[recovery],
                                     models={('C0', 'alfworld'): ('model-b',)})
    units.write_json(root / 'G' / 'recovery-consumed-1.json', {'by': 'owner', 'date': '2026-11-13', 'decision': 'go'})
    doc = readout.build(root, open_sealed=True, now=0)['chains']['G']
    office = doc['panels']['officeqa']['contrasts']['S3-S2']
    assert office['status'] == 'split' and office['delta'] is None and office['reference']['recoveries'] == [1]
    assert set(office['reference']['ranges']) == {'S5', 'S2'} and office['reference']['point_points'] == 25.0
    alf = doc['panels']['alfworld']['contrasts']['S5-C0']
    assert alf['status'] == 'split' and alf['reference']['reason'] == 'model ids differ'
    assert {(row['bench'], tuple(row['of'])) for row in doc['reference']} >= {('officeqa', ('S5', 'S2')),
                                                                             ('alfworld', ('S5', 'C0'))}
    office_row = next(row for row in doc['reference'] if row['bench'] == 'officeqa' and row['of'] == ['S5', 'S2'])
    assert office_row['contrasts'] == ['S3-C', 'S3-S2', 'S4-C', 'S5-C'] and office_row['recoveries'] == [1]
    term = doc['cl_metrics']['per_bench']['officeqa']['L']['gain_over_C']
    assert term['kind'] == 'split' and term['value'] is None and abs(term['reference'] - .25) < 1e-9
    macro = doc['cl_metrics']['macro']['L']['gain_over_C']   # officeqa and searchqa split, zebralogic measured
    assert macro['a']['value'] is None and macro['a']['text'] == 'mixed: 1 same-phase, 2 split, no mean'
    assert macro['b']['value'] is None and macro['b']['kind'] == 'mixed'
    forgetting = doc['cl_metrics']['per_bench']['officeqa']['L']['forgetting']   # RP4 over same-phase terms only
    assert forgetting['kind'] == 'split' and forgetting['note'] == 'split only'
    assert [row['event'] for row in forgetting['split_terms']] == ['S1', 'S2']
    text = readout.markdown(doc)
    reference = text.split('## Reference block')[1].split('##')[0]
    assert '| officeqa | S5-S2 | S3-C, S3-S2, S4-C, S5-C | +25.0 |' in reference and 'recoveries 1' in reference
    assert 'model ids differ' in reference and 'mixed: 1 same-phase, 2 split, no mean' in text
    assert '| S3-S2 | S5-S2 | not same-phase: reference block only |' in text
    # the same recovery with same_phase: true and a pause of 2 h does not split
    units.write_json(root / 'G' / 'recovery-consumed-1.json', {'by': 'owner', 'date': '2026-11-13', 'decision': 'go',
                                                               'same_phase': True})
    again = readout.build(root, open_sealed=True, now=1)['chains']['G']
    assert again['panels']['officeqa']['contrasts']['S3-S2']['status'] == 'measured'
    assert again['recoveries'] == [{'n': 1, 'at': clock(at), 'basis': 'pause', 'outage_seconds': 7200.0,
                                    'same_phase': True, 'splits': False}]


def test_a_crash_recovery_is_bounded_by_the_latest_earlier_unit_file(tmp_path):
    """R89, R90 phase cases (I-4, I-15): a recovery with paused None whose latest earlier unit file is 10 min older
    than its time and whose owner record says same_phase does not split; without same_phase, or with no earlier
    unit file, it splits; a killed attempt without done.json still has a time range from its cell file times."""
    chain_dir = tmp_path / 'G'
    write_fresh(chain_dir, 'searchqa', 'S5', [True] * 4, start=T0)
    write_fresh(chain_dir, 'searchqa', 'C0', [True] * 4, start=T0 + 3000, done=False)   # killed: no done.json
    _cells, meta = readout._load_fresh_unit(chain_dir / 'test-read-C0-searchqa')
    assert meta['done'] is False and meta['start'] == meta['finish'] == T0 + 3060 and meta['range'][0] == clock(T0 + 3060)
    first, _ = readout._load_fresh_unit(chain_dir / 'test-read-S5-searchqa')[1], None
    for name in ('state.json',):
        assert not (chain_dir / name).exists()

    def phases(at, same):
        units.write_json(chain_dir / 'recovery-consumed-1.json', {'by': 'owner', 'decision': 'go',
                                                                 **({'same_phase': True} if same else {})})
        return readout._Phases(chain_dir, {'recoveries': [{'n': 1, 'paused': None, 'at': clock(at)}]})
    # the latest unit file before the recovery is the S5 done.json (T0 + 300): 10 min earlier
    found = phases(T0 + 900, True)
    assert found.recoveries[0]['outage_seconds'] == 600.0 and not found.recoveries[0]['splits']
    assert found.check(first, meta)['same_phase'] is True
    assert phases(T0 + 900, False).check(first, meta) == {'same_phase': False, 'reason': 'recovery', 'recoveries': [1]}
    early = phases(T0 - 600, True)   # no unit file before it: splits (never treated as 0 h)
    assert early.recoveries[0]['outage_seconds'] is None and early.recoveries[0]['splits']
    assert early.check(first, meta)['same_phase'] is True   # outside the window of these two units
    shifted = dict(first, start=T0 - 1200)
    assert early.check(shifted, meta)['recoveries'] == [1]


def test_generalization_view_marks_home_same_type_and_other_type_benches(tmp_path):
    """One compact view: per step k and bench, S<k> minus the previous state (S0 = C under base historical) from
    the representatives, '-' where the step changed nothing on that panel; home / same-type / other-type from the
    step's type map (officeqa joins searchqa's type at step 2). It decides nothing."""
    root, plan, order = economy_root(tmp_path)
    doc = readout.build(root, open_sealed=True, now=0)['chains']['G']
    view = doc['generalization']
    assert view['S1']['previous'] == 'C' and view['S1']['home_bench'] == 'searchqa'
    s1 = view['S1']['cells']
    assert s1['searchqa']['relation'] == 'home' and s1['searchqa']['kind'] == 'measured'
    assert abs(s1['searchqa']['value'] - 100 / 3) < 1e-9 and s1['searchqa']['of'] == ['S5', 'C']   # q3 unknown: excluded
    assert s1['officeqa']['relation'] == 'other-type' and s1['officeqa']['kind'] == 'same_class'
    s2 = view['S2']['cells']
    assert s2['searchqa']['relation'] == 'same-type' and s2['officeqa']['relation'] == 'home'
    assert view['S3']['cells']['officeqa']['kind'] == 'measured' and view['S3']['cells']['officeqa']['of'] == ['S5', 'S2']
    assert view['S3']['cells']['officeqa']['relation'] == 'other-type'
    assert view['S4']['cells']['zebralogic']['kind'] == 'none' and view['S4']['cells']['zebralogic']['source'] == 'pending'
    assert view['S4']['cells']['zebralogic']['relation'] == 'other-type'    # S4 is the stale pair: no value
    assert view['S3']['home_bench'] == 'zebralogic' and view['S3']['cells']['zebralogic']['kind'] == 'same_class'
    assert view['S5']['cells']['zebralogic']['kind'] == 'none' and view['S5']['cells']['zebralogic']['relation'] == 'other-type'
    assert view['S3']['cells']['alfworld']['kind'] == 'measured'           # the fallback S2 against S5: identical
    assert view['S3']['cells']['alfworld']['requests'] == 'identical'
    text = readout.markdown(doc)
    row = table_row(text.split('## Generalization view')[1], 'S2')
    assert row['searchqa'] == '- (same)' and row['officeqa'] == '- (home)' and row['zebralogic'] == '- (other)'
    assert row['alfworld'] == '+0.0 noise sample (other)'                   # the fallback S2 against S1 (= S5)


def test_a_full_state_renders_exactly_as_without_a_read_plan(tmp_path):
    """R6, ACCEPT: read_plan = full (the code default) keeps the typed-v1 readout: the same documents and markdown
    as a state without a read-plan entry, in both modes."""
    root = make_root(tmp_path)
    plain = {mode: readout.chain_readout(root, 'G', open_sealed=mode, stamp='x') for mode in (False, True)}
    state = json.loads((root / 'G' / 'state.json').read_text())
    units.write_json(root / 'G' / 'state.json', {**state, 'read_plan': {'mode': 'full'}})
    for mode in (False, True):
        doc = readout.chain_readout(root, 'G', open_sealed=mode, stamp='x')
        assert {k: v for k, v in doc.items() if k != 'state'} == {k: v for k, v in plain[mode].items() if k != 'state'}
        assert readout.markdown(doc) == readout.markdown(plain[mode])
    assert readout.status(root)['chains']['G']['read_plan'] == {'mode': 'full', 'plan_sha256': None}


def test_projected_economy_cells_hold_ids_and_hashes_only():
    """R90: the projection keeps returned model ids, the system hash, the first selection request, offered ids, the
    public hash and the first request hash; never a request or reply text."""
    cell = econ_cell('searchqa', 'S5', 'q0', True, ('model-a', 'model-b'))
    cell['mount']['selection'] = {'status': 'ok', 'attempts': [H('selection')], 'raw_excerpt': CANARY}
    cell['mount']['programs_offered'] = ['prog-1']
    cell['selection_sends'] = [{'request_sha256': H('selection'), 'system': CANARY,
                                'receipt': {'returned_model': 'model-a', 'response': CANARY}}]
    row = readout._project_economy(cell)
    assert CANARY not in json.dumps(row)
    assert row['returned_models'] == ['model-a', 'model-b', 'model-a']
    assert row['inputs'] == {'system_sha256': H(system_text('searchqa', 'S5')), 'selection_sha256': H('selection'),
                             'programs_offered': ['prog-1'], 'public_hash': rp.public_sha256(public_of('searchqa', 'q0')),
                             'first_request': None}


# ---- fix-c (batch-3 review rc-readout): the start of learning, noise samples, alias rows, missing terms ------------
def section(text, title, end='\n## '):
    """The markdown text from the heading or line ``title`` to the next level-2 heading."""
    return text.split(title, 1)[1].split(end, 1)[0]


def test_economy_terms_start_from_the_base_row_C_under_historical(tmp_path):
    """rc-readout-1 (addendum D17: C is the start of learning): under base 'historical' S0 := C, so the forward transfer
    of a bench whose requests no step changed before its own step is a structural '-' (officeqa: S1 is in C's class),
    and the plasticity of step 1 is S1 - C, never C's own gain over C0; under 'format' S0 := C0 as before."""
    root, plan, order = economy_root(tmp_path)
    doc = readout.build(root, open_sealed=True, now=0)['chains']['G']
    cl = doc['cl_metrics']
    assert cl['definitions']['S0'] == 'C' and 'S0 := C ' in cl['definitions']['formulas']
    office, search = cl['per_bench']['officeqa']['L'], cl['per_bench']['searchqa']['L']
    assert office['forward_transfer']['kind'] == 'structural' and office['forward_transfer']['of'] == ['S2', 'S2']
    assert search['plasticity']['of'] == ['S5', 'C'] and abs(search['plasticity']['value'] - .25) < 1e-9
    assert search['gain_over_C0']['of'] == ['S5', 'C0'] and abs(search['gain_over_C0']['value'] - .5) < 1e-9  # kept
    text = readout.markdown(doc)
    assert '## Continual-learning metrics (economy: terms through the resolver; S0 := C, the start of learning)' in text
    rows = section(text, '## Continual-learning metrics', 'Side H:')
    assert table_row(rows, 'officeqa')['forward transfer'] == '-' and table_row(rows, 'searchqa')['plasticity'] == '+25.0'
    # base 'format': S0 := C0 (the forward transfer of officeqa is then S1 - C0 through the representatives)
    state = json.loads((root / 'G' / 'state.json').read_text())
    units.write_json(root / 'G' / 'state.json', {**state, 'base_card': 'format'})
    cl = readout.build(root, open_sealed=True, now=1)['chains']['G']['cl_metrics']
    office = cl['per_bench']['officeqa']['L']
    assert cl['definitions']['S0'] == 'C0' and office['forward_transfer']['of'] == ['S2', 'C0']
    assert office['forward_transfer']['kind'] == 'measured' and abs(office['forward_transfer']['value'] - .25) < 1e-9


def test_identical_request_terms_are_noise_samples_in_the_terms_maxima_macros_and_alias_rows(tmp_path, monkeypatch):
    """rc-readout-2: a term between two same-phase fresh units with identical requests (a re-read of a voided alias, a
    fallback class) is a noise sample, never a measured effect: no value of its own, never the RP4 maximum, apart in
    both macro columns, and a 5x5 alias row standing for such a contrast prints its label. Shapes of the review:
    econ2 (spreadsheetbench S4 re-read with S5's requests, alfworld fallback S2) and econ3 (alfworld C a fallback with
    the requests of S1..S5)."""
    monkeypatch.setitem(OUTCOMES, ('alfworld', 'S2'), [True, True, True, False])          # 75 vs S5 50
    monkeypatch.setitem(OUTCOMES, ('spreadsheetbench', 'S4'), [True, True, True, True])   # 100 vs S5 75
    root, plan, order = economy_root(tmp_path / 'econ2')
    doc = readout.build(root, open_sealed=True, now=0)['chains']['G']
    sheet, alf = (doc['cl_metrics']['per_bench'][b]['L'] for b in ('spreadsheetbench', 'alfworld'))
    assert doc['panels']['spreadsheetbench']['contrasts']['S5-S4']['noise_sample'] is True
    back = sheet['backward_transfer']
    assert (back['kind'], back['value'], back['requests']) == ('noise_sample', None, 'identical')
    assert abs(back['reference'] + .25) < 1e-9
    after = sheet['forgetting_after_home']   # S4 only: a noise sample, by construction, never the maximum
    assert after['kind'] == 'structural' and after['value'] == 0.0 and after['structural_terms'] == 0
    assert [(row['event'], round(row['reference'], 9)) for row in after['noise_terms']] == [('S4', .25)]
    forgetting = alf['forgetting']           # S1, S3, S4 in S5's class and the fallback S2 a noise sample
    assert forgetting['kind'] == 'structural' and forgetting['structural_terms'] == 3
    assert [row['event'] for row in forgetting['noise_terms']] == ['S2'] and forgetting['other_max'] is None
    macro = doc['cl_metrics']['macro']['L']['backward_transfer']
    assert macro['b']['n'] == 2 and macro['a']['noise_samples'] == 1 and macro['a']['structural'] == 1
    rows = section(readout.markdown(doc), '## Continual-learning metrics', 'Side H:')
    assert table_row(rows, 'spreadsheetbench')['backward transfer'] == '- (noise sample, ref -25.0)'
    assert table_row(rows, 'alfworld')['forgetting'] == ('- (4 by-construction terms, of which 1 noise sample: '
                                                        'S2 ref +25.0)')
    assert table_row(rows, 'macro (a)')['backward transfer'] == '+12.5 (1 of 4 structural, 1 noise sample as 0)'
    # econ3: C of alfworld is a fallback with the requests of S1..S5
    monkeypatch.setitem(globals(), 'FALLBACK', ('C', 'alfworld'))
    monkeypatch.delitem(OUTCOMES, ('alfworld', 'S2'))
    monkeypatch.setitem(OUTCOMES, ('alfworld', 'C'), [True, False, False, False])          # 25 vs S5 50
    root, plan, order = economy_root(tmp_path / 'econ3')
    doc = readout.build(root, open_sealed=True, now=1)['chains']['G']
    gain = doc['cl_metrics']['per_bench']['alfworld']['L']['gain_over_C']
    assert gain['kind'] == 'noise_sample' and gain['value'] is None and abs(gain['reference'] - .25) < 1e-9
    macro = doc['cl_metrics']['macro']['L']['gain_over_C']
    assert macro['b']['n'] == 3 and macro['a']['noise_samples'] == 1   # searchqa, officeqa, zebralogic measured
    cell = doc['five_by_five']['S1']['diff_points_vs_C']['alfworld']
    assert cell['kind'] == 'alias' and cell['value'] is None and cell['of'] == 'S5'
    assert cell['shown']['kind'] == 'measured' and cell['shown']['requests'] == 'identical'
    five = section(readout.markdown(doc), 'S<k> - C, mean paired', 'Accuracy of S<k> on L')
    assert table_row(five, '1')['alfworld'] == '=S5 +25.0 noise sample u/i/c 0/0/0'
    assert table_row(five, '5')['alfworld'] == '+25.0 noise sample'


def test_a_5x5_alias_row_inside_one_class_is_a_dash_and_otherwise_prints_its_representatives_contrast(tmp_path):
    """rc-readout-4: a 5x5 difference between two events of one class is '-' whatever the row's source (zebralogic S1,
    S2 and C0 are one class; officeqa S1 and C), never '=X —'; another alias row prints the contrast it stands for."""
    root, plan, order = economy_root(tmp_path)
    doc = readout.build(root, open_sealed=True, now=0)['chains']['G']
    five = doc['five_by_five']
    for event in ('S1', 'S2'):
        assert five[event]['diff_points_vs_C0']['zebralogic']['kind'] == 'same_class'
    assert five['S1']['diff_points_vs_C']['officeqa']['kind'] == 'same_class'
    shown = five['S3']['diff_points_vs_C0']['officeqa']
    assert shown['kind'] == 'alias' and shown['of'] == 'S5' and abs(shown['shown']['value'] - 50.0) < 1e-9
    text = readout.markdown(doc)
    vs_c0 = section(text, 'S<k> - C0, mean paired', 'S<k> - C, mean paired')
    vs_c = section(text, 'S<k> - C, mean paired', 'Accuracy of S<k> on L')
    assert table_row(vs_c0, '1')['zebralogic'] == '-' and table_row(vs_c0, '2')['zebralogic'] == '-'
    assert table_row(vs_c, '1')['officeqa'] == '-'
    assert table_row(vs_c0, '3')['officeqa'] == '=S5 +50.0 u/i/c 0/0/0'
    assert '=S3 —' not in text and '=S2 —' not in text


def test_a_maximum_with_a_missing_earlier_reading_is_incomplete(tmp_path):
    """rc-readout-5: zebralogic's S4 is pending (its alias record exists, its state entry not yet): the forgetting
    maximum over S1..S4 is 'incomplete', with the missing event and the maximum of the others beside, never a signed
    value; its macro counts it as pending."""
    root, plan, order = economy_root(tmp_path)
    doc = readout.build(root, open_sealed=True, now=0)['chains']['G']
    forgetting = doc['cl_metrics']['per_bench']['zebralogic']['L']['forgetting']
    assert forgetting['kind'] == 'incomplete' and forgetting['value'] is None
    assert forgetting['missing_terms'] == [{'event': 'S4', 'source': 'pending'}]
    assert abs(forgetting['partial'] + .25) < 1e-9
    macro = doc['cl_metrics']['macro']['L']['forgetting']
    assert macro['a']['pending'] == 2 and macro['a']['benches'] == 3   # zebralogic and spreadsheetbench incomplete
    rows = section(readout.markdown(doc), '## Continual-learning metrics', 'Side H:')
    assert table_row(rows, 'zebralogic')['forgetting'] == 'incomplete [missing: S4 pending; max of the others -25.0]'


def test_the_generalization_view_labels_a_bench_routed_into_the_home_type(tmp_path):
    """rc-readout-3: officeqa has no source at step 1, but the fresh unit standing for S1 (S2, same requests) routed
    its items into searchqa's type t01: at S1 officeqa is 'routed 4/4', not 'other'; a bench none of whose items was
    routed into the home type stays 'other' (officeqa at S3, zebralogic's type)."""
    root, plan, order = economy_root(tmp_path)
    unit = root / 'G' / 'test-read-S2-officeqa' / 'cells'
    for path in sorted(unit.glob('*.json')):
        cell = units.read_json(path, allow_sealed=True)
        path.chmod(0o644)
        units.write_json(path, {**cell, 'mount': {**cell['mount'], 'type': 't01'}}, allow_sealed=True)
    doc = readout.build(root, open_sealed=True, now=0)['chains']['G']
    view = doc['generalization']
    s1 = view['S1']['cells']['officeqa']
    assert (s1['relation'], s1['routed_items'], s1['items']) == ('routed', 4, 4) and s1['kind'] == 'same_class'
    s3 = view['S3']['cells']['officeqa']
    assert (s3['relation'], s3['routed_items'], s3['items'], s3['kind']) == ('other-type', 0, 4, 'measured')
    assert view['S2']['cells']['searchqa']['relation'] == 'same-type'
    row = table_row(section(readout.markdown(doc), '## Generalization view'), 'S1')
    assert row['officeqa'] == '- (routed 4/4)' and row['searchqa'] == '+33.3 (home)'


def test_the_related_gain_table_compares_whole_gate_slices(tmp_path):
    """rc-readout-6: a program decides at home on its fired items (+50 on 2 of 50 items), but the related gain covers
    the member's whole gate slice, so 'home gain pts' is the program's whole-slice gain (+2) and the fired gain has its
    own column; a card row keeps its gain. RP15: the member bench carries its kind."""
    member = {'kind': 'member', 'bench': 'searchqa', 'source': 'src-a', 'n': 40, 'repeats': 3, 'gain_points': -1.0,
              'se_points': .5, 'tau_points': 3.0, 'better': 1, 'worse': 2, 'tied': 37, 'no_regress': True,
              'baseline': {'unit': 's2/member-searchqa-base'}, 'baseline_selected': False}
    program = {'kind': 'program', 'accepted': True, 'reason': 'accepted', 'gain_points_fired': 50.0,
               'gain_points': 2.0, 'fired_items': 2, 'n': 50, 'repeats': 3, 'tau_points': 3.0,
               'shared_with': [{'bench': 'searchqa', 'source': 'src-a', 'member': 'routed', 'routed_gate_items': 2}],
               'members': [member]}
    rows = [readout._decision_row('programs[0]', program)]
    text = '\n'.join(readout._md_related(rows))
    row = table_row(text, 'programs[0]')
    assert row['home gain pts'] == '+2.0' and row['home fired gain pts'] == '+50.0'
    assert row['related gain pts'] == '-1.0' and row['member bench'] == 'searchqa (routed: 2 gate items)'
    card = {**program, 'kind': 'card', 'gain_points': 12.0}
    row = table_row('\n'.join(readout._md_related([readout._decision_row('cards[0]', card)])), 'cards[0]')
    assert row['home gain pts'] == '+12.0' and row['home fired gain pts'] == '—'


def test_the_terminal_read_counts_are_the_readouts(tmp_path):
    """rc-readout-7: ``run`` and ``smoke`` print the read counts of the readout and ``status`` (one definition):
    ``state_summary`` with the chain directory resolves the chain as the readout does."""
    from scripts import run_typed
    root, plan, order = economy_root(tmp_path)
    state = json.loads((root / 'G' / 'state.json').read_text())
    summary = run_typed.state_summary(state, root / 'G')
    status = readout.status(root)['chains']['G']
    assert summary['read_plan']['reads'] == status['reads'] == readout.read_counts(readout._resolve(root, 'G'), state)
    assert summary['read_plan']['reads']['fallbacks'] == 2 and summary['read_plan']['reads']['void_aliases'] == 5
    assert summary['read_plan']['plan'] == plan['plan_sha256'][:12] and summary['read_plan']['mode'] == 'economy'
