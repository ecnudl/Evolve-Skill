"""Candidate-attributable cross harm with real routing and hook execution."""
from contextlib import contextmanager
from dataclasses import replace

import pytest

from skillopt.execskill import policy, profiles as p, v222_gate as gate, v225_cards
from skillopt.execskill.package import empty, with_
from tests.execskill_fakes_env import procedure
from tests.execskill_v226_fakes import DiagnosticsWorker
from tests.test_execskill_v225_routing import VIEWS


def packages(card=False):
    base = empty(step='G/s0', evidence='engineering_fixture')
    old = procedure('fx-inherited-zebra', ('applies', 'before_call'), origin='zebralogic',
        policy_version=policy.POLICY_VERSION_V222,
        source="def applies(view):\n    return 'columns' in view\n\ndef before_call(view, state):\n    return {'facts': ['Compare the constraints.']}\n")
    parent = with_(base, step='G/s3-zebralogic', add=[old])
    new = (v225_cards.make_card('spreadsheetbench', 'Check the supplied values.') if card else
        procedure('fx-sheet-candidate', ('applies', 'before_call'), origin='spreadsheetbench',
            policy_version=policy.POLICY_VERSION_V222,
            source="def applies(view):\n    return 'instruction' in view\n\ndef before_call(view, state):\n    return {'facts': ['Check the supplied values.']}\n"))
    return parent, with_(parent, step='G/s4-spreadsheetbench', add=[new])


def slices():
    return {bench: [{'task_id': bench + '-%02d' % n, 'public': VIEWS[bench]}
                    for n in range(18)] for bench in gate.BENCHES}


def inspector(parent, *, fault='timeout', flaky=False, new_fault=None, configuration='main-v10'):
    def inspect(bench, before, after, items):
        @contextmanager
        def workers(package, key):
            class FaultWorker(DiagnosticsWorker):
                def call(self, proc_id, fn, args, **kw):
                    if fn == 'before_call' and key == 'zebralogic-00':
                        inherited = proc_id == 'fx-inherited-zebra' and (not flaky or package.sha256 == parent.sha256)
                        if inherited or proc_id == new_fault:
                            return {'ok': False, 'fault': fault, 'exc_type': 'RuntimeError' if fault == 'exception' else None,
                                    'message': 'authored inherited failure', 'line': 1}
                    return super().call(proc_id, fn, args, **kw)
            worker = FaultWorker(diagnostics_configuration=p.ZEBRA_PC_V15).start(package)
            try:
                yield worker
            finally:
                worker.close()
        return gate.inspect(bench, before, after, items, workers,
            views={row['task_id']: VIEWS[bench] for row in items}, configuration=configuration)
    return inspect


def paired(items, *, harmful=False):
    return {(arm, row['task_id']): [{'judge': {'v2': {'token': 'pass' if harmful and arm == 'S' else 'fail'}}}]
            for row in items for arm in ('S', "S'")}


@pytest.mark.parametrize('card', [False, True])
@pytest.mark.parametrize('fault', ['timeout', 'exception'])
def test_inherited_zebra_fault_does_not_reject_sheet_procedure_or_card(card, fault):
    parent, candidate = packages(card)
    seen = []
    def run(bench, _before, _after, items):
        seen.append(bench)
        return paired(items)
    found, record = gate.check(home='spreadsheetbench', parent=parent, candidate=candidate,
        slices=slices(), inspector=inspector(parent, fault=fault), run_pairs=run,
        phase='acceptance', configuration='main-v10')
    zebra = record['benches']['zebralogic']
    assert found == candidate and record['passed']
    assert zebra['identity_proven'] and zebra['candidate_faults'] == []
    assert len(zebra['inherited_faults']) == 2 and not seen


def test_flaky_inherited_fault_with_a_changed_request_is_measured():
    parent, candidate = packages()
    seen = []
    def run(bench, _before, _after, items):
        seen.append((bench, [row['task_id'] for row in items]))
        return paired(items)
    found, record = gate.check(home='spreadsheetbench', parent=parent, candidate=candidate,
        slices=slices(), inspector=inspector(parent, flaky=True), run_pairs=run,
        phase='acceptance', configuration='main-v10')
    assert found == candidate and record['passed']
    assert seen == [('zebralogic', ['zebralogic-00'])]
    assert len(record['benches']['zebralogic']['inherited_faults']) == 1


def test_candidate_only_fault_still_rejects_even_with_identical_inherited_fault():
    parent, candidate = packages()
    added = replace(parent.procedures[0], id='fx-new-zebra', description='A new faulty hook.')
    candidate = with_(candidate, step=candidate.step, add=[added])
    found, record = gate.check(home='spreadsheetbench', parent=parent, candidate=candidate,
        slices=slices(), inspector=inspector(parent, new_fault=added.id),
        run_pairs=lambda _b, _p, _c, items: paired(items), narrower=lambda *a, **kw: None,
        phase='acceptance', configuration='main-v10')
    zebra = record['benches']['zebralogic']
    assert found is None and not record['passed']
    assert zebra['reason'] == 'routing_fault'
    assert [row['procedure'] for row in zebra['candidate_faults']] == [added.id]
    assert len(zebra['inherited_faults']) == 2


def test_changed_procedure_cannot_claim_its_matching_fault_is_inherited():
    parent, _ = packages()
    changed = replace(parent.procedures[0], source=parent.procedures[0].source + '\n# Changed implementation.\n')
    candidate = replace(parent, procedures=(changed,))
    rows = slices()['zebralogic']
    found = inspector(parent)('zebralogic', parent, candidate, rows)
    assert found['candidate_faults'][0]['procedure'] == changed.id
    assert len(found['candidate_faults']) == len(found['inherited_faults']) == 1
    assert not found['identity_proven']


def test_narrowing_recheck_ignores_identical_inherited_faults():
    parent, candidate = packages()
    old = candidate.procedures[-1]
    revised = replace(old, source="def applies(view):\n    return 'context' in view or 'instruction' in view\n\ndef before_call(view, state):\n    return {'facts': ['Check the supplied values.']}\n")
    candidate = replace(candidate, procedures=candidate.procedures[:-1] + (revised,))
    found, record = gate.check(home='spreadsheetbench', parent=parent, candidate=candidate,
        slices=slices(), inspector=inspector(parent),
        run_pairs=lambda bench, _p, _c, items: paired(items, harmful=bench == 'officeqa'),
        phase='acceptance', configuration='main-v10')
    assert found is not None and found.sha256 != candidate.sha256 and record['passed']
    zebra = record['narrowing']['rechecked']['zebralogic']
    assert zebra['passed'] and zebra['identity_proven'] and len(zebra['inherited_faults']) == 2


def test_frozen_main_v9_still_rejects_an_inherited_fault():
    parent, candidate = packages()
    _, record = gate.check(home='spreadsheetbench', parent=parent, candidate=candidate,
        slices=slices(), inspector=inspector(parent, configuration='main-v9'),
        run_pairs=lambda _b, _p, _c, items: paired(items),
        phase='acceptance', configuration='main-v9')
    assert not record['passed'] and record['benches']['zebralogic']['reason'] == 'routing_fault'
    assert 'inherited_faults' not in record['benches']['zebralogic']
