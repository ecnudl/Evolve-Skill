"""v2.12 F/C-only consent, dispatch, chain-end gate and reporting; authored fixtures only."""
import itertools
import json
from contextlib import contextmanager

import pytest

from skillopt.coevo5.calls import Endpoint, Slots
from skillopt.continual_eval.core import read_json, write_json
from skillopt.execskill import cells, chain, evaluation, package, profiles as p, readout, solver, units, zebralogic as z
from skillopt.validator_pilot.api import digest
from tests.execskill_v293_fakes import tmp_path  # noqa: F401
from tests.test_execskill_acceptance import fast_statistics  # noqa: F401
from tests.test_execskill_chain import Launch, Learn, setting as chain_setting
from tests.test_execskill_evaluation import consent_value
from tests.test_execskill_readout import cell
from tests.test_execskill_zpc_pipeline import SourceWorker, fixture_pool, offline, public_grid  # noqa: F401

CONFIG = p.ZEBRA_PC_V13
EVIDENCE = 'engineering_fixture'
SOURCE = '''def applies(view):
    return "fixture structural zero" not in view["question"]
def before_call(view, state):
    return {"facts": ["Use the public clues."]}
'''


def final_package():
    proc = package.Procedure('fx-zebra-v212', z.BENCH, 'Use public clues.', ('applies', 'before_call'),
                             SOURCE, EVIDENCE, max_note_chars=200)
    return package.Package((proc,), step='D/s1-zebralogic', evidence=EVIDENCE)


def consent():
    return consent_value(multi_arm_arms=['F', 'C'], date='2026-10-30',
                         note='Delegated owner consent: one accepted Zebra package chain-end read.')


def test_exact_owner_consent_and_legacy_implicit_consent_stays_frozen(tmp_path):
    write_json(tmp_path / 'consent.json', consent())
    assert evaluation.consent(tmp_path, CONFIG) == consent()
    assert set(consent()) == p.CONSENT_FIELDS
    with pytest.raises(ValueError, match='consent'):
        evaluation.consent(tmp_path)


@pytest.mark.parametrize('changes', [
    {'multi_arm_arms': ['F', 'C', 'B']}, {'multi_arm_arms': ['F', 'C', 'P_F']},
    {'multi_arm_arms': ['F', 'C', 'T_F']}, {'multi_arm_arms': ['F', 'C', 'withholding']},
    {'multi_arm_arms': ['F', 'C', 'C']}, {'multi_arm_arms': ['C']},
    {'test_evaluation': False}, {'sheet_test_qualification': True}, {'by': 'agent'}, {'note': ''},
])
def test_v13_rejects_any_other_consent(tmp_path, changes):
    write_json(tmp_path / 'consent.json', {**consent(), **changes})
    with pytest.raises(ValueError, match='consent'):
        evaluation.consent(tmp_path, CONFIG)


def test_real_evaluation_dispatches_only_f_c_and_no_test_twins(tmp_path):
    tasks = fixture_pool()[:4]
    tasks[0]['public']['question'] += '\nfixture structural zero'
    final = final_package()
    card = package.empty(step='D/card', evidence=EVIDENCE)
    shared = tmp_path / 'shared'
    write_json(shared / 'consent.json', consent())
    calls = []
    class Solver:
        def call(self, system, user):
            calls.append((system, user))
            return {'ok': True, 'response': json.dumps({'solution': public_grid(z.parse_user(user))}),
                    'finish_reason': 'stop', 'error_type': None,
                    'usage': {'prompt_tokens': 10, 'completion_tokens': 5, 'total_tokens': 15},
                    'attempts': [{'status': 200}]}
    endpoint = Endpoint(Solver(), model='deepseek-v4-flash', max_tokens=100,
                        slots=Slots(tmp_path / 'slots', 'deepseek', 1), sleep=lambda _: None)
    unit_root = tmp_path / 'D/test/zebralogic'
    ticks = itertools.count()
    context = cells.Context(attempt=unit_root / 'attempt-1', endpoint=endpoint, runtime={z.BENCH: {}},
        cards={z.BENCH: z.CARD_TEXT}, native=None, episodes=None, worker=lambda _: SourceWorker(),
        evidence=EVIDENCE, clock=lambda: float(next(ticks)), configuration=CONFIG)
    @contextmanager
    def workers(found, item):
        worker = SourceWorker().start(found, kind='cell')
        try:
            yield worker
        finally:
            worker.close()
    def panel(pinned, bench, *, access):
        assert bench == z.BENCH
        return tasks, {'panel_hash': digest(tasks), 'excluded_without_pages': [], 'source_files': None}
    result = evaluation.evaluate(unit_root, run='authored-v212', shared=shared, pinned=None, chain='D',
        bench=z.BENCH, arms={'F': cells.Arm('candidate', final), 'C': cells.Arm('card', card)},
        context=context, workers=1, route_workers=workers, canaries=[], panel=panel, run_configuration=CONFIG)
    records = [read_json(path) for path in (unit_root / 'attempt-1/cells').glob('*.json')]
    assert result['counts']['by_arm'] == {'C': 4, 'F': 4}
    assert result['twins'] == 0 and result['structural_zero'] == 1
    assert len(records) == 8 and len(calls) == 7
    assert {row['cell']['arm'] for row in records} == {'F', 'C'}
    assert {row['arm_kind'] for row in records} == {'candidate', 'card'}
    assert all(row['configuration'] == CONFIG for row in records)
    # The registered card stays mandatory; the inherited Zebra shell places the official format in USER only.
    assert context.cards[z.BENCH] == z.CARD_TEXT
    assert all(system == solver.QA_SYSTEM for system, _ in calls)
    assert [row['cell']['arm'] for row in records if row['shared_with'] is not None] == ['F']
    assert 'blank_arm' not in result and 'instruction_start' not in result
    assert not (unit_root / 'attempt-1/transient').exists()
    with pytest.raises(ValueError, match='complete'):
        evaluation.evaluate(unit_root, run='authored-v212', shared=shared, pinned=None, chain='D',
            bench=z.BENCH, arms={'F': cells.Arm('candidate', final), 'C': cells.Arm('card', card)},
            context=context, workers=1, route_workers=workers, canaries=[], panel=panel, run_configuration=CONFIG)
    assert len(calls) == 7


@pytest.mark.parametrize('accepted', [False, True])
def test_chain_end_reads_once_only_when_a_package_was_accepted(tmp_path, monkeypatch, accepted):
    setting = chain_setting(tmp_path, chain_='D', consent=False)
    setting.extra.update(configuration=CONFIG, test_read_terms={'D': {z.BENCH: '1000'}})
    if accepted:
        write_json(setting.shared / 'consent.json', consent())
    monkeypatch.setattr(chain, 'first_call', lambda *args, **kwargs: None)
    learn, launch = Learn(accept=accepted), Launch(tmp_path)
    assert chain.run(setting, 'D', learn=learn, launch=launch) == {'status': 'complete'}
    assert [(k, bench) for _, k, bench, _ in learn.calls] == [(1, z.BENCH)]
    assert [spec['bench'] for spec in launch.specs] == ([z.BENCH] if accepted else [])
    result = p.verified(read_json(setting.root / 'D' / chain.TEST_READ), 'test-read')
    assert result['status'] == ('read' if accepted else 'not_read')
    assert result['arms'] == ['F', 'C']
    assert chain.run(setting, 'D', learn=learn, launch=launch) == {'status': 'complete'}
    assert len(learn.calls) == 1 and len(launch.specs) == int(accepted)


def test_unit_entry_constructs_f_c_without_loading_donors(tmp_path, monkeypatch):
    setting = chain_setting(tmp_path, chain_='D', consent=False)
    setting.extra['configuration'] = CONFIG
    setting.runtime = {z.BENCH: {}}
    setting.sandbox = {'cleanup_events': [], 'start_events': []}
    write_json(setting.shared / 'consent.json', consent())
    final = final_package()
    package.save(setting.root / 'D', final)
    unit_root = setting.root / 'D/test/zebralogic'
    spec = tmp_path / 'spec.json'
    write_json(spec, {'chain': 'D', 'bench': z.BENCH, 'package_sha256': final.sha256, 'unit_root': str(unit_root)})
    captured = []
    def forbidden(*args, **kwargs):
        pytest.fail('v13 must not load donor corpora or create placebo/text arms')
    monkeypatch.setattr(evaluation, 'setting_of', lambda *a, **kw: setting)
    monkeypatch.setattr(units, 'for_unit', lambda *a, **kw: setting)
    monkeypatch.setattr(evaluation.budgets, 'endpoint', lambda *a, **kw: None)
    monkeypatch.setattr(units, 'cell_context', lambda *a, **kw: None)
    monkeypatch.setattr(units, 'drainer', lambda *a, **kw: None)
    monkeypatch.setattr(evaluation, 'make_read_canaries', lambda *a, **kw: None)
    monkeypatch.setattr(evaluation, 'load_canaries', lambda *a, **kw: [])
    for name in ('donor_corpora', 'placebo_arm', 'frozen_texts'):
        monkeypatch.setattr(evaluation, name, forbidden)
    monkeypatch.setattr(evaluation, 'evaluate', lambda *a, **kw: captured.append(kw))
    assert evaluation.run_unit_spec({'data': {}}, spec=spec, panel=forbidden) == chain.EXIT_COMPLETE
    assert set(captured[0]['arms']) == {'F', 'C'}
    assert captured[0]['run_configuration'] == CONFIG and captured[0]['stages'] is None


def test_readout_reports_only_f_c_without_imported_or_placebo_claims(fast_statistics):
    data = {(arm, 'authored-%d' % i, 0): cell('pass' if arm == 'F' else 'fail')
            for arm in ('F', 'C') for i in range(12)}
    result = readout.readout({z.BENCH: data}, learned=[z.BENCH], procedures={}, label='engineering',
                            evidence=EVIDENCE, configuration=CONFIG)
    assert result['configuration'] == CONFIG and result['evidence_kind'] == 'pipeline_control'
    assert result['imported'] == [] and result['learned'] == [z.BENCH]
    assert set(result['contrasts'][z.BENCH]) == {'F-C'}
    assert result['contrasts'][z.BENCH]['F-C']['mean'] == 1
    assert result['q1_home'][z.BENCH]['n'] == 12
    assert result['q2_similar'] == {} and result['q3_noninferiority'] is None
    assert result['placebo'] == result['code_vs_text'] == result['twins'] == {'removed': True}


def test_report_forwards_configuration_to_the_reduced_readout(tmp_path, monkeypatch, fast_statistics):
    root = tmp_path / 'root'
    final = final_package()
    package.save(root / 'D', final)
    write_json(root / 'D/test-read.json', p.record('test-read', EVIDENCE,
        {'status': 'read', 'package_sha256': final.sha256}))
    data = {(arm, 'authored-%d' % i, 0): cell('pass' if arm == 'F' else 'fail')
            for arm in ('F', 'C') for i in range(4)}
    def unseal(*args, **kwargs):
        assert kwargs['configuration'] == CONFIG
        return {'units': {z.BENCH: data}, 'label': 'engineering'}
    monkeypatch.setattr(evaluation, 'unseal', unseal)
    out = tmp_path / 'readout'
    result = readout.report({'root': str(root), p.RECORD_HASH: 'authored-v212', 'evidence': EVIDENCE,
                            'configuration': CONFIG, 'data': {'launchable_chains': ['D']}}, out=out)
    value = p.verified(read_json(out / 'readout-D.json'), 'readout')
    assert result == {'D': value[p.RECORD_HASH]}
    assert value['configuration'] == CONFIG
    assert set(value['contrasts'][z.BENCH]) == {'F-C'}
    assert set(value['arms'][z.BENCH]) == {'F', 'C'}
    assert value['learned'] == [z.BENCH]


def test_sealed_cells_preserve_inherited_route_keyword_and_model_metadata(tmp_path):
    from tests.test_execskill_v295_profile import (
        test_sealed_cell_preserves_inherited_configuration_route_and_keyword_metadata)
    test_sealed_cell_preserves_inherited_configuration_route_and_keyword_metadata(tmp_path, CONFIG)
