"""Request byte identities and no-worker delivery for authored card packages."""
import pytest
from contextlib import nullcontext

from skillopt.coevo5.calls import _request_hash
from skillopt.execskill import profiles as p, reuse, solver, v225_cards as c, v222_cards, v222_gate
from skillopt.execskill.package import empty, with_, withhold
from skillopt.execskill.sandbox import client

VIEWS = {'searchqa': {'question': 'Find the author.', 'context': 'Supplied evidence.'},
         'officeqa': {'question': 'How many units?', 'context': 'Supplied table.'},
         'zebralogic': {'question': 'There are 5 houses, numbered 1 to 5 from left to right, as seen from across the street. An authored grid puzzle.',
                        'columns': ['Name', 'Color']},
         'spreadsheetbench': {'instruction': 'Update the supplied workbook.', 'workbook_preview': {}},
         'alfworld': {'initial_observation': 'An authored room.', 'admissible_commands_at_reset': ['look']}}


def package(home):
    start = empty(step='G/s0', evidence='engineering_fixture')
    return with_(start, step='G/s1', add=[c.make_card(home, 'Compare the supplied constraints carefully.')])


@pytest.mark.parametrize('home', c.BENCHES)
@pytest.mark.parametrize('bench', c.BENCHES[:-1])
def test_card_routed_only_to_own_bench_request_byte_identity(home, bench):
    pkg = package(home)
    without = withhold(pkg, pkg.order)
    fmt = v222_cards.format_text(bench)
    actual = reuse.signature(bench, pkg, VIEWS[bench], None, card_text=fmt, configuration=p.MAIN_V9)
    baseline = reuse.signature(bench, without, VIEWS[bench], None, card_text=fmt, configuration=p.MAIN_V9)
    if bench != home:
        assert actual == baseline
        assert actual['request_sha256'] == _request_hash(
            solver._system(bench, fmt, {}, configuration=p.MAIN_V9), solver._user(bench, VIEWS[bench]))
    else:
        assert actual['request_sha256'] != baseline['request_sha256']
    assert not actual['enabled'] and not actual['faults']


@pytest.mark.parametrize('bench', c.BENCHES)
def test_route_card_exactly_once_before_fixed_format_block(bench):
    pkg = package(bench)
    fmt = v222_cards.format_text(bench)
    content = c.metadata(pkg.card_for(bench))['text']
    composed = c.compose(bench, fmt, pkg)
    assert composed.count(content) == 1 and composed.endswith(fmt)
    assert composed.index(content) < composed.index(fmt)
    assert c.compose(bench, '', pkg) == ''


def test_solver_card_only_package_starts_no_worker_and_matches_reuse_signature():
    pkg = package('searchqa')
    class Trap:
        def __getattr__(self, _):
            raise AssertionError('A card never starts a worker')
    calls = []
    def call(system, user):
        calls.append((system, user))
        return {'ok': True, 'finish_reason': 'stop', 'response': '<answer>authored</answer>', 'usage': {}}
    solver.solve('searchqa', VIEWS['searchqa'], v222_cards.format_text('searchqa'), pkg, call,
                 configuration=p.MAIN_V9, worker=Trap())
    assert len(calls) == 1
    sig = reuse.signature('searchqa', pkg, VIEWS['searchqa'], None,
                          card_text=v222_cards.format_text('searchqa'), configuration=p.MAIN_V9)
    assert _request_hash(*calls[0]) == sig['request_sha256']


def test_worker_load_entries_exclude_cards_and_worker_source_is_main_v8():
    pkg = package('searchqa')
    assert client._entries(pkg) == []
    assert client.worker_sha256(p.MAIN_V9) == client.worker_sha256(p.MAIN_V8)
    worker = client.Worker(instruction_configuration=p.MAIN_V9)
    worker.start(pkg, kind='cell')
    assert worker._entries == [] and not worker.names
    worker.close()


@pytest.mark.parametrize('home', c.BENCHES)
@pytest.mark.parametrize('bench', c.BENCHES)
def test_cross_inspection_proves_four_other_benches_identical_at_zero_calls(home, bench):
    pkg = package(home)
    before = withhold(pkg, pkg.order)
    rows = [{'task_id': 'authored-item', 'public': VIEWS[bench]}]
    found = v222_gate.inspect(bench, before, pkg, rows, lambda *_: nullcontext(None),
        views={'authored-item': VIEWS[bench]}, card_text=v222_cards.format_text(bench), configuration=p.MAIN_V9)
    assert found['fired'] == (1 if home == bench else 0)
    assert found['identity_proven'] is (home != bench)
    assert not found['faults']


def test_authored_views_and_cards_fixture_is_pinned():
    import json
    from pathlib import Path
    root = Path(__file__).parent / 'fixtures/execskill/v225_cards'
    assert json.loads((root / 'authored-views.json').read_text()) == VIEWS
    assert json.loads((root / 'authored-cards.json').read_text()) == {
        bench: c.metadata(package(bench).card_for(bench)) for bench in c.BENCHES}
