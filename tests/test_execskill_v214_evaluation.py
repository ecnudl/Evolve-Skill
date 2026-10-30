"""main-v5 stage reads, sharing and qualification/scan race guards; authored fixtures only."""
import itertools
from contextlib import contextmanager
from pathlib import Path

import pytest

from skillopt.coevo5.calls import Endpoint, Slots
from skillopt.coevo5.protocol import RUNTIME
from skillopt.continual_eval.core import read_json, write_json
from skillopt.execskill import cells, chain, evaluation, instruction_start, package, profiles as p, zebralogic
from tests.execskill_fakes_env import FakeSandbox
from tests.execskill_v293_fakes import tmp_path  # noqa: F401
from tests.test_execskill_chain import Launch, setting as chain_setting
from tests.test_execskill_evaluation import (CARD_PACKAGE, FINAL, ITEMS, Solver, consent_value, panel,
                                            s0_canaries)
from tests.test_execskill_stage_read import STAGES, hooks
from tests.test_execskill_v212_evaluation import final_package
from tests.test_execskill_zpc_pipeline import SourceWorker, fixture_pool, offline, public_grid  # noqa: F401
from skillopt.validator_pilot.api import digest

CONFIG = 'main-v5'
EVIDENCE = 'engineering_fixture'


def consent():
    return consent_value(multi_arm_arms=['F', 'C', 'B', 'stages'], sheet_test_qualification=True,
                         note='Authored main-v5 stage read fixture.')


def test_exact_consent_requires_stage_arms_and_sheet_qualification(tmp_path):
    write_json(tmp_path / 'consent.json', consent())
    assert evaluation.consent(tmp_path, CONFIG) == consent()


@pytest.mark.parametrize('changes', [
    {'multi_arm_arms': ['F', 'C', 'B']}, {'multi_arm_arms': ['F', 'C', 'stages']},
    {'multi_arm_arms': ['F', 'C', 'B', 'stages', 'S1']}, {'sheet_test_qualification': False},
])
def test_invalid_consent_is_refused(tmp_path, changes):
    write_json(tmp_path / 'consent.json', {**consent(), **changes})
    with pytest.raises(ValueError, match='consent'):
        evaluation.consent(tmp_path, CONFIG)


def test_reduced_arms_and_all_stage_sources_share_in_one_offline_unit(tmp_path):
    shared = tmp_path / 'shared'
    write_json(shared / 'consent.json', consent())
    solver = Solver()
    endpoint = Endpoint(solver, model=p.CHAINS['D'], max_tokens=100,
                        slots=Slots(tmp_path / 'slots', 'deepseek', 2), sleep=lambda _: None)
    root = tmp_path / 'D/test/officeqa'
    ticks = itertools.count()
    context = cells.Context(attempt=root / 'attempt-1', endpoint=endpoint, runtime=RUNTIME,
        cards={'officeqa': instruction_start.pins()['officeqa']['text']},
        native=None, episodes=None, worker=lambda _: FakeSandbox(hooks()), evidence=EVIDENCE,
        clock=lambda: float(next(ticks)), configuration=CONFIG)
    @contextmanager
    def workers(found, item):
        worker = FakeSandbox(hooks()).start(found, kind='cell')
        try:
            yield worker
        finally:
            worker.close()
    result = evaluation.evaluate(root, run='authored-v214', shared=shared, pinned=None, chain='D', bench='officeqa',
        arms={'F': cells.Arm('candidate', FINAL), 'C': cells.Arm('card', CARD_PACKAGE),
              'B': cells.Arm('blank', CARD_PACKAGE)}, context=context, workers=2, route_workers=workers,
        canaries=[], panel=panel, stages=STAGES, run_configuration=CONFIG)
    records = [read_json(path) for path in (root / 'attempt-1/cells').glob('*.json')]
    assert result['stages']['rows'] == STAGES['rows']
    assert result['stages']['sources'] == {
        'S1': {'C': 4, 'F': 4, 'sent': 4}, 'S2': {'C': 9, 'sent': 3},
        'S3': {'C': 4, 'F': 4, 'S1': 4}}
    assert result['stages']['fallback'] == 0
    assert set(result['packages']) == {'F', 'C', 'B', 'S1', 'S2', 'S3'}
    assert len(records) == len(ITEMS) * 6 and result['twins'] == 0
    assert solver.calls == sum(row['shared_with'] is None for row in records)
    assert all(row['shared_with'] is None for row in records if row['cell']['arm'] == 'B')
    assert all(row['configuration'] == CONFIG for row in records)
    assert read_json(root / 'attempt-1/canary_scan.json')['vanished'] == 0


def test_zebra_blank_is_the_card_cell_and_sends_no_request(tmp_path):
    import json
    tasks = fixture_pool()[:4]
    tasks[0]['public']['question'] += '\nfixture structural zero'
    final = final_package()
    card = package.empty(step='D/card', evidence=EVIDENCE)
    shared = tmp_path / 'shared'
    write_json(shared / 'consent.json', consent())
    calls = []
    class ZebraSolver:
        def call(self, system, user):
            from skillopt.execskill import zebralogic
            calls.append((system, user))
            return {'ok': True, 'response': json.dumps({'solution': public_grid(zebralogic.parse_user(user))}),
                    'finish_reason': 'stop', 'error_type': None,
                    'usage': {'prompt_tokens': 10, 'completion_tokens': 5, 'total_tokens': 15},
                    'attempts': [{'status': 200}]}
    endpoint = Endpoint(ZebraSolver(), model=p.CHAINS['D'], max_tokens=100,
                        slots=Slots(tmp_path / 'slots', 'deepseek', 1), sleep=lambda _: None)
    root = tmp_path / 'D/test/zebralogic'
    context = cells.Context(attempt=root / 'attempt-1', endpoint=endpoint, runtime={'zebralogic': {}},
        cards={'zebralogic': zebralogic.CARD_TEXT}, native=None, episodes=None,
        worker=lambda _: SourceWorker(), evidence=EVIDENCE, configuration=CONFIG)
    @contextmanager
    def workers(found, item):
        worker = SourceWorker().start(found, kind='cell')
        try:
            yield worker
        finally:
            worker.close()
    def synthetic_panel(pinned, bench, *, access):
        assert bench == 'zebralogic'
        return tasks, {'panel_hash': digest(tasks), 'excluded_without_pages': [], 'source_files': None}
    result = evaluation.evaluate(root, run='authored-v214', shared=shared, pinned=None, chain='D', bench='zebralogic',
        arms={'F': cells.Arm('candidate', final), 'C': cells.Arm('card', card), 'B': cells.Arm('blank', card)},
        context=context, workers=1, route_workers=workers, canaries=[], panel=synthetic_panel,
        stages={'rows': ['C', 'C', 'C', 'F', 'F', 'F'], 'packages': {}}, run_configuration=CONFIG)
    records = [read_json(path) for path in (root / 'attempt-1/cells').glob('*.json')]
    assert len(records) == 12 and len(calls) == 7
    by_id = {row['cell']['id']: row for row in records}
    blanks = [row for row in records if row['cell']['arm'] == 'B']
    assert len(blanks) == 4 and all(row['calls'] == [] and row['card'] == '' for row in blanks)
    assert all(by_id[row['shared_with']]['cell']['arm'] == 'C' for row in blanks)
    assert result['blank_sharing']['cells'] == 4 and result['blank_sharing']['dispatches'] == 0
    assert result['stages']['rows'] == ['C', 'C', 'C', 'F', 'F', 'F']


def test_stage_rows_preserve_every_empty_duplicate_and_import_row(tmp_path):
    root = tmp_path / 'D'
    start = package.empty(step='D/s0', evidence=EVIDENCE)
    final = final_package()
    package.save(root, final)
    order = p.CONFIGURATIONS[CONFIG]['order']
    for k, bench in enumerate(order, 1):
        write_json(root / ('s%d-%s' % (k, bench)) / 'step.json', p.record('step', EVIDENCE,
            {'chain': 'D', 'k': k, 'bench': bench, 'package_sha256': (start if k < 5 else final).sha256}))
    assert evaluation.stage_rows(root, 'D', order, final, start) == {
        'rows': ['C', 'C', 'C', 'C', 'C', 'F'], 'packages': {}}


def test_import_only_chain_still_reads_after_qualification(tmp_path, monkeypatch):
    setting = chain_setting(tmp_path, chain_='D', consent=False)
    setting.extra.update(configuration=CONFIG)
    write_json(setting.shared / 'consent.json', consent())
    events = []
    monkeypatch.setattr(chain, 'first_call', lambda *args, **kwargs: None)
    monkeypatch.setattr(evaluation, 'prepare_test_qualification', lambda *args, **kwargs: events.append('qualified'))
    imported = final_package()
    def learn(setting, root, chain, k, bench, parent):
        return (imported if k == 5 else parent), p.record('step', EVIDENCE, {'k': k})
    launched = Launch(tmp_path)
    def launch(setting, spec):
        assert events[0] == 'qualified'
        events.append(spec['bench'])
        return launched(setting, spec)
    assert chain.run(setting, 'D', learn=learn, launch=launch) == {'status': 'complete'}
    assert set(events[1:]) == set(p.read_benches(CONFIG))
    record = read_json(setting.root / 'D/test-read.json')
    assert record['status'] == 'read' and record['arms'] == ['F', 'C', 'B', 'stages']


def test_qualification_failure_starts_no_test_children(tmp_path, monkeypatch):
    setting = chain_setting(tmp_path, chain_='D', consent=False)
    setting.extra['configuration'] = CONFIG
    def stop(*args, **kwargs):
        raise cells.Pause('qualification_paused', 'authored', 'shared/qualification')
    monkeypatch.setattr(evaluation, 'prepare_test_qualification', stop)
    with pytest.raises(cells.Pause, match='qualification_paused'):
        chain.evaluate(setting, 'D', final_package(), launch=lambda *args: pytest.fail('read started too soon'))


@pytest.mark.parametrize('configuration,vanishes', [(CONFIG, True), ('main-v4', True), (CONFIG, False)])
def test_scan_records_only_vanished_files_and_keeps_existing_unreadable_fatal(tmp_path, monkeypatch,
                                                                           configuration, vanishes):
    path = tmp_path / 'artifact.json'
    path.write_text('{"authored": true}')
    original = evaluation._texts
    def raced(found):
        if found == path:
            if vanishes:
                found.unlink()
                raise FileNotFoundError('authored race')
            raise PermissionError('authored unreadable file')
        yield from original(found)
    monkeypatch.setattr(evaluation, '_texts', raced)
    missing = []
    if configuration == CONFIG and vanishes:
        assert evaluation.canary_scan(tmp_path, [], configuration=configuration, vanished=missing) == (0, [])
        assert missing == [{'path': 'artifact.json'}]
    else:
        with pytest.raises(FileNotFoundError if vanishes else PermissionError):
            evaluation.canary_scan(tmp_path, [], configuration=configuration, vanished=missing)
        assert missing == []


def test_unit_scan_counts_vanished_by_relative_location(tmp_path, monkeypatch):
    unit, shared = tmp_path / 'unit', tmp_path / 'shared'
    path = shared / 'test/scorer-artifact.json'
    path.parent.mkdir(parents=True)
    path.write_text('{}')
    def raced(found):
        found.unlink()
        raise FileNotFoundError('authored race')
        yield
    monkeypatch.setattr(evaluation, '_texts', raced)
    scan = evaluation._scanned(unit, shared, [], configuration=CONFIG)
    assert scan == {'artifacts_scanned': 0, 'hits': [], 'vanished': 1,
                    'vanished_paths': [{'where': 'shared_test', 'path': 'scorer-artifact.json'}]}


def test_root_scan_records_vanished_file(tmp_path, monkeypatch):
    path = tmp_path / 'artifact.json'
    path.write_text('{}')
    def raced(found, windows):
        found.unlink()
        raise FileNotFoundError('authored race')
    monkeypatch.setattr(evaluation, '_found', raced)
    missing = []
    assert evaluation.root_scan(tmp_path, [], configuration=CONFIG, vanished=missing) == (0, [])
    assert missing == [{'path': 'artifact.json'}]


@pytest.mark.parametrize('default_dispatch', [False, True])
def test_read_canaries_use_zebra_and_never_livemath(tmp_path, monkeypatch, default_dispatch):
    root = tmp_path / 'root'
    write_json(root / 'shared/consent.json', consent())
    s0_canaries(root)
    sources = evaluation.read_canary_sources(CONFIG)
    assert sources == {'officeqa': 'question', 'zebralogic': 'question', 'spreadsheetbench': 'instruction'}
    pools = {}
    for bench in p.CONFIGURATIONS[CONFIG]['order']:
        path = tmp_path / 'pools' / (bench + '.json')
        field = sources.get(bench, 'question')
        items = [{'task_id': bench + '-practice', 'public': {field: 'Authored practice only for ' + bench}, 'private': {}}]
        if bench == 'zebralogic':
            from tests.test_execskill_zpc_adapter import pool_rows
            items = pool_rows()
        write_json(path, items)
        import hashlib
        pools[bench] = {'path': str(path), 'sha256': hashlib.sha256(path.read_bytes()).hexdigest()}
    seen = []
    def synthetic_panel(pinned, bench, *, access):
        seen.append(bench)
        assert bench in sources
        tasks = [{'task_id': bench + '-authored-' + str(i),
                  'public': {sources[bench]: 'Authored canary panel for %s item %d with enough characters.' % (bench, i)},
                  'private': {}} for i in range(6)]
        return tasks, {'panel_hash': digest(tasks)}
    pinned = {'zebralogic': {'path': 'authored-not-opened', 'sha256': 'b' * 64}}
    chosen = synthetic_panel
    if default_dispatch:
        def other_panel(found, bench, *, access):
            assert bench != 'zebralogic' and found == pinned
            return synthetic_panel(found, bench, access=access)
        def zebra_panel(found, bench, *, access):
            assert bench == 'zebralogic' and found == pinned['zebralogic']
            return synthetic_panel(found, bench, access=access)
        monkeypatch.setattr(evaluation.data, 'test_panel', other_panel)
        monkeypatch.setattr(zebralogic, 'test_panel', zebra_panel)
        chosen = other_panel
    result = evaluation.make_read_canaries(root, pinned, pools=pools, run='authored', evidence=EVIDENCE,
        panel=chosen, order=p.CONFIGURATIONS[CONFIG]['order'], configuration=CONFIG)
    assert set(seen) == set(sources) and set(result['counts']) == set(sources)
    assert len(evaluation.load_canaries(root, read=True, configuration=CONFIG)) == 25


def test_mixed_zebra_test_dispatch_passes_only_its_child_pin(tmp_path, monkeypatch):
    write_json(tmp_path / 'consent.json', consent())
    child = {'path': 'authored-path-not-opened', 'sha256': 'a' * 64}
    mixed = {'zebralogic': child, 'officeqa': {'authored': True}}
    seen = []
    def fake_zebra_panel(pinned, bench, *, access):
        seen.append((pinned, bench, access.unit))
        assert pinned == child
        tasks = fixture_pool()[:2]
        return tasks, {'panel_hash': digest(tasks), 'excluded_without_pages': [], 'source_files': None}
    monkeypatch.setattr(zebralogic, 'test_panel', fake_zebra_panel)
    tasks = evaluation.test_tasks(tmp_path, mixed, 'zebralogic', 'D/test/zebralogic', run='authored',
        runtime={}, native=None, workers=1, evidence=EVIDENCE, configuration=CONFIG)
    assert len(tasks) == 2 and seen == [(child, 'zebralogic', 'D/test/zebralogic')]


def test_main_v5_unseal_refuses_absent_other_chain_before_reading_any_score(tmp_path):
    write_json(tmp_path / 'D/chain-complete.json', {})
    with pytest.raises(ValueError, match='both chains'):
        evaluation.unseal(tmp_path, tmp_path / 'D', 'D', [], run='authored', evidence=EVIDENCE,
                          configuration=CONFIG)


def test_direct_unit_qualifies_after_first_response_and_before_any_attempt(tmp_path, monkeypatch):
    setting = chain_setting(tmp_path, chain_='D', consent=False)
    setting.extra['configuration'] = CONFIG
    write_json(setting.shared / 'consent.json', consent())
    events = []
    monkeypatch.setattr(evaluation, 'setting_of', lambda *a, **kw: setting)
    monkeypatch.setattr(chain, 'confirmation', lambda *a, **kw: events.append('first-response-confirmed'))
    def qualification(*args, **kwargs):
        events.append('qualification')
        raise cells.Pause('qualification_paused', 'authored', 'shared/qualification')
    monkeypatch.setattr(evaluation, 'prepare_test_qualification', qualification)
    root = setting.root / 'D/test/officeqa'
    spec = tmp_path / 'spec.json'
    write_json(spec, {'chain': 'D', 'bench': 'officeqa', 'package_sha256': FINAL.sha256, 'unit_root': str(root)})
    assert evaluation.run_unit_spec({'data': {'pinned': {}}}, spec=spec) == chain.EXIT_PAUSED
    assert events == ['first-response-confirmed', 'qualification']
    assert not root.exists()
