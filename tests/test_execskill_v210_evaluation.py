"""v2.10 exact read arms, instruction/blank prompts and no-sandbox baseline; offline fixtures."""
import itertools
from types import SimpleNamespace

import pytest

from skillopt.coevo5.calls import Endpoint, Slots
from skillopt.coevo5.protocol import RUNTIME
from skillopt.continual_eval.core import read_json, write_json
from skillopt.execskill import cells, evaluation, instruction_start, profiles, readout, solver
from skillopt.execskill.package import empty
from tests.execskill_fakes_env import FakeSandbox
from tests.execskill_v293_fakes import tmp_path  # noqa: F401
from tests.test_execskill_acceptance import fast_statistics  # noqa: F401
from tests.test_execskill_evaluation import (CARD, CARD_PACKAGE, FINAL, HOOKS, ITEMS, ZERO, Solver,
                                            consent_value, panel, route_workers)
from tests.test_execskill_readout import cell


@pytest.mark.parametrize('configuration,arms', [('main-v3', ('F', 'C', 'B')), ('baseline-v210', ('C', 'B'))])
def test_consent_names_exactly_the_registered_read_arms(configuration, arms, tmp_path):
    assert profiles.read_arms_of(configuration) == arms
    write_json(tmp_path / 'consent.json', consent_value(multi_arm_arms=list(arms)))
    assert evaluation.consent(tmp_path, configuration)['multi_arm_arms'] == list(arms)
    for n, bad in enumerate([list(arms) + ['twins'], list(arms) + ['P_F'], list(arms)[:-1], list(arms) + [arms[0]]]):
        directory = tmp_path / str(n)
        write_json(directory / 'consent.json', consent_value(multi_arm_arms=bad))
        with pytest.raises(ValueError, match='consent'):
            evaluation.consent(directory, configuration)


@pytest.mark.parametrize('bench', profiles.BENCHES)
@pytest.mark.parametrize('kind', ['candidate', 'parent', 'card', 'dup', 'blank'])
def test_each_arm_system_contains_instruction_once_except_blank(bench, kind):
    instruction = instruction_start.pins()[bench]['text']
    cards = instruction_start.active_cards({bench: instruction}, profiles.MAIN_V3)
    seen = []
    def capture(found_bench, public, card, package, call, **kwargs):
        seen.append((card, solver._system(found_bench, card, kwargs['runtime'])))
    context = SimpleNamespace(cards=cards, configuration=profiles.MAIN_V3, runtime={bench: RUNTIME[bench]},
                              solve=capture, worker=lambda _: None, native=None, nominal={})
    cells._shell(context, {'benchmark': bench}, {'public': {}},
                 cells.Arm(kind, empty(step='D/s0', evidence='engineering_fixture')), None)
    card, system = seen[0]
    assert card == ('' if kind == 'blank' else instruction)
    assert system.count(instruction) == (0 if kind == 'blank' else 1)
    assert system == solver._system(bench, card, RUNTIME[bench])
    if kind == 'blank':
        assert solver.GUIDANCE not in system
        contract = ("\nReturn the concise final answer inside <answer>...</answer>."
                    if bench in ('searchqa', 'officeqa') else solver.LIVEMATH_CONTRACT
                    if bench == 'livemath' else solver.SHEET_CONTRACT_V2
                    if bench == 'spreadsheetbench' and RUNTIME[bench].get('prompt_layout') == solver.CONTRACT_FIRST_LAYOUT_V2
                    else "\nReturn one complete Python program in a ```python code block.")
        assert system == solver.QA_SYSTEM + contract


def test_card_and_empty_parent_have_identical_instruction_system_and_baseline_needs_no_worker():
    bench = 'alfworld'
    def forbidden(*args, **kwargs):
        pytest.fail('The procedure-free baseline must not create a Docker worker')
    cards = instruction_start.active_cards({bench: instruction_start.pins()[bench]['text']}, profiles.BASELINE_V210)
    seen = []
    context = SimpleNamespace(cards=cards, configuration=profiles.BASELINE_V210, runtime={bench: RUNTIME[bench]},
        solve=lambda b, public, card, package, call, **kw: seen.append((solver._system(b, card, kw['runtime']), kw['worker'])),
        worker=forbidden, native=None, nominal={})
    for kind in ('card', 'parent'):
        cells._shell(context, {'benchmark': bench}, {'public': {}}, cells.Arm(kind, CARD_PACKAGE), None)
    assert seen[0] == seen[1] and seen[0][1] is None


@pytest.mark.parametrize('configuration', ['main-v3', 'baseline-v210'])
def test_actual_read_dispatches_only_new_arms_and_keeps_b_independent(configuration, tmp_path):
    shared = tmp_path / 'shared'
    write_json(shared / 'consent.json', consent_value(multi_arm_arms=list(profiles.read_arms_of(configuration))))
    model = Solver()
    requests = []
    original = model.call
    def traced(system, user):
        requests.append(system)
        return original(system, user)
    model.call = traced
    endpoint = Endpoint(model, model='deepseek-v4.1-flash-1017', max_tokens=100,
                        slots=Slots(tmp_path / 'slots', 'deepseek', 2), sleep=lambda _: None)
    unit_root = tmp_path / 'D/test/officeqa'
    ticks = itertools.count()
    context = cells.Context(attempt=unit_root / 'attempt-1', endpoint=endpoint, runtime=RUNTIME,
        cards={b: instruction_start.pins()[b]['text'] for b in profiles.BENCHES},
        native=Slots(tmp_path / 'slots', 'spreadsheet-native', 1),
        episodes=Slots(tmp_path / 'slots', 'alfworld-episode', 1),
        worker=lambda bench: FakeSandbox(HOOKS), evidence='engineering_fixture',
        clock=lambda: float(next(ticks)), configuration=configuration)
    arms = {'C': cells.Arm('card', CARD_PACKAGE), 'B': cells.Arm('blank', CARD_PACKAGE)}
    if configuration == profiles.MAIN_V3:
        arms = {'F': cells.Arm('candidate', FINAL), **arms}
    def forbidden(*args, **kwargs):
        pytest.fail('Baseline routing must not create a sandbox')
    found = evaluation.evaluate(unit_root, run='authored-v210', shared=shared, pinned=None, chain='D',
        bench='officeqa', arms=arms, context=context, workers=2,
        route_workers=forbidden if configuration == profiles.BASELINE_V210 else route_workers,
        canaries=[], panel=panel, run_configuration=configuration)
    records = [read_json(path) for path in (unit_root / 'attempt-1/cells').glob('*.json')]
    assert {row['cell']['arm'] for row in records} == set(profiles.read_arms_of(configuration))
    assert len(records) == len(ITEMS) * len(arms) and found['twins'] == 0
    assert all(row['shared_with'] is None for row in records if row['cell']['arm'] == 'B')
    assert all(row['card'] == '' and row['arm_kind'] == 'blank' for row in records if row['cell']['arm'] == 'B')
    assert found['instruction_start'] == instruction_start.START
    assert found['blank_arm'] == instruction_start.blank_definition()
    shared_f = [row for row in records if row['shared_with'] is not None]
    assert len(shared_f) == (len(ZERO) if configuration == profiles.MAIN_V3 else 0)
    assert all(row['cell']['arm'] == 'F' for row in shared_f)
    assert model.calls == len(records) - len(shared_f)
    instruction = instruction_start.pins()['officeqa']['text']
    assert sum(instruction not in text for text in requests) == len(ITEMS)
    assert all(text.count(instruction) <= 1 for text in requests)
    assert all(text == solver._system('officeqa', '', RUNTIME['officeqa'])
               for text in requests if instruction not in text)
    assert not (unit_root / 'attempt-1/transient').exists()


@pytest.mark.parametrize('configuration', ['main-v3', 'baseline-v210'])
def test_readout_reports_only_available_contrasts(configuration, fast_statistics):
    data = {(arm, 'item-%d' % i, 0): cell('pass' if arm in ('F', 'C') else 'fail')
            for arm in profiles.read_arms_of(configuration) for i in range(12)}
    found = readout.readout({'officeqa': data}, learned=[], procedures={}, label='engineering',
                           evidence='engineering_fixture', configuration=configuration)
    assert set(found['arms']['officeqa']) == set(profiles.read_arms_of(configuration))
    expected = {'C-B'} if configuration == profiles.BASELINE_V210 else {'F-C', 'C-B', 'F-B'}
    assert set(found['contrasts']['officeqa']) == expected
    assert found['contrasts']['officeqa']['C-B']['mean'] == 1
    assert found['placebo'] == found['code_vs_text'] == found['twins'] == {'removed': True}


def test_baseline_alfworld_actual_solver_uses_instruction_or_blank_without_sandbox(tmp_path, monkeypatch):
    from tests.execskill_fakes_env import Script, alf_sessions
    from tests.fixtures.execskill.items import alfworld_items
    sessions = alf_sessions(monkeypatch)
    game = alfworld_items(tmp_path / 'games')[0]
    def forbidden(*args, **kwargs):
        pytest.fail('The baseline ALFWorld shell must not instantiate a Docker sandbox')
    context = cells.Context(attempt=tmp_path / 'attempt-1', endpoint=None,
        runtime={'alfworld': {**RUNTIME['alfworld'], 'max_steps': 1}},
        cards={'alfworld': instruction_start.pins()['alfworld']['text']},
        native=None, episodes=None, worker=forbidden, evidence='engineering_fixture',
        configuration=profiles.BASELINE_V210)
    requests = []
    for kind in ('card', 'blank'):
        script = Script(['look'])
        prediction = cells._shell(context, {'benchmark': 'alfworld'}, game,
                                  cells.Arm(kind, CARD_PACKAGE), script)
        assert prediction['shell']['sandbox'] is None
        requests.extend(script.requests)
    instruction = instruction_start.pins()['alfworld']['text']
    assert [system.count(instruction) for system, _ in requests] == [1, 0]
    assert solver.GUIDANCE not in requests[1][0]
    assert all(system.startswith(solver.ALF_SYSTEM) for system, _ in requests)
    assert len(sessions) == 2 and all(session.closed for session in sessions)


@pytest.mark.parametrize('learned', [('searchqa',), tuple(profiles.BENCHES[:-1])])
def test_main_keeps_inherited_f_c_inference_without_treating_import_as_learning(learned, fast_statistics):
    data = {bench: {(arm, 'item-%d' % i, 0): cell(
        'pass' if arm == 'F' or i % 3 else 'fail', enabled=('authored-procedure',) if arm == 'F' else (),
        room='room-%d' % (i // 3) if bench == 'alfworld' else None)
        for arm in profiles.read_arms_of(profiles.MAIN_V3) for i in range(12)} for bench in profiles.BENCHES}
    procedures = {'authored-procedure': 'searchqa', 'imported-procedure': 'alfworld'}
    found = readout.readout(data, learned=learned, procedures=procedures, label='engineering',
                           evidence='engineering_fixture', configuration=profiles.MAIN_V3)
    exposed = list(learned) + ['alfworld']
    assert found['learned'] == list(learned) and found['imported'] == ['alfworld']
    assert found['q1_home'] == readout.q1_home(data, learned)
    assert set(found['q1_home']) == set(learned) and 'alfworld' not in found['q1_home']
    assert found['q2_similar'] == readout.q2_similar(data, exposed, procedures)
    assert found['similar'] == readout.similar(exposed)
    assert found['dissimilar'] == readout.dissimilar(exposed)
    if found['dissimilar']:
        assert found['q3_noninferiority'] == readout.q3_noninferiority(data, exposed)
        assert 'alfworld' not in found['q3_noninferiority']['benches']
    else:
        assert found['q3_noninferiority'] is None
    assert set(found['contrasts']['alfworld']) == {'F-C', 'C-B', 'F-B'}
