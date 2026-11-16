"""Card identities use the real worker factory, shell renderer and solver dispatch."""
from contextlib import contextmanager
from types import SimpleNamespace
import json
from pathlib import Path

import pytest

from skillopt.coevo5.calls import _request_hash
from skillopt.execskill import acceptance, profiles as p, solver, step, v222_cards, v225_phase
from skillopt.execskill.package import empty, with_
from skillopt.execskill.v225_cards import make_card
from skillopt.validator_pilot.api import digest
from tests.execskill_fakes_env import FakeSandbox, alf_sessions
from tests.execskill_v293_fakes import tmp_path  # noqa: F401
from tests.test_execskill_v225_anchor_environment import task_for


class FirstRequest(BaseException):
    pass


def fixture_step(root, bench):
    """Only native resources are fake; _item_workers and all identity code remain real."""
    task = task_for(root, bench)
    if bench == 'alfworld':
        game = json.loads(Path(task['public']['game_file']).read_text())
        view = solver.alfworld_routing_view(game['initial_observation'], game['admissible_commands'])
        task['public'].update(routing_view=view, routing_view_sha256=digest(view))
    created = []
    @contextmanager
    def workers(package, *, kind, inputs_dir=None, **options):
        worker = FakeSandbox().start(package, kind=kind, inputs_dir=inputs_dir)
        created.append({'worker': worker, 'kind': kind, 'inputs_dir': inputs_dir, **options})
        try:
            yield worker
        finally:
            worker.close()
    st = SimpleNamespace(bench=bench, setting=SimpleNamespace(
        extra={'configuration': 'main-v10'}, cards={bench: v222_cards.format_text(bench)}),
        services=SimpleNamespace(item_workers=None, workers=workers), runtime=lambda: {})
    parent = empty(step='G/s0', evidence='engineering_fixture')
    candidate = with_(parent, step='G/s1', add=[make_card(bench, 'Compare all supplied constraints carefully.')])
    return st, task, parent, candidate, created


def sent_request(st, task, candidate):
    calls = []
    def call(system, user):
        calls.append((system, user))
        raise FirstRequest()
    with pytest.raises(FirstRequest):
        solver.solve(st.bench, task['public'], st.setting.cards[st.bench], candidate, call,
            runtime=st.runtime(), configuration='main-v10', worker=FakeSandbox())
    assert len(calls) == 1
    return _request_hash(*calls[0])


@pytest.mark.parametrize('bench', p.MAIN_V5_ORDER)
def test_real_pair_signatures_card_full_touch_equals_solver_request_on_every_bench(tmp_path, monkeypatch, bench):
    alf_sessions(monkeypatch)
    st, task, parent, candidate, workers = fixture_step(tmp_path, bench)
    key, public = task['task_id'], task['public']
    view = solver.routing_view(bench, public, runtime=st.runtime())
    identities = step._pair_signatures(st, candidate, parent, {key: public}, [(key, view)])
    assert v225_phase.request_changed(identities) == [key]
    assert identities[key]["S'"]['request_sha256'] == sent_request(st, task, candidate)
    assert identities[key]["S'"]['faults'] == []
    assert len(workers) == 2 and all(row['worker'].closed for row in workers)
    if bench == 'spreadsheetbench':
        assert all(row['inputs_dir'] is not None for row in workers)
    # Identity support does not add an ALFWorld learning phase.
    assert p.train_rounds('main-v10', 'alfworld') == 0


@pytest.mark.parametrize('bench', p.MAIN_V5_ORDER[:-1])
def test_acceptance_seals_composed_card_request_as_sent_by_solver(tmp_path, monkeypatch, bench):
    st, task, parent, candidate, _ = fixture_step(tmp_path, bench)
    key, public = task['task_id'], task['public']
    view = solver.routing_view(bench, public, runtime=st.runtime())
    sealed = acceptance.prepare(tmp_path/'decision', chain='G', bench=bench,
        step='G/s1', unit='G/s1/accept-r1', candidate=candidate, parent=parent,
        views={key: view}, blocks={key: 'block'}, workers=step._item_workers(st, {key: public}),
        trajectories=[], configuration='main-v10', initial=parent,
        rule=p.acceptance_rule('main-v10', bench),
        reuse={'card_text': st.setting.cards[bench], 'runtime': st.runtime()})
    pair = sealed['reuse']['signatures']['real'][key]
    assert pair["S'"]['request_sha256'] == sent_request(st, task, candidate)
    assert pair["S'"]['request_sha256'] != pair['S']['request_sha256']


def test_frozen_main_v9_pair_signature_retains_missing_card_configuration(tmp_path):
    st, task, parent, candidate, _ = fixture_step(tmp_path, 'searchqa')
    st.setting.extra['configuration'] = p.MAIN_V9
    key, public = task['task_id'], task['public']
    signatures = step._pair_signatures(st, candidate, parent, {key: public},
        [(key, solver.routing_view(st.bench, public))])
    assert signatures[key]["S'"] == signatures[key]['S']
