"""The per-item mount of typed-v2 (fakes only: scripted clients, a fake shell where an environment would be needed,
no network, no Docker, no /data)."""
import json
import shutil
import tempfile
from pathlib import Path

import pytest

from skillopt.execskill import solver, v222_cards, zebralogic
from skillopt.execskill.errors import BalanceExhausted, PackageInvalid
from skillopt.execskill.package import Package, Procedure, empty
from skillopt.execskill.typed import ORDER, library as lib, mount, tasktypes as typing_, units
from skillopt.execskill.v225_cards import CARD_JOIN
from skillopt.validator_pilot.api import digest
from tests.execskill_fakes_env import Script, receipt
from tests.fixtures.execskill.items import searchqa_items, spreadsheetbench_items


@pytest.fixture
def tmp_path():
    """A neutral directory: pytest's own tmp_path carries the word 'test', which the sealed-path guard refuses."""
    root = Path('/tmp/typed2-neutral')
    root.mkdir(parents=True, exist_ok=True)
    made = Path(tempfile.mkdtemp(prefix='mount-', dir=root))
    try:
        yield made
    finally:
        shutil.rmtree(made, ignore_errors=True)


# ---- fixtures ------------------------------------------------------------------------------------------------
SOURCE = ('"""A fixture program."""\n\n\ndef applies(view):\n    return True\n\n\n'
          'def before_call(view, state):\n    return None\n')
ANSWER = '<answer>Fixtown 0</answer>'
ZEBRA_QUESTION = ('There are 2 houses, numbered 1 to 2 from left to right, as seen from across the street. Each house '
                  'is occupied by a different person. Eric drinks milk. The milk drinker lives in house 1. Arnold '
                  'drinks tea.')
ZEBRA_GRID = {'House 1': {'Name': 'Eric', 'Drink': 'milk'}, 'House 2': {'Name': 'Arnold', 'Drink': 'tea'}}
ZEBRA_ITEM = {'benchmark': 'zebralogic', 'task_id': 'fx-zebra-1',
              'public': {'question': ZEBRA_QUESTION, 'columns': ['Name', 'Drink']}, 'private': {'answer': ZEBRA_GRID}}
JUDGED = {'version': 'fake-judge', 'scorer': 'fake', 'official': {'status': 'pass', 'reason': 'fake'},
          'final': {'token': 'pass'}, 'v2': {'token': 'pass'}, 'lenient': {'pass': True}, 'format': {'reply': True},
          'flags': [], 'carrier': 'official'}


def fake_embedder(texts):
    """Deterministic 8-d vectors: one direction per text family, a small per-text jitter."""
    import random
    rows = []
    for text in texts:
        base = [0.0] * 8
        base[3 if 'treasury' in text else 4] = 1.0
        rng = random.Random(text)
        rows.append([x + rng.uniform(-.05, .05) for x in base])
    return rows


def program_record(pid='fx-typed-a'):
    return Procedure(id=pid, origin='searchqa', description='A fixture program.', hooks=('applies', 'before_call'),
                     source=SOURCE, evidence='engineering_fixture', max_note_chars=600).to_json()


def card_skill(tid):
    return lib.make_skill(skill_id='card-%s-s1' % tid, name='evidence-answer-card', kind='card', home_type=tid,
                          body={'text': '- read every snippet before answering'},
                          origin={'chain': 'G', 'step': 1, 'bench': 'searchqa'}, description='For evidence QA.')


def program_skill(tid, pid='fx-typed-a', name='snippet-scanner'):
    return lib.make_skill(skill_id='prog-%s-s1-%s' % (tid, pid[-1]), name=name, kind='program', home_type=tid,
                          body={'procedure': program_record(pid)}, origin={'chain': 'G', 'step': 1, 'bench': 'searchqa'},
                          description='Scans the snippets for named values.')


def typed_world(*, card=True, programs=1):
    """A type map with one QA source/type and a library with its card and programs."""
    tm = typing_.TypeMap()
    texts = ['Which fixture town keeps the bell number %d?' % i for i in range(40)]
    sid = tm.add_source({'path': '/x/searchqa.json', 'sha256': 'a' * 64}, 'question/context', fake_embedder(texts), step=1)
    tid = tm.new_type(sid, step=1)
    library = lib.Library()
    if card:
        library.add(card_skill(tid))
        tm.set_card(tid, 'card-%s-s1' % tid, step=1)
    for n in range(programs):
        skill = program_skill(tid, pid='fx-typed-%s' % 'abc'[n], name='snippet-scanner-%s' % 'abc'[n])
        library.add(skill)
        tm.add_program(tid, skill['skill_id'], step=1)
    centroid = tm.data['sources'][sid]['centroid']
    return tm, library, tid, centroid


def qa_item():
    return searchqa_items(1)[0]


def far_vector():
    return fake_embedder(['treasury table z'])[0]


# ---- cards -----------------------------------------------------------------------------------------------------
@pytest.mark.parametrize('bench', ORDER)
def test_system_card_bytes_per_bench_and_arm(bench):
    block = mount.format_block(bench)
    assert mount.system_card(bench, '') == block == mount.system_card(bench, '  \n')
    assert mount.system_card(bench, 'learned card') == 'learned card' + CARD_JOIN + block == 'learned card\n\n' + block
    historical = mount.historical_card(bench)
    if bench == 'zebralogic':
        assert block == historical == zebralogic.CARD_TEXT == v222_cards.format_text(bench)
    else:
        assert block == v222_cards.format_text(bench) and historical == v222_cards.historical_text(bench)
        assert historical != block and len(historical) > len(block)
    with pytest.raises(ValueError):
        mount.system_card(bench, None)


def test_mount_arms_compose_the_registered_system_cards():
    tm, library, tid, centroid = typed_world(programs=0)
    item = qa_item()
    c0 = mount.mount('searchqa', item, arm='C0', typemap=None, library=None, vector=None)
    assert c0['system_card'] == mount.format_block('searchqa') and c0['card_text'] == '' and not c0['routed']
    assert c0['signature'] == 'question/context' and c0['type'] is None and c0['selection'] is None
    assert c0['system_card_sha256'] == lib.sha256_text(c0['system_card'])
    c = mount.mount('searchqa', item, arm='C', typemap=None, library=None, vector=None)
    assert c['system_card'] == c['card_text'] == mount.historical_card('searchqa')
    f = mount.mount('searchqa', item, arm='F', typemap=tm, library=library, vector=centroid)
    assert f['system_card'] == '- read every snippet before answering' + CARD_JOIN + mount.format_block('searchqa')
    zc0 = mount.mount('zebralogic', ZEBRA_ITEM, arm='C0', typemap=None, library=None, vector=None)
    zc = mount.mount('zebralogic', ZEBRA_ITEM, arm='C', typemap=None, library=None, vector=None)
    assert zc0['system_card'] == zc['system_card'] == zebralogic.CARD_TEXT and zc0['signature'] == 'puzzle_template'
    # typed-v2 step 5b (addendum D17): B, the learning base, is a mount arm (the base alone; 'format' = C0's text);
    # an unknown arm is still refused (a read event never mounts)
    b = mount.mount('searchqa', item, arm='B', typemap=None, library=None, vector=None)
    assert {**b, 'arm': 'C0'} == c0 and b['arm'] == 'B'
    for unknown in ('S1', 'b', 'C1'):
        with pytest.raises(ValueError, match='Unknown mount arm'):
            mount.mount('searchqa', item, arm=unknown, typemap=None, library=None, vector=None)


# ---- mount records ----------------------------------------------------------------------------------------------
def test_mount_unknown_items_get_no_skill():
    item = qa_item()
    unseen = mount.mount('searchqa', item, arm='F', typemap=typing_.TypeMap(), library=lib.Library(), vector=None)
    assert unseen['unknown_reason'] == 'unseen_signature' and unseen['type'] is None and unseen['routed']
    assert unseen['card_text'] == '' and unseen['system_card'] == mount.format_block('searchqa')
    assert unseen['programs_offered'] == [] and unseen['programs_enabled'] == [] and unseen['enabled'] == []
    tm, library, tid, centroid = typed_world()
    far = mount.mount('searchqa', item, arm='F', typemap=tm, library=library, vector=far_vector())
    assert far['unknown_reason'] == 'distance_above_p95' and far['type'] is None and far['source'].startswith('src-')
    assert far['distance'] > far['threshold'] and far['card_skill'] is None and far['selection'] is None
    assert far['system_card'] == mount.format_block('searchqa')
    with pytest.raises(ValueError):  # a typed structure needs the item's vector
        mount.mount('searchqa', item, arm='F', typemap=tm, library=library, vector=None)
    with pytest.raises(ValueError):  # a routed arm needs the map and the library
        mount.mount('searchqa', item, arm='F', typemap=None, library=None, vector=centroid)


def test_mount_typed_without_programs_makes_no_selection_call():
    tm, library, tid, centroid = typed_world(programs=0)
    calls = Script([])
    rec = mount.mount('searchqa', qa_item(), arm='F', typemap=tm, library=library, vector=centroid, selector=calls)
    assert rec['type'] == tid and rec['unknown_reason'] is None and rec['distance'] <= rec['threshold']
    assert rec['card_skill'] == 'card-%s-s1' % tid and rec['card_text'] == '- read every snippet before answering'
    assert rec['selection']['status'] == 'not_needed' and rec['selection']['tokens'] == 0 and not calls.requests
    assert rec['programs_offered'] == rec['programs_enabled'] == rec['enabled'] == []


def test_mount_typed_with_programs_selects_with_one_format_retry():
    tm, library, tid, centroid = typed_world(programs=2)
    selector = Script(['not json at all', '{"use": ["snippet-scanner-b"], "why": "named values"}'])
    rec = mount.mount('searchqa', qa_item(), arm='F', typemap=tm, library=library, vector=centroid, selector=selector)
    assert rec['programs_offered'] == ['prog-%s-s1-a' % tid, 'prog-%s-s1-b' % tid]
    selection = rec['selection']
    assert selection['status'] == 'ok' and selection['use'] == ['snippet-scanner-b'] and selection['why'] == 'named values'
    assert len(selection['attempts']) == 2 and selection['request_sha256'] == selection['attempts'][1]
    assert selection['tokens'] == 30 and selection['failure'] is None and selection['raw_excerpt'].startswith('{"use"')
    first_user = json.loads(selector.requests[0][1])
    assert first_user['skills'] == library.index(home_type=tid, kinds=('program',)) and first_user['task'].startswith('Which fixture town')
    assert selector.requests[0][0] == lib.SELECTION_SYSTEM and selector.requests[1][1].endswith(lib.SELECTION_RETRY)
    assert rec['programs_enabled'] == ['prog-%s-s1-b' % tid] and rec['enabled'] == [program_record('fx-typed-b')]
    # the library's own (acceptance) order, whatever order the model lists
    both = Script(['{"use": ["snippet-scanner-b", "snippet-scanner-a"], "why": "both"}'])
    rec = mount.mount('searchqa', qa_item(), arm='F', typemap=tm, library=library, vector=centroid, selector=both)
    assert rec['programs_enabled'] == ['prog-%s-s1-a' % tid, 'prog-%s-s1-b' % tid]
    # two unusable replies: a parse failure mounts nothing, and is recorded as such
    bad = Script(['{"use": ["other-skill"], "why": "x"}', receipt('', ok=False)])
    rec = mount.mount('searchqa', qa_item(), arm='F', typemap=tm, library=library, vector=centroid, selector=bad)
    assert rec['selection']['status'] == 'parse_failure' and rec['selection']['failure'] and len(bad.requests) == 2
    assert rec['programs_enabled'] == [] and rec['enabled'] == []
    assert rec['system_card'].startswith('- read every snippet')  # the card stays mounted
    none = Script(['{"use": [], "why": "none applies"}'])
    rec = mount.mount('searchqa', qa_item(), arm='F', typemap=tm, library=library, vector=centroid, selector=none)
    assert rec['selection']['status'] == 'none_selected' and len(none.requests) == 1 and rec['enabled'] == []
    with pytest.raises(ValueError):  # programs without a selector would silently measure nothing
        mount.mount('searchqa', qa_item(), arm='F', typemap=tm, library=library, vector=centroid)


def test_mount_candidate_arms():
    tm, library, tid, centroid = typed_world(programs=0)
    never = Script([])
    candidate = {'procedure': program_record('fx-cand-prog'), 'home_type': tid}
    rec = mount.mount('searchqa', qa_item(), arm='cand_program', typemap=tm, library=library, vector=centroid,
                      selector=never, candidate=candidate)
    assert not never.requests and rec['selection']['status'] == 'not_needed'
    assert rec['enabled'] == [candidate['procedure']] and rec['programs_enabled'] == [] and rec['programs_offered'] == []
    assert rec['candidate'] == {'kind': 'program', 'applied': True, 'id': 'fx-cand-prog',
                                'sha256': candidate['procedure']['record_sha256'], 'home_type': tid}
    package = mount.package_for(rec['enabled'], step='typed/G/s1', evidence='engineering_fixture')
    assert package.order == ('fx-cand-prog',) and package.for_bench('searchqa')[0].id == 'fx-cand-prog'
    as_object = mount.mount('searchqa', qa_item(), arm='cand_program', typemap=tm, library=library, vector=centroid,
                            candidate={'procedure': Procedure.from_json(candidate['procedure']), 'home_type': tid})
    assert as_object['enabled'] == rec['enabled']
    card = mount.mount('searchqa', qa_item(), arm='cand_card', typemap=tm, library=library, vector=centroid,
                       candidate={'text': '- a new card', 'home_type': tid})
    assert card['card_text'] == '- a new card' and card['system_card'] == '- a new card' + CARD_JOIN + mount.format_block('searchqa')
    assert card['card_skill'] == 'card-%s-s1' % tid and card['candidate'] == {
        'kind': 'card', 'applied': True, 'sha256': lib.sha256_text('- a new card'), 'home_type': tid}
    # an item routed to ANOTHER type keeps that type's mount (arm F): acceptance installs the candidate only into its
    # home type, so the gate must not credit it there (Codex review 11/10, finding 3)
    other = mount.mount('searchqa', qa_item(), arm='cand_card', typemap=tm, library=library, vector=centroid,
                        candidate={'text': '- a new card', 'home_type': 't99'})
    plain = mount.mount('searchqa', qa_item(), arm='F', typemap=tm, library=library, vector=centroid)
    assert other['candidate'] == {'kind': 'card', 'applied': False, 'reason': 'other_type', 'home_type': 't99'}
    assert other['system_card'] == plain['system_card'] and other['card_skill'] == plain['card_skill']
    elsewhere = mount.mount('searchqa', qa_item(), arm='cand_program', typemap=tm, library=library, vector=centroid,
                            selector=never, candidate={**candidate, 'home_type': 't99'})
    assert elsewhere['enabled'] == [] and elsewhere['candidate']['applied'] is False
    with pytest.raises(ValueError):  # a candidate always names its home type
        mount.mount('searchqa', qa_item(), arm='cand_card', typemap=tm, library=library, vector=centroid,
                    candidate={'text': '- a new card'})
    unknown = mount.mount('searchqa', qa_item(), arm='cand_card', typemap=tm, library=library, vector=far_vector(),
                          candidate={'text': '- a new card', 'home_type': tid})
    assert unknown['candidate'] == {'kind': 'card', 'applied': False, 'reason': 'distance_above_p95'}
    assert unknown['card_text'] == '' and unknown['system_card'] == mount.format_block('searchqa')
    with pytest.raises(ValueError):
        mount.mount('searchqa', qa_item(), arm='F', typemap=tm, library=library, vector=centroid, candidate={'text': 'x'})
    with pytest.raises(ValueError):
        mount.mount('searchqa', qa_item(), arm='cand_card', typemap=tm, library=library, vector=centroid,
                    candidate={'text': ' ', 'home_type': tid})
    tm.set_card(tid, 'card-of-another-step', step=2)  # the map and the library must agree
    with pytest.raises(ValueError):
        mount.mount('searchqa', qa_item(), arm='F', typemap=tm, library=library, vector=centroid)


# ---- packages and shell readers --------------------------------------------------------------------------------
def test_package_for_and_procedure_from_record():
    record = program_record()
    procedure = mount.procedure_from_record(record)
    assert isinstance(procedure, Procedure) and procedure.to_json() == record and procedure.sha256 == record['record_sha256']
    assert mount.procedure_from_record(procedure) is procedure
    package = mount.package_for([record, program_record('fx-typed-b')], step='typed/G/s2', evidence='engineering_fixture')
    assert isinstance(package, Package) and package.order == ('fx-typed-a', 'fx-typed-b') and package.evidence == 'engineering_fixture'
    assert mount.package_for([], step='typed/G/s2', evidence='smoke') == empty(step='typed/G/s2', evidence='smoke')
    with pytest.raises(PackageInvalid):  # a fixture procedure only rides in a fixture package
        mount.package_for([record], step='typed/G/s2', evidence='smoke')
    tampered = dict(record, description='edited after sealing')
    with pytest.raises(PackageInvalid):
        mount.procedure_from_record(tampered)
    with pytest.raises(ValueError):
        mount.package_for([], step='bad step label', evidence='smoke')
    assert mount.step_label('typed/G/s1 outcomes') == 'typed/G/s1-outcomes' and len(mount.step_label('x' * 300)) == 200


def test_fired_ids_and_faults_from_a_shell_record():
    prediction = {'status': 'available', 'output': 'x', 'shell': {
        'route': {'per_procedure': {'fx-a': {'applies': True, 'enabled': True, 'fault': None},
                                    'fx-b': {'applies': None, 'enabled': False, 'fault': 'exception'},
                                    'fx-c': {'applies': 'default_true', 'enabled': True, 'fault': None},
                                    'fx-d': {'applies': False, 'enabled': False, 'fault': None}},
                  'enabled': ['fx-a', 'fx-c']},
        'faults': [{'procedure': 'fx-b', 'hook': 'applies', 'kind': 'exception', 'exc_type': 'KeyError', 'message': 'k'}],
        'deciding_receipt': 0}}
    assert mount.fired_ids(prediction) == ['fx-a', 'fx-c'] and mount.enabled_ids(prediction) == ['fx-a', 'fx-c']
    assert mount.faults(prediction) == prediction['shell']['faults'] and mount.faults(prediction)[0] is not prediction['shell']['faults'][0]
    assert mount.fired_ids({'status': 'unknown', 'shell': {'route': None, 'faults': []}}) == []
    assert mount.fired_ids({'status': 'unknown'}) == [] and mount.faults(None) == [] and mount.enabled_ids(None) == []


def test_excerpt_and_views(tmp_path):
    assert mount.excerpt(None) is None and mount.excerpt('abc', 10) == 'abc'
    cut = mount.excerpt('x' * 50, 20)
    assert len(cut) == 20 and cut.endswith(mount.TRUNCATION_MARK)
    assert mount.excerpt({'b': 1, 'a': 2}) == '{"a": 2, "b": 1}'
    item = qa_item()
    assert mount.view_of('searchqa', item, None) == {'question': item['public']['question'], 'context': item['public']['context']}
    assert mount.view_of('zebralogic', ZEBRA_ITEM, {'zebralogic': {}}) == {'question': ZEBRA_QUESTION, 'columns': ['Name', 'Drink']}
    sheet = spreadsheetbench_items(tmp_path, 1)[0]
    view = mount.view_of('spreadsheetbench', sheet, {'spreadsheetbench': {'spreadsheet_preview_version': 'public-formula-preview-v1'}})
    assert set(view) == {'instruction', 'workbook_preview', 'input_path', 'required_output_path', 'required_answer_position'}
    assert typing_.structural_signature(view) == 'workbook_preview' and typing_.public_text(view).startswith('Put the sum')
    assert mount.bench_runtime('searchqa', {'searchqa': {'a': 1}, 'officeqa': {}}) == {'a': 1}
    assert mount.bench_runtime('searchqa', None) == {} and mount.bench_runtime('searchqa', {'prompt_layout': 'x'}) == {'prompt_layout': 'x'}
    with pytest.raises(ValueError):
        mount.bench_runtime('searchqa', {'officeqa': {}})


# ---- solve: the real shell and judge on scripted replies ------------------------------------------------------
def c0(bench, item):
    return mount.mount(bench, item, arm='C0', typemap=None, library=None, vector=None)


def test_solve_cell_record_with_the_real_shell_and_judge():
    item = qa_item()
    script = Script([ANSWER])
    row = mount.solve('searchqa', item, c0('searchqa', item), call=script, runtime={'searchqa': {}}, unit='G/s1/outcomes',
                      tag='t1', scorer_root=None, mode='test')
    expected = {'bench', 'item_id', 'arm', 'mount', 'prediction_status', 'output_excerpt', 'reply', 'correct', 'token',
                'official', 'format', 'flags', 'fired', 'faults', 'tokens', 'sends', 'request_sha256',
                'configuration_error', 'infrastructure_unknown', 'failure', 'public_hash'}
    assert expected <= set(row)
    assert row['bench'] == 'searchqa' and row['item_id'] == 'fx-searchqa-00' and row['arm'] == 'C0'
    assert row['correct'] is True and row['token'] == 'pass' and row['official']['status'] == 'pass'
    assert row['prediction_status'] == 'available' and row['reply'] == ANSWER == row['output_excerpt'] and row['output'] is None
    assert row['format']['tag_present'] and row['flags'] == [] and row['fired'] == [] and row['faults'] == []
    assert row['tokens'] == 15 and len(row['sends']) == 1 and row['request_sha256'] == [row['sends'][0]['request_sha256']]
    assert row['configuration_error'] is False and row['infrastructure_unknown'] is False and row['failure'] is None
    assert row['public_hash'] == lib.canonical_sha256(item['public']) and row['evidence'] == 'engineering_fixture'
    assert row['step'] == 'typed/G/s1/outcomes' and row['package_sha256'] == empty(step='typed/G/s1/outcomes', evidence='engineering_fixture').sha256
    assert row['mount']['enabled'] == [] and row['mount']['system_card'] == mount.format_block('searchqa') and row['deciding_receipt'] == 0
    system, user = script.requests[0]
    assert system == (solver.QA_SYSTEM + '\n\n' + solver.GUIDANCE + mount.format_block('searchqa')
                      + '\nReturn the concise final answer inside <answer>...</answer>.')
    assert json.loads(user) == {'question': item['public']['question'], 'context': item['public']['context']}
    json.dumps(row)  # the record is plain JSON


def test_solve_unknown_outcomes_are_never_scored_as_wrong():
    item = qa_item()
    http = {'ok': False, 'response': None, 'finish_reason': None, 'usage': {}, 'error_type': 'http_502'}
    row = mount.solve('searchqa', item, c0('searchqa', item), call=Script([http]), runtime=None, unit='u', tag='t',
                      scorer_root=None, mode='test')
    assert row['correct'] is None and row['token'].startswith('unknown') and row['prediction_status'] == 'unknown'
    assert row['reason'] == 'model_call_unavailable' and row['infrastructure_unknown'] is True
    assert row['configuration_error'] is False and row['reply'] is None and row['tokens'] == 0
    truncated = {'ok': False, 'response': 'partial', 'finish_reason': 'length', 'usage': {}, 'error_type': 'finish_length'}
    row = mount.solve('searchqa', item, c0('searchqa', item), call=Script([truncated]), runtime=None, unit='u', tag='t',
                      scorer_root=None, mode='test')
    assert row['correct'] is False and row['token'] == 'fail' and row['infrastructure_unknown'] is False
    broken = {'ok': True, 'response': ANSWER, 'finish_reason': 'stop', 'usage': {}}
    row = mount.solve('searchqa', item, c0('searchqa', item), call=Script([broken]), runtime={'searchqa': {'prompt_layout': 'unregistered'}},
                      unit='u', tag='t', scorer_root=None, mode='test')
    assert row['correct'] is None and row['reason'] == 'invalid_prompt_layout' and row['configuration_error'] is True
    with pytest.raises(ValueError):
        mount.solve('searchqa', item, c0('searchqa', item), call=Script([ANSWER]), runtime=None, unit='u', tag='t',
                    scorer_root=None, mode='paid')


def test_solve_zebralogic_scores_through_the_judge():
    reply = json.dumps({'reasoning': 'given', 'solution': ZEBRA_GRID})
    script = Script([reply])
    row = mount.solve('zebralogic', ZEBRA_ITEM, c0('zebralogic', ZEBRA_ITEM), call=script, runtime={'zebralogic': {}},
                      unit='u', tag='t', scorer_root=None, mode='smoke')
    assert row['correct'] is True and row['official']['reason'] == 'zebralogic_all_cells_match' and row['score'] is None
    assert row['format']['grid'] is True and row['evidence'] == 'typed_v3_smoke' and row['item_id'] == 'fx-zebra-1'
    assert script.requests[0][0] == solver.QA_SYSTEM + '\n\n' + solver.GUIDANCE + zebralogic.CARD_TEXT
    assert script.requests[0][1].endswith('\n') and ZEBRA_QUESTION in script.requests[0][1]
    wrong = Script([json.dumps({'reasoning': 'x', 'solution': {**ZEBRA_GRID, 'House 2': {'Name': 'Peter', 'Drink': 'tea'}}})])
    row = mount.solve('zebralogic', ZEBRA_ITEM, c0('zebralogic', ZEBRA_ITEM), call=wrong, runtime=None, unit='u', tag='t',
                      scorer_root=None, mode='smoke')
    assert row['correct'] is False and row['official']['reason'] == 'zebralogic_cell_mismatch'


def test_solve_reraises_ledger_and_balance_stops_instead_of_recording_unknowns(tmp_path):
    item = qa_item()
    capped = units.Ledger(tmp_path / 'ledger.json', 1_000)
    call = units.CallRecorder(lambda s, u: receipt(ANSWER), capped, max_tokens=4000, tag='t', unit='u', out_path=None)
    with pytest.raises(units.Stop):  # the frozen shell would have recorded model_call_exception:Stop
        mount.solve('searchqa', item, c0('searchqa', item), call=call, runtime=None, unit='u', tag='t', scorer_root=None, mode='test')
    assert capped.state['stop_reason'] == 'token_cap'
    exhausted = Script([BalanceExhausted('route B balance')])
    with pytest.raises(BalanceExhausted):
        mount.solve('searchqa', item, c0('searchqa', item), call=exhausted, runtime=None, unit='u', tag='t', scorer_root=None, mode='test')
    # an ordinary client exception stays the shell's unknown reply, counted as infrastructure
    flaky = Script([RuntimeError('socket closed')])
    row = mount.solve('searchqa', item, c0('searchqa', item), call=flaky, runtime=None, unit='u', tag='t', scorer_root=None, mode='test')
    assert row['correct'] is None and row['reason'] == 'model_call_exception:RuntimeError' and row['infrastructure_unknown'] is True
    assert row['sends'][0]['exception'] == 'RuntimeError'
    # a recorder's own send log and token count are the cell's
    ledger = units.Ledger(tmp_path / 'big.json', 10 ** 7)
    recorder = units.CallRecorder(lambda s, u: receipt(ANSWER), ledger, max_tokens=4000, tag='t', unit='u',
                                  out_path=tmp_path / 'calls.json')
    row = mount.solve('searchqa', item, c0('searchqa', item), call=recorder, runtime=None, unit='u', tag='t', scorer_root=None, mode='test')
    assert row['correct'] is True and row['sends'] == recorder.sends and row['tokens'] == recorder.tokens() == 15
    assert 'system' in row['sends'][0] and ledger.state['reported'] == 15


# ---- solve: fake shell where an environment would be needed ------------------------------------------------------
def fake_prediction(output, **extra):
    return {'status': 'available', 'output': output, 'costs': {'calls': 1, 'usage': {}}, 'reason': 'fake',
            'shell': {'route': None, 'calls': [], 'procedure_events': [], 'faults': [], 'deciding_receipt': 0}, **extra}


class FakeNative:
    def __init__(self):
        self.held, self.holds = False, 0

    def hold(self):
        native = self

        class Hold:
            def __enter__(self):
                native.held, native.holds = True, native.holds + 1

            def __exit__(self, *args):
                native.held = False
        return Hold()


def test_solve_sheet_score_context_and_native_hold(tmp_path, monkeypatch):
    item = spreadsheetbench_items(tmp_path / 'items', 1)[0]
    native, seen = FakeNative(), {}

    def fake_solve(bench, public, card_text, package, call, **options):
        seen['solve'] = {'bench': bench, 'card': card_text, 'package': package, 'options': options}
        call('system', 'user')
        return fake_prediction({'code': 'print(1)', 'cases': [{'status': 'available', 'output_base64': 'AAAA'}]})

    def fake_score(bench, public, private, prediction, *, runtime):
        seen['context'] = runtime['_score_context']
        seen['held'] = native.held
        return {'status': 'pass', 'score': 1.0, 'reason': 'fake_recalc', 'metrics': {}}

    def fake_judge(bench, public, private, prediction, receipts, *, runtime, score):
        seen['judge'] = {'receipts': len(receipts), 'score': score, 'runtime': runtime}
        return dict(JUDGED)
    monkeypatch.setattr(mount.solver, 'solve', fake_solve)
    monkeypatch.setattr(mount.backends, 'score', fake_score)
    monkeypatch.setattr(mount.judge, 'judge', fake_judge)
    runtime = {'spreadsheetbench': {'prompt_layout': 'contract-first-v2', 'spreadsheet_scorer': 'qualified_lo_recalc_v7_v1'}}
    root = tmp_path / 'unit'
    row = mount.solve('spreadsheetbench', item, c0('spreadsheetbench', item), call=Script(['```python\nprint(1)\n```']),
                      runtime=runtime, native=native, nominal_tokens=16384, unit='G/s4/outcomes', tag='cell-9',
                      scorer_root=root, mode='run')
    context = seen['context']
    request = {'benchmark': 'spreadsheetbench', 'unit': 'G/s4/outcomes', 'cell': 'cell-9', 'scoring': 0}
    assert set(context) == {'artifact_dir', 'position', 'request', 'prediction_hash'}
    assert context['request'] == request and context['position'] == digest(request)
    assert context['artifact_dir'] == str(root / 'host_only' / 'scorer_artifacts' / context['position'])
    assert seen['held'] is True and native.holds == 1 and not native.held
    assert seen['solve']['options']['native'] is native and seen['solve']['options']['nominal_tokens'] == 16384
    assert seen['solve']['options']['configuration'] == 'main-v10' and seen['solve']['options']['worker'] is None
    assert seen['solve']['options']['runtime'] == runtime['spreadsheetbench'] and seen['solve']['package'].evidence == 'pilot_real_run'
    assert seen['judge'] == {'receipts': 1, 'score': {'status': 'pass', 'score': 1.0, 'reason': 'fake_recalc', 'metrics': {}},
                             'runtime': runtime['spreadsheetbench']}
    assert '_score_context' not in seen['judge']['runtime']
    assert row['correct'] is True and row['score']['status'] == 'pass' and row['score_position'] == {'position': context['position'], 'scoring': 0}
    assert row['output'] == {'code': 'print(1)', 'cases': [{'status': 'available', 'reason': None}]} and row['evidence'] == 'typed_v3_real_run'
    assert 'AAAA' not in json.dumps(row) and row['nominal_tokens'] == 16384
    # an interrupted attempt at position 0 moves the next scoring to a fresh position; a saved result of the same
    # prediction is reused; another prediction's result is skipped
    prediction = fake_prediction({'code': 'print(1)', 'cases': []})
    first = Path(mount.score_context('u', 't', root, prediction)['artifact_dir'])
    first.mkdir(parents=True)
    (first / 'started.json').write_text('{}')
    assert mount.fresh_score_context('u', 't', root, prediction)['request']['scoring'] == 1
    (first / 'result.json').write_text(json.dumps({'binding': {'prediction_hash': digest(prediction)}}))
    assert mount.fresh_score_context('u', 't', root, prediction)['request']['scoring'] == 0
    (first / 'result.json').write_text(json.dumps({'binding': {'prediction_hash': 'other'}}))
    assert mount.fresh_score_context('u', 't', root, prediction)['request']['scoring'] == 1
    with pytest.raises(ValueError):
        mount.solve('spreadsheetbench', item, c0('spreadsheetbench', item), call=Script(['x']), runtime=runtime,
                    unit='u', tag='t', scorer_root=None, mode='run')


def test_solve_scoring_exception_is_an_unknown_score(tmp_path, monkeypatch):
    item = spreadsheetbench_items(tmp_path / 'items', 1)[0]

    def fake_solve(bench, public, card_text, package, call, **options):
        call('system', 'user')
        return fake_prediction({'code': 'x', 'cases': []})

    def broken_score(*args, **kwargs):
        raise KeyError('test_files')
    judged = {}

    def fake_judge(bench, public, private, prediction, receipts, *, runtime, score):
        judged['score'] = score
        return {**JUDGED, 'v2': {'token': 'unknown'}, 'final': {'token': 'unknown'}, 'official': {'status': 'unknown', 'reason': score['reason']}}
    monkeypatch.setattr(mount.solver, 'solve', fake_solve)
    monkeypatch.setattr(mount.backends, 'score', broken_score)
    monkeypatch.setattr(mount.judge, 'judge', fake_judge)
    row = mount.solve('spreadsheetbench', item, c0('spreadsheetbench', item), call=Script(['x']), runtime=None,
                      unit='u', tag='t', scorer_root=tmp_path, mode='test')
    assert judged['score']['reason'] == 'native_scoring_exception:KeyError' and row['correct'] is None
    assert row['infrastructure_unknown'] is False and row['configuration_error'] is False


def test_solve_worker_factory_only_with_enabled_programs(monkeypatch):
    tm, library, tid, centroid = typed_world(programs=1)
    item = qa_item()
    seen, made = [], []

    class FakeWorker:
        pass

    def factory():
        made.append(FakeWorker())
        return made[-1]

    def fake_solve(bench, public, card_text, package, call, **options):
        seen.append({'package': package, 'worker': options['worker'], 'card': card_text})
        call('s', 'u')
        return fake_prediction(ANSWER, shell={'route': {'per_procedure': {'fx-typed-a': {'applies': True, 'enabled': True}},
                                                        'enabled': ['fx-typed-a']}, 'faults': [], 'deciding_receipt': 0})
    monkeypatch.setattr(mount.solver, 'solve', fake_solve)
    monkeypatch.setattr(mount.judge, 'judge', lambda *a, **k: dict(JUDGED))
    selector = Script(['{"use": ["snippet-scanner-a"], "why": "use it"}'])
    mounted = mount.mount('searchqa', item, arm='F', typemap=tm, library=library, vector=centroid, selector=selector)
    row = mount.solve('searchqa', item, mounted, call=Script([ANSWER]), runtime=None, worker_factory=factory,
                      unit='G/s1/outcomes', tag='t', scorer_root=None, mode='test', step='typed/G/s1')
    assert len(made) == 1 and seen[0]['worker'] is made[0] and seen[0]['package'].order == ('fx-typed-a',)
    assert seen[0]['package'].step == 'typed/G/s1' and seen[0]['card'] == mounted['system_card']
    assert row['fired'] == ['fx-typed-a'] and row['route_enabled'] == ['fx-typed-a'] and row['correct'] is True
    assert row['mount']['enabled'] == [{'id': 'fx-typed-a', 'record_sha256': program_record('fx-typed-a')['record_sha256']}]
    assert row['mount']['programs_enabled'] == ['prog-%s-s1-a' % tid] and row['package_sha256'] == seen[0]['package'].sha256
    with pytest.raises(ValueError):  # programs need a worker factory
        mount.solve('searchqa', item, mounted, call=Script([ANSWER]), runtime=None, unit='u', tag='t', scorer_root=None, mode='test')
    plain = mount.mount('searchqa', item, arm='C0', typemap=None, library=None, vector=None)
    mount.solve('searchqa', item, plain, call=Script([ANSWER]), runtime=None, worker_factory=factory, unit='u', tag='t',
                scorer_root=None, mode='test')
    assert len(made) == 1 and seen[1]['worker'] is None and seen[1]['package'].order == ()


def test_solve_alfworld_summary_and_episode_slot(monkeypatch):
    item = {'benchmark': 'alfworld', 'task_id': 'fx-alf-1', 'public': {'game_file': '/x/game.tw-pddl'}, 'private': {}}
    episodes, seen = FakeNative(), {}

    def fake_solve(bench, public, card_text, package, call, **options):
        seen['held'] = episodes.held
        call('s', 'u')
        call('s', 'u2')
        trace = [{'observation': 'You are in a kitchen.', 'action': 'go to sink 1', 'post_observation': 'You arrive at sink 1.'},
                 {'observation': 'You arrive at sink 1.', 'action': 'take mug 1', 'post_observation': 'You won!'}]
        return fake_prediction({'won': True, 'steps': 2}, trace=trace,
                               shell={'route': None, 'faults': [], 'deciding_receipt': 1})
    monkeypatch.setattr(mount.solver, 'solve', fake_solve)
    monkeypatch.setattr(mount.judge, 'judge', lambda *a, **k: dict(JUDGED))
    mounted = {'arm': 'C0', 'system_card': mount.format_block('alfworld'), 'enabled': []}
    row = mount.solve('alfworld', item, mounted, call=Script(['<action>go to sink 1</action>', '<action>take mug 1</action>']),
                      runtime={'alfworld': {'max_steps': 50}}, unit='u', tag='t', scorer_root=None, mode='test', episodes=episodes)
    assert seen['held'] is True and episodes.holds == 1 and not episodes.held
    assert row['output'] == {'won': True, 'steps': 2, 'trace_steps': 2, 'last_action': 'take mug 1', 'last_observation': 'You won!'}
    assert row['reply'] == '<action>take mug 1</action>' and row['deciding_receipt'] == 1 and len(row['sends']) == 2
    assert row['system_card_sha256'] == lib.sha256_text(mount.format_block('alfworld'))


def test_solve_shell_exception_is_a_configuration_failure(monkeypatch):
    item = qa_item()

    def broken(bench, public, card_text, package, call, **options):
        call('s', 'u')
        raise KeyError('runtime')
    monkeypatch.setattr(mount.solver, 'solve', broken)
    row = mount.solve('searchqa', item, c0('searchqa', item), call=Script([ANSWER]), runtime=None, unit='u', tag='t',
                      scorer_root=None, mode='test')
    assert row['failure'] == 'KeyError' and row['configuration_error'] is True and row['correct'] is None
    assert row['token'] is None and len(row['sends']) == 1 and row['tokens'] == 15 and row['infrastructure_unknown'] is False
