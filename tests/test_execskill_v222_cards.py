"""Pinned instruction decompositions and authored local request identities; no model or task data."""
from copy import deepcopy
from dataclasses import replace
import hashlib
import json

import pytest

from skillopt.execskill import instruction_start, notes, policy, profiles as p, reuse, solver, v222_cards as cards
from skillopt.execskill.package import Package, Procedure, empty, procedure_benches
from tests.execskill_fakes_env import FakeSandbox
from tests.execskill_v293_fakes import tmp_path  # noqa: F401

VIEWS = {
    'searchqa': {'question': 'Who wrote the short story?', 'context': 'Snippet one: Morgan wrote the short story.'},
    'officeqa': {'question': 'What was the total amount in dollars?', 'context': 'Quantity table: total 40 dollars.'},
    'zebralogic': {'puzzle': 'A finite ordered-house puzzle.', 'num_houses': 3, 'categories': {}},
    'spreadsheetbench': {'instruction': 'Copy a value.', 'workbook_preview': {'Sheet1': [['x']]},
                        'input_path': 'input.xlsx', 'required_output_path': 'output.xlsx',
                        'required_answer_position': 'A1'},
    'alfworld': {'initial_observation': 'Your task is to: move an object.',
                'admissible_commands_at_reset': ['look'], 'task_text': 'move an object.'},
}


def functions(package):
    hooks = {}
    for procedure in package.procedures:
        namespace = {}
        exec(procedure.source, namespace)
        hooks[procedure.id] = {hook: namespace[hook] for hook in procedure.hooks}
    return hooks


def test_all_five_historical_cards_are_losslessly_partitioned_and_pinned():
    found = cards.pins()
    assert set(found) == set(instruction_start.pins())
    assert set(found) == {'searchqa', 'officeqa', 'livemath', 'spreadsheetbench', 'alfworld'}
    for bench, row in found.items():
        assert 2 <= len(row['segments']) <= 5
        lines = row['historical']['text'].splitlines(True)
        recovered = {}
        for part in [row['format'], *row['segments']]:
            assert part['sha256'] == hashlib.sha256(part['text'].encode()).hexdigest()
            for index in part['line_indices']:
                assert index not in recovered
                recovered[index] = lines[index]
        assert ''.join(recovered[i] for i in sorted(recovered)) == instruction_start.pins()[bench]['text']
    assert cards.format_text('zebralogic') == 'Follow the format in the user message.'
    assert cards.manifest_pins()['segments']['zebralogic'] == []
    assert cards.manifest_pins()['inactive_historical_bench'] == 'livemath'


def test_changed_fixture_is_rejected_before_a_procedure_is_created(tmp_path, monkeypatch):
    for name in cards.FILE_SHA256:
        (tmp_path / name).write_bytes((cards.FIXTURE / name).read_bytes())
    path = tmp_path / 'searchqa.json'
    path.write_text(path.read_text() + '\n')
    monkeypatch.setattr(cards, 'FIXTURE', tmp_path)
    with pytest.raises(ValueError, match='decomposition hash differs'):
        cards.initial_package(evidence='engineering_fixture')


def test_initial_package_has_real_note_procedures_with_unchanged_caps_and_roundtrips():
    package = cards.initial_package(evidence='engineering_fixture', step='G/s0')
    assert len(package.procedures) == 11 and package.step == 'G/s0'
    for proc in package.procedures:
        assert proc.policy_version == policy.POLICY_VERSION_V222
        assert proc.max_note_chars == 1500
        assert set(proc.hooks) == {'applies', 'before_call', 'alf_before_step'}
        assert cards.is_segment(proc) and cards.segment_metadata(proc)['seeded']
        assert Procedure.from_json(proc.to_json()) == proc
        namespace = {}
        exec(proc.source, namespace)
        assert ''.join(namespace['SEGMENT_FIELDS']['facts']) == namespace['SEGMENT_TEXT']
        assert all(len(chunk) <= 200 for chunk in namespace['SEGMENT_FIELDS']['facts'])
        fields, dropped = notes.screen(namespace['SEGMENT_FIELDS'], bench=proc.origin,
                                       outcome_judged=True, audited=True)
        assert not notes.fault_drops(dropped, outcome_judged=True)
        assert len(notes.render(fields, bench=proc.origin, header='')) <= 1500
    assert notes.MAX_NOTE_CHARS['alfworld'] == 1500
    assert notes.MAX_NOTE_CHARS['searchqa'] == 4000


@pytest.mark.parametrize('bench', cards.BENCHES)
def test_seed_predicates_use_public_structure_and_fire_only_at_authored_home(bench):
    package = cards.initial_package(evidence='engineering_fixture')
    hooks = functions(package)
    for proc in package.procedures:
        expected = proc.origin == bench
        assert hooks[proc.id]['applies'](VIEWS[bench]) is expected
        changed = dict(VIEWS[bench], bench='wrong-name', benchmark='wrong-name', id='foreign-id')
        assert hooks[proc.id]['applies'](changed) is expected


def test_quantity_cues_are_words_and_learning_can_transfer_shared_structure():
    generic = cards.make_segment('searchqa', 'Inspect the supplied evidence.', {'kind': 'public_evidence'},
                                 evidence='engineering_fixture', step=1)
    hooks = functions(Package((generic,), 'G/one', 'engineering_fixture'))
    assert hooks[generic.id]['applies'](VIEWS['searchqa'])
    assert hooks[generic.id]['applies'](VIEWS['officeqa'])
    package = cards.initial_package(evidence='engineering_fixture')
    hooks = functions(package)
    pirate = dict(VIEWS['searchqa'], question='Which pirate wrote the story?')
    assert all(hooks[proc.id]['applies'](pirate) for proc in cards.own_segments(package, 'searchqa'))
    assert not any(hooks[proc.id]['applies'](pirate) for proc in cards.own_segments(package, 'officeqa'))
    with pytest.raises(ValueError, match='public task structure'):
        cards.make_segment('searchqa', 'Inspect evidence.', {'kind': 'benchmark_name'}, evidence='engineering_fixture')


@pytest.mark.parametrize('bench', ['searchqa', 'officeqa', 'spreadsheetbench'])
def test_segments_change_actual_request_and_log_emitted_note_identity(bench):
    package = cards.initial_package(evidence='engineering_fixture')
    worker = FakeSandbox(functions(package)).start(package, kind='cell')
    observed = []
    identity = reuse.signature(bench, package, VIEWS[bench], worker, card_text=cards.format_text(bench),
                               configuration=p.MAIN_V8, note_observer=lambda shell, _: observed.append(shell.record()))
    blank = empty(step='G/s0', evidence='engineering_fixture')
    base = reuse.signature(bench, blank, VIEWS[bench], None, card_text=cards.format_text(bench), configuration=p.MAIN_V8)
    assert identity['request_sha256'] != base['request_sha256']
    assert identity['faults'] == []
    assert observed[0]['notes'] and all(row['delivered_text'] for row in observed[0]['notes'])
    assert all(row['origin'] == bench and row['segment']['home'] == bench for row in observed[0]['notes'])
    worker.close()


def test_alf_segments_deliver_through_existing_per_step_hook_and_total_cap():
    package = cards.initial_package(evidence='engineering_fixture')
    worker = FakeSandbox(functions(package)).start(package, kind='cell')
    shell = solver._Shell('alfworld', package, lambda *a, **k: pytest.fail('no model call'), worker,
                          withhold=(), restore=(), placebo=None, text=None, native=None, nominal=None,
                          configuration=p.MAIN_V8)
    shell.started = True
    shell.route_on(VIEWS['alfworld'])
    view = {'initial_observation': VIEWS['alfworld']['initial_observation'], 'observation': 'A room.',
            'admissible_commands': ['look'], 'recent_history': []}
    text, discouraged = shell.before_step(view, {}, 0)
    assert text and len(text) <= 1500 and discouraged == []
    emitted = [row for row in shell.record()['notes'] if row['delivered_text']]
    assert emitted and all(row['hook'] == 'alf_before_step' for row in emitted)
    assert len(emitted) < len(cards.own_segments(package, 'alfworld'))  # unchanged aggregate cap stays real
    worker.close()


def test_only_exact_pinned_seed_source_gets_public_alf_example_exception():
    package = cards.initial_package(evidence='engineering_fixture')
    examples = [proc for proc in cards.own_segments(package, 'alfworld')
                if any(v.rule == 'receptacle_literal' for v in policy.check(proc.source, version=policy.POLICY_VERSION_V29))]
    assert examples
    for proc in examples:
        assert policy.check(proc.source, version=policy.POLICY_VERSION_V222) == []
        assert any(v.rule == 'receptacle_literal' for v in policy.check(proc.source + '\n# changed\n', version=policy.POLICY_VERSION_V222))


def test_new_policy_scope_and_records_do_not_change_legacy_procedures():
    source = 'def applies(view):\n    return True\n\ndef before_call(view, state):\n    return {}\n'
    old = Procedure(id='p-searchqa-1-1', origin='searchqa', description='Authored scope check',
                    hooks=('applies', 'before_call'), source=source, evidence='engineering_fixture',
                    max_note_chars=100, policy_version=policy.POLICY_VERSION_V29)
    new = replace(old, policy_version=policy.POLICY_VERSION_V222)
    assert 'zebralogic' not in procedure_benches(old) and 'zebralogic' in procedure_benches(new)
    assert old.to_json()['version'].endswith('procedure-v2-9')
    assert new.to_json()['version'].endswith('procedure-v2-22')
    assert notes.audited(new) and notes.outcome_judged(new)
    assert policy.source_limit(new.policy_version) == policy.source_limit(old.policy_version)
    assert policy.policy_sha256(version=policy.POLICY_VERSION_V29) != policy.policy_sha256(version=policy.POLICY_VERSION_V222)


@pytest.mark.parametrize('bench', cards.BENCHES)
def test_arm_contracts_and_historical_card_check_are_explicit(bench):
    package = cards.initial_package(evidence='engineering_fixture', step='G/s0')
    arms = {arm: cards.arm_definition(bench, arm, package=package, initial=package) for arm in cards.ARMS}
    assert arms['B']['card'] == '' and not arms['B']['package'].order
    assert arms['C0']['card'] == cards.format_text(bench) and not arms['C0']['package'].order
    assert arms['C']['package'] == arms['F']['package'] == package
    assert all(arms[arm]['card'] == cards.format_text(bench) for arm in ('C0', 'C', 'F'))
    with pytest.raises(ValueError, match='only to the decomposition'):
        cards.arm_definition(bench, 'C_hist')
    assert cards.arm_definition(bench, 'C_hist', decomposition=True)['card'] == cards.historical_text(bench)
    with pytest.raises(ValueError, match='only for main-v8'):
        cards.arm_definition(bench, 'C', configuration=p.MAIN_V7)


def test_zebra_format_is_in_main_v8_system_only_and_blank_stays_blank():
    neutral = cards.format_text('zebralogic')
    assert neutral in solver._system('zebralogic', neutral, {}, configuration=p.MAIN_V8)
    assert solver._system('zebralogic', neutral, {}, configuration=p.MAIN_V7) == solver.QA_SYSTEM
    assert solver._system('zebralogic', '', {}, configuration=p.MAIN_V8) == solver.QA_SYSTEM


def test_active_and_historical_card_maps_are_distinct_only_for_new_configuration():
    active = {bench: cards.format_text(bench) for bench in cards.BENCHES}
    assert instruction_start.active_cards(active, p.MAIN_V8) == active
    assert instruction_start.original_cards(active, p.MAIN_V8) == {bench: cards.historical_text(bench) for bench in cards.BENCHES}
    fallback = {**active, 'searchqa': cards.historical_text('searchqa')}
    assert instruction_start.active_cards(fallback, p.MAIN_V8) == fallback
    with pytest.raises(ValueError, match='fixed format blocks'):
        instruction_start.active_cards({**active, 'searchqa': 'unregistered card'}, p.MAIN_V8)


def test_answer_markers_cannot_be_hidden_at_a_chunk_boundary():
    for text in ['<answer>bad</answer>', 'x' * 198 + '<answer>bad</answer>']:
        with pytest.raises(ValueError, match='unchanged note safety'):
            cards.make_segment('searchqa', text, {'kind': 'public_evidence'}, evidence='engineering_fixture')


def sample(bench, passed=80, counter=100):
    field = {'searchqa': 'tag_present', 'officeqa': 'single_number', 'spreadsheetbench': 'program_delivered',
             'zebralogic': 'program_delivered', 'alfworld': 'action_violations'}[bench]
    items = 20 if bench == 'alfworld' else 100
    passed = min(passed, items)
    return {'items': items, 'passed': passed, 'observed_passed': passed, 'unknown': 0,
            'unknown_by_token': {}, 'scoring_side': 'H', 'format': {field: min(counter, items)},
            'format_applicable': {field: items}, 'format_not_applicable': {field: 0}}


def test_decomposition_accuracy_and_format_guards_are_both_required():
    assert cards.decomposition_decision('searchqa', sample('searchqa'), sample('searchqa', 79))['decision'] == 'accept_split'
    assert cards.decomposition_decision('searchqa', sample('searchqa'), sample('searchqa', 78))['decision'] == 'whole_card_fallback'
    assert cards.decomposition_decision('searchqa', sample('searchqa'), sample('searchqa', counter=99))['decision'] == 'whole_card_fallback'
    assert cards.decomposition_decision('alfworld', sample('alfworld', counter=2), sample('alfworld', counter=1))['decision'] == 'accept_split'
    assert cards.decomposition_decision('alfworld', sample('alfworld', counter=2), sample('alfworld', counter=3))['decision'] == 'whole_card_fallback'


@pytest.mark.parametrize('bench', ['officeqa', 'spreadsheetbench', 'alfworld'])
def test_whole_card_fallback_removes_seed_notes_without_truncating_or_raising_caps(bench):
    initial = cards.initial_package(evidence='engineering_fixture', fallback=[bench])
    assert not cards.own_segments(initial, bench) and not initial.for_bench(bench)
    bad = cards.decomposition_decision(bench, sample(bench, counter=0 if bench == 'alfworld' else 100),
                                      sample(bench, passed=0, counter=1 if bench == 'alfworld' else 100))
    assert bad['decision'] == 'whole_card_fallback' and bad['hygiene_enabled'] is False
    assert bad['shell_card_sha256'] == hashlib.sha256(cards.historical_text(bench).encode()).hexdigest()


def test_decomposition_identity_needs_all_requests_and_no_faults():
    identity = {'request_sha256': 'a' * 64, 'post_call': [], 'faults': []}
    pairs = {str(i): {'C_hist': identity, 'C': dict(identity)} for i in range(100)}
    assert cards.decomposition_identity('zebralogic', pairs)['decision'] == 'accept_identity'
    pairs['0']['C']['faults'] = [{'kind': 'authored'}]
    assert cards.decomposition_identity('zebralogic', pairs)['decision'] == 'measurement_required'
    with pytest.raises(ValueError, match='entire registered available-count'):
        cards.decomposition_identity('zebralogic', {})


def test_decomposition_draw_is_seeded_and_uses_exact_practice_denominators():
    pools = {bench: ['authored-%03d' % i for i in range(140)] for bench in cards.BENCHES}
    first = cards.decomposition_slices(pools)
    assert first == cards.decomposition_slices({bench: list(reversed(rows)) for bench, rows in pools.items()})
    assert {bench: row['count'] for bench, row in first.items()} == {bench: 20 if bench == 'alfworld' else 100 for bench in cards.BENCHES}
    assert all(row['side'] == 'practice' and row['arms'] == ['C_hist', 'C'] for row in first.values())


def test_learned_segment_uses_existing_engineer_parse_and_build_then_enforces_actual_fixed_delivery():
    from types import SimpleNamespace
    from skillopt.execskill import engineer
    from skillopt.execskill.errors import PackageInvalid
    proc = cards.make_segment('searchqa', 'Inspect the supplied evidence.', {'kind': 'public_evidence'},
                              evidence='engineering_fixture', step=1)
    entry = {'kind': 'new', 'description': 'A transferable content segment', 'hooks': list(proc.hooks),
             'max_note_chars': 1500, 'requests_second_call': False, 'state_bytes': 0}
    reply = '```json\n' + json.dumps({'changes': [entry]}) + '\n```\n```python\n' + proc.source + '\n```'
    entries, sources = engineer.parse(reply, lenient=True)
    change = engineer.changes_of(entries, sources, 'a' * 64)[0]
    change.trajectory_resolution = []  # authored proposal has no replay references
    ctx = SimpleNamespace(configuration=p.MAIN_V8, bench='searchqa', k=1, mode=engineer.TRAIN,
                          parent=empty(step='G/s0', evidence='engineering_fixture'), reserved=set(), sheet={},
                          step='G/s1-searchqa', evidence='engineering_fixture')
    result = engineer._build(change, ctx)
    assert cards.is_segment(result.procedures[0]) and result.procedures[0].policy_version == policy.POLICY_VERSION_V222
    assert 'V222_SEGMENT' in cards.ENGINEER_SENTENCE and 'kind=new or revision' in cards.ENGINEER_SENTENCE
    with pytest.raises(PackageInvalid, match='at most 1500'):
        replace(proc, max_note_chars=1501)
    with pytest.raises(PackageInvalid, match='fixed fields with before_call'):
        replace(proc, source=proc.source.replace('def before_call(view, state):\n    return SEGMENT_FIELDS',
                                               'def before_call(view, state):\n    return {}'))
    with pytest.raises(PackageInvalid, match='rather than benchmark'):
        replace(proc, source=proc.source.replace(cards.PREDICATES['public_evidence'], "view.get('bench') == 'searchqa'"))


def test_new_worker_bundle_loads_p0_and_imported_policies_without_promoting_old_sources():
    from skillopt.execskill.sandbox import client, worker, worker_v215, worker_v222
    package = cards.initial_package(evidence='engineering_fixture')
    generic = Procedure(id='p-searchqa-1-1', origin='searchqa', description='Imported authored helper',
                        hooks=('applies', 'before_call'), source='def applies(view):\n    return False\n\ndef before_call(view, state):\n    return {}\n',
                        evidence='engineering_fixture', max_note_chars=100, policy_version=policy.POLICY_VERSION_V29)
    combined = Package(package.procedures + (generic,), 'G/s0', 'engineering_fixture')
    request = client._load_request(combined, client._entries(combined), client.CELL_LIMITS.worker(),
                                   mixed_policy_bundle='main-v8-instruction-segments')
    request['seq'] = 1
    assert request['policy_version'] == policy.POLICY_VERSION_V222
    found = worker_v222.handle_load(request, {'loaded': None}, policy)
    assert found['ok'] and found['rejected'] == [] and found['loaded'] == list(combined.order)
    assert worker.handle_load(request, {'loaded': None}, policy)['error'] == 'unknown mixed-policy import bundle'
    assert worker_v215.handle_load(request, {'loaded': None}, policy)['error'] == 'unknown mixed-policy import bundle'
    request['procedures'][-1]['source'] += '\n# ' + 'x' * 25000
    found = worker_v222.handle_load(request, {'loaded': None}, policy)
    assert found['rejected'] == [{'id': generic.id, 'reason': 'policy:size'}]


def test_worker_selection_is_explicit_and_keeps_historical_worker_bytes(tmp_path):
    from skillopt.execskill.sandbox import client
    old = client.Worker(docker=object(), scratch=tmp_path)
    child = client.Worker(docker=object(), scratch=tmp_path, instruction_configuration=p.MAIN_V8,
                          diagnostics_configuration=p.ZEBRA_PC_V15)
    assert old.mixed_policy_bundle is None and child.mixed_policy_bundle == 'main-v8-instruction-segments'
    assert (old._runner_dir() / 'worker.py').read_bytes() == client.WORKER_FILE.read_bytes()
    assert (child._runner_dir() / 'worker.py').read_bytes() == client.INSTRUCTION_WORKER_FILE.read_bytes()
    assert client.worker_sha256(configuration=p.MAIN_V8) == hashlib.sha256(client.INSTRUCTION_WORKER_FILE.read_bytes()).hexdigest()
    assert client.worker_sha256(configuration=p.MAIN_V7) == hashlib.sha256(client.WORKER_FILE.read_bytes()).hexdigest()
    old.close()
    child.close()
    with pytest.raises(ValueError, match='require the main-v8'):
        client.Worker(docker=object(), mixed_policy_bundle='main-v8-instruction-segments')
