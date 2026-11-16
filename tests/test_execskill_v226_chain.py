"""Authored full controller chain: real learn, sandbox hooks, identities and fresh reads.

Only supply/examiner authoring, model transport, native execution, and machine
resources are replaced. No production request identity or decision is mocked.
ALFWorld retains the registered import-only fifth step.
"""
from contextlib import contextmanager, nullcontext
from copy import deepcopy
from functools import partial
import base64
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from skillopt.coevo5.calls import Endpoint, Slots
from skillopt.coevo5.protocol import RUNTIME
from skillopt.continual_eval import backends
from skillopt.continual_eval.core import read_json, write_json
from skillopt.execskill import (budgets, chain, cells, engineer_v211, evaluation, package,
    profiles as p, rounds, slots, solver, step, units, v210_import, v218_lock,
    v222_cards, v222_gate, v222_runtime, v225_read as read, v226_candidates)
from skillopt.execskill.registry import Registry
from skillopt.validator_pilot.api import digest
from tests.execskill_fakes import engineer_reply
from tests.execskill_fakes_env import FakeNative, alf_sessions, receipt
from tests.execskill_v226_fakes import DiagnosticsWorker
from tests.execskill_v293_fakes import tmp_path  # noqa: F401
from tests.test_execskill_v225_anchor_environment import Pool, task_for
from tests.test_execskill_v29_audit import Judge

SOURCE = '''def applies(view):
    return "columns" in view or "workbook_preview" in view

def before_call(view, state):
    if "columns" in view:
        return {"facts": ["Compare the supplied constraints carefully."], "diagnostics": {"authored": "x" * 2048}}
    return {"facts": ["Compare the supplied constraints carefully."]}
'''


class Worker(DiagnosticsWorker):
    def __init__(self, *, errors=(), opened=None, **kw):
        super().__init__(**kw)
        self.errors, self.rejected = errors, {}
        self.tag, self.docker = kw.get('tag'), None
        if opened is not None:
            opened.append(self)

    def ping(self):
        return {'ok': True}

    def call(self, proc_id, fn, args, **kw):
        proc = next(row for row in self.package.procedures if row.id == proc_id)
        # Authored host-side hook evaluation defect, outside the worker protocol.
        # A Python exception inside the procedure itself remains a sandbox fault.
        if fn == 'before_call' and 'columns' in args[0] and any(marker in proc.source for marker in self.errors):
            raise ValueError('authored candidate-local host defect; private item excluded')
        return super().call(proc_id, fn, args, **kw)


class Roles:
    def __init__(self, st, scenario, seen):
        self.st, self.scenario, self.seen, self.calls = st, scenario, seen, []

    def count(self, prefix):
        return sum(call['label'].startswith(prefix) for call in self.calls)

    def plain(self, role, system, user, *, label, **options):
        self.calls.append({'role': role, 'label': label, 'request_sha256': digest([system, user]),
                           'valid': True, 'reason': None})
        payload = json.loads(user)
        self.seen.append((self.st.bench, label, payload))
        if role == 'describer':
            return 'Compare the supplied constraints carefully.'
        if payload.get('request') == 'analyse':
            return engineer_reply({'findings': []}, [])
        if 'card' in label:
            return '{}'
        number = int(label.split('engineer-r', 1)[1].split('/')[0]) if 'engineer-r' in label else 0
        proposal_rounds = (1, 2) if self.scenario in ('isolated', 'systematic') else (1,)
        if self.st.bench not in ('zebralogic', 'spreadsheetbench') or number not in proposal_rounds:
            return engineer_reply({'changes': []}, [])
        if self.st.bench == 'zebralogic' and number != 1:
            return engineer_reply({'changes': []}, [])
        source = SOURCE
        if self.st.bench == 'spreadsheetbench' and number == 1 and self.scenario != 'normal':
            source += '\n# authored_host_defect_one\n'
        if self.st.bench == 'spreadsheetbench' and number == 2 and self.scenario == 'systematic':
            source += '\n# authored_host_defect_two\n'
        excluded = [bench for bench in p.SUPPORTED_BENCHES
                    if bench not in (('zebralogic',) if self.st.bench == 'zebralogic'
                                     else ('zebralogic', 'spreadsheetbench'))]
        entry = {'kind': 'new', 'description': 'Compare constraints in the supplied public input.',
            'hooks': ['applies', 'before_call'], 'max_note_chars': 4000,
            'excluded_benches': excluded, 'replay_tests': []}
        return engineer_reply({'changes': [entry]}, [source])


def authored_chain(root, monkeypatch, scenario):
    runtime = deepcopy(RUNTIME)
    runtime['zebralogic'] = {}
    runtime['spreadsheetbench'].update(spreadsheet_scorer='qualified_lo_recalc_v7_v1', recalculation={})
    templates = {bench: task_for(root, bench) for bench in p.MAIN_V5_ORDER}
    pools, cuts, harms = {}, {}, {}
    for bench, template in templates.items():
        pool = [{**deepcopy(template), 'task_id': bench + '-authored-%03d' % n,
                 'partition': 'practice'} for n in range(450)]
        if bench == 'alfworld':
            game = read_json(Path(template['public']['game_file']))
            view = {'initial_observation': game['initial_observation'], 'admissible_commands_at_reset': game['admissible_commands']}
            for item in pool:
                item['public'].update(routing_view=view, routing_view_sha256=digest(view))
        pools[bench] = pool
        cuts[bench] = {'run': pool[:6], 'confirm': pool[6:46], 'accept': pool[300:340]}
        cuts[bench].update({'confirm-r%d' % n: pool[6 + 40 * (n-1):6 + 40 * (n-1) + p.confirm_spec(p.MAIN_V10, bench, n)['items']] for n in range(1, 7)} if bench != 'alfworld' else {})
        harms[bench] = pool[380:398]
    registrations = v222_gate.registration(harms, configuration=p.MAIN_V10)
    monkeypatch.setattr(v222_runtime, 'preflight', lambda _: (harms, registrations))
    monkeypatch.setattr(v218_lock, 'environment', lambda *a, **kw: nullcontext())
    monkeypatch.setattr(step._Step, 'verify', lambda _: None)
    monkeypatch.setattr(chain, '_verified', lambda *a: None)
    monkeypatch.setattr(chain, 'first_call', lambda *a, **kw: None)
    monkeypatch.setattr(chain, 'read_consent', lambda *a: None)
    monkeypatch.setattr(chain, 'complete_deferred_termination', lambda *a: False)
    monkeypatch.setattr(read, 'read_budget', lambda *a: {'authored': True})
    monkeypatch.setattr(budgets, 'own_ledger', lambda *a: SimpleNamespace(declare=lambda _: None))
    monkeypatch.setattr(step, 'cost_projection', lambda *a, **kw: {})
    monkeypatch.setattr(step, 'cap_check', lambda *a, **kw: None)
    opened, seen, requests = [], [], []
    errors = ('authored_host_defect_one', 'authored_host_defect_two')
    def worker(**options):
        return Worker(errors=errors, opened=opened, **options)
    monkeypatch.setattr(units, 'Worker', worker)
    @contextmanager
    def workers(pkg, **options):
        made = worker(**options).start(pkg)
        try:
            yield made
        finally:
            made.close()
    native = FakeNative().install(monkeypatch)
    alf_sessions(monkeypatch)
    def native_output(request, rt):
        return {**native.native(request, rt), 'output_base64': base64.b64encode(
            Path(templates['spreadsheetbench']['private']['test_files'][0]).read_bytes()).decode()}
    monkeypatch.setattr(backends, '_native', native_output)
    original_score = backends.score
    def score(bench, public, private, prediction, *, runtime=None):
        if bench != 'spreadsheetbench':
            return original_score(bench, public, private, prediction, runtime=runtime)
        good = 'AUTHORED_WRONG' not in str(prediction)
        return {'status': 'pass' if good else 'fail', 'reason': 'authored_workbook_values',
                'cleanup_confirmed': True, 'metrics': {'cases': [{'status': 'pass' if good else 'fail'}]}}
    monkeypatch.setattr(backends, 'score', score)
    def answer(bench, system, user):
        requests.append((bench, system, user))
        if bench == 'alfworld':
            return receipt('<action>look</action>')
        notes = 'Compare the supplied constraints carefully.' in user
        if bench == 'zebralogic':
            return receipt(json.dumps({'reasoning': 'Authored fixture.', 'solution': templates[bench]['private']['answer']}) if notes else '{}')
        if bench == 'spreadsheetbench':
            return receipt("```python\nimport openpyxl\nb = openpyxl.load_workbook('input.xlsx')\n"
                "b.active['B1'] = 15\nb.save('output.xlsx')\n# " + ('AUTHORED_RIGHT' if notes else 'AUTHORED_WRONG') + '\n```')
        return receipt('<answer>Fixtown 0</answer>' if bench == 'searchqa' else '<answer>200</answer>')
    def endpoint(bench):
        return Endpoint(SimpleNamespace(call=partial(answer, bench)), model=p.CHAINS['G'],
            max_tokens=p.solver_tokens(p.CHAINS['G'], bench),
            slots=Slots(root/'provider-slots', p.CHAINS['G'], 1), sleep=lambda _: None)
    monkeypatch.setattr(step._Step, 'solver', lambda st, *a, cell_bench=None, **kw: endpoint(cell_bench or st.bench))
    def roles(st, role):
        made = Roles(st, scenario, seen)
        if st.calls is not None:
            st.calls.append(made)
        return made
    monkeypatch.setattr(step._Step, 'roles', roles)
    monkeypatch.setattr(units, 'audit_judges', lambda *a: {'G': Judge(), 'D': Judge()})
    def slices(st):
        cut = cuts[st.bench]
        write_json(st.root/step.SLICES_FILE, p.record('step-slices', st.evidence, {
            'chain': st.chain, 'k': st.k, 'bench': st.bench,
            'slices': {key: [row['task_id'] for row in rows] for key, rows in cut.items()}}))
        return cut
    monkeypatch.setattr(step, '_slices', slices)
    monkeypatch.setattr(step, '_diagnose', lambda st, cut: st.unit('diagnose', lambda _: {'detectors': []}))
    def generate(st, cut):
        generated = [p.record('generated-item', st.evidence, {'id': 'generated-' + st.bench + str(n),
            'task_id': 'generated-' + st.bench + str(n), 'benchmark': st.bench, 'public': deepcopy(row['public']), 'private': deepcopy(row['private'])})
            for n, row in enumerate(cut['run'][:3])]
        return st.unit('generate', lambda _: {'mode': 'families', 'generator': None, 'g_self': generated})
    monkeypatch.setattr(step, '_generate', generate)
    setting = units.Setting(run=digest(['authored-main-v10-chain', scenario]), root=root, shared=root/'shared',
        pools=pools, cards={b: v222_cards.format_text(b) for b in p.MAIN_V5_ORDER}, runtime=runtime,
        clients=None, budget=None, slots={name: Pool() for name in (slots.LIVE, slots.CALL, slots.NATIVE, slots.EPISODE)},
        sandbox={}, evidence='engineering_fixture', workers=1,
        extra={'configuration': p.MAIN_V10, 'slot_root': root/'slots',
               'alfworld_v11_import': v210_import.pins(), 'v211_prompt_pins': engineer_v211.pins()})
    services = step.Services(registry=Registry(root/'registry', evidence=setting.evidence), sources=None,
                             workers=workers, sleep=lambda _: None)
    write_json(setting.shared/'consent.json', {'test_evaluation': True, 'sheet_test_qualification': True,
        'multi_arm_arms': list(read.ARMS), 'by': 'owner', 'date': '2026-11-09', 'note': 'Authored offline fixture.'})
    launched = []
    def launch(setting, spec):
        bench, event = spec['bench'], spec['label']
        pkg = package.load(root/'G/packages'/(spec['package_sha256'] + '.json'))
        unit_root = Path(spec['unit_root'])
        context = units.cell_context(setting, unit_root/'attempt-1', endpoint(bench))
        def panel(pinned, found, *, access):
            return [deepcopy(templates[found])], {'panel_hash': digest(templates[found]),
                'excluded_without_pages': [], 'source_files': []}
        result = read.evaluate_unit(unit_root, event=event, run=setting.run, shared=setting.shared, pinned=None,
            chain='G', bench=bench, chosen=read.arms(pkg, event, chain='G', evidence=setting.evidence),
            context=context, workers=1, canaries=[], panel=panel)
        write_json(read.status_path(setting, 'G', event, bench), p.record('read-status', setting.evidence, {
            'run': setting.run, 'chain': 'G', 'bench': bench, 'label': event, 'status': 'complete',
            'package_sha256': pkg.sha256, 'unit_sha256': result[p.RECORD_HASH]}))
        launched.append((event, bench))
        return 0
    result = read.run(setting, 'G', learn=partial(step.learn, services=services), launch=launch)
    if result['status'] == 'paused':
        result['diagnostics'] = [f.read_text() for f in root.rglob('diagnostics.log')]
    return result, SimpleNamespace(setting=setting, opened=opened, seen=seen, requests=requests, reads=launched)


@pytest.mark.parametrize('scenario', ['normal', 'isolated', 'systematic'])
def test_authored_main_v10_chain_accepts_zebra_then_sheet_and_imports_alfworld(tmp_path, monkeypatch, scenario):
    result, found = authored_chain(tmp_path/'run', monkeypatch, scenario)
    assert result['status'] == ('paused' if scenario == 'systematic' else 'complete'), json.dumps(result, indent=2)
    chain_root = found.setting.root/'G'
    zebra = p.verified(read_json(chain_root/'s3-zebralogic/step.json'), 'step')
    assert zebra['decision'] == 'accept' and zebra['reason'] == 'immediate_acceptance_last_incumbent', json.dumps(zebra, indent=2)
    sheet_root = chain_root/'s4-spreadsheetbench'
    if scenario == 'systematic':
        assert result['kind'] == 'configuration' and result['reason'] == 'ValueError'
        assert sum(v226_candidates.counts(sheet_root).values()) == 2
        assert not (chain_root/'s5-alfworld/step.json').exists()
        return
    sheet = p.verified(read_json(sheet_root/'step.json'), 'step')
    assert sheet['decision'] == 'accept' and sheet['reason'] == 'immediate_acceptance_last_incumbent', json.dumps(sheet, indent=2)
    assert (sheet_root/'selftest/unit.json').exists()
    assert (sheet_root/'accept-r2/unit.json' if scenario == 'isolated' else sheet_root/'accept-r1/unit.json').exists()
    assert sum(sheet['candidate_errors'].values()) == int(scenario == 'isolated')
    if scenario == 'isolated':
        assert sheet['candidate_error_events'] == [{'kind': 'candidate_error', 'exception': 'ValueError',
            'where': __name__ + ':call'}]
        assert sheet['training']['rounds'][0]['reason'] == 'candidate_error'
        assert sheet['training']['rounds'][1]['adopted']
    imported = p.verified(read_json(chain_root/'s5-alfworld/step.json'), 'step')
    assert imported['decision'] == 'import' and imported['learning'] == 'import'
    assert len(found.reads) == 40
    assert all((chain_root/'test'/event/bench/'unit.json').exists()
               for event in read.EVENTS for bench in p.MAIN_V5_ORDER)
    # A spreadsheet engineer executes the earlier Zebra trajectory on a bound
    # diagnostics worker (the original K2 pause), with the real worker semantics.
    replay_workers = [w for w in found.opened if w.tag in {units.unit_tag('G', 'G/s4-spreadsheetbench/engineer-r%d' % n) for n in range(1, 7)}]
    assert any(call[1] == 'before_call' and call[-1] for w in replay_workers for call in w.calls)
    assert all(w.diagnostics_configuration == p.ZEBRA_PC_V15 for w in replay_workers)
